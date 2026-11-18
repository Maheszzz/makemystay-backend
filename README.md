<div align="center">
  <h1>MakeMyStay.ai Backend API</h1>
  <p>FastAPI + SQLAlchemy + MySQL backend powering MakeMyStay.ai.</p>
</div>

---

## Tech Stack & Requirements

- **Python**: `3.10+` (production Docker/EC2; `3.9` also works locally)
- **Framework**: FastAPI, Uvicorn, Pydantic v2 (`pydantic-settings`)
- **Database & Migrations**: MySQL 8.x, SQLAlchemy 2.0, Alembic
- **Optional Local Services**: Redis (for Celery / RQ / rate-limiting & caching)

---

## Local Developer Setup

1. **Clone the repository**
   ```bash
   git clone <backend-repository-url>
   cd makemystay-backend
   ```

2. **Create and activate a Python virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
   For running the test suite, also install dev/test dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and configure your local database and secrets:
   ```env
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_USER=appuser
   DB_PASSWORD=your_local_db_password
   DB_NAME=makemystay
   ENV=development
   SECRET_KEY=replace_with_a_long_random_secret_key
   MAIL_USERNAME=your_smtp_username
   MAIL_PASSWORD=your_smtp_password
   MAIL_FROM=noreply@example.com
   MAIL_PORT=587
   MAIL_SERVER=smtp.example.com
   MAIL_FROM_NAME=MakeMyStay
   ```
   > **Note:** Keep `ENV=development`, `RUN_SCHEDULER=false`, and `LEAD_PULL_SYNC_ENABLED=false` for normal local development.

5. **Prepare local MySQL database & run migrations**
   Create the local database (if it does not exist):
   ```sql
   CREATE DATABASE makemystay CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
   Run Alembic migrations:
   ```bash
   alembic upgrade head
   ```

6. **Start the FastAPI server**
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   - API root: `http://127.0.0.1:8000`
   - Swagger UI: `http://127.0.0.1:8000/docs`
   - Health check: `http://127.0.0.1:8000/api/v1/health`

---

## Environment Loading Architecture

All environment loading is centralized in [`app/core/config.py`](app/core/config.py):
- **Local development**: Loads `.env` only (`load_app_env()` with `override=False`, so exported shell env vars always take precedence).
- **Production (EC2 / containers)**: Managed on the server via `.env.production` (when `ENV=production`) and PM2/container environment variables; never overwritten by local development files.
- **Alembic**: Uses [`app/utils/alembic_helper.py`](app/utils/alembic_helper.py), which delegates directly to `load_app_env()`.
- **Startup validation**: `validate_startup_settings()` validates required database, auth, and mail settings when the FastAPI app starts.

---

## Production Database SSH Tunnel (Optional)

If you need read/client access to a private RDS instance via an EC2 bastion:
```bash
ssh -i /path/to/your-key.pem -L 3336:172.31.46.162:3306 ubuntu@<EC2_HOST>
```
Never commit `.pem` keys or production credentials into the repository.

---

## Testing & Verification

```bash
# Run pytest suite (requires requirements-dev.txt)
pytest

# Check Alembic migration status
alembic current
```

## License

Proprietary software. All rights reserved. © 2026 MakeMyStay.ai
