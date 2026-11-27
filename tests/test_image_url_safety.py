"""Uploads must never leave browser-only (blob:/data:) URLs in the database."""

import sys
import unittest
from datetime import datetime
from unittest.mock import patch

from botocore.exceptions import ClientError, NoCredentialsError
from pydantic import ValidationError

from app.api.upload import _storage_http_error
from app.schemas.realty import PropertyImageCreate, PropertyImageResponse, PropertyImageSync, PropertyImageUpdate
from app.utils.cloudfront import get_cloudfront_signed_url

BLOB = "blob:https://admin.makemystay.ai/e933d45f-4ee5-4515-ade2-4ab16bcdb068"


class TestRejectBrowserOnlyUrls(unittest.TestCase):
    def test_create_sync_update_reject_blob_and_data(self):
        for bad in (BLOB, "data:image/png;base64,AAAA", "  BLOB:http://x"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    PropertyImageCreate(image_url=bad)
                with self.assertRaises(ValidationError):
                    PropertyImageSync(image_url=bad)
                with self.assertRaises(ValidationError):
                    PropertyImageUpdate(image_url=bad)

    def test_real_urls_and_keys_accepted(self):
        for ok in ("https://d1.cloudfront.net/properties/1/a.jpg", "properties/1/user_1/a.png"):
            self.assertEqual(PropertyImageSync(image_url=ok).image_url, ok)
        self.assertIsNone(PropertyImageUpdate(image_url=None).image_url)

    def test_reading_existing_bad_rows_does_not_crash(self):
        r = PropertyImageResponse(id=1, property_id=2, image_url=BLOB, created_at=datetime(2026, 11, 27))
        self.assertEqual(r.image_url, BLOB)  # returned untouched, not signed as an S3 key

    def test_cloudfront_never_signs_blob_urls(self):
        self.assertEqual(get_cloudfront_signed_url(BLOB), BLOB)
        self.assertEqual(get_cloudfront_signed_url(""), "")


class TestStorageErrors(unittest.TestCase):
    def _client_error(self, code):
        return ClientError({"Error": {"Code": code, "Message": "x"}}, "PutObject")

    def test_invalid_key_is_503_with_clear_message(self):
        e = _storage_http_error(self._client_error("InvalidAccessKeyId"))
        self.assertEqual(e.status_code, 503)
        self.assertIn("InvalidAccessKeyId", e.detail)
        self.assertNotIn("AKIA", e.detail)

    def test_missing_credentials_is_503(self):
        self.assertEqual(_storage_http_error(NoCredentialsError()).status_code, 503)

    def test_other_errors_are_502_without_internals(self):
        e = _storage_http_error(RuntimeError("socket blew up at 10.0.0.5"))
        self.assertEqual(e.status_code, 502)
        self.assertNotIn("10.0.0.5", e.detail)


class TestCleanupScript(unittest.TestCase):
    def test_report_and_apply(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.models.realty import Property, PropertyImage

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Property.__table__.create(engine)
        PropertyImage.__table__.create(engine)
        Session = sessionmaker(bind=engine)
        s = Session()
        good = "https://cdn.example/p/1.jpg"
        s.add(Property(id=1, property_name="Sri Sathyasai PG", location="Whitefield", property_type="PG", listing_type="rent",
                       metadata_json={"uploaded_images": [{"public_url": BLOB}, {"public_url": good}]}))
        s.add(PropertyImage(id=10, property_id=1, image_url=BLOB, is_primary=True, sort_order=0))
        s.add(PropertyImage(id=11, property_id=1, image_url=good, is_primary=False, sort_order=1))
        s.commit()
        s.close()

        sys.path.insert(0, "scripts")
        import fix_browser_only_image_urls as script

        with patch.object(script, "MySQLSessionLocal", Session), patch.object(sys, "argv", ["x", "--apply"]):
            script.main()

        s = Session()
        self.assertEqual([i.image_url for i in s.query(PropertyImage).all()], [good])
        self.assertEqual(s.get(Property, 1).metadata_json["uploaded_images"], [{"public_url": good}])
        s.close()


if __name__ == "__main__":
    unittest.main()
