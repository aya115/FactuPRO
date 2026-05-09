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
