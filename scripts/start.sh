#!/bin/bash
set -e

# Run database migrations (optional, depends on infra strategy, sometimes run separately)
echo "Running migrations..."
alembic upgrade head

# Start Uvicorn backend
echo "Starting FastAPI backend on 0.0.0.0:8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
