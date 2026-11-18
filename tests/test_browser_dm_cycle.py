import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.desktop_rpc import BROWSER_BUBBLE_SEPARATOR, execute
from core.memory import Memory


class BrowserDmCycleTests(unittest.TestCase):

    def test_agent_activation_enables_all_approved_dialogue_flows(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            activated = execute("setAgentActive", {"active": True})
            status = execute("agentStatus", {})
            self.assertTrue(activated["automatic_replies"])
            self.assertTrue(status["active"])
            self.assertTrue(status["automatic_replies"])

    def test_payment_concern_is_portuguese_and_reassures_without_auto_charge(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            lead_id = execute("create", {"name": "Clínica", "contact": "clinica.teste"})
            answer = execute("draft", {
                "id": lead_id,
                "browser_history": [
                    {"role": "assistant", "text": "Você ganhou 3 meses grátis."},
                    {"role": "user", "text": "Mas depois não passa automático para o pago?"},
                ],
            })
            parts = answer.split(BROWSER_BUBBLE_SEPARATOR)
            self.assertEqual(3, len(parts))
            self.assertIn("não gera cobrança automática", parts[0])
            self.assertIn("empresa séria e comprometida com a qualidade", parts[1])
            self.assertIn("experiência realmente transformadora", parts[2])
            self.assertNotRegex(answer, r"(?i)okay|we've|next step|lead")

    def test_automatic_reply_authorization_approves_waiting_dm_actions(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            lead_id = execute("create", {"name": "Clínica", "contact": "clinica.teste"})
            queued = execute("queue", {"id": lead_id, "text": "Resposta validada"})
            result = execute("setAutomaticReplies", {"enabled": True})
            campaigns = execute("records", {"type": "campaigns"})
            row = next(item for item in campaigns if item["id"] == queued["id"])
            self.assertEqual(1, result["approved_waiting"])
            self.assertEqual("approved", row["status"])

    def test_browser_history_import_classifies_lead_and_can_backfill(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            imported = execute("browserImportThread", {
                "thread_id": "history-01", "username": "clinica.quente",
                "messages": [
                    {"id": "a" * 64, "direction": "outgoing", "text": "Posso mostrar os planos?"},
                    {"id": "b" * 64, "direction": "incoming", "text": "Qual o preço para contratar hoje?"},
                ],
            })
            self.assertEqual(imported["qualification"]["stage"], "hot")
            self.assertGreaterEqual(imported["qualification"]["score"], 70)
            result = execute("classifyImportedHistory", {})
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["classified"][0]["contact"], "clinica.quente")
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

    def test_browser_cycle_keeps_separate_bubbles_until_sending(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("setAgentActive", {"active": True})
            prize = (
                "! Parabéns voce ganhou 3 meses gratis do nosso app Premium. "
                "Escolha entre o Clinica TEA multiprofissional ou a versão para um profissional."
            )
            messages = [
                {"id": "a" * 64, "direction": "outgoing", "text": "Obrigado por seguir! Diga eu quero"},
                {"id": "b" * 64, "direction": "incoming", "text": "Eu quero"},
                {"id": "c" * 64, "direction": "outgoing", "text": prize},
                {"id": "d" * 64, "direction": "incoming", "text": "Clínica multiprofissional"},
            ]
            cycle = execute("browserScreenCycle", self._payload(messages))
            self.assertTrue(cycle["new_message"])
            self.assertIn(BROWSER_BUBBLE_SEPARATOR, cycle["text"])
            bubbles = cycle["text"].split(BROWSER_BUBBLE_SEPARATOR)
            self.assertEqual(5, len(bubbles))
            for bubble in bubbles:
                self.assertNotIn("[[AGENT_BUBBLE]]", bubble)
            self.assertIn("convite_tres_meses", bubbles[1])
            self.assertIn("51 8054-2244", bubbles[4])

            execute("browserScreenConfirm", {
                "message_key": cycle["message_key"],
                "lead_id": cycle["lead_id"],
                "text": cycle["text"],
                "thread_id": "123456",
            })
            with Memory(Path(folder) / "agent.sqlite3") as memory:
                saved = [row[1] for row in reversed(memory.list_conversations(cycle["lead_id"], 40))
                         if row[0] == "assistant"]
            self.assertEqual(bubbles, saved[-5:])

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

    def test_sweep_memory_keeps_each_browser_message_idempotent(self):
        """A varredura pode reencontrar uma DM; o histórico não pode gerar
        uma segunda resposta para a mesma última mensagem."""
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("setAgentActive", {"active": True})
            thread = "weekly-sweep-thread"
            messages = [
                {"id": "c" * 64, "text": "Vocês já usam algum app para a gestão?", "direction": "outgoing"},
                {"id": "d" * 64, "text": "Ainda não uso nenhum sistema", "direction": "incoming"},
            ]
            payload = {"url": "https://www.instagram.com/direct/t/weekly-sweep-thread/", "thread_id": thread, "username": "clinica_semanal", "message_id": messages[-1]["id"], "message": messages[-1]["text"], "direction": "incoming", "messages": messages}
            first = execute("browserScreenCycle", payload)
            self.assertTrue(first["new_message"])
            execute("browserScreenConfirm", {"message_key": first["message_key"], "lead_id": first["lead_id"], "text": first["text"], "thread_id": thread})
            second = execute("browserScreenCycle", payload)
            self.assertFalse(second["new_message"])

    def test_unavailable_message_is_reaction_only_and_never_gets_sales_text(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("setAgentActive", {"active": True})
            messages = [
                {"id": "e" * 64, "direction": "outgoing", "text": "Obrigado por seguir! Curta nossos conteúdos."},
                {
                    "id": "f" * 64,
                    "direction": "incoming",
                    "text": "Message unavailable This content may have been deleted by its owner or hidden by their privacy settings.",
                },
            ]

            first = execute("browserScreenCycle", self._payload(messages))
            repeated = execute("browserScreenCycle", self._payload(messages))

            self.assertFalse(first["new_message"])
            self.assertEqual("like", first["reaction"])
            self.assertTrue(first["reaction_pending"])
            self.assertEqual("reaction-only-content", first["reason"])
            self.assertFalse(repeated["new_message"])
            with Memory(Path(folder) / "agent.sqlite3") as memory:
                actions = memory.db.execute(
                    "select action,status from pending_actions where action='instagram_message_like_review'"
                ).fetchall()
                self.assertEqual(actions, [("instagram_message_like_review", "pending")])

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
            clinic_link = execute("draft", {"id": lead_id, "browser_history": [
                {"role": "assistant", "text": question}, {"role": "user", "text": "Somos uma clínica multiprofissional"},
                {"role": "assistant", "text": clinic}, {"role": "user", "text": "Sim, pode enviar o link"},
            ]})
            individual = execute("draft", {"id": lead_id, "browser_history": [
                {"role": "assistant", "text": question}, {"role": "user", "text": "Atendo sozinha no consultório"},
            ]})
            individual_link = execute("draft", {"id": lead_id, "browser_history": [
                {"role": "assistant", "text": question}, {"role": "user", "text": "Atendo sozinha no consultório"},
                {"role": "assistant", "text": individual}, {"role": "user", "text": "Claro, pode mandar o link"},
            ]})
            self.assertIn("Posso enviar o link", clinic)
            self.assertEqual(2, len(clinic.split(BROWSER_BUBBLE_SEPARATOR)))
            self.assertIn("erpclinicatea.com/login/admin", clinic_link)
            self.assertIn("plano=clinica-multiprofissional", clinic_link)
            self.assertIn("convite_tres_meses", clinic_link)
            clinic_parts = clinic_link.split(BROWSER_BUBBLE_SEPARATOR)
            self.assertEqual(5, len(clinic_parts))
            self.assertIn("convite_tres_meses", clinic_parts[1])
            self.assertIn("3 dias", clinic_parts[2])
            self.assertIn("dados saõ criptografados", clinic_parts[3])
            self.assertIn("51 8054-2244", clinic_parts[4])
            self.assertIn("Posso enviar o link", individual)
            self.assertIn("erpclinicatea.com/login/admin", individual_link)
            self.assertIn("plano=profissional", individual_link)
            self.assertIn("3 meses grátis", individual_link)
            self.assertEqual(5, len(individual_link.split(BROWSER_BUBBLE_SEPARATOR)))

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

    def test_partnership_and_supplier_use_two_natural_bubbles(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            from core.desktop_rpc import BROWSER_BUBBLE_SEPARATOR
            lead_id = execute("create", {"name": "Contato", "contact": "contato"})
            supplier = execute("draft", {"id": lead_id, "browser_history": [
                {"role": "user", "text": "Olá, oferecemos um produto que pode interessar vocês."},
            ]})
            partnership = execute("draft", {"id": lead_id, "browser_history": [
                {"role": "user", "text": "Gostaríamos de propor uma parceria."},
            ]})
            closing = execute("draft", {"id": lead_id, "browser_history": [
                {"role": "user", "text": "Obrigado pela atenção, até mais."},
            ]})
            self.assertIn(BROWSER_BUBBLE_SEPARATOR, supplier)
            self.assertIn("me explicar do que se trata", supplier)
            self.assertIn(BROWSER_BUBBLE_SEPARATOR, partnership)
            self.assertIn("abertos a parcerias", partnership)
            self.assertEqual(closing, "Muito obrigado pela oportunidade! Um grande abraço e fica com Deus!")

    def test_proposal_analysis_creates_one_three_day_followup(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            lead_id = execute("create", {"name": "Clínica", "contact": "clinica"})
            history = [{"role": "user", "text": "Vamos analisar a proposta com a equipe."}]
            answer = execute("draft", {"id": lead_id, "browser_history": history})
            self.assertIn("Fico à disposição", answer)
            self.assertEqual(len(execute("followupRecords", {})), 1)
            item = execute("followupRecords", {})[0]
            self.assertEqual(item["task"], "Retomar proposta analisada em 3 dias")
            self.assertIn("Já tem um retorno", item["draft"])
            execute("draft", {"id": lead_id, "browser_history": history})
            self.assertEqual(len(execute("followupRecords", {})), 1)

    def test_campaign_claim_is_exclusive_and_records_result(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            created = execute("campaignDiscover", {"profiles": [{
                "username": "clinica.teste", "text": "Clínica multidisciplinar TEA", "following": False,
            }]})["created"]
            self.assertEqual(len(created), 1)
            claimed = execute("campaignClaim", {})
            self.assertTrue(claimed["claimed"])
            self.assertEqual(claimed["payload"]["username"], "clinica.teste")
            self.assertFalse(execute("campaignClaim", {})["claimed"])
            self.assertEqual(execute("campaignConfirm", {"id": claimed["id"], "state": "sent"})["state"], "sent")

    def test_campaign_failure_requeues_twice_then_requires_review(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            created = execute("campaignDiscover", {"profiles": [{
                "username": "clinica.teste", "text": "Clínica multidisciplinar TEA", "following": False,
            }]})["created"]
            claimed = execute("campaignClaim", {})
            self.assertTrue(claimed["claimed"])
            execute("campaignStage", {"id": claimed["id"], "stage": "dm"})

            first = execute("campaignFail", {"id": claimed["id"], "note": "Conversa ainda carregando"})
            self.assertEqual("pending", first["state"])
            self.assertEqual(1, first["attempts"])
            reclaimed = execute("campaignClaim", {})
            self.assertTrue(reclaimed["claimed"])
            self.assertEqual("dm", reclaimed["stage"])

            second = execute("campaignFail", {"id": claimed["id"], "note": "Conversa ainda carregando"})
            self.assertEqual("pending", second["state"])
            self.assertEqual(2, second["attempts"])
            execute("campaignClaim", {})
            third = execute("campaignFail", {"id": claimed["id"], "note": "Conversa ainda carregando"})
            self.assertEqual("needs_check", third["state"])
            self.assertEqual(3, third["attempts"])
            self.assertFalse(execute("campaignClaim", {})["claimed"])

    def test_pending_follower_resumes_and_records_last_message(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("setAgentActive", {"active": True})
            first = execute("followerCycle", {"username": "clinica.teste", "profile": {
                "username": "clinica.teste", "bio": "Clínica multidisciplinar TEA", "text": "Clínica ABA",
            }})
            resumed = execute("followerCycle", {"username": "clinica.teste", "profile": {}})
            self.assertTrue(resumed["new_follower"])
            self.assertTrue(resumed["resume"])
            self.assertEqual(resumed["text"], first["text"])
            confirmed = execute("followerConfirm", {"username": "clinica.teste", "text": first["text"]})
            self.assertTrue(confirmed["message_recorded"])
            self.assertEqual(execute("agentStatus", {})["prospecting_active"], False)
            execute("setProspectingActive", {"active": True})
            self.assertTrue(execute("agentStatus", {})["prospecting_active"])
            self.assertFalse(execute("followerCycle", {"username": "clinica.teste", "profile": {}})["new_follower"])

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
                answer.split(BROWSER_BUBBLE_SEPARATOR),
                [
                    "Tudo bem! Espero que sim 😊",
                    "Por acaso já utiliza algum app ou programa para administrar sua clínica?",
                ],
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
                "Obrigado por seguir! Parabéns pelo trabalho da clínica! Tenho um presente para a sua equipe. "
                "Diga “eu quero” que te mando para você. 😊",
            )

            reserved = execute("followerCycle", {"username": "clinica.nova"})
            self.assertTrue(reserved["new_follower"])
            self.assertTrue(reserved["resume"])
            self.assertEqual(reserved["text"], first["text"])

            execute("followerConfirm", {"username": "clinica.nova", "text": first["text"]})
            sent = execute("followerCycle", {"username": "clinica.nova"})
            self.assertFalse(sent["new_follower"])
            self.assertEqual(sent["status"], "sent")

    def test_follower_gift_offers_version_choice_then_sends_link(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            execute("setAgentActive", {"active": True})
            greeting = execute("followerCycle", {
                "username": "clinica.nova",
                "profile": {"bio": "Clínica multidisciplinar com equipe ABA"},
            })
            execute("followerConfirm", {
                "username": "clinica.nova", "text": greeting["text"],
            })
            with Memory(Path(folder) / "agent.sqlite3") as memory:
                lead_id = next(row[0] for row in memory.list_leads() if row[2] == "clinica.nova")
            prize = execute("draft", {
                "id": lead_id,
                "browser_history": [
                    {"role": "assistant", "text": greeting["text"]},
                    {"role": "user", "text": "Eu quero"},
                ],
            })
            self.assertEqual(
                "! Parabéns voce ganhou 3 meses gratis do nosso app Premium. "
                "Escolha entre o Clinica TEA multiprofissional ou a versão para um profissional.",
                prize,
            )
            answer = execute("draft", {
                "id": lead_id,
                "browser_history": [
                    {"role": "assistant", "text": greeting["text"]},
                    {"role": "user", "text": "Eu quero"},
                    {"role": "assistant", "text": prize},
                    {"role": "user", "text": "Clínica multiprofissional"},
                ],
            })
            parts = answer.split(BROWSER_BUBBLE_SEPARATOR)
            self.assertEqual(len(parts), 5)
            self.assertIn("Multiprofissional", parts[0])
            self.assertNotIn("erpclinicatea.com/login/admin", parts[0])
            self.assertIn("erpclinicatea.com/login/admin", parts[1])
            self.assertEqual(
                'Aviso esse link é valido por 3 dias. Caso não seja ativado voce perde o premios 😢',
                parts[2],
            )
            self.assertEqual(
                'Essa é uma tivação segura seus dados saõ criptografados e possuimos um sitema demonitormento. Sem uso de dados bancarios e sem uso de cartão.',
                parts[3],
            )
            self.assertEqual(
                'A intalação pode receber suporte para duvidas. o tempo de resposta pode varia de acordo com o fluxo de atendimentos. whatsapp assintencia 51 8054-2244',
                parts[4],
            )

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
            self.assertIn("Tenho um presente", professional["text"])
            self.assertNotIn("ERP Clínica TEA Pro", professional["text"])

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
