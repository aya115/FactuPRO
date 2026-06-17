# Power BI — Mesures Assistant IA (Page 5)

## 1. Mettre à jour les données PostgreSQL

Après déploiement du backend, recréer les vues BI :

```bash
docker compose exec backend python -c "from app import run_migrations; run_migrations()"
```

Ou redémarrer le backend (les vues sont appliquées au démarrage).

Dans **Power BI Desktop** : **Accueil → Actualiser** pour charger la table **`fact_qa_questions_bi`**.

## 2. Relations Power BI (important)

### Clé primaire de `qa_questions` / `fact_qa_questions_bi`

- **Clé unique** : `question_id` (ou `id`) — une ligne = une question
- **`user_id` n’est PAS unique** : le même utilisateur peut poser 5, 10, 100 questions

Si Power BI affiche *« valeur en double user_id = 5 »*, c’est qu’une relation est mal configurée (souvent `user_id` traité comme clé unique).

### Relations correctes

| De (plusieurs) | Colonne | Vers (un) | Colonne | Cardinalité |
|----------------|---------|-----------|---------|-------------|
| `fact_qa_questions_bi` | `user_key` | `dim_user_bi` | `user_key` | **Plusieurs vers un (*:1)** |
| `fact_qa_questions_bi` | `date_id` | `dim_date_bi` | `date_id` | **Plusieurs vers un (*:1)** |

**À ne pas faire** : relation *un vers plusieurs* avec `users` en partant de `user_id` sur `qa_questions` comme côté « un ».

### Corriger dans Power BI Desktop

1. **Modélisation** (icône diagramme)
2. **Supprimer** la relation incorrecte entre `qa_questions` et `users`
3. Recréer : glisser `fact_qa_questions_bi[user_key]` → `dim_user_bi[user_key]`
4. Vérifier : **Plusieurs vers un (*:1)**, sens des filtres : **Simple**
5. Clic droit sur `fact_qa_questions_bi` → **Marquer comme table de date** non — mais définir `question_id` comme clé si demandé (Power BI : ne pas marquer `user_id` unique)
6. **Accueil → Actualiser**

## 3. Nombre de questions **par utilisateur** (mesure DAX uniquement)

Relation obligatoire : `fact_qa_questions_bi[user_key]` → `dim_user_bi[user_key]` (**Plusieurs vers un *:1**).

Clic droit sur **`fact_qa_questions_bi`** → **Nouvelle mesure** :

```dax
Nb questions par utilisateur =
COUNTROWS ( fact_qa_questions_bi )
```

Cette mesure compte les questions **dans le contexte du visuel** : avec `dim_user_bi[full_name]` en axe, chaque barre affiche le total de cet utilisateur.

**Graphique à barres** :
- Axe Y : `dim_user_bi[full_name]`
- Valeurs : `Nb questions par utilisateur`
- Trier par valeur décroissante

**Tableau** :
- Colonnes : `dim_user_bi[full_name]`, `dim_user_bi[role]`, `dim_user_bi[email]`
- Valeurs : `Nb questions par utilisateur`

---

## 4. Autres mesures DAX

Clic droit sur **`fact_qa_questions_bi`** → **Nouvelle mesure**, puis coller chaque formule.

### Cartes (comme vos indicateurs actuels)

```dax
Nb questions IA =
COUNTROWS ( fact_qa_questions_bi )
```

```dax
Nb questions IA avec SQL =
CALCULATE (
    COUNTROWS ( fact_qa_questions_bi ),
    fact_qa_questions_bi[has_sql_flag] = 1
)
```

```dax
Nb utilisateurs Assistant IA =
DISTINCTCOUNT ( fact_qa_questions_bi[user_id] )
```

```dax
Nb questions IA ce mois =
CALCULATE (
    COUNTROWS ( fact_qa_questions_bi ),
    DATESMTD ( dim_date_bi[full_date] )
)
```
*(Nécessite la relation `date_id` avec `dim_date_bi`.)*

Sans relation date, utilisez plutôt :

```dax
Nb questions IA 30 jours =
CALCULATE (
    COUNTROWS ( fact_qa_questions_bi ),
    fact_qa_questions_bi[question_date] >= TODAY () - 30
)
```

```dax
Nb questions comptables =
CALCULATE (
    COUNTROWS ( fact_qa_questions_bi ),
    fact_qa_questions_bi[role] = "comptable"
)
```

```dax
Nb questions superviseurs =
CALCULATE (
    COUNTROWS ( fact_qa_questions_bi ),
    fact_qa_questions_bi[role] IN { "superviseur", "admin" }
)
```

### Longueur moyenne des questions

```dax
Longueur moyenne question (car.) =
AVERAGE ( fact_qa_questions_bi[question_length_chars] )
```

## 5. Visuels suggérés pour la Page 5

| Visuel | Champ / mesure |
|--------|----------------|
| **Carte** | `Nb questions IA` |
| **Carte** | `Nb questions IA avec SQL` |
| **Carte** | `Nb utilisateurs Assistant IA` |
| **Graphique courbes** | Axe : `question_date` — Valeur : `Nb questions IA` |
| **Graphique à barres** | Axe : `dim_user_bi[full_name]` — Valeur : `Nb questions par utilisateur` |
| **Graphique à barres** | Axe : `role` — Valeur : `Nb questions IA` |
| **Table** | `full_name`, `question`, `question_date`, `has_sql_flag` |

## 6. Colonnes de `fact_qa_questions_bi`

| Colonne | Description |
|---------|-------------|
| `question_id` | Identifiant unique |
| `user_id` / `user_key` | Utilisateur |
| `full_name`, `email`, `role` | Profil |
| `question` | Texte posé à l’assistant |
| `sql_generated` | Requête SQL générée (si succès) |
| `created_at` | Horodatage |
| `question_date` | Date (pour filtres) |
| `date_id` | Lien vers `dim_date_bi` |
| `has_sql_flag` | 1 si SQL produit |
| `question_length_chars` | Longueur de la question |

## 7. Note

Les questions ne sont enregistrées que lorsque l’assistant répond **sans** demander de clarification (`/qa` dans l’app). Les questions abandonnées ou en erreur peuvent ne pas apparaître.
