import hashlib
import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.memory import Memory
from scripts.vps.meta_webhook import ingest, verify_signature, verify_subscription


class MetaWebhookTests(unittest.TestCase):
    def test_subscription_requires_matching_token(self):
        with patch.dict(os.environ, {"META_WEBHOOK_VERIFY_TOKEN": "verify-test"}, clear=False):
            self.assertEqual(
                verify_subscription({
                    "hub.mode": "subscribe",
                    "hub.verify_token": "verify-test",
                    "hub.challenge": "challenge-123",
                }),
                "challenge-123",
            )
            self.assertIsNone(verify_subscription({"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"}))

    def test_signature_is_required_and_checked(self):
        body = b'{"object":"instagram"}'
        with patch.dict(os.environ, {"INSTAGRAM_APP_SECRET": "app-secret"}, clear=False):
            signature = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
            self.assertTrue(verify_signature(body, signature))
            self.assertFalse(verify_signature(body, "sha256=invalid"))
            self.assertFalse(verify_signature(body, None))

    def test_ingest_imports_only_messages_and_deduplicates(self):
        payload = {
            "object": "instagram",
            "entry": [{"messaging": [
                {"sender": {"id": "lead-1"}, "recipient": {"id": "account-1"}, "timestamp": 1_700_000_000_000, "message": {"mid": "m-1", "text": "Olá"}},
                {"sender": {"id": "lead-1"}, "recipient": {"id": "account-1"}, "timestamp": 1_700_000_000_000, "reaction": {"action": "react"}},
            ]}],
        }
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"IG_BUSINESS_ACCOUNT_ID": "account-1"}, clear=False):
            memory = Memory(Path(folder) / "agent.sqlite3")
            try:
                first = ingest(memory, payload)
                again = ingest(memory, json.loads(json.dumps(payload)))
                self.assertEqual(first, {"imported": 1, "duplicate": 0, "ignored": 1})
                self.assertEqual(again, {"imported": 0, "duplicate": 1, "ignored": 1})
                lead = memory.list_leads()[0]
                self.assertEqual(lead[2], "lead-1")
                self.assertEqual(memory.get_setting("instagram.recipient:" + str(lead[0])), '{"account":"account-1","recipient":"lead-1"}')
            finally:
                memory.close()


if __name__ == "__main__":
    unittest.main()
