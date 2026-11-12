import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import Memory, parse_decision
from sales_logic import draft_followup, qualify_lead


class CoreTests(unittest.TestCase):
    def test_plain_text_is_answer(self):
        self.assertEqual(parse_decision("Olá cliente"), {"action": "answer", "text": "Olá cliente"})

    def test_unknown_action_is_blocked(self):
        decision = parse_decision('{"action":"send_message","text":"oi"}')
        self.assertEqual(decision["action"], "answer")

    def test_navigation_requires_structured_json(self):
        decision = parse_decision('resultado {"action":"navigate","url":"https://example.com"}')
        self.assertEqual(decision["url"], "https://example.com")

    def test_memory_persists_messages(self):
        with tempfile.TemporaryDirectory() as folder:
            old = os.getcwd()
            os.chdir(folder)
            try:
                memory = Memory(os.path.join(folder, "test.sqlite3"))
                memory.add("user", "teste")
                self.assertEqual(memory.recent(), [("user", "teste")])
            finally:
                memory.db.close()
                os.chdir(old)

    def test_sales_entities_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            old = os.getcwd()
            os.chdir(folder)
            try:
                memory = Memory(os.path.join(folder, "test.sqlite3"))
                lead_id = memory.add_lead("Cliente teste", "5511999999999", "interessado")
                product_id = memory.add_product("Produto teste", 99.90)
                opportunity_id = memory.add_opportunity(lead_id, product_id, 99.90, "enviar proposta")
                followup_id = memory.add_followup(lead_id, "2030-01-01", "retornar contato")
                self.assertGreater(lead_id, 0)
                self.assertGreater(product_id, 0)
                self.assertGreater(opportunity_id, 0)
                self.assertGreater(followup_id, 0)
                self.assertEqual(memory.list_leads()[0][1], "Cliente teste")
            finally:
                memory.db.close()
                os.chdir(old)

    def test_lead_qualification_is_deterministic(self):
        result = qualify_lead("Quero comprar hoje, qual o preço e posso pagar por Pix?")
        self.assertEqual(result.stage, "hot")
        self.assertGreaterEqual(result.score, 60)

    def test_followup_uses_stage(self):
        text = draft_followup("Ana", "Plano Premium", "warm")
        self.assertIn("Ana", text)
        self.assertIn("Plano Premium", text)


if __name__ == "__main__":
    unittest.main()
