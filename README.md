
<div align="center">
  <h1>MakeMyStay.ai - Backend API</h1>
  <p>The robust FastAPI backend powering the first AI-native revenue engine for co-living and rental operators.</p>

  <p>
    <a href="https://fastapi.tiangolo.com/">
      <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi" alt="FastAPI" />
    </a>
    <a href="https://www.python.org/">
      <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
    </a>
    <a href="https://www.sqlalchemy.org/">
      <img src="https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy" />
    </a>
    <a href="https://www.mysql.com/">
      <img src="https://img.shields.io/badge/MySQL-4479A1?style=for-the-badge&logo=mysql&logoColor=white" alt="MySQL" />
    </a>
  </p>
</div>

---

## 🚀 Features

- **High Performance API**: Built with FastAPI for speed and efficiency.
- **Relational Data Management**: Powered by SQLAlchemy ORM and MySQL.
- **Data Validation**: Strict type checking and validation using Pydantic schemas.
- **Secure Endpoints**: API endpoints for property management, contacts, and services.
- **Scripting Support**: Automated scripts for bulk property insertion and updates.

## 🛠️ Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Language**: [Python 3.10+](https://www.python.org/) (production; **3.9** is OK locally if annotations use `typing.Optional` / `Union` — avoid `X | None` in type hints, which requires 3.10+)
- **ORM**: [SQLAlchemy](https://www.sqlalchemy.org/)
- **Database**: [MySQL](https://www.mysql.com/)
- **Server**: [Uvicorn](https://www.uvicorn.org/)
- **Validation**: [Pydantic](https://docs.pydantic.dev/)

## 📦 Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd no-broker-backend
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   Copy the example environment file and configure your credentials:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your database details:
   ```env
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_password
   DB_NAME=makemystay
   ```

5. **Start the server**
   ```bash
   python3 -m uvicorn app.main:app --reload
   ```
   The API will be available at `http://localhost:8000`.

## Database access via SSH tunnel

Production MySQL often sits on a private IP (for example RDS). You reach it by SSH port forwarding through an EC2 instance that can see that address.

### Private key (`.pem`)

- Use the **private key file** from the EC2 key pair (for example `~/Downloads/makemystayrealty.pem`). It is not stored in this repository and cannot be recovered from AWS if you lose the file; you would need a new key pair or another access method (for example SSM).
- Restrict permissions on the key: `chmod 600 /path/to/your.pem`
- Never commit `.pem` files or paste private key contents into issues, chat, or CI logs.

### Defaults in `deploy.sh`

[`deploy.sh`](deploy.sh) uses:

- **`DEPLOY_PEM`**: PEM path (default on this machine’s layout: `/Users/maheswaranm/Downloads/makemystayrealty.pem`). Override with `DEPLOY_PEM=/path/to/key.pem`.
- **`DEPLOY_HOST`**: SSH target (default `13.126.149.224`). The deploy script also targets `13.201.61.117` in its server loop.
- **User**: `ubuntu`

### Example tunnel

Forward local port `3336` to MySQL on the database host **as resolved from the EC2 box** (replace the private IP if yours differs):

```bash
ssh -i ~/Downloads/makemystayrealty.pem -L 3336:172.31.46.162:3306 ubuntu@13.126.149.224
```

Keep that session open. Then point your SQL client or app at **`127.0.0.1:3336`**. For local overrides when tunneling, see [`.env.example`](.env.example) (`DB_PORT=3336` is documented there).

### Other repos / machines

- Debug logs in this repo may reference paths like `makemystay-backend.pem` on Windows; that is not necessarily your local key path.
- The frontend repo’s `deploy.sh` may default to a different PEM (for example `$HOME/.ssh/mmsr_deploy_key.pem`); that can differ from the key used for this backend / DB bastion.

## Portal leads → Zoho CRM (operations)

**High-volume sources** (99acres, Housing.com, CSV imports) set `crm_status=pending` in MySQL. They are pushed to Zoho by the Celery task `sync_pending_leads_batch_task` (bulk upsert), which **Celery Beat** schedules every **60 seconds** ([`app/core/celery_app.py`](app/core/celery_app.py)). You must run:

- `celery -A app.core.celery_app worker` (consumer)
- `celery -A app.core.celery_app beat` (scheduler — without this, pending leads never reach Zoho)

**99acres** typically sends leads with **POST** `/webhooks/99acres` (XML). Check logs for `99acres webhook` and `process_webhook_lead_task`. Validate the portal’s push URL and `X-API-Key` / query `api_key` match production.

**Zoho list view:** Bulk upsert uses duplicate checks on **Phone** and **Email**. New inquiries often **update an existing lead**; **Created Time** may stay old—sort or search by **Modified Time** (or by phone).

**Health:** From the repo root, `PYTHONPATH=. python scripts/check_sync_health.py` prints CRM status counts and “today” ingest (MySQL `CURRENT_DATE`). Admins can also **POST** `/api/v1/admin/sync/zoho-pending-batch` to enqueue one batch manually if Beat was offline.

## 📚 API Documentation

Once the server is running, you can access the interactive API documentation:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## 📂 Project Structure

```bash
no-broker-backend/
├── app/
│   ├── main.py          # Application entry point
│   ├── models/          # SQLAlchemy database models
│   ├── schemas/         # Pydantic schemas for validation
│   ├── api/             # API route handlers
│   ├── core/            # Core configuration and database setup
│   └── repo/            # Repository layer for DB interactions
├── insert_bulk_properties.py # Script to adding properties
├── update_bulk_properties.py # Script for updating property images
├── requirements.txt     # Python dependencies
└── .env                 # Environment variables
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is proprietary software. All rights reserved. © 2026 MakeMyStay.ai
