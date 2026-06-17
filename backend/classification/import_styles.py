# -*- coding: utf-8 -*-
"""
Fusionne styles.csv dans final_dataset_ml.csv (catégorie Vêtements / Clothing).

Par défaut le libellé `produit` = productDisplayName (descriptions réalistes type facture).
articleType sert au filtrage et à l'échantillonnage stratifié (évite 30k lignes identiques).

Usage :
  python import_styles.py
  python import_styles.py --produit-column articleType
  python import_styles.py --max-total 2500 --max-per-type 80
"""

import argparse
from pathlib import Path

import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = MODEL_DIR / "styles.csv"
TARGET_CSV = MODEL_DIR / "final_dataset_ml.csv"
CATEGORY = "Vêtements / Clothing"

CLOTHING_MASTER_CATEGORIES = frozenset({"Apparel", "Footwear"})


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def load_styles_rows(
    csv_path: Path,
    produit_column: str = "productdisplayname",
    max_total: int = 2500,
    max_per_type: int = 80,
    random_state: int = 42,
) -> pd.DataFrame:
    df = _normalize_columns(pd.read_csv(csv_path, on_bad_lines="skip"))
    produit_col = produit_column.lower().replace(" ", "_")

    if produit_col not in df.columns:
        raise ValueError(
            f"Colonne '{produit_column}' introuvable dans {csv_path}. "
            f"Colonnes : {list(df.columns)}"
        )

    master_col = "mastercategory" if "mastercategory" in df.columns else None
    type_col = "articletype" if "articletype" in df.columns else None

    if master_col:
        df = df[df[master_col].astype(str).isin(CLOTHING_MASTER_CATEGORIES)]

    df[produit_col] = df[produit_col].astype(str).str.strip()
    df = df[df[produit_col].str.lower().isin(["", "nan"]) == False]

    if type_col and max_per_type > 0:
        sampled = []
        for _, group in df.groupby(type_col, sort=False):
            sampled.append(group.sample(n=min(len(group), max_per_type), random_state=random_state))
        df = pd.concat(sampled, ignore_index=True)

    if max_total > 0 and len(df) > max_total:
        df = df.sample(n=max_total, random_state=random_state)

    rows = [{"produit": str(row[produit_col]).strip(), "categorie": CATEGORY} for _, row in df.iterrows()]
    out = pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["produit"], keep="first")
    return out


def merge_into_dataset(styles_df: pd.DataFrame, target: Path) -> dict:
    if target.exists():
        base = pd.read_csv(target, sep=";")
    else:
        base = pd.DataFrame(columns=["produit", "categorie"])

    base["produit"] = base["produit"].astype(str).str.strip()
    base["categorie"] = base["categorie"].astype(str).str.strip()
    before = len(base)

    existing = set(base["produit"].str.lower())
    new_rows = styles_df[~styles_df["produit"].str.lower().isin(existing)]
    merged = pd.concat([base, new_rows], ignore_index=True)
    merged.to_csv(target, sep=";", index=False)

    return {
        "base_rows": before,
        "styles_rows": len(styles_df),
        "added": len(new_rows),
        "skipped_duplicates": len(styles_df) - len(new_rows),
        "total": len(merged),
        "category": CATEGORY,
    }


def main():
    parser = argparse.ArgumentParser(description="Importer styles.csv dans final_dataset_ml.csv")
    parser.add_argument("--input", "-i", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--produit-column",
        default="productDisplayName",
        help="Colonne libellé produit (productDisplayName recommandé, articleType = trop générique)",
    )
    parser.add_argument("--max-total", type=int, default=45, help="Max lignes importées (0 = illimité)")
    parser.add_argument("--max-per-type", type=int, default=15, help="Max lignes par articleType")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Fichier introuvable : {args.input}")
        print("Placer styles.csv dans backend/classification/")
        raise SystemExit(1)

    styles_df = load_styles_rows(
        args.input,
        produit_column=args.produit_column,
        max_total=args.max_total,
        max_per_type=args.max_per_type,
    )
    stats = merge_into_dataset(styles_df, TARGET_CSV)

    print(f"Source : {args.input}")
    print(f"Colonne libellé : {args.produit_column}")
    print(f"Catégorie : {stats['category']}")
    print(f"Lignes styles lues : {stats['styles_rows']}")
    print(f"Ajoutées : {stats['added']}")
    print(f"Doublons ignorés : {stats['skipped_duplicates']}")
    print(f"Total final_dataset_ml.csv : {stats['total']}")
    print()
    print("Prochaine étape : python train.py")


if __name__ == "__main__":
    main()
