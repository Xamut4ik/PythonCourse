#!/bin/sh
set -e

echo "Waiting for database..."

python - <<'PY'
import os
import time
import psycopg

while True:
    try:
        conn = psycopg.connect(
            host=os.environ["DB_HOST"],
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            connect_timeout=3,
        )
        conn.close()
        break
    except psycopg.OperationalError:
        print("Database is not ready. Retrying...")
        time.sleep(2)
PY

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Django..."
exec "$@"
