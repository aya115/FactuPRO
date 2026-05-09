# -*- coding: utf-8 -*-
import pandas as pd
import glob
import ast
import os
import csv

csv.field_size_limit(10_000_000)

INPUT_FOLDER = "C:/data_pfe"
OUTPUT_FOLDER = "C:/data_pfe/clean"
FINAL_FILE = "C:/data_pfe/final_dataset_ml.csv"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

possible_columns = {
    'produit': ['product_name','title','product_title','name','product','Product.Name','Product_Name','produit'],
    'categorie': ['category','category_name','categories',
                  'potential_product_categories','Industry',
                  'root_category','breadcrumb','category_tree','categorie']
}

# On ne filtre plus les catégories interdites
FORBIDDEN_WORDS = [
    "dress","jeans","shirt","t-shirt","skirt",
    "lipstick","makeup","perfume","toy",
    "jewelry","cosmetic","fashion"
]

CATEGORY_MAPPING = {
    "office supplies": "Office Supplies",
    "technology": "IT / Technology",
    "software": "Software / SaaS",
    "enterprise software": "Software / SaaS",
    "furniture": "Furniture"
}

def clean_category(x):
    if pd.isna(x):
        return None

    if isinstance(x, str) and x.startswith("["):
        try:
            x = ast.literal_eval(x)
        except:
            pass

    if isinstance(x, list):
        if len(x) == 0:
            return None
        x = x[-1]

    if isinstance(x, str) and ">" in x:
        x = x.split(">")[-1]

    x = str(x).strip().lower()
    if x in ["", "none", "nan", "[]"]:
        return None

    return CATEGORY_MAPPING.get(x, x.title())

def is_business_product(desc):
    """Supprime uniquement les mots vraiment non B2B (mode, cosmétique, jouets, etc.)"""
    desc = desc.lower()
    return not any(w in desc for w in FORBIDDEN_WORDS)

# ===== lecture robuste multi-encodage =====
def read_csv_safe(path):
    for enc in ["utf-8", "latin-1", "cp1252"]:
        for sep in [";", ",", "\t"]:
            try:
                return pd.read_csv(path, encoding=enc, sep=sep, engine="python")
            except:
                pass
    raise ValueError(f"❌ Impossible de lire {path}")

# ================= PIPELINE =================

all_clean = []
csv_files = glob.glob(os.path.join(INPUT_FOLDER, "*.csv"))

for i, file in enumerate(csv_files, 1):
    print(f"[{i}/{len(csv_files)}] {file}")

    try:
        df = read_csv_safe(file)
    except Exception as e:
        print("   → ERREUR lecture :", e)
        continue

    rename_dict = {}
    for std, possibles in possible_columns.items():
        for col in df.columns:
            if col.lower().strip() in [p.lower() for p in possibles]:
                rename_dict[col] = std
                break

    df = df.rename(columns=rename_dict)

    if 'produit' not in df.columns or 'categorie' not in df.columns:
        print("   → ignoré (colonnes manquantes)")
        continue

    df = df[['produit','categorie']]
    df['categorie'] = df['categorie'].apply(clean_category)

    # On ne supprime plus les catégories interdites
    # df = df[~df['categorie'].isin(FORBIDDEN_CATEGORIES)]
    df = df[df['produit'].apply(is_business_product)]  # on peut garder pour exclure mode/cosmetic/toy

    df = df.dropna()
    df = df.drop_duplicates()
    df = df[df['produit'].str.strip() != ""]
    df = df[df['categorie'].str.strip() != ""]

    all_clean.append(df)

final_df = pd.concat(all_clean, ignore_index=True)
final_df.to_csv(FINAL_FILE, index=False, sep=";", encoding="utf-8")

print("\n===================================")
print("🔥 DATASET FINAL B2B GÉNÉRÉ (tous produits inclus)")
print("Fichier :", FINAL_FILE)
print("Lignes :", len(final_df))
print("Répartition :")
print(final_df['categorie'].value_counts(normalize=True))
print("===================================")
