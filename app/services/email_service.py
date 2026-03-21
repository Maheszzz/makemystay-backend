"""IMAP Email Ingestion Service."""

import email
import imaplib
import re
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Optional

from loguru import logger

from app.configs.db_config import MySQLSessionLocal
from app.core.config import settings
from app.schemas.lead import LeadCreate
from app.services.lead_processor import process_lead


def _get_text_from_email(msg) -> str:
    """Extracts text content from an email message."""
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type in ["text/plain", "text/html"] and "attachment" not in content_disposition:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        text += payload.decode(charset, errors="replace")
                except Exception as e:
                    logger.warning(f"Failed to decode email part: {e}")
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
        except Exception as e:
            logger.warning(f"Failed to decode email body: {e}")

    # If it looks like HTML, strip tags
    if "<html" in text.lower() or "<body" in text.lower() or "<table" in text.lower():
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(text, "html.parser")
            text = soup.get_text(separator="\n")
        except ImportError:
            # Basic fallback if bs4 is not installed
            text = re.sub(r"<[^>]+>", "\n", text)
            text = "\n".join([line.strip() for line in text.split("\n") if line.strip()])

    # Explicit Hardening
    text = re.sub(r"(?i)<script.*?>.*?</script>", "", text, flags=re.DOTALL)
    text = text[:10000]  # Hard max 10KB to prevent memory bomb regex evaluating

    return text


def _decode_mime_header(value: str) -> str:
    """Decode MIME-encoded email headers safely."""
    if not value:
        return ""
    decoded_parts = decode_header(value)
    chunks = []
    for raw, charset in decoded_parts:
        try:
            if isinstance(raw, bytes):
                chunks.append(raw.decode(charset or "utf-8", errors="replace"))
            else:
                chunks.append(str(raw))
        except Exception:
            chunks.append(str(raw))
    return "".join(chunks)


def _detect_lead_source(from_header: str, subject: str, text: str) -> Optional[str]:
    """Infer lead source from sender, subject and body text."""
    haystack = f"{from_header}\n{subject}\n{text[:2000]}".lower()
    if "housing.com" in haystack or "pahal.housing.com" in haystack:
        return "housing"
    if "99acres" in haystack or "99acres.com" in haystack:
        return "99acres"
    return None


def _extract_lead_epoch(msg) -> Optional[int]:
    """Parse email Date header to epoch seconds (UTC)."""
    raw_date = msg.get("Date", "")
    if not raw_date:
        return None
    try:
        dt = parsedate_to_datetime(raw_date)
        if dt is None:
            return None
        return int(dt.timestamp())
    except Exception:
        return None


def parse_housing_email(text: str) -> Optional[LeadCreate]:
    """Parse Housing.com lead email."""
    # Matches labels followed by colon and some spacing
    name_match = re.search(r"(?i)name[\s:]+([^\n]+)", text)
    phone_match = re.search(r"(?i)(?:phone|mobile|contact)[\s:]+([\+\d\-\s]+)", text)
    email_match = re.search(r"(?i)email[\s:]+([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
    project_match = re.search(r"(?i)(?:project|property|looking for)[\s:]+([^\n]+)", text)

    phone = phone_match.group(1).strip() if phone_match else None
    if not phone or len(re.sub(r"\D", "", phone)) < 7:
        return None

    return LeadCreate(
        name=name_match.group(1).strip() if name_match else None,
        phone=re.sub(r"[^\+\d]", "", phone),
        email=email_match.group(1).strip() if email_match else None,
        project_name=project_match.group(1).strip() if project_match else None,
    )


def parse_99acres_email(text: str) -> Optional[LeadCreate]:
    """Parse 99acres lead email."""
    # Similar structure handling
    name_match = re.search(r"(?i)name[\s:]+([^\n]+)", text)
    phone_match = re.search(r"(?i)(?:phone|mobile|contact|contact number)[\s:]+([\+\d\-\s]+)", text)
    email_match = re.search(r"(?i)email[\s:]+([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
    project_match = re.search(r"(?i)(?:project|property|interested in)[\s:]+([^\n]+)", text)

    phone = phone_match.group(1).strip() if phone_match else None
    if not phone or len(re.sub(r"\D", "", phone)) < 7:
        return None

    return LeadCreate(
        name=name_match.group(1).strip() if name_match else None,
        phone=re.sub(r"[^\+\d]", "", phone),
        email=email_match.group(1).strip() if email_match else None,
        project_name=project_match.group(1).strip() if project_match else None,
    )


async def sync_emails_job() -> Dict[str, Any]:
    """Connect to IMAP, parse unseen lead emails and return a sync summary."""
    summary: Dict[str, Any] = {
        "status": "ok",
        "fetched": 0,
        "processed": 0,
        "imported": 0,
        "skipped": 0,
        "errors": 0,
    }
    if not settings.IMAP_SERVER or not settings.IMAP_USERNAME:
        logger.debug("IMAP config missing. Skipping email ingestion.")
        summary["status"] = "skipped"
        summary["message"] = "IMAP config missing"
        return summary

    logger.info("Connecting to IMAP server for email ingestion...")
    mail = None
    try:
        mail = imaplib.IMAP4_SSL(settings.IMAP_SERVER, settings.IMAP_PORT)
        mail.login(settings.IMAP_USERNAME, settings.IMAP_PASSWORD)
        mail.select("inbox")

        # IMAP search syntax is limited; query unseen first, then filter in-app.
        status, response = mail.search(None, "UNSEEN")
        if status != "OK":
            logger.error(f"Failed to search emails: {response}")
            summary["status"] = "error"
            summary["errors"] += 1
            summary["message"] = "Failed to search inbox"
            return summary

        email_ids = response[0].split()
        summary["fetched"] = len(email_ids)
        if not email_ids:
            logger.debug("No new lead emails found.")
            return summary

        logger.info(f"Found {len(email_ids)} unseen lead emails.")

        db = MySQLSessionLocal()
        try:
            for e_id in email_ids:
                res, msg_data = mail.fetch(e_id, "(RFC822)")
                if res != "OK":
                    summary["errors"] += 1
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        summary["processed"] += 1
                        msg = email.message_from_bytes(response_part[1])

                        from_header = _decode_mime_header(msg.get("From", ""))
                        subject = _decode_mime_header(msg.get("Subject", ""))

                        text = _get_text_from_email(msg)
                        source = _detect_lead_source(from_header, subject, text)
                        if source is None:
                            logger.debug(
                                "Skipping unseen email (not housing/99acres): "
                                f"from={from_header!r}, subject={subject!r}"
                            )
                            summary["skipped"] += 1
                            continue

                        lead_data = (
                            parse_housing_email(text) if source == "housing" else parse_99acres_email(text)
                        )
                        lead_epoch = _extract_lead_epoch(msg)
                        message_id = (msg.get("Message-ID") or "").strip("<> ")
                        if lead_data and lead_epoch:
                            lead_data.lead_date = lead_epoch
                        if lead_data and message_id:
                            lead_data.external_id = f"email:{message_id}"

                        if lead_data:
                            logger.info(f"Successfully parsed email lead from {source}: {lead_data.phone}")
                            created = await process_lead(
                                db,
                                lead_data,
                                source=source,
                                raw_payload={
                                    "email_body": text[:2000],
                                    "subject": subject,
                                    "from": from_header,
                                    "message_id": message_id or None,
                                },
                            )
                            if created:
                                summary["imported"] += 1
                            else:
                                summary["skipped"] += 1
                        else:
                            logger.warning(
                                f"Could not parse lead data from {source} email: "
                                f"from={from_header!r}, subject={subject!r}"
                            )
                            summary["skipped"] += 1

            # Note: The emails are implicitly marked as \Seen when fetched unless (BODY.PEEK) is used.
            db.commit()
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error during IMAP email sync: {e}")
        summary["status"] = "error"
        summary["errors"] += 1
        summary["message"] = str(e)
    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except Exception as logout_err:
                logger.debug(f"IMAP logout error: {logout_err}")
    return summary
