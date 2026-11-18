import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from scripts.vps import internal_browser_agent
from scripts.vps.internal_browser import COMMENT_TEXTS


def _repost_metadata_sequence(values):
    """Devolve os metadados em ordem e repete o último estado no fim."""
    values = list(values)

    def next_value():
        return values.pop(0) if len(values) > 1 else values[0]

    return next_value


class InternalBrowserAgentMetadataTests(unittest.TestCase):
    def setUp(self):
        internal_browser_agent._RECENT_UNREAD_TARGETS.clear()
        internal_browser_agent._LAST_NOTIFICATION_SCAN = 0.0

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._composer_center", return_value={"x": 700.0, "y": 835.0})
    @patch("scripts.vps.internal_browser_agent._page", return_value="")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_clear_composer_uses_native_select_all_and_backspace(self, action, _page, _composer, _wait):
        _page.side_effect = [True, ""]
        internal_browser_agent._clear_composer()

        self.assertEqual([
            call({"kind": "click", "x": 700.0, "y": 835.0}),
            call({"kind": "key", "key": "SelectAll"}),
            call({"kind": "key", "key": "Backspace"}),
        ], action.call_args_list)

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._composer_center", return_value={"x": 700.0, "y": 835.0})
    @patch("scripts.vps.internal_browser_agent._page", side_effect=["abc", "", ""])
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_clear_composer_erases_remaining_characters_when_select_all_is_ignored(self, action, _page, _composer, _wait):
        _page.side_effect = [True, "abc", ""]
        internal_browser_agent._clear_composer()

        self.assertEqual(4, action.call_args_list.count(call({"kind": "key", "key": "Backspace"})))

    def test_composer_safe_text_percent_encodes_underscores_only_inside_urls(self):
        text = "Link: https://erpclinicatea.com/login/admin?plano=clinica-multiprofissional&convite=3-meses&utm_source=instagram&utm_campaign=convite_tres_meses. Tudo_certo"

        result = internal_browser_agent._composer_safe_text(text)

        self.assertEqual(
            "Link: https://erpclinicatea.com/login/admin?plano=clinica-multiprofissional&convite=3-meses&utm%5Fsource=instagram&utm%5Fcampaign=convite%5Ftres%5Fmeses. Tudo_certo",
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
        page.side_effect = [expected, True, "rascunho anterior", True, "novo link", expected, "", expected]

        result = internal_browser_agent._send_bubble("novo link", expected)

        self.assertTrue(result["sent"])
        clear.assert_called_once_with()
        self.assertEqual([
            call({"kind": "click", "x": 700.0, "y": 835.0}),
            call({"kind": "click", "x": 700.0, "y": 835.0}),
            call({"kind": "type", "text": "novo link"}),
            call({"kind": "click", "x": 1100.0, "y": 835.0}),
        ], action.call_args_list)

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._send_button_center", return_value={"x": 1100.0, "y": 835.0})
    @patch("scripts.vps.internal_browser_agent._message_count", side_effect=[0, 1])
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent._composer_center", return_value={"x": 700.0, "y": 835.0})
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_send_bubble_uses_enter_if_button_click_keeps_the_draft(
        self, action, _composer, page, _count, _send, _wait
    ):
        expected = "https://www.instagram.com/direct/t/123/"
        page.side_effect = [expected, True, "", True, "nova mensagem", expected, "nova mensagem", expected]

        result = internal_browser_agent._send_bubble("nova mensagem", expected)

        self.assertTrue(result["sent"])
        self.assertIn(call({"kind": "key", "key": "Enter"}), action.call_args_list)

    @patch("scripts.vps.internal_browser_agent._page", return_value=1)
    def test_message_count_includes_visible_dir_auto_bubbles(self, page):
        self.assertEqual(1, internal_browser_agent._message_count("mensagem enviada"))
        expression = page.call_args.args[0]
        self.assertIn('[dir="auto"]', expression)
        self.assertIn("r.left>450", expression)
        self.assertIn("canonical", expression)

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

    @patch("scripts.vps.internal_browser_agent.time.monotonic", return_value=100.0)
    def test_message_event_fallback_checks_recent_rows_even_if_blue_dot_was_cleared(self, _clock):
        rows = [
            {"key": "new", "href": "https://www.instagram.com/direct/t/new/", "label": "Mensagem recente", "unread": False},
            {"key": "old", "href": "https://www.instagram.com/direct/t/old/", "label": "Mensagem antiga", "unread": False},
        ]
        internal_browser_agent._RECENT_UNREAD_TARGETS["old"] = 200.0

        result = internal_browser_agent._pending_message_fallback_targets(rows)

        self.assertEqual([rows[0]], result)

    @patch("scripts.vps.internal_browser_agent.time.monotonic", return_value=100.0)
    def test_message_event_fallback_accepts_a_native_click_target_without_href(self, _clock):
        row = {"key": "native", "href": "", "label": "Mensagem recente", "x": 270.0, "y": 340.0}

        self.assertEqual([row], internal_browser_agent._pending_message_fallback_targets([row]))

    @patch("scripts.vps.internal_browser_agent._open_home", return_value=True)
    @patch("scripts.vps.internal_browser_agent._sweep_due", return_value=False)
    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._pending_message_fallback_targets")
    @patch("scripts.vps.internal_browser_agent._process_thread")
    @patch("scripts.vps.internal_browser_agent._open_target", return_value=True)
    @patch("scripts.vps.internal_browser_agent._inbox_targets", return_value=[{"key": "manual", "href": "https://www.instagram.com/direct/t/manual/", "unread": False}])
    @patch("scripts.vps.internal_browser_agent._open_inbox", return_value=True)
    @patch("scripts.vps.internal_browser_agent.browser.metadata")
    @patch("scripts.vps.internal_browser_agent.browser.snapshot")
    @patch("scripts.vps.internal_browser_agent.browser.status")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_cycle_falls_back_to_recent_thread_when_phone_marked_message_as_read(
        self, execute, status, snapshot, metadata, _open_inbox, _targets, open_target, process, fallback, _wait, _sweep_due, _home
    ):
        execute.side_effect = [
            {"active": True},
            {"mode": "sales"},
            {"mode": "prospecting", "next_mode": "sales", "idle_cycles": 0},
        ]
        status.return_value = {"running": True, "ready": True}
        snapshot.return_value = {"url": "https://www.instagram.com/direct/inbox", "authenticated": True}
        metadata.return_value = {"message_pending": True, "notification_pending": False, "message_controls": 1, "notification_controls": 0}
        fallback.return_value = [{"key": "manual", "href": "https://www.instagram.com/direct/t/manual/", "unread": False}]
        process.return_value = {"processed": True, "replied": True, "source": "message-event-fallback"}

        result = internal_browser_agent.cycle()

        self.assertEqual("message", result["browser"])
        self.assertTrue(result["replied"])
        open_target.assert_called_once_with(fallback.return_value[0])
        _home.assert_called_once_with()
        self.assertTrue(result["returned_home"])

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent._open_notifications", return_value=True)
    def test_notification_candidates_are_normalized_and_deduplicated(self, open_notifications, page, _wait):
        page.return_value = ["Clinica.Teste", "clinica.teste", "fono_legal"]

        result = internal_browser_agent._notification_candidates()

        self.assertEqual(["clinica.teste", "fono_legal"], [item["username"] for item in result])
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

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_open_target_navigates_to_known_thread_when_virtualized_row_ignores_click(self, action, page, _wait):
        page.side_effect = [False, "https://www.instagram.com/direct/t/456/"]
        target = {"href": "https://www.instagram.com/direct/t/456/", "label": "Conversa"}

        opened = internal_browser_agent._open_target(target)

        self.assertTrue(opened)
        action.assert_called_once_with({"kind": "navigate", "url": target["href"]})

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_open_target_clicks_native_row_when_inbox_has_no_thread_href(self, action, page, _wait):
        page.side_effect = [False, "https://www.instagram.com/direct/t/789/"]
        target = {"href": "", "label": "Conversa", "x": 270.0, "y": 340.0}

        opened = internal_browser_agent._open_target(target)

        self.assertTrue(opened)
        action.assert_called_once_with({"kind": "click", "x": 270.0, "y": 340.0})

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch("scripts.vps.internal_browser_agent._click_surface", return_value=False)
    @patch("scripts.vps.internal_browser_agent._page")
    def test_open_inbox_navigates_when_collapsed_layout_has_no_clickable_messages_control(self, page, click_surface, action, _wait):
        page.side_effect = ["https://www.instagram.com/", "https://www.instagram.com/direct/inbox/"]

        opened = internal_browser_agent._open_inbox()

        self.assertTrue(opened)
        click_surface.assert_called_once()
        action.assert_called_once_with({"kind": "navigate", "url": internal_browser_agent.INBOX_URL})

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._click_surface", return_value=False)
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_open_home_navigates_when_thread_has_no_clickable_home_link(self, action, page, click_surface, _wait):
        page.side_effect = ["https://www.instagram.com/direct/t/123/", "https://www.instagram.com/"]

        opened = internal_browser_agent._open_home()

        self.assertTrue(opened)
        click_surface.assert_called_once()
        action.assert_called_once_with({"kind": "navigate", "url": internal_browser_agent.HOME_URL})

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


    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._composer_center", return_value={"x": 1021.0, "y": 751.0})
    @patch("scripts.vps.internal_browser_agent._profile_message_button", return_value={"x": 751.0, "y": 352.0})
    @patch("scripts.vps.internal_browser_agent._page", return_value="https://www.instagram.com/clinica.teste/")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_open_profile_dm_accepts_overlay_without_thread_url(self, action, _page, _button, _composer, _wait):
        result = internal_browser_agent._open_profile_dm("clinica.teste")

        self.assertEqual("overlay", result["mode"])
        self.assertIn(call({"kind": "click", "x": 751.0, "y": 352.0}), action.call_args_list)

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._composer_center", return_value={"x": 1021.0, "y": 751.0})
    @patch("scripts.vps.internal_browser_agent._profile_message_button", return_value={"x": 751.0, "y": 352.0})
    @patch("scripts.vps.internal_browser_agent._page", return_value="https://www.instagram.com/direct/t/123/")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_open_profile_dm_returns_thread_when_url_changes(self, action, _page, _button, _composer, _wait):
        result = internal_browser_agent._open_profile_dm("clinica.teste")

        self.assertEqual("thread", result["mode"])
        self.assertEqual("123", result["thread_id"])

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._send_button_center", return_value={"x": 1195.0, "y": 751.0})
    @patch("scripts.vps.internal_browser_agent._overlay_state")
    @patch("scripts.vps.internal_browser_agent._focus_composer")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent._composer_center", return_value={"x": 1021.0, "y": 751.0})
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_send_overlay_bubble_confirms_bubble_inside_profile_panel(
        self, action, _composer, page, _focus, overlay, _send, _wait
    ):
        url = "https://www.instagram.com/clinica.teste/"
        page.side_effect = [url, "", "texto", url, "", url]
        overlay.side_effect = [
            {"found": True, "count": 0, "panel_text": False},
            {"found": True, "count": 1, "panel_text": True},
        ]

        result = internal_browser_agent._send_overlay_bubble("texto")

        self.assertTrue(result["sent"])
        self.assertIn(call({"kind": "type", "text": "texto"}), action.call_args_list)
        self.assertIn(call({"kind": "click", "x": 1195.0, "y": 751.0}), action.call_args_list)

    @patch("scripts.vps.internal_browser_agent._own_username", return_value="erpclinicatea")
    @patch("scripts.vps.internal_browser_agent._open_home", return_value=True)
    @patch("scripts.vps.internal_browser_agent._send_overlay_bubble")
    @patch("scripts.vps.internal_browser_agent._open_profile_dm", return_value={"mode": "overlay", "url": "https://www.instagram.com/clinica.teste/"})
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_prospecting_retry_stage_skips_follow_and_comment(
        self, execute, _page, action, open_dm, send_overlay, _home, _own
    ):
        execute.side_effect = [
            {"active": True, "prospecting_active": True},
            {"ready": True},
            {"created": [{"id": 7}]},
            {"claimed": True, "id": 7, "stage": "dm", "payload": {
                "username": "clinica.teste", "intro": "Olá! Tudo bem?",
            }},
            {"reserved": True},
            {"allowed": True, "reason": ""},
            {"id": 7, "state": "sent"},
            {"id": 7, "step": "dm", "result": "confirmed"},
            {"username": "clinica.teste", "kind": "clinic_multi"},
        ]
        _page.side_effect = [
            "https://www.instagram.com/",
            [{"username": "clinica.teste", "text": "Clínica multidisciplinar TEA", "following": False}],
        ]

        result = internal_browser_agent._prospecting_cycle()

        self.assertEqual("prospecting-sent", result["browser"])
        self.assertEqual("overlay", result["mode"])
        open_dm.assert_called_once_with("clinica.teste")
        send_overlay.assert_called_once_with("Olá! Tudo bem?")
        action.assert_not_called()
        self.assertIn(
            call("campaignConfirm", {"id": 7, "state": "sent", "note": "Interações medidas: dm=ok"}),
            execute.call_args_list,
        )


    @patch("scripts.vps.internal_browser_agent._clear_composer")
    @patch("scripts.vps.internal_browser_agent._focus_composer")
    @patch("scripts.vps.internal_browser_agent._page", return_value="https://www.instagram.com/clinica.teste/")
    @patch("scripts.vps.internal_browser_agent._composer_center", return_value={"x": 1021.0, "y": 751.0})
    @patch("scripts.vps.internal_browser_agent._overlay_state", return_value={"found": True, "count": 1, "panel_text": True})
    @patch("scripts.vps.internal_browser_agent.browser.action")
    def test_send_overlay_bubble_does_not_duplicate_existing_bubble(
        self, action, overlay, _composer, _page, _focus, clear
    ):
        result = internal_browser_agent._send_overlay_bubble("texto")

        self.assertTrue(result["sent"])
        self.assertEqual("overlay-already-present", result["method"])
        clear.assert_called_once_with()
        self.assertNotIn(call({"kind": "type", "text": "texto"}), action.call_args_list)

    @patch("scripts.vps.internal_browser_agent._own_username", return_value="erpclinicatea")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_prospecting_skips_own_profile_without_retry(self, execute, _page, _own):
        execute.side_effect = [
            {"active": True, "prospecting_active": True},
            {"ready": True},
            {"created": [{"id": 9}]},
            {"claimed": True, "id": 9, "stage": "", "payload": {"username": "erpclinicatea"}},
            {"id": 9, "state": "skipped"},
        ]
        _page.side_effect = [
            "https://www.instagram.com/",
            [{"username": "clinica.teste", "text": "Clínica", "following": False}],
        ]

        result = internal_browser_agent._prospecting_cycle()

        self.assertEqual("prospecting-skipped", result["browser"])
        self.assertIn(
            call("campaignConfirm", {"id": 9, "state": "skipped", "note": "Perfil inválido para prospecção"}),
            execute.call_args_list,
        )
        self.assertNotIn("campaignFail", [c.args[0] for c in execute.call_args_list if c.args])

    @patch("scripts.vps.internal_browser_agent._own_username", return_value="erpclinicatea")
    @patch("scripts.vps.internal_browser_agent._open_home", return_value=True)
    @patch("scripts.vps.internal_browser_agent._open_profile_dm", side_effect=internal_browser_agent._ProspectSkip("Botão de mensagem não encontrado"))
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_prospecting_skips_profile_without_message_surface(self, execute, _page, open_dm, _home, _own):
        execute.side_effect = [
            {"active": True, "prospecting_active": True},
            {"ready": True},
            {"created": [{"id": 11}]},
            {"claimed": True, "id": 11, "stage": "dm", "payload": {"username": "sem.dm"}},
            {"reserved": True},
            {"allowed": True, "reason": ""},
            {"id": 11, "state": "skipped"},
        ]
        _page.side_effect = [
            "https://www.instagram.com/",
            [{"username": "sem.dm", "text": "Clínica", "following": False}],
        ]

        result = internal_browser_agent._prospecting_cycle()

        self.assertEqual("prospecting-skipped", result["browser"])
        self.assertIn(
            call("campaignConfirm", {"id": 11, "state": "skipped", "note": "Botão de mensagem não encontrado"}),
            execute.call_args_list,
        )
        self.assertNotIn("campaignFail", [c.args[0] for c in execute.call_args_list if c.args])


    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent._own_username", return_value="erpclinicatea")
    @patch("scripts.vps.internal_browser_agent._open_home", return_value=True)
    @patch("scripts.vps.internal_browser_agent._send_overlay_bubble", return_value={"sent": True})
    @patch(
        "scripts.vps.internal_browser_agent._open_profile_dm",
        return_value={"mode": "overlay", "url": "https://www.instagram.com/clinica.teste/"},
    )
    @patch("scripts.vps.internal_browser_agent._engage_repost", return_value=(True, {"repost_state": "reposted"}))
    @patch("scripts.vps.internal_browser_agent._engage_comment", return_value=(True, {"comment_present": True}))
    @patch(
        "scripts.vps.internal_browser_agent._engage_step",
        side_effect=[
            (True, {"follow_state": "following", "post": {"x": 640.0, "y": 300.0}}),
            (True, {"like_state": "liked"}),
        ],
    )
    @patch("scripts.vps.internal_browser_agent._engagement_metadata", return_value={"post": {"x": 640.0, "y": 300.0}})
    @patch("scripts.vps.internal_browser_agent._wait_post_controls", return_value=(True, {"like_state": "not_liked", "comment": {"x": 785.0, "y": 525.0}}))
    @patch("scripts.vps.internal_browser_agent._wait_page_ready", return_value=True)
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_prospecting_engages_and_sends_approved_profile_intro(
        self, execute, _page, action, ready, post_controls, metadata, engage_step, engage_comment, engage_repost,
        open_dm, send_overlay, _home, _own, _wait
    ):
        execute.side_effect = [
            {"active": True, "prospecting_active": True},
            {"ready": True},
            {"created": [{"id": 3}]},
            {"claimed": True, "id": 3, "stage": "", "payload": {"username": "clinica.teste"}},
            {"reserved": True},
            {"username": "clinica.teste", "segment": "clinic_multi", "intro": "Saudação aprovada para clínica"},
            {"id": 3, "stage": "dm"},
            {"allowed": True, "reason": ""},
            {"id": 3, "state": "sent"},
            {"id": 3, "step": "dm", "result": "confirmed"},
            {"username": "clinica.teste", "kind": "clinic_multi"},
        ]
        _page.side_effect = [
            "https://www.instagram.com/",
            [{"username": "clinica.teste", "text": "Clínica multidisciplinar TEA", "following": False}],
            "Clínica TEA atendimento infantil equipe multidisciplinar",
        ]

        result = internal_browser_agent._prospecting_cycle()

        self.assertEqual("prospecting-sent", result["browser"])
        self.assertEqual(
            {"follow": True, "like": True, "comment": True, "repost": True, "dm": True},
            result["actions"],
        )
        self.assertIn(call({"kind": "click", "x": 640.0, "y": 300.0}), action.call_args_list)
        engage_step.assert_any_call(3, "follow", "follow", "follow_state", "following")
        engage_step.assert_any_call(3, "like", "like", "like_state", "liked")
        engage_comment.assert_called_once_with(3)
        engage_repost.assert_called_once_with(3)
        self.assertGreaterEqual(ready.call_count, 2)
        send_overlay.assert_called_once_with("Saudação aprovada para clínica")
        self.assertIn(
            call("campaignProfileIntro", {"username": "clinica.teste", "text": "Clínica TEA atendimento infantil equipe multidisciplinar"}),
            execute.call_args_list,
        )
        self.assertIn(
            call("campaignConfirm", {
                "id": 3, "state": "sent",
                "note": "Interações medidas: follow=ok, like=ok, comment=ok, repost=ok, dm=ok",
            }),
            execute.call_args_list,
        )


class EngagementConfirmationTests(unittest.TestCase):
    """Cada clique só é considerado feito quando os metadados confirmam."""

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.execute")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch(
        "scripts.vps.internal_browser_agent._engagement_metadata",
        side_effect=[
            {"follow": {"x": 900.0, "y": 120.0}, "follow_state": "not_following"},
            {"follow": None, "follow_state": "following"},
        ],
    )
    def test_engage_step_confirms_after_metadata_state_changes(self, metadata, action, execute, _wait):
        confirmed, observed = internal_browser_agent._engage_step(
            55, "follow", "follow", "follow_state", "following"
        )

        self.assertTrue(confirmed)
        self.assertEqual("following", observed["follow_state"])
        action.assert_called_once_with({"kind": "click", "x": 900.0, "y": 120.0})
        self.assertIn(
            call("campaignActionAudit", {
                "id": 55, "step": "follow", "result": "confirmed",
                "detail": "attempt=1; follow_state=following",
            }),
            execute.call_args_list,
        )

    @patch(
        "scripts.vps.internal_browser_agent._wait_for_state",
        return_value=(False, {"follow_state": "not_following"}),
    )
    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.execute")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch(
        "scripts.vps.internal_browser_agent._engagement_metadata",
        return_value={"follow": {"x": 900.0, "y": 120.0}, "follow_state": "not_following"},
    )
    def test_engage_step_reports_unconfirmed_after_all_attempts(self, metadata, action, execute, _wait, _wait_state):
        confirmed, _ = internal_browser_agent._engage_step(
            56, "follow", "follow", "follow_state", "following"
        )

        self.assertFalse(confirmed)
        self.assertEqual(3, action.call_count)
        self.assertIn(
            call("campaignActionAudit", {
                "id": 56, "step": "follow", "result": "unconfirmed",
                "detail": "attempts=3; follow_state=not_following",
            }),
            execute.call_args_list,
        )

    @patch("scripts.vps.internal_browser_agent.next_comment_text", return_value=COMMENT_TEXTS[0])
    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.execute")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch(
        "scripts.vps.internal_browser_agent._engagement_metadata",
        side_effect=[
            {"comment": {"x": 760.0, "y": 600.0}},
            {"comment": None, "comment_field": {"x": 640.0, "y": 740.0},
             "comment_post": {"x": 957.0, "y": 596.0}},
            {"comment_post": {"x": 957.0, "y": 596.0}},
            {"comment_present": True, "comment_count": 1},
        ],
    )
    def test_engage_comment_waits_for_field_and_confirms_text(self, metadata, action, execute, _wait, _next_text):
        confirmed, _ = internal_browser_agent._engage_comment(57)

        self.assertTrue(confirmed)
        self.assertIn(call({"kind": "click", "x": 760.0, "y": 600.0}), action.call_args_list)
        self.assertIn(call({"kind": "click", "x": 640.0, "y": 740.0}), action.call_args_list)
        self.assertIn(call({"kind": "key", "key": "SelectAll"}), action.call_args_list)
        self.assertIn(
            call({"kind": "type", "text": "Muito bonito o trabalho de vocês! 😊"}),
            action.call_args_list,
        )
        self.assertIn(call({"kind": "click", "x": 957.0, "y": 596.0}), action.call_args_list)
        self.assertNotIn(call({"kind": "key", "key": "Enter"}), action.call_args_list)
        self.assertIn(
            call("campaignActionAudit", {
                "id": 57, "step": "comment", "result": "confirmed",
                "detail": "attempt=1; comment_present=True; text=" + COMMENT_TEXTS[0][:60],
            }),
            execute.call_args_list,
        )

    @patch("scripts.vps.internal_browser_agent.next_comment_text", return_value=COMMENT_TEXTS[1])
    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.execute")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch(
        "scripts.vps.internal_browser_agent._engagement_metadata",
        side_effect=[
            {"comment": {"x": 760.0, "y": 600.0}},
            {"comment_field": {"x": 640.0, "y": 740.0}},
            {},
            {"comment_present": True, "comment_count": 1},
        ],
    )
    def test_engage_comment_falls_back_to_enter_without_post_button(self, metadata, action, execute, _wait, _next_text):
        confirmed, _ = internal_browser_agent._engage_comment(59)

        self.assertTrue(confirmed)
        self.assertIn(call({"kind": "key", "key": "Enter"}), action.call_args_list)

    def test_next_comment_text_rotates_without_repeating(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SALES_AGENT_DB": str(Path(folder) / "agent.sqlite3")}
        ):
            seen = [internal_browser_agent.next_comment_text() for _ in range(len(COMMENT_TEXTS) * 3)]
            self.assertTrue(all(first != second for first, second in zip(seen, seen[1:])))
            self.assertEqual(set(COMMENT_TEXTS), set(seen))
            self.assertIn("❤️❤️❤️", COMMENT_TEXTS)
            self.assertIn("👏👏👏", COMMENT_TEXTS)
            self.assertIn("Já vou seguir! ❤️❤️", COMMENT_TEXTS)
            self.assertIn("Vou seguir para acompanhar mais esse trabalho !! ❤️❤️", COMMENT_TEXTS)

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.execute")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch(
        "scripts.vps.internal_browser_agent._engagement_metadata",
        side_effect=_repost_metadata_sequence([
            {"repost": {"x": 825.0, "y": 525.0}, "repost_state": "not_reposted"},
            {"repost_state": "not_reposted"},
            {"repost_confirm": {"x": 237.0, "y": 557.0}, "repost_state": "not_reposted"},
            {"repost_confirm": {"x": 237.0, "y": 557.0}, "repost_state": "not_reposted"},
            {"repost_confirm": {"x": 237.0, "y": 557.0}, "repost_state": "not_reposted"},
            {"repost_confirm": {"x": 237.0, "y": 557.0}, "repost_state": "not_reposted"},
            {"repost_state": "reposted"},
        ]),
    )
    def test_engage_repost_clicks_control_and_confirms_state(self, metadata, action, execute, _wait):
        confirmed, _ = internal_browser_agent._engage_repost(58)

        self.assertTrue(confirmed)
        self.assertIn(call({"kind": "click", "x": 825.0, "y": 525.0}), action.call_args_list)
        self.assertIn(call({"kind": "click", "x": 237.0, "y": 557.0}), action.call_args_list)
        self.assertIn(call({"kind": "key", "key": "Escape"}), action.call_args_list)
        self.assertIn(
            call("campaignActionAudit", {
                "id": 58, "step": "repost", "result": "confirmed",
                "detail": "attempt=1; repost_state=reposted",
            }),
            execute.call_args_list,
        )

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch("scripts.vps.internal_browser_agent.execute")
    @patch("scripts.vps.internal_browser_agent.browser.action")
    @patch(
        "scripts.vps.internal_browser_agent._engagement_metadata",
        side_effect=_repost_metadata_sequence([
            {"repost": None, "repost_confirm": {"x": 237.0, "y": 557.0}, "repost_state": "unknown"},
            {"repost_confirm": {"x": 237.0, "y": 557.0}, "repost_state": "unknown"},
            {"repost_confirm": {"x": 237.0, "y": 557.0}, "repost_state": "unknown"},
            {"repost_confirm": {"x": 237.0, "y": 557.0}, "repost_state": "unknown"},
            {"repost_state": "reposted"},
        ]),
    )
    def test_engage_repost_confirms_already_open_sheet(self, metadata, action, execute, _wait):
        """Sheet aberto por tentativa anterior: clicar direto no botão roxo."""
        confirmed, _ = internal_browser_agent._engage_repost(60)

        self.assertTrue(confirmed)
        self.assertIn(call({"kind": "click", "x": 237.0, "y": 557.0}), action.call_args_list)
        self.assertNotIn(call({"kind": "click", "x": 825.0, "y": 525.0}), action.call_args_list)
        self.assertIn(call({"kind": "key", "key": "Escape"}), action.call_args_list)

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch(
        "scripts.vps.internal_browser_agent._engagement_metadata",
        side_effect=[
            {"like_state": "unknown", "comment": None},
            {"like_state": "not_liked", "comment": {"x": 785.0, "y": 525.0}},
        ],
    )
    def test_wait_post_controls_polls_until_modal_is_ready(self, metadata, _wait):
        ready, observed = internal_browser_agent._wait_post_controls(timeout=3)

        self.assertTrue(ready)
        self.assertEqual("not_liked", observed["like_state"])

    @patch("scripts.vps.internal_browser_agent._wait")
    @patch(
        "scripts.vps.internal_browser_agent._page",
        side_effect=[False, False, True],
    )
    def test_wait_page_ready_polls_until_page_has_content(self, page, _wait):
        self.assertTrue(internal_browser_agent._wait_page_ready(timeout=3))
        self.assertEqual(3, page.call_count)


class ProspectingDiscoveryTests(unittest.TestCase):
    """O feed precisa continuar sendo explorado quando nada é descoberto."""

    @patch("scripts.vps.internal_browser_agent._scroll_feed")
    @patch("scripts.vps.internal_browser_agent._own_username", return_value="erpclinicatea")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_empty_discovery_scrolls_feed_instead_of_stalling(self, execute, page, _own, scroll):
        execute.side_effect = [
            {"active": True, "prospecting_active": True},
            {"ready": True},
            {"created": [], "reviewed": 21},
            {"claimed": False},
        ]
        page.side_effect = [
            "https://www.instagram.com/",
            [{"username": "clinica.atypica", "text": "Clinica atypica equipe", "following": True}],
        ]

        result = internal_browser_agent._prospecting_cycle()

        self.assertEqual("prospecting-scrolled", result["browser"])
        self.assertEqual(0, result["discovered"])
        scroll.assert_called_once_with()

    @patch("scripts.vps.internal_browser_agent._scroll_feed")
    @patch("scripts.vps.internal_browser_agent._own_username", return_value="erpclinicatea")
    @patch("scripts.vps.internal_browser_agent._page")
    @patch("scripts.vps.internal_browser_agent.execute")
    def test_discovery_with_new_lead_does_not_scroll(self, execute, page, _own, scroll):
        execute.side_effect = [
            {"active": True, "prospecting_active": True},
            {"ready": True},
            {"created": [{"id": 9}], "reviewed": 21},
            {"claimed": False},
        ]
        page.side_effect = [
            "https://www.instagram.com/",
            [{"username": "clinica.nova", "text": "Clinica nova equipe", "following": False}],
        ]

        result = internal_browser_agent._prospecting_cycle()

        self.assertEqual("prospecting-no-candidate", result["browser"])
        self.assertEqual(1, result["discovered"])
        scroll.assert_not_called()


if __name__ == "__main__":
    unittest.main()
