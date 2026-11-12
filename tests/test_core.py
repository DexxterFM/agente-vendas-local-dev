import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import Memory, parse_decision


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
                memory = Memory()
                memory.add("user", "teste")
                self.assertEqual(memory.recent(), [("user", "teste")])
            finally:
                memory.db.close()
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
