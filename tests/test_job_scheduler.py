import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.desktop_rpc import execute
from core.job_scheduler import MAX_IDLE_CYCLES, force_mode, status
from core.memory import Memory


class JobSchedulerTests(unittest.TestCase):
    def test_default_mode_is_sales(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                state = status(memory)
            self.assertEqual("sales", state["mode"])
            self.assertEqual("prospecting", state["next_mode"])

    def test_completed_job_hands_turn_to_prospecting(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                after = execute_job_complete(memory, "sales")
                self.assertEqual("prospecting", after["mode"])
                self.assertEqual("sales", after["next_mode"])
                self.assertEqual(0, after["idle_cycles"])
                self.assertEqual("sales", after["last_job"]["mode"])
                self.assertTrue(after["changed_at"])
                rows = memory.db.execute(
                    "select action,target from audit_events where action='sales.agent.job_mode_switched'"
                ).fetchall()
                self.assertEqual([("sales.agent.job_mode_switched", "prospecting")], rows)

    def test_idle_cycles_hand_turn_without_a_job(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                from core.job_scheduler import idle_tick
                state = status(memory)
                for _ in range(MAX_IDLE_CYCLES - 1):
                    state = idle_tick(memory, "sales")
                    self.assertEqual("sales", state["mode"])
                state = idle_tick(memory, "sales")
                self.assertEqual("prospecting", state["mode"])

    def test_job_from_inactive_mode_does_not_change_the_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                force_mode(memory, "prospecting")
                unchanged = execute_job_complete(memory, "sales")
                self.assertEqual("prospecting", unchanged["mode"])
                self.assertEqual({}, unchanged["last_job"])

    def test_force_mode_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                first = force_mode(memory, "prospecting")
                second = force_mode(memory, "prospecting")
                self.assertEqual(first, second)
                with self.assertRaises(ValueError):
                    force_mode(memory, "unknown")

    def test_rpcs_expose_the_queue_to_the_panel(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            self.assertEqual("sales", execute("browserModeStatus", {})["mode"])
            self.assertEqual("prospecting", execute("browserModeSet", {"mode": "prospecting"})["mode"])
            for _ in range(MAX_IDLE_CYCLES):
                idle = execute("browserModeIdle", {"mode": "prospecting"})
            self.assertEqual("sales", idle["mode"])
            self.assertEqual(
                "prospecting",
                execute("browserModeComplete", {"mode": "sales", "detail": "dm respondida"})["mode"],
            )


def execute_job_complete(memory, mode):
    from core.job_scheduler import complete_job
    return complete_job(memory, mode, "job de teste")


if __name__ == "__main__":
    unittest.main()
