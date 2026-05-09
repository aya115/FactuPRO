# CI/CD Setup

This project uses two GitHub Actions workflows:

- `CI` in `.github/workflows/ci.yml`
- `CD` in `.github/workflows/cd.yml`

## CI workflow

Runs on `pull_request`, on `workflow_dispatch` (manuel), and on pushes to `main` / `develop` / `factupro`.

Checks included:

- Backend dependency install (`backend/requirements.txt`)

- Backend syntax compilation (`python -m compileall`)
- Frontend dependency install (`npm ci`)
- Frontend tests (`npm test -- --watchAll=false --passWithNoTests`)
- Frontend production build (`npm run build`)

## CD workflow

Runs on:

- Push to `main`
- Manual trigger (`workflow_dispatch`)

Deployment strategy:

- SSH into your server
- Update repository to latest `main`
- Run `docker compose up -d --build`

## Required GitHub Secrets

Create these repository secrets in GitHub:

- `DEPLOY_HOST`: server IP or domain
- `DEPLOY_USER`: SSH user on server
- `DEPLOY_SSH_KEY`: private SSH key content (PEM/OpenSSH)
- `DEPLOY_PORT`: SSH port (usually `22`)
- `DEPLOY_APP_DIR`: absolute path of project on server (example: `/opt/invoice_app`)

## Server prerequisites

On the deployment server, ensure:

- Docker and Docker Compose plugin are installed
- Project repo is already cloned in `DEPLOY_APP_DIR`
- `.env` exists in that directory with production values
- SSH user has rights to run docker commands

## First deployment checklist

1. Push this branch to GitHub.
2. Add all required secrets.
3. Open Actions tab and run `CD` manually once.
4. Verify services:
   - Frontend: `http://<server>:3000`
   - Backend: `http://<server>:5000`

## Dépannage

### CD : `missing server host` ou erreur sur les secrets

Le job **CD** a besoin des secrets du dépôt. Va dans **Settings → Secrets and variables → Actions** et crée au minimum :

- `DEPLOY_HOST` : IP ou nom de domaine du serveur
- `DEPLOY_USER` : utilisateur SSH (ex. `ubuntu`, `deploy`)
- `DEPLOY_SSH_KEY` : contenu de la **clé privée** SSH (celle qui correspond à la clé publique sur le serveur)
- `DEPLOY_PORT` : port SSH (souvent `22`) — optionnel, `22` est utilisé par défaut si vide
- `DEPLOY_APP_DIR` : chemin absolu du clone Git sur le serveur (ex. `/home/ubuntu/FactuPRO`)

Sans ces valeurs, le déploiement SSH ne peut pas démarrer.

### CI : échec sur « Run frontend tests »

Le test par défaut CRA cherchait le texte « learn react » qui n’existe plus. Le fichier `frontend/src/App.test.js` a été aligné sur la page d’accueil actuelle (router + AuthProvider).

### CI : `Cannot find module 'react-router-dom'`

Avec **react-router-dom v7**, le champ `exports` du paquet n’est pas toujours résolu par **Jest 27** (CRA 5). Des entrées `jest.moduleNameMapper` ont été ajoutées dans `frontend/package.json` pour pointer vers les fichiers CommonJS réels (`dist/index.js`, etc.).

### CI : `ReferenceError: TextEncoder is not defined`

**react-router v7** utilise `TextEncoder` au chargement. Sous **Jest + jsdom**, ce global peut être absent. Un polyfill a été ajouté dans `frontend/src/setupTests.js` via le module Node `util`.

### CI : `Unexpected token 'export'` dans `react-markdown`

**react-markdown** est publié en **ESM** ; Jest (CRA) ne transpile pas `node_modules` par défaut. Un stub **CommonJS** est dans `frontend/__mocks__/react-markdown.js` et est forcé via **`jest.moduleNameMapper`** (`^react-markdown$` → ce fichier), car `jest.mock` dans `setupTests.js` peut s’exécuter trop tard pour les imports transitifs.
