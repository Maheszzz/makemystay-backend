"""Admin: bulk import leads from CSV (multipart)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from loguru import logger
from sqlalchemy.orm import Session

from app.api.admin.schemas import (
    CsvImportResponse,
    CsvImportRetryQueuedResponse,
    LeadCsvImportResponse,
)
from app.configs.db_config import get_mysql_db
from app.core import security
from app.core.rate_limit import limiter
from app.models.csv_import import CsvImport
from app.services.csv_lead_import import run_csv_import

router = APIRouter()

_MAX_BYTES = 15 * 1024 * 1024  # 15 MiB
_MAX_ROWS = 5000
_READ_CHUNK = 1024 * 1024  # 1 MiB


@router.get(
    "/admin/leads/import-history",
    response_model=list[CsvImportResponse],
    summary="List recent CSV import history (admin)",
)
def list_import_history(
    limit: int = 50,
    db: Session = Depends(get_mysql_db),
    _admin=Depends(security.admin_required),
):
    """Returns the most recent CSV import records."""
    from app.models.user import User

    rows = (
        db.query(CsvImport)
        .outerjoin(User, CsvImport.created_by == User.id)
        .order_by(CsvImport.id.desc())
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        d = CsvImportResponse.from_orm(r)
        d.created_by_name = (r.creator.full_name or r.creator.email) if r.creator else None
        out.append(d)
    return out


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
    dry_run: bool = Form(False, description="Process without committing if True"),
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.get_current_user),
):
    """
    Upload a CSV file; each row is processed through the same pipeline as webhooks
    (dedup, assignment, CRM sync queue). Phone column is required per row.

    **Limits:** 15 MB file size, 5000 data rows. Rate limited per IP.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

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

    # Check for processing if NOT dry_run
    if not dry_run:
        active = db.query(CsvImport).filter(CsvImport.status == "processing").first()
        if active:
            raise HTTPException(
                status_code=409, 
                detail=f"Another import (Import #{active.id}) is currently processing. Please wait for it to finish."
            )

    # Create CsvImport record if NOT dry_run
    import_id = None
    if not dry_run:
        imp = CsvImport(
            file_name=file.filename or "unknown.csv",
            source=src,
            status="pending",
            created_by=current_user.id,
        )
        db.add(imp)
        db.commit()
        db.refresh(imp)
        import_id = imp.id

        # Gap #3: Async execution
        from app.tasks.lead_tasks import process_csv_import_task
        process_csv_import_task.delay(import_id, text, src)
        
        return LeadCsvImportResponse(
            import_id=import_id,
            row_count=0,
            imported=0,
            duplicates=0,
            skipped_no_phone=0,
            errors=0,
            status="pending"
        )

    # Dry run remains synchronous for immediate feedback
    try:
        result = await run_csv_import(
            db,
            text,
            src,
            dry_run=True,
            skip_rows=0,
            max_rows=_MAX_ROWS,
        )
        return LeadCsvImportResponse(**result.to_dict(), status="dry_run")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("dry-run failed: {}", e)
        raise HTTPException(status_code=500, detail="Dry run failed") from e


@router.post(
    "/admin/leads/import/{import_id}/cancel",
    summary="Cancel an in-flight CSV import (worker stops on next row)",
)
def cancel_csv_import(
    import_id: int,
    db: Session = Depends(get_mysql_db),
    _admin=Depends(security.admin_required),
):
    """Sets status to ``cancelled``; the Celery worker checks each row and exits."""
    imp = db.query(CsvImport).filter(CsvImport.id == import_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Import not found")
    if imp.status not in ("pending", "processing"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel import in status '{imp.status}'",
        )
    imp.status = "cancelled"
    db.commit()
    return {"import_id": import_id, "status": "cancelled"}


@router.post(
    "/admin/leads/import/{import_id}/retry-failures",
    response_model=CsvImportRetryQueuedResponse,
    summary="Queue retry of failed rows for a CSV import",
)
def queue_retry_csv_import_failures(
    import_id: int,
    db: Session = Depends(get_mysql_db),
    _admin=Depends(security.admin_required),
):
    """Re-runs rows stored in ``csv_import_failures`` via Celery (staggered Zoho enqueue)."""
    imp = db.query(CsvImport).filter(CsvImport.id == import_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Import not found")
    from app.models.csv_import import CsvImportFailure

    n = db.query(CsvImportFailure).filter(CsvImportFailure.import_id == import_id).count()
    if n == 0:
        raise HTTPException(status_code=400, detail="No failed rows to retry for this import")
    if imp.status == "processing":
        raise HTTPException(status_code=409, detail="Import is still processing")

    active = db.query(CsvImport).filter(CsvImport.status == "processing").first()
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"Another import (Import #{active.id}) is currently processing.",
        )

    from app.tasks.lead_tasks import retry_csv_import_failures_task

    retry_csv_import_failures_task.delay(import_id)
    return CsvImportRetryQueuedResponse(import_id=import_id, status="queued")
