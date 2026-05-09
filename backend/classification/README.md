# Classification supervisée des charges

Ce module utilise un modèle **Random Forest** entraîné sur TF-IDF pour classifier automatiquement les descriptions d'articles de facture en catégories comptables.

## Entraînement du modèle

### 1. Installer les dépendances

```bash
cd backend
pip install scikit-learn joblib
```

### 2. Préparer les données

Le fichier `training_data.csv` contient des exemples labellisés :

```csv
description,category
"Ordinateur portable","Équipement informatique"
"Licence Microsoft Office","Logiciels"
"Essence trajet","Transport"
...
```

**Ajoutez vos propres exemples** pour améliorer le modèle. Plus il y a de données par catégorie, meilleure sera la prédiction.

### 3. Lancer l'entraînement

```bash
cd backend
python -m classification.train
```

Ou avec un fichier CSV personnalisé :

```bash
python -m classification.train mon_fichier.csv
```

Le modèle sera sauvegardé dans `classification/expense_classifier.joblib`.

## Intégration

Une fois le modèle entraîné, le pipeline utilise **automatiquement** le classifieur supervisé au lieu de l'IA Groq pour la classification. Si aucun modèle n'est trouvé, le système revient sur la classification par IA.

## Catégories par défaut

- Fournitures de bureau
- Logiciels
- Transport
- Maintenance
- Équipement informatique
- Services professionnels
- Communication
- Formation
- Autres
