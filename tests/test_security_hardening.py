"""
Regression tests for admin/API security hardening:
- staff-only data endpoints reject anonymous requests
- refresh tokens cannot be used as access tokens
- admin WebSocket rejects unauthenticated connections
- upload helpers sanitize client-controlled S3 key parts
"""

import unittest
from datetime import timedelta

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core import security
from app.main import app


class TestStaffOnlyEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_anonymous_requests_are_rejected(self):
        for path in (
            "/api/v1/payments",
            "/api/v1/payments/transactions",
            "/api/v1/payments/transactions/order_x",
            "/api/v1/payments/webhook-events",
            "/api/v1/schedule-demo",
        ):
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 401, f"{path} should require auth, got {r.status_code}")


class TestTokenTypes(unittest.TestCase):
    def test_refresh_token_is_not_an_access_token(self):
        refresh = security.create_refresh_token({"sub": "someone@example.com"})
        self.assertIsNone(security.get_user_from_token(refresh, db=None))

    def test_garbage_token_rejected(self):
        self.assertIsNone(security.get_user_from_token("not-a-jwt", db=None))
        self.assertIsNone(security.get_user_from_token(None, db=None))

    def test_get_current_user_rejects_refresh_token(self):
        refresh = security.create_refresh_token({"sub": "someone@example.com"}, timedelta(minutes=5))

        class _Req:
            cookies = {}

        with self.assertRaises(Exception) as ctx:
            security.get_current_user(_Req(), token=refresh, db=None)
        self.assertEqual(getattr(ctx.exception, "status_code", None), 401)


class TestAdminWebsocketAuth(unittest.TestCase):
    def test_ws_without_token_is_closed(self):
        client = TestClient(app)
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with client.websocket_connect("/api/v1/ws/admin") as ws:
                ws.receive_text()
        self.assertEqual(ctx.exception.code, 1008)


class TestUploadSanitizers(unittest.TestCase):
    def test_safe_extension(self):
        from app.api.upload import _safe_extension

        self.assertEqual(_safe_extension("photo.PNG"), "png")
        self.assertEqual(_safe_extension("noext"), "jpg")
        self.assertEqual(_safe_extension("x.php%00.jpg/../a"), "jpg")
        self.assertEqual(_safe_extension(None), "jpg")

    def test_property_id_pattern(self):
        from app.api.upload import _SAFE_PROPERTY_ID

        self.assertTrue(_SAFE_PROPERTY_ID.match("123"))
        self.assertTrue(_SAFE_PROPERTY_ID.match("my-slug_1"))
        self.assertFalse(_SAFE_PROPERTY_ID.match("../etc"))
        self.assertFalse(_SAFE_PROPERTY_ID.match("a/b"))


if __name__ == "__main__":
    unittest.main()


class TestPaymentOrderValidation(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_expected_fee_table(self):
        from app.api.payment import expected_service_fee

        self.assertEqual(expected_service_fee("PG", "sharing"), 1500)
        self.assertEqual(expected_service_fee("colive pg", "PRIVATE"), 2500)
        self.assertEqual(expected_service_fee("1BHK", None), 4000)
        self.assertEqual(expected_service_fee("2bhk", "fixed"), 6000)
        self.assertIsNone(expected_service_fee("Villa", None))
        self.assertIsNone(expected_service_fee(None, None))

    def test_wrong_fee_for_known_type_rejected(self):
        r = self.client.post(
            "/api/v1/payments/create-order",
            json={"amount": 100, "property_type": "1BHK"},
        )
        self.assertEqual(r.status_code, 400)

    def test_over_max_rejected(self):
        r = self.client.post("/api/v1/payments/create-order", json={"amount": 10**12})
        self.assertEqual(r.status_code, 400)

    def test_non_positive_and_bad_currency_rejected(self):
        self.assertEqual(self.client.post("/api/v1/payments/create-order", json={"amount": 0}).status_code, 422)
        self.assertEqual(
            self.client.post("/api/v1/payments/create-order", json={"amount": 100, "currency": "USD"}).status_code,
            422,
        )


class TestMiscLockdown(unittest.TestCase):
    def test_whoami_requires_admin(self):
        r = TestClient(app, raise_server_exceptions=False).get("/api/v1/whoami")
        self.assertEqual(r.status_code, 401)

    def test_public_form_endpoints_are_rate_limited(self):
        from app.core.rate_limit import limiter

        limited = set(limiter._route_limits.keys())
        for name in (
            "app.api.realty.create_contact",
            "app.api.realty.add_property_review",
            "app.api.demo.schedule_demo",
            "app.api.retell.create_web_call",
            "app.api.payment.create_order",
        ):
            self.assertIn(name, limited)

    def test_enterprise_router_no_longer_shadows_realty_paths(self):
        from fastapi.routing import APIRoute

        seen = {}
        for r in app.routes:
            if isinstance(r, APIRoute):
                for m in r.methods:
                    key = (m, r.path)
                    self.assertNotIn(key, seen, f"duplicate route {key}")
                    seen[key] = r


class TestClientIpForRateLimits(unittest.TestCase):
    def _req(self, headers, client=("127.0.0.1", 1234)):
        from starlette.requests import Request

        scope = {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": client,
        }
        return Request(scope)

    def test_alb_then_nginx_chain_uses_real_client(self):
        from app.core.rate_limit import client_ip

        # client -> ALB (adds client) -> nginx (adds ALB private IP)
        r = self._req({"X-Forwarded-For": "49.36.10.7, 10.0.1.25", "X-Real-IP": "10.0.1.25"})
        self.assertEqual(client_ip(r), "49.36.10.7")

    def test_spoofed_left_entries_ignored(self):
        from app.core.rate_limit import client_ip

        r = self._req({"X-Forwarded-For": "1.2.3.4, 106.51.22.9, 10.0.0.5"})
        self.assertEqual(client_ip(r), "106.51.22.9")

    def test_nginx_only_real_ip(self):
        from app.core.rate_limit import client_ip

        r = self._req({"X-Real-IP": "117.96.4.20"})
        self.assertEqual(client_ip(r), "117.96.4.20")

    def test_local_fallback(self):
        from app.core.rate_limit import client_ip

        self.assertEqual(client_ip(self._req({})), "127.0.0.1")
