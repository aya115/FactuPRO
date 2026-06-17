# FactuPRO — Dashboard innovant Grafana (sans redondance Power BI)

**Rôle :** monitoring **technique temps réel** uniquement — ce que Power BI ne couvre pas.  
**Source :** `Prometheus`  
**URL :** http://localhost:3030/d/factupro-innovant  
**Analyse métier** (OCR, corrections, alertes, catégories, assistant IA) → **Power BI** `/analytics/bi`

**Période recommandée :** Last 7 days

---

## Panneaux conservés

### 1. Santé & disponibilité

| Panneau | Type | Requête PromQL |
|---------|------|----------------|
| Backend UP/DOWN | Stat | `up{job="factupro-backend"}` |
| Disponibilité 6 h (%) | Stat | `avg_over_time(up{job="factupro-backend"}[6h]) * 100` |
| Taux échec upload (live) | Gauge | `rate(factupro_upload_errors_total[5m]) / (rate(factupro_uploads_total[5m]) + rate(factupro_upload_errors_total[5m]) + 1e-9) * 100` |
| Timeline disponibilité | State timeline | `up{job="factupro-backend"}` |

### 2. Erreurs techniques upload

| Panneau | Type | Requête PromQL | Légende |
|---------|------|----------------|---------|
| Erreurs upload / min | Time series | `rate(factupro_upload_errors_total[5m]) * 60` | Erreurs / min |
| Uploads réussis / min | Time series | `rate(factupro_uploads_total[5m]) * 60` | Uploads / min |
| Taux d'échec upload (%) | Time series | `rate(factupro_upload_errors_total[5m]) / (rate(factupro_uploads_total[5m]) + rate(factupro_upload_errors_total[5m]) + 1e-9) * 100` | % échec |
| Répartition succès / erreurs | Pie chart | A: `increase(factupro_uploads_total[6h])` · B: `increase(factupro_upload_errors_total[6h])` | — |
| Volume période | Bar gauge | A: `increase(factupro_upload_errors_total[$__range])` · B: `increase(factupro_uploads_total[$__range])` | — |

### 3. Performance pipeline (session conteneur)

| Panneau | Type | Requête PromQL | Légende |
|---------|------|----------------|---------|
| Temps moyen / facture (s) | Time series | `factupro_avg_processing_seconds` | Moyenne (s) |
| Dérivée latence | Time series | `deriv(factupro_avg_processing_seconds[30m])` | Tendance 30 min |
| Factures traitées (session) | Time series | `factupro_invoices_processed_total` | Factures |
| Lignes traitées (session) | Time series | `factupro_invoice_lines_total` | Lignes |
| Temps cumulé pipeline | Time series | `factupro_processing_seconds_total` | Secondes |
| Heatmap activité uploads | Heatmap | `sum(increase(factupro_uploads_total[$__rate_interval]))` | — |

### 4. Anomalies ML (runtime)

| Panneau | Type | Requête PromQL | Légende |
|---------|------|----------------|---------|
| Anomalies session | Time series | `factupro_anomalies_total` | Cumul session |
| Taux anomalies % | Time series | `factupro_anomaly_rate_pct` | % session |

---

## Panneaux retirés (désormais dans Power BI)

| Ancien panneau Grafana | Équivalent Power BI |
|------------------------|---------------------|
| Précision OCR, score qualité, taux correction | Page OCR / vues `ocr_precision_details` |
| Alertes superviseur | PostgreSQL `supervisor_alerts` |
| Lignes non classées, % catégories | `fact_invoice_lines_star_bi`, `dim_category_bi` |
| Factures OCR évaluées | Vues factures / OCR |
| Tendances corrections comptable | `v_invoice_corrected_lines_bi`, confirmations |
| Indice confiance IA, corrections post-IA | Pages superviseur Power BI |
| Assistant IA (questions) | `fact_qa_questions_bi` (Page 5) |

---

## Alertes Grafana recommandées (PromQL)

```promql
# Backend down
up{job="factupro-backend"} == 0

# Pic d'erreurs upload
rate(factupro_upload_errors_total[5m]) > 0.01

# Latence pipeline élevée
factupro_avg_processing_seconds > 120
```

---

## Vérifier que Prometheus reçoit les métriques

```text
http://localhost:9090/graph
```

Test rapide :

```promql
factupro_uploads_total
up{job="factupro-backend"}
```

Si **No data** : vérifier http://localhost:9090/targets → `factupro-backend` = **UP**, puis uploader une facture.

---

## Redémarrer Grafana après modification

```bash
docker compose build grafana
docker compose up -d --force-recreate grafana
```
