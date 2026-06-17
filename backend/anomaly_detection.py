# -*- coding: utf-8 -*-
"""
Détection des anomalies sur les factures.

Version hybride:
- règles métiers déterministes (cohérence calculs / TVA)
- score sémantique description <-> catégorie via embeddings (sans historique)
"""
import os
import re
from typing import List, Dict

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None

# ================= CONFIG DÉTECTION ANOMALIES =================
ANOMALY_ALGORITHM = "hybrid_rule_plus_semantic"
TOLERANCE_PCT = 1.0
VALID_VAT_RATES = [5.0, 10.0, 20.0, 2.1, 0]
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
SEMANTIC_SIMILARITY_MIN = 0.33
# Après reranking hybride, beaucoup de scores restent entre 0.35–0.55 ; 0.42 limite les faux positifs « faible précision ».
CLASSIFICATION_PRECISION_MIN = float(os.environ.get("CLASSIFICATION_PRECISION_MIN", "0.42"))

# pondérations du score global [0..1]
WEIGHTS = {
    "rule_error": 0.35,
    "rule_warning": 0.15,
    "semantic_mismatch": 0.25,
    "format_issue": 0.10,
}

_EMBEDDER = None


def _clamp01(value):
    return max(0.0, min(1.0, float(value)))


def get_anomaly_config():
    """Retourne la config pour documentation / métriques."""
    return {
        "algorithm": ANOMALY_ALGORITHM,
        "variables": [
            "quantity", "net_price", "net", "gross", "vat_percentage", "vat_rate",
            "description", "category", "totals.net", "totals.vat", "totals.gross"
        ],
        "threshold_pct": TOLERANCE_PCT,
        "valid_vat_rates": VALID_VAT_RATES,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "semantic_similarity_min": SEMANTIC_SIMILARITY_MIN,
        "classification_precision_min": CLASSIFICATION_PRECISION_MIN,
        "weights": WEIGHTS,
    }


def _to_float(val):
    """
    Convertit une valeur en float avec gestion de formats internationaux:
    - 1 234,56
    - 1\u202f234,56 €
    - USD 1,234.56
    - 1'234.50
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if not isinstance(val, str):
        return None

    s = str(val).strip()
    if not s:
        return None

    # supprimer devise et symboles non numériques utiles
    s = s.replace("\u202f", " ").replace("\xa0", " ").replace("'", "")
    s = re.sub(r"[^\d,\.\-\s]", "", s).strip()
    if not s:
        return None
    s = re.sub(r"\s+", "", s)

    # déterminer séparateur décimal
    comma_count = s.count(",")
    dot_count = s.count(".")

    if comma_count > 0 and dot_count > 0:
        # dernier séparateur rencontré = décimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif comma_count > 0:
        # ",": décimal si 1-2 chiffres à droite, sinon milliers
        parts = s.split(",")
        if len(parts[-1]) in (1, 2):
            s = "".join(parts[:-1]) + "." + parts[-1]
        else:
            s = "".join(parts)
    elif dot_count > 0:
        # ".": décimal si 1-2 chiffres à droite, sinon milliers
        parts = s.split(".")
        if len(parts[-1]) in (1, 2):
            s = "".join(parts[:-1]) + "." + parts[-1]
        else:
            s = "".join(parts)

    try:
        return float(s)
    except ValueError:
        return None


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is not None:
        return _EMBEDDER
    if SentenceTransformer is None:
        return None
    try:
        _EMBEDDER = SentenceTransformer(EMBEDDING_MODEL_NAME)
        return _EMBEDDER
    except Exception:
        return None


def _semantic_similarity(text_a, text_b):
    """
    Similarité cosinus [0..1] entre deux textes via embedding.
    Retourne None si le modèle n'est pas disponible.
    """
    if not text_a or not text_b:
        return None
    embedder = _get_embedder()
    if embedder is None:
        return None
    try:
        vectors = embedder.encode(
            [str(text_a), str(text_b)],
            normalize_embeddings=True,
            show_progress_bar=False
        )
#Cosinus Cos(0°) = 1 → vecteurs identiques
#Cos(90°) = 0 → vecteurs orthogonaux → pas de similarité
#Cos(180°) = -1 → vecteurs opposés
#Donc ici, score est entre -1 et 1.
        score = float(vectors[0] @ vectors[1])  # cos sim car normalisé
        return _clamp01((score + 1.0) / 2.0)    # map [-1,1] -> [0,1]
    except Exception:
        return None


def _severity_weight(severity):
    return WEIGHTS["rule_error"] if severity == "error" else WEIGHTS["rule_warning"]


def _add(anomalies: List[Dict], typ, message, severity, score):
    anomalies.append({
        "type": typ,
        "message": message,
        "severity": severity,
        "score": round(_clamp01(score), 3),
    })


def detect_anomalies(invoice):
    """
    Détecte les anomalies sur une facture structurée.

    Returns:
        list: [{"type", "message", "severity", "score"}, ...]
    """
    anomalies = []
    items = invoice.get("items") or invoice.get("lineItems") or []
    totals = invoice.get("totals") or {}

    if not items:
        return anomalies

    global_score = 0.0
    parse_failures = 0#compteur d’échecs de conversion numérique (quantité, net, prix).

    # ---- 1) Vérification prix × quantité ≈ net par ligne ----
    for i, it in enumerate(items):
        qty = _to_float(it.get("quantity"))
        net = _to_float(it.get("net"))
        net_price = _to_float(it.get("net_price"))

        if qty is None and it.get("quantity") is not None:
            parse_failures += 1
        if net is None and it.get("net") is not None:
            parse_failures += 1
        if net_price is None and it.get("net_price") is not None:
            parse_failures += 1

        if qty is not None and net_price is not None and net is not None:
            expected_net = qty * net_price
            if expected_net > 0:
                delta_pct = abs(net - expected_net) / expected_net * 100
                if delta_pct > TOLERANCE_PCT:
                    desc = (it.get("description") or "")[:40]
                    sev = "error" if delta_pct > 5 else "warning"
                    score = min(1.0, delta_pct / 100.0 + 0.25)#Pourquoi +0.25 ? Pour donner un minimum de gravité, même si l’écart est légèrement supérieur à la tolérance.
                    _add(
                        anomalies,
                        "calcul_ligne",
                        f"Ligne {i+1} ({desc}...): {qty} x {net_price} != {net} "
                        f"(attendu: {expected_net:.2f})",
                        sev,
                        score,
                    )
                    global_score += _severity_weight(sev)

    # ---- 2) Vérification somme des lignes = totaux ----
    sum_net = sum(_to_float(it.get("net")) or 0 for it in items)
    sum_gross = sum(_to_float(it.get("gross")) or 0 for it in items)
    total_net = _to_float(totals.get("net"))
    total_vat = _to_float(totals.get("vat"))
    total_gross = _to_float(totals.get("gross"))
#Vérifie que la somme des nets des lignes ≈ total net.
    net_totals_ok = True
    if total_net is not None and total_net > 0 and sum_net > 0:
        delta_net_pct = abs(sum_net - total_net) / total_net * 100
        if delta_net_pct > TOLERANCE_PCT:
            net_totals_ok = False
            _add(
                anomalies,
                "total_net",
                f"Somme net lignes ({sum_net:.2f}) != total net facture ({total_net:.2f})",
                "error",
                min(1.0, delta_net_pct / 100.0 + 0.35),
            )
            global_score += WEIGHTS["rule_error"]
#Vérifie si total_gross ≈ total_net + TVA.
    totals_ttc_coherent = False
    if total_net is not None and total_gross is not None:
        expected_gross = total_net + (total_vat or 0)
        if expected_gross > 0:
            ttc_delta_pct = abs(total_gross - expected_gross) / expected_gross * 100
            totals_ttc_coherent = ttc_delta_pct <= TOLERANCE_PCT

    if total_gross is not None and total_gross > 0 and sum_gross > 0:
        delta_ttc_pct = abs(sum_gross - total_gross) / total_gross * 100
        if delta_ttc_pct > TOLERANCE_PCT:
            _add(
                anomalies,
                "total_ttc",
                f"Somme TTC lignes ({sum_gross:.2f}) != total TTC facture ({total_gross:.2f})",
                "error",
                min(1.0, delta_ttc_pct / 100.0 + 0.35),
            )
            global_score += WEIGHTS["rule_error"]

    # ---- 3) Vérification TTC ligne ---- Vérifie que TTC ≥ Net sur chaque ligne.
    for i, it in enumerate(items):
        net = _to_float(it.get("net"))
        gross = _to_float(it.get("gross"))
        if net is None or net <= 0 or gross is None:
            continue
        if gross < net:
            if gross == 0 and sum_gross == 0 and totals_ttc_coherent and net_totals_ok:
                continue
            _add(
                anomalies,
                "ttc_inferieur_net",
                f"Ligne {i+1}: TTC ({gross:.2f}) inferieur au net ({net:.2f})",
                "error",
                0.85,
            )
            global_score += WEIGHTS["rule_error"]

    # ---- 4) Vérification taux de TVA ----
    for i, it in enumerate(items):
        vat_raw = it.get("vat_rate", it.get("vat_percentage"))
        vat_rate = _to_float(vat_raw)
        if vat_raw is not None and vat_rate is None:
            parse_failures += 1
        if vat_rate is not None and vat_rate > 0:
            rate_pct = vat_rate * 100 if vat_rate <= 1 else vat_rate
            if not any(abs(rate_pct - r) < 0.1 for r in VALID_VAT_RATES):
                _add(
                    anomalies,
                    "taux_tva",
                    f"Ligne {i+1}: taux TVA {rate_pct:.2f}% non standard",
                    "warning",
                    0.55,
                )
                global_score += WEIGHTS["rule_warning"]

    # ---- 5) Cohérence sémantique description <-> catégorie ----
    for i, it in enumerate(items):
        desc = (it.get("description") or "").strip()
        category = (it.get("category") or "").strip()
        if not desc or not category:
            continue
        if category == "Non classé" or it.get("classification_source") == "fallback":
            continue
        sim = _semantic_similarity(desc, category)
        if sim is None:
            continue
        if sim < SEMANTIC_SIMILARITY_MIN:
            semantic_score = _clamp01((SEMANTIC_SIMILARITY_MIN - sim) + 0.45)
            _add(
                anomalies,
                "semantic_category_mismatch",
                f"Ligne {i+1}: description peu coherente avec categorie '{category}' (sim={sim:.2f})",
                "warning",
                semantic_score,
            )
            global_score += WEIGHTS["semantic_mismatch"] * (1.0 - sim)

    # ---- 6) Faible précision de classification ----
    for i, it in enumerate(items):
        precision = it.get("precision_score", it.get("confidence"))
        if precision is None:
            continue
        precision_val = _to_float(precision)
        if precision_val is None:
            continue
        if precision_val < CLASSIFICATION_PRECISION_MIN:
            low_conf_score = _clamp01((CLASSIFICATION_PRECISION_MIN - precision_val) + 0.45)
            _add(
                anomalies,
                "low_classification_precision",
                f"Ligne {i+1}: precision de classification faible ({precision_val:.4f})",
                "warning",
                low_conf_score,
            )
            global_score += WEIGHTS["semantic_mismatch"] * (1.0 - precision_val)
#Si certaines valeurs n’ont pas pu être converties correctement, ajoute une anomalie de format.
    if parse_failures > 0:
        _add(
            anomalies,
            "format_montant",
            f"Formats numeriques ambigus detectes ({parse_failures} champ(s))",
            "warning",
            min(1.0, 0.25 + parse_failures * 0.05),
        )
        global_score += WEIGHTS["format_issue"]

    # score agrégé pour la facture
    # score agrégé pour la facture uniquement si > 0
    if global_score > 0:
        _add(
            anomalies,
            "invoice_risk_score",
            "Score global de risque anomalie facture",
            "warning" if global_score < 0.6 else "error",
            _clamp01(global_score),
        )

    return anomalies
