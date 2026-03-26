"""Shared CSV → lead pipeline for CLI and admin API (same column mapping as ``import_leads_csv``)."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.schemas.lead import LeadCreate
from app.services.lead_processor import process_lead
from app.utils.phone_normalize import normalize_to_indian_mobile_10

# Map logical field -> list of CSV header names to try (lowercase compared).
COLUMN_ALIASES: Dict[str, List[str]] = {
    "phone": [
        "mobile",
        "phone",
        "phone1",
        "contact number",
        "contactnumber",
        "tel",
        "mobile number",
        "phonenumber",
        "phone number",
    ],
    "name": ["name", "customer name", "lead name", "full name", "fullname"],
    "email": ["email", "e-mail", "mail id"],
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
    phone = normalize_to_indian_mobile_10(raw_phone) if raw_phone else None
    if not phone:
        return None
    name = _get(row, header_map, "name") or "User"
    email = _get(row, header_map, "email") or None
    if email == "":
        email = None
    city = _get(row, header_map, "city") or None
    location = _get(row, header_map, "location") or None
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
    imported: int = 0
    duplicates: int = 0
    skipped_no_phone: int = 0
    skipped_empty: int = 0
    errors: int = 0
    row_count: int = 0
    error_samples: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
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


async def run_csv_import(
    db: Session,
    text: str,
    source: str,
    *,
    dry_run: bool = False,
    skip_rows: int = 0,
    max_rows: int = 5000,
) -> CsvImportResult:
    """
    Import leads from CSV text. Uses ``process_lead`` (dedup, Zoho queue, etc.).
    """
    rows, header_map = parse_csv_text(text)
    if skip_rows:
        rows = rows[skip_rows:]
    if len(rows) > max_rows:
        raise ValueError(f"Too many rows ({len(rows)}); maximum is {max_rows}")

    out = CsvImportResult(row_count=len(rows))

    for i, row in enumerate(rows, start=1):
        if _row_is_effectively_empty(row):
            out.skipped_empty += 1
            continue
        lc = row_to_lead_create(row, header_map)
        if not lc:
            logger.warning("Row {}: no valid phone — {}", i, row)
            out.skipped_no_phone += 1
            continue
        if dry_run:
            logger.info("DRY RUN row {}: {} → {}", i, lc.phone, lc.name)
            out.imported += 1
            continue
        try:
            result = await process_lead(
                db,
                lc,
                source,
                raw_payload=lc.model_dump(),
                raise_on_failure=True,
            )
            if result is None:
                out.duplicates += 1
                logger.debug("Row {}: duplicate or skipped", i)
            else:
                out.imported += 1
                logger.info("Row {}: lead id {}", i, result.id)
        except Exception as e:
            out.errors += 1
            logger.error("Row {}: {}", i, e)
            _append_error_sample(out.error_samples, f"Row {i}: {e!s}")

    return out
