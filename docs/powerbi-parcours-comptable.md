# Power BI — Parcours comptable (corrections vs direct OK)

Visualisation **métier** retirée de Grafana pour éviter la redondance : à construire dans **Power BI** avec PostgreSQL.

## 1. Mettre à jour les vues PostgreSQL

```bash
docker compose exec backend python -c "from app import run_migrations; run_migrations()"
```

Tables / vues utilisées :

| Vue | Rôle |
|-----|------|
| `fact_comptable_parcours_bi` | Une ligne par facture **confirmée** |
| `dim_confirmation_date_bi` | Calendrier des dates de confirmation |
| `dim_user_bi` | Comptable (optionnel) |

### Colonnes clés de `fact_comptable_parcours_bi`

| Colonne | Signification |
|---------|----------------|
| `confirmation_date` | Jour où le comptable a validé la facture |
| `had_manual_correction_flag` | `1` = le comptable a modifié au moins un champ · `0` = direct OK |
| `parcours_type` | Libellé : « Correction comptable » ou « Direct OK (sans correction) » |
| `ocr_precision_pct` | Précision OCR (0–100) |
| `champs_corriges_count` | Nombre de champs corrigés |
| `supervisor_alert_flag` | `1` si alerte superviseur créée |

> Source : comparaison OCR original vs version validée dans `ocr_precision_details` (persistant en base, contrairement aux compteurs Prometheus qui repartent à 0 au redémarrage Docker).

---

## 2. Importer dans Power BI Desktop

1. **Obtenir des données** → PostgreSQL → serveur Docker (`localhost`, base `invoice_db`, user/mot de passe du `.env`)
2. Cocher : `fact_comptable_parcours_bi`, `dim_confirmation_date_bi`, `dim_user_bi`
3. **Modélisation** :
   - `fact_comptable_parcours_bi[confirmation_date_id]` → `dim_confirmation_date_bi[date_id]` (**Plusieurs vers un *:1**)
   - `fact_comptable_parcours_bi[user_key]` → `dim_user_bi[user_key]` (**Plusieurs vers un *:1**)

4. **Accueil → Actualiser**

---

## 3. Mesures DAX (équivalent Grafana)

Clic droit sur **`fact_comptable_parcours_bi`** → **Nouvelle mesure** :

### Cartes du jour

```dax
Corrections du jour =
CALCULATE (
    COUNTROWS ( fact_comptable_parcours_bi ),
    fact_comptable_parcours_bi[had_manual_correction_flag] = 1
)
```

```dax
Direct OK du jour =
CALCULATE (
    COUNTROWS ( fact_comptable_parcours_bi ),
    fact_comptable_parcours_bi[had_manual_correction_flag] = 0
)
```

```dax
Conformité % =
VAR Total =
    COUNTROWS ( fact_comptable_parcours_bi )
VAR Ok =
    CALCULATE (
        COUNTROWS ( fact_comptable_parcours_bi ),
        fact_comptable_parcours_bi[had_manual_correction_flag] = 0
    )
RETURN
    DIVIDE ( Ok, Total, 0 ) * 100
```

---

## 4. Visuels recommandés (comme l’ancien Grafana)

### Courbe verte / rouge qui fonctionne (1 seule forme continue)

> **Pourquoi 2 mesures sur un graphique en courbes ne marche pas :**  
> `BLANK()` coupe la ligne. Power BI trace **2 séries séparées** (point isolé en rouge, trait plat en vert) — pas une courbe unique.

**Solution recommandée : graphique en aires empilées** (forme de courbe continue, vert en bas + rouge en haut).

```dax
Palier conforme =
VAR v = [Corrections par jour]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( v ), BLANK (),
        v <= 1, v,
        1
    )
```

```dax
Surplus alerte =
VAR v = [Corrections par jour]
RETURN
    IF ( v > 1, v - 1, BLANK () )
```

**Configuration :**
1. Visual : **Graphique en aires empilées** (Stacked area chart) — pas « courbes » classique
2. Axe X : `dim_confirmation_date_bi[full_date]`
3. Axe Y : `Palier conforme` + `Surplus alerte` (les 2 mesures)
4. Couleurs : `Palier conforme` = **vert** · `Surplus alerte` = **rouge**
5. Format → **Étiquettes** : désactivées (optionnel)

**Lecture :** la forme totale monte avec les corrections. Le **bas reste vert** (0–1 correction), le **haut devient rouge** quand ça dépasse 1.

---

### Alternative : une seule courbe + seuil (si vous refusez l’aire)

1. Axe Y : **uniquement** `Corrections par jour` (retirez les 2 mesures zone)
2. Format → **Analyse** → **Ligne constante** → valeur **1** → couleur orange (seuil)
3. Courbe **bleue/grise** : bas = bien, au-dessus de 1 = zone alerte

---

### Ancienne méthode (2 mesures courbes — déconseillée)

Les mesures `Corrections zone conforme` / `Corrections zone alerte` avec `BLANK()` provoquent des **trous** sur un graphique en courbes. Préférer `Palier conforme` + `Surplus alerte` en **aires empilées**.

### Courbe « Tendance corrections par jour »

- **Type** : Graphique en courbes ou histogramme
- **Axe X** : `dim_confirmation_date_bi[full_date]`
- **Valeurs** : `Corrections du jour` (ou les 2 mesures zone conforme / alerte ci-dessus)
- **Interprétation** : courbe haute = beaucoup de corrections · basse ou à zéro = journée conforme

### Courbe « Indice conformité % »

- **Axe X** : `dim_confirmation_date_bi[full_date]`
- **Valeurs** : `Conformité %`
- **Format** : pourcentage, échelle 0–100
- **Interprétation** : proche de 100 % = factures validées sans retouche

### Barres empilées vert / orange

- **Type** : Histogramme empilé
- **Axe X** : `dim_confirmation_date_bi[full_date]`
- **Axe Y** : `Direct OK du jour` (vert) + `Corrections du jour` (orange)
- Ou utiliser `parcours_type` en légende avec **Nombre de factures** = `COUNTROWS(fact_comptable_parcours_bi)`

### Donut période

- **Légende** : `parcours_type`
- **Valeurs** : `Nombre de factures = COUNTROWS(fact_comptable_parcours_bi)`

---

## 5. Où placer la page dans le rapport

- **Page superviseur** (ex. page OCR / alertes déjà embedée dans `/analytics/bi`)
- Ou nouvelle **Page 6 — Parcours comptable**

Après publication sur Power BI Service, mettre à jour `backend/data/powerbi_pages.json` si vous ajoutez une page embed dédiée.

---

## 6. Filtre « aujourd’hui »

Sur les cartes KPI, ajouter un filtre visuel ou une mesure :

```dax
Corrections aujourd'hui =
CALCULATE (
    [Corrections du jour],
    dim_confirmation_date_bi[full_date] = TODAY ()
)
```

---

## Grafana vs Power BI

| | Grafana (retiré) | Power BI (recommandé) |
|--|------------------|------------------------|
| Corrections / jour | Compteur Prometheus session | Historique PostgreSQL complet |
| Après redémarrage Docker | Données perdues | Données conservées |
| Public | Admin / ops | Superviseur / direction |

Grafana **FactuPRO — Dashboard innovant** garde uniquement le monitoring **technique** (API, erreurs upload, latence).
