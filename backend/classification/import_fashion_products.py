# -*- coding: utf-8 -*-
"""
Fusionne fashion_products.csv (Kaggle) dans final_dataset_ml.csv.

Source : https://www.kaggle.com/datasets/bhanupratapbiswas/fashion-products
Télécharger fashion_products.csv puis le placer dans backend/classification/

Usage :
  python -m classification.import_fashion_products
  python -m classification.import_fashion_products --input chemin/vers/fashion_products.csv
  python -m classification.import_fashion_products --with-brand   # "Nike Jeans" au lieu de "Jeans"
"""

import argparse
from pathlib import Path

import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = MODEL_DIR / "fashion_products.csv"
TARGET_CSV = MODEL_DIR / "final_dataset_ml.csv"
CATEGORY = "Vêtements / Clothing"


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def load_fashion_rows(csv_path: Path, with_brand: bool) -> pd.DataFrame:
    df = _normalize_columns(pd.read_csv(csv_path))
    name_col = "product_name" if "product_name" in df.columns else None
    if name_col is None:
        raise ValueError(
            f"Colonne 'Product Name' introuvable dans {csv_path}. "
            f"Colonnes : {list(df.columns)}"
        )

    brand_col = "brand" if "brand" in df.columns else None

    rows = []
    for _, row in df.iterrows():
        name = str(row.get(name_col, "")).strip()
        if not name or name.lower() in ("nan", "product_name", "product name"):
            continue
        if with_brand and brand_col:
            brand = str(row.get(brand_col, "")).strip()
            if brand and brand.lower() != "nan":
                produit = f"{brand} {name}".strip()
            else:
                produit = name
        else:
            produit = name
        rows.append({"produit": produit, "categorie": CATEGORY})

    out = pd.DataFrame(rows)
    out["produit"] = out["produit"].astype(str).str.strip()
    out = out[out["produit"] != ""].drop_duplicates(subset=["produit"], keep="first")
    return out


def merge_into_dataset(fashion_df: pd.DataFrame, target: Path) -> dict:
    if target.exists():
        base = pd.read_csv(target, sep=";")
    else:
        base = pd.DataFrame(columns=["produit", "categorie"])

    base["produit"] = base["produit"].astype(str).str.strip()
    base["categorie"] = base["categorie"].astype(str).str.strip()
    before = len(base)

    existing = set(base["produit"].str.lower())
    new_rows = fashion_df[~fashion_df["produit"].str.lower().isin(existing)]
    merged = pd.concat([base, new_rows], ignore_index=True)
    merged.to_csv(target, sep=";", index=False)

    return {
        "base_rows": before,
        "fashion_rows": len(fashion_df),
        "added": len(new_rows),
        "skipped_duplicates": len(fashion_df) - len(new_rows),
        "total": len(merged),
        "category": CATEGORY,
    }


def main():
    parser = argparse.ArgumentParser(description="Importer fashion_products.csv dans final_dataset_ml.csv")
    parser.add_argument("--input", "-i", type=Path, default=DEFAULT_INPUT, help="Chemin vers fashion_products.csv")
    parser.add_argument(
        "--with-brand",
        action="store_true",
        help="Préfixer avec la marque (ex. Nike Jeans) — recommandé pour de meilleures prédictions",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Fichier introuvable : {args.input}")
        print()
        print("Étapes :")
        print("  1. Télécharger sur https://www.kaggle.com/datasets/bhanupratapbiswas/fashion-products")
        print("  2. Placer fashion_products.csv dans backend/classification/")
        print("  3. Relancer : python -m classification.import_fashion_products")
        raise SystemExit(1)

    fashion_df = load_fashion_rows(args.input, with_brand=args.with_brand)
    stats = merge_into_dataset(fashion_df, TARGET_CSV)

    print(f"Source : {args.input}")
    print(f"Catégorie assignée : {stats['category']}")
    print(f"Lignes mode lues : {stats['fashion_rows']}")
    print(f"Ajoutées : {stats['added']}")
    print(f"Doublons ignorés : {stats['skipped_duplicates']}")
    print(f"Total final_dataset_ml.csv : {stats['total']} lignes")
    print()
    print("Prochaine étape : python -m classification.train")
    print("Puis : docker compose restart backend")


if __name__ == "__main__":
    main()
