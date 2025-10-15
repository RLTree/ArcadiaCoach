#!/usr/bin/env bash
set -euo pipefail

echo "[Arcadia Coach] Running database migrations..."
python -m scripts.run_migrations

echo "[Arcadia Coach] Starting Arcadia Coach backend..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
