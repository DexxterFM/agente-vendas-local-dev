import os
import unittest
from unittest.mock import patch

from adapters import postflow


class PostflowConfigurationTests(unittest.TestCase):
    def test_internal_channel_uses_only_the_official_loopback_endpoint(self):
        with patch.dict(os.environ, {
            "POSTFLOW_BASE_URL": "http://127.0.0.1:3999",
            "POSTFLOW_TRUSTED_LOCAL": "true",
            "SALES_AGENT_INTERNAL_TOKEN": "test",
        }, clear=True):
            self.assertEqual(postflow._base(), "http://127.0.0.1:3110")

    def test_trusted_local_requires_explicit_flag_loopback_and_internal_token(self):
        with patch.dict(os.environ, {"POSTFLOW_BASE_URL": "http://127.0.0.1:3110", "POSTFLOW_TRUSTED_LOCAL": "true", "SALES_AGENT_INTERNAL_TOKEN": "test"}, clear=True):
            self.assertTrue(postflow.configured())
        with patch.dict(os.environ, {"POSTFLOW_BASE_URL": "https://postflow.example.com", "POSTFLOW_TRUSTED_LOCAL": "true"}, clear=True):
            self.assertFalse(postflow.configured())
        with patch.dict(os.environ, {"POSTFLOW_BASE_URL": "http://127.0.0.1:3110"}, clear=True):
            self.assertFalse(postflow.configured())
        with patch.dict(os.environ, {"POSTFLOW_BASE_URL": "http://127.0.0.1:3110", "POSTFLOW_TRUSTED_LOCAL": "true"}, clear=True):
            self.assertFalse(postflow.configured())

    def test_token_configures_any_authorized_base(self):
        with patch.dict(os.environ, {"POSTFLOW_BASE_URL": "https://postflow.example.com", "POSTFLOW_API_TOKEN": "test"}, clear=True):
            self.assertTrue(postflow.configured())

    @patch("adapters.postflow._request")
    def test_status_reports_available_thread_count(self, request):
        request.side_effect = [
            {"ok": True, "service": "instagram-agent"},
            {"threads": [{"id": "a"}, {"id": "b"}]},
        ]
        with patch.dict(os.environ, {"POSTFLOW_BASE_URL": "https://postflow.example.com", "POSTFLOW_API_TOKEN": "test"}, clear=True):
            result = postflow.status()
        self.assertEqual(result["status"], "connected")
        self.assertEqual(result["threads"], 2)
        self.assertIn("2 conversa", result["detail"])

    @patch("adapters.postflow._request")
    def test_sync_ingestion_returns_only_sanitized_counts(self, request):
        request.return_value = {"synced": True, "stats": {"threads": 2, "messages": 4, "comments": 1}, "token": "must-not-return"}
        result = postflow.sync_ingestion()
        self.assertEqual(result, {"status": "connected", "category": "imported", "synced": True, "threads": 2, "messages": 4, "comments": 1})

    @patch("adapters.postflow._request", side_effect=RuntimeError("PostFlow HTTP 401: token invalid"))
    def test_sync_ingestion_hides_authorization_detail(self, _request):
        result = postflow.sync_ingestion()
        self.assertEqual(result, {"status": "attention", "category": "authorization_rejected", "synced": False})
