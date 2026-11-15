import os
import unittest
from unittest.mock import patch

from adapters import postflow


class PostflowConfigurationTests(unittest.TestCase):
    def test_trusted_local_requires_explicit_flag_and_loopback(self):
        with patch.dict(os.environ, {"POSTFLOW_BASE_URL": "http://127.0.0.1:3110", "POSTFLOW_TRUSTED_LOCAL": "true"}, clear=True):
            self.assertTrue(postflow.configured())
        with patch.dict(os.environ, {"POSTFLOW_BASE_URL": "https://postflow.example.com", "POSTFLOW_TRUSTED_LOCAL": "true"}, clear=True):
            self.assertFalse(postflow.configured())
        with patch.dict(os.environ, {"POSTFLOW_BASE_URL": "http://127.0.0.1:3110"}, clear=True):
            self.assertFalse(postflow.configured())

    def test_token_configures_any_authorized_base(self):
        with patch.dict(os.environ, {"POSTFLOW_BASE_URL": "https://postflow.example.com", "POSTFLOW_API_TOKEN": "test"}, clear=True):
            self.assertTrue(postflow.configured())
