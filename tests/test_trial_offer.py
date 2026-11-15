import tempfile
import unittest
from pathlib import Path

from core.memory import Memory
from core.trial_offer import get_trial_offer, save_trial_offer


class TrialOfferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.memory = Memory(Path(self.temp.name) / "agent.sqlite3")

    def tearDown(self):
        self.memory.close()
        self.temp.cleanup()

    def test_configured_links_replace_defaults_and_persist(self):
        saved = save_trial_offer(self.memory, {
            "company_name": "AvanthCode",
            "company_url": "https://avanthcode.com",
            "activation": "Ative pelo link para iniciar os três meses.",
            "clinic": {"name": "Multi", "url": "https://avanthcode.com/multi-teste"},
            "professional": {"name": "Pro", "url": "https://avanthcode.com/pro-teste"},
        })
        self.assertEqual(saved["clinic"]["url"], "https://avanthcode.com/multi-teste")
        self.assertEqual(get_trial_offer(self.memory)["professional"]["url"], "https://avanthcode.com/pro-teste")

    def test_rejects_non_https_trial_link(self):
        offer = get_trial_offer(self.memory)
        offer["clinic"]["url"] = "http://invalid.example"
        with self.assertRaises(ValueError):
            save_trial_offer(self.memory, offer)
