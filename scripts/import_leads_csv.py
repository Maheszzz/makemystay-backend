#!/usr/bin/env python3
"""Import leads from a CSV (e.g. 99acres export) into MySQL via the normal lead pipeline.

Uses ``app.services.csv_lead_import`` (same path as webhooks and admin upload).

Usage::

    cd no-broker-backend
    PYTHONPATH=. python scripts/import_leads_csv.py /path/to/leads.csv

Options::

    --source 99acres     Source label stored on ``leads.source`` (default: 99acres)
    --dry-run            Print what would be imported without writing to DB
    --skip-rows N        Skip first N data rows (after header), default 0

Column names are matched case-insensitively. Expected (any subset):

- **Phone (required):** Mobile, Phone, Phone1, Contact Number, Tel, etc.
- **Optional:** Name, Email, City, Location, Budget, Message, QryId / Lead Id / External Id

If your CSV uses different headers, edit ``COLUMN_ALIASES`` in
``app/services/csv_lead_import.py`` or add a header row in Excel and re-export.

Examples::

    PYTHONPATH=. python scripts/import_leads_csv.py ~/Downloads/99acres_leads.csv
    PYTHONPATH=. python scripts/import_leads_csv.py ./data.csv --dry-run
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

from app.configs.db_config import MySQLSessionLocal
from app.services.csv_lead_import import run_csv_import


def main() -> None:
    parser = argparse.ArgumentParser(description="Import leads from CSV")
    parser.add_argument("csv_path", type=Path, help="Path to CSV file")
    parser.add_argument("--source", default="99acres", help="leads.source value")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    parser.add_argument("--skip-rows", type=int, default=0, help="Skip N data rows after header")
    args = parser.parse_args()

    path = args.csv_path.expanduser()
    if not path.is_file():
        logger.error("File not found: {}", path)
        sys.exit(1)

    text = path.read_text(encoding="utf-8-sig")

    db = MySQLSessionLocal()
    try:

        async def _run():
            return await run_csv_import(
                db,
                text,
                args.source,
                dry_run=args.dry_run,
                skip_rows=args.skip_rows,
                max_rows=5000,
            )

        result = asyncio.run(_run())
    except ValueError as e:
        logger.error("{}", e)
        sys.exit(1)
    finally:
        db.close()

    logger.info(
        "Done. imported={} duplicates={} no_phone={} empty={} errors={} rows={} dry_run={}",
        result.imported,
        result.duplicates,
        result.skipped_no_phone,
        result.skipped_empty,
        result.errors,
        result.row_count,
        args.dry_run,
    )


if __name__ == "__main__":
    main()
