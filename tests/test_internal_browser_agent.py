import unittest
from unittest.mock import patch

from scripts.vps import internal_browser_agent


class InternalBrowserAgentMetadataTests(unittest.TestCase):
    @patch("scripts.vps.internal_browser_agent._sweep_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent.browser.metadata")
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_cycle_propagates_notification_metadata_without_opening_dm(
        self, execute, status, snapshot, metadata, _sweep_due
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

        result = internal_browser_agent.cycle()

        self.assertEqual("ready", result["browser"])
        self.assertTrue(result["notification_pending"])
        self.assertFalse(result["message_pending"])
        self.assertEqual(1, result["notification_controls"])


if __name__ == "__main__":
    unittest.main()
