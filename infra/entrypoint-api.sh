#!/bin/sh
set -e

echo "[api] Aplicando migrations Alembic..."
alembic upgrade head
echo "[api] Migrations OK."

echo "[api] Subindo servidor..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
