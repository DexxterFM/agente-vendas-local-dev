import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.desktop_rpc import execute
from core.activation_token import ActivationTokenManager
from core.memory import Memory


class ActivationTokenValidationTests(unittest.TestCase):
    def test_register_tokens_success(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                mgr = ActivationTokenManager(memory)
                result = mgr.register_tokens([
                    "ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY",
                    "ERPDEMO-6F490A537E-nw4gjRmsu9quQrIo6wheQnPnOMfsAovzpOfREFf5Ud0",
                ])
            self.assertEqual(result["registered"], 2)
            self.assertEqual(result["skipped"], 0)
            self.assertTrue(result["expires_at"])

    def test_register_duplicate_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                mgr = ActivationTokenManager(memory)
                mgr.register_tokens(["ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY"])
                result = mgr.register_tokens(["ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY"])
            self.assertEqual(result["registered"], 0)
            self.assertEqual(result["skipped"], 1)

    def test_register_invalid_format_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                mgr = ActivationTokenManager(memory)
                result = mgr.register_tokens(["TOKEN-INVALIDO", "ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY"])
            self.assertEqual(result["registered"], 1)
            self.assertEqual(result["skipped"], 1)

    def test_consume_token_returns_code(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                mgr = ActivationTokenManager(memory)
                mgr.register_tokens(["ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY"])
                result = mgr.consume_token(1, "Clínica Teste")
            self.assertIsNotNone(result)
            self.assertTrue(result["consumed"])
            self.assertEqual(result["token"], "ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY")
            self.assertEqual(result["lead_id"], 1)

    def test_consume_token_single_use(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                mgr = ActivationTokenManager(memory)
                mgr.register_tokens(["ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY"])
                first = mgr.consume_token(1, "Lead A")
                second = mgr.consume_token(2, "Lead B")
            self.assertIsNotNone(first)
            self.assertIsNone(second)  # Token já usado

    def test_no_available_token_returns_none(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                mgr = ActivationTokenManager(memory)
                result = mgr.consume_token(1, "Lead")
            self.assertIsNone(result)

    def test_stats(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "agent.sqlite3"
            with Memory(db) as memory:
                mgr = ActivationTokenManager(memory)
                mgr.register_tokens([
                    "ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY",
                    "ERPDEMO-6F490A537E-nw4gjRmsu9quQrIo6wheQnPnOMfsAovzpOfREFf5Ud0",
                ])
                mgr.consume_token(1, "Lead A")
                stats = mgr.stats()
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["used"], 1)
            self.assertEqual(stats["available"], 1)

    def test_register_tokens_rpc(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            result = execute("activationTokenRegister", {
                "tokens": "ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY, ERPDEMO-6F490A537E-nw4gjRmsu9quQrIo6wheQnPnOMfsAovzpOfREFf5Ud0"
            })
        self.assertEqual(result["registered"], 2)

    def test_activation_token_stats_rpc(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("activationTokenRegister", {
                "tokens": ["ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY"]
            })
            stats = execute("activationTokenStats", {})
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["available"], 1)

    def test_activation_token_list_rpc(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("activationTokenRegister", {
                "tokens": ["ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY"]
            })
            lst = execute("activationTokenList", {})
        self.assertEqual(len(lst["tokens"]), 1)
        self.assertEqual(lst["tokens"][0]["code"], "ERPDEMO-41C47C9C61-FzY1-KhQaGkQhTb6m1fRQsUluz20ztTirct_GGeFFWY")
        self.assertEqual(lst["tokens"][0]["used"], 0)


if __name__ == "__main__":
    unittest.main()
