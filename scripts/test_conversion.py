import asyncio
import json
from datetime import datetime, timezone
from loguru import logger
from app.configs.db_config import MySQLSessionLocal
from app.models.lead import Lead
from app.utils.zoho_adapter import CRMLeadAdapter, classify_lead
from app.services.zoho_webhook_service import zoho_webhook_service
from app.tasks.zoho_tasks import convert_zoho_lead_to_deal_task

async def test_conversion_flow():
    db = MySQLSessionLocal()
    try:
        # 1. Test Classification
        mock_data = {
            "message": "I am very interested and want a site visit tomorrow",
            "source": "housing"
        }
        category = classify_lead(mock_data)
        print(f"Classification Test: {category} (Expected: Hot Lead or Warm Lead)")

        # 2. Test Adapter Mapping
        lead = Lead(
            name="Test User",
            phone="+919999999999",
            project_name="Pride Enclave",
            lead_stage="Interested",
            zoho_lead_id="test_zoho_id_123"
        )
        adapter = CRMLeadAdapter(lead, "housing")
        payload = adapter.to_zoho_payload()
        print(f"Adapter Payload: {json.dumps(payload, indent=2)}")

        # 3. Test Webhook Normalization
        mock_webhook = {
            "id": "123456789",
            "Full_Name": "Zoho Webhook Lead",
            "Phone": "9876543210",
            "Lead_Status": "Interested",
            "Project_Name": "Green Valley"
        }
        normalized = zoho_webhook_service.normalize_zoho_payload(mock_webhook)
        print(f"Normalized Payload: {json.dumps(normalized, indent=2)}")
        
        if normalized["lead_stage"] == "Interested":
            print("✅ Webhook correctly captured high-intent status.")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_conversion_flow())
