import psycopg2

DB_CONFIG = {
    "dbname": "mydatabase",
    "user": "myuser",  # ✅ Match this with POSTGRES_USER
    "password": "mypassword",  # ✅ Match this with POSTGRES_PASSWORD
    "host": "localhost",  # ✅ PostgreSQL runs on localhost inside Docker
    "port": "5432"  # ✅ Default PostgreSQL port
}

try:
    conn = psycopg2.connect(**DB_CONFIG)
    print("✅ Connected to PostgreSQL in Docker!")
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
