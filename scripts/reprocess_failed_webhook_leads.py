#!/usr/bin/env python3
"""Reprocess `failed_webhook_leads` rows (99acres XML fragments) after adapter fixes.

Run from repo root:
  cd no-broker-backend && PYTHONPATH=. python scripts/reprocess_failed_webhook_leads.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import xml.etree.ElementTree as ET

from loguru import logger

from app.adapters.acers_adapter import AcersAdapter
from app.configs.db_config import MySQLSessionLocal
from app.repo.failed_webhook_lead_repo import list_unprocessed, mark_processed
from app.services.lead_processor import process_lead


def main() -> None:
    db = MySQLSessionLocal()
    try:
        rows = list_unprocessed(db, limit=5000)
        logger.info("Reprocessing {} failed_webhook_lead row(s)", len(rows))
        ok = 0
        for row in rows:
            if row.source != "99acres":
                logger.warning("skip id={} source={}", row.id, row.source)
                continue
            try:
                qry = ET.fromstring(row.payload.strip())
            except ET.ParseError as e:
                logger.error("id={} invalid XML: {}", row.id, e)
                continue
            lead = AcersAdapter.to_lead_create(qry)
            if not lead:
                logger.warning("id={} still unmapped (no valid phone)", row.id)
                continue
            try:
                asyncio.run(
                    process_lead(db, lead, "99acres", raw_payload=lead.model_dump())
                )
                mark_processed(db, row.id)
                ok += 1
                logger.info("reprocessed failed_webhook_lead id={}", row.id)
            except Exception as e:
                logger.error("id={} process_lead failed: {}", row.id, e)
        logger.info("Done. Successfully reprocessed {} row(s).", ok)
    finally:
        db.close()


if __name__ == "__main__":
    main()
