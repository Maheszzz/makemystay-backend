"""Shared CSV → lead pipeline for CLI and admin API (same column mapping as ``import_leads_csv``)."""

from __future__ import annotations

import csv
import hashlib
import io
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.schemas.lead import LeadCreate
from app.services.lead_processor import process_lead
from app.utils.csv_normalization import normalize_location, normalize_name, normalize_phone

# Map logical field -> list of CSV header names to try (lowercase compared).
COLUMN_ALIASES: Dict[str, List[str]] = {
    "phone": [
        "mobile",
        "phone",
        "phone1",
        "contactno",
        "contact number",
        "contactnumber",
        "tel",
        "mobile number",
        "mobile no",
        "phonenumber",
        "phone number",
    ],
    "name": ["name", "customer name", "lead name", "full name", "fullname"],
    "email": ["email", "e-mail", "mail id", "emailid", "email id"],
    "city": ["city"],
    "location": ["location", "area", "locality"],
    "budget": ["budget", "price range", "price"],
    "message": ["message", "qryinfo", "query", "remarks", "comments"],
    "external_id": [
        "qryid",
        "qry id",
        "lead id",
        "leadid",
        "enquiry id",
        "external id",
        "enquiry no",
    ],
    "project_name": ["project", "projectname", "project name", "property"],
}


def norm_header(h: str) -> str:
    return (h or "").strip().lower().replace("\ufeff", "")


def build_row_map(fieldnames: List[str]) -> Dict[str, str]:
    """Map normalized header -> original header (for DictReader access)."""
    out: Dict[str, str] = {}
    for h in fieldnames:
        out[norm_header(h)] = h
    return out


def _get(row: Dict[str, str], header_map: Dict[str, str], logical: str) -> str:
    for alias in COLUMN_ALIASES.get(logical, []):
        orig = header_map.get(alias)
        if orig is not None:
            v = (row.get(orig) or "").strip()
            if v:
                return v
    return ""


def _get_phone_raw(row: Dict[str, str], header_map: Dict[str, str]) -> str:
    v = _get(row, header_map, "phone")
    if v:
        return v
    for key, orig in header_map.items():
        if "phone" in key or "mobile" in key or key == "tel":
            val = (row.get(orig) or "").strip()
            if val:
                return val
    return ""


def row_to_lead_create(row: Dict[str, str], header_map: Dict[str, str]) -> Optional[LeadCreate]:
    raw_phone = _get_phone_raw(row, header_map)
    phone = normalize_phone(raw_phone) if raw_phone else None
    if not phone:
        return None
    name = normalize_name(_get(row, header_map, "name") or "User")
    email = _get(row, header_map, "email") or None
    if email == "":
        email = None
    city = normalize_location(_get(row, header_map, "city"))
    location = normalize_location(_get(row, header_map, "location"))
    budget = _get(row, header_map, "budget") or None
    message = _get(row, header_map, "message") or None
    project_name = _get(row, header_map, "project_name") or None
    external_id = _get(row, header_map, "external_id") or None
    if external_id == "":
        external_id = None
    try:
        return LeadCreate(
            name=name,
            email=email,
            phone=phone,
            city=city,
            location=location,
            budget=budget,
            message=message,
            project_name=project_name,
            external_id=external_id,
        )
    except Exception:
        return None


def _row_is_effectively_empty(row: Dict[str, str]) -> bool:
    return not any((v or "").strip() for v in row.values())


def parse_csv_text(text: str) -> tuple[List[Dict[str, str]], Dict[str, str]]:
    """Parse CSV text; returns (data rows, header_map for COLUMN_ALIASES). Uses ``StringIO`` for RFC-correct multiline fields."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    header_map = build_row_map(list(reader.fieldnames))
    rows = list(reader)
    return rows, header_map


@dataclass
class CsvImportResult:
    import_id: Optional[int] = None
    imported: int = 0
    duplicates: int = 0
    skipped_no_phone: int = 0
    skipped_empty: int = 0
    errors: int = 0
    row_count: int = 0
    error_samples: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "import_id": self.import_id,
            "imported": self.imported,
            "duplicates": self.duplicates,
            "skipped_no_phone": self.skipped_no_phone,
            "skipped_empty": self.skipped_empty,
            "errors": self.errors,
            "row_count": self.row_count,
            "error_samples": self.error_samples,
        }


def _append_error_sample(samples: List[str], msg: str, limit: int = 15) -> None:
    if len(samples) >= limit:
        return
    samples.append(msg[:500])


from app.models.lead import Lead
from app.models.csv_import import CsvImport, CsvImportFailure


async def run_csv_import(
    db: Session,
    text: str,
    source: str,
    *,
    dry_run: bool = False,
    skip_rows: int = 0,
    max_rows: int = 5000,
    import_id: Optional[int] = None,
) -> CsvImportResult:
    """
    Import leads from CSV text. Uses ``process_lead`` (dedup, Zoho queue, etc.).
    """
    file_hash = hashlib.md5(text.encode("utf-8")).hexdigest()

    # 1. Idempotency Check (only if not dry run)
    if not dry_run:
        existing_import = db.query(CsvImport).filter(CsvImport.file_hash == file_hash, CsvImport.status == "completed").first()
        if existing_import:
            raise ValueError(f"This file has already been imported successfully (Import #{existing_import.id})")

    rows, header_map = parse_csv_text(text)
    if skip_rows:
        rows = rows[skip_rows:]
    if len(rows) > max_rows:
        raise ValueError(f"Too many rows ({len(rows)}); maximum is {max_rows}")

    out = CsvImportResult(row_count=len(rows), import_id=import_id)

    # Update record status if we have one
    imp: Optional[CsvImport] = None
    if import_id and not dry_run:
        imp = db.query(CsvImport).filter(CsvImport.id == import_id).first()
        if imp:
            imp.status = "processing"
            imp.file_hash = file_hash
            imp.processing_started_at = datetime.now(timezone.utc)
            imp.processing_completed_at = None
            db.commit()

    # Use a specific recovery tag if it's a manual import
    processed_source = source
    if not dry_run and not source.endswith("_recovery") and source != "website":
        processed_source = f"{source}_recovery"

    started = time.perf_counter()
    row_latencies_ms: List[float] = []
    cancelled_break = False

    for i, row in enumerate(rows, start=1):
        if import_id and not dry_run:
            st = db.query(CsvImport.status).filter(CsvImport.id == import_id).scalar()
            if st == "cancelled":
                cancelled_break = True
                break

        row_t0 = time.perf_counter()
        if _row_is_effectively_empty(row):
            out.skipped_empty += 1
            row_latencies_ms.append((time.perf_counter() - row_t0) * 1000.0)
            continue

        lc = row_to_lead_create(row, header_map)
        if not lc:
            logger.warning("Row {}: no valid phone — {}", i, row)
            out.skipped_no_phone += 1
            if imp:
                failure = CsvImportFailure(
                    import_id=import_id,
                    row_index=i,
                    row_data=row,
                    error_message="Missing or invalid phone number",
                )
                db.add(failure)
            row_latencies_ms.append((time.perf_counter() - row_t0) * 1000.0)
            continue

        if dry_run:
            from app.models.lead import Lead

            existing = db.query(Lead).filter(Lead.phone == lc.phone).first()
            if existing:
                out.duplicates += 1
            else:
                out.imported += 1
            row_latencies_ms.append((time.perf_counter() - row_t0) * 1000.0)
            continue

        try:
            result = await process_lead(
                db,
                lc,
                processed_source,
                raw_payload=lc.model_dump(),
                raise_on_failure=True,
                csv_import_stagger_index=i,
                sync_to_zoho=imp.sync_to_zoho if imp else True,
                send_whatsapp=imp.send_whatsapp if imp else True,
                trigger_ai=imp.trigger_ai if imp else True,
            )
            if result is None:
                out.errors += 1
            elif (result.reentry_count or 0) > 0:
                out.duplicates += 1
            else:
                out.imported += 1
        except Exception as e:
            out.errors += 1
            logger.error("Row {}: {}", i, e)
            _append_error_sample(out.error_samples, f"Row {i}: {e!s}")
            if imp:
                failure = CsvImportFailure(
                    import_id=import_id,
                    row_index=i,
                    row_data=row,
                    error_message=str(e),
                )
                db.add(failure)
        row_latencies_ms.append((time.perf_counter() - row_t0) * 1000.0)

    # Update CsvImport record final status + metrics
    if imp:
        imp.total_rows = out.row_count
        imp.imported = out.imported
        imp.duplicates = out.duplicates
        imp.failed = out.errors
        imp.skipped_no_phone = out.skipped_no_phone
        imp.processing_completed_at = datetime.now(timezone.utc)
        dur = time.perf_counter() - started
        imp.duration_seconds = dur
        if dur > 0 and out.row_count > 0:
            imp.rows_per_second = out.row_count / dur
        else:
            imp.rows_per_second = None
        if out.row_count > 0:
            imp.failure_rate = out.errors / out.row_count
        else:
            imp.failure_rate = None
        attempt_ok = out.imported + out.duplicates + out.errors
        if attempt_ok > 0:
            imp.success_rate = (out.imported + out.duplicates) / attempt_ok
        else:
            imp.success_rate = None
        if row_latencies_ms:
            imp.avg_row_latency_ms = sum(row_latencies_ms) / len(row_latencies_ms)
        else:
            imp.avg_row_latency_ms = None

        if cancelled_break:
            imp.status = "cancelled"
        elif out.errors == 0 and out.skipped_no_phone == 0:
            imp.status = "completed"
        elif out.imported > 0 or out.duplicates > 0:
            imp.status = "partial"
        else:
            imp.status = "failed"

        db.commit()

    return out


def _processed_source_for_import(source: str) -> str:
    if source.endswith("_recovery") or source == "website":
        return source
    return f"{source}_recovery"


async def retry_csv_import_failed_rows(db: Session, import_id: int) -> CsvImportResult:
    """
    Re-process rows recorded in ``CsvImportFailure`` for an import (admin retry).
    Staggers Zoho sync the same way as the original CSV run.
    """
    imp = db.query(CsvImport).filter(CsvImport.id == import_id).first()
    if not imp:
        raise ValueError("Import not found")

    failures = (
        db.query(CsvImportFailure)
        .filter(CsvImportFailure.import_id == import_id)
        .order_by(CsvImportFailure.id.asc())
        .all()
    )
    if not failures:
        return CsvImportResult(import_id=import_id, row_count=0)

    processed_source = _processed_source_for_import(imp.source)
    out = CsvImportResult(row_count=len(failures), import_id=import_id)

    imp.status = "processing"
    imp.processing_started_at = datetime.now(timezone.utc)
    imp.processing_completed_at = None
    db.commit()

    extra_imported = 0
    extra_dup = 0
    t0 = time.perf_counter()
    latencies: List[float] = []
    cancelled_break = False

    for j, fail in enumerate(failures, start=1):
        st = db.query(CsvImport.status).filter(CsvImport.id == import_id).scalar()
        if st == "cancelled":
            cancelled_break = True
            break

        row = fail.row_data if isinstance(fail.row_data, dict) else {}
        if not row:
            latencies.append(0.0)
            continue

        fieldnames = list(row.keys())
        header_map = build_row_map(fieldnames)
        row_t0 = time.perf_counter()
        lc = row_to_lead_create(row, header_map)
        if not lc:
            fail.error_message = fail.error_message or "Missing or invalid phone number"
            db.commit()
            latencies.append((time.perf_counter() - row_t0) * 1000.0)
            continue

        try:
            result = await process_lead(
                db,
                lc,
                processed_source,
                raw_payload=lc.model_dump(),
                raise_on_failure=True,
                csv_import_stagger_index=j,
                sync_to_zoho=imp.sync_to_zoho,
                send_whatsapp=imp.send_whatsapp,
                trigger_ai=imp.trigger_ai,
            )
            if result is None:
                pass
            elif (result.reentry_count or 0) > 0:
                extra_dup += 1
                db.delete(fail)
            else:
                extra_imported += 1
                db.delete(fail)
            db.commit()
        except Exception as e:
            logger.error("Retry import {} row {}: {}", import_id, fail.row_index, e)
            fail.error_message = str(e)[:500]
            db.commit()
        latencies.append((time.perf_counter() - row_t0) * 1000.0)

    dur = time.perf_counter() - t0
    remaining_failures = (
        db.query(CsvImportFailure).filter(CsvImportFailure.import_id == import_id).count()
    )
    imp.imported = (imp.imported or 0) + extra_imported
    imp.duplicates = (imp.duplicates or 0) + extra_dup
    imp.failed = remaining_failures
    imp.processing_completed_at = datetime.now(timezone.utc)
    imp.duration_seconds = dur
    if dur > 0 and out.row_count > 0:
        imp.rows_per_second = out.row_count / dur
    else:
        imp.rows_per_second = None
    if out.row_count > 0:
        imp.failure_rate = remaining_failures / out.row_count
    else:
        imp.failure_rate = None
    retry_attempts = extra_imported + extra_dup + remaining_failures
    if retry_attempts > 0:
        imp.success_rate = (extra_imported + extra_dup) / retry_attempts
    else:
        imp.success_rate = None
    if latencies:
        imp.avg_row_latency_ms = sum(latencies) / len(latencies)
    else:
        imp.avg_row_latency_ms = None

    if cancelled_break:
        imp.status = "cancelled"
    elif remaining_failures == 0:
        imp.status = "completed" if (imp.imported or 0) > 0 or (imp.duplicates or 0) > 0 else "failed"
    elif extra_imported > 0 or extra_dup > 0:
        imp.status = "partial"
    else:
        imp.status = "failed"

    db.commit()

    out.imported = extra_imported
    out.duplicates = extra_dup
    out.errors = remaining_failures
    return out
