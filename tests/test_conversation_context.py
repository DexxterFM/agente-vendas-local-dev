import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.memory import Memory
from core.conversation_context import (
    can_send,
    fingerprint,
    is_opening,
    normalize,
)


class ConversationContextTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = str(Path(self.folder.name) / "ctx.sqlite3")

    def test_is_opening_detects_first_contact_phrases(self):
        self.assertTrue(is_opening("Obrigado por seguir! Parabéns pelo trabalho"))
        self.assertTrue(is_opening("Vi o trabalho da clínica e achei muito bonito"))
        self.assertTrue(is_opening("Tenho um presente para você"))
        self.assertFalse(is_opening("Que bom! Qual app vocês usam hoje?"))
        self.assertFalse(is_opening("Posso enviar o link para ativar?"))

    def test_can_send_blocks_opening_in_existing_conversation(self):
        with Memory(self.db) as memory:
            memory.add_conversation(1, "assistant", "Obrigado por seguir!")
            memory.add_conversation(1, "user", "Oi")
            allowed, reason = can_send(
                memory, 1, "clinica", "Obrigado por seguir! Parabéns pelo trabalho"
            )
            self.assertFalse(allowed)
            self.assertEqual(reason, "opening-in-existing-conversation")

    def test_can_send_allows_continuation_in_existing_conversation(self):
        with Memory(self.db) as memory:
            memory.add_conversation(1, "assistant", "Obrigado por seguir!")
            memory.add_conversation(1, "user", "Sim, uso um sistema")
            allowed, reason = can_send(
                memory, 1, "clinica", "Que bom! Qual app vocês usam hoje?"
            )
            self.assertTrue(allowed)
            self.assertEqual(reason, "")

    def test_can_send_blocks_duplicate_on_screen(self):
        with Memory(self.db) as memory:
            screen = [{"role": "assistant", "text": "Qual app vocês usam?"}]
            allowed, reason = can_send(
                memory, None, "clinica", "Qual app vocês usam?", screen
            )
            self.assertFalse(allowed)
            self.assertEqual(reason, "duplicate-on-screen")

    def test_can_send_blocks_duplicate_in_history(self):
        with Memory(self.db) as memory:
            memory.add_conversation(1, "assistant", "Qual app vocês usam?")
            allowed, reason = can_send(
                memory, 1, "clinica", "Qual app vocês usam?"
            )
            self.assertFalse(allowed)
            self.assertEqual(reason, "duplicate-in-history")

    def test_normalize_and_fingerprint_are_stable(self):
        self.assertEqual(normalize("  Olá   mundo  "), "olá mundo")
        self.assertEqual(fingerprint("Olá mundo"), fingerprint("  olá   MUNDO "))

    def test_has_prior_exchange(self):
        from core.conversation_context import has_prior_exchange
        self.assertFalse(has_prior_exchange([]))
        self.assertFalse(has_prior_exchange([("user", "oi")]))
        self.assertTrue(has_prior_exchange([("assistant", "oi"), ("user", "oi")]))
        self.assertTrue(has_prior_exchange([("user", "oi"), ("user", "oi")]))


if __name__ == "__main__":
    unittest.main()
