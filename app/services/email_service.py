"""IMAP Email Ingestion Service."""

import email
import imaplib
import re
from email.header import decode_header
from typing import Optional

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


async def sync_emails_job():
    """Connects to IMAP, fetches unseen emails, parses and ingests them."""
    if not settings.IMAP_SERVER or not settings.IMAP_USERNAME:
        logger.debug("IMAP config missing. Skipping email ingestion.")
        return

    logger.info("Connecting to IMAP server for email ingestion...")
    mail = None
    try:
        mail = imaplib.IMAP4_SSL(settings.IMAP_SERVER, settings.IMAP_PORT)
        mail.login(settings.IMAP_USERNAME, settings.IMAP_PASSWORD)
        mail.select("inbox")

        # Search for unseen emails from housing or 99acres
        status, response = mail.search(None, '(UNSEEN OR FROM "housing.com" FROM "99acres.com")')
        if status != "OK":
            logger.error(f"Failed to search emails: {response}")
            return

        email_ids = response[0].split()
        if not email_ids:
            logger.debug("No new lead emails found.")
            return

        logger.info(f"Found {len(email_ids)} unseen lead emails.")

        db = MySQLSessionLocal()
        try:
            for e_id in email_ids:
                res, msg_data = mail.fetch(e_id, "(RFC822)")
                if res != "OK":
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])

                        from_header_raw = msg.get("From", "")
                        from_header_decoded = decode_header(from_header_raw)[0]
                        from_header = str(
                            from_header_decoded[0].decode(from_header_decoded[1] or "utf-8")
                            if isinstance(from_header_decoded[0], bytes)
                            else from_header_decoded[0]
                        )

                        text = _get_text_from_email(msg)
                        source = None
                        lead_data = None

                        if "housing.com" in from_header.lower():
                            source = "housing"
                            lead_data = parse_housing_email(text)
                        elif "99acres" in from_header.lower() or "99acres.com" in from_header.lower():
                            source = "99acres"
                            lead_data = parse_99acres_email(text)

                        if lead_data:
                            logger.info(f"Successfully parsed email lead from {source}: {lead_data.phone}")
                            await process_lead(
                                db,
                                lead_data,
                                source=source,
                                raw_payload={"email_body": text[:2000], "subject": msg.get("Subject", "")},
                            )
                        else:
                            logger.warning(f"Could not parse lead data from email sent by: {from_header}")

            # Note: The emails are implicitly marked as \Seen when fetched unless (BODY.PEEK) is used.
            db.commit()
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error during IMAP email sync: {e}")
    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except Exception as logout_err:
                logger.debug(f"IMAP logout error: {logout_err}")
