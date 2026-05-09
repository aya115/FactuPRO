# -*- coding: utf-8 -*-
import csv
from pathlib import Path

CSV_PATH = Path(__file__).parent / "final_dataset_ml.csv"

with open(CSV_PATH, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=';')
    print("Colonnes trouvées :", reader.fieldnames)
    for row in reader:
        print("Première ligne :", row)
        break
