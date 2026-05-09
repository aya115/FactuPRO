import pandas as pd
from pathlib import Path


def main():
  """
  Re-crée un dataset équilibré à partir de final_dataset_ml.csv :
  - Regroupe plusieurs catégories en 'Charges bancaires'
  - Réduit le nombre d'exemples des grosses catégories
  - Sauvegarde le résultat dans final_dataset_ml_balanced.csv
  """
  root = Path(__file__).resolve().parent
  src = root / "final_dataset_ml.csv"
  dst = root / "final_dataset_ml_balanced.csv"

  df = pd.read_csv(src, sep=";")

  # 1) Regrouper les catégories bancaires
  banking_mapping = {
    "Frais bancaires": "Charges bancaires",
    "Commissions": "Charges bancaires",
    "Fichiers bancaires": "Charges bancaires",
    "Frais de dossier": "Charges bancaires",
  }
  df["categorie"] = df["categorie"].replace(banking_mapping)

  # 2) Fusion Honoraires comptables + Prestations diverses
  df["categorie"] = df["categorie"].replace({
    "Honoraires comptables": "Honoraires et prestations",
    "Prestations diverses": "Honoraires et prestations",
  })

  # 3) Limiter la taille des grosses catégories
  caps = {
    "Office Supplies": 1000,
    "IT / Technology": 900,
    "Furniture": 900,
    "Livre / Book": 800,
  }

  groups = []
  for cat, group in df.groupby("categorie", sort=False):
    cap = caps.get(cat)
    if cap is not None and len(group) > cap:
      group = group.sample(n=cap, random_state=42)
    groups.append(group)

  balanced = pd.concat(groups, ignore_index=True)
  # Mélange global pour éviter un ordre par catégorie
  balanced = balanced.sample(frac=1.0, random_state=42).reset_index(drop=True)

  balanced.to_csv(dst, sep=";", index=False)

  print("=== Comptage original ===")
  print(df["categorie"].value_counts())
  print("\n=== Comptage équilibré (écrit dans final_dataset_ml_balanced.csv) ===")
  print(balanced["categorie"].value_counts())


if __name__ == "__main__":
  main()

