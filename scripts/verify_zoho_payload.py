import sys
import os
from unittest.mock import MagicMock

# Add app to path
sys.path.append(os.getcwd())

from app.utils.zoho_adapter import CRMLeadAdapter

def test_payload_generation():
    print("Testing Zoho CRM Payload Generation...")
    
    # Mock lead with AI tags and owner ID
    mock_lead = MagicMock()
    mock_lead.name_ = "John Doe"
    mock_lead.phone = "9876543210"
    mock_lead.email = "john.doe@example.com"
    mock_lead.message = "Interested in 3BHK"
    mock_lead.location = "Bangalore"
    mock_lead.property_type = "Villa"
    mock_lead.units = "2"
    
    # AI Tags
    mock_lead.interested = True
    mock_lead.call_status = "completed"
    mock_lead.summary_budget = "5Cr"
    
    # Owner mapping
    mock_lead.owner_zoho_id = "1234567890"

    adapter = CRMLeadAdapter(mock_lead, "housing")
    payload = adapter.to_zoho_payload()
    
    print("\nGenerated Payload:")
    import json
    print(json.dumps(payload, indent=4))
    
    # Assertions for sanity
    assert payload["First_Name"] == "John"
    assert payload["Last_Name"] == "Doe"
    assert payload["AI_Interested"] is True
    assert payload["AI_Call_Status"] == "completed"
    assert payload["AI_Budget"] == "5Cr"
    assert payload["Owner"]["id"] == "1234567890"
    
    print("\nSanity Check: SUCCESS")

if __name__ == "__main__":
    test_payload_generation()
