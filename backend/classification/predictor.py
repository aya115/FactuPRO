# -*- coding: utf-8 -*-

import os
import re
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from sentence_transformers import SentenceTransformer

MODEL_DIR = Path(__file__).resolve().parent
MODEL_PATH = MODEL_DIR / "expense_classifier_transformer.joblib"
CSV_BASE_PATH = MODEL_DIR / "final_dataset_ml.csv"

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_CATEGORY = "Non classé"

SIMILARITY_THRESHOLD = 0.48
TOP_K = 5

# Si le classifieur sklearn est peu confiant (max proba bas), on retente via le plus proche voisin
# sur les embeddings de référence (_X_ref) — souvent plus proche du CSV / des exemples courts.
HYBRID_SUPERVISED_MIN_CONF = float(os.environ.get("CLASSIFICATION_SUPERVISED_MIN_CONF", "0.45"))
HYBRID_NN_MARGIN = float(os.environ.get("CLASSIFICATION_HYBRID_NN_MARGIN", "0.03"))

# Libellés équivalents pour l’imputation PCG (clé = normalisée lower strip)
OUTPUT_CATEGORY_ALIASES = {
    "frais bancaires": "Charges bancaires",
    "frais bankaires": "Charges bancaires",
}


# =============================
# TEXT CLEANER
# =============================

def clean_description(text):
    if not text:
        return ""
    text = str(text).lower().strip()
    text = re.sub(r'\s+', ' ', text)
    return text[:500]


def _canonical_category_label(name):
    if not name:
        return name
    key = str(name).strip().lower()
    return OUTPUT_CATEGORY_ALIASES.get(key, str(name).strip())


# =============================
# CLASSIFIER CORE (NO RAG, NO LLM)
# =============================

class ExpenseClassifier:

    def __init__(self, model_path=None):

        self.model_path = Path(model_path or MODEL_PATH)

        self.pipeline = None
        self.embedder = None

        self._X_ref = None
        self._y_ref = None
        self._ref_descriptions = None
        self._load()

    # -------------------------

    def _load(self):

        try:

            # Load pretrained pipeline
            if self.model_path.exists():

                self.pipeline = joblib.load(self.model_path)

                model_name = self.pipeline.get(
                    "embedding_model_name",
                    EMBEDDING_MODEL
                )

                self.embedder = SentenceTransformer(model_name)

                self._X_ref = self.pipeline.get("X_ref")
                self._y_ref = self.pipeline.get("y_ref")
                self._ref_descriptions = self.pipeline.get("ref_descriptions")

                if self._X_ref is not None and self._y_ref is not None:

                    self._X_ref = np.asarray(self._X_ref)
                    self._y_ref = np.asarray(self._y_ref)

                    if self._ref_descriptions is None:
                        self._ref_descriptions = [""] * len(self._y_ref)

                    print("✅ Vectorized classifier loaded")
                    return

            # CSV fallback dataset

            if CSV_BASE_PATH.exists():

                df = pd.read_csv(CSV_BASE_PATH, sep=";")

                df = df.dropna(subset=["produit", "categorie"])

                df["produit"] = df["produit"].astype(str).apply(clean_description)

                df = df[df["produit"].str.strip() != ""]

                X = df["produit"].tolist()
                y = df["categorie"].astype(str).tolist()

                if not X:
                    raise ValueError("CSV base vide")

                if self.embedder is None:
                    #Quand tu fais SentenceTransformer(EMBEDDING_MODEL), le package va télécharger automatiquement le modèle depuis Hugging Face si ce n’est pas déjà sur ton disque.
#Ensuite, il est stocké dans le cache local (par défaut ~/.cache/torch/sentence_transformers) pour ne pas le retélécharger à chaque fois.
                    self.embedder = SentenceTransformer(EMBEDDING_MODEL)

                self._X_ref = self.embedder.encode(
                    X,
                    normalize_embeddings=True,
                    show_progress_bar=False
                )

                self._y_ref = np.array(y)
                self._ref_descriptions = X

                print("✅ CSV vectorized classifier loaded")

        except Exception as e:
            print("⚠️ Loading classifier error:", e)

    # -------------------------

    @property
    def is_available(self):
        return self.embedder is not None and self._X_ref is not None

    # =============================
    # Prediction Engine (PURE SEMANTIC MATCHING)
    # =============================

    def predict(self, descriptions):
#Prend une liste de descriptions (ex : ["Achat toner HP"]).
        if not descriptions or not self.is_available:
            return []

        texts = [clean_description(d) for d in descriptions]

        # 🔥 Embeddings
        X_emb = self.embedder.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        clf = None
        if isinstance(self.pipeline, dict):
            clf = self.pipeline.get("classifier")

        preds = []

        if clf is not None:
            y_pred = clf.predict(X_emb)
            y_proba = clf.predict_proba(X_emb)
            X_ref_nn = (
                np.asarray(self._X_ref, dtype=np.float32)
                if self._X_ref is not None and len(np.asarray(self._X_ref).shape) == 2
                else None
            )
            y_ref_nn = np.asarray(self._y_ref) if self._y_ref is not None else None

            for i, original_desc in enumerate(descriptions):
                predicted_category = str(y_pred[i])
                confidence = float(np.max(y_proba[i]))
                source = "supervised_transformer"

                # Rerank hybride : sklearn hésitant → voisin le plus proche dans la base de référence
                if (
                    X_ref_nn is not None
                    and y_ref_nn is not None
                    and X_ref_nn.size > 0
                    and confidence < HYBRID_SUPERVISED_MIN_CONF
                ):
                    sims_row = (X_emb[i : i + 1] @ X_ref_nn.T).ravel()
                    j_nn = int(np.argmax(sims_row))
                    nn_sim = float(sims_row[j_nn])
                    nn_cat = str(y_ref_nn[j_nn])
                    if nn_sim > confidence + HYBRID_NN_MARGIN or (
                        nn_sim >= SIMILARITY_THRESHOLD - 0.05 and nn_sim > confidence
                    ):
                        predicted_category = nn_cat
                        confidence = nn_sim
                        source = "hybrid_embedding_rerank"

                predicted_category = _canonical_category_label(predicted_category)

                preds.append({
                    "description": original_desc,
                    "category": predicted_category,
                    "classification_source": source,
                    "confidence": round(confidence, 4),
                    "precision_score": round(confidence, 4),
                })

            return preds

        # CSV / référence vectorielle sans joblib classifier : plus proche voisin (cosinus = produit scalaire si normalisé)
        X_ref = np.asarray(self._X_ref, dtype=np.float32)
        y_ref = np.asarray(self._y_ref)
        sims = X_emb @ X_ref.T

        for i, original_desc in enumerate(descriptions):
            row = sims[i]
            j = int(np.argmax(row))
            score = float(row[j])
            if score < SIMILARITY_THRESHOLD:
                predicted_category = DEFAULT_CATEGORY
                source = "embedding_nn_below_threshold"
            else:
                predicted_category = str(y_ref[j])
                source = "embedding_nn"

            predicted_category = _canonical_category_label(predicted_category)

            preds.append({
                "description": original_desc,
                "category": predicted_category,
                "classification_source": source,
                "confidence": round(score, 4),
                "precision_score": round(score, 4),
                "similarity_score": round(score, 4),
            })

        return preds

    # =============================

    def classify_items(self, items):

        if not items:
            return {"items": []}

        descriptions = [it.get("description", "") for it in items]

        return {
            "items": self.predict(descriptions)
        }