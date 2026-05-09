# -*- coding: utf-8 -*-
"""
Retire le fond blanc d'un logo PNG : les pixels très clairs et peu saturés
(blanc / gris papier) passent en transparent ; les couleurs du logo sont conservées.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def process(path: Path) -> None:
    img = Image.open(path).convert("RGBA")
    d = np.asarray(img, dtype=np.float32)
    r, g, b, a = d[:, :, 0], d[:, :, 1], d[:, :, 2], d[:, :, 3]

    chroma = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
    luma = (r + g + b) / 3.0

    # "Blancheur" du pixel : haute si luma élevée ET faible chroma (fond papier)
    w_luma = np.clip((luma - 195) / 60.0, 0.0, 1.0)
    w_chroma = 1.0 - np.clip(chroma / 42.0, 0.0, 1.0)
    whiteness = w_luma * w_chroma

    mult = 1.0 - whiteness
    new_a = np.clip(a * mult, 0, 255)

    d[:, :, 3] = new_a.astype(np.uint8)
    Image.fromarray(d.astype(np.uint8), "RGBA").save(path, optimize=True)
    print(f"OK: {path}")


if __name__ == "__main__":
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "frontend" / "public" / "factupro-logo.png"
    process(p)
