import bcrypt
import psycopg2
import os

PG_HOST = "localhost"
PG_DB = "testdb"
PG_USER = "postgres"
PG_PASSWORD = "postgres"

email = "aya.soltani@esprit.tn"
password = "adminadmin"  # change après première connexion
full_name = "admin"

conn = psycopg2.connect(
        host=PG_HOST,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD
    )

cur = conn.cursor()

password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

cur.execute("""
        INSERT INTO users (email, password_hash, full_name, role)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (email) DO NOTHING
    """, (email, password_hash, full_name, "admin"))

conn.commit()
cur.close()
conn.close()

print("✅ Admin créé avec succès")