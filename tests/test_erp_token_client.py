import io
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.erp_token_client import DEFAULT_BASE_URL, TOKEN_PATH, generate_demo_token, plan_slug_for_url


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


class ErpTokenClientTests(unittest.TestCase):

    def test_plan_slug_mapping(self):
        self.assertEqual("enterprise", plan_slug_for_url("https://erpclinicatea.com/login/admin?plano=clinica-multiprofissional&convite=3-meses"))
        self.assertEqual("enterprise", plan_slug_for_url("...plano=enterprise..."))
        self.assertEqual("professional", plan_slug_for_url("https://erpclinicatea.com/login/admin?plano=profissional&convite=3-meses"))
        self.assertEqual("professional", plan_slug_for_url(""))
        self.assertEqual("starter", plan_slug_for_url("?plano=starter"))

    def test_generate_demo_token_posts_3m_policy_and_returns_token(self):
        payload = {"ok": True, "token": "ERPDEMO-31DA0F4C95-abcdefghijklmnopqrstuvwxyzABCDEFG", "durationCode": "3m", "planSlug": "professional"}
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(json.dumps(payload).encode("utf-8"))

        with patch("core.erp_token_client.urllib.request.urlopen", side_effect=fake_urlopen):
            result = generate_demo_token(api_key="SEGREDO", base_url="https://erp.example.com/")

        self.assertEqual(payload, result)
        self.assertEqual("https://erp.example.com" + TOKEN_PATH, captured["url"])
        self.assertEqual("SEGREDO", captured["headers"].get("X-agent-token"))
        self.assertEqual("3m", captured["body"]["durationCode"])
        self.assertEqual("test", captured["body"]["accountKind"])
        self.assertEqual("retain", captured["body"]["dataPolicy"])
        self.assertEqual(30, captured["body"]["redeemWithinDays"])

    def test_generate_demo_token_uses_default_base_and_plan(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(b'{"ok":true,"token":"ERPDEMO-AAAAAAAAAA-abcdefghijklmnopqrstuvwxyzABCDEFG"}')

        with patch.dict(os.environ, {"ERP_CLINICATEA_API_BASE_URL": "", "ERP_DEMO_TOKEN_API_KEY": "K"}), \
             patch("core.erp_token_client.urllib.request.urlopen", side_effect=fake_urlopen):
            result = generate_demo_token()

        self.assertEqual(DEFAULT_BASE_URL + TOKEN_PATH, captured["url"])
        self.assertEqual("professional", captured["body"]["planSlug"])
        self.assertTrue(result["ok"])

    def test_generate_demo_token_without_key_returns_none(self):
        with patch.dict(os.environ, {"ERP_DEMO_TOKEN_API_KEY": ""}), \
             patch("core.erp_token_client.urllib.request.urlopen") as urlopen:
            result = generate_demo_token()
        self.assertIsNone(result)
        urlopen.assert_not_called()

    def test_generate_demo_token_http_error_returns_none(self):
        import urllib.error
        with patch("core.erp_token_client.urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            result = generate_demo_token(api_key="K")
        self.assertIsNone(result)

    def test_generate_demo_token_error_payload_returns_none(self):
        with patch("core.erp_token_client.urllib.request.urlopen", return_value=FakeResponse(b'{"ok":false,"error":"invalid_duration"}')):
            result = generate_demo_token(api_key="K")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
