"""
Crée (ou met à jour) un utilisateur admin pour la base Postgres du docker-compose.

Connexion :
  - Depuis ta machine (hôte) : par défaut localhost:5433, base invoice_docker
    (voir docker-compose : port 5433 -> 5432 dans le conteneur).
  - Depuis le conteneur backend : docker compose exec backend python create_admin_docker.py
    → PG_HOST=db, PG_PORT=5432 sont déjà définis par compose.

Variables optionnelles (même noms que app.py) :
  PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD
  ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_FULL_NAME
"""
import argparse
import os
import sys

import bcrypt
import psycopg2


def pg_config():
    host = os.environ.get("PG_HOST", "localhost")
    # Hôte Windows/Linux vers Postgres du compose : 5433. Dans le conteneur : 5432.
    port_default = "5432" if host == "db" else "5433"
    port = int(os.environ.get("PG_PORT", port_default))
    db = os.environ.get("PG_DB", "invoice_docker")
    user = os.environ.get("PG_USER", "postgres")
    password = os.environ.get("PG_PASSWORD", "postgres")
    return host, port, db, user, password


def main():
    parser = argparse.ArgumentParser(description="Créer ou mettre à jour un compte admin (Docker).")
    parser.add_argument("--email", default=os.environ.get("ADMIN_EMAIL", "aya.soltani@esprit.tn"))
    parser.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD", "adminadmin"))
    parser.add_argument("--full-name", default=os.environ.get("ADMIN_FULL_NAME", "admin"))
    args = parser.parse_args()

    host, port, db, user, password_pg = pg_config()
    password_hash = bcrypt.hashpw(args.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=db,
            user=user,
            password=password_pg,
        )
    except psycopg2.OperationalError as e:
        print(f"Connexion impossible ({host}:{port} / {db}) : {e}", file=sys.stderr)
        print(
            "Vérifie que le conteneur db tourne (docker compose up -d db) "
            "et que PG_HOST / PG_PORT correspondent (hôte : 5433, conteneur : db:5432).",
            file=sys.stderr,
        )
        sys.exit(1)

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (email, password_hash, full_name, role)
        VALUES (%s, %s, %s, 'admin')
        ON CONFLICT (email) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            full_name = EXCLUDED.full_name,
            role = 'admin'
        """,
        (args.email, password_hash, args.full_name),
    )
    conn.commit()
    cur.close()
    conn.close()

    print(f"OK — compte admin prêt : {args.email} (rôle admin, change le mot de passe après connexion)")


if __name__ == "__main__":
    main()
