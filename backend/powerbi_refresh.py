# -*- coding: utf-8 -*-
"""
Déclenche l'actualisation du dataset Power BI via l'API REST (après facture / correction).

Configuration (.env) :
  POWERBI_AUTO_REFRESH=1
  POWERBI_TENANT_ID=...
  POWERBI_CLIENT_ID=...
  POWERBI_CLIENT_SECRET=...
  POWERBI_DATASET_ID=cc93fdbe-f8ab-48bd-b9b1-bc701f34c4ca
  POWERBI_WORKSPACE_ID=          # optionnel ; workspace (pas « Mon espace » perso)
  POWERBI_REFRESH_MIN_INTERVAL_SEC=30
"""

from __future__ import annotations

import os
import threading
import time

import httpx

_lock = threading.Lock()
_pending_timer: threading.Timer | None = None
_last_refresh_at = 0.0
_token_cache: dict = {"access_token": None, "expires_at": 0.0}


def _cfg(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def is_powerbi_refresh_enabled() -> bool:
    if _cfg("POWERBI_AUTO_REFRESH", "0").lower() not in ("1", "true", "yes", "on"):
        return False
    return bool(
        _cfg("POWERBI_TENANT_ID")
        and _cfg("POWERBI_CLIENT_ID")
        and _cfg("POWERBI_CLIENT_SECRET")
        and _cfg("POWERBI_DATASET_ID")
    )


def _min_interval_sec() -> float:
    try:
        return max(5.0, float(_cfg("POWERBI_REFRESH_MIN_INTERVAL_SEC", "30")))
    except ValueError:
        return 30.0


def _get_access_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    tenant = _cfg("POWERBI_TENANT_ID")
    client_id = _cfg("POWERBI_CLIENT_ID")
    client_secret = _cfg("POWERBI_CLIENT_SECRET")

    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://analysis.windows.net/powerbi/api/.default",
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, data=data)
        resp.raise_for_status()
        payload = resp.json()

    token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))
    _token_cache["access_token"] = token
    _token_cache["expires_at"] = now + expires_in
    return token


def _trigger_refresh_now(reason: str = "") -> dict:
    global _last_refresh_at

    dataset_id = _cfg("POWERBI_DATASET_ID")
    workspace_id = _cfg("POWERBI_WORKSPACE_ID")
    token = _get_access_token()

    if workspace_id:
        url = (
            f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}"
            f"/datasets/{dataset_id}/refreshes"
        )
    else:
        url = f"https://api.powerbi.com/v1.0/myorg/datasets/{dataset_id}/refreshes"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, headers=headers, json={})

    _last_refresh_at = time.time()

    if resp.status_code in (200, 202):
        print(f"✅ Power BI refresh déclenché ({reason or 'facture'})", flush=True)
        return {"ok": True, "status": resp.status_code}

    if resp.status_code == 409:
        print(f"ℹ️ Power BI refresh déjà en cours ({reason})", flush=True)
        return {"ok": True, "status": 409, "already_running": True}

    detail = resp.text[:500]
    print(f"⚠️ Power BI refresh échoué ({resp.status_code}): {detail}", flush=True)
    return {"ok": False, "status": resp.status_code, "detail": detail}


def _run_scheduled_refresh(reason: str) -> None:
    global _pending_timer
    with _lock:
        _pending_timer = None
    try:
        _trigger_refresh_now(reason)
    except Exception as e:
        print(f"⚠️ Power BI refresh: {e}", flush=True)


def schedule_powerbi_refresh(reason: str = "invoice_change") -> bool:
    """
    Planifie un refresh (debounce) pour ne pas spammer l'API si plusieurs lignes changent.
    Retourne False si la fonctionnalité est désactivée.
    """
    if not is_powerbi_refresh_enabled():
        return False

    global _pending_timer
    delay = _min_interval_sec()

    def _fire():
        _run_scheduled_refresh(reason)

    with _lock:
        if _pending_timer is not None:
            _pending_timer.cancel()
        _pending_timer = threading.Timer(delay, _fire)
        _pending_timer.daemon = True
        _pending_timer.start()

    print(f"🔄 Power BI refresh planifié dans {int(delay)}s ({reason})", flush=True)
    return True
