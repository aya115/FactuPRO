# -*- coding: utf-8 -*-
"""
Limite uniquement Vêtements et Livre dans final_dataset_ml.csv.

Usage :
  python rebalance_dataset.py --in-place
"""

import argparse
import pandas as pd
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent
SRC = MODEL_DIR / "final_dataset_ml.csv"
DST = MODEL_DIR / "final_dataset_ml_balanced.csv"

# Seuls ces plafonds sont appliques — les autres categories ne sont jamais modifiees
CATEGORY_CAPS = {
    "Livre / Book": 50,
    "Vêtements / Clothing": 45,
}


def apply_caps(df: pd.DataFrame, caps: dict, random_state: int = 42) -> pd.DataFrame:
    groups = []
    for cat, group in df.groupby("categorie", sort=False):
        cap = caps.get(cat)
        if cap is not None and len(group) > cap:
            group = group.sample(n=cap, random_state=random_state)
        groups.append(group)
    out = pd.concat(groups, ignore_index=True)
    return out.sample(frac=1.0, random_state=random_state).reset_index(drop=True)


def rebalance(src: Path = SRC, dst: Path = DST, caps: dict = None, random_state: int = 42):
    caps = caps or CATEGORY_CAPS
    df = pd.read_csv(src, sep=";")
    balanced = apply_caps(df, caps, random_state=random_state)
    balanced.to_csv(dst, sep=";", index=False)
    return df, balanced


def main():
    parser = argparse.ArgumentParser(description="Limiter Vêtements (45) et Livre (50) uniquement")
    parser.add_argument("--input", type=Path, default=SRC)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true")
    args = parser.parse_args()

    out = args.input if args.in_place else (args.output or DST)
    before, after = rebalance(args.input, out)

    print("=== Avant ===")
    print(before["categorie"].value_counts())
    print(f"\n=== Apres ({out}) ===")
    print(after["categorie"].value_counts())
    print(f"\nLignes : {len(before)} -> {len(after)}")


if __name__ == "__main__":
    main()
