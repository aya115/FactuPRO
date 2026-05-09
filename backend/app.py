from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import os
import re
import tempfile
from pathlib import Path
from functools import wraps
from werkzeug.utils import secure_filename
import psycopg2
from decimal import Decimal
import jwt
import bcrypt
from datetime import datetime, timedelta

# Charger .env avant les clients API (OPENAI_API_KEY, GEMINI_API_KEY, etc.)
try:
    from dotenv import load_dotenv

    _root = Path(__file__).resolve().parent.parent
    # Charger les deux emplacements (sans break) : backend/.env peut compléter la racine
    for _p in (_root / ".env", _root / "backend" / ".env"):
        if _p.exists():
            load_dotenv(_p, override=True)
except Exception:
    pass

import google.generativeai as genai
from groq import Groq
from openai import OpenAI

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

_openai_client = None


def get_openai_client():
    global _openai_client
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    if _openai_client is None:
        _openai_client = OpenAI(api_key=key)
    return _openai_client
TRANSCRIPTION_PROVIDER = os.getenv("TRANSCRIPTION_PROVIDER", "groq").strip().lower()
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
OPENAI_WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")

_groq_stt_client = None


def _groq_api_key():
    return (os.getenv("GROQ_API_KEY") or "").strip()


def get_groq_stt_client():
    """Client Groq pour la transcription (lazy, clé lue après load_dotenv)."""
    global _groq_stt_client
    key = _groq_api_key()
    if not key:
        return None
    if _groq_stt_client is None:
        _groq_stt_client = Groq(api_key=key)
    return _groq_stt_client

# --- TTS (lecture vocale) : uniquement OpenAI (si quota OK) ---
# Défaut tts-1 : moins cher que gpt-4o-mini-tts ; surcharger via OPENAI_TTS_MODEL si besoin.
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1")
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "nova")


def _resolve_transcription_backend():
    """Retourne 'groq' ou 'openai' selon .env et les clés disponibles."""
    p = TRANSCRIPTION_PROVIDER
    has_openai = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    has_groq = bool(_groq_api_key())

    if p == "groq":
        return "groq" if has_groq else None
    if p == "openai":
        return "openai" if has_openai else None
    # auto : préférer Groq pour éviter 429 OpenAI
    if has_groq:
        return "groq"
    return "openai" if has_openai else None

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")

gemini_model = genai.GenerativeModel(
    model_name=GEMINI_MODEL
)
app = Flask(__name__)
CORS(app, supports_credentials=True)
#Configuration JWT pour l’authentification
JWT_SECRET = os.environ.get("JWT_SECRET") or "change-me-in-production-secret-key"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
VALID_ROLES = ("comptable", "superviseur", "admin")

# ================= CONFIG =================
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".json", ".xml"}

PG_HOST = os.environ.get("PG_HOST") or "localhost"
PG_PORT = int(os.environ.get("PG_PORT") or "5432")
PG_DB = os.environ.get("PG_DB") or "testdb"
PG_USER = os.environ.get("PG_USER") or "postgres"
PG_PASSWORD = os.environ.get("PG_PASSWORD") or "postgres"


def get_pg_connection():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD,
    )


def init_users_table():
    """Crée la table users si elle n'existe pas."""
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(255),
            role VARCHAR(50) NOT NULL CHECK (role IN ('comptable', 'superviseur', 'admin')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    """)
    conn.commit()
    cur.close()
    conn.close()


def init_qa_questions_table():
    """Crée la table qa_questions si elle n'existe pas (historique des questions Assistant IA)."""
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS qa_questions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            question TEXT NOT NULL,
            sql_generated TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_qa_questions_user_id ON qa_questions(user_id);
        CREATE INDEX IF NOT EXISTS idx_qa_questions_created_at ON qa_questions(created_at DESC);
    """)
    conn.commit()
    cur.close()
    conn.close()


def init_supervisor_alerts_table():
    """Crée la table des alertes destinées aux superviseurs."""
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS supervisor_alerts (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
            created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            message TEXT NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_supervisor_alerts_read_created
            ON supervisor_alerts(is_read, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_supervisor_alerts_invoice
            ON supervisor_alerts(invoice_id);
        """
    )
    conn.commit()
    cur.close()
    conn.close()


def init_invoice_tables():
    """Crée le schéma factures si absent (Docker ou première install)."""
    conn = get_pg_connection()
    cur = conn.cursor()
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id SERIAL PRIMARY KEY,
            filename TEXT,
            invoice_number TEXT,
            date_of_issue TEXT,
            seller_name TEXT,
            client_name TEXT,
            total_net NUMERIC,
            total_vat NUMERIC,
            total_gross NUMERIC,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS invoices_items (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
            description TEXT,
            quantity NUMERIC,
            net_price NUMERIC,
            net NUMERIC,
            gross NUMERIC,
            vat_percentage NUMERIC,
            category TEXT,
            account TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS invoices_corrected (
            id SERIAL PRIMARY KEY,
            original_invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
            invoice_number TEXT,
            date_of_issue DATE,
            seller_name TEXT,
            client_name TEXT,
            total_net NUMERIC,
            total_vat NUMERIC,
            total_gross NUMERIC
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS invoice_items_corrected (
            id SERIAL PRIMARY KEY,
            corrected_invoice_id INTEGER NOT NULL REFERENCES invoices_corrected(id) ON DELETE CASCADE,
            description TEXT,
            quantity NUMERIC,
            net_price NUMERIC,
            net NUMERIC,
            gross NUMERIC,
            vat_percentage NUMERIC,
            category TEXT,
            account TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS ocr_precision_details (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
            field_name TEXT NOT NULL,
            extracted_value TEXT,
            corrected_value TEXT,
            is_correct BOOLEAN,
            precision_pct NUMERIC
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_invoices_items_invoice_id ON invoices_items(invoice_id);",
        "CREATE INDEX IF NOT EXISTS idx_invoices_corrected_original ON invoices_corrected(original_invoice_id);",
        "CREATE INDEX IF NOT EXISTS idx_invoice_items_corrected_corr ON invoice_items_corrected(corrected_invoice_id);",
        "CREATE INDEX IF NOT EXISTS idx_ocr_precision_invoice ON ocr_precision_details(invoice_id);",
    ]
    for sql in stmts:
        cur.execute(sql)
    conn.commit()
    cur.close()
    conn.close()


def require_auth(f):
    """Décorateur: exige un JWT valide. Met user_id, email, role dans request.auth_user."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Token manquant ou invalide"}), 401
        token = auth_header[7:].strip()
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            request.auth_user = payload
            return f(*args, **kwargs)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expiré"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token invalide"}), 401
    return decorated

def require_role(*roles):
    """
    Si l'utilisateur est admin → accès total.
    Sinon → doit appartenir aux rôles autorisés.
    """

    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = getattr(request, "auth_user", None)

            if not user:
                return jsonify({"error": "Non authentifié"}), 401

            user_role = user.get("role")

            # ⭐ ADMIN = accès universel
            if user_role == "admin":
                return f(*args, **kwargs)

            # Sinon vérifier les rôles autorisés
            if user_role not in roles:
                return jsonify({"error": "Accès refusé"}), 403

            return f(*args, **kwargs)

        return decorated

    return wrapper

    
# ================= FONCTIONS =================
def allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


# ================= AUTH ROUTES =================

@app.route("/auth/signup", methods=["POST"])
def signup():
    """Inscription: email, password, full_name, role (comptable|superviseur|admin)."""
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        full_name = (data.get("full_name") or "").strip() or None
        role = (data.get("role") or "comptable").strip().lower()

        if not email:
            return jsonify({"error": "Email requis"}), 400
        if not re.match(r"^[\w.+-]+@[\w.-]+\.\w+$", email):
            return jsonify({"error": "Email invalide"}), 400
        if len(password) < 6:
            return jsonify({"error": "Mot de passe minimum 6 caractères"}), 400
        # Interdire création admin via signup public
        if role == "admin":
            return jsonify({"error": "Création de compte admin non autorisée"}), 403

        if role not in ("comptable", "superviseur"):
            return jsonify({"error": "Rôle invalide"}), 400

        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        init_users_table()
        conn = get_pg_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (%s, %s, %s, %s) RETURNING id, email, full_name, role",
                (email, password_hash, full_name, role),
            )
            row = cur.fetchone()
            conn.commit()
            user_id, user_email, user_name, user_role = row[0], row[1], row[2], row[3]
        except psycopg2.IntegrityError:
            conn.rollback()
            return jsonify({"error": "Cet email est déjà utilisé"}), 409
        finally:
            cur.close()
            conn.close()

        payload = {
            "user_id": user_id,
            "email": user_email,
            "role": user_role,
            "full_name": user_name,
            "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        return jsonify({
            "token": token,
            "user": {"id": user_id, "email": user_email, "full_name": user_name, "role": user_role},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/auth/signin", methods=["POST"])
def signin():
    """Connexion: email, password."""
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not email or not password:
            return jsonify({"error": "Email et mot de passe requis"}), 400

        init_users_table()
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, password_hash, full_name, role FROM users WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return jsonify({"error": "Email ou mot de passe incorrect"}), 401

        user_id, user_email, stored_hash, full_name, role = row
        if not bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
            return jsonify({"error": "Email ou mot de passe incorrect"}), 401

        payload = {
            "user_id": user_id,
            "email": user_email,
            "role": role,
            "full_name": full_name,
            "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        return jsonify({
            "token": token,
            "user": {"id": user_id, "email": user_email, "full_name": full_name, "role": role},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/auth/me", methods=["GET"])
@require_auth
def auth_me():
    """Retourne les infos utilisateur courant (pour vérifier le token)."""
    u = request.auth_user
    return jsonify({
        "user": {
            "id": u.get("user_id"),
            "email": u.get("email"),
            "full_name": u.get("full_name"),
            "role": u.get("role"),
        },
    })


# ================= ROUTES =================

@app.route("/")
def home():
    return "API Invoice OK"

@app.route("/upload", methods=["POST"])
@require_auth
@require_role("comptable")
def upload_invoice():
    try:
        if "file" not in request.files:
            return jsonify({"error": "Aucun fichier envoyé"}), 400

        file = request.files["file"]

        if file.filename == "":
            return jsonify({"error": "Nom de fichier invalide"}), 400

        if not allowed_file(file.filename):
            return jsonify({"error": "Format non supporté"}), 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # 🔥 Traitement OCR + IA
        try:
            from utils import process_files  # lazy import (évite de bloquer l'API si dépendances OCR manquantes)

            user_id = request.auth_user.get("user_id")
            # En mode upload interactif, on NE sauvegarde PAS encore en base.
            # L'utilisateur verra les données extraites et pourra les corriger
            # avant validation via /invoices/confirm.
            result = process_files([filepath], user_id=user_id, auto_save=True)
        except Exception as e:
            return (
                jsonify(
                    {
                        "error": (
                            "Le traitement OCR/IA n'est pas disponible dans cet environnement. "
                            f"Détail: {str(e)}"
                        )
                    }
                ),
                500,
            )

        # Optionnel : supprimer le fichier après traitement
        # os.remove(filepath)

        return jsonify({"processed": result})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/invoices/confirm", methods=["POST"])
@require_auth
@require_role("comptable", "superviseur", "admin")
def confirm_invoice():
    try:
        from utils import (
            save_corrected_invoice_db,
            compute_ocr_precision_db  # ← CHANGEMENT IMPORTANT
        )

        payload = request.get_json(silent=True) or {}

        invoice_id = payload.get("invoice_id")
        corrected = payload.get("corrected") or {}
        extracted = payload.get("extracted") or {}  # ← AJOUTER CECI

        if not invoice_id:
            return jsonify({"error": "invoice_id manquant"}), 400

        # ✅ Sauvegarde correction
        save_corrected_invoice_db(invoice_id, corrected)

        # ✅ Recalcul PRECISION en utilisant extracted et corrected directement
        precision_db = compute_ocr_precision_db(extracted, corrected)

        if precision_db is None:
            precision_db = 0.0

        precision_db = round(float(precision_db), 4)

        # Alerte superviseur uniquement si correction réelle par un comptable
        actor = getattr(request, "auth_user", {}) or {}
        actor_role = actor.get("role")
        manual_changes = _has_manual_changes(extracted, corrected)
        if actor_role == "comptable" and manual_changes:
            actor_id = actor.get("user_id")
            actor_name = (actor.get("full_name") or actor.get("email") or "Comptable").strip()
            try:
                init_supervisor_alerts_table()
                conn = get_pg_connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO supervisor_alerts (invoice_id, created_by_user_id, message)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        invoice_id,
                        actor_id,
                        f"Correction manuelle effectuée par {actor_name}. Merci de vérifier cette facture.",
                    ),
                )
                conn.commit()
                cur.close()
                conn.close()
            except Exception as alert_error:
                # Ne bloque pas le workflow métier si l'alerte échoue
                print(f"⚠️ Alerte superviseur non créée: {alert_error}")

        return jsonify({
            "status": "success",
            "invoice_id": invoice_id,
            "ocr_precision_pct": precision_db,
            "manual_changes": manual_changes,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/invoices/<int:invoice_id>/details", methods=["GET"])
@require_auth
@require_role("superviseur", "admin", "comptable")
def get_invoice_details(invoice_id):
    try:
        user = request.auth_user
        role = user.get("role")

        conn = get_pg_connection()
        cur = conn.cursor()

        # Vérifier les permissions
        if role == "comptable":
            cur.execute(
                "SELECT user_id FROM invoices WHERE id = %s",
                (invoice_id,)
            )
            row = cur.fetchone()
            if not row or row[0] != user.get("user_id"):
                return jsonify({"error": "Accès non autorisé"}), 403

        # Récupérer les détails de la facture
        cur.execute("""
            SELECT
                i.id,
                i.filename,
                i.invoice_number,
                i.date_of_issue,
                i.seller_name,
                i.client_name,
                i.total_net,
                i.total_vat,
                i.total_gross,
                i.user_id,
                json_agg(
                    json_build_object(
                        'item_id', it.id,
                        'description', it.description,
                        'quantity', it.quantity,
                        'net_price', it.net_price,
                        'net', it.net,
                        'gross', it.gross,
                        'vat_percentage', it.vat_percentage,
                        'category', it.category,
                        'account', it.account
                    ) ORDER BY it.id
                ) as items
            FROM invoices i
            LEFT JOIN invoices_items it ON i.id = it.invoice_id
            WHERE i.id = %s
            GROUP BY i.id
        """, (invoice_id,))

        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return jsonify({"error": "Facture non trouvée"}), 404

        columns = [
            "id", "filename", "invoice_number", "date_of_issue",
            "seller_name", "client_name", "total_net", "total_vat",
            "total_gross", "user_id", "items"
        ]

        result = {}
        for i, col in enumerate(columns):
            result[col] = _json_safe_value(row[i])

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
def _json_safe_value(v):
    # psycopg2 peut renvoyer Decimal/date/datetime: on les sérialise proprement
    if v is None:
        return None
    iso = getattr(v, "isoformat", None)
    if callable(iso):
        return v.isoformat()
    try:
        from decimal import Decimal

        if isinstance(v, Decimal):
            return float(v)
    except Exception:
        pass
    return v


def _normalize_for_compare(v):
    """Normalise une structure JSON pour comparer extracted/corrected."""
    if isinstance(v, dict):
        return {str(k): _normalize_for_compare(v[k]) for k in sorted(v.keys())}
    if isinstance(v, list):
        return [_normalize_for_compare(x) for x in v]
    if isinstance(v, (int, float, Decimal)):
        try:
            return round(float(v), 4)
        except Exception:
            return v
    if isinstance(v, str):
        return re.sub(r"\s+", " ", v).strip()
    return v


def _has_manual_changes(extracted, corrected):
    return _normalize_for_compare(extracted or {}) != _normalize_for_compare(corrected or {})
@app.route("/admin/users", methods=["POST"])
@require_auth
@require_role("admin")
def create_user():
    try:
        data = request.get_json() or {}

        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        full_name = data.get("full_name") or ""
        role = (data.get("role") or "").lower()

        if role not in ("comptable", "superviseur", "admin"):
            return jsonify({"error": "Rôle invalide"}), 400

        if len(password) < 6:
            return jsonify({"error": "Mot de passe trop court"}), 400

        password_hash = bcrypt.hashpw(
            password.encode(),
            bcrypt.gensalt()
        ).decode()

        conn = get_pg_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO users (email, password_hash, full_name, role)
            VALUES (%s,%s,%s,%s)
            RETURNING id
        """, (email, password_hash, full_name, role))

        user_id = cur.fetchone()[0]

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"id": user_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/users/<int:user_id>", methods=["PUT"])
@require_auth
@require_role("admin")
def update_user(user_id):
    try:
        data = request.get_json() or {}

        full_name = data.get("full_name")
        role = data.get("role")

        conn = get_pg_connection()
        cur = conn.cursor()

        if full_name:
            cur.execute("""
                UPDATE users
                SET full_name=%s
                WHERE id=%s
            """, (full_name, user_id))

        if role:
            if role not in ("comptable", "superviseur", "admin"):
                return jsonify({"error": "Role invalide"}), 400

            cur.execute("""
                UPDATE users
                SET role=%s
                WHERE id=%s
            """, (role, user_id))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"status": "updated"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500     

@app.route("/admin/users/<int:user_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def delete_user(user_id):
    try:
        conn = get_pg_connection()
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM users
            WHERE id=%s AND role != 'admin'
        """, (user_id,))    

        conn.commit()

        cur.close()
        conn.close()

        return jsonify({"status": "deleted"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500  
@app.route("/metrics/ocr-details/<int:invoice_id>", methods=["GET"])
@require_auth
def ocr_precision_details_api(invoice_id):

    try:
        conn = get_pg_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT field_name, extracted_value, corrected_value, is_correct
            FROM ocr_precision_details
            WHERE invoice_id = %s
            ORDER BY id ASC
        """, (invoice_id,))

        rows = cur.fetchall()

        cur.close()
        conn.close()

        data = []

        for r in rows:
            data.append({
                "field": r[0],
                "extracted": r[1],
                "corrected": r[2],
                "correct": r[3]
            })

        return jsonify({
            "invoice_id": invoice_id,
            "details": data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/supervisor/alerts", methods=["GET"])
@require_auth
@require_role("superviseur", "admin")
def list_supervisor_alerts():
    try:
        limit = int(request.args.get("limit", 20))
        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100
        only_unread = str(request.args.get("unread", "1")).strip().lower() in ("1", "true", "yes")

        init_supervisor_alerts_table()
        conn = get_pg_connection()
        cur = conn.cursor()
        where_sql = "WHERE sa.is_read = FALSE" if only_unread else ""
        cur.execute(
            f"""
            SELECT
                sa.id,
                sa.invoice_id,
                sa.created_by_user_id,
                sa.message,
                sa.is_read,
                sa.created_at,
                u.full_name,
                u.email
            FROM supervisor_alerts sa
            LEFT JOIN users u ON u.id = sa.created_by_user_id
            {where_sql}
            ORDER BY sa.created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        data = []
        for r in rows:
            data.append(
                {
                    "id": r[0],
                    "invoice_id": r[1],
                    "created_by_user_id": r[2],
                    "message": r[3],
                    "is_read": bool(r[4]),
                    "created_at": _json_safe_value(r[5]),
                    "created_by_name": r[6] or r[7] or "Utilisateur",
                }
            )

        return jsonify({"alerts": data, "count": len(data)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/supervisor/alerts/<int:alert_id>/read", methods=["PUT"])
@require_auth
@require_role("superviseur", "admin")
def mark_supervisor_alert_read(alert_id):
    try:
        init_supervisor_alerts_table()
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE supervisor_alerts
            SET is_read = TRUE
            WHERE id = %s
            RETURNING id
            """,
            (alert_id,),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not row:
            return jsonify({"error": "Alerte introuvable"}), 404
        return jsonify({"status": "ok", "id": row[0]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
def _sanitize_date_of_issue_casts(sql: str) -> str:
    """
    Remplace les casts de date_of_issue (TEXT) vers date par une forme sûre
    pour éviter l'erreur "invalid input syntax for type date" quand la valeur est ''.
    """
    # date_of_issue::date -> expression qui renvoie NULL pour chaîne vide
    safe_expr = "(NULLIF(TRIM(COALESCE(date_of_issue, '')), '')::date)"
    sql = re.sub(
        r"\bdate_of_issue\s*::\s*date\b",
        safe_expr,
        sql,
        flags=re.IGNORECASE,
    )
    # CAST(date_of_issue AS date) -> idem
    sql = re.sub(
        r"CAST\s*\(\s*date_of_issue\s+AS\s+date\s*\)",
        "CAST(NULLIF(TRIM(COALESCE(date_of_issue, '')), '') AS date)",
        sql,
        flags=re.IGNORECASE,
    )
    # to_date(date_of_issue, fmt) -> premier arg sûr (vide -> NULL)
    sql = re.sub(
        r"to_date\s*\(\s*date_of_issue\s*,",
        "to_date(NULLIF(TRIM(COALESCE(date_of_issue, '')), ''),",
        sql,
        flags=re.IGNORECASE,
    )
    return sql


def _generate_qa_explanation(question: str, columns: list, data_rows: list, kpis: list) -> str:
    """Génère une phrase d'explication des résultats (ex. 'Le top 3 représente 65% du TTC')."""
    from utils import safe_json_parse
    try:
        kpi_str = ", ".join([f"{k.get('label', '')}: {k.get('value', '')}" for k in (kpis or [])[:5]])
        prompt = (
            f"Question utilisateur: {question}\n"
            f"Colonnes du résultat: {', '.join(columns[:10])}. Nombre de lignes: {len(data_rows)}.\n"
            f"KPIs: {kpi_str}\n\n"
            "Écris UNE seule phrase courte en français qui résume le résultat (ex: 'Le top 3 des clients représente 65% du total TTC.', '28 factures correspondent à ces critères.'). Réponds UNIQUEMENT par cette phrase, sans guillemets ni préambule."
        )
        response = gemini_model.generate_content(
            contents=prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.3, top_p=1, max_output_tokens=150),
        )
        if response and response.candidates:
            raw = response.candidates[0].content.parts[0].text.strip()
            return raw[:300] if raw else ""
    except Exception:
        pass
    return ""


def _generate_qa_suggestions(question: str, columns: list, data_rows: list) -> list:
    """Génère 2 à 3 suggestions de questions de suivi."""
    from utils import safe_json_parse
    try:
        prompt = (
            f"Question posée: {question}\n"
            f"Résultat: {len(data_rows)} lignes, colonnes: {', '.join(columns[:8])}.\n\n"
            "Propose 2 ou 3 questions de suivi courtes en français que l'utilisateur pourrait poser (ex: 'Voir le détail par mois ?', 'Top 10 par montant ?', 'Filtrer par catégorie X ?'). "
            "Réponds UNIQUEMENT en JSON: {\"suggestions\": [\"question 1\", \"question 2\"]}"
        )
        response = gemini_model.generate_content(
            contents=prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.4, top_p=1, max_output_tokens=200),
        )
        if response and response.candidates:
            raw = response.candidates[0].content.parts[0].text.strip()
            spec = safe_json_parse(raw) or {}
            sug = spec.get("suggestions")
            if isinstance(sug, list):
                return [str(s).strip() for s in sug[:4] if s]
    except Exception:
        pass
    return []


def _run_invoice_qa(question: str):
    """
    Agent SQL générique:
    - 1) Demande à Groq de générer une requête SELECT Postgres sur invoices / invoices_items
    - 2) Exécute la requête
    - 3) Retourne les lignes + quelques KPIs génériques
    """
    from utils import safe_json_parse

    schema_description = """
Tu as accès à une base PostgreSQL avec le schéma suivant:

TABLE invoices (
    id INTEGER PRIMARY KEY,
    filename TEXT,
    invoice_number TEXT,
    date_of_issue TEXT,
    seller_name TEXT,
    client_name TEXT,
    total_net NUMERIC,
    total_vat NUMERIC,
    total_gross NUMERIC
);

TABLE invoices_items (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER REFERENCES invoices(id),
    description TEXT,
    quantity NUMERIC,
    net_price NUMERIC,
    net NUMERIC,
    gross NUMERIC,
    vat_percentage NUMERIC,
    category TEXT,
    account TEXT
);
"""

    prompt = (
        "Tu es un assistant SQL pour PostgreSQL.\n"
        "L'utilisateur pose des questions (en français ou anglais) sur les factures.\n"
        "Ton rôle est de proposer UNE requête SQL SELECT qui répond le mieux possible à la question,\n"
        "en utilisant UNIQUEMENT les tables et colonnes décrites.\n\n"
        + schema_description
        + """
Règles OBLIGATOIRES:
- Ne fais que des requêtes SELECT, jamais de INSERT/UPDATE/DELETE/DDL.
- Utilise uniquement les tables invoices et invoices_items.
- Utilise des noms de colonnes exacts.
- Utilise la syntaxe PostgreSQL standard.
- Synonymes à respecter: "montant", "total", "somme", "TTC" = totaux (total_gross ou SUM(gross)); "fournisseur", "vendeur", "vendor", "seller" = colonne seller_name; "client" = client_name; "catégorie" = category; "HT", "net" = total_net / net; "TVA" = total_vat.
- La colonne date_of_issue est de type TEXT. Pour filtrer par année/mois, utilise des comparaisons de chaînes (ex. date_of_issue LIKE '2024%' ou date_of_issue >= '2024-01-01' AND date_of_issue < '2025-01-01'). Évite de caster date_of_issue en date si des valeurs vides peuvent exister.
- Si la question demande des totaux, utilise SUM() et éventuellement GROUP BY.

Si la question est trop vague ou ambiguë (ex. "TTC catégorie" sans période, "les montants" sans précision), ne génère PAS de sql: mets "clarification" avec une courte question de clarification en français et "clarification_suggestions" avec un tableau de 2 à 4 suggestions de précision (ex. ["total TTC par catégorie pour 2024", "évolution du TTC par mois"]). Sinon génère sql, commentaire et viz.

Réponds STRICTEMENT en JSON, SANS AUCUN TEXTE AVANT OU APRÈS, au format (soit avec sql, soit avec clarification):
{
    "sql": "SELECT ...",
    "commentaire": "courte explication en français",
    "viz": { "type": "pie|bar|line|table", "labelColumn": "...", "valueColumn": "...", "title": "..." }
}
OU si question vague:
{
    "clarification": "Voulez-vous une période précise (ex. année) ou voir toutes les données ?",
    "clarification_suggestions": ["total TTC par catégorie pour 2024", "total TTC par catégorie (toutes périodes)"]
}
"""
    )

    prompt += f'\n\nQuestion utilisateur: "{question}"\n'

    from utils import safe_json_parse

    response = gemini_model.generate_content(
        contents=prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0,
            top_p=1,
            max_output_tokens=2048
        )
    )

    raw = ""
    if response and response.candidates:
        raw = response.candidates[0].content.parts[0].text.strip()
    spec = safe_json_parse(raw) or {}
    sql = (spec.get("sql") or "").strip()
    commentaire = (spec.get("commentaire") or spec.get("comment") or "").strip()
    viz = spec.get("viz") or {}
    clarification = (spec.get("clarification") or "").strip()
    clarification_suggestions = spec.get("clarification_suggestions") or []

    if clarification and (not sql or not sql.lower().lstrip().startswith("select")):
        return {
            "question": question,
            "clarification": clarification,
            "clarification_suggestions": clarification_suggestions if isinstance(clarification_suggestions, list) else [],
        }

    if not sql or not sql.lower().lstrip().startswith("select"):
        raise ValueError("Requête SQL non valide générée par l'IA.")
    # Empêche les requêtes multiples
    if ";" in sql.strip().rstrip(";"):
        raise ValueError("Requête SQL invalide (plusieurs statements).")
    # Sécurité perf: si l'IA n'a pas mis de LIMIT, on en ajoute un.
    if " limit " not in f" {sql.lower()} ":
        sql = sql.rstrip().rstrip(";") + " LIMIT 200"

    # Éviter "invalid input syntax for type date" quand date_of_issue est vide
    sql = _sanitize_date_of_issue_casts(sql)

    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    columns = [col.name for col in cur.description]
    cur.close()
    conn.close()

    data_rows = []
    for r in rows:
        obj = {columns[i]: _json_safe_value(r[i]) for i in range(len(columns))}
        data_rows.append(obj)

    def _is_number(x):
        return isinstance(x, (int, float, Decimal))

    kpis = [{"label": "Nombre de lignes", "value": len(data_rows)}]
    if data_rows:
        sample = data_rows[0]
        for key in sample.keys():
            col_vals = [row.get(key) for row in data_rows if _is_number(row.get(key))]
            if not col_vals:
                continue
            total = float(sum(col_vals))
            kpis.append({"label": f"Somme de {key}", "value": total})
            if len(kpis) >= 4:
                break

    explanation = _generate_qa_explanation(question, columns, data_rows, kpis)
    suggestions = _generate_qa_suggestions(question, columns, data_rows)

    return {
        "question": question,
        "sql": sql,
        "commentaire": commentaire,
        "viz": viz,
        "columns": columns,
        "rows": data_rows[:500],
        "kpis": kpis,
        "explanation": explanation,
        "suggestions": suggestions,
    }


@app.route("/invoices", methods=["GET"])
@require_auth
@require_role("superviseur", "admin", "comptable")
def list_invoices():
    try:
        user = request.auth_user
        role = user.get("role")

        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        q = (request.args.get("q") or "").strip()

        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200
        if offset < 0:
            offset = 0

        where_sql = " WHERE 1=1 "
        params = []

        # ✅ Recherche globale
        if q:
            like = f"%{q}%"
            where_sql += """
                AND (
                    i.filename ILIKE %s OR
                    i.invoice_number ILIKE %s OR
                    i.seller_name ILIKE %s OR
                    i.client_name ILIKE %s OR
                    it.description ILIKE %s
                )
            """
            params.extend([like, like, like, like, like])

        # ⭐ Filtre COMPTABLE → seulement ses factures
        if role == "comptable":
            where_sql += " AND i.user_id = %s "
            params.append(user.get("user_id"))

        conn = get_pg_connection()
        cur = conn.cursor()

        # Count total
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM invoices_items AS it
            JOIN invoices AS i ON it.invoice_id = i.id
            {where_sql}
            """,
            params,
        )

        total = cur.fetchone()[0]

        # Data query
        cur.execute(
            f"""
            SELECT
                i.id AS invoice_id,
                i.user_id,
                it.id AS item_id,
                i.filename,
                i.invoice_number,
                i.date_of_issue,
                i.seller_name,
                i.client_name,
                it.description,
                it.quantity,
                it.net_price,
                it.net,
                it.gross,
                it.vat_percentage,
                it.category,
                it.account
            FROM invoices_items AS it
            JOIN invoices AS i ON it.invoice_id = i.id
            {where_sql}
            ORDER BY i.id DESC, it.id ASC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )

        rows = cur.fetchall()

        columns = [
            "invoice_id",
            "user_id",
            "item_id",
            "filename",
            "invoice_number",
            "date_of_issue",
            "seller_name",
            "client_name",
            "description",
            "quantity",
            "net_price",
            "net",
            "gross",
            "vat_percentage",
            "category",
            "account",
        ]

        data = []
        for r in rows:
            obj = {columns[i]: _json_safe_value(r[i]) for i in range(len(columns))}
            data.append(obj)

        cur.close()
        conn.close()

        return jsonify({
            "total": total,
            "limit": limit,
            "offset": offset,
            "data": data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/qa", methods=["POST"])
@require_auth
def invoice_qa():
    """
    Endpoint d'agent IA générique pour questions sur les factures.
    Body JSON: { "question": "..." }
    Enregistre la question en base (table qa_questions) avec l'id de l'utilisateur.
    """
    try:
        payload = request.get_json(silent=True) or {}
        question = (payload.get("question") or "").strip()
        if not question:
            return jsonify({"error": "Champ 'question' manquant"}), 400

        result = _run_invoice_qa(question)

        if "clarification" not in result:
            init_qa_questions_table()
            user_id = request.auth_user.get("user_id")
            if user_id:
                conn = get_pg_connection()
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO qa_questions (user_id, question, sql_generated) VALUES (%s, %s, %s)",
                    (user_id, question, result.get("sql")),
                )
                conn.commit()
                cur.close()
                conn.close()

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/audio/transcribe", methods=["POST"])
@require_auth
def audio_transcribe():
    """
    Speech-to-Text : Groq Whisper par défaut (whisper-large-v3-turbo), ou OpenAI (whisper-1).
    multipart/form-data: champ 'file' = enregistrement audio (webm, mp3, wav, etc.)
    """
    backend = _resolve_transcription_backend()
    if backend is None:
        hint = (
            "Configurez GROQ_API_KEY dans .env (recommandé, fichier à la racine du projet ou backend/.env), "
            "puis redémarrez Flask. Pour forcer OpenAI : TRANSCRIPTION_PROVIDER=openai."
        )
        if TRANSCRIPTION_PROVIDER == "groq":
            hint = "TRANSCRIPTION_PROVIDER=groq mais GROQ_API_KEY est vide ou absent. Ajoutez la clé Groq dans .env."
        return jsonify({"error": f"Aucun service de transcription disponible. {hint}"}), 503
    if "file" not in request.files:
        return jsonify({"error": "Fichier audio manquant (champ 'file')"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "Fichier audio invalide"}), 400
    raw = f.read()
    if not raw or len(raw) < 50:
        return jsonify({"error": "Audio trop court ou vide"}), 400
    suffix = os.path.splitext(secure_filename(f.filename) or "audio")[1].lower() or ".webm"
    if suffix not in (".webm", ".mp3", ".wav", ".m4a", ".mp4", ".mpeg", ".mpga", ".oga", ".ogg"):
        suffix = ".webm"
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=suffix)
        os.write(fd, raw)
        os.close(fd)

        if backend == "groq":
            gclient = get_groq_stt_client()
            if not gclient:
                return jsonify({"error": "Client Groq indisponible (GROQ_API_KEY)."}), 503
            with open(tmp, "rb") as audio_fp:
                transcription = gclient.audio.transcriptions.create(
                    model=GROQ_WHISPER_MODEL,
                    file=audio_fp,
                    language="fr",
                )
            model_used = GROQ_WHISPER_MODEL
        else:
            oclient = get_openai_client()
            if not oclient:
                return jsonify({"error": "OPENAI_API_KEY manquant (configuration serveur)"}), 503
            with open(tmp, "rb") as audio_fp:
                transcription = oclient.audio.transcriptions.create(
                    model=OPENAI_WHISPER_MODEL,
                    file=audio_fp,
                    language="fr",
                )
            model_used = OPENAI_WHISPER_MODEL

        text = (transcription.text or "").strip()
        return jsonify({"text": text, "model": model_used, "backend": backend})
    except Exception as e:
        return jsonify({"error": f"Transcription: {str(e)}"}), 500
    finally:
        if tmp and os.path.isfile(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


@app.route("/audio/speak", methods=["POST"])
@require_auth
def audio_speak():
    """
    Text-to-Speech via OpenAI (gpt-4o-mini-tts par défaut).
    JSON: { "text": "...", "voice": "nova" (optionnel) }
    Réponse: audio/mpeg
    """
    if not os.getenv("OPENAI_API_KEY"):
        return jsonify({"error": "OPENAI_API_KEY manquant (configuration serveur)"}), 503
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Champ 'text' manquant ou vide"}), 400
    # Limite prudente (tokens TTS)
    text = text[:4096]
    voice = (payload.get("voice") or OPENAI_TTS_VOICE or "nova").strip()
    allowed_voices = {
        "alloy", "ash", "ballad", "coral", "echo", "fable", "nova",
        "onyx", "sage", "shimmer", "verse", "marin", "cedar",
    }
    if voice not in allowed_voices:
        voice = OPENAI_TTS_VOICE if OPENAI_TTS_VOICE in allowed_voices else "nova"
    try:
        oclient = get_openai_client()
        if not oclient:
            return jsonify({"error": "OPENAI_API_KEY manquant (configuration serveur)"}), 503
        speech = oclient.audio.speech.create(
            model=OPENAI_TTS_MODEL,
            voice=voice,
            input=text,
            response_format="mp3",
        )
        audio_bytes = speech.content
        return Response(
            audio_bytes,
            mimetype="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )
    except Exception as e:
        return jsonify({"error": f"Synthèse vocale: {str(e)}"}), 500


@app.route("/metrics", methods=["GET"])
@require_auth
@require_role("superviseur", "admin")
def get_metrics():
    """
    Retourne les métriques du pipeline (OCR, classification, temps, anomalies).
    Pour override la précision OCR (évaluation externe): ?ocr_precision=95.5
    """
    try:
        from metrics import get_all_metrics

        ocr_override = request.args.get("ocr_precision", type=float)
        result = get_all_metrics(ocr_precision_override=ocr_override)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/analytics", methods=["GET"])
@require_auth
@require_role("admin")
def admin_analytics():
    """
    Statistiques agrégées pour le tableau de bord Admin.
    - Nombre total de factures
    - Nombre de vendeurs (seller_name distincts)
    - Nombre de clients (client_name distincts)
    - Nombre de catégories (category distinctes)
    - Répartition des factures par catégorie
    - Top clients par nombre de factures
    """
    try:
        conn = get_pg_connection()
        cur = conn.cursor()

        # Totaux simples
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_invoices,
                COUNT(DISTINCT COALESCE(seller_name, '')) FILTER (WHERE seller_name IS NOT NULL AND seller_name <> '') AS total_sellers,
                COUNT(DISTINCT COALESCE(client_name, '')) FILTER (WHERE client_name IS NOT NULL AND client_name <> '') AS total_clients
            FROM invoices
            """
        )
        row = cur.fetchone()
        total_invoices = int(row[0] or 0)
        total_sellers = int(row[1] or 0)
        total_clients = int(row[2] or 0)

        # Catégories (via lignes d'articles)
        cur.execute(
            """
            SELECT
                COALESCE(NULLIF(TRIM(category), ''), 'Sans catégorie') AS category,
                COUNT(DISTINCT invoice_id) AS invoice_count
            FROM invoices_items
            GROUP BY COALESCE(NULLIF(TRIM(category), ''), 'Sans catégorie')
            ORDER BY invoice_count DESC, category ASC
            """
        )
        rows_cat = cur.fetchall()
        invoices_per_category = [
            {
                "category": r[0],
                "invoice_count": int(r[1] or 0),
            }
            for r in rows_cat
        ]
        total_categories = len(invoices_per_category)

        # Top clients par nombre de factures
        cur.execute(
            """
            SELECT
                COALESCE(NULLIF(TRIM(client_name), ''), 'Client inconnu') AS client_name,
                COUNT(*) AS invoice_count
            FROM invoices
            GROUP BY COALESCE(NULLIF(TRIM(client_name), ''), 'Client inconnu')
            ORDER BY invoice_count DESC, client_name ASC
            LIMIT 8
            """
        )
        rows_clients = cur.fetchall()
        invoices_per_client = [
            {
                "client_name": r[0],
                "invoice_count": int(r[1] or 0),
            }
            for r in rows_clients
        ]

        cur.close()
        conn.close()

        return jsonify(
            {
                "totals": {
                    "invoices": total_invoices,
                    "sellers": total_sellers,
                    "clients": total_clients,
                    "categories": total_categories,
                },
                "invoices_per_category": invoices_per_category,
                "invoices_per_client": invoices_per_client,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/users", methods=["GET"])
@require_auth
@require_role("admin")
def list_users():
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, email, full_name, role FROM users")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    users = []
    for r in rows:
        users.append({
            "id": r[0],
            "email": r[1],
            "full_name": r[2],
            "role": r[3]
        })

    return jsonify({"users": users})
# ================= MAIN =================
def run_migrations():
    """Applique les migrations (user_id sur invoices)."""
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS user_id INTEGER;")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS supervisor_alerts (
                id SERIAL PRIMARY KEY,
                invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
                created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                message TEXT NOT NULL,
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_supervisor_alerts_read_created ON supervisor_alerts(is_read, created_at DESC);"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_supervisor_alerts_invoice ON supervisor_alerts(invoice_id);")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️ Migration user_id: {e}")


if __name__ == "__main__":
    init_users_table()
    init_invoice_tables()
    init_supervisor_alerts_table()
    run_migrations()
    _debug = os.environ.get("FLASK_DEBUG", "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    app.run(debug=_debug, host="0.0.0.0", port=5000)