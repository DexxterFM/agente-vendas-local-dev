import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.memory import Memory
from core.trial_lifecycle import TrialLifecycle


class TrialLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.memory = Memory(Path(self.temp.name) / "agent.sqlite3")
        self.lifecycle = TrialLifecycle(self.memory)
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def tearDown(self):
        self.memory.close()
        self.temp.cleanup()

    def test_trial_never_charges_automatically_and_warns_ten_days_before(self):
        self.lifecycle.start("clinic", self.start)
        state = self.lifecycle.status("clinic", self.start + timedelta(days=80))
        self.assertEqual(state["status"], "ending_soon")
        self.assertFalse(state["automatic_charge"])
        self.assertIn("Não haverá cobrança automática", self.lifecycle.warning_message(state))

    def test_expiry_locks_access_and_keeps_encrypted_export_for_15_days(self):
        self.lifecycle.start("clinic", self.start)
        expired = self.lifecycle.status(
            "clinic",
            self.start + timedelta(days=90),
            {"conversations": [{"text": "dado clínico"}]},
        )
        self.assertEqual(expired["status"], "expired_locked")
        self.assertIn("encrypted_export", expired)
        self.assertNotIn("dado clínico", expired["encrypted_export"])
        self.assertFalse(expired["automatic_charge"])
        deleted = self.lifecycle.status("clinic", self.start + timedelta(days=105))
        self.assertEqual(deleted["status"], "deleted")
        self.assertNotIn("encrypted_export", deleted)

    def test_continuation_requires_explicit_confirmation(self):
        self.lifecycle.start("clinic", self.start)
        requested = self.lifecycle.request_continuation("clinic")
        self.assertEqual(requested["status"], "continuation_requested")
        self.assertFalse(requested.get("payment_confirmed_at"))
        paid = self.lifecycle.confirm_payment("clinic")
        self.assertEqual(paid["status"], "paid_active")


if __name__ == "__main__":
    unittest.main()
