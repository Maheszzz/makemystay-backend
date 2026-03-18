import json
from typing import Any, Optional

from loguru import logger

from app.configs.db_config import MySQLSessionLocal
from app.models.lead_event import LeadEvent


def publish_event(lead_id: int, event_type: str, message: str, payload: Optional[Any] = None):
    """
    Publish an event for a lead. 
    Currently logs to database, but can be extended to Redis/Message Queues.
    """
    logger.info(f"Event published for Lead #{lead_id}: [{event_type}] {message}")

    with MySQLSessionLocal() as session:
        try:
            # Convert payload to JSON string if it's a dict or list
            payload_str = None
            if payload:
                if isinstance(payload, (dict, list)):
                    payload_str = json.dumps(payload)
                else:
                    payload_str = str(payload)

            new_event = LeadEvent(
                lead_id=lead_id,
                event_type=event_type,
                message=message,
                payload=payload_str
            )
            session.add(new_event)
            session.commit()
        except Exception as e:
            logger.error(f"Failed to log event for Lead #{lead_id}: {e}")
            session.rollback()
