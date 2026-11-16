import unittest
from unittest.mock import patch

from scripts.vps import internal_browser_agent


class InternalBrowserAgentMetadataTests(unittest.TestCase):
    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_notification_candidates_are_normalized_and_deduplicated(self, action, page, _wait):
        page.return_value = ["Clinica.Teste", "clinica.teste", "fono_legal"]

        result = internal_browser_agent._notification_candidates()

        self.assertEqual(["clinica.teste", "fono_legal"], result)
        action.assert_called_once_with({"kind": "navigate", "url": "https://www.instagram.com/notifications/"})

    @patch("scripts.vps.internal_browser_agent._sweep_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent._capture_notification_actions")
    @patch("scripts.vps.internal_browser_agent.browser.metadata")
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_cycle_propagates_notification_metadata_without_opening_dm(
        self, execute, status, snapshot, metadata, capture, _sweep_due
    ):
        execute.return_value = {"active": True}
        status.return_value = {"running": True, "ready": True}
        snapshot.return_value = {"url": "https://www.instagram.com/", "authenticated": True}
        metadata.return_value = {
            "message_pending": False,
            "notification_pending": True,
            "message_controls": 3,
            "notification_controls": 1,
        }
        capture.return_value = {"notification_candidates": 1, "notification_queued": 1}

        result = internal_browser_agent.cycle()

        self.assertEqual("ready", result["browser"])
        self.assertTrue(result["notification_pending"])
        self.assertFalse(result["message_pending"])
        self.assertEqual(1, result["notification_controls"])
        self.assertEqual(1, result["notification_queued"])
        capture.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
