import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.desktop_rpc import execute
from core.memory import Memory
from core.profile_memory import ProfileMemory, classify


class ProfileClassificationTests(unittest.TestCase):

    def test_clinic_and_multidisciplinary_are_separate(self):
        self.assertEqual("clinic", classify("Clínica Fono Audição")["kind"])
        self.assertEqual(
            "clinic_multi",
            classify("Clínica multidisciplinar de desenvolvimento infantil")["kind"],
        )

    def test_therapist_specialties_from_operator_are_recorded(self):
        text = ("Terapeuta ocupacional, psicomotricista, fonoaudiólogo, fisioterapia, "
                "psicopedagogia, neuropsicólogo e ABA")
        result = classify(text)
        self.assertEqual("therapist", result["kind"])
        for name in ("terapia ocupacional", "psicomotricidade", "fonoaudiologia",
                     "fisioterapia", "psicopedagogia", "neuropsicologia", "aba"):
            self.assertIn(name, result["specialties"])

    def test_unrelated_profile_is_community(self):
        self.assertEqual("community", classify("Restaurante e cafeteria")["kind"])


class ProfileMemoryTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db_path = Path(self.folder.name) / "agent.sqlite3"
        self.env = patch.dict(os.environ, {"SALES_AGENT_DB": str(self.db_path)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.memory = Memory(self.db_path)
        self.addCleanup(self.memory.close)
        self.profiles = ProfileMemory(self.memory)

    def test_same_message_is_not_sent_twice_to_same_profile(self):
        first = "Obrigado por seguir! Parabéns pelo trabalho da clínica!"
        self.assertTrue(self.profiles.message_allowed("clinica.teste", first)["allowed"])
        self.profiles.observe(
            "clinica.teste", "Clínica multidisciplinar", actions={"follow": True, "like": True},
            message=first, stage="dm",
        )
        guard = self.profiles.message_allowed("clinica.teste", first)
        self.assertFalse(guard["allowed"])
        self.assertEqual("duplicate-message", guard["reason"])

    def test_consecutive_duplicate_is_blocked_even_when_text_changes_slightly(self):
        self.profiles.observe("terapeuta.teste", "Psicopedagogia", message="Olá, tudo bem?")
        self.assertFalse(self.profiles.message_allowed("terapeuta.teste", "Olá, tudo bem?")["allowed"])
        self.assertTrue(self.profiles.message_allowed("terapeuta.teste", "Outra mensagem")["allowed"])

    def test_actions_are_merged_without_losing_previous_steps(self):
        self.profiles.observe("clinica.dois", "Clínica", actions={"follow": True})
        record = self.profiles.observe("clinica.dois", "Clínica", actions={"dm": True}, message="Oi")
        self.assertTrue(record["actions"]["follow"])
        self.assertTrue(record["actions"]["dm"])
        self.assertTrue(record["dm_sent"])

    def test_rpc_blocks_repeated_campaign_and_skips_claimed_profile(self):
        intro = "Obrigado por seguir! Parabéns pelo seu trabalho!"
        execute("campaignProfileObserve", {
            "username": "psicologa.teste", "text": "Psicóloga e terapeuta",
            "actions": {"follow": True}, "message": intro, "sent": True,
        })
        record = execute("campaignProfileMemory", {"username": "psicologa.teste"})
        self.assertEqual("therapist", record["kind"])
        self.assertFalse(execute("campaignMessageGuard", {
            "username": "psicologa.teste", "text": intro,
        })["allowed"])

        from core.desktop_rpc import execute as rpc
        memory = Memory(self.db_path)
        self.addCleanup(memory.close)
        pending_id = memory.create_pending_action(
            "instagram_follow_intro",
            {"username": "psicologa.teste", "intro": intro},
            "Teste de repetição",
        )
        self.assertFalse(rpc("campaignClaim", {})["claimed"])
        rows = memory.db.execute(
            "select status,decision_note from pending_actions where id=?", (pending_id,)
        ).fetchone()
        self.assertEqual("skipped", rows[0])
        self.assertIn("já contactado", rows[1])


if __name__ == "__main__":
    unittest.main()
