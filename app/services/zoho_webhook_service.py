import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from loguru import logger
from sqlalchemy.orm import Session
from app.models.lead import Lead
from app.repo import lead as lead_repo

class ZohoWebhookService:
    """Service layer for normalizing Zoho CRM data and performing idempotent upserts on Leads."""
    
    def process_payload(self, db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Entry point for Processing Zoho Webhook payload with Elite observability."""
        start_time = datetime.now(timezone.utc)
        try:
            # 1. Normalize
            data = self.normalize_zoho_payload(payload)
            if not data.get("external_id"):
                return {"status": "error", "error": "Missing Zoho Lead ID (id/LEADID)"}

            # Capture event_type for audit
            event_type = payload.get("event_type", "lead_update")

            # 2. Upsert
            lead_id = self.upsert_lead(db, data)
            
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            return {
                "status": "success", 
                "lead_id": lead_id, 
                "event_type": event_type,
                "duration_ms": duration_ms
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def normalize_zoho_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Maps Zoho CRM JSON fields to our internal Lead model.
        
        Tailors to the expected keys from a Zoho CRM Workflow Webhook (JSON).
        """
        # Zoho payload typically has camelCase or Snake_Case depending on module custom fields
        return {
            "external_id": payload.get("id") or payload.get("LEADID"),
            "name": payload.get("Full_Name") or f"{payload.get('First_Name', '')} {payload.get('Last_Name', '')}".strip(),
            "phone": payload.get("Phone") or payload.get("Mobile"),
            "email": payload.get("Email"),
            "location": payload.get("City") or payload.get("Location"),
            "project_name": payload.get("Project_Name"),
            "source": payload.get("Lead_Source", "zoho_webhook"),
            "lead_stage": payload.get("Lead_Status", "new"),
            "sub_status": payload.get("Lead_Substatus"),
            "crm_status": "success", # To prevent batch sync loops
            "last_zoho_sync_at": datetime.now(timezone.utc)
        }

    def upsert_lead(self, db: Session, data: Dict[str, Any]) -> int:
        """Performs a safe, idempotent upsert of a lead based on Zoho ID."""
        external_id = data.get("external_id")
        
        # 1. Search by Zoho Lead ID (source of truth)
        lead = db.query(Lead).filter(Lead.zoho_lead_id == external_id).first()
        
        if not lead and data.get("phone"):
            # 2. Fallback search by phone to prevent duplicate record if ID was just assigned
            lead = db.query(Lead).filter(Lead.phone == data["phone"]).first()

        if lead:
            # Update existing lead with fresh CRM data
            for key, value in data.items():
                if key == "external_id":
                    lead.zoho_lead_id = value
                elif hasattr(lead, key):
                    setattr(lead, key, value)
            
            logger.info(f"Zoho Webhook: Updated existing Lead #{lead.id} from Zoho {external_id}")
            db.commit()
            return lead.id
        else:
            # Create new lead (rare, usually it's an update, but possible)
            # We map external_id to zoho_lead_id
            new_lead_data = {**data}
            new_lead_data["zoho_lead_id"] = new_lead_data.pop("external_id")
            
            new_lead = Lead(**new_lead_data)
            db.add(new_lead)
            db.commit()
            db.refresh(new_lead)
            
            logger.info(f"Zoho Webhook: Created NEW Lead #{new_lead.id} from Zoho {external_id}")
            return new_lead.id

zoho_webhook_service = ZohoWebhookService()
