# Monitoring FactuPRO — Grafana & Prometheus

## Power BI vs Grafana (complémentaires, sans redondance)

| Outil | Rôle | Source de données |
|-------|------|-------------------|
| **Power BI** (`/analytics/bi`) | Analyse **métier** : OCR, corrections, alertes, catégories, assistant IA | PostgreSQL (vues `fact_*_bi`, dims) |
| **Grafana — Dashboard innovant** | **Technique temps réel** : santé API, erreurs upload, latence pipeline | Prometheus uniquement |
| **Grafana — Monitoring technique** | Détail Prometheus (stats instantanées) | `/internal/prometheus/metrics` |
| **Grafana — PostgreSQL** (optionnel) | Exploitation live SQL (messagerie, détail OCR par champ) | Requêtes directes sur la base |

Le dashboard **FactuPRO — Dashboard innovant** ne duplique plus Power BI : OCR, corrections comptable et alertes superviseur sont dans Power BI ; Grafana garde uniquement ce que Prometheus expose en direct.

**Parcours comptable (courbe corrections / jour)** : [`docs/powerbi-parcours-comptable.md`](../docs/powerbi-parcours-comptable.md) — vue `fact_comptable_parcours_bi`.

**Requêtes SQL Grafana** (si besoin) : [`docs/grafana-requetes-postgresql.md`](../docs/grafana-requetes-postgresql.md).

## Accès

- **Grafana** : http://localhost:3030 — login `admin` / `admin` (docker-compose)
- **Prometheus** : http://localhost:9090
- Dashboard analytique : **FactuPRO — Analytics innovant** (`/d/factupro-analytics`) — heatmaps, risques OCR, messagerie, catégories
- Dashboard technique : **FactuPRO — Monitoring technique** (`/d/factupro-tech`) — Prometheus
- Dashboard innovant : **FactuPRO — Dashboard innovant** (`/d/factupro-innovant`) — santé API, erreurs upload, perf pipeline (sans redondance Power BI)

**Requêtes dashboard innovant (PromQL)** : [`docs/grafana-dashboard-innovant-promql.md`](../docs/grafana-dashboard-innovant-promql.md)

## Métriques exposées (Prometheus)

### Pipeline (session / runtime)
- `factupro_avg_processing_seconds` — temps moyen par facture
- `factupro_pipeline_success_rate_pct` — % factures avec lignes extraites
- `factupro_anomaly_rate_pct` — anomalies / lignes
- `factupro_ocr_precision_pct` — précision OCR (PostgreSQL)

### Base PostgreSQL (persistant)
- `factupro_db_invoices_total`, `factupro_db_invoice_lines_total`
- `factupro_supervisor_alerts_unread` — alertes à traiter
- `factupro_correction_rate_pct` — % factures corrigées
- `factupro_db_items_uncategorized` — lignes sans catégorie

### Activité (compteurs — graphiques dans le temps)
- `factupro_uploads_total` / `factupro_upload_errors_total`
- `factupro_confirmations_total` / `factupro_confirmations_with_edits_total`

## Relancer après modification

```bash
docker compose build grafana
docker compose up -d --force-recreate grafana
```

Attendre ~30 s puis ouvrir :
- Innovant (technique temps réel) : http://localhost:3030/d/factupro-innovant
- Technique : http://localhost:3030/d/factupro-tech

### Si tous les panneaux affichent « No data »

1. Vérifier Prometheus : http://localhost:9090/targets → `factupro-backend` doit être **UP**.
2. Dans Grafana : **Connections → Data sources** → choisir **Prometheus** (URL `http://prometheus:9090`), pas `prometheus-1` ni une source sans URL.
3. Reconstruire Grafana (corrige les sources dupliquées) :
   ```bash
   docker compose build grafana
   docker compose up -d --force-recreate grafana
   ```
4. Rafraîchir le dashboard (F5) ou **Dashboard settings → JSON Model → Save**.
