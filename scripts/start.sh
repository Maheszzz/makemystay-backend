#!/bin/bash
set -e

# Run database migrations (optional, depends on infra strategy, sometimes run separately)
echo "Running migrations..."
alembic upgrade head

# Start Uvicorn backend in the background
echo "Starting FastAPI backend..."
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4 &

# Start Nginx in the foreground
echo "Starting Nginx proxy..."
nginx -g "daemon off;"
