import json
import os
import hashlib

RUNTIME_METRICS_PATH = "runtime_metrics.json"


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
            return

        # Snapshot pipeline stabilité métrique
        if pipeline_json is not None:
            new_hash = compute_invoice_snapshot_hash(pipeline_json)

            if data.get("last_pipeline_hash") == new_hash:
                return

            data["last_pipeline_hash"] = new_hash

        last_score = data.get("last_logged_accuracy")

        if last_score is not None:
            if abs(last_score - score) < 1e-6:
                return

        data["ocr_scores"].append(score)
        data["last_logged_accuracy"] = score

    except Exception:
        return

    save_runtime_metrics(data)


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
    else:
        scores = rt.get("ocr_scores", [])
        avg_structured_accuracy = sum(scores) / len(scores) if scores else 0

    return {
        "nb_invoices_processed": nb_processed,
        "ocr_precision_pct": round(avg_structured_accuracy, 2),
        "avg_processing_time_sec": round(avg_processing_time, 2),
        "nb_confirmed_invoices": rt["nb_confirmed_invoices"],
        "pipeline_success_rate_pct": round(success_rate, 2)
    }