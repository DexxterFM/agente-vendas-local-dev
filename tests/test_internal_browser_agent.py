import unittest
from unittest.mock import patch

from scripts.vps import internal_browser_agent


class InternalBrowserAgentMetadataTests(unittest.TestCase):
    @patch("scripts.vps.internal_browser_agent._page")
    def test_inbox_targets_prioritize_blue_unread_metadata(self, page):
        page.return_value = [
            {"href": "https://www.instagram.com/direct/t/read/", "label": "Conversa antiga", "unread": False, "bold": False, "blue": False},
            {"href": "https://www.instagram.com/direct/t/new/", "label": "Mensagem nova", "unread": True, "bold": True, "blue": True},
        ]

        targets = internal_browser_agent._inbox_targets()

        self.assertEqual("https://www.instagram.com/direct/t/new/", targets[0]["href"])
        self.assertTrue(targets[0]["unread"])
        self.assertTrue(targets[0]["bold"])

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

    @patch("scripts.vps.internal_browser_agent._sweep_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent._process_thread", return_value={"processed": True, "replied": True})
    @patch("scripts.vps.internal_browser_agent._open_target", return_value=True)
    @patch("scripts.vps.internal_browser_agent._inbox_targets")
    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch("scripts.vps.internal_browser_agent.browser.metadata")
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_cycle_opens_blue_unread_row_instead_of_first_visible_conversation(
        self, execute, status, snapshot, metadata, action, _wait, inbox_targets,
        open_target, process_thread, _sweep_due
    ):
        execute.return_value = {"active": True}
        status.return_value = {"running": True, "ready": True}
        snapshot.return_value = {"url": "https://www.instagram.com/", "authenticated": True}
        metadata.return_value = {
            "message_pending": True, "notification_pending": False,
            "message_controls": 1, "notification_controls": 1,
        }
        unread = {"href": "https://www.instagram.com/direct/t/new/", "label": "Nova", "unread": True, "bold": True, "blue": True}
        inbox_targets.return_value = [unread, {"href": "https://www.instagram.com/direct/t/old/", "label": "Antiga", "unread": False}]

        result = internal_browser_agent.cycle()

        self.assertEqual("message", result["browser"])
        self.assertEqual(1, result["inbox_unread"])
        open_target.assert_called_once_with(unread)
        process_thread.assert_called_once_with("unread-row-metadata")

    @patch("scripts.vps.internal_browser_agent._sweep_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent._process_thread")
    @patch("scripts.vps.internal_browser_agent._open_target", return_value=True)
    @patch("scripts.vps.internal_browser_agent._inbox_targets")
    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch("scripts.vps.internal_browser_agent.browser.metadata")
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_open_thread_does_not_block_another_blue_unread_conversation(
        self, execute, status, snapshot, metadata, action, _wait, inbox_targets,
        open_target, process_thread, _sweep_due
    ):
        execute.return_value = {"active": True}
        status.return_value = {"running": True, "ready": True}
        snapshot.return_value = {
            "url": "https://www.instagram.com/direct/t/current/", "authenticated": True,
        }
        metadata.return_value = {
            "message_pending": True, "notification_pending": False,
            "message_controls": 1, "notification_controls": 1,
        }
        unread = {"href": "https://www.instagram.com/direct/t/new/", "label": "Nova", "unread": True, "bold": True, "blue": True}
        inbox_targets.return_value = [unread]
        process_thread.side_effect = [
            {"processed": True, "replied": False, "reason": "no-pending-incoming"},
            {"processed": True, "replied": True},
        ]

        result = internal_browser_agent.cycle()

        self.assertEqual("message", result["browser"])
        self.assertEqual(1, result["inbox_unread"])
        self.assertEqual(
            [unittest.mock.call("open-thread"), unittest.mock.call("unread-row-metadata")],
            process_thread.call_args_list,
        )
        open_target.assert_called_once_with(unread)


if __name__ == "__main__":
    unittest.main()
