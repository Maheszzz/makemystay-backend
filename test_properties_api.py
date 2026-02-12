import unittest
import urllib.request
import urllib.error
import json
import time

BASE_URL = "http://localhost:8000/api/v1"

class TestPropertiesAPI(unittest.TestCase):
    def setUp(self):
        self.created_property_id = None
        self.created_image_id = None

    def make_request(self, method, endpoint, data=None):
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if data:
            data_bytes = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
        else:
            req = urllib.request.Request(url, headers=headers, method=method)
            
        try:
            with urllib.request.urlopen(req) as response:
                if response.status == 204:
                    return None
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            print(f"\nRequest failed: {method} {url}")
            print(f"Status: {e.code}")
            print(f"Reason: {e.reason}")
            try:
                print(f"Response: {e.read().decode('utf-8')}")
            except:
                pass
            raise

    def test_lifecycle(self):
        print("\n--- Starting Property Lifecycle Test ---")

        # 1. Create Property
        print("\n1. Creating Property...")
        property_data = {
            "property_name": "Test Villa",
            "location": "Test Location, Bangalore",
            "phone": "9876543210",
            "property_type": "2BHK",
            "listing_type": "rent",
            "private_price": 10000.0,
            "description": "A beautiful test villa"
        }
        response = self.make_request("POST", "/realty/properties", property_data)
        self.assertIsNotNone(response.get("id"))
        self.property_id = response["id"]
        print(f"Created property with ID: {self.property_id}")

        # 2. Get Property
        print("\n2. Fetching Property...")
        response = self.make_request("GET", f"/realty/properties/{self.property_id}")
        self.assertEqual(response["property_name"], "Test Villa")
        self.assertEqual(response["location"], "Test Location, Bangalore")
        print("Property fetched successfully.")

        # 3. Update Property
        print("\n3. Updating Property...")
        update_data = {
            "property_name": "Updated Test Villa",
            "private_price": 12000.0
        }
        response = self.make_request("PUT", f"/realty/properties/{self.property_id}", update_data)
        self.assertEqual(response["property_name"], "Updated Test Villa")
        self.assertEqual(response["private_price"], 12000.0)
        print("Property updated successfully.")

        # 4. List Properties
        print("\n4. Listing Properties...")
        response = self.make_request("GET", "/realty/properties?limit=5")
        self.assertIsInstance(response, list)
        found = any(p["id"] == self.property_id for p in response)
        self.assertTrue(found)
        print(f"Listed {len(response)} properties. Found created property: {found}")

        # 5. Add Image
        print("\n5. Adding Property Image...")
        image_data = {
            "image_url": "http://example.com/image.jpg",
            "is_primary": True,
            "sort_order": 1
        }
        response = self.make_request("POST", f"/realty/properties/{self.property_id}/images", image_data)
        self.assertIsNotNone(response.get("id"))
        self.image_id = response["id"]
        print(f"Added image with ID: {self.image_id}")

        # 6. List Images
        print("\n6. Listing Property Images...")
        response = self.make_request("GET", f"/realty/properties/{self.property_id}/images")
        self.assertIsInstance(response, list)
        self.assertTrue(len(response) > 0)
        print(f"Found {len(response)} images.")

        # 7. Delete Image
        print("\n7. Deleting Property Image...")
        self.make_request("DELETE", f"/realty/images/{self.image_id}")
        # Verify deletion
        response = self.make_request("GET", f"/realty/properties/{self.property_id}/images")
        found = any(img["id"] == self.image_id for img in response)
        self.assertFalse(found)
        print("Image deleted successfully.")

        # 8. Delete Property
        print("\n8. Deleting Property...")
        self.make_request("DELETE", f"/realty/properties/{self.property_id}")
        
        # Verify deletion
        try:
            self.make_request("GET", f"/realty/properties/{self.property_id}")
            self.fail("Property should have been deleted")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)
        print("Property deleted successfully.")

if __name__ == "__main__":
    unittest.main()
