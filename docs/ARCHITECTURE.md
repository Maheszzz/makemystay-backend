# no-broker-backend — architecture

## Request flow

1. **Uvicorn** loads `app.main:app` (FastAPI).
2. **Middleware**: CORS (explicit origins + regex for `localhost` / `127.0.0.1` any port — avoids **400** preflight failures when `ENV=production` locally) → CSRF (skipped for Bearer auth) → rate limit (SlowAPI) → routes. Optional **`CORS_EXTRA_ORIGINS`** env (comma-separated) adds more origins.
3. **Routers** are registered in one place: `app/bootstrap/routers.py` (`register_routers`). The HTTP surface area is easier to audit than scattered `include_router` calls in `main.py`.
4. **API prefix**: most routes live under `/api/v1`. Exceptions:
   - Razorpay: also mounted at `/payments/webhook` (dashboards often omit `/api/v1`).
   - Some webhook modules are included **with and without** `/api/v1` for reachability (see `routers.py`).

## Python version

- **Production** uses **Python 3.10+** (PEP 604 `X | Y` unions in annotations are fine).
- If you run **Python 3.9** locally, use **`typing.Optional`** / **`typing.Union`** for optional types in annotations — `int | None` is evaluated at import time on 3.9 and will raise `TypeError`.

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

**`GET /api/v1/leads`** — CRM role-based list (`app/api/admin/crm.py`). The legacy repo-based listing lives at **`GET /api/v1/webhooks/lead-list`** (`app/api/webhooks.py`); do not add a second `GET /leads` on another router or Starlette will only match the first registered route.
| Lead enums & metadata payload | `app/core/lead_schema.py` |
| Models | `app/models/` |
| Celery | `app/core/celery_app.py`, `app/tasks/` |

## Related clients

- **makemystay-admin** (this repo’s sibling): Vite app, calls the same API base (e.g. `https://api.makemystay.ai/api/v1`) with Bearer admin JWT. The Leads CRM UI is split into `useLeadsPage` + modals under `src/features/leads/` (see that repo’s `src/features/leads/README.md`).
- **Public site**: separate frontend; same API for listings/contacts where applicable.
