"""Admin: bulk import leads from CSV (multipart)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from loguru import logger
from sqlalchemy.orm import Session

from app.api.admin.schemas import LeadCsvImportResponse
from app.configs.db_config import get_mysql_db
from app.core import security
from app.core.rate_limit import limiter
from app.services.csv_lead_import import run_csv_import

router = APIRouter()

_MAX_BYTES = 15 * 1024 * 1024  # 15 MiB
_MAX_ROWS = 5000
_READ_CHUNK = 1024 * 1024  # 1 MiB


async def _read_upload_bytes(upload: UploadFile, max_bytes: int) -> bytes:
    """Read upload in chunks so a single huge file cannot exhaust memory before the size check."""
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await upload.read(_READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large (max {max_bytes // (1024 * 1024)} MB)",
                )
            chunks.append(chunk)
    finally:
        await upload.close()

    return b"".join(chunks)


@router.post(
    "/admin/leads/import-csv",
    response_model=LeadCsvImportResponse,
    summary="Import leads from CSV (admin)",
)
@limiter.limit("10/minute")
async def import_leads_csv(
    request: Request,
    file: UploadFile = File(..., description="UTF-8 CSV with a header row"),
    source: str = Form(
        "csv",
        description="Stored on leads.source (e.g. csv, 99acres, housing)",
    ),
    db: Session = Depends(get_mysql_db),
    _admin=Depends(security.admin_required),
):
    """
    Upload a CSV file; each row is processed through the same pipeline as webhooks
    (dedup, assignment, CRM sync queue). Phone column is required per row.

    **Limits:** 15 MB file size, 5000 data rows. Rate limited per IP.
    """
    raw = await _read_upload_bytes(file, _MAX_BYTES)
    if not raw.strip():
        raise HTTPException(status_code=400, detail="Empty file")

    src = (source or "csv").strip()[:64]
    if not src:
        src = "csv"

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        logger.warning("import-csv decode error: {}", e)
        raise HTTPException(
            status_code=400,
            detail="File must be UTF-8 encoded CSV (with or without BOM)",
        ) from e

    try:
        result = await run_csv_import(
            db,
            text,
            src,
            dry_run=False,
            skip_rows=0,
            max_rows=_MAX_ROWS,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("import-csv failed: {}", e)
        raise HTTPException(status_code=500, detail="Import failed") from e

    return LeadCsvImportResponse(**result.to_dict())
