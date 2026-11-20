import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.memory import Memory
from core.instagram_profile_memory import (
    InstagramProfileMemory,
    infer_flow_step,
)


class InstagramProfileMemoryTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = str(Path(self.folder.name) / "ig.sqlite3")

    def test_record_sent_then_can_send_blocks_resend(self):
        with Memory(self.db) as memory:
            flow = InstagramProfileMemory(memory)
            self.assertTrue(flow.record_sent("clinica.teste", "Olá! Tudo bem?", flow_step="intro"))
            allowed, reason = flow.can_send("clinica.teste", "Olá! Tudo bem?")
            self.assertFalse(allowed)
            self.assertEqual(reason, "already-sent-to-profile")
            # Variação de caixa/espaço também é bloqueada (hash normalizado).
            allowed2, _ = flow.can_send("clinica.teste", "  olá!  tudo bem? ")
            self.assertFalse(allowed2)

    def test_different_message_allowed(self):
        with Memory(self.db) as memory:
            flow = InstagramProfileMemory(memory)
            flow.record_sent("clinica.teste", "Olá! Tudo bem?", flow_step="intro")
            allowed, reason = flow.can_send("clinica.teste", "Qual app vocês usam?")
            self.assertTrue(allowed)
            self.assertEqual(reason, "")

    def test_per_profile_isolation(self):
        with Memory(self.db) as memory:
            flow = InstagramProfileMemory(memory)
            flow.record_sent("perfil.a", "Mensagem única")
            allowed, _ = flow.can_send("perfil.b", "Mensagem única")
            self.assertTrue(allowed)
            allowed2, _ = flow.can_send("perfil.a", "Mensagem única")
            self.assertFalse(allowed2)

    def test_duplicate_record_returns_false(self):
        with Memory(self.db) as memory:
            flow = InstagramProfileMemory(memory)
            self.assertTrue(flow.record_sent("clinica", "MSG"))
            self.assertFalse(flow.record_sent("clinica", "MSG"))

    def test_flow_steps_tracking(self):
        with Memory(self.db) as memory:
            flow = InstagramProfileMemory(memory)
            flow.record_sent("clinica", "Obrigado por seguir!", flow_step="intro")
            flow.record_sent("clinica", "Qual app vocês usam?", flow_step="welcome_question")
            self.assertEqual(flow.last_step("clinica"), "welcome_question")
            self.assertEqual(flow.steps_taken("clinica"), ["intro", "welcome_question"])
            self.assertEqual(len(flow.sent_messages("clinica")), 2)

    def test_infer_flow_step(self):
        self.assertEqual(infer_flow_step("Obrigado por seguir! Parabéns"), "intro")
        self.assertEqual(infer_flow_step("Você merece! Já possui algum app?"), "welcome_question")
        self.assertEqual(infer_flow_step("Seu link de instalação: https://..."), "install_link")
        self.assertEqual(infer_flow_step("Aviso esse link é valido por 3 dias"), "install_validity")
        self.assertEqual(infer_flow_step("Mensagem qualquer"), "reply")

    def test_profile_metadata(self):
        with Memory(self.db) as memory:
            flow = InstagramProfileMemory(memory)
            flow.ensure_profile("clinica", kind="clinic_multi", segment="clinic",
                                specialties=["aba", "fonoaudiologia"], thread_id="t123")
            profile = flow.get_profile("clinica")
            self.assertEqual(profile["kind"], "clinic_multi")
            self.assertEqual(profile["segment"], "clinic")
            self.assertIn("aba", profile["specialties"])
            self.assertEqual(profile["thread_id"], "t123")


if __name__ == "__main__":
    unittest.main()
