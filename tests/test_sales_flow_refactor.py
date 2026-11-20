import unittest
from unittest.mock import MagicMock

from core.sales_flow_engine import SalesFlowEngine


class TestSalesFlowRefactor(unittest.TestCase):
    def setUp(self):
        self.engine = SalesFlowEngine()

    def test_no_false_positive_on_sim_and_nao_in_discovery(self):
        # "Sim" em DISCOVERY não deve entregar token prematuramente
        res_sim = self.engine.route("clinica_teste", "Sim", current_stage="DISCOVERY")
        self.assertEqual(res_sim["intent"], "DISCOVERY_QUALIFY")
        self.assertIsNone(res_sim["action"])

        # "Não" em DISCOVERY avança para OFFER sem disparar opt-out
        res_nao = self.engine.route("clinica_teste", "Ainda não usamos nada", current_stage="DISCOVERY")
        self.assertEqual(res_nao["intent"], "NO_APP_OFFER")
        self.assertEqual(res_nao["next_stage"], "OFFER")

    def test_edition_qualification_before_token_issue(self):
        # Lead diz "eu quero" na oferta -> pergunta edição antes de gerar token
        res_offer = self.engine.route("clinica_teste", "Eu quero testar", current_stage="OFFER")
        self.assertEqual(res_offer["intent"], "QUALIFY_EDITION")
        self.assertEqual(res_offer["next_stage"], "EDITION_SELECT")
        self.assertIsNone(res_offer["action"])

        # Lead responde "clínica com equipe" -> gera token multiprofessional
        res_multi = self.engine.route("clinica_teste", "Somos uma clínica com 6 terapeutas", current_stage="EDITION_SELECT")
        self.assertEqual(res_multi["action"], "GENERATE_TOKEN_MULTI")
        self.assertEqual(res_multi["next_stage"], "TOKEN_SENT")

    def test_thanks_after_token_does_not_regress_funnel(self):
        # Agradecimento após receber token não retrocede para pergunta de descoberta
        res = self.engine.route("clinica_teste", "Muito obrigado!", current_stage="TOKEN_SENT")
        self.assertEqual(res["intent"], "POST_TOKEN_THANKS")
        self.assertEqual(res["next_stage"], "TOKEN_SENT")
        self.assertNotIn("app para", res["bubbles"][0].lower())
        self.assertNotIn("app ou", res["bubbles"][0].lower())

    def test_global_interruptions_override_any_stage(self):
        # Opt-out em EDITION_SELECT
        res_opt = self.engine.route("clinica_teste", "Não quero mais receber mensagens", current_stage="EDITION_SELECT")
        self.assertEqual(res_opt["intent"], "OPT_OUT")
        self.assertEqual(res_opt["action"], "MARK_OPT_OUT")

        # Cobrança em OFFER retorna 3 balões
        res_bill = self.engine.route("clinica_teste", "Vocês mandam boleto?", current_stage="OFFER")
        self.assertEqual(res_bill["intent"], "BILLING_FLOW")
        self.assertEqual(len(res_bill["bubbles"]), 3)

    def test_operator_learning_reuses_strategy_in_similar_context(self):
        from core.flow_studio import FlowStudio
        fs = FlowStudio.__new__(FlowStudio)
        fs.memory = None
        # Mock memory
        import unittest.mock as mock
        fs.memory = mock.MagicMock()
        fs.memory.get_setting.return_value = "[]"
        if hasattr(fs, "learn_from_operator"):
            fs.learn_from_operator(
                trigger_text="Vocês integram com guia TISS de convênio médico?",
                response_text="Sim! O ERP Clínica TEA possui faturamento TISS completo para convênios.",
                stage="OFFER",
            )
            matched = fs.match("Vocês integram guia TISS convênio médico?", stage="OFFER")
            self.assertIsNotNone(matched)
            self.assertIn("TISS", matched)

    def test_human_rate_limiter_enforces_hourly_quota(self):
        from core.job_scheduler import HumanRateLimiter
        import unittest.mock as mock
        memory = mock.MagicMock()
        # Simula que _count_actions retorna 20 (acima do limite de 15 para follow)
        memory.db.execute.return_value.fetchone.return_value = (20,)
        memory.get_setting.return_value = ""
        limiter = HumanRateLimiter(memory)
        allowed, _, _ = limiter.can_perform_action("follow")
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
