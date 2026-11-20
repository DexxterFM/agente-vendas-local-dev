import unittest
from unittest.mock import patch

from scripts.vps import internal_browser_agent


class JobModeCycleTests(unittest.TestCase):
    def setUp(self):
        internal_browser_agent._RECENT_UNREAD_TARGETS.clear()
        internal_browser_agent._LAST_NOTIFICATION_SCAN = 0.0

    @patch("scripts.vps.internal_browser_agent._prospecting_cycle")
    @patch("scripts.vps.internal_browser_agent._process_thread")
    @patch("scripts.vps.internal_browser_agent._sweep_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent.browser.frontend_events", return_value={"events": [], "last": {}})
    @patch("scripts.vps.internal_browser_agent.browser.stalled_page_watchdog", return_value={"stalled": False})
    @patch("scripts.vps.internal_browser_agent.browser.metadata", return_value={"message_pending": False, "notification_pending": False, "message_controls": 0, "notification_controls": 0})
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status", return_value={"running": True, "ready": True})
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_prospecting_turn_never_reads_a_dm(
        self, execute, _status, snapshot, _metadata, _watchdog, _frontend,
        _sweep, process, prospect,
    ):
        execute.side_effect = [
            {"active": True, "prospecting_active": True},
            {"mode": "prospecting"},
            {"mode": "sales", "next_mode": "prospecting", "idle_cycles": 0},
        ]
        snapshot.return_value = {
            "url": "https://www.instagram.com/",
            "authenticated": True,
        }
        prospect.return_value = {
            "prospecting": True,
            "browser": "prospecting-sent",
            "username": "clinica.teste",
        }

        result = internal_browser_agent.cycle(mode="prospecting")

        prospect.assert_called_once_with()
        process.assert_not_called()
        self.assertEqual("prospecting-sent", result["browser"])
        self.assertEqual("sales", result["mode"])
        self.assertIn("browserModeComplete", [call.args[0] for call in execute.call_args_list])

    @patch("scripts.vps.internal_browser_agent._prospecting_cycle")
    @patch("scripts.vps.internal_browser_agent._process_thread")
    @patch("scripts.vps.internal_browser_agent._sweep_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent._notification_scan_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent.browser.frontend_events", return_value={"events": [], "last": {}})
    @patch("scripts.vps.internal_browser_agent.browser.stalled_page_watchdog", return_value={"stalled": False})
    @patch("scripts.vps.internal_browser_agent.browser.metadata", return_value={"message_pending": False, "notification_pending": False, "message_controls": 0, "notification_controls": 0})
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status", return_value={"running": True, "ready": True})
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_sales_turn_never_starts_prospecting(
        self, execute, _status, snapshot, _metadata, _watchdog, _frontend,
        _scan, _sweep, process, prospect,
    ):
        execute.side_effect = [
            {"active": True, "prospecting_active": True},
            {"mode": "sales"},
            {"mode": "prospecting", "next_mode": "sales", "idle_cycles": 0},
        ]
        snapshot.return_value = {
            "url": "https://www.instagram.com/direct/inbox",
            "authenticated": True,
        }
        process.return_value = {"processed": True, "replied": True}

        result = internal_browser_agent.cycle(mode="sales")

        prospect.assert_not_called()
        self.assertEqual("ready", result["browser"])
        self.assertEqual("prospecting", result["mode"])
        self.assertIn("browserModeIdle", [call.args[0] for call in execute.call_args_list])

    @patch("scripts.vps.internal_browser_agent._prospecting_cycle")
    @patch("scripts.vps.internal_browser_agent._process_thread")
    @patch("scripts.vps.internal_browser_agent._open_inbox")
    @patch("scripts.vps.internal_browser_agent._sweep_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent._notification_scan_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent.browser.frontend_events", return_value={"events": [], "last": {}})
    @patch("scripts.vps.internal_browser_agent.browser.stalled_page_watchdog", return_value={"stalled": False})
    @patch("scripts.vps.internal_browser_agent.browser.metadata", return_value={"message_pending": False, "notification_pending": False, "message_controls": 0, "notification_controls": 0})
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status", return_value={"running": True, "ready": True})
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_no_interaction_never_opens_dm_or_sends(
        self, execute, _status, snapshot, _metadata, _watchdog, _frontend,
        _scan, _sweep, open_inbox, process, prospect,
    ):
        # Sem bolinha vermelha, sem notificação e sem evento frontend, o cycle
        # não deve abrir a caixa de entrada nem processar conversa alguma.
        execute.side_effect = [
            {"active": True, "prospecting_active": True},
            {"mode": "sales"},
            {"mode": "prospecting", "next_mode": "sales", "idle_cycles": 0},
        ]
        snapshot.return_value = {
            "url": "https://www.instagram.com/",
            "authenticated": True,
        }

        result = internal_browser_agent.cycle(mode="sales")

        open_inbox.assert_not_called()
        process.assert_not_called()
        prospect.assert_not_called()
        self.assertEqual("ready", result["browser"])


if __name__ == "__main__":
    unittest.main()
