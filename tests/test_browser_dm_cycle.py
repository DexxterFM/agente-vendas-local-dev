import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.desktop_rpc import execute
from core.memory import Memory


class BrowserDmCycleTests(unittest.TestCase):
    def _payload(self, messages):
        latest = messages[-1]
        return {
            "url": "https://www.instagram.com/direct/t/123456/",
            "thread_id": "123456",
            "username": "clinica.teste",
            "message_id": latest["id"],
            "message": latest["text"],
            "direction": latest["direction"],
            "messages": messages,
        }

    def test_full_visible_history_drives_reply_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("setAgentActive", {"active": True})
            messages = [
                {"id": "a" * 64, "direction": "outgoing", "text": "Vocês já usam algum app para a gestão?"},
                {"id": "b" * 64, "direction": "incoming", "text": "Sim"},
            ]
            cycle = execute("browserScreenCycle", self._payload(messages))
            self.assertTrue(cycle["new_message"])
            self.assertIn("Qual app", cycle["text"])

            execute(
                "browserScreenConfirm",
                {
                    "message_key": cycle["message_key"],
                    "lead_id": cycle["lead_id"],
                    "text": cycle["text"],
                    "thread_id": "123456",
                },
            )
            repeated = execute("browserScreenCycle", self._payload(messages))
            self.assertFalse(repeated["new_message"])

            with Memory(Path(folder) / "agent.sqlite3") as memory:
                history = list(reversed(memory.list_conversations(cycle["lead_id"], 20)))
                self.assertEqual([row[0] for row in history], ["assistant", "user", "assistant"])
                self.assertEqual(history[0][1], "Vocês já usam algum app para a gestão?")
                contexts = memory.db.execute(
                    "select value from settings where key like 'sales.agent.browser_context:%'"
                ).fetchall()
                self.assertEqual(len(contexts), 1)
                self.assertIn('"text": "Sim"', contexts[0][0])

    def test_repeated_literal_message_is_stored_when_its_stable_id_is_new(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("setAgentActive", {"active": True})
            first = [
                {"id": "a" * 64, "direction": "outgoing", "text": "Vocês já usam algum app?"},
                {"id": "b" * 64, "direction": "incoming", "text": "Sim"},
            ]
            cycle = execute("browserScreenCycle", self._payload(first))
            execute("browserScreenConfirm", {
                "message_key": cycle["message_key"], "lead_id": cycle["lead_id"],
                "text": cycle["text"], "thread_id": "123456",
            })
            second = first + [
                {"id": "c" * 64, "direction": "outgoing", "text": cycle["text"]},
                {"id": "d" * 64, "direction": "incoming", "text": "Sim"},
            ]
            next_cycle = execute("browserScreenCycle", self._payload(second))
            self.assertTrue(next_cycle["new_message"])
            with Memory(Path(folder) / "agent.sqlite3") as memory:
                history = list(reversed(memory.list_conversations(cycle["lead_id"], 20)))
                self.assertEqual(sum(1 for role, text, _ in history if role == "user" and text == "Sim"), 2)
                self.assertEqual(sum(1 for role, text, _ in history if role == "assistant" and text == cycle["text"]), 1)

    def test_short_competitor_name_advances_from_the_previous_question(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            lead_id = execute("create", {"name": "Clínica teste", "contact": "clinica.teste"})
            answer = execute("draft", {
                "id": lead_id,
                "browser_history": [
                    {"role": "assistant", "text": "Qual app ou programa vocês usam hoje?"},
                    {"role": "user", "text": "Clínica ágil"},
                ],
            })
            self.assertIn("Clínica Ágil", answer)
            self.assertIn("ERP Clínica TEA", answer)
            self.assertNotIn("Qual app", answer)

    def test_competitor_cycle_exposes_poster_metadata(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("setAgentActive", {"active": True})
            messages = [
                {"id": "a" * 64, "direction": "outgoing", "text": "Qual sistema vocês usam?"},
                {"id": "b" * 64, "direction": "incoming", "text": "Usamos o Feegow"},
            ]
            cycle = execute("browserScreenCycle", self._payload(messages))
            self.assertEqual(cycle["competitor"]["slug"], "feegow")
            self.assertFalse(cycle["competitor"]["asset_ready"])
            self.assertTrue(cycle["competitor"]["asset_path"].endswith("feegow.png"))

    def test_no_app_starts_product_discovery(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            lead_id = execute("create", {"name": "Clínica teste", "contact": "clinica.teste"})
            answer = execute("draft", {
                "id": lead_id,
                "browser_history": [
                    {"role": "assistant", "text": "Vocês já usam algum app ou programa?"},
                    {"role": "user", "text": "Ainda não"},
                ],
            })
            self.assertIn("salvar muitas horas", answer)
            self.assertIn("cuidar dos seus pacientes", answer)
            self.assertIn("clínica com equipe", answer)

    def test_no_app_variants_follow_the_same_flow(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            lead_id = execute("create", {"name": "Clínica teste", "contact": "clinica.teste"})
            for text in ("Não", "Ainda não", "Nunca", "Estava procurando", "Já usei mas não uso mais"):
                answer = execute("draft", {
                    "id": lead_id,
                    "browser_history": [
                        {"role": "assistant", "text": "Já utiliza algum app para a gestão?"},
                        {"role": "user", "text": text},
                    ],
                })
                self.assertIn("salvar muitas horas", answer, text)
                self.assertIn("consultório individual", answer, text)

    def test_trial_link_is_routed_by_service_profile(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            lead_id = execute("create", {"name": "Clínica teste", "contact": "clinica.teste"})
            question = "Você atende em uma clínica com equipe ou trabalha em consultório individual?"
            clinic = execute("draft", {"id": lead_id, "browser_history": [
                {"role": "assistant", "text": question}, {"role": "user", "text": "Somos uma clínica multiprofissional"},
            ]})
            individual = execute("draft", {"id": lead_id, "browser_history": [
                {"role": "assistant", "text": question}, {"role": "user", "text": "Atendo sozinha no consultório"},
            ]})
            self.assertIn("erpclinicatea.com/planos", clinic)
            self.assertIn("convite_tres_meses", clinic)
            self.assertIn("produto-profissional?convite=3-meses", individual)
            self.assertIn("3 meses grátis", individual)

    def test_persona_answers_name_and_location(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            lead_id = execute("create", {"name": "Clínica teste", "contact": "clinica.teste"})
            self.assertIn("Denis", execute("draft", {"id": lead_id, "browser_history": [{"role": "user", "text": "Qual é seu nome?"}]}))
            self.assertIn("Porto Alegre", execute("draft", {"id": lead_id, "browser_history": [{"role": "user", "text": "De onde você é?"}]}))
            company = execute("draft", {"id": lead_id, "browser_history": [{"role": "user", "text": "Qual é a sua empresa?"}]})
            self.assertIn("AvanthCode", company)
            self.assertIn("https://avanthcode.com", company)

    def test_positive_reaction_keeps_the_sales_flow_open(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            lead_id = execute("create", {"name": "Clínica teste", "contact": "clinica.teste"})
            answer = execute("draft", {
                "id": lead_id,
                "browser_history": [
                    {"role": "assistant", "text": "O app nasceu da experiência real de famílias e terapeutas."},
                    {"role": "user", "text": "Que legal 🙂"},
                ],
            })
            self.assertIn("Fico feliz", answer)
            self.assertIn("usam algum app", answer)

    def test_opening_thanks_returns_to_app_discovery(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            lead_id = execute("create", {"name": "Clínica Diluz", "contact": "diluz.oficial"})
            answer = execute("draft", {
                "id": lead_id,
                "browser_history": [
                    {
                        "role": "assistant",
                        "text": "Boa tarde! Muito legal seu trabalho! Já utiliza algum app para a gestão do seu espaço de saúde?",
                    },
                    {"role": "user", "text": "Obrigado"},
                ],
            })
            self.assertEqual(
                answer,
                "Você merece! 😊 Mas me conta: já possui algum app ou programa para a gestão da sua clínica?",
            )
            self.assertNotIn("testar", answer.casefold())

    def test_qualified_greeting_returns_to_app_discovery(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            lead_id = execute("create", {"name": "Clínica teste", "contact": "clinica.teste"})
            answer = execute("draft", {
                "id": lead_id,
                "browser_history": [
                    {"role": "assistant", "text": "Muito legal o trabalho da clínica de vocês!"},
                    {"role": "user", "text": "Boa tarde!"},
                ],
            })
            self.assertEqual(
                answer,
                "Tudo bem! Espero que sim 😊 Por acaso já utiliza algum app ou programa para administrar sua clínica? Se já usa, qual?",
            )
            self.assertNotIn("como posso ajudar", answer.casefold())

    def test_new_follower_is_welcomed_once(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("setAgentActive", {"active": True})
            first = execute("followerCycle", {
                "username": "Clinica.Nova",
                "profile": {"name": "Clínica Nova", "bio": "Clínica multidisciplinar com equipe ABA"},
            })
            self.assertTrue(first["new_follower"])
            self.assertEqual(first["username"], "clinica.nova")
            self.assertEqual(first["segment"], "clinic_multi")
            self.assertEqual(
                first["text"],
                "Obrigado por seguir! Parabéns pelo trabalho da clínica! Tenho um presente para a sua equipe: "
                "3 meses grátis do ERP Clínica TEA Multi. Se quiser, é só dizer “eu quero” que já envio para você. 😊",
            )

            reserved = execute("followerCycle", {"username": "clinica.nova"})
            self.assertFalse(reserved["new_follower"])
            self.assertEqual(reserved["status"], "claimed")

            execute("followerConfirm", {"username": "clinica.nova"})
            sent = execute("followerCycle", {"username": "clinica.nova"})
            self.assertFalse(sent["new_follower"])
            self.assertEqual(sent["status"], "sent")

    def test_follower_profile_selects_pro_or_community_message(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("setAgentActive", {"active": True})
            professional = execute("followerCycle", {
                "username": "fono.teste",
                "profile": {"name": "Fono Teste", "bio": "Fonoaudióloga infantil"},
            })
            self.assertEqual(professional["segment"], "professional_pro")
            self.assertIn("ERP Clínica TEA Pro", professional["text"])

            community = execute("followerCycle", {
                "username": "musica.teste",
                "profile": {"name": "Música Teste", "bio": "Banda e música ao vivo"},
            })
            self.assertEqual(community["segment"], "community")
            self.assertEqual(
                community["text"],
                "Obrigado por seguir! Curta nossos conteúdos e compartilhe com amigos para ajudar! 😊",
            )

    def test_failed_follower_welcome_can_be_retried(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("setAgentActive", {"active": True})
            self.assertTrue(execute("followerCycle", {"username": "clinica.teste"})["new_follower"])
            execute("followerReset", {"username": "clinica.teste"})
            self.assertTrue(execute("followerCycle", {"username": "clinica.teste"})["new_follower"])


if __name__ == "__main__":
    unittest.main()
