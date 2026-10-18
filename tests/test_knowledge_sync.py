import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stoneart_products


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, login_response, sync_response):
        self.login_response = login_response
        self.sync_response = sync_response
        self.post_calls = []
        self.request_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append({"url": url, **kwargs})
        return self.login_response

    def request(self, method, url, **kwargs):
        self.request_calls.append({"method": method, "url": url, **kwargs})
        return self.sync_response


def config():
    return {
        "LOCAL_KB_SYNC_ENABLED": "true",
        "LOCAL_KB_BASE_URL": "http://kb.test",
        "LOCAL_KB_ADMIN_ORIGIN": "https://ai.stoneartsculpture.com",
        "LOCAL_KB_ADMIN_USERNAME": "admin",
        "LOCAL_KB_ADMIN_PASSWORD": "test-password",
        "LOCAL_KB_SYNC_TIMEOUT": "45",
        "LOCAL_KB_VERIFY_TLS": "true",
    }


class KnowledgeSyncTests(unittest.TestCase):
    def test_product_sync_logs_in_and_posts_with_origin(self):
        session = FakeSession(
            FakeResponse(200, {"authenticated": True}),
            FakeResponse(
                200,
                {
                    "source_total": 10,
                    "created": 1,
                    "updated": 0,
                    "unchanged": 9,
                },
            ),
        )
        with patch("stoneart_products.requests.Session", return_value=session):
            result = stoneart_products.sync_knowledge_base_products(config())

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "sync")
        self.assertEqual(session.post_calls[0]["json"]["username"], "admin")
        self.assertEqual(
            session.post_calls[0]["headers"]["Origin"],
            "https://ai.stoneartsculpture.com",
        )
        self.assertEqual(session.request_calls[0]["method"], "POST")
        self.assertEqual(
            session.request_calls[0]["url"],
            "http://kb.test/api/imports/stoneart/sync",
        )
        self.assertEqual(session.request_calls[0]["timeout"], 45)

    def test_safe_sync_reports_license_error_without_raising(self):
        session = FakeSession(
            FakeResponse(200, {"authenticated": True}),
            FakeResponse(
                402,
                {
                    "detail": "尚未上传授权证书",
                    "license_status": {"valid": False, "status": "missing"},
                },
            ),
        )
        with patch("stoneart_products.requests.Session", return_value=session):
            result = stoneart_products.safe_sync_knowledge_base(
                config(),
                product={"status": "published"},
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 402)
        self.assertEqual(result["error"], "尚未上传授权证书")
        self.assertEqual(result["license_status"]["status"], "missing")

    def test_disabled_sync_is_skipped(self):
        settings = config()
        settings["LOCAL_KB_SYNC_ENABLED"] = "false"
        result = stoneart_products.safe_sync_knowledge_base(
            settings,
            product={"status": "published"},
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["enabled"])
        self.assertIn("skipped", result)


if __name__ == "__main__":
    unittest.main()
