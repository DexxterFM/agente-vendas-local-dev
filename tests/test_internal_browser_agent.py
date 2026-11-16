import unittest
from unittest.mock import call, patch

from scripts.vps import internal_browser_agent


class InternalBrowserAgentMetadataTests(unittest.TestCase):
    def setUp(self):
        internal_browser_agent._RECENT_UNREAD_TARGETS.clear()
        internal_browser_agent._LAST_NOTIFICATION_SCAN = 0.0

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._page", return_value="")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_clear_composer_uses_native_select_all_and_backspace(self, action, _page, _wait):
        internal_browser_agent._clear_composer()

        self.assertEqual([
            call({"kind": "key", "key": "SelectAll"}),
            call({"kind": "key", "key": "Backspace"}),
        ], action.call_args_list)

    def test_composer_safe_text_percent_encodes_underscores_only_inside_urls(self):
        text = "Link: https://erpclinicatea.com/planos?utm_source=instagram&utm_campaign=convite_tres_meses. Tudo_certo"

        result = internal_browser_agent._composer_safe_text(text)

        self.assertEqual(
            "Link: https://erpclinicatea.com/planos?utm%5Fsource=instagram&utm%5Fcampaign=convite%5Ftres%5Fmeses. Tudo_certo",
            result,
        )

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._send_button_center", return_value={"x": 1100.0, "y": 835.0})
    @patch("scripts.vps.internal_browser_agent._clear_composer")
    @patch("scripts.vps.internal_browser_agent._message_count", side_effect=[0, 1])
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent._composer_center", return_value={"x": 700.0, "y": 835.0})
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_send_bubble_clears_stale_draft_and_clicks_send_with_native_mouse(
        self, action, _composer, page, _count, clear, _send, _wait
    ):
        expected = "https://www.instagram.com/direct/t/123/"
        page.side_effect = ["rascunho anterior", "novo link", expected, expected]

        result = internal_browser_agent._send_bubble("novo link", expected)

        self.assertTrue(result["sent"])
        clear.assert_called_once_with()
        self.assertEqual([
            call({"kind": "click", "x": 700.0, "y": 835.0}),
            call({"kind": "type", "text": "novo link"}),
            call({"kind": "click", "x": 1100.0, "y": 835.0}),
        ], action.call_args_list)

    @patch("scripts.vps.internal_browser_agent._page", return_value=1)
    def test_message_count_includes_visible_dir_auto_bubbles(self, page):
        self.assertEqual(1, internal_browser_agent._message_count("mensagem enviada"))
        expression = page.call_args.args[0]
        self.assertIn('[dir="auto"]', expression)
        self.assertIn("r.left>450", expression)

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

    def test_recently_checked_blue_row_is_not_reopened_until_it_changes(self):
        target = {"key": "denis.machado", "href": "", "label": "Denis Machado Boa tarde 5 min", "unread": True}
        self.assertEqual([target], internal_browser_agent._actionable_unread([target]))
        internal_browser_agent._RECENT_UNREAD_TARGETS[
            internal_browser_agent._unread_target_key(target)
        ] = internal_browser_agent.time.monotonic() + 300
        self.assertEqual([], internal_browser_agent._actionable_unread([target]))
        changed_time = {**target, "label": "Denis Machado Boa tarde 6 min"}
        self.assertEqual([], internal_browser_agent._actionable_unread([changed_time]))

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent._open_notifications", return_value=True)
    def test_notification_candidates_are_normalized_and_deduplicated(self, open_notifications, page, _wait):
        page.return_value = ["Clinica.Teste", "clinica.teste", "fono_legal"]

        result = internal_browser_agent._notification_candidates()

        self.assertEqual(["clinica.teste", "fono_legal"], result)
        open_notifications.assert_called_once_with()

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_open_target_clicks_existing_spa_anchor_without_page_navigate(self, action, page, _wait):
        page.side_effect = [True, "https://www.instagram.com/direct/t/123/"]

        opened = internal_browser_agent._open_target({
            "href": "https://www.instagram.com/direct/t/123/",
            "label": "Denis Machado Boa tarde",
        })

        self.assertTrue(opened)
        action.assert_not_called()

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

        self.assertEqual("notification", result["browser"])
        self.assertTrue(result["notification_pending"])
        self.assertFalse(result["message_pending"])
        self.assertEqual(1, result["notification_controls"])
        self.assertEqual(1, result["notification_queued"])
        capture.assert_called_once_with()

    @patch("scripts.vps.internal_browser_agent._capture_notification_actions")
    @patch("scripts.vps.internal_browser_agent._inbox_targets")
    @patch("scripts.vps.internal_browser_agent.browser.metadata")
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_notification_is_processed_before_dm_when_both_are_pending(
        self, execute, status, snapshot, metadata, inbox_targets, capture
    ):
        execute.return_value = {"active": True}
        status.return_value = {"running": True, "ready": True}
        snapshot.return_value = {"url": "https://www.instagram.com/", "authenticated": True}
        metadata.return_value = {
            "message_pending": True, "notification_pending": True,
            "message_controls": 1, "notification_controls": 1,
        }
        capture.return_value = {"notification_candidates": 1, "notification_queued": 1}

        result = internal_browser_agent.cycle()

        self.assertEqual("notification", result["browser"])
        self.assertEqual(1, result["notification_candidates"])
        capture.assert_called_once_with()
        inbox_targets.assert_not_called()

    @patch("scripts.vps.internal_browser_agent._sweep_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent._process_thread", return_value={"processed": True, "replied": True})
    @patch("scripts.vps.internal_browser_agent._open_target", return_value=True)
    @patch("scripts.vps.internal_browser_agent._open_inbox", return_value=True)
    @patch("scripts.vps.internal_browser_agent._inbox_targets")
    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch("scripts.vps.internal_browser_agent.browser.metadata")
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_cycle_opens_blue_unread_row_instead_of_first_visible_conversation(
        self, execute, status, snapshot, metadata, action, _wait, inbox_targets,
        open_inbox, open_target, process_thread, _sweep_due
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
        self.assertEqual(1, result["inbox_actionable_unread"])
        open_target.assert_called_once_with(unread)
        process_thread.assert_called_once_with("unread-row-metadata")
        open_inbox.assert_called_once_with()

    @patch("scripts.vps.internal_browser_agent._sweep_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent._process_thread")
    @patch("scripts.vps.internal_browser_agent._open_target", return_value=True)
    @patch("scripts.vps.internal_browser_agent._open_inbox", return_value=True)
    @patch("scripts.vps.internal_browser_agent._inbox_targets")
    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch("scripts.vps.internal_browser_agent.browser.metadata")
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_open_thread_does_not_block_another_blue_unread_conversation(
        self, execute, status, snapshot, metadata, action, _wait, inbox_targets,
        open_inbox, open_target, process_thread, _sweep_due
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
        open_inbox.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
