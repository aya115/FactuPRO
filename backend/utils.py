import os, json, shutil, time, re
import cv2, numpy as np
from pdf2image import convert_from_path
import pytesseract
from groq import Groq
from pytesseract import Output
from anomaly_detection import detect_anomalies
from accounting_imputation import add_account_to_items
import psycopg2
from decimal import Decimal
from ocr_engine import similarity_match, numeric_match
# ================= CONFIG =================
WORK_FOLDER = os.path.expanduser("~/invoice_processing/")
BUSINESS_FOLDER = os.path.join(WORK_FOLDER, "business_invoices")
os.makedirs(BUSINESS_FOLDER, exist_ok=True)

PG_HOST = "localhost"
PG_DB = "testdb"
PG_USER = "postgres"
PG_PASSWORD = "postgres"

def get_pg_connection():
    return psycopg2.connect(
        host=PG_HOST,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD
    )

MODEL = "llama-3.3-70b-versatile"

_groq_llm_client = None


def get_groq_llm_client():
    """Client Groq pour l'analyse de factures (clé uniquement via GROQ_API_KEY, jamais en dur dans le code)."""
    global _groq_llm_client
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not key:
        return None
    if _groq_llm_client is None:
        _groq_llm_client = Groq(api_key=key)
    return _groq_llm_client

MAX_RETRIES = 3
BASE_DELAY = 2
MIN_DELAY_BETWEEN_REQUESTS = 1.5

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Program Files\Tesseract-OCR\tessdata"

# ================= UTILS =================
def clean_text(text):
    if not text:
        return ""
    text = text.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ================= UTILS AMÉLIORÉS =================
def preprocess_image(img):
    """Prétraitement pour améliorer l'OCR"""
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Seuillage adaptatif pour texte clair
    img = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 11, 2)
    # Filtre median pour réduire le bruit
    img = cv2.medianBlur(img, 3)
    return img
def ocr_to_generic_json(img):
    #Elle extrait : chaque mot sa position dans l’image
    df = pytesseract.image_to_data(
        img,
        lang="eng+fra",
        output_type=Output.DATAFRAME
    )
    df = df.dropna(subset=["text"])
    df = df[df["text"].str.strip() != ""]

    return df[["text", "left", "top"]].to_dict("records")
def ocr_to_plain_text(img):
    # Convertit toute l’image en texte brut
    return pytesseract.image_to_string(img, lang="eng+fra")
def ocr_to_spatial_words(img):
    df = pytesseract.image_to_data(img, output_type=Output.DATAFRAME)
    df = df.dropna(subset=["text"])
    df = df[df.text.str.strip() != ""]
    return df[["text", "left", "top"]].to_dict("records")


def extract_text_from_json(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_text_from_xml(xml_path):
    with open(xml_path, "r", encoding="utf-8") as f:
        return [{"col1": line} for line in f.read().splitlines()]


def extract_text_from_image(img_path):
    img = cv2.imread(img_path)
    if img is None:
        return []
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return ocr_to_generic_json(img)


def extract_ocr_text_from_pdf(pdf_path):
    pages = convert_from_path(pdf_path, dpi=300)
    ocr_rows = []
    for page in pages:
        img = np.array(page)
        if img.ndim == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        ocr_rows.extend(ocr_to_generic_json(img))
    return ocr_rows

import re

def extract_text_from_pdf(pdf_path):
    """Détecte PDF texte ou scanné et applique OCR si nécessaire"""
    from pdfplumber import open as open_pdf

    ocr_rows = []
    try:#PDF texte	lecture directe// PDF scanné	OCR
        with open_pdf(pdf_path) as pdf:
            text_found = False
            for page in pdf.pages:
                text = page.extract_text()
                if text and text.strip():
                    text_found = True
                    for line in text.splitlines():
                        ocr_rows.append({"col1": clean_text(line)})
            if not text_found:
                # PDF scanné → OCR
                print(f"ℹ️ PDF scanné détecté: {pdf_path}")
                ocr_rows = extract_ocr_text_from_pdf(pdf_path)
    except Exception as e:
        print(f"⚠️ Erreur PDF {pdf_path}: {e}")
        ocr_rows = extract_ocr_text_from_pdf(pdf_path)

    return ocr_rows

def safe_json_parse(text):
    # transformer une réponse LLM (souvent "sale") en JSON exploitable
    # stratégie:
    # 1) JSON direct
    # 2) blocs ```json ... ``` (du dernier au premier)
    # 3) extraction d'objets équilibrés {...} dans tout le texte (du dernier au premier)
    if not isinstance(text, str):
        return {}

    raw = text.strip()
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    def _extract_balanced_objects(s):
        objs = []
        start = -1
        depth = 0
        in_str = False
        esc = False
        for i, ch in enumerate(s):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
                continue

            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start != -1:
                        objs.append(s[start:i + 1])
                        start = -1
        return objs

    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE)
    for block in reversed(fenced_blocks):
        block = block.strip()
        if not block:
            continue
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        for candidate in reversed(_extract_balanced_objects(block)):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue

    for candidate in reversed(_extract_balanced_objects(raw)):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue

    return {}


def _extract_name(val):
    """Extrait le nom depuis un dict {name: ...} ou une chaîne."""
    if val is None:
        return None
    if isinstance(val, dict):
        return val.get("name") or None
    if isinstance(val, str):
        return val.strip() or None
    return str(val) if val else None


def _to_numeric(val):
    if val is None:
        return None

    if isinstance(val, (int, float)):
        return float(val)

    if isinstance(val, str):
        s = val.strip()

        if not s:
            return None

        s = s.replace("\u00A0", " ")

        s_clean = re.sub(r"[^0-9,.\-]", "", s)

        if not s_clean:
            return None

        if "," in s_clean and "." in s_clean:
            last_comma = s_clean.rfind(",")
            last_dot = s_clean.rfind(".")

            if last_dot > last_comma:
                s_clean = s_clean.replace(",", "")
            else:
                s_clean = s_clean.replace(".", "").replace(",", ".")

        elif "," in s_clean:
            s_clean = s_clean.replace(",", ".")

        try:
            return float(s_clean)
        except:
            return None

    try:
        return float(val)
    except:
        return None

def compute_structured_accuracy(extracted, corrected):
    """Calcule la précision (%) entre l'extraction IA/OCR et la correction manuelle."""
    if not extracted or not corrected:
        return None

    total = 0
    correct = 0

    def cmp(v1, v2):
        nonlocal total, correct

        total += 1

        n1 = _to_numeric(v1)
        n2 = _to_numeric(v2)
#si différence très petite (0.01 max) :✔️ considéré comme correct
        if n1 is not None and n2 is not None:
            if abs(n1 - n2) <= 1e-2:
                correct += 1
        else:# comparaison stricte des chaînes
            if str(v1 or "").strip() == str(v2 or "").strip():
                correct += 1

    fields = [
        ("invoice_number", lambda d: d.get("invoice_number")),
        ("date_of_issue", lambda d: d.get("date_of_issue")),
        ("seller_name", lambda d: (d.get("seller_name") or {}).get("name")),
        ("client_name", lambda d: (d.get("client_name") or {}).get("name"))
    ]

    for _, getter in fields:
        cmp(getter(extracted), getter(corrected))

    ext_items = extracted.get("items") or []
    cor_items = corrected.get("items") or []
#👉 compare seulement les items communs
    n = min(len(ext_items), len(cor_items))

    for i in range(n):
        for key in ["description", "quantity", "net_price", "net", "gross", "vat_percentage"]:
            cmp(
                ext_items[i].get(key),
                cor_items[i].get(key)
            )

    if total == 0:
        return None
# les champs correcte / totale des champs *100
    return round((correct / total) * 100, 2)


def save_invoice_to_db(invoice_data, user_id=None):
    conn = get_pg_connection()
    cur = conn.cursor()

    try:
        j = invoice_data.get("json_output") or {}
        items = (invoice_data.get("classification") or {}).get("items") or []
        totals = j.get("totals") or {}

        seller = _extract_name(j.get("seller_name"))
        client = _extract_name(j.get("client_name"))

        cur.execute("""
            INSERT INTO invoices
            (filename, invoice_number, date_of_issue, seller_name, client_name,
             total_net, total_vat, total_gross, user_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            invoice_data.get("filename", ""),
            j.get("invoice_number"),
            j.get("date_of_issue"),
            seller,
            client,
            _to_numeric(totals.get("net")),
            _to_numeric(totals.get("vat")),
            _to_numeric(totals.get("gross")),
            user_id
        ))

        invoice_id = cur.fetchone()[0]

        # INSERT ITEMS
        for it in items:
            cur.execute("""
                INSERT INTO invoices_items
                (invoice_id, description, quantity, net_price, net,
                 gross, vat_percentage, category, account)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                invoice_id,
                (it.get("description") or "").strip() or None,
                _to_numeric(it.get("quantity")),
                _to_numeric(it.get("net_price")),
                _to_numeric(it.get("net")),
                _to_numeric(it.get("gross")),
                _to_numeric(it.get("vat_percentage")),
                (it.get("category") or "").strip() or None,
                (it.get("account_proposed") or it.get("account") or "").strip() or None
            ))

        conn.commit()

        print(f"💾 Enregistré en base (invoice_id={invoice_id})")

        return invoice_id

    except Exception as e:
        conn.rollback()
        print("❌ PostgreSQL ERROR:", e)
        raise

    finally:
        cur.close()
        conn.close()

# ================= NORMALISATION =================
def _normalize_invoice_keys_minimal(data):
    """Normalise juste les clés, sans recalculer les montants."""
    if not isinstance(data, dict):
        return data

    aliases = {
        "invoice_number": ["invoice_number", "invoiceNumber", "numero", "numero_facture", "Invoice Number"],
        "date_of_issue": ["date_of_issue", "dateOfIssue", "date", "Date", "date_emission", "issue_date"],
        "seller_name": ["seller_name", "sellerName", "seller", "Seller", "fournisseur", "vendor"],
        "client_name": ["client_name", "clientName", "client", "Client", "acheteur", "buyer", "Buyer"],
        "items": ["items", "lineItems", "line_items", "Items", "articles"],
        "totals": ["totals", "Totals", "total", "summary"],
    }

    out = dict(data)
    for standard_key, possible_keys in aliases.items():
        if standard_key in out and out[standard_key] is not None:
            continue
        for k in possible_keys:
            if k != standard_key and k in out and out[k] is not None:
                out[standard_key] = out.pop(k, out[k])
                break

    # Les totaux ne sont pas recalculés, juste renommés si besoin
    return out


def _normalize_item_keys(item):
    """Normalise les clés d'un item (gross_worth/ttc → gross, vat_rate → vat_percentage, etc.)."""
    if not isinstance(item, dict):
        return item
    out = dict(item)
    # gross: gross_worth, grossWorth, ttc, TTC, gross_amount...
    gross_aliases = [
    "gross_worth",
    "grossWorth",
    "gross worth",
    "Gross worth",
    "ttc",
    "TTC",
    "gross_amount",
    "grossAmount",
    "total_ttc"
]
    current_gross = _to_numeric(out.get("gross"))
    if current_gross is None or current_gross == 0:
        for k in gross_aliases:
            if k in out and out[k] is not None:
                v = _to_numeric(out[k])
                if v is not None and v != 0:
                    out["gross"] = v
                    break
    # vat_percentage: vat_rate, vatRate, vat_percent, vat%, vat (si c'est un pourcentage)
    vat_pct_aliases = ["vat_rate", "vatRate", "vat_percent", "vat_percent_rate", "vat"]
    current_vat = _to_numeric(out.get("vat_percentage"))
    if current_vat is None or current_vat == 0:
        for k in vat_pct_aliases:
            if k in out and out[k] is not None:
                v = _to_numeric(out[k])
                if v is not None and 0 <= v <= 100:
                    out["vat_percentage"] = v
                    break
    return out


def _normalize_and_fill_items(data):
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return

    for i, it in enumerate(items):
        it = _normalize_item_keys(it)

        # 🔥 SI net = 0 mais quantity et net_price existent
        net_val = _to_numeric(it.get("net"))
        qty = _to_numeric(it.get("quantity"))
        price = _to_numeric(it.get("net_price"))

        if (net_val is None or net_val == 0) and qty and price:
            it["net"] = round(qty * price, 2)

        items[i] = it

def extract_seller_client_blocks(ocr_words):

    if not ocr_words:
        return "", ""

    xs = [w["left"] for w in ocr_words if "left" in w]
    if not xs:
        return "", ""

    median_x = np.median(xs)

    seller = []
    client = []

    for w in ocr_words:
        text = w["text"]

        if w["left"] < median_x:
            seller.append(text)
        else:
            client.append(text)

    return " ".join(seller), " ".join(client)
def extract_invoice_date_from_text(text):
    if not text:
        return ""

    # Format principal
    patterns = [
        r"Date of issue[:\s]*\n?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})",
        r"Issue date[:\s]*\n?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})",
        r"\b([0-9]{2}/[0-9]{2}/[0-9]{4})\b"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return ""
def build_prompt_invoice_markdown(img, filename):
    plain_text = ocr_to_plain_text(img)
    extracted_date = extract_invoice_date_from_text(plain_text)
    print("DATE DETECTEE:", extracted_date)

    spatial_words = ocr_to_spatial_words(img)
    seller_text, client_text = extract_seller_client_blocks(spatial_words)
    print("\n===== OCR TEXT =====\n")
    print(plain_text)
    print("\n====================\n")

    return f"""
Tu es un expert-comptable et analyste de factures.

Fichier: {filename}

Bloc Vendeur :
{seller_text}

Bloc Client :
{client_text}

Texte complet OCR :
{plain_text}

🔹 INSTRUCTIONS :
- Détails du seller et client
- Analyse la facture et **extrait tous les items présents** dans le texte OCR.
- Pour chaque item, affiche exactement ce qui est écrit : description, quantité, Net price, Net worth, VAT, Gross worth.
- Affiche également les totaux **tels qu’ils apparaissent dans la facture**, sans recalcul.
- Présente tout sous forme de Markdown clair et structuré.
- Extraire tous les items présents.
⚠️ RÈGLE ABSOLUE :
- N’ARRONDIS jamais les valeurs.
- N’invente jamais un chiffre absent.
- N’effectue aucun recalcul.
- Copie exactement le texte OCR détecté.
- Si illisible → champ vide uniquement.
- N'invente jamais une valeur absente.

- Si un champ est illisible → laisse vide.
- Si la facture contient des formats européens (7.525,06) → normalise intelligemment.
- Termine toujours par le bloc JSON structuré.

⚠️ FAIBLESSES CRITIQUES
- Note simplement les montants manquants ou incohérents, sans recalcul.

🏆 RECOMMANDATIONS
- Basées uniquement sur les données présentes dans la facture.

📋 OBLIGATOIRE – À LA FIN de ta réponse, ajoute un bloc JSON pour les données structurées, exactement comme suit (sans texte après) :
```json
{{"seller_name": {{"name": "", "address": "", "tax_id": ""}}, "client_name": {{"name": "", "address": "", "tax_id": ""}}, "invoice_number": "", "date_of_issue": "", "items": [{{"description": "", "quantity": 0, "net_price": 0, "net": 0, "gross": 0, "vat_percentage": 0}}], "totals": {{"net": 0, "vat": 0, "gross": 0}}}}
```
- Pour chaque item, remplis **obligatoirement** : description, quantity, net_price, net, **gross** (TTC / Gross worth), **vat_percentage** (taux TVA en %, ex: 10 pour 10%).
- Si la facture affiche "Gross worth" ou "TTC", mets cette valeur dans **gross**. Si elle affiche "VAT [%]" ou "TVA %", mets le nombre (sans le symbole %) dans **vat_percentage**.
- Remplis les totaux (net, vat, gross) de la section récapitulative si présents.
Remplis ce JSON avec les vraies valeurs extraites de la facture. Le bloc doit être le dernier élément de ta réponse.
"""

# ================= IA =================
def analyze_invoice(prompt, retry=0):
    gc = get_groq_llm_client()
    if gc is None:
        return {"error": "GROQ_API_KEY manquante: definir la variable dans .env (voir .env.example)."}
    try:#👉 ici tu envoies le prompt au modèle :
        response = gc.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=4000
        )
        # On récupère le texte brut, sans tenter de parser en JSON
        raw_text = response.choices[0].message.content.strip()
        return {"raw_response": raw_text}
    except Exception as e:
        if retry < MAX_RETRIES:
            time.sleep(BASE_DELAY * (2 ** retry))
            return analyze_invoice(prompt, retry + 1)
        print(f"❌ Erreur analyse Groq (après retries): {e}")
        return {"error": f"Erreur analyse Groq: {e}"}


# ================= CLASSIFICATION =================
_expense_classifier = None
def clean_description(text):
    """Nettoyage des descriptions avant classification"""
    if not text:
        return ""
    text = str(text).lower()
    text = text.replace("\n", " ").replace("\r", " ")
    text = text.replace("[", "").replace("]", "")
    text = text.replace("\"", "").replace("\\", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:200]  # limite longueur si trop long

def _get_classifier():
    """Instancie le classifieur une seule fois"""
    global _expense_classifier
    if _expense_classifier is None:
        try:
            print("ℹ️ Import du classifieur...")
            from classification.predictor import ExpenseClassifier
            print("ℹ️ Instanciation du classifieur...")
            _expense_classifier = ExpenseClassifier()
            print(f"✅ Classifieur chargé : {_expense_classifier.is_available}")
        except Exception as e:
            print(f"⚠️ Classifieur supervisé non chargé: {e}")
            _expense_classifier = False
    return _expense_classifier if _expense_classifier else None

def classify_expense(invoice_json):
    """
    Classifie les items d'une facture.
    - Nettoie les descriptions avant de prédire
    - Fallback 'Non classé' si modèle indisponible
    """
    #👉 tu récupères les lignes de facture
    items = invoice_json.get("items", [])
    if not items:
        return {"items": [], "source": "none"}
#🧠 3. chargement modèle
    clf = _get_classifier()
    if not clf or not clf.is_available:
        print("⚠️ Classifieur indisponible, fallback activé")
        return {
            "items": [
                {
                    "description": it.get("description", ""),
                    "category": "Non classé",
                    "classification_source": "fallback",
                    "precision_score": 0.0,
                }
                for it in items
            ],
            "source": "fallback"
        }

    # Nettoyage des descriptions
    for it in items:
        raw_desc = it.get("description", "")
        it["description_clean"] = clean_description(raw_desc)
        print(f"📝 Original: '{raw_desc}' → Nettoyé: '{it['description_clean']}'")

    # Préparer la liste pour le modèle
    descriptions_clean = [it["description_clean"] for it in items]
    predictions = clf.predict(descriptions_clean)
    
    # Affichage des prédictions pour debug
    for i, p in enumerate(predictions):
        print(f"✅ Item {i}: → {p['category']}")

    # Remplacer les catégories et ajouter source RAG / score / snippets
    for i, it in enumerate(items):
        #🔁 7. injection des résultats dans items
        it["category"] = predictions[i]["category"]
        if "classification_source" in predictions[i]:
            it["classification_source"] = predictions[i]["classification_source"]
        if "precision_score" in predictions[i]:
            it["precision_score"] = predictions[i]["precision_score"]
        elif "confidence" in predictions[i]:
            it["precision_score"] = predictions[i]["confidence"]
        if "similarity_score" in predictions[i]:
            it["similarity_score"] = predictions[i]["similarity_score"]
        

    return {"items": items, "source": "supervised_transformer"}



from ocr_engine import similarity_match, numeric_match

def compute_ocr_precision_from_db(invoice_id):

    conn = get_pg_connection()
    cur = conn.cursor()

    try:

        total = 0
        correct = 0

        # HEADER
        cur.execute("""
            SELECT invoice_number, date_of_issue,
                   seller_name, client_name,
                   total_net, total_vat, total_gross
            FROM invoices
            WHERE id=%s
        """, (invoice_id,))

        ocr_header = cur.fetchone() or [None]*7

        cur.execute("""
            SELECT invoice_number, date_of_issue,
                   seller_name, client_name,
                   total_net, total_vat, total_gross
            FROM invoices_corrected
            WHERE original_invoice_id=%s
            ORDER BY id DESC
            LIMIT 1
        """, (invoice_id,))

        corrected_header = cur.fetchone() or [None]*7

        # HEADER MATCHING
        for i in range(7):

            total += 1

            v1 = normalize_party_value(ocr_header[i])
            v2 = normalize_party_value(corrected_header[i])

            if safe_match(v1, v2):
                correct += 1

        # ITEMS MATCHING
        cur.execute("""
            SELECT description, quantity, net_price,
                   net, gross, vat_percentage
            FROM invoices_items
            WHERE invoice_id=%s
            ORDER BY id
        """, (invoice_id,))

        ocr_items = cur.fetchall()

        cur.execute("""
            SELECT description, quantity, net_price,
                   net, gross, vat_percentage
            FROM invoice_items_corrected
            WHERE corrected_invoice_id = (
                SELECT id FROM invoices_corrected
                WHERE original_invoice_id=%s
                ORDER BY id DESC
                LIMIT 1
            )
            ORDER BY id
        """, (invoice_id,))

        corrected_items = cur.fetchall()

        n = min(len(ocr_items), len(corrected_items))

        for i in range(n):
            for j in range(6):

                total += 1

                v1 = ocr_items[i][j]
                v2 = corrected_items[i][j]

                if safe_match(v1, v2):
                    correct += 1

        if total == 0:
            return 0.0

        return round((correct / total) * 100, 2)

    finally:
        cur.close()
        conn.close()



def normalize_party_value(val):
    if val is None:
        return ""
    if isinstance(val, dict):
        return (val.get("name") or "").strip()
    return str(val).strip()

def safe_match(v1, v2):
    """
    Vérifie la correspondance exacte entre deux valeurs.
    - Pour les nombres: tolérance très faible (1e-4)
    - Pour les chaînes: strip + lower pour éviter les petites différences
    """
    from ocr_engine import numeric_match, similarity_match

    n1 = _to_numeric(v1)
    n2 = _to_numeric(v2)

    if n1 is not None and n2 is not None:
        return abs(n1 - n2) < 1e-4

    s1 = str(v1 or "").strip().lower()
    s2 = str(v2 or "").strip().lower()
    return s1 == s2


def compute_ocr_precision_db(extracted, corrected):
    """
    Calcul plus strict de la précision OCR.
    """
    if not extracted or not corrected:
        return 0.0

    total = 0
    correct = 0

    # HEADER
    fields = ["invoice_number", "date_of_issue", "seller_name", "client_name",
              "total_net", "total_vat", "total_gross"]

    for f in fields:
        total += 1
        if safe_match(extracted.get(f), corrected.get(f)):
            correct += 1

    # ITEMS
    ext_items = extracted.get("items", [])
    cor_items = corrected.get("items", [])

    n = min(len(ext_items), len(cor_items))
    keys = ["description", "quantity", "net_price", "net", "gross", "vat_percentage"]

    for i in range(n):
        for k in keys:
            total += 1
            if safe_match(ext_items[i].get(k), cor_items[i].get(k)):
                correct += 1

    if total == 0:
        return 0.0
    return round((correct / total) * 100, 4)  # Plus précis


def log_ocr_precision_details(invoice_id, extracted, corrected):
    """
    Enregistre les détails OCR et précision dans la base.
    """
    conn = get_pg_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM ocr_precision_details WHERE invoice_id=%s", (invoice_id,))

    rows_to_insert = []
    total = 0
    correct = 0

    # HEADER
    fields = ["invoice_number", "date_of_issue", "seller_name", "client_name",
              "total_net", "total_vat", "total_gross"]

    for f in fields:
        extracted_val = normalize_party_value(extracted.get(f))
        corrected_val = normalize_party_value(corrected.get(f))
        is_correct = safe_match(extracted_val, corrected_val)
        total += 1
        if is_correct:
            correct += 1
        rows_to_insert.append((invoice_id, f, extracted_val, corrected_val, is_correct))

    # ITEMS
    ext_items = extracted.get("items", [])
    cor_items = corrected.get("items", [])
    n = min(len(ext_items), len(cor_items))
    keys = ["description", "quantity", "net_price", "net", "gross", "vat_percentage"]

    for i in range(n):
        for k in keys:
            extracted_val = str(ext_items[i].get(k, "")).strip()
            corrected_val = str(cor_items[i].get(k, "")).strip()
            is_correct = safe_match(extracted_val, corrected_val)
            total += 1
            if is_correct:
                correct += 1
            rows_to_insert.append((invoice_id, f"item_{i+1}.{k}", extracted_val, corrected_val, is_correct))

    precision = round((correct / total) * 100, 4)

    for row in rows_to_insert:
        cur.execute("""
            INSERT INTO ocr_precision_details
            (invoice_id, field_name, extracted_value, corrected_value, is_correct, precision_pct)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (*row, precision))

    conn.commit()
    cur.close()
    conn.close()

    print(f"🎯 Précision OCR enregistrée: {precision}%")
    return precision

from datetime import datetime

def normalize_date_pg(date_str):
    if not date_str:
        return None

    if isinstance(date_str, datetime):
        return date_str

    if not isinstance(date_str, str):
        return None

    date_str = date_str.strip()

    # Essayer plusieurs formats OCR possibles
    formats = [
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y-%m-%d"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except:
            pass

    return None
def save_corrected_invoice_db(original_id, corrected_json):
    """
    Version corrigée et production-safe de l'enregistrement des factures corrigées.
    Gère correctement la foreign key corrected_invoice_id et utilise une transaction atomique.
    """

    conn = get_pg_connection()
    cur = conn.cursor()

    try:
        # ================= TRANSACTION START =================
        conn.autocommit = False

        # ---------- HEADER CORRIGÉ ----------
        cur.execute("""
            INSERT INTO invoices_corrected (
                original_invoice_id,
                invoice_number,
                date_of_issue,
                seller_name,
                client_name,
                total_net,
                total_vat,
                total_gross
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            original_id,
            corrected_json.get("invoice_number"),
            normalize_date_pg(corrected_json.get("date_of_issue")),
            normalize_party_value(corrected_json.get("seller_name")),
            normalize_party_value(corrected_json.get("client_name")),
            _to_numeric(corrected_json.get("totals", {}).get("net")),
            _to_numeric(corrected_json.get("totals", {}).get("vat")),
            _to_numeric(corrected_json.get("totals", {}).get("gross"))
        ))

        # ID généré par invoices_corrected (IMPORTANT pour FK items)
        corrected_invoice_db_id = cur.fetchone()[0]

        # ---------- ITEMS CORRIGÉS ----------
        for item in corrected_json.get("items", []):
            cur.execute("""
                INSERT INTO invoice_items_corrected (
                    corrected_invoice_id,
                    description,
                    quantity,
                    net_price,
                    net,
                    gross,
                    vat_percentage,
                    category,
                    account
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                corrected_invoice_db_id,
                item.get("description"),
                _to_numeric(item.get("quantity")),
                _to_numeric(item.get("net_price")),
                _to_numeric(item.get("net")),
                _to_numeric(item.get("gross")),
                _to_numeric(item.get("vat_percentage")),
                item.get("category"),
                item.get("account")
            ))

        # ---------- OCR PRECISION LOG ----------
        cur.execute("""
            SELECT invoice_number, date_of_issue, seller_name, client_name,
                   total_net, total_vat, total_gross
            FROM invoices
            WHERE id = %s
        """, (original_id,))

        row = cur.fetchone()

        extracted = {
            "invoice_number": row[0] if row else None,
            "date_of_issue": row[1] if row else None,
            "seller_name": row[2] if row else None,
            "client_name": row[3] if row else None,
            "total_net": row[4] if row else None,
            "total_vat": row[5] if row else None,
            "total_gross": row[6] if row else None,
            "items": []
        }

        # Items OCR originaux
        cur.execute("""
            SELECT description, quantity, net_price,
                   net, gross, vat_percentage
            FROM invoices_items
            WHERE invoice_id = %s
            ORDER BY id
        """, (original_id,))

        item_rows = cur.fetchall()

        for r in item_rows:
            extracted["items"].append({
                "description": r[0],
                "quantity": r[1],
                "net_price": r[2],
                "net": r[3],
                "gross": r[4],
                "vat_percentage": r[5]
            })

        # Logging précision OCR détaillée
        # 🔥 Construire une version plate pour le logging
        corrected_for_log = dict(corrected_json)

        totals = corrected_json.get("totals", {})

        corrected_for_log["total_net"] = totals.get("net")
        corrected_for_log["total_vat"] = totals.get("vat")
        corrected_for_log["total_gross"] = totals.get("gross")
        log_ocr_precision_details(original_id, extracted, corrected_for_log)
        # ================= COMMIT =================
        conn.commit()

        return corrected_invoice_db_id

    except Exception as e:
        conn.rollback()
        print("❌ Erreur save_corrected_invoice_db :", e)
        raise

    finally:
        cur.close()
        conn.close()




def get_invoice_json_by_id(invoice_id):
    conn = get_pg_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT json_output
            FROM invoices
            WHERE id = %s
        """, (invoice_id,))

        row = cur.fetchone()

        return row[0] if row else {}

    except Exception:
        return {}

    finally:
        cur.close()
        conn.close()        


def _normalize_text_key(value):
    return (str(value or "").strip().lower()) or None


def _detect_blocking_duplicate_only(invoice_json):
    """
    Pré-check rapide (ultra tôt) pour bloquer l'enregistrement:
    - même fournisseur + même numéro de facture
    Retourne [] si pas de doublon / si infos insuffisantes.
    """
    anomalies = []
    if not isinstance(invoice_json, dict):
        return anomalies

    seller_obj = invoice_json.get("seller_name")
    seller_name = _extract_name(seller_obj)
    invoice_number = (invoice_json.get("invoice_number") or "").strip()

    seller_key = _normalize_text_key(seller_name)
    if not seller_key or not invoice_number:
        return anomalies

    conn = None
    cur = None
    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1
            FROM invoices
            WHERE LOWER(TRIM(COALESCE(seller_name, ''))) = %s
              AND TRIM(COALESCE(invoice_number, '')) = %s
            LIMIT 1
            """,
            (seller_key, invoice_number),
        )
        if cur.fetchone():
            anomalies.append({
                "type": "possible_duplicate_invoice",
                "message": "Doublon détecté: même fournisseur + même numéro de facture",
                "severity": "error",
                "score": 0.98,
            })
    except Exception as e:
        print(f"⚠️ Pré-check doublon indisponible: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return anomalies


def _detect_document_quality_anomalies(invoice_json, user_id=None):
    """
    Détection documentaire:
    - facture potentiellement en doublon (numéro/seller ou seller+date+montant)
    - document incomplet (numéro/date/seller/TVA)
    - incohérences légales simples
    """
    anomalies = []
    if not isinstance(invoice_json, dict):
        return anomalies

    def add(typ, msg, severity="warning", score=0.55):
        anomalies.append({
            "type": typ,
            "message": msg,
            "severity": severity,
            "score": round(float(score), 3),
        })

    seller_obj = invoice_json.get("seller_name")
    seller_name = _extract_name(seller_obj)
    seller_tax_id = (seller_obj or {}).get("tax_id") if isinstance(seller_obj, dict) else None
    invoice_number = (invoice_json.get("invoice_number") or "").strip()
    issue_date = (invoice_json.get("date_of_issue") or "").strip()
    totals = invoice_json.get("totals") or {}
    total_vat = _to_numeric(totals.get("vat"))
    total_net = _to_numeric(totals.get("net"))
    total_gross = _to_numeric(totals.get("gross"))
    items = invoice_json.get("items") or []

    # 1) Incomplétude documentaire
    if not invoice_number:
        add("missing_invoice_number", "Numéro de facture absent", "error", 0.95)
    elif len(invoice_number) < 3:
        add("invalid_invoice_number", f"Numéro de facture trop court ({invoice_number})", "warning", 0.65)

    if not issue_date:
        add("missing_issue_date", "Date de facture absente", "error", 0.9)

    if not seller_name:
        add("missing_seller_name", "Vendeur/Fournisseur absent", "error", 0.9)

    if not seller_tax_id:
        add("missing_seller_tax_id", "Tax ID vendeur absent (incohérence légale possible)", "warning", 0.6)

    # TVA manquante/incohérente
    has_vat_line = any((_to_numeric((it or {}).get("vat_percentage")) or 0) > 0 for it in items if isinstance(it, dict))
    if has_vat_line and (total_vat is None):
        add("missing_total_vat", "TVA totale absente alors que des lignes ont une TVA", "error", 0.9)
    if (total_net is not None and total_gross is not None and total_gross > total_net) and (total_vat is None):
        add("missing_total_vat", "TVA totale absente alors que TTC > HT", "error", 0.9)
    if total_vat is not None and total_vat < 0:
        add("invalid_total_vat", "TVA totale négative", "error", 0.95)

    # 2) Doublons potentiels en base
    conn = None
    cur = None
    try:
        conn = get_pg_connection()
        cur = conn.cursor()

        seller_key = _normalize_text_key(seller_name)

        # Cas fort: même fournisseur + même numéro (ne pas exposer invoice_id)
        if seller_key and invoice_number:
            cur.execute(
                """
                SELECT 1
                FROM invoices
                WHERE LOWER(TRIM(COALESCE(seller_name, ''))) = %s
                  AND TRIM(COALESCE(invoice_number, '')) = %s
                LIMIT 1
                """,
                (seller_key, invoice_number),
            )
            row = cur.fetchone()
            if row:
                add(
                    "possible_duplicate_invoice",
                    "Doublon détecté: même fournisseur + même numéro de facture",
                    "error",
                    0.98,
                )

        # Cas proche: même fournisseur + même date + même total TTC
        if seller_key and issue_date and total_gross is not None:
            cur.execute(
                """
                SELECT total_gross
                FROM invoices
                WHERE LOWER(TRIM(COALESCE(seller_name, ''))) = %s
                  AND TRIM(COALESCE(date_of_issue, '')) = %s
                ORDER BY id DESC
                LIMIT 20
                """,
                (seller_key, issue_date),
            )
            for (db_total_gross,) in cur.fetchall():
                db_g = _to_numeric(db_total_gross)
                if db_g is None:
                    continue
                if abs(db_g - total_gross) <= 0.01:
                    add(
                        "possible_duplicate_invoice",
                        "Doublon possible: même fournisseur + même date + même total TTC",
                        "warning",
                        0.88,
                    )
                    break
    except Exception as e:
        print(f"⚠️ Détection doublons indisponible: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return anomalies

# ================= PIPELINE =================
# Assure-toi d'avoir importé ta fonction detect_anomalies

def process_files(file_paths, user_id=None, auto_save=True):
    all_data = []
    t0_total = time.time()

    for i, filepath in enumerate(file_paths, 1):
        filename = os.path.basename(filepath)
        print(f"\n[{i}/{len(file_paths)}] Traitement: {filename}")

        ext = os.path.splitext(filename)[1].lower()

        try:
            # ================= PDF =================
            if ext == ".pdf":
                pages = convert_from_path(filepath, dpi=300)
                all_responses = []

                for p, page in enumerate(pages, 1):
                    print(f"   → Page {p}/{len(pages)}")
                    img = np.array(page)
                    prompt = build_prompt_invoice_markdown(img, filename)
                    result = analyze_invoice(prompt)
                    if result.get("error"):
                        raise RuntimeError(result.get("error"))
                    all_responses.append(result.get("raw_response", ""))

                raw_response = "\n\n--- PAGE BREAK ---\n\n".join(all_responses)
                parsed_json = safe_json_parse(raw_response)
                normalized_json = _normalize_invoice_keys_minimal(parsed_json)
                # 🔥 Forcer la date si vide
                if not normalized_json.get("date_of_issue"):
                    forced_date = extract_invoice_date_from_text(raw_response)
                    if not forced_date:
                        # fallback depuis OCR direct
                        forced_date = extract_invoice_date_from_text(prompt)

                    if forced_date:
                        print("📌 DATE FORCÉE:", forced_date)
                        normalized_json["date_of_issue"] = forced_date
                _normalize_and_fill_items(normalized_json)
                anomalies_list = detect_anomalies(normalized_json)
                # ✅ Pré-check doublon (ultra tôt)
                early_dupes = _detect_blocking_duplicate_only(normalized_json)
                if early_dupes:
                    anomalies_list.extend(early_dupes)
                    invoice_data = {
                        "filename": filename,
                        "raw_response": raw_response,
                        "json": normalized_json,
                        "json_output": normalized_json,
                        "anomalies": anomalies_list,
                        "classification": {"items": [], "source": "skipped_due_to_duplicate"},
                        "blocked": True,
                        "blocked_reason": "duplicate_invoice",
                    }
                    # aller au post-traitement sans continuer le pipeline
                    raise RuntimeError("__EARLY_DUPLICATE__")

            # ================= IMAGES =================
            elif ext in [".jpg", ".jpeg", ".png"]:
                img = cv2.imread(filepath)
                if img is None:
                    print("⚠️ Image non lisible")
                    continue

                prompt = build_prompt_invoice_markdown(img, filename)
                result = analyze_invoice(prompt)
                if result.get("error"):
                    raise RuntimeError(result.get("error"))
                raw_response = result.get("raw_response", "")
                parsed_json = safe_json_parse(raw_response)
                normalized_json = _normalize_invoice_keys_minimal(parsed_json)
                # 🔥 Forcer la date si vide
                if not normalized_json.get("date_of_issue"):
                    forced_date = extract_invoice_date_from_text(raw_response)
                    if not forced_date:
                        # fallback depuis OCR direct
                        forced_date = extract_invoice_date_from_text(prompt)

                    if forced_date:
                        print("📌 DATE FORCÉE:", forced_date)
                        normalized_json["date_of_issue"] = forced_date
                _normalize_and_fill_items(normalized_json)
                anomalies_list = detect_anomalies(normalized_json)
                # ✅ Pré-check doublon (ultra tôt)
                early_dupes = _detect_blocking_duplicate_only(normalized_json)
                if early_dupes:
                    anomalies_list.extend(early_dupes)
                    invoice_data = {
                        "filename": filename,
                        "raw_response": raw_response,
                        "json": normalized_json,
                        "json_output": normalized_json,
                        "anomalies": anomalies_list,
                        "classification": {"items": [], "source": "skipped_due_to_duplicate"},
                        "blocked": True,
                        "blocked_reason": "duplicate_invoice",
                    }
                    raise RuntimeError("__EARLY_DUPLICATE__")

            # ================= JSON =================
            elif ext == ".json":
                json_data = extract_text_from_json(filepath)
                normalized_json = _normalize_invoice_keys_minimal(json_data)
                _normalize_and_fill_items(normalized_json)
                anomalies_list = detect_anomalies(normalized_json)
                raw_response = ""
                # ✅ Pré-check doublon (ultra tôt)
                early_dupes = _detect_blocking_duplicate_only(normalized_json)
                if early_dupes:
                    anomalies_list.extend(early_dupes)
                    invoice_data = {
                        "filename": filename,
                        "raw_response": raw_response,
                        "json": normalized_json,
                        "json_output": normalized_json,
                        "anomalies": anomalies_list,
                        "classification": {"items": [], "source": "skipped_due_to_duplicate"},
                        "blocked": True,
                        "blocked_reason": "duplicate_invoice",
                    }
                    raise RuntimeError("__EARLY_DUPLICATE__")

            # ================= XML =================
            elif ext == ".xml":
                text_data = extract_text_from_xml(filepath)
                full_text = "\n".join(
                    [line.get("col1", "") if isinstance(line, dict) else str(line) for line in text_data]
                )
                prompt = f"""
Tu es un expert-comptable et analyste de factures.

Fichier: {filename}

Texte fourni (non OCR image) :
{full_text}

Analyse complète en Markdown et JSON.
"""
                result = analyze_invoice(prompt)
                if result.get("error"):
                    raise RuntimeError(result.get("error"))
                raw_response = result.get("raw_response", "")
                parsed_json = safe_json_parse(raw_response)
                normalized_json = _normalize_invoice_keys_minimal(parsed_json)
                # 🔥 Forcer la date si vide
                if not normalized_json.get("date_of_issue"):
                    forced_date = extract_invoice_date_from_text(raw_response)
                    if not forced_date:
                        # fallback depuis OCR direct
                        forced_date = extract_invoice_date_from_text(prompt)

                    if forced_date:
                        print("📌 DATE FORCÉE:", forced_date)
                        normalized_json["date_of_issue"] = forced_date
                _normalize_and_fill_items(normalized_json)
                anomalies_list = detect_anomalies(normalized_json)
                # ✅ Pré-check doublon (ultra tôt)
                early_dupes = _detect_blocking_duplicate_only(normalized_json)
                if early_dupes:
                    anomalies_list.extend(early_dupes)
                    invoice_data = {
                        "filename": filename,
                        "raw_response": raw_response,
                        "json": normalized_json,
                        "json_output": normalized_json,
                        "anomalies": anomalies_list,
                        "classification": {"items": [], "source": "skipped_due_to_duplicate"},
                        "blocked": True,
                        "blocked_reason": "duplicate_invoice",
                    }
                    raise RuntimeError("__EARLY_DUPLICATE__")

            else:
                print(f"⚠️ Format non supporté: {ext}")
                continue

            # ================= CLASSIFICATION + IMPUTATION =================
            classified = classify_expense(normalized_json)
            items_with_accounts = add_account_to_items(classified.get("items", []))
            # 🔧 SÉCURITÉ ABSOLUE : ne jamais perdre les chiffres
            for i, it in enumerate(items_with_accounts):
                original = classified["items"][i]
                for k in ["quantity","net_price","net","gross","vat_percentage"]:
                    it[k] = original.get(k)
                    
            # Conserver la catégorie prédite
            for i, it in enumerate(items_with_accounts):
                it["category"] = classified["items"][i]["category"]
                if "classification_source" in classified["items"][i]:
                    it["classification_source"] = classified["items"][i]["classification_source"]
                if "precision_score" in classified["items"][i]:
                    it["precision_score"] = classified["items"][i]["precision_score"]
                if "similarity_score" in classified["items"][i]:
                    it["similarity_score"] = classified["items"][i]["similarity_score"]
                if "rag_web_snippets" in classified["items"][i]:
                    it["rag_web_snippets"] = classified["items"][i]["rag_web_snippets"]
                if "rag_csv_examples" in classified["items"][i]:
                    it["rag_csv_examples"] = classified["items"][i]["rag_csv_examples"]

            classified["items"] = items_with_accounts
            # Recalcul des anomalies après classification pour inclure precision_score
            anomalies_list = detect_anomalies({
                "items": classified.get("items", []),
                "totals": normalized_json.get("totals", {}),
            })
            # Détection documentaire (doublons + document incomplet)
            doc_anomalies = _detect_document_quality_anomalies(normalized_json, user_id=user_id)
            if doc_anomalies:
                anomalies_list.extend(doc_anomalies)

            # ================= CRÉATION DU DICT FINAL =================
            invoice_data = {
                "filename": filename,
                "raw_response": raw_response,
                "json": normalized_json,
                "json_output": normalized_json,
                "anomalies": anomalies_list,
                "classification": classified,
            }

        except Exception as e:
            # Si doublon bloquant détecté, on garde invoice_data construit et on continue.
            if str(e) == "__EARLY_DUPLICATE__":
                print("⛔ Doublon détecté tôt: pipeline interrompu")
                # invoice_data a déjà été construit au moment du pré-check
            else:
                print(f"⚠️ Erreur extraction {filename}: {e}")
                invoice_data = {
                    "filename": filename,
                    "raw_response": "",
                    "json": {},
                    "json_output": {},
                    "anomalies": [],
                    "error": str(e),
                    "classification": {"items": [], "source": "none"},
                }

        # ================= POST TRAITEMENT =================
        invoice_data = invoice_data if isinstance(invoice_data, dict) else {}
        invoice_data.setdefault("filename", filename)
        invoice_data.setdefault("raw_response", "")
        invoice_data.setdefault("json", {})
        invoice_data.setdefault("json_output", invoice_data.get("json", {}))
        invoice_data.setdefault("anomalies", [])
        invoice_data.setdefault("blocked", False)
        invoice_data.setdefault("blocked_reason", None)

        # Copie dans le dossier business
        try:
            shutil.copy(filepath, BUSINESS_FOLDER)
        except Exception as e:
            print(f"⚠️ Copie fichier échouée: {e}")

        # Affichage JSON et Markdown
        if invoice_data.get("json_output"):
            print("\n=== JSON Structuré ===\n")
            print(json.dumps(invoice_data["json_output"], indent=4, ensure_ascii=False))
            print("\n=======================\n")

        if invoice_data.get("raw_response"):
            print("\n=== Markdown généré ===\n")
            print(invoice_data.get("raw_response", ""))
            print("\n=======================\n")

        # Affichage anomalies
        if invoice_data.get("anomalies"):
            print("\n=== Anomalies détectées ===\n")
            for a in invoice_data["anomalies"]:
                print(f"[{a['severity'].upper()}] {a['message']}")
            print("\n===========================\n")

        all_data.append(invoice_data)

        # En mode "batch" classique on enregistre directement en base.
        # Pour le mode human-in-the-loop, auto_save sera passé à False
        # et l'enregistrement se fera via une route dédiée /invoices/confirm.
        has_blocking_duplicate = any(
            (a.get("type") == "possible_duplicate_invoice" and a.get("severity") == "error")
            for a in (invoice_data.get("anomalies") or [])
        )
        has_processing_error = bool(invoice_data.get("error"))
        has_extracted_payload = bool(invoice_data.get("json_output"))
        if auto_save and not has_blocking_duplicate and not has_processing_error and has_extracted_payload:
            invoice_id = save_invoice_to_db(
                invoice_data,
                user_id=user_id
            )
            invoice_data["invoice_id"] = invoice_id
        elif auto_save and has_processing_error:
            invoice_data["invoice_id"] = None
            print("⛔ Enregistrement ignoré: extraction/IA en erreur")
        elif auto_save and has_blocking_duplicate:
            invoice_data["invoice_id"] = None
            invoice_data["blocked"] = True
            invoice_data["blocked_reason"] = "duplicate_invoice"
            print("⛔ Enregistrement bloqué: doublon détecté")
        time.sleep(MIN_DELAY_BETWEEN_REQUESTS)

    # Mise à jour des métriques runtime
    t_total = time.time() - t0_total
    nb_invoices = len(all_data)
    nb_with_items = sum(1 for d in all_data if (d.get("json_output") or {}).get("items"))
    nb_anomalies = sum(len(d.get("anomalies") or []) for d in all_data)
    nb_lines = sum(len((d.get("classification") or {}).get("items") or []) for d in all_data)
    try:
        from metrics import update_runtime_metrics
        update_runtime_metrics(
            nb_invoices=nb_invoices,
            nb_with_items=nb_with_items,
            processing_time_sec=t_total,
            nb_anomalies=nb_anomalies,
            nb_lines=nb_lines,
        )
    except Exception as e:
        print(f"⚠️ Métriques non mises à jour: {e}")

    return all_data
