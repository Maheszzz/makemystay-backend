# no-broker-backend — architecture

## Request flow

1. **Uvicorn** loads `app.main:app` (FastAPI).
2. **Middleware**: CORS → CSRF (skipped for Bearer auth) → rate limit (SlowAPI) → routes.
3. **Routers** are registered in one place: `app/bootstrap/routers.py` (`register_routers`). The HTTP surface area is easier to audit than scattered `include_router` calls in `main.py`.
4. **API prefix**: most routes live under `/api/v1`. Exceptions:
   - Razorpay: also mounted at `/payments/webhook` (dashboards often omit `/api/v1`).
   - Some webhook modules are included **with and without** `/api/v1` for reachability (see `routers.py`).

## Database & schema

- **Runtime DB**: MySQL via SQLAlchemy (`app/configs/db_config.py`).
- **Schema changes**: **Alembic** (`alembic/`) is the source of truth in production — run `alembic upgrade head` on deploy.
- **Optional dev DDL**: `SQLALCHEMY_CREATE_ALL_ON_STARTUP` (default `false`). When `true`, imports all models and runs `create_all` once at startup — useful for a fresh local DB; **do not** rely on this in production.

## Key packages

| Area | Location |
|------|----------|
| Admin API (composed router) | `app/api/admin/__init__.py` → `operations.py` (stats, sync, jobs, WhatsApp, payments) + `crm.py` (leads, RMs, funnel, workload) |
| Shared admin request bodies | `app/api/admin/schemas.py` |
| Lead processing | `app/services/lead_processor.py`, `app/tasks/lead_tasks.py` |
| Lead enums & metadata payload | `app/core/lead_schema.py` |
| Models | `app/models/` |
| Celery | `app/core/celery_app.py`, `app/tasks/` |

## Related clients

- **makemystay-admin** (this repo’s sibling): Vite app, calls the same API base (e.g. `https://api.makemystay.ai/api/v1`) with Bearer admin JWT. The Leads CRM UI is split into `useLeadsPage` + modals under `src/features/leads/` (see that repo’s `src/features/leads/README.md`).
- **Public site**: separate frontend; same API for listings/contacts where applicable.
