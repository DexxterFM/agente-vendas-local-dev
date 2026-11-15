import tempfile
import unittest
from pathlib import Path

from core.memory import Memory
from core.prospecting_pacing import ProspectingPacing


class ProspectingPacingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.memory = Memory(Path(self.temp.name) / "agent.sqlite3")
        self.now = 10_000
        self.pacing = ProspectingPacing(
            self.memory,
            clock=lambda: self.now,
            dice=lambda: 1,
            jitter=lambda: 15,
        )

    def tearDown(self):
        self.memory.close()
        self.temp.cleanup()

    def test_reservation_is_always_more_than_five_minutes(self):
        round_ = self.pacing.reserve_round("instagram_outreach", "clinica.teste")
        self.assertTrue(round_["reserved"])
        self.assertGreater(round_["interval_seconds"], 300)
        self.assertEqual(round_["roll"], 1)
        self.assertTrue(any(row[2] == "sales.prospecting.roll" for row in self.memory.list_audit()))

    def test_second_round_waits_for_persisted_window(self):
        first = self.pacing.reserve_round()
        waiting = self.pacing.reserve_round()
        self.assertFalse(waiting["reserved"])
        self.assertGreater(waiting["wait_seconds"], 0)
        self.now = first["next_at"]
        self.assertTrue(self.pacing.reserve_round()["reserved"])
