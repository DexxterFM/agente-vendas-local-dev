import hashlib
import unittest
from unittest.mock import patch

from scripts.vps import internal_browser_agent as agent


class InternalBrowserAgentTests(unittest.TestCase):
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_cycle_waits_for_login_without_navigation(self, execute, status, snapshot):
        execute.return_value = {"active": True}
        status.return_value = {"running": True, "ready": True}
        snapshot.return_value = {"authenticated": False, "url": "https://www.instagram.com/accounts/login/"}

        result = agent.cycle()

        self.assertEqual({"active": True, "browser": "waiting-login"}, result)
        execute.assert_called_once_with("agentStatus", {})

    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_cycle_keeps_identity_transition_untouched(self, execute, status, snapshot):
        execute.return_value = {"active": True}
        status.return_value = {"running": True, "ready": True}
        # Algumas páginas intermediárias não exibem campos de senha. Mesmo
        # assim, nunca podem liberar varredura/navegação do agente.
        snapshot.return_value = {"authenticated": True, "url": "https://www.facebook.com/login/identify/"}

        result = agent.cycle()

        self.assertEqual({"active": True, "browser": "waiting-login"}, result)
        execute.assert_called_once_with("agentStatus", {})

    @patch("scripts.vps.internal_browser_agent._page")
    def test_thread_snapshot_builds_stable_message_ids(self, page):
        page.return_value = {
            "url": "https://www.instagram.com/direct/t/thread-1/",
            "thread_id": "thread-1",
            "username": "clinica.exemplo",
            "messages": [
                {"text": " Olá   Denis ", "direction": "incoming", "ordinal": 1},
                {"text": "Olá! Tudo bem?", "direction": "outgoing", "ordinal": 1},
            ],
        }

        snapshot = agent._thread_snapshot()

        self.assertEqual("thread-1", snapshot["thread_id"])
        self.assertEqual("clinica.exemplo", snapshot["username"])
        self.assertEqual("Olá Denis", snapshot["messages"][0]["text"])
        expected = hashlib.sha256("thread-1\0incoming\0Olá Denis\0".encode() + b"1").hexdigest()
        self.assertEqual(expected, snapshot["messages"][0]["id"])

    @patch("scripts.vps.internal_browser_agent._thread_snapshot")
    @patch("scripts.vps.internal_browser_agent._message_count")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch("scripts.vps.internal_browser_agent._composer_center")
    def test_send_confirms_visible_outgoing_bubble(self, center, action, wait, page, count, snapshot):
        center.return_value = {"x": 500, "y": 700}
        count.return_value = 1
        page.side_effect = lambda expression: "texto" if "activeElement" in expression else "https://www.instagram.com/direct/t/a/"
        snapshot.return_value = {"messages": [{"direction": "outgoing", "text": "texto"}]}

        result = agent._send_bubble("texto", "https://www.instagram.com/direct/t/a/")

        self.assertTrue(result["sent"])
        self.assertEqual("virtual-keyboard-visible-bubble", result["method"])
        self.assertEqual("click", action.call_args_list[0].args[0]["kind"])
        self.assertEqual("type", action.call_args_list[1].args[0]["kind"])
        self.assertEqual("Enter", action.call_args_list[2].args[0]["key"])


if __name__ == "__main__":
    unittest.main()
