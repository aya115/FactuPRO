import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

# Toujours le fichier à côté de ce module (évite cwd différent ; Docker : /app/runtime_metrics.json).
RUNTIME_METRICS_PATH = os.environ.get(
    "RUNTIME_METRICS_JSON_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime_metrics.json"),
)


# ================= STORAGE =================

def load_runtime_metrics():
    default_metrics = {
        "nb_invoices_processed": 0,
        "nb_invoices_with_items": 0,
        "total_processing_time": 0.0,
        "nb_confirmed_invoices": 0,
        "ocr_scores": [],
        "nb_anomalies": 0,
        "nb_total_lines": 0,
        "last_pipeline_hash": "",
        "last_logged_accuracy": None
    }

    if not os.path.exists(RUNTIME_METRICS_PATH):
        return default_metrics

    try:
        with open(RUNTIME_METRICS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        for k, v in default_metrics.items():
            data.setdefault(k, v)

        return data

    except Exception:
        return default_metrics


def save_runtime_metrics(data):
    with open(RUNTIME_METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ================= PIPELINE HASH =================

def compute_invoice_snapshot_hash(invoice_json):

    if not invoice_json:
        return ""

    try:
        normalized = json.dumps(
            invoice_json,
            sort_keys=True,
            ensure_ascii=True
        )

        return hashlib.sha256(
            normalized.encode("utf-8")
        ).hexdigest()

    except Exception:
        return ""


# ================= UPDATE METRICS =================

def update_structured_accuracy(accuracy_pct, pipeline_json=None):

    data = load_runtime_metrics()

    try:
        score = float(accuracy_pct)

        if score != score:
            logger.warning(
                "update_structured_accuracy: score NaN ignoré (path=%s)",
                RUNTIME_METRICS_PATH,
            )
            return

        # Évite uniquement un double-enregistrement pour le MÊME payload corrigé (double clic).
        # Ne PAS comparer au dernier score : deux factures différentes peuvent toutes deux faire 100 %%.
        if pipeline_json is not None:
            new_hash = compute_invoice_snapshot_hash(pipeline_json)
            if new_hash and data.get("last_pipeline_hash") == new_hash:
                msg = (
                    f"[metrics] update_structured_accuracy SKIP doublon hash={new_hash[:12]}… "
                    f"path={RUNTIME_METRICS_PATH}"
                )
                logger.info(msg)
                print(msg, flush=True)
                return

            if new_hash:
                data["last_pipeline_hash"] = new_hash

        data["ocr_scores"].append(score)
        data["last_logged_accuracy"] = score
        data["nb_confirmed_invoices"] = int(data.get("nb_confirmed_invoices") or 0) + 1

        msg = (
            f"[metrics] update_structured_accuracy OK score={score} "
            f"n_scores={len(data['ocr_scores'])} path={RUNTIME_METRICS_PATH}"
        )
        logger.info(msg)
        print(msg, flush=True)

    except Exception as ex:
        logger.exception(
            "update_structured_accuracy: échec avant sauvegarde (path=%s): %s",
            RUNTIME_METRICS_PATH,
            ex,
        )
        return

    try:
        save_runtime_metrics(data)
    except Exception as ex:
        logger.exception(
            "update_structured_accuracy: écriture fichier impossible %s: %s",
            RUNTIME_METRICS_PATH,
            ex,
        )


# ================= UPDATE GLOBAL METRICS =================

def update_runtime_metrics(
        nb_invoices,
        nb_with_items,
        processing_time_sec,
        nb_anomalies,
        nb_lines
):

    data = load_runtime_metrics()

    data["nb_invoices_processed"] += int(nb_invoices or 0)
    data["nb_invoices_with_items"] += int(nb_with_items or 0)
    data["total_processing_time"] += float(processing_time_sec or 0)
    data["nb_anomalies"] += int(nb_anomalies or 0)
    data["nb_total_lines"] += int(nb_lines or 0)

    save_runtime_metrics(data)


# ================= METRICS QUERY =================

def get_ocr_precision_avg_from_db():
    """
    Moyenne de précision OCR par facture confirmée (persistée en PostgreSQL).
    Le fichier runtime_metrics.json est éphémère sous Docker ; la base est la source de vérité.
    """
    try:
        from utils import get_pg_connection

        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT AVG(precision_pct)::float, COUNT(*)::int
            FROM (
                SELECT invoice_id, MAX(precision_pct) AS precision_pct
                FROM ocr_precision_details
                GROUP BY invoice_id
            ) per_invoice
            """
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row or row[1] is None or int(row[1]) == 0:
            return None, 0
        return float(row[0] or 0), int(row[1])
    except Exception as ex:
        logger.warning("get_ocr_precision_avg_from_db: %s", ex)
        return None, 0


def get_all_metrics(ocr_precision_override=None):

    rt = load_runtime_metrics()

    nb_processed = max(rt["nb_invoices_processed"], 0)

    success_rate = (
        (rt["nb_invoices_with_items"] / nb_processed * 100)
        if nb_processed > 0 else 0
    )

    avg_processing_time = (
        rt["total_processing_time"] / nb_processed
        if nb_processed > 0 else 0
    )

    if ocr_precision_override is not None:
        avg_structured_accuracy = float(ocr_precision_override)
        ocr_confirmed_count = int(rt.get("nb_confirmed_invoices") or 0)
    else:
        db_avg, db_count = get_ocr_precision_avg_from_db()
        if db_count > 0 and db_avg is not None:
            avg_structured_accuracy = db_avg
            ocr_confirmed_count = db_count
        else:
            scores = rt.get("ocr_scores", [])
            avg_structured_accuracy = sum(scores) / len(scores) if scores else 0
            ocr_confirmed_count = len(scores)

    return {
        "nb_invoices_processed": nb_processed,
        "ocr_precision_pct": round(avg_structured_accuracy, 2),
        "ocr_precision": round(avg_structured_accuracy, 2),
        "ocr_confirmed_count": ocr_confirmed_count,
        "avg_processing_time_sec": round(avg_processing_time, 2),
        "nb_confirmed_invoices": max(
            int(rt.get("nb_confirmed_invoices") or 0),
            ocr_confirmed_count,
        ),
        "pipeline_success_rate_pct": round(success_rate, 2),
    }


def get_db_technical_snapshot():
    """
    Instantané PostgreSQL pour Grafana / Prometheus (complément Power BI).
    Métriques opérationnelles : alertes, lignes, corrections, catégorisation.
    """
    empty = {
        "db_invoices_total": 0,
        "db_invoices_corrected": 0,
        "db_invoice_lines_total": 0,
        "db_items_uncategorized": 0,
        "db_users_total": 0,
        "db_users_comptable": 0,
        "supervisor_alerts_unread": 0,
        "supervisor_alerts_total": 0,
        "ocr_confirmed_invoices": 0,
        "ocr_precision_db_pct": 0.0,
        "correction_rate_pct": 0.0,
    }
    try:
        from utils import get_pg_connection

        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                (SELECT COUNT(*)::int FROM invoices),
                (SELECT COUNT(DISTINCT original_invoice_id)::int FROM invoices_corrected),
                (SELECT COUNT(*)::int FROM invoices_items),
                (SELECT COUNT(*)::int FROM invoices_items
                 WHERE category IS NULL OR TRIM(category) = ''),
                (SELECT COUNT(*)::int FROM users),
                (SELECT COUNT(*)::int FROM users WHERE role = 'comptable'),
                (SELECT COUNT(*)::int FROM supervisor_alerts WHERE is_read = FALSE),
                (SELECT COUNT(*)::int FROM supervisor_alerts),
                (SELECT COUNT(DISTINCT invoice_id)::int FROM ocr_precision_details)
            """
        )
        row = cur.fetchone()
        db_avg, db_count = get_ocr_precision_avg_from_db()
        cur.close()
        conn.close()

        invoices = int(row[0] or 0)
        corrected = int(row[1] or 0)
        correction_rate = (
            round(corrected / invoices * 100, 2) if invoices > 0 else 0.0
        )

        return {
            "db_invoices_total": invoices,
            "db_invoices_corrected": corrected,
            "db_invoice_lines_total": int(row[2] or 0),
            "db_items_uncategorized": int(row[3] or 0),
            "db_users_total": int(row[4] or 0),
            "db_users_comptable": int(row[5] or 0),
            "supervisor_alerts_unread": int(row[6] or 0),
            "supervisor_alerts_total": int(row[7] or 0),
            "ocr_confirmed_invoices": int(row[8] or 0),
            "ocr_precision_db_pct": round(float(db_avg or 0), 2),
            "correction_rate_pct": correction_rate,
        }
    except Exception as ex:
        logger.warning("get_db_technical_snapshot: %s", ex)
        return empty
