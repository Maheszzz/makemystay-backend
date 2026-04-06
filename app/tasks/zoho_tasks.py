from datetime import datetime, timezone, timedelta
from loguru import logger
from app.configs.db_config import MySQLSessionLocal
from app.core.celery_app import celery_app
from app.models.lead import Lead
from app.models.zoho_webhook_event import ZohoWebhookEvent
from app.services.zoho_webhook_service import zoho_webhook_service

@celery_app.task(name="process_zoho_webhook_task", bind=True, max_retries=5)
def process_zoho_webhook_task(self, event_id: int) -> str:
    """Celery Task: Processes a logged Zoho webhook event.
    
    1. Fetches the event from the DB
    2. Normalizes the Zoho data to our internal Lead model
    3. Performs an idempotent upsert on the Lead
    4. Marks the event as 'processed'
    """
    db = MySQLSessionLocal()
    try:
        event = db.query(ZohoWebhookEvent).filter(ZohoWebhookEvent.id == event_id).first()
        if not event:
            logger.error(f"Zoho Webhook Task: Event ID {event_id} not found.")
            return "event_not_found"

        if event.status == "processed":
            return "already_processed"

        event.status = "processing"
        event.retry_count = self.request.retries
        db.commit()

        # Business Logic handled by service layer
        result = zoho_webhook_service.process_payload(db, event.payload)
        
        if result["status"] == "success":
            event.status = "processed"
            event.event_type = result.get("event_type")
            event.processing_time_ms = result.get("duration_ms")
            event.processed_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(f"Zoho Webhook Task: Success | event={event_id} | lead={result.get('lead_id')} | type={event.event_type} | time={event.processing_time_ms}ms")
            
            # Check for high-intent status to auto-convert to Deal (Conversion Engine)
            lead_id = result.get("lead_id")
            if lead_id:
                lead = db.query(Lead).get(lead_id)
                if lead and lead.lead_stage in {"Interested", "Qualified", "visit_scheduled"}:
                    convert_zoho_lead_to_deal_task.delay(lead.id)
            
            return "success"
        else:
            raise Exception(result.get("error", "Unknown error in service layer"))

    except Exception as e:
        db.rollback()
        error_msg = str(e)
        logger.error(f"Zoho Webhook Task: Failure | event={event_id} | retry={self.request.retries}/{self.max_retries} | error={error_msg}")
        
        if event:
            # Re-fetch to ensure session integrity
            event.status = "failed"
            event.error_log = error_msg
            db.commit()
            
        # Retry logic for transient failures (e.g., DB lock)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        
        return f"failed: {error_msg}"
    finally:
        db.close()

@celery_app.task(bind=True, max_retries=3)
def convert_zoho_lead_to_deal_task(self, lead_id: int):
    """Promotes a Zoho Lead to a Contact + Deal in Zoho CRM."""
    db = MySQLSessionLocal()
    try:
        lead = db.query(Lead).get(lead_id)
        if not lead or not lead.zoho_lead_id:
            return "skipped: no zoho_id"

        # 1. Convert Lead in Zoho
        deal_name = f"{lead.name} - {lead.project_name or 'New Interest'}"
        deal_data = {
            "Deal_Name": deal_name[:120],
            "Stage": "Qualification",
            "Amount": 0,
            "Closing_Date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            "Description": f"Auto-converted from Lead #{lead.id} focus: {lead.property_type or 'General'}"
        }

        from app.utils.zoho_crm_service import zoho_crm_service
        import asyncio
        loop = asyncio.get_event_loop()
        res = loop.run_until_complete(zoho_crm_service.convert_lead(lead.zoho_lead_id, deal_data))

        # 2. Update Lead status in Backend
        lead.status = "converted"
        lead.lead_stage = "converted"
        db.commit()
        
        # 3. Trigger WhatsApp Alert (Revenue Engine)
        try:
            from app.services.alert_service import alert_service
            alert_service.send_deal_created_alert(lead.name, lead.phone, lead.project_name)
        except Exception as wa_error:
            logger.error(f"Conversion Alert failed: {wa_error}")
        
        logger.info(f"Conversion Engine: Lead #{lead_id} converted to Deal successfully.")
        return "success"

    except Exception as e:
        db.rollback()
        logger.error(f"Conversion Engine: Failed to convert Lead #{lead_id}: {str(e)}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)
        return f"failed: {str(e)}"
    finally:
        db.close()
