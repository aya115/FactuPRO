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
import threading
import json

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


_openrouter_client = None
OPENROUTER_CHAT_MODEL = os.getenv(
    "OPENROUTER_CHAT_MODEL", "google/gemini-2.0-flash-001"
)


def get_openrouter_client():
    """Client OpenAI-compatible pour OpenRouter (messagerie intelligente)."""
    global _openrouter_client
    key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return None
    if _openrouter_client is None:
        _openrouter_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
        )
    return _openrouter_client


def _openrouter_chat_generate(prompt, *, max_tokens=400, temperature=0.3):
    """Génération texte via OpenRouter — utilisé par la messagerie uniquement."""
    client = get_openrouter_client()
    if not client:
        return None
    extra_headers = {}
    app_url = (os.getenv("OPENROUTER_APP_URL") or "http://localhost:3000").strip()
    app_name = (os.getenv("OPENROUTER_APP_NAME") or "FactuPRO").strip()
    if app_url:
        extra_headers["HTTP-Referer"] = app_url
    if app_name:
        extra_headers["X-Title"] = app_name
    response = client.chat.completions.create(
        model=OPENROUTER_CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        extra_headers=extra_headers or None,
    )
    if not response.choices:
        return None
    return (response.choices[0].message.content or "").strip()


def _openrouter_available():
    return bool((os.getenv("OPENROUTER_API_KEY") or "").strip())
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


def init_chat_messages_table():
    """Messagerie directe comptable ↔ superviseur."""
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            receiver_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_chat_messages_pair_created
            ON chat_messages(sender_id, receiver_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_receiver_unread
            ON chat_messages(receiver_id, is_read);
        """
    )
    cur.execute(
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;"
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
            issue_date DATE,
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
            precision_pct NUMERIC,
            logged_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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


@app.route("/internal/prometheus/metrics", methods=["GET"])
def prometheus_metrics():
    """
    Métriques au format Prometheus (scraping interne Docker / réseau privé).
    Ne pas exposer sur Internet sans protection.
    """
    try:
        from prometheus_export import prometheus_metrics_response

        return prometheus_metrics_response()
    except Exception as e:
        return Response(f"# error: {e}\n", mimetype="text/plain; charset=utf-8"), 500


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
            try:
                from prometheus_export import record_upload_error

                record_upload_error()
            except Exception:
                pass
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

        try:
            from prometheus_export import record_upload_success

            record_upload_success()
        except Exception:
            pass

        return jsonify({"processed": result})

    except Exception as e:
        try:
            from prometheus_export import record_upload_error

            record_upload_error()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@app.route("/invoices/confirm", methods=["POST"])
@require_auth
@require_role("comptable", "superviseur", "admin")
def confirm_invoice():
    try:
        from utils import save_corrected_invoice_db

        payload = request.get_json(silent=True) or {}

        invoice_id = payload.get("invoice_id")
        corrected = payload.get("corrected") or {}
        extracted = payload.get("extracted") or {}

        if not invoice_id:
            return jsonify({"error": "invoice_id manquant"}), 400

        # Sauvegarde + précision OCR : même calcul que `ocr_precision_details` (pas le JSON brut du navigateur).
        _, precision_db = save_corrected_invoice_db(invoice_id, corrected)

        if precision_db is None:
            precision_db = 0.0

        precision_db = round(float(precision_db), 4)

        print(
            f"[confirm] invoice_id={invoice_id} precision_db={precision_db}% "
            f"(extracted keys={list(extracted.keys())[:8]}, corrected keys={list(corrected.keys())[:8]})",
            flush=True,
        )

        # Alimente runtime_metrics.json → factupro_ocr_precision_pct (Prometheus / Grafana)
        try:
            from metrics import update_structured_accuracy

            update_structured_accuracy(precision_db, pipeline_json=corrected)
        except Exception as met_e:
            print(f"⚠️ Métrique ocr_scores non mise à jour: {met_e}", flush=True)

        # Alerte superviseur uniquement si correction réelle par un comptable
        actor = getattr(request, "auth_user", {}) or {}
        actor_role = actor.get("role")
        manual_changes = _has_manual_changes(extracted, corrected)

        try:
            from prometheus_export import record_confirm_success

            record_confirm_success(manual_edit=bool(manual_changes))
        except Exception:
            pass
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
                i.issue_date,
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
            "id", "filename", "invoice_number", "date_of_issue", "issue_date",
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


def _party_name(value):
    if isinstance(value, dict):
        return str(value.get("name") or "").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _item_field(item, key):
    if not isinstance(item, dict):
        return None
    aliases = {
        "gross": ("gross", "gross_worth"),
        "vat_percentage": ("vat_percentage", "vat"),
        "quantity": ("quantity", "qty"),
    }
    if key in aliases:
        for alias in aliases[key]:
            if item.get(alias) is not None:
                return item.get(alias)
        return None
    return item.get(key)


def _values_differ(v1, v2):
    from utils import _to_numeric

    n1, n2 = _to_numeric(v1), _to_numeric(v2)
    if n1 is not None and n2 is not None:
        return abs(n1 - n2) > 1e-2
    return str(v1 or "").strip() != str(v2 or "").strip()


def _has_manual_changes(extracted, corrected):
    """Détecte une vraie modification métier (pas la normalisation JSON du frontend)."""
    extracted = extracted or {}
    corrected = corrected or {}

    for key in ("invoice_number", "date_of_issue"):
        if _values_differ(extracted.get(key), corrected.get(key)):
            return True

    for key in ("seller_name", "client_name"):
        if _values_differ(_party_name(extracted.get(key)), _party_name(corrected.get(key))):
            return True

    ext_items = extracted.get("items") or []
    cor_items = corrected.get("items") or []
    if len(ext_items) != len(cor_items):
        return True

    for i in range(len(ext_items)):
        for field in ("description", "quantity", "net_price", "net", "gross", "vat_percentage"):
            if _values_differ(_item_field(ext_items[i], field), _item_field(cor_items[i], field)):
                return True

    for total_key in ("net", "vat", "gross"):
        ext_total = (extracted.get("totals") or {}).get(total_key)
        cor_total = (corrected.get("totals") or {}).get(total_key)
        if _values_differ(ext_total, cor_total):
            return True

    return False
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


CHAT_ROLES = ("comptable", "superviseur")


def _chat_partner_role(role):
    if role == "comptable":
        return "superviseur"
    if role == "superviseur":
        return "comptable"
    return None


def _can_chat_between(sender_role, receiver_role):
    return (sender_role, receiver_role) in (
        ("comptable", "superviseur"),
        ("superviseur", "comptable"),
    )


def _get_user_role(user_id):
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


def _extract_invoice_refs(text):
    """Repère les références facture (#12, facture 45) dans un message."""
    if not text:
        return []
    ids = set()
    for m in re.finditer(
        r"(?:facture|invoice)\s*#?\s*(\d{1,8})|#\s*(\d{1,8})\b",
        text,
        re.IGNORECASE,
    ):
        g = m.group(1) or m.group(2)
        if g:
            ids.add(int(g))
    return sorted(ids)


def _analyze_message_rules(content, sender_role):
    """Analyse heuristique : priorité, intention, factures citées."""
    lower = (content or "").lower()
    refs = _extract_invoice_refs(content)
    if any(w in lower for w in ("urgent", "asap", "immédiat", "bloquant", "critique")):
        priority = "urgent"
    elif any(w in lower for w in ("important", "prioritaire", "rapidement")):
        priority = "high"
    else:
        priority = "normal"
    if "?" in content or any(w in lower for w in ("pourquoi", "comment", "pouvez", "pourriez")):
        intent = "question"
    elif any(w in lower for w in ("corriger", "correction", "revoir", "erreur ocr")):
        intent = "correction"
    elif any(w in lower for w in ("valider", "validé", "approuv", "conforme", "ok pour")):
        intent = "approval"
    elif any(w in lower for w in ("merci", "reçu", "noté", "bien reçu")):
        intent = "ack"
    else:
        intent = "info"
    label_map = {
        "question": "Question",
        "correction": "Correction",
        "approval": "Validation",
        "ack": "Accusé",
        "info": "Info",
    }
    return {
        "priority": priority,
        "intent": intent,
        "intent_label": label_map.get(intent, "Info"),
        "invoice_ids": refs,
        "sender_role": sender_role,
    }


def _enrich_message_analysis_with_ai(content, base_meta, partner_role):
    """Enrichissement IA via OpenRouter — retombe sur heuristiques si indisponible."""
    if not _openrouter_available():
        return base_meta
    from utils import safe_json_parse

    try:
        prompt = (
            f"Message comptabilité ({base_meta.get('sender_role')} → {partner_role}):\n"
            f"\"{content[:800]}\"\n\n"
            "Analyse en JSON strict:\n"
            '{"priority":"normal|high|urgent","intent":"question|correction|approval|ack|info",'
            '"intent_label":"court libellé FR","tone":"neutral|positive|concerned","insight":"1 phrase FR max 120 car."}'
        )
        raw = _openrouter_chat_generate(prompt, max_tokens=180, temperature=0.2)
        if not raw:
            return base_meta
        spec = safe_json_parse(raw) or {}
        for key in ("priority", "intent", "intent_label", "tone", "insight"):
            val = spec.get(key)
            if val:
                base_meta[key] = val
        if spec.get("intent"):
            labels = {
                "question": "Question",
                "correction": "Correction",
                "approval": "Validation",
                "ack": "Accusé",
                "info": "Info",
            }
            base_meta["intent_label"] = labels.get(spec["intent"], base_meta.get("intent_label"))
    except Exception:
        pass
    return base_meta


def _fetch_chat_history(my_id, partner_id, limit=40):
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sender_id, content, created_at
        FROM chat_messages
        WHERE (sender_id = %s AND receiver_id = %s)
           OR (sender_id = %s AND receiver_id = %s)
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (my_id, partner_id, partner_id, my_id, limit),
    )
    rows = list(reversed(cur.fetchall()))
    cur.close()
    conn.close()
    return rows


def _format_chat_history_for_ai(history, my_id, partner_name):
    lines = []
    for sender_id, content, _created in history:
        who = "Moi" if sender_id == my_id else partner_name
        lines.append(f"{who}: {content}")
    return "\n".join(lines[-30:])


def _chat_role_templates(role):
    if role == "comptable":
        return [
            "Bonjour, j'ai une question concernant la facture #{id}.",
            "La correction OCR a été effectuée sur la facture #{id}, merci de valider.",
            "Pouvez-vous confirmer l'imputation comptable de la facture #{id} ?",
        ]
    if role == "superviseur":
        return [
            "Merci de revoir la facture #{id} : anomalie détectée sur le montant.",
            "Validation OK pour la facture #{id}, vous pouvez clôturer le dossier.",
            "Avez-vous le justificatif complémentaire pour la facture #{id} ?",
        ]
    return []


def _chat_assist_suggest(history_text, my_role, partner_role, partner_name):
    from utils import safe_json_parse

    templates = _chat_role_templates(my_role)
    fallback = [{"text": t.replace("#{id}", "#…"), "reason": "Modèle rapide"} for t in templates[:3]]
    if not history_text.strip():
        return {"suggestions": fallback, "source": "templates"}

    if not _openrouter_available():
        return {"suggestions": fallback, "source": "templates"}

    try:
        prompt = (
            f"Tu es copilote messagerie FactuPRO. Rôle expéditeur: {my_role}. "
            f"Destinataire: {partner_name} ({partner_role}).\n"
            f"Historique récent:\n{history_text}\n\n"
            "Propose 3 réponses courtes, professionnelles, en français, adaptées au contexte comptable/factures.\n"
            'JSON: {"suggestions":[{"text":"...","reason":"pourquoi en 5 mots max"}]}'
        )
        raw = _openrouter_chat_generate(prompt, max_tokens=400, temperature=0.45)
        if not raw:
            return {"suggestions": fallback, "source": "templates"}
        spec = safe_json_parse(raw) or {}
        sug = spec.get("suggestions")
        if isinstance(sug, list) and sug:
            cleaned = []
            for item in sug[:3]:
                if isinstance(item, dict) and item.get("text"):
                    cleaned.append(
                        {
                            "text": str(item["text"]).strip()[:500],
                            "reason": str(item.get("reason") or "Suggestion IA").strip()[:80],
                        }
                    )
            if cleaned:
                return {"suggestions": cleaned, "source": "ai"}
    except Exception:
        pass
    return {"suggestions": fallback, "source": "templates"}


def _chat_assist_improve(draft, tone, my_role, partner_name, history_text):
    tones = {
        "pro": "ton professionnel et courtois",
        "concise": "ton très concis (2 phrases max)",
        "friendly": "ton chaleureux mais professionnel",
    }
    style = tones.get(tone, tones["pro"])
    if not _openrouter_available():
        improved = draft.strip()
        if improved and not improved[0].isupper():
            improved = improved[0].upper() + improved[1:]
        if improved and improved[-1] not in ".!?":
            improved += "."
        return {"text": improved, "source": "rules"}

    try:
        prompt = (
            f"Reformule ce brouillon pour un message {my_role} → {partner_name} "
            f"({style}). Garde le sens. Contexte:\n{history_text[-1200:]}\n\n"
            f"Brouillon: \"{draft[:800]}\"\n\n"
            "Réponds UNIQUEMENT par le message reformulé, sans guillemets."
        )
        text = _openrouter_chat_generate(prompt, max_tokens=300, temperature=0.35)
        return {"text": (text or draft).strip()[:2000], "source": "ai"}
    except Exception:
        return {"text": draft.strip(), "source": "fallback"}


def _chat_assist_summarize(history_text, my_role, partner_name):
    if not history_text.strip():
        return {"summary": "Aucun échange pour l'instant.", "action_items": [], "source": "empty"}
    if not _openrouter_available():
        lines = [l for l in history_text.split("\n") if l.strip()]
        preview = " · ".join(lines[-3:])[:220]
        return {
            "summary": f"Derniers échanges : {preview}",
            "action_items": [],
            "source": "rules",
        }
    from utils import safe_json_parse

    try:
        prompt = (
            f"Résume cette conversation FactuPRO ({my_role} ↔ {partner_name}) en français.\n"
            f"{history_text}\n\n"
            'JSON: {"summary":"2 phrases max","action_items":["action 1","action 2"]}'
        )
        raw = _openrouter_chat_generate(prompt, max_tokens=350, temperature=0.25)
        if not raw:
            raise ValueError("Réponse OpenRouter vide")
        spec = safe_json_parse(raw) or {}
        items = spec.get("action_items")
        if not isinstance(items, list):
            items = []
        return {
            "summary": str(spec.get("summary") or "").strip()[:600],
            "action_items": [str(x).strip() for x in items[:4] if x],
            "source": "ai",
        }
    except Exception:
        return {
            "summary": "Résumé indisponible — consultez les derniers messages.",
            "action_items": [],
            "source": "fallback",
        }


def _fetch_chat_context(user_id, role):
    """Contexte métier injecté dans le copilote (factures récentes, alertes)."""
    ctx = {"recent_invoices": [], "alerts": [], "quick_templates": _chat_role_templates(role)}
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, invoice_number, seller_name, total_gross, date_of_issue
            FROM invoices
            ORDER BY id DESC
            LIMIT 6
            """
        )
        for r in cur.fetchall():
            ctx["recent_invoices"].append(
                {
                    "id": r[0],
                    "invoice_number": r[1],
                    "seller_name": r[2],
                    "total_gross": _json_safe_value(r[3]),
                    "date_of_issue": r[4],
                }
            )
        if role == "superviseur":
            init_supervisor_alerts_table()
            cur.execute(
                """
                SELECT sa.invoice_id, sa.message, sa.created_at
                FROM supervisor_alerts sa
                WHERE sa.is_read = FALSE
                ORDER BY sa.created_at DESC
                LIMIT 5
                """
            )
            for r in cur.fetchall():
                ctx["alerts"].append(
                    {
                        "invoice_id": r[0],
                        "message": r[1],
                        "created_at": _json_safe_value(r[2]),
                    }
                )
        cur.close()
        conn.close()
    except Exception:
        pass
    return ctx


@app.route("/chat/conversations", methods=["GET"])
@require_auth
@require_role(*CHAT_ROLES)
def list_chat_conversations():
    """Liste des interlocuteurs (rôle opposé) avec aperçu du dernier message."""
    try:
        init_chat_messages_table()
        me = request.auth_user
        my_id = me["user_id"]
        my_role = me.get("role")
        partner_role = _chat_partner_role(my_role)
        if not partner_role:
            return jsonify({"conversations": []})

        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                u.id,
                u.email,
                u.full_name,
                u.role,
                lm.content,
                lm.created_at,
                lm.sender_id,
                lm.metadata,
                COALESCE(unread.cnt, 0) AS unread_count
            FROM users u
            LEFT JOIN LATERAL (
                SELECT content, created_at, sender_id, metadata
                FROM chat_messages
                WHERE (sender_id = u.id AND receiver_id = %s)
                   OR (sender_id = %s AND receiver_id = u.id)
                ORDER BY created_at DESC
                LIMIT 1
            ) lm ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*)::int AS cnt
                FROM chat_messages
                WHERE sender_id = u.id AND receiver_id = %s AND is_read = FALSE
            ) unread ON TRUE
            WHERE u.role = %s AND u.id != %s
            ORDER BY lm.created_at DESC NULLS LAST, u.full_name NULLS LAST, u.email
            """,
            (my_id, my_id, my_id, partner_role, my_id),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        conversations = []
        for r in rows:
            meta = r[7] if len(r) > 7 else {}
            if meta and not isinstance(meta, dict):
                try:
                    meta = json.loads(meta) if meta else {}
                except Exception:
                    meta = {}
            conversations.append(
                {
                    "user_id": r[0],
                    "email": r[1],
                    "full_name": r[2],
                    "role": r[3],
                    "last_message": r[4],
                    "last_message_at": _json_safe_value(r[5]),
                    "last_message_is_mine": r[6] == my_id if r[6] is not None else None,
                    "unread_count": r[8] or 0,
                    "last_priority": meta.get("priority"),
                    "last_intent": meta.get("intent"),
                }
            )

        return jsonify({"conversations": conversations})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/chat/messages", methods=["GET"])
@require_auth
@require_role(*CHAT_ROLES)
def list_chat_messages():
    """Messages échangés avec un interlocuteur."""
    try:
        partner_id = request.args.get("user_id", type=int)
        if not partner_id:
            return jsonify({"error": "user_id requis"}), 400

        limit = request.args.get("limit", 50, type=int)
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200
        before_id = request.args.get("before_id", type=int)

        me = request.auth_user
        my_id = me["user_id"]
        my_role = me.get("role")
        partner_role = _get_user_role(partner_id)
        if not partner_role or not _can_chat_between(my_role, partner_role):
            return jsonify({"error": "Interlocuteur invalide"}), 403

        init_chat_messages_table()
        conn = get_pg_connection()
        cur = conn.cursor()

        params = [my_id, partner_id, partner_id, my_id]
        before_sql = ""
        if before_id:
            before_sql = "AND id < %s"
            params.append(before_id)
        params.append(limit)

        cur.execute(
            f"""
            SELECT id, sender_id, receiver_id, content, is_read, created_at, metadata
            FROM chat_messages
            WHERE (sender_id = %s AND receiver_id = %s)
               OR (sender_id = %s AND receiver_id = %s)
            {before_sql}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cur.fetchall()

        cur.execute(
            """
            UPDATE chat_messages
            SET is_read = TRUE
            WHERE sender_id = %s AND receiver_id = %s AND is_read = FALSE
            """,
            (partner_id, my_id),
        )
        conn.commit()
        cur.close()
        conn.close()

        messages = []
        for r in reversed(rows):
            meta = r[6]
            if meta and not isinstance(meta, dict):
                try:
                    meta = json.loads(meta) if meta else {}
                except Exception:
                    meta = {}
            messages.append(
                {
                    "id": r[0],
                    "sender_id": r[1],
                    "receiver_id": r[2],
                    "content": r[3],
                    "is_read": bool(r[4]),
                    "created_at": _json_safe_value(r[5]),
                    "is_mine": r[1] == my_id,
                    "metadata": meta or {},
                }
            )

        return jsonify({"messages": messages, "partner_id": partner_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/chat/messages", methods=["POST"])
@require_auth
@require_role(*CHAT_ROLES)
def send_chat_message():
    """Envoie un message à un comptable ou superviseur."""
    try:
        data = request.get_json(silent=True) or {}
        receiver_id = data.get("receiver_id")
        content = (data.get("content") or "").strip()

        if not receiver_id:
            return jsonify({"error": "receiver_id requis"}), 400
        try:
            receiver_id = int(receiver_id)
        except (TypeError, ValueError):
            return jsonify({"error": "receiver_id invalide"}), 400
        if not content:
            return jsonify({"error": "Message vide"}), 400
        if len(content) > 4000:
            return jsonify({"error": "Message trop long (4000 caractères max)"}), 400

        me = request.auth_user
        sender_id = me["user_id"]
        sender_role = me.get("role")
        receiver_role = _get_user_role(receiver_id)
        if not receiver_role or not _can_chat_between(sender_role, receiver_role):
            return jsonify({"error": "Destinataire invalide"}), 403
        if receiver_id == sender_id:
            return jsonify({"error": "Destinataire invalide"}), 400

        meta = _analyze_message_rules(content, sender_role)
        meta = _enrich_message_analysis_with_ai(content, meta, receiver_role)

        init_chat_messages_table()
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO chat_messages (sender_id, receiver_id, content, metadata)
            VALUES (%s, %s, %s, %s::jsonb)
            RETURNING id, sender_id, receiver_id, content, is_read, created_at, metadata
            """,
            (sender_id, receiver_id, content, json.dumps(meta)),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        row_meta = row[6]
        if row_meta and not isinstance(row_meta, dict):
            try:
                row_meta = json.loads(row_meta) if row_meta else {}
            except Exception:
                row_meta = meta

        return jsonify(
            {
                "message": {
                    "id": row[0],
                    "sender_id": row[1],
                    "receiver_id": row[2],
                    "content": row[3],
                    "is_read": bool(row[4]),
                    "created_at": _json_safe_value(row[5]),
                    "is_mine": True,
                    "metadata": row_meta or meta,
                }
            }
        ), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/chat/unread-count", methods=["GET"])
@require_auth
@require_role(*CHAT_ROLES)
def chat_unread_count():
    try:
        init_chat_messages_table()
        my_id = request.auth_user["user_id"]
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)::int
            FROM chat_messages
            WHERE receiver_id = %s AND is_read = FALSE
            """,
            (my_id,),
        )
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return jsonify({"unread_count": count or 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/chat/context", methods=["GET"])
@require_auth
@require_role(*CHAT_ROLES)
def chat_context():
    try:
        me = request.auth_user
        ctx = _fetch_chat_context(me["user_id"], me.get("role"))
        return jsonify(ctx)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/chat/assist", methods=["POST"])
@require_auth
@require_role(*CHAT_ROLES)
def chat_assist():
    """Copilote IA : suggestions, reformulation, résumé."""
    try:
        data = request.get_json(silent=True) or {}
        action = (data.get("action") or "").strip().lower()
        partner_id = data.get("partner_id")
        draft = (data.get("draft") or "").strip()
        tone = (data.get("tone") or "pro").strip().lower()

        if not partner_id:
            return jsonify({"error": "partner_id requis"}), 400
        try:
            partner_id = int(partner_id)
        except (TypeError, ValueError):
            return jsonify({"error": "partner_id invalide"}), 400

        me = request.auth_user
        my_id = me["user_id"]
        my_role = me.get("role")
        partner_role = _get_user_role(partner_id)
        if not partner_role or not _can_chat_between(my_role, partner_role):
            return jsonify({"error": "Interlocuteur invalide"}), 403

        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT full_name, email FROM users WHERE id = %s",
            (partner_id,),
        )
        prow = cur.fetchone()
        cur.close()
        conn.close()
        partner_name = (prow[0] or prow[1] or "Interlocuteur") if prow else "Interlocuteur"

        history = _fetch_chat_history(my_id, partner_id, limit=40)
        history_text = _format_chat_history_for_ai(history, my_id, partner_name)

        if action == "suggest_replies":
            result = _chat_assist_suggest(history_text, my_role, partner_role, partner_name)
            return jsonify(result)

        if action == "improve_draft":
            if not draft:
                return jsonify({"error": "draft requis"}), 400
            result = _chat_assist_improve(draft, tone, my_role, partner_name, history_text)
            return jsonify(result)

        if action == "summarize":
            result = _chat_assist_summarize(history_text, my_role, partner_name)
            return jsonify(result)

        return jsonify({"error": "action invalide (suggest_replies, improve_draft, summarize)"}), 400
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


def _qa_amount_column(columns):
    """Colonne montant préférée pour graphiques / KPIs."""
    prefs = (
        "total_gross", "total_ttc", "montant_ttc", "amount_gross", "gross",
        "total_net", "total_vat", "net", "montant", "total", "value",
    )
    lower = {c.lower(): c for c in columns}
    for p in prefs:
        if p in lower:
            return lower[p]
    for c in columns:
        cl = c.lower()
        if any(x in cl for x in ("gross", "ttc", "montant", "amount", "total", "net")):
            if "id" not in cl and "year" not in cl and "month" not in cl:
                return c
    return None


def _qa_label_column(columns, amount_col):
    """Colonne libellé pour graphiques."""
    prefs = (
        "invoice_number", "numero_facture", "seller_name", "client_name",
        "category", "month_label", "period", "label", "name",
    )
    lower = {c.lower(): c for c in columns}
    for p in prefs:
        if p in lower and lower[p] != amount_col:
            return lower[p]
    skip = {amount_col, "invoice_id", "id"} if amount_col else {"invoice_id", "id"}
    for c in columns:
        cl = c.lower()
        if c in skip or cl in skip:
            continue
        if any(x in cl for x in ("_id", "invoice_year", "invoice_month", "year", "month")):
            continue
        return c
    year_c = lower.get("invoice_year") or lower.get("year")
    month_c = lower.get("invoice_month") or lower.get("month")
    if year_c and month_c:
        return "__composite_period__"
    return None


def _build_qa_kpis(columns, data_rows):
    kpis = [{"label": "Nombre de lignes", "value": len(data_rows)}]
    amount_col = _qa_amount_column(columns)
    if amount_col and data_rows:
        vals = [
            float(r[amount_col])
            for r in data_rows
            if isinstance(r.get(amount_col), (int, float, Decimal))
        ]
        if vals:
            kpis.append({
                "label": "Total TTC (résultat)",
                "value": round(sum(vals), 2),
            })
            if len(vals) > 1:
                kpis.append({
                    "label": "Montant max",
                    "value": round(max(vals), 2),
                })
    return kpis[:4]


def _enrich_qa_viz(viz, columns, data_rows, question):
    if not isinstance(viz, dict):
        viz = {}
    amount_col = _qa_amount_column(columns)
    label_col = _qa_label_column(columns, amount_col)
    if amount_col and not viz.get("valueColumn"):
        viz["valueColumn"] = amount_col
    if label_col and label_col != "__composite_period__" and not viz.get("labelColumn"):
        viz["labelColumn"] = label_col
    if label_col == "__composite_period__":
        viz["labelColumn"] = "__composite_period__"
    q = (question or "").lower()
    if not viz.get("type"):
        if "facture" in q and amount_col:
            viz["type"] = "bar"
        elif any(x in q for x in ("évolution", "evolution", "par mois", "mensuel")):
            viz["type"] = "line"
        elif "catégorie" in q or "categorie" in q:
            viz["type"] = "pie"
    if not viz.get("title") and "facture" in q:
        viz["title"] = "Factures (montant TTC)"
    return viz


import time as _time

_gemini_last_call_ts = 0.0


def _gemini_min_interval_sec() -> float:
    try:
        return max(0.0, float(os.getenv("GEMINI_MIN_INTERVAL_SEC", "13")))
    except (TypeError, ValueError):
        return 13.0


def _gemini_throttle():
    """Espace les appels pour rester sous le quota gratuit (~5 req/min)."""
    global _gemini_last_call_ts
    wait = _gemini_min_interval_sec()
    if wait <= 0:
        return
    elapsed = _time.time() - _gemini_last_call_ts
    if elapsed < wait:
        _time.sleep(wait - elapsed)
    _gemini_last_call_ts = _time.time()


def _gemini_retry_delay_seconds(exc: Exception) -> float:
    msg = str(exc)
    for pattern in (
        r"retry in ([\d.]+)\s*s",
        r"RetryDelay.*?(\d+(?:\.\d+)?)\s*s",
        r'"retryDelay":\s*"(\d+)s"',
    ):
        m = re.search(pattern, msg, re.I)
        if m:
            return min(float(m.group(1)) + 1.0, 60.0)
    return 15.0


def _gemini_generate_with_retry(
    prompt: str, *, max_tokens: int = 2048, temperature: float = 0.0, max_retries: int = 4
) -> str:
    """Appel Gemini avec throttle + retry automatique sur erreur 429 (quota)."""
    if not (os.getenv("GEMINI_API_KEY") or "").strip():
        raise ValueError("GEMINI_API_KEY manquante dans .env.")

    last_ex = None
    for attempt in range(max_retries):
        _gemini_throttle()
        try:
            response = gemini_model.generate_content(
                contents=prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    top_p=1,
                    max_output_tokens=max_tokens,
                ),
            )
            if response and response.candidates:
                text = response.candidates[0].content.parts[0].text.strip()
                if text:
                    return text
            raise ValueError("Réponse Gemini vide.")
        except Exception as ex:
            last_ex = ex
            msg = str(ex).lower()
            if (
                attempt < max_retries - 1
                and ("429" in msg or "quota" in msg or "resource_exhausted" in msg or "rate" in msg)
            ):
                _time.sleep(_gemini_retry_delay_seconds(ex))
                continue
            if "429" in msg or "quota" in msg or "resource_exhausted" in msg:
                raise ValueError(
                    "Quota Gemini dépassé (offre gratuite : environ 5 requêtes par minute). "
                    "Attendez 1 minute, évitez de cliquer plusieurs fois, ou activez la facturation sur "
                    "https://aistudio.google.com (clé API payante). "
                    "Variable GEMINI_MIN_INTERVAL_SEC=13 espace déjà les appels automatiquement."
                ) from ex
            raise ValueError(f"Erreur Gemini (Assistant IA): {ex}") from ex

    if last_ex:
        raise last_ex
    raise ValueError("Échec appel Gemini.")


def _qa_use_extra_gemini_calls() -> bool:
    """Si false (défaut), 1 seul appel Gemini par question (SQL) — préserve le quota."""
    return os.getenv("GEMINI_QA_EXTRA_CALLS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _qa_display_mode(columns, data_rows, question):
    """invoices = cartes facture ; table = tableau seul."""
    if not data_rows:
        return "empty"
    lower = {c.lower() for c in columns}
    has_invoice = "invoice_id" in lower or (len(columns) == 1 and "id" in lower)
    amount_col = _qa_amount_column(columns)
    q = (question or "").lower()
    if has_invoice and amount_col and ("facture" in q or "invoice" in q):
        return "invoices"
    return "table"


def _simple_qa_explanation(columns: list, data_rows: list, kpis: list) -> str:
    n = len(data_rows or [])
    if n == 0:
        return "Aucun résultat pour cette requête."
    if kpis:
        parts = [f"{k.get('label', '')}: {k.get('value', '')}" for k in (kpis or [])[:3] if k]
        return f"{n} ligne(s) — " + ", ".join(parts) + "."
    return f"{n} ligne(s) retournée(s)."


def _simple_qa_suggestions(question: str) -> list:
    q = (question or "").lower()
    if "fournisseur" in q or "vendeur" in q or "seller" in q:
        return [
            "Total TTC par fournisseur cette année",
            "Nombre de factures par client",
        ]
    if "client" in q:
        return [
            "Top 10 clients par montant TTC",
            "Évolution du TTC par mois",
        ]
    return [
        "Total TTC par catégorie",
        "Top 10 fournisseurs par nombre de factures",
    ]


def _generate_qa_explanation(question: str, columns: list, data_rows: list, kpis: list) -> str:
    """Synthèse (Gemini seulement si GEMINI_QA_EXTRA_CALLS=1)."""
    if not _qa_use_extra_gemini_calls():
        return _simple_qa_explanation(columns, data_rows, kpis)
    try:
        kpi_str = ", ".join([f"{k.get('label', '')}: {k.get('value', '')}" for k in (kpis or [])[:5]])
        prompt = (
            f"Question utilisateur: {question}\n"
            f"Colonnes du résultat: {', '.join(columns[:10])}. Nombre de lignes: {len(data_rows)}.\n"
            f"KPIs: {kpi_str}\n\n"
            "Écris UNE seule phrase courte en français qui résume le résultat. Réponds UNIQUEMENT par cette phrase."
        )
        raw = _gemini_generate_with_retry(prompt, max_tokens=150, temperature=0.3)
        return raw[:300] if raw else _simple_qa_explanation(columns, data_rows, kpis)
    except Exception:
        return _simple_qa_explanation(columns, data_rows, kpis)


def _generate_qa_suggestions(question: str, columns: list, data_rows: list) -> list:
    """Suggestions (Gemini seulement si GEMINI_QA_EXTRA_CALLS=1)."""
    if not _qa_use_extra_gemini_calls():
        return _simple_qa_suggestions(question)
    from utils import safe_json_parse

    try:
        prompt = (
            f"Question posée: {question}\n"
            f"Résultat: {len(data_rows)} lignes, colonnes: {', '.join(columns[:8])}.\n\n"
            'Réponds UNIQUEMENT en JSON: {"suggestions": ["question 1", "question 2"]}'
        )
        raw = _gemini_generate_with_retry(prompt, max_tokens=200, temperature=0.4)
        spec = safe_json_parse(raw) or {}
        sug = spec.get("suggestions")
        if isinstance(sug, list) and sug:
            return [str(s).strip() for s in sug[:4] if s]
    except Exception:
        pass
    return _simple_qa_suggestions(question)


def _run_invoice_qa(question: str):
    """
    Agent SQL générique:
    - 1) Demande à Gemini de générer une requête SELECT Postgres
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
    issue_date DATE,
    seller_name TEXT,
    client_name TEXT,
    total_net NUMERIC,
    total_vat NUMERIC,
    total_gross NUMERIC,
    user_id INTEGER REFERENCES users(id)
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

Vues (SELECT autorisées, optimisées pour analyses / Power BI) :
VIEW public.v_invoices_header_bi — une ligne par facture (invoice_id, issue_date, date_of_issue_text, montants, vendeur, client, user_id).
VIEW public.v_invoice_lines_bi — une ligne par ligne article (LEFT JOIN : facture sans ligne = une ligne avec line_id NULL) ; utilise issue_date pour le temps.
VIEW public.v_users_bi — utilisateurs (user_id, email, full_name, role).
VIEW public.v_invoice_corrected_lines_bi — versions corrigées des factures reliées à l’original.

Modèle en étoile (vues, idéal Power BI / rapport) :
VIEW public.dim_date_bi — date_id (YYYYMMDD), full_date, calendar_year (année grégorienne), iso_year, mois, trimestre, iso_week_num (semaine ISO via TO_CHAR IW), etc.
VIEW public.dim_user_bi — user_key (= user_id), email, full_name, role.
VIEW public.dim_category_bi — category_key, category_name.
VIEW public.dim_supplier_bi — supplier_key, supplier_name.
VIEW public.dim_client_bi — client_key, client_name.
VIEW public.fact_invoice_lines_star_bi — table de faits au grain ligne (line_id, invoice_id, date_id, user_id, supplier_key, client_key, category_key, qty, montants, etc.).
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
- Utilise uniquement les tables et vues décrites ci-dessus.
- Utilise des noms de colonnes exacts.
- Utilise la syntaxe PostgreSQL standard.
- Synonymes à respecter: "montant", "total", "somme", "TTC" = totaux (total_gross ou SUM(gross)); "fournisseur", "vendeur", "vendor", "seller" = colonne seller_name; "client" = client_name; "catégorie" = category; "HT", "net" = total_net / net; "TVA" = total_vat.
- La colonne date_of_issue est le texte brut extrait. Pour les filtres par mois/année ou Power BI, utilise la colonne issue_date (type DATE, format calendaire).
- Si la question demande des totaux, utilise SUM() et éventuellement GROUP BY.
- Si la question porte sur une ou plusieurs FACTURES (numéro, vendeur, client, « facture la plus élevée », « max par mois », etc.) :
  inclure dans le SELECT : invoice_id (ou id), invoice_number, issue_date, seller_name, client_name, total_gross (montant TTC).
  Pour « max / plus grand total par mois et année » : une ligne par (année, mois) avec la facture gagnante (DISTINCT ON, ROW_NUMBER ou sous-requête), pas seulement les IDs.
- Pour viz : labelColumn = libellé lisible (invoice_number, seller_name, ou mois+année) ; valueColumn = colonne montant (total_gross, pas invoice_id ni année).

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

    raw = _gemini_generate_with_retry(prompt, max_tokens=2048, temperature=0.0)
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

    kpis = _build_qa_kpis(columns, data_rows)
    viz = _enrich_qa_viz(viz, columns, data_rows, question)
    display_mode = _qa_display_mode(columns, data_rows, question)

    explanation = _generate_qa_explanation(question, columns, data_rows, kpis)
    suggestions = _generate_qa_suggestions(question, columns, data_rows)

    return {
        "question": question,
        "sql": sql,
        "commentaire": commentaire,
        "viz": viz,
        "displayMode": display_mode,
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
                i.issue_date,
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
            "issue_date",
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


@app.route("/api/powerbi/supervisor-embed", methods=["GET"])
@require_auth
@require_role("admin", "superviseur")
def powerbi_supervisor_embed():
    """URLs d’embed Power BI pour le superviseur (pages 3 et 5)."""
    try:
        from powerbi_embed import supervisor_embed_payload

        return jsonify(supervisor_embed_payload())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/powerbi-pages", methods=["GET", "PUT"])
@require_auth
@require_role("admin")
def admin_powerbi_pages():
    """Lire / enregistrer les IDs de pages Power BI (sans rebuild Docker)."""
    try:
        from powerbi_embed import get_powerbi_config, supervisor_embed_payload, update_powerbi_pages

        if request.method == "GET":
            return jsonify(
                {
                    "config": get_powerbi_config(),
                    "supervisor": supervisor_embed_payload(),
                }
            )
        data = request.get_json(silent=True) or {}
        cfg = update_powerbi_pages(data)
        return jsonify(
            {
                "config": cfg,
                "supervisor": supervisor_embed_payload(),
                "message": "Configuration Power BI enregistrée.",
            }
        )
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


def _powerbi_view_definitions():
    """Définitions CREATE OR REPLACE VIEW pour outils BI (Power BI, etc.)."""
    return (
        """
        CREATE OR REPLACE VIEW public.v_users_bi AS
        SELECT
            u.id AS user_id,
            u.email,
            u.full_name,
            u.role
        FROM public.users u;
        """,
        """
        CREATE OR REPLACE VIEW public.v_invoices_header_bi AS
        SELECT
            i.id AS invoice_id,
            i.issue_date,
            i.date_of_issue AS date_of_issue_text,
            i.invoice_number,
            i.filename,
            i.seller_name,
            i.client_name,
            i.total_net,
            i.total_vat,
            i.total_gross,
            i.user_id
        FROM public.invoices i;
        """,
        """
        CREATE OR REPLACE VIEW public.v_invoice_lines_bi AS
        SELECT
            i.id AS invoice_id,
            i.issue_date,
            i.date_of_issue AS date_of_issue_text,
            i.invoice_number,
            i.filename,
            i.seller_name,
            i.client_name,
            i.total_net AS invoice_total_net,
            i.total_vat AS invoice_total_vat,
            i.total_gross AS invoice_total_gross,
            i.user_id,
            it.id AS line_id,
            it.description AS line_description,
            it.quantity AS line_quantity,
            it.net_price AS line_net_price,
            it.net AS line_net,
            it.gross AS line_gross,
            it.vat_percentage AS line_vat_pct,
            it.category AS line_category,
            it.account AS line_account
        FROM public.invoices i
        LEFT JOIN public.invoices_items it ON it.invoice_id = i.id;
        """,
        """
        CREATE OR REPLACE VIEW public.v_invoice_corrected_lines_bi AS
        SELECT
            ic.id AS corrected_invoice_id,
            ic.original_invoice_id,
            i.issue_date AS original_issue_date,
            i.date_of_issue AS original_date_text,
            i.invoice_number AS original_invoice_number,
            ic.invoice_number AS corrected_invoice_number,
            ic.date_of_issue AS corrected_issue_date,
            ic.seller_name AS corrected_seller_name,
            ic.client_name AS corrected_client_name,
            ic.total_net AS corrected_total_net,
            ic.total_vat AS corrected_total_vat,
            ic.total_gross AS corrected_total_gross,
            itc.id AS corrected_line_id,
            itc.description AS line_description,
            itc.quantity AS line_quantity,
            itc.net_price AS line_net_price,
            itc.net AS line_net,
            itc.gross AS line_gross,
            itc.vat_percentage AS line_vat_pct,
            itc.category AS line_category,
            itc.account AS line_account
        FROM public.invoices_corrected ic
        JOIN public.invoices i ON i.id = ic.original_invoice_id
        LEFT JOIN public.invoice_items_corrected itc ON itc.corrected_invoice_id = ic.id;
        """,
    )


def _star_schema_bi_view_definitions():
    """
    Mini modèle en étoile (vues) pour Power BI : relations claires fact ↔ dimensions.
    Pas de tables physiques : données toujours alignées sur invoices / invoices_items.
    """
    return (
        """
        CREATE OR REPLACE VIEW public.dim_date_bi AS
        SELECT DISTINCT
            (TO_CHAR(i.issue_date::date, 'YYYYMMDD'))::integer AS date_id,
            i.issue_date::date AS full_date,
            EXTRACT(year FROM i.issue_date::date)::integer AS calendar_year,
            TO_CHAR(i.issue_date::date, 'IYYY')::integer AS iso_year,
            EXTRACT(month FROM i.issue_date::date)::integer AS month_num,
            TRIM(TO_CHAR(i.issue_date::date, 'Month')) AS month_name,
            EXTRACT(quarter FROM i.issue_date::date)::integer AS quarter_num,
            TO_CHAR(i.issue_date::date, 'IW')::integer AS iso_week_num,
            TRIM(TO_CHAR(i.issue_date::date, 'Day')) AS weekday_name
        FROM public.invoices i
        WHERE i.issue_date IS NOT NULL;
        """,
        """
        CREATE OR REPLACE VIEW public.dim_user_bi AS
        SELECT
            u.id AS user_key,
            u.id AS user_id,
            u.email,
            u.full_name,
            u.role
        FROM public.users u;
        """,
        """
        CREATE OR REPLACE VIEW public.dim_category_bi AS
        SELECT
            dense_rank() OVER (ORDER BY cat) AS category_key,
            cat AS category_name
        FROM (
            SELECT DISTINCT COALESCE(NULLIF(TRIM(it.category), ''), 'Non classé') AS cat
            FROM public.invoices_items it
        ) s;
        """,
        """
        CREATE OR REPLACE VIEW public.dim_supplier_bi AS
        SELECT
            dense_rank() OVER (ORDER BY sn) AS supplier_key,
            sn AS supplier_name
        FROM (
            SELECT DISTINCT TRIM(i.seller_name) AS sn
            FROM public.invoices i
            WHERE i.seller_name IS NOT NULL AND TRIM(i.seller_name) <> ''
        ) s;
        """,
        """
        CREATE OR REPLACE VIEW public.dim_client_bi AS
        SELECT
            dense_rank() OVER (ORDER BY cn) AS client_key,
            cn AS client_name
        FROM (
            SELECT DISTINCT TRIM(i.client_name) AS cn
            FROM public.invoices i
            WHERE i.client_name IS NOT NULL AND TRIM(i.client_name) <> ''
        ) s;
        """,
        """
        CREATE OR REPLACE VIEW public.fact_invoice_lines_star_bi AS
        SELECT
            it.id AS line_id,
            i.id AS invoice_id,
            CASE
                WHEN i.issue_date IS NOT NULL
                THEN (TO_CHAR(i.issue_date::date, 'YYYYMMDD'))::integer
            END AS date_id,
            i.user_id,
            ds.supplier_key,
            dc.client_key,
            dcat.category_key,
            it.quantity AS qty,
            it.net_price,
            it.net AS amount_net,
            it.gross AS amount_gross,
            it.vat_percentage AS vat_pct,
            it.description AS product_description,
            i.invoice_number,
            i.filename
        FROM public.invoices_items it
        INNER JOIN public.invoices i ON i.id = it.invoice_id
        LEFT JOIN public.dim_supplier_bi ds
            ON ds.supplier_name = TRIM(i.seller_name)
        LEFT JOIN public.dim_client_bi dc
            ON dc.client_name = TRIM(i.client_name)
        LEFT JOIN public.dim_category_bi dcat
            ON dcat.category_name = COALESCE(NULLIF(TRIM(it.category), ''), 'Non classé');
        """,
        """
        CREATE OR REPLACE VIEW public.fact_qa_questions_bi AS
        SELECT
            q.id AS question_id,
            q.user_id,
            u.user_key,
            u.email,
            u.full_name,
            u.role,
            q.question,
            q.sql_generated,
            q.created_at,
            q.created_at::date AS question_date,
            CASE
                WHEN q.created_at IS NOT NULL
                THEN (TO_CHAR(q.created_at::date, 'YYYYMMDD'))::integer
            END AS date_id,
            CASE
                WHEN q.sql_generated IS NOT NULL AND TRIM(q.sql_generated) <> '' THEN 1
                ELSE 0
            END AS has_sql_flag,
            LENGTH(TRIM(q.question)) AS question_length_chars
        FROM public.qa_questions q
        LEFT JOIN public.dim_user_bi u ON u.user_id = q.user_id;
        """,
        """
        CREATE OR REPLACE VIEW public.dim_confirmation_date_bi AS
        SELECT DISTINCT
            (TO_CHAR(d.confirmation_date, 'YYYYMMDD'))::integer AS date_id,
            d.confirmation_date AS full_date,
            EXTRACT(year FROM d.confirmation_date)::integer AS calendar_year,
            EXTRACT(month FROM d.confirmation_date)::integer AS month_num,
            TRIM(TO_CHAR(d.confirmation_date, 'Month')) AS month_name,
            EXTRACT(quarter FROM d.confirmation_date)::integer AS quarter_num,
            TRIM(TO_CHAR(d.confirmation_date, 'Day')) AS weekday_name
        FROM (
            SELECT DATE(opd.logged_at) AS confirmation_date
            FROM public.ocr_precision_details opd
            WHERE opd.logged_at IS NOT NULL
        ) d;
        """,
        """
        CREATE OR REPLACE VIEW public.fact_comptable_parcours_bi AS
        SELECT
            i.id AS invoice_id,
            i.invoice_number,
            i.user_id,
            u.user_key,
            u.full_name AS comptable_name,
            u.role AS comptable_role,
            DATE(MAX(opd.logged_at)) AS confirmation_date,
            (TO_CHAR(DATE(MAX(opd.logged_at)), 'YYYYMMDD'))::integer AS confirmation_date_id,
            ROUND(MAX(opd.precision_pct)::numeric, 2) AS ocr_precision_pct,
            COUNT(*) FILTER (WHERE opd.is_correct = FALSE)::int AS champs_corriges_count,
            COUNT(*)::int AS champs_evalues_count,
            CASE
                WHEN BOOL_OR(opd.is_correct = FALSE) THEN 1
                ELSE 0
            END AS had_manual_correction_flag,
            CASE
                WHEN BOOL_OR(opd.is_correct = FALSE) THEN 'Correction comptable'
                ELSE 'Direct OK (sans correction)'
            END AS parcours_type,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM public.supervisor_alerts sa
                    WHERE sa.invoice_id = i.id
                ) THEN 1
                ELSE 0
            END AS supervisor_alert_flag
        FROM public.invoices i
        INNER JOIN public.ocr_precision_details opd ON opd.invoice_id = i.id
        LEFT JOIN public.dim_user_bi u ON u.user_id = i.user_id
        WHERE opd.logged_at IS NOT NULL
        GROUP BY i.id, i.invoice_number, i.user_id, u.user_key, u.full_name, u.role;
        """,
    )


# ================= MAIN =================
def run_migrations():
    """Applique les migrations (user_id sur invoices)."""
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS user_id INTEGER;")
        cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS issue_date DATE;")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_invoices_issue_date ON invoices(issue_date);"
        )
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
        cur.execute(
            """
            ALTER TABLE public.ocr_precision_details
            ADD COLUMN IF NOT EXISTS logged_at TIMESTAMPTZ;
            """
        )

        # Vues prêtes pour Power BI
        for view_sql in _powerbi_view_definitions():
            cur.execute(view_sql)
        for view_sql in _star_schema_bi_view_definitions():
            cur.execute(view_sql)

        conn.commit()
        cur.close()
        conn.close()
        print("✅ Vues Power BI + modèle étoile (dim_* / fact_*) à jour", flush=True)
        try:
            from utils import backfill_invoice_issue_dates

            n = backfill_invoice_issue_dates()
            if n:
                print(f"✅ issue_date : {n} facture(s) rétro-remplie(s) pour Power BI / filtres", flush=True)
        except Exception as bf_e:
            print(f"⚠️ Backfill issue_date : {bf_e}", flush=True)
    except Exception as e:
        print(f"⚠️ Migration user_id: {e}")


def _warm_expense_classifier_async():
    """Télécharge / charge le modèle d'embeddings en arrière-plan pour ne pas bloquer le 1er /upload 10+ min."""

    def _run():
        try:
            from utils import _get_classifier

            clf = _get_classifier()
            print("✅ Warm-up classifieur terminé" if clf else "ℹ️ Warm-up classifieur: indisponible")
        except Exception as e:
            print(f"⚠️ Warm-up classifieur: {e}")

    threading.Thread(target=_run, daemon=True, name="warm-expense-classifier").start()


if __name__ == "__main__":
    init_users_table()
    init_invoice_tables()
    init_qa_questions_table()
    init_supervisor_alerts_table()
    init_chat_messages_table()
    run_migrations()
    _warm_expense_classifier_async()
    _debug = os.environ.get("FLASK_DEBUG", "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    app.run(debug=_debug, host="0.0.0.0", port=5000)