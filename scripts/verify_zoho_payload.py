import sys
import os
from unittest.mock import MagicMock

# Add app to path
sys.path.append(os.getcwd())

from app.utils.zoho_adapter import CRMLeadAdapter

def test_payload_generation():
    print("Testing Zoho CRM Payload Generation...")
    
    class MockLead:
        def __init__(self):
            self.name_ = "John Doe"
            self.phone = "9876543210"
            self.email = "john.doe@example.com"
            self.message = "Interested in 3BHK"
            self.location = "Bangalore"
            self.property_type = "Villa"
            self.units = "2"
            self.interested = True
            self.call_status = "completed"
            self.summary_budget = "5Cr"
            self.owner_zoho_id = "1234567890"
            self.lead_stage = "new"
            self.source = "housing"

    mock_lead = MockLead()

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
