# -*- coding: utf-8 -*-
"""
Entraînement du modèle supervisé avec embeddings Transformer
Version améliorée (multilingual + embeddings normalisés)
"""

import sys
import numpy as np
import joblib
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, f1_score
from sentence_transformers import SentenceTransformer

MODEL_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = MODEL_DIR / "final_dataset_ml.csv"
MODEL_PATH = MODEL_DIR / "expense_classifier_transformer.joblib"

# 🔥 NOUVEAU MODELE MULTILINGUAL
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

MAX_MAJOR_CLASS = 500
MIN_MINOR_CLASS = 100
RARE_THRESHOLD = 30

FORBIDDEN_WORDS = [
    "dress","jeans","shirt","t-shirt","skirt",
    "lipstick","makeup","perfume","toy",
    "jewelry","cosmetic","fashion"
]


def clean_text(text):
    return str(text).lower().strip()


def filter_business_data(df):
    #Nettoie texte
    df["produit"] = df["produit"].astype(str)
    df = df[df['produit'].str.lower().apply(
        lambda x: not any(w in x for w in FORBIDDEN_WORDS)
    )]
    #Supprime lignes vides
    df = df.dropna(subset=['produit','categorie'])
    df = df.drop_duplicates()
    df = df[df['produit'].str.strip() != ""]
    df = df[df['categorie'].str.strip() != ""]
    return df


def map_rare_categories(df, category_col="categorie"):
    #Distribution des classes
    counts = df[category_col].value_counts()
    rare_cats = counts[counts < RARE_THRESHOLD].index.tolist()
    df[category_col] = df[category_col].apply(
        lambda x: "Other / Divers" if x in rare_cats else x
    )
    return df



def train(csv_path=None):
    csv_path = Path(csv_path or DEFAULT_DATA)

    df = pd.read_csv(csv_path, sep=";")

    # Nettoyage basique
    df = df.dropna(subset=['produit','categorie'])
    df['produit'] = df['produit'].astype(str).str.lower().str.strip()
    df['categorie'] = df['categorie'].astype(str).str.strip()

    # Supprimer ligne header parasite si existe
    df = df[df["categorie"].str.lower() != "categorie"]

    print("\nDistribution réelle :")
    print(df['categorie'].value_counts())

    X = df["produit"].tolist()
    y = df["categorie"].tolist()
#Charge MiniLM
    embedder = SentenceTransformer(EMBEDDING_MODEL)
#Transformer texte → vecteurs
    X_emb = embedder.encode(
        X,
        normalize_embeddings=True,
        show_progress_bar=True
    )
#Split train / test
    X_train, X_test, y_train, y_test = train_test_split(
        X_emb,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )
#Création modèle
    clf = LogisticRegression(
        #nombre maximum d’itérations pour optimiser le modèle
        max_iter=3000,
        class_weight="balanced",
        C=2.0#contrôle la force de la régularisation L2 (évite overfitting).
    )
#Entraînement de modele calcule w et b
    clf.fit(X_train, y_train)
#Prédiction test
    y_pred = clf.predict(X_test)

    print("\nAccuracy:", accuracy_score(y_test, y_pred))
    print("\nClassification report:")
    print(classification_report(y_test, y_pred))

if __name__ == "__main__":
    train()
