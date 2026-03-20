import json
from typing import Any, Optional

from loguru import logger
from datetime import datetime

from app.configs.db_config import MySQLSessionLocal
from app.models.lead_event import LeadEvent
from app.core.redis import redis_conn, ADMIN_CHANNEL


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
            
            # Broadcast the event real-time to connected WebSocket Dashboards
            if redis_conn:
                try:
                    parsed_payload = payload
                    if isinstance(payload_str, str) and (payload_str.startswith("{") or payload_str.startswith("[")):
                        try:
                            parsed_payload = json.loads(payload_str)
                        except json.JSONDecodeError:
                            parsed_payload = payload_str

                    pub_data = {
                        "type": event_type,
                        "priority": "high" if "HOT" in event_type or "ASSIGNED" in event_type else "normal",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "data": {
                            "id": new_event.id,
                            "lead_id": lead_id,
                            "message": message,
                            "details": parsed_payload
                        }
                    }
                    redis_conn.publish(ADMIN_CHANNEL, json.dumps(pub_data))
                except Exception as redis_err:
                    logger.error(f"Failed to publish to redis: {redis_err}")
                    
        except Exception as e:
            logger.error(f"Failed to log event for Lead #{lead_id}: {e}")
            session.rollback()
