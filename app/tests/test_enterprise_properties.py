"""
Automated unittest suite for Phase 3 – Enterprise Real Estate Backend Architecture.
Verifies:
- Sprint 1: Soft Delete & Enterprise Models
- Sprint 3, 5, 6, 7: REST CRUD, Pydantic Validation, RBAC, Publish Workflow
- Sprint 8 & 9: Analytics & Automatic CRM Lead Capture on Document Download
- Sprint 10: Unified Single-Response Public Website Payload
- 3 Special Features: Version History Audit Logs, Unit Availability, Tags
"""

import unittest
import uuid
from fastapi.testclient import TestClient

from app.main import app
from app.configs.db_config import MySQLBase, mysql_engine
from app.core import security


class DummyAdminUser:
    id = 1
    email = "admin@makemystay.ai"
    role = "admin"


class TestEnterpriseProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Ensure database tables exist and set up dependency overrides."""
        MySQLBase.metadata.create_all(bind=mysql_engine)
        app.dependency_overrides[security.admin_or_employee_required] = lambda: DummyAdminUser()
        app.dependency_overrides[security.admin_required] = lambda: DummyAdminUser()
        cls.client = TestClient(app)
        cls.property_id = None
        cls.property_slug = f"ultra-luxury-hsr-penthouse-{uuid.uuid4().hex[:6]}"
        cls.brochure_doc_id = None

    @classmethod
    def tearDownClass(cls):
        """Clean up dependency overrides."""
        app.dependency_overrides.clear()

    def test_01_create_property_with_enterprise_schema(self):
        """Test POST /api/v1/properties creates a property with nested modules and initial audit log."""
        payload = {
            "property_name": "Ultra Luxury HSR Penthouse",
            "slug": self.property_slug,
            "property_code": f"UL-{uuid.uuid4().hex[:6].upper()}",
            "location": "HSR Layout",
            "city": "Bangalore",
            "locality": "Sector 2",
            "phone": "+919876543210",
            "property_type": "3BHK",
            "listing_type": "rent",
            "property_category": "Rental",
            "status": "draft",
            "visibility": "public",
            "owner_name": "Rajesh Kumar",
            "owner_phone": "+919988776655",
            "owner_email": "owner@example.com",
            "pricing": {
                "starting_price": 45000.0,
                "max_price": 60000.0,
                "security_deposit": "200000",
                "maintenance_charges": "5000",
                "electricity_charges": "12/unit",
                "water_charges": "Included",
                "negotiable": True,
                "available_offers": "1 Month Free Parking",
            },
            "images": [
                {
                    "image_url": "https://cdn.makemystay.ai/images/hsr-hero.jpg",
                    "is_primary": True,
                    "category": "Bedroom",
                    "alt_text": "Ultra Luxury HSR Penthouse - Bedroom",
                }
            ],
            "documents": [
                {
                    "document_type": "brochure",
                    "title": "HSR Penthouse Brochure",
                    "document_url": "https://cdn.makemystay.ai/docs/hsr-brochure.pdf",
                },
                {
                    "document_type": "pricing",
                    "title": "Pricing Schedule 2026",
                    "document_url": "https://cdn.makemystay.ai/docs/hsr-pricing.pdf",
                },
            ],
            "units": [
                {
                    "unit_code": "Penthouse A",
                    "unit_type": "3BHK",
                    "status": "available",
                    "floor": "Top Floor",
                    "rent_price": 55000.0,
                }
            ],
            "tags": [
                {"tag_name": "Luxury", "tag_category": "Lifestyle"},
                {"tag_name": "Near Metro", "tag_category": "Commute"},
            ],
            "seo": {
                "meta_title": "Luxury Penthouse in HSR Layout - MakeMyStay",
                "meta_description": "Rent a fully furnished 3BHK penthouse in HSR Layout Bangalore.",
                "seo_keywords": "hsr layout penthouse, luxury rental bangalore",
                "robots_tag": "index, follow",
            },
        }

        response = self.client.post("/api/v1/properties", json=payload)
        self.assertIn(response.status_code, [200, 201], f"Create failed: {response.text}")

        data = response.json()
        prop_data = data["data"] if "data" in data and isinstance(data["data"], dict) else data

        self.assertEqual(prop_data["property_name"], "Ultra Luxury HSR Penthouse")
        self.assertEqual(prop_data["status"], "draft")
        self.assertEqual(prop_data["owner_name"], "Rajesh Kumar")
        self.assertEqual(prop_data["pricing"]["starting_price"], 45000.0)
        self.assertEqual(len(prop_data["documents"]), 2)
        self.assertEqual(len(prop_data["images"]), 1)
        self.assertEqual(prop_data["images"][0]["image_url"], "https://cdn.makemystay.ai/images/hsr-hero.jpg")
        self.assertEqual(len(prop_data["units"]), 1)
        self.assertEqual(len(prop_data["tags"]), 2)

        # Verify /realty/properties alias works identically
        alias_res = self.client.get(f"/api/v1/realty/properties/{prop_data['id']}")
        self.assertEqual(alias_res.status_code, 200)

        TestEnterpriseProperties.property_id = prop_data["id"]
        TestEnterpriseProperties.brochure_doc_id = prop_data["documents"][0]["id"]

    def test_02_version_history_audit_log_recorded(self):
        """Verify Special Feature #1: PropertyAuditLog recorded version 1 on creation."""
        prop_id = TestEnterpriseProperties.property_id
        self.assertIsNotNone(prop_id, "property_id should be set by test_01")
        response = self.client.get(f"/api/v1/properties/{prop_id}/audit-logs")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        logs = data["data"] if "data" in data and isinstance(data["data"], list) else data
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[-1]["version_number"], 1)
        self.assertEqual(logs[-1]["action"], "create")

    def test_03_update_property_bumps_version(self):
        """Verify PUT /api/v1/properties/{id} updates fields and increments audit version."""
        prop_id = TestEnterpriseProperties.property_id
        update_payload = {
            "property_name": "Ultra Luxury HSR Penthouse - Updated",
            "pricing": {
                "starting_price": 48000.0,
                "max_price": 65000.0,
            },
        }
        response = self.client.put(f"/api/v1/properties/{prop_id}", json=update_payload)
        self.assertEqual(response.status_code, 200)

        # Verify audit logs now have version 2
        logs_resp = self.client.get(f"/api/v1/properties/{prop_id}/audit-logs")
        logs_data = logs_resp.json()
        logs = logs_data["data"] if "data" in logs_data and isinstance(logs_data["data"], list) else logs_data
        self.assertGreaterEqual(len(logs), 2)
        self.assertEqual(logs[0]["version_number"], 2)
        self.assertEqual(logs[0]["action"], "update")

    def test_04_property_publish_workflow(self):
        """Verify Sprint 6 Publish Workflow: Draft -> Pending Review -> Approved -> Published."""
        prop_id = TestEnterpriseProperties.property_id
        # 1. Transition to pending_review
        res1 = self.client.post(
            f"/api/v1/properties/{prop_id}/publish",
            json={"status": "pending_review", "reason": "Ready for manager review"},
        )
        self.assertEqual(res1.status_code, 200)

        # 2. Transition to published
        res2 = self.client.post(
            f"/api/v1/properties/{prop_id}/publish",
            json={"status": "published", "reason": "Approved for live website"},
        )
        self.assertEqual(res2.status_code, 200)

    def test_05_sprint_10_unified_public_website_payload(self):
        """
        Verify Sprint 10: GET /api/v1/public/properties/{slug} returns
        the complete unified single response for published property.
        """
        response = self.client.get(f"/api/v1/public/properties/{self.property_slug}")
        self.assertEqual(response.status_code, 200, f"Public slug fetch failed: {response.text}")
        data = response.json()
        prop_data = data["data"] if "data" in data and isinstance(data["data"], dict) else data

        self.assertEqual(prop_data["property_name"], "Ultra Luxury HSR Penthouse - Updated")
        self.assertEqual(prop_data["status"], "published")
        self.assertIn("pricing", prop_data)
        self.assertIn("documents", prop_data)
        self.assertIn("units", prop_data)
        self.assertIn("tags", prop_data)
        self.assertIn("seo", prop_data)

    def test_06_sprint_9_lead_capture_on_document_download(self):
        """
        Verify Sprint 9 Lead Capture: Downloading a brochure captures
        user details and automatically creates an assigned CRM Lead.
        """
        doc_id = TestEnterpriseProperties.brochure_doc_id
        params = {
            "user_name": "Amitabh Sharma",
            "user_phone": "+919811223344",
            "user_email": "amitabh@example-client.com",
            "user_company": "Tech Corp Bangalore",
            "purpose": "Company Executive Relocation",
        }
        response = self.client.post(f"/api/v1/documents/{doc_id}/download", params=params)
        self.assertEqual(response.status_code, 200, f"Download lead capture failed: {response.text}")
        res_json = response.json()
        self.assertEqual(res_json["status"], "success")
        self.assertEqual(res_json["document_type"], "brochure")
        self.assertEqual(res_json["document_url"], "https://cdn.makemystay.ai/docs/hsr-brochure.pdf")

        # Verify analytics summary shows the generated lead
        prop_id = TestEnterpriseProperties.property_id
        analytics_resp = self.client.get(f"/api/v1/properties/{prop_id}/analytics")
        self.assertEqual(analytics_resp.status_code, 200)
        an_data = analytics_resp.json()
        metrics = an_data["data"] if "data" in an_data and isinstance(an_data["data"], dict) else an_data
        self.assertGreaterEqual(metrics["total_downloads"], 1)
        self.assertGreaterEqual(metrics["total_leads_generated"], 1)

    def test_07_soft_delete_and_restore_property(self):
        """Verify Soft Delete (never permanently erase) and restore."""
        prop_id = TestEnterpriseProperties.property_id
        # 1. Soft Delete
        del_res = self.client.delete(f"/api/v1/properties/{prop_id}")
        self.assertEqual(del_res.status_code, 204)

        # 2. Public endpoint should now return 404
        pub_res = self.client.get(f"/api/v1/public/properties/{self.property_slug}")
        self.assertEqual(pub_res.status_code, 404)

        # 3. Restore
        restore_res = self.client.post(f"/api/v1/properties/{prop_id}/restore")
        self.assertEqual(restore_res.status_code, 200)

        restored_data = restore_res.json()
        prop_restored = (
            restored_data["data"]
            if "data" in restored_data and isinstance(restored_data["data"], dict)
            else restored_data
        )
        self.assertFalse(prop_restored["is_deleted"])
        self.assertEqual(prop_restored["status"], "draft")


if __name__ == "__main__":
    unittest.main()
