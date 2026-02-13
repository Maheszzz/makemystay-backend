import requests
import json

API_URL = "http://localhost:8000/api/v1/realty/properties"

properties = [
    {
        "property_name": "Connect coliving",
        "location": "Aecs layout",
        "starting_price": 8999.0,
        "property_type": "PG",
        "listing_type": "rent",
        "phone": "9999999999",
        "description": "Added via bulk script - 12/02/2026"
    },
    {
        "property_name": "PRO COLIVE PG",
        "location": "Hsr layout",
        "starting_price": 29999.0,
        "property_type": "PG",
        "listing_type": "rent",
        "phone": "9999999999",
        "description": "Added via bulk script - 12/02/2026"
    }
]

def add_properties():
    headers = {
        "Content-Type": "application/json"
    }
    
    success_count = 0
    
    for prop in properties:
        try:
            print(f"Adding {prop['property_name']}...")
            response = requests.post(API_URL, headers=headers, json=prop)
            
            if response.status_code in [200, 201]:
                print(f"✅ Success: {prop['property_name']}")
                success_count += 1
            else:
                print(f"❌ Failed: {prop['property_name']} - Status: {response.status_code}")
                print(response.text)
                
        except Exception as e:
            print(f"❌ Error adding {prop['property_name']}: {str(e)}")

    print(f"\nFinished. Successfully added {success_count}/{len(properties)} properties.")

if __name__ == "__main__":
    add_properties()
