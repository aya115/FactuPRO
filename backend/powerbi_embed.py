"""Configuration embed Power BI (pages superviseur, URLs)."""

import json
import os
from pathlib import Path

def _config_path():
    """Fichier persistant (volume Docker uploads ou data/ en local)."""
    uploads = Path(os.environ.get("UPLOAD_FOLDER", "/app/uploads"))
    if uploads.is_dir() or os.environ.get("UPLOAD_FOLDER"):
        return uploads / "powerbi_pages.json"
    return Path(__file__).resolve().parent / "data" / "powerbi_pages.json"


CONFIG_PATH = _config_path()

DEFAULT_REPORT_ID = "69dc2b69-b15b-4f93-9823-d605bdd2ae5e"
DEFAULT_PAGE_3_ID = "95265ac3319c3eb069d9"
DEFAULT_PAGE_5_ID = "d7076eb25b057d6ac5a6"


def _bundled_defaults_path():
    return Path(__file__).resolve().parent / "data" / "powerbi_pages.json"


def _load_file_config():
    bundled = _bundled_defaults_path()
    paths = []
    if bundled.is_file() and bundled != CONFIG_PATH:
        paths.append(bundled)
    if CONFIG_PATH.is_file():
        paths.append(CONFIG_PATH)
    merged = {}
    for path in paths:
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f) or {}
                for key, val in data.items():
                    if val is not None and str(val).strip() != "":
                        merged[key] = val
        except (json.JSONDecodeError, OSError):
            continue
    return merged


def _save_file_config(data):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_powerbi_config():
    """Fusionne fichier JSON + variables d'environnement."""
    cfg = _load_file_config()
    report_id = (
        os.environ.get("POWERBI_REPORT_ID")
        or cfg.get("report_id")
        or DEFAULT_REPORT_ID
    ).strip()
    supervisor_report_id = (
        os.environ.get("POWERBI_SUPERVISOR_REPORT_ID")
        or cfg.get("supervisor_report_id")
        or ""
    ).strip()
    page_3_id = (
        os.environ.get("POWERBI_PAGE_3_ID")
        or cfg.get("page_3_id")
        or DEFAULT_PAGE_3_ID
    ).strip()
    page_5_id = (
        os.environ.get("POWERBI_PAGE_5_ID")
        or cfg.get("page_5_id")
        or DEFAULT_PAGE_5_ID
    ).strip()
    page_3_name = (
        os.environ.get("POWERBI_PAGE_3_NAME") or cfg.get("page_3_name") or "Page 3"
    ).strip()
    page_5_name = (
        os.environ.get("POWERBI_PAGE_5_NAME") or cfg.get("page_5_name") or "Page 5"
    ).strip()
    return {
        "report_id": report_id,
        "supervisor_report_id": supervisor_report_id,
        "page_3_id": page_3_id,
        "page_5_id": page_5_id,
        "page_3_name": page_3_name,
        "page_5_name": page_5_name,
    }


def update_powerbi_pages(payload):
    """Met à jour le fichier JSON (admin)."""
    current = _load_file_config()
    allowed = (
        "report_id",
        "supervisor_report_id",
        "page_3_id",
        "page_5_id",
        "page_3_name",
        "page_5_name",
    )
    for key in allowed:
        if key in payload and payload[key] is not None:
            current[key] = str(payload[key]).strip()
    _save_file_config(current)
    return get_powerbi_config()


def _page_segment_is_guid(segment):
    """GUID Power BI (avec tirets) → paramètre pageId ; sinon nom interne de page."""
    return bool(segment and "-" in segment and len(segment) >= 32)


def _build_embed_url(report_id, page_id=None, page_name=None, hide_navigation=False):
    from urllib.parse import urlencode

    query = {
        "reportId": report_id,
        "autoAuth": "true",
    }
    segment = (page_id or page_name or "").strip()
    if segment:
        # L’ID dans l’URL app.powerbi.com/.../05287cbe... est le *name* de page, pas pageId.
        if _page_segment_is_guid(segment):
            query["pageId"] = segment
        else:
            query["pageName"] = segment
    elif page_name:
        query["pageName"] = page_name
    if hide_navigation:
        embed_config = {
            "navContentPaneEnabled": False,
            "filterPaneEnabled": False,
            "panes": {
                "pageNavigation": {"visible": False},
                "filters": {"expanded": False, "visible": False},
            },
        }
    else:
        embed_config = {
            "navContentPaneEnabled": True,
            "filterPaneEnabled": False,
        }
    query["config"] = json.dumps(embed_config, separators=(",", ":"))
    if hide_navigation:
        query["navContentPaneEnabled"] = "false"
        query["filterPaneEnabled"] = "false"
        query["pageNavigation"] = "false"
    return f"https://app.powerbi.com/reportEmbed?{urlencode(query)}"


def supervisor_embed_payload():
    cfg = get_powerbi_config()
    dedicated = bool(cfg["supervisor_report_id"])
    report_id = cfg["supervisor_report_id"] or cfg["report_id"]
    pages = [
        {
            "key": "ocr",
            "label": "OCR & corrections",
            "page_id": cfg["page_3_id"],
            "page_name": cfg["page_3_name"],
            "embed_url": _build_embed_url(
                report_id,
                page_id=cfg["page_3_id"] or None,
                page_name=cfg["page_3_name"] if not cfg["page_3_id"] else None,
                hide_navigation=True,
            ),
            "view_url": _view_url(cfg["report_id"], cfg["page_3_id"]),
        },
        {
            "key": "alerts",
            "label": "Alertes & comptes PCG",
            "page_id": cfg["page_5_id"],
            "page_name": cfg["page_5_name"],
            "embed_url": _build_embed_url(
                report_id,
                page_id=cfg["page_5_id"] or None,
                page_name=cfg["page_5_name"] if not cfg["page_5_id"] else None,
                hide_navigation=True,
            ),
            "view_url": _view_url(cfg["report_id"], cfg["page_5_id"]),
        },
    ]
    configured = bool(
        dedicated or (cfg["page_3_id"] and cfg["page_5_id"])
    )
    return {
        "report_id": report_id,
        "dedicated_supervisor_report": dedicated,
        "pages_configured": configured,
        "pages": pages,
        "admin_embed_url": _build_embed_url(cfg["report_id"], hide_navigation=False),
    }


def _view_url(report_id, page_id=None):
    if page_id:
        return (
            f"https://app.powerbi.com/groups/me/reports/{report_id}/"
            f"{page_id}?experience=power-bi"
        )
    return f"https://app.powerbi.com/groups/me/reports/{report_id}?experience=power-bi"
