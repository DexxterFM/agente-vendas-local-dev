import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.agent import Agent
from core.config import load_config
from core.instagram import build_plan, normalize_profile_url
from core.memory import Memory
from core.playbook import (
    build_playbook_context,
    draft_objection_reply,
    search_playbook,
)
from core.style import (
    analyze_style,
    draft_with_style,
    greeting_for_hour,
    human_delay_seconds,
)


class StyleTests(unittest.TestCase):
    def test_style_profile_and_prompt(self):
        samples = [
            "Boa tarde! Tudo bem? Quero entender melhor a proposta.",
            "Boa tarde, tudo bem? Vou verificar o valor e te retorno.",
            "Boa tarde! Consegui ver o material, obrigado.",
        ]
        profile = analyze_style(samples)
        self.assertEqual(profile.sample_count, 3)
        self.assertTrue(profile.ready)
        self.assertEqual(profile.typical_greeting, "boa tarde")
        self.assertGreater(profile.avg_words, 0)
        self.assertIn("Estilo do operador", profile.prompt())
        self.assertIn("boa tarde", profile.summary())

    def test_draft_with_style_removes_emoji(self):
        profile = analyze_style(["Boa tarde, tudo bem? Vamos conversar."] * 3)
        result = draft_with_style("Tudo ótimo! 😀", profile, greeting="Boa tarde")
        self.assertNotIn("😀", result)
        self.assertIn("Boa tarde", result)

    def test_explicit_greeting_wins_over_learned_greeting(self):
        profile = analyze_style(["Boa noite, tudo bem?", "Boa noite! Vamos conversar."] * 2)
        self.assertEqual(profile.typical_greeting, "boa noite")
        result = draft_with_style("Podemos conversar?", profile, greeting="Bom dia")
        self.assertTrue(result.startswith("Bom dia"))
        self.assertNotIn("Boa noite", result)

    def test_greeting_and_delay(self):
        self.assertEqual(greeting_for_hour(8), "Bom dia")
        self.assertEqual(greeting_for_hour(14), "Boa tarde")
        self.assertEqual(greeting_for_hour(21), "Boa noite")
        self.assertGreaterEqual(human_delay_seconds("mensagem curta"), 3)
        self.assertLessEqual(human_delay_seconds("palavra " * 200), 20)


class PlaybookTests(unittest.TestCase):
    def test_objection_search(self):
        entries = search_playbook("A pessoa disse que já usa outro aplicativo")
        keys = {entry.key for entry in entries}
        self.assertIn("objection-other-app", keys)
        reply = draft_objection_reply("já uso outro app", "Plano X")
        self.assertIn("o que você mais valoriza", reply)

    def test_custom_knowledge_is_retrieved(self):
        custom = [
            {
                "id": 1,
                "title": "Objeção de contrato",
                "content": "Explique a política de cancelamento sem inventar prazos.",
                "tags": "contrato cancelamento objeção",
                "active": True,
            }
        ]
        entries = search_playbook("como responder sobre contrato", custom)
        self.assertTrue(any(entry.category == "personalizado" for entry in entries))
        context = build_playbook_context(entries)
        self.assertIn("política de cancelamento", context)

    def test_comparison_guidance_is_ethical(self):
        entries = search_playbook("comparativo print concorrente")
        self.assertTrue(entries)
        joined = " ".join(entry.guidance for entry in entries)
        self.assertIn("verificáveis", joined)
        self.assertIn("Nunca", joined)


class InstagramTests(unittest.TestCase):
    def test_profile_normalization(self):
        self.assertEqual(
            normalize_profile_url("@empresa.teste"),
            "https://www.instagram.com/empresa.teste/",
        )
        self.assertEqual(
            normalize_profile_url("https://www.instagram.com/empresa.teste/"),
            "https://www.instagram.com/empresa.teste/",
        )
        for value in (
            "http://instagram.com/empresa",
            "https://example.com/empresa",
            "https://www.instagram.com/p/abc123/",
            "https://www.instagram.com/",
        ):
            with self.assertRaises(ValueError):
                normalize_profile_url(value)

    def test_plan_contains_confirmation_only_actions(self):
        plan = build_plan(
            "https://www.instagram.com/loja.teste/",
            "Loja de moda. Link na bio. Atendimento por WhatsApp.",
            product="Plano X",
            hour=15,
            name="Ana",
        )
        self.assertEqual(plan.insight.niche, "moda")
        self.assertIn("link na bio", plan.insight.signals)
        actions = {action.action for action in plan.actions}
        self.assertEqual(actions, {"follow", "comment", "send_message", "repost"})
        self.assertTrue(all(action.requires_confirmation for action in plan.actions))
        self.assertIn("Boa tarde", plan.initial_message)
        self.assertGreaterEqual(plan.delay_seconds, 3)
        self.assertTrue(plan.checklist)
        payload = plan.actions[0].payload(plan.insight)
        self.assertEqual(payload["execution"], "disabled")
        self.assertTrue(payload["requires_confirmation"])


class LearningMemoryTests(unittest.TestCase):
    def test_style_and_knowledge_are_local_and_removable(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / "learning.sqlite3")
            try:
                first = memory.add_style_sample("Boa tarde, tudo bem?", "manual")
                second = memory.add_style_sample("token=segredo123", "manual")
                self.assertGreater(first, 0)
                self.assertGreater(second, 0)
                texts = memory.style_texts(10)
                self.assertTrue(any("[REDACTED]" in text for text in texts))
                knowledge_id = memory.add_knowledge(
                    "Objeção de preço",
                    "Pergunte o orçamento antes de falar de desconto.",
                    "preço desconto",
                )
                self.assertGreater(knowledge_id, 0)
                entries = memory.knowledge_entries()
                self.assertEqual(entries[0]["title"], "Objeção de preço")
                memory.delete_knowledge(knowledge_id)
                self.assertEqual(memory.knowledge_entries(), [])
                self.assertEqual(memory.clear_style_samples(), 2)
                self.assertEqual(memory.style_texts(), [])
            finally:
                memory.close()

    def test_agent_prompt_includes_authorized_learning(self):
        captured = {}

        class StubOllama:
            def chat(self, messages, format_json=True):
                captured["messages"] = messages
                return '{"action":"answer","text":"Entendi."}'

        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / "agent.sqlite3")
            try:
                memory.add_style_sample("Boa tarde! Vamos direto ao ponto.", "manual")
                memory.add_style_sample("Boa tarde, posso te ajudar?", "manual")
                memory.add_knowledge(
                    "Concorrente",
                    "Nunca critique o concorrente; compare apenas fatos verificáveis.",
                    "concorrente comparação",
                )
                agent = Agent(memory, load_config(), ollama=StubOllama())
                answer = agent.run("O cliente disse que já usa um concorrente.")
                self.assertEqual(answer, "Entendi.")
                system = captured["messages"][0]["content"]
                self.assertIn("Estilo do operador", system)
                self.assertIn("Nunca critique o concorrente", system)
                self.assertIn("confirmação humana", system)
            finally:
                memory.close()


if __name__ == "__main__":
    unittest.main()
