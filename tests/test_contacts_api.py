"""
Tests for the MakeMyStay contact endpoint and CRM integration.

Verifies:
1. Successful contact creation (201 Created, DB persistence, background task queued).
2. Input validation failures return HTTP 422 (not HTTP 200).
3. Database errors return HTTP 500 (not HTTP 200).
4. Unhandled server errors return HTTP 500 (not HTTP 200).
5. In-house CRM webhook push behavior (success, network failure, HTTP 500, unconfigured).
6. Complete elimination of obsolete `app.services.contact_notifications` import references.
"""

import ast
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.configs.db_config import MySQLBase, get_mysql_db
from app.core.config import settings
from app.main import app
from app.models.realty import Contact
from app.services.crm_contact import push_contact_to_crm

# Use SQLite in-memory database for fully isolated, offline testing
_sqlite_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_sqlite_engine)


def _override_get_mysql_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


class TestContactsAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create tables on the in-memory SQLite database
        MySQLBase.metadata.create_all(bind=_sqlite_engine)
        app.dependency_overrides[get_mysql_db] = _override_get_mysql_db
        cls.client = TestClient(app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def setUp(self):
        # Clean contacts table between tests
        db = _TestSession()
        db.query(Contact).delete()
        db.commit()
        db.close()

    def test_create_contact_success(self):
        """Valid contact submission returns HTTP 201 with standardized response."""
        payload = {
            "name": "Arun Kumar",
            "phone": "9876543210",
            "email": "arun.kumar@example.com",
            "message": "Interested in 2BHK luxury apartments in Whitefield",
            "location": "Whitefield, Bangalore",
            "property_type": "Apartment",
            "status": "new",
        }

        with patch("app.api.realty.push_contact_to_crm") as mock_crm_push:
            response = self.client.post("/api/v1/realty/contacts", json=payload)

        self.assertEqual(response.status_code, 201)
        body = response.json()
        contact_data = body.get("data") if (isinstance(body, dict) and "data" in body and body["data"] is not None) else body
        self.assertIsNotNone(contact_data)
        name_val = contact_data.get("name_") or contact_data.get("name")
        self.assertEqual(name_val, "Arun Kumar")
        self.assertEqual(contact_data.get("phone"), "9876543210")
        self.assertEqual(contact_data.get("email"), "arun.kumar@example.com")
        self.assertIn("id", contact_data)

        # Verify DB persistence
        db = _TestSession()
        saved = db.query(Contact).filter(Contact.phone == "9876543210").first()
        self.assertIsNotNone(saved)
        self.assertEqual(saved.name_, "Arun Kumar")
        self.assertEqual(saved.email, "arun.kumar@example.com")
        db.close()

        # Verify background CRM task was queued
        mock_crm_push.assert_called_once()
        args, _ = mock_crm_push.call_args
        self.assertEqual(args[0]["name_"], "Arun Kumar")
        self.assertEqual(args[1], saved.id)

    def test_create_contact_validation_failure_returns_422(self):
        """Invalid phone/email must return HTTP 422 Unprocessable Entity, NOT 200."""
        # Phone not matching 10-digit Indian mobile pattern
        payload = {
            "name": "Invalid Phone",
            "phone": "12345",
            "email": "invalid@example.com",
            "message": "Testing validation",
        }
        response = self.client.post("/api/v1/realty/contacts", json=payload)
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertFalse(body.get("success"))
        self.assertIsNotNone(body.get("error"))

    def test_create_contact_missing_fields_returns_422(self):
        """Missing required message/email must return HTTP 422, NOT 200."""
        payload = {
            "name": "Missing Fields",
            "phone": "9876543210",
        }
        response = self.client.post("/api/v1/realty/contacts", json=payload)
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertFalse(body.get("success"))

    def test_create_contact_database_error_returns_500(self):
        """Database errors must return HTTP 500 Internal Server Error, NOT 200."""
        payload = {
            "name": "DB Error Test",
            "phone": "9876543210",
            "email": "dberror@example.com",
            "message": "Testing DB failure handling",
        }

        with patch("app.repo.realty.create_contact", side_effect=SQLAlchemyError("Connection lost")):
            response = self.client.post("/api/v1/realty/contacts", json=payload)

        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertFalse(body.get("success"))
        self.assertIn("Failed to create contact", str(body.get("error")))

    def test_unhandled_exception_returns_500_not_200(self):
        """Unhandled exceptions (e.g. unexpected crash or missing module) return HTTP 500, NOT 200."""
        payload = {
            "name": "Crash Test",
            "phone": "9876543210",
            "email": "crashtest@example.com",
            "message": "Testing unexpected exception handling",
        }

        with patch("app.repo.realty.create_contact", side_effect=ModuleNotFoundError("No module named 'app.services.contact_notifications'")):
            response = self.client.post("/api/v1/realty/contacts", json=payload)

        # Critical contract requirement: genuine failures must not return HTTP 200
        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertFalse(body.get("success"))
        self.assertIsNone(body.get("data"))
        self.assertIsNotNone(body.get("error"))

    def test_crm_push_webhook_success(self):
        """CRM webhook push sends correct payload and auth header."""
        contact_dict = {
            "name_": "CRM Tester",
            "phone": "9876543210",
            "email": "crm@example.com",
            "message": "Looking for commercial lease",
            "location": "Indiranagar",
            "property_type": "Commercial",
            "source": "Website",
        }

        with patch.object(settings, "CRM_WEBHOOK_URL", "https://crm.makemystay.ai/api/v1/leads/webhook"), \
             patch.object(settings, "CRM_WEBHOOK_SECRET", "test_crm_secret_123"), \
             patch("httpx.post") as mock_post:

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            push_contact_to_crm(contact_dict, contact_id=42)

            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            self.assertEqual(kwargs["headers"]["X-API-Key"], "test_crm_secret_123")
            self.assertEqual(kwargs["json"]["name"], "CRM Tester")
            self.assertEqual(kwargs["json"]["phone"], "9876543210")
            self.assertEqual(kwargs["json"]["email"], "crm@example.com")
            self.assertEqual(kwargs["json"]["source"], "Website")

    def test_crm_push_unconfigured_skips_cleanly(self):
        """When CRM_WEBHOOK_URL or SECRET is empty, push_contact_to_crm skips gracefully."""
        contact_dict = {"name": "No CRM", "phone": "9876543210", "email": "nocrm@example.com"}

        with patch.object(settings, "CRM_WEBHOOK_URL", ""), \
             patch.object(settings, "CRM_WEBHOOK_SECRET", ""), \
             patch("httpx.post") as mock_post:

            push_contact_to_crm(contact_dict, contact_id=43)
            mock_post.assert_not_called()

    def test_crm_push_network_error_handled_gracefully(self):
        """Network error during CRM webhook push is logged and does not raise exception."""
        contact_dict = {"name": "Net Error", "phone": "9876543210", "email": "net@example.com"}

        with patch.object(settings, "CRM_WEBHOOK_URL", "https://crm.makemystay.ai/webhook"), \
             patch.object(settings, "CRM_WEBHOOK_SECRET", "secret"), \
             patch("httpx.post", side_effect=httpx.ConnectError("Network unreachable")):

            # Must not raise exception
            try:
                push_contact_to_crm(contact_dict, contact_id=44)
            except Exception as e:
                self.fail(f"push_contact_to_crm raised an exception on network failure: {e}")

    def test_crm_push_http_500_handled_gracefully(self):
        """HTTP error from CRM webhook is logged and does not raise exception."""
        contact_dict = {"name": "500 Error", "phone": "9876543210", "email": "500@example.com"}

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error", request=MagicMock(), response=mock_resp
        )

        with patch.object(settings, "CRM_WEBHOOK_URL", "https://crm.makemystay.ai/webhook"), \
             patch.object(settings, "CRM_WEBHOOK_SECRET", "secret"), \
             patch("httpx.post", return_value=mock_resp):

            # Must not raise exception
            try:
                push_contact_to_crm(contact_dict, contact_id=45)
            except Exception as e:
                self.fail(f"push_contact_to_crm raised an exception on CRM HTTP error: {e}")

    def test_no_obsolete_contact_notifications_imports_in_source_tree(self):
        """Ensure no python files in the repo reference 'app.services.contact_notifications'."""
        root_dir = Path(__file__).resolve().parent.parent / "app"
        obsolete_references = []

        for py_file in root_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if "contact_notifications" in content:
                obsolete_references.append(str(py_file.relative_to(root_dir.parent)))

        self.assertEqual(
            obsolete_references,
            [],
            f"Found references to obsolete 'contact_notifications' in: {obsolete_references}",
        )


if __name__ == "__main__":
    unittest.main()
