# -*- coding: utf-8 -*-
import json
import os
import re
from pathlib import Path

# ================= CONFIG (chargée depuis JSON, surcharge possible via env) =================
_CONFIG_PATH = Path(__file__).resolve().parent / "data" / "pcg_imputation_config.json"
_ENV_CONFIG = os.environ.get("PCG_IMPUTATION_CONFIG")


def _load_imputation_config():
    """Charge le mapping catégorie → comptes PCG depuis un fichier JSON."""
    path = Path(_ENV_CONFIG) if _ENV_CONFIG else _CONFIG_PATH
    fallback = {
        "default_account": None,
        "asset_min_amount": 500,
        "category_aliases": {},
        "category_rules": {
            "IT / Technology": {"expense": "606300", "asset": "218300"},
            "Furniture": {"expense": "606300", "asset": "218400"},
            "Office Supplies": {"expense": "606400"},
        },
    }
    try:
        if path.is_file():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data.get("category_rules"), dict):
                return {
                    "default_account": data.get("default_account"),
                    "asset_min_amount": int(data.get("asset_min_amount", 500)),
                    "category_aliases": data.get("category_aliases") or {},
                    "category_rules": data["category_rules"],
                }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return fallback


_CFG = _load_imputation_config()
DEFAULT_ACCOUNT = _CFG["default_account"]
ASSET_MIN_AMOUNT = _CFG["asset_min_amount"]
CATEGORY_RULES = _CFG["category_rules"]
_CATEGORY_ALIASES = _CFG["category_aliases"]


def resolve_category_key(category):
    """Libellé exact du classifieur, sinon alias, sinon tel quel."""
    if not category:
        return None
    c = str(category).strip()
    if c in CATEGORY_RULES:
        return c
    return _CATEGORY_ALIASES.get(c, c)


# ================= UTILS =================
def normalize_account(val):
    """Normalise un compte pour qu'il soit à 6 chiffres."""
    if not val:
        return None
    s = re.sub(r"\s+", "", str(val))
    return s if re.fullmatch(r"\d{6}", s) else None


def get_existing_account(item):
    """Renvoie un compte existant si déjà présent dans l'item."""
    for k in ["account", "account_proposed", "compte"]:
        acc = normalize_account(item.get(k))
        if acc:
            return acc
    return None


def get_amount(item):
    """Récupère le montant de l'item."""
    for key in ["net", "amount", "gross"]:
        val = item.get(key)
        if val:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None


# ================= ASSET DETECTION =================
def detect_asset(amount, rules):
    """
    Détecte si un item doit être considéré comme un actif.
    Basé uniquement sur la présence d'une règle 'asset' et le montant.
    """
    if not rules or "asset" not in rules:
        return False
    return amount is not None and amount >= ASSET_MIN_AMOUNT


# ================= ACCOUNT PROPOSAL =================
def propose_account(category, amount):
    """Propose un compte comptable basé sur la catégorie et le montant."""
    key = resolve_category_key(category)
    if not key:
        return DEFAULT_ACCOUNT
    rules = CATEGORY_RULES.get(key)
    if not rules:
        return DEFAULT_ACCOUNT
    if detect_asset(amount, rules):
        return rules["asset"]
    return rules.get("expense", DEFAULT_ACCOUNT)


# ================= PIPELINE PRINCIPAL =================
def add_account_to_items(items):
    results = []
    for item in items:
        amount = get_amount(item)

        # 1️⃣ garder l'existant si présent
        existing = get_existing_account(item)
        if existing:
            new = item.copy()
            new["account_proposed"] = existing
            new["source"] = "preserved"
            results.append(new)
            continue

        # 2️⃣ lire directement la catégorie existante
        category = item.get("category") or "Non classé"

        # 3️⃣ proposer le compte
        account = propose_account(category, amount)

        # 4️⃣ sauvegarder résultat
        new = item.copy()
        new["account_proposed"] = account
        new["source"] = "category_based"
        results.append(new)

    return results


# ================= TEST =================
if __name__ == "__main__":
    items = [
        {"description": "Clavier sans fil Logitech", "amount": 45, "category": "IT / Technology"},
        {"description": "Dell PowerEdge Server R740", "amount": 3500, "category": "IT / Technology"},
        {"description": "Papier A4", "amount": 10, "category": "Office Supplies"},
        {"description": "Chaise bureau ergonomique", "amount": 600, "category": "Furniture"},
        {"description": "Achat Amazon", "amount": 120, "category": None},
        {"description": "Abonnement SaaS", "amount": 99, "category": "Logiciels / Licences"},
        {"description": "Inconnu", "amount": 50, "category": "Non classé"},
    ]

    out = add_account_to_items(items)
    for x in out:
        print(x)
