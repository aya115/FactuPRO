# Métriques du pipeline Factures IA

## Détection d'anomalies

| Élément | Valeur |
|---------|--------|
| **Algorithme** | Règles métiers (rule-based), pas de ML |
| **Variables surveillées** | `quantity`, `net_price`, `net`, `gross`, `vat_percentage` (lignes) ; `totals.net`, `totals.vat`, `totals.gross` (facture) |
| **Seuil** | `TOLERANCE_PCT = 1.0` % (écart relatif max accepté pour les montants) |
| **Taux de TVA valides (France)** | 5 %, 10 %, 20 %, 2.1 %, 0 % |

Source : `backend/anomaly_detection.py` – fonction `get_anomaly_config()`.

---

## Métriques exposées

| Métrique | Description | Source |
|----------|-------------|--------|
| **Précision OCR (%)** | Taux de succès d’extraction structurée (factures avec au moins 1 item parsé) | Compteurs runtime |
| **Accuracy classification** | Accuracy du classifieur sur le test set | `classification/metrics.json` (sauvegardé par `train.py`) |
| **F1-score (weighted)** | F1 macro/weighted du classifieur | Idem |
| **Temps moyen de traitement (s)** | Temps total / nombre de factures traitées | Compteurs runtime |
| **Taux d’erreur résiduel (%)** | Nombre d’anomalies / nombre total de lignes × 100 | Compteurs runtime |

---

## API

- **GET /metrics** (authentifié) : retourne toutes les métriques.
- Override OCR : `GET /metrics?ocr_precision=95.5` (si évaluation externe).

---

## Fichiers

- `backend/anomaly_detection.py` : config détection + `get_anomaly_config()`
- `backend/metrics.py` : agrégation et exposition
- `backend/classification/train.py` : sauvegarde accuracy + F1 dans `metrics.json`
- `backend/runtime_metrics.json` : compteurs cumulés (créé au premier traitement)
