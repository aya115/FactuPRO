# -*- coding: utf-8 -*-
"""
Enrichit la categorie Logiciels / Licences dans final_dataset_ml.csv
avec des noms du Comptoir du Libre (diversite, sans doublons).

- Conserve les exemples metier distincts deja presents
- Remplace uniquement les libelles generiques / repetitifs (WinAuditor x N, SaaS, Cloud…)
- Garde le meme nombre total d'exemples Logiciels / Licences
- Ne modifie aucune autre categorie

Usage :
  python import_comptoir_logiciels.py
  python import_comptoir_logiciels.py --dry-run
"""

import argparse
import re
from pathlib import Path

import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent
DEFAULT_COMPTOIR = MODEL_DIR / "comptoir-du-libre.org-2026.04.21-logiciels-libres-v1.csv"
TARGET_CSV = MODEL_DIR / "final_dataset_ml.csv"
CATEGORY = "Logiciels / Licences"

# Libelles trop generiques ou deja couverts par un autre exemple proche
REPLACE_EXACT = {
    "abonnement logiciel",
    "logiciel de gestion",
    "saas",
    "cloud",
    "hebergement",
    "hébergement",
    "h\u251c\u00aebergement",
    "h├®bergement",
    "acces winauditor",
    "accès winauditor",
    "acc\u251c\u00aes winauditor",
    "acc├¿s winauditor",
    "licence winauditor",
    "logiciel winauditor",
}

# Corriger l'encodage casse sur les lignes conservees
ENCODING_FIXES = {
    "comptabilit\u251c\u00ae": "comptabilité",
    "comptabilit├®": "comptabilité",
    "mise \u251c\u00a0 jour logiciel": "mise à jour logiciel",
    "mise ├á jour logiciel": "mise à jour logiciel",
    "perp\u251c\u00aetuelle": "perpétuelle",
    "perp├®tuelle": "perpétuelle",
    "acces winauditor": "accès winauditor",
    "acc\u251c\u00aes winauditor": "accès winauditor",
    "acc├¿s winauditor": "accès winauditor",
    "h\u251c\u00aebergement": "hébergement",
    "h├®bergement": "hébergement",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower().strip())


def _fix_encoding(text: str) -> str:
    out = str(text)
    for bad, good in ENCODING_FIXES.items():
        out = out.replace(bad, good)
    return out.strip()


def load_comptoir_software(csv_path: Path) -> list[str]:
    df = pd.read_csv(csv_path, sep=";", encoding="utf-8", on_bad_lines="skip")
    if "software" not in df.columns:
        raise ValueError(f"Colonne 'software' absente dans {csv_path}")

    names = []
    seen = set()
    for raw in df["software"].astype(str):
        name = raw.strip().strip('"')
        if not name or name.lower() == "nan":
            continue
        key = _norm(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _invoice_label(software: str, idx: int) -> str:
    templates = [
        "Licence {name}",
        "Abonnement annuel {name}",
        "Renouvellement licence {name}",
        "Maintenance et support {name}",
    ]
    return templates[idx % len(templates)].format(name=software)


def enrich_logiciels(
    target: Path,
    comptoir_path: Path,
    dry_run: bool = False,
    random_state: int = 42,
) -> dict:
    df = pd.read_csv(target, sep=";")
    comptoir_names = load_comptoir_software(comptoir_path)

    mask = df["categorie"].astype(str).str.strip() == CATEGORY
    logiciels_idx = df.index[mask].tolist()
    target_count = len(logiciels_idx)

    existing_all = {_norm(p) for p in df["produit"].astype(str)}

    to_replace_idx = []
    kept = []
    for idx in logiciels_idx:
        produit = _fix_encoding(df.at[idx, "produit"])
        df.at[idx, "produit"] = produit
        key = _norm(produit)
        if key in REPLACE_EXACT:
            to_replace_idx.append(idx)
        else:
            kept.append(produit)

    comptoir_pool = comptoir_names.copy()
    pd.Series(comptoir_pool).sample(frac=1.0, random_state=random_state).tolist()

    new_labels = []
    ci = 0
    for i, idx in enumerate(to_replace_idx):
        while ci < len(comptoir_pool):
            label = _invoice_label(comptoir_pool[ci], i)
            ci += 1
            if _norm(label) not in existing_all:
                existing_all.add(_norm(label))
                new_labels.append(label)
                df.at[idx, "produit"] = label
                break
        else:
            raise RuntimeError("Pas assez de logiciels Comptoir du Libre uniques")

    if not dry_run:
        df.to_csv(target, sep=";", index=False, encoding="utf-8-sig")

    return {
        "logiciels_total": target_count,
        "kept": len(kept),
        "replaced": len(to_replace_idx),
        "kept_examples": kept,
        "new_examples": new_labels,
    }


def main():
    parser = argparse.ArgumentParser(description="Diversifier Logiciels / Licences via Comptoir du Libre")
    parser.add_argument("--input-comptoir", type=Path, default=DEFAULT_COMPTOIR)
    parser.add_argument("--target", type=Path, default=TARGET_CSV)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.input_comptoir.exists():
        print(f"Fichier introuvable : {args.input_comptoir}")
        raise SystemExit(1)
    if not args.target.exists():
        print(f"Fichier introuvable : {args.target}")
        raise SystemExit(1)

    stats = enrich_logiciels(args.target, args.input_comptoir, dry_run=args.dry_run)
    print(f"Logiciels / Licences : {stats['logiciels_total']} exemples (inchange)")
    print(f"Conserves : {stats['kept']}")
    print(f"Remplaces (generiques/repetitifs) : {stats['replaced']}")
    print("\nConserves :")
    for p in stats["kept_examples"]:
        print(f"  - {p}")
    print("\nNouveaux libelles :")
    for p in stats["new_examples"]:
        print(f"  - {p}")
    if args.dry_run:
        print("\n(dry-run : fichier non modifie)")
    else:
        print("\nEcrit dans", str(args.target))
        print("Prochaine etape : python train.py")


if __name__ == "__main__":
    main()
