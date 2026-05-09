from datasets import load_dataset
from pathlib import Path
from PIL import Image
import json

OUT_DIR = Path("hf_invoice_dataset")
OUT_DIR.mkdir(exist_ok=True)

ds = load_dataset("GokulRajaR/invoice-ocr-json", split="train")
print(f"Nombre d'exemples : {len(ds)}")

N = 50  # ou plus
for i in range(min(N, len(ds))):
    sample = ds[i]

    # ICI : sample["file"] est déjà une image PIL
    img = sample["file"]
    if not isinstance(img, Image.Image):
        # fallback au cas où, mais normalement inutile
        img = Image.open(img).convert("RGB")

    data = sample["data"]  # chaîne JSON annotée

    # Sauvegarder l'image
    img_path = OUT_DIR / f"invoice_{i:04d}.png"
    img.save(img_path)

    # Sauvegarder le JSON de vérité terrain
    json_path = OUT_DIR / f"invoice_{i:04d}.json"
    try:
        gt = json.loads(data)
    except Exception:
        gt = {"raw": data}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(gt, f, indent=2, ensure_ascii=False)

print(f"Sauvegardé {min(N, len(ds))} exemples dans {OUT_DIR.resolve()}")