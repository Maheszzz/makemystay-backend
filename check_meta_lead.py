from app.configs.db_config import SessionLocal
from app.models.lead import Lead
from app.models.agent import Agent
import json

def check_lead():
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.phone == "+919790341157").order_by(Lead.updated_at.desc()).first()
        if lead:
            print(f"Lead ID {lead.id}:")
            print(f"  Status: {lead.status}")
            print(f"  Property Type: {lead.property_type}")
            print(f"  Location: {lead.location}")
            print(f"  Assigned To Agent ID: {lead.assigned_to}")
            print(f"  Raw Payload: {json.dumps(lead.raw_payload) if lead.raw_payload else 'None'}")
        else:
            print("Lead not found")
    finally:
        db.close()

if __name__ == "__main__":
    check_lead()
