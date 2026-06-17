"""Exposition Prometheus : monitoring technique (Grafana), complément de Power BI."""
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from flask import Response

# --- Compteurs d'activité (historique / débit dans Grafana) ---
_c_uploads = Counter(
    "factupro_uploads_total",
    "Nombre de traitements upload OCR réussis",
)
_c_upload_errors = Counter(
    "factupro_upload_errors_total",
    "Échecs de traitement upload OCR",
)
_c_confirmations = Counter(
    "factupro_confirmations_total",
    "Factures confirmées par un comptable",
)
_c_confirmations_edited = Counter(
    "factupro_confirmations_with_edits_total",
    "Confirmations avec correction manuelle (alerte superviseur possible)",
)

# --- Pipeline (fichier runtime, cumul session / conteneur) ---
_g_invoices_processed = Gauge(
    "factupro_invoices_processed_total",
    "Factures traitées par le pipeline (cumul runtime)",
)
_g_invoices_with_items = Gauge(
    "factupro_invoices_with_items_total",
    "Factures avec au moins une ligne extraite (cumul runtime)",
)
_g_processing_seconds = Gauge(
    "factupro_processing_seconds_total",
    "Temps total de traitement pipeline (secondes)",
)
_g_anomalies = Gauge(
    "factupro_anomalies_total",
    "Anomalies détectées (cumul runtime)",
)
_g_lines = Gauge(
    "factupro_invoice_lines_total",
    "Lignes de facture traitées (cumul runtime)",
)
_g_ocr_precision = Gauge(
    "factupro_ocr_precision_pct",
    "Précision OCR moyenne (%, source PostgreSQL ou runtime)",
)
_g_avg_processing = Gauge(
    "factupro_avg_processing_seconds",
    "Temps moyen de traitement par facture (secondes)",
)
_g_pipeline_success = Gauge(
    "factupro_pipeline_success_rate_pct",
    "Taux de succès pipeline (factures avec items / traitées)",
)
_g_anomaly_rate = Gauge(
    "factupro_anomaly_rate_pct",
    "Taux d'anomalies par rapport aux lignes traitées (%)",
)

# --- PostgreSQL (état réel, persistant — ce que Power BI ne suit pas en temps réel) ---
_g_db_invoices = Gauge("factupro_db_invoices_total", "Factures en base PostgreSQL")
_g_db_corrected = Gauge(
    "factupro_db_invoices_corrected",
    "Factures ayant une version corrigée en base",
)
_g_db_lines = Gauge("factupro_db_invoice_lines_total", "Lignes articles en base")
_g_db_items_uncategorized = Gauge(
    "factupro_db_items_uncategorized",
    "Lignes sans catégorie comptable",
)
_g_db_users = Gauge("factupro_db_users_total", "Utilisateurs enregistrés")
_g_db_comptables = Gauge("factupro_db_users_comptable", "Comptables actifs")
_g_alerts_unread = Gauge(
    "factupro_supervisor_alerts_unread",
    "Alertes superviseur non lues",
)
_g_alerts_total = Gauge(
    "factupro_supervisor_alerts_total",
    "Alertes superviseur (toutes)",
)
_g_ocr_confirmed_db = Gauge(
    "factupro_ocr_confirmed_invoices_db",
    "Factures avec précision OCR enregistrée (PostgreSQL)",
)
_g_correction_rate = Gauge(
    "factupro_correction_rate_pct",
    "Part des factures corrigées / total en base (%)",
)


def record_upload_success():
    _c_uploads.inc()


def record_upload_error():
    _c_upload_errors.inc()


def record_confirm_success(*, manual_edit: bool = False):
    _c_confirmations.inc()
    if manual_edit:
        _c_confirmations_edited.inc()


def _sync_pipeline_gauges(rt, agg):
    nb_processed = float(rt.get("nb_invoices_processed") or 0)
    nb_lines = float(rt.get("nb_total_lines") or 0)
    nb_anomalies = float(rt.get("nb_anomalies") or 0)

    _g_invoices_processed.set(nb_processed)
    _g_invoices_with_items.set(float(rt.get("nb_invoices_with_items") or 0))
    _g_processing_seconds.set(float(rt.get("total_processing_time") or 0))
    _g_anomalies.set(nb_anomalies)
    _g_lines.set(nb_lines)
    _g_ocr_precision.set(float(agg.get("ocr_precision_pct") or 0))
    _g_avg_processing.set(float(agg.get("avg_processing_time_sec") or 0))
    _g_pipeline_success.set(float(agg.get("pipeline_success_rate_pct") or 0))
    _g_anomaly_rate.set(
        round(nb_anomalies / nb_lines * 100, 2) if nb_lines > 0 else 0.0
    )


def _sync_db_gauges(db):
    _g_db_invoices.set(float(db.get("db_invoices_total") or 0))
    _g_db_corrected.set(float(db.get("db_invoices_corrected") or 0))
    _g_db_lines.set(float(db.get("db_invoice_lines_total") or 0))
    _g_db_items_uncategorized.set(float(db.get("db_items_uncategorized") or 0))
    _g_db_users.set(float(db.get("db_users_total") or 0))
    _g_db_comptables.set(float(db.get("db_users_comptable") or 0))
    _g_alerts_unread.set(float(db.get("supervisor_alerts_unread") or 0))
    _g_alerts_total.set(float(db.get("supervisor_alerts_total") or 0))
    _g_ocr_confirmed_db.set(float(db.get("ocr_confirmed_invoices") or 0))
    _g_correction_rate.set(float(db.get("correction_rate_pct") or 0))


def prometheus_metrics_response():
    from metrics import get_all_metrics, get_db_technical_snapshot, load_runtime_metrics

    rt = load_runtime_metrics()
    agg = get_all_metrics()
    db = get_db_technical_snapshot()

    _sync_pipeline_gauges(rt, agg)
    _sync_db_gauges(db)

    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
