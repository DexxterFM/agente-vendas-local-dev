import unittest
import base64
import struct
from unittest.mock import patch

from scripts.vps import internal_browser


class InternalBrowserTests(unittest.TestCase):
    @patch("scripts.vps.internal_browser._http")
    def test_status_exposes_only_aggregate_runtime_metadata(self, request):
        request.side_effect = [
            {"Browser": "Internal Browser 1"},
            [{"type": "page", "url": "https://www.instagram.com/"}],
        ]
        self.assertEqual(
            internal_browser.status(),
            {"running": True, "ready": True, "product": "Internal Browser 1"},
        )

    @patch("scripts.vps.internal_browser._http")
    def test_target_prefers_recovery_window_opened_by_login(self, request):
        request.return_value = [
            {"id": "home", "type": "page", "url": "https://www.instagram.com/"},
            {"id": "recovery", "type": "page", "url": "https://www.facebook.com/login/identify/"},
            {"id": "two-step", "type": "page", "url": "https://www.facebook.com/two_step_verification/authentication/"},
        ]

        page = internal_browser._target()

        self.assertEqual("two-step", page["id"])

    @patch("scripts.vps.internal_browser._http")
    def test_target_keeps_main_page_ahead_of_stale_login_tab(self, request):
        request.return_value = [
            {"id": "old-login", "type": "page", "url": "https://www.instagram.com/accounts/login/"},
            {"id": "home", "type": "page", "url": "https://www.instagram.com/"},
            {"id": "signup", "type": "page", "url": "https://www.instagram.com/accounts/emailsignup/"},
        ]

        page = internal_browser._target()

        self.assertEqual("home", page["id"])

    @patch("scripts.vps.internal_browser._http")
    def test_target_keeps_authenticated_page_ahead_of_stale_password_recovery(self, request):
        request.return_value = [
            {"id": "inbox", "type": "page", "url": "https://www.instagram.com/direct/inbox/"},
            {"id": "recovery", "type": "page", "url": "https://www.instagram.com/auth_platform/reset_password/?apc=redacted"},
        ]

        page = internal_browser._target()

        self.assertEqual("inbox", page["id"])

    @patch("scripts.vps.internal_browser.evaluate")
    def test_snapshot_preserves_unauthenticated_state(self, evaluate):
        evaluate.return_value = {
            "url": "https://www.instagram.com/accounts/login/",
            "authenticated": False,
            "hasMessages": False,
            "hasNotifications": False,
            "text": "conteúdo privado",
        }

        result = internal_browser.snapshot()

        self.assertFalse(result["authenticated"])
        self.assertNotIn("text", result)

    @patch("scripts.vps.internal_browser.evaluate")
    def test_snapshot_does_not_return_page_text(self, evaluate):
        evaluate.return_value = {
            "url": "https://www.instagram.com/",
            "authenticated": True,
            "hasMessages": True,
            "hasNotifications": True,
            "text": "conteúdo privado",
        }
        result = internal_browser.snapshot()
        self.assertEqual(result["authenticated"], True)
        self.assertTrue(result["hasMessages"])
        self.assertNotIn("text", result)

    @patch("scripts.vps.internal_browser.evaluate")
    def test_visual_state_exposes_readiness_without_page_content(self, evaluate):
        evaluate.return_value = {
            "ready": False,
            "path": "/direct/inbox/",
            "authenticated_surface": True,
            "direct": True,
            "document_ready": True,
            "private_text": "não pode sair",
        }

        result = internal_browser.visual_state()

        self.assertFalse(result["ready"])
        self.assertTrue(result["authenticated_surface"])
        self.assertNotIn("private_text", result)

    @patch("scripts.vps.internal_browser.evaluate")
    def test_metadata_returns_only_aggregate_indicators(self, evaluate):
        evaluate.return_value = {
            "path": "/", "message_controls": 3, "notification_controls": 1,
            "message_pending": False, "notification_pending": True,
            "private_text": "não pode sair",
        }

        result = internal_browser.metadata()

        self.assertEqual("/", result["path"])
        self.assertFalse(result["message_pending"])
        self.assertTrue(result["notification_pending"])
        self.assertNotIn("private_text", result)

    @patch("scripts.vps.internal_browser.evaluate")
    def test_frontend_events_expose_only_structural_status(self, evaluate):
        evaluate.return_value = {
            "installed": True,
            "sequence": 4,
            "event_count": 1,
            "events": [{
                "sequence": 4,
                "at": 999,
                "path": "/direct/inbox/",
                "message_pending": True,
                "notification_pending": False,
                "unread_rows": 1,
                "unread_confirmed": 1,
                "private_text": "não deve sair",
            }],
        }

        result = internal_browser.frontend_events()

        self.assertTrue(result["installed"])
        self.assertEqual(1, result["event_count"])
        self.assertEqual(1, result["last"]["unread_rows"])
        self.assertNotIn("private_text", result["last"])

    @patch("scripts.vps.internal_browser.evaluate", return_value=True)
    def test_frontend_event_pending_uses_lightweight_queue_check(self, evaluate):
        self.assertTrue(internal_browser.frontend_event_pending())
        self.assertIn("__salesAgentFrontEventsV1", evaluate.call_args.args[0])

    @patch("scripts.vps.internal_browser.visual_state")
    def test_stalled_page_watchdog_pauses_without_reloading(self, visual_state):
        visual_state.return_value = {
            "ready": False, "authenticated_surface": True, "direct": True,
        }

        result = internal_browser.stalled_page_watchdog()

        self.assertEqual(
            {"stalled": True, "armed": False, "throttled": False, "armed_seconds": 0},
            result,
        )
        visual_state.assert_called_once_with()

    @patch("scripts.vps.internal_browser._with_page")
    def test_action_rejects_external_navigation_without_touching_page(self, page):
        with self.assertRaises(ValueError):
            internal_browser.action({"kind": "navigate", "url": "https://example.com"})
        page.assert_not_called()

    @patch("scripts.vps.internal_browser._with_page")
    def test_action_forwards_normal_editing_keys(self, with_page):
        calls = []

        class Page:
            def call(self, method, payload):
                calls.append((method, payload))
                return {}

        with_page.side_effect = lambda callback: callback(Page())

        result = internal_browser.action({"kind": "key", "key": "Backspace"})

        self.assertEqual({"ok": True}, result)
        self.assertEqual("Input.dispatchKeyEvent", calls[0][0])
        self.assertEqual("Backspace", calls[0][1]["key"])
        self.assertEqual(8, calls[0][1]["windowsVirtualKeyCode"])

    @patch("scripts.vps.internal_browser._with_page")
    def test_action_select_all_uses_control_a_keyboard_sequence(self, with_page):
        calls = []

        class Page:
            def call(self, method, payload):
                calls.append((method, payload))
                return {}

        with_page.side_effect = lambda callback: callback(Page())

        result = internal_browser.action({"kind": "key", "key": "SelectAll"})

        self.assertEqual({"ok": True}, result)
        self.assertEqual(["Control", "a", "a", "Control"], [payload["key"] for _, payload in calls])
        self.assertEqual(2, calls[1][1]["modifiers"])

    @patch("scripts.vps.internal_browser.time.sleep")
    @patch("scripts.vps.internal_browser._with_page")
    def test_action_types_each_character_through_native_text_input(self, with_page, _sleep):
        calls = []

        class Page:
            def call(self, method, payload):
                calls.append((method, payload))
                return {}

        with_page.side_effect = lambda callback: callback(Page())

        result = internal_browser.action({"kind": "type", "text": "Ab"})

        self.assertEqual({"ok": True}, result)
        self.assertEqual(["Input.insertText", "Input.insertText"], [method for method, _ in calls])
        self.assertEqual("A", calls[0][1]["text"])
        self.assertEqual("b", calls[1][1]["text"])

    @patch("scripts.vps.internal_browser._with_page")
    def test_action_navigates_back_through_internal_history(self, with_page):
        calls = []

        class Page:
            def call(self, method, payload=None):
                calls.append((method, payload))
                if method == "Page.getNavigationHistory":
                    return {"currentIndex": 1, "entries": [{"id": 21}, {"id": 22}]}
                return {}

        with_page.side_effect = lambda callback: callback(Page())

        self.assertEqual({"ok": True, "moved": True}, internal_browser.action({"kind": "back"}))
        self.assertIn(("Page.navigateToHistoryEntry", {"entryId": 21}), calls)

    @patch("scripts.vps.internal_browser._with_page")
    def test_import_session_limits_cookies_to_authorized_domains(self, with_page):
        calls = []

        class Page:
            def call(self, method, payload=None):
                calls.append((method, payload))
                return {}

        with_page.side_effect = lambda callback: callback(Page())
        result = internal_browser.import_session_cookies([
            {"name": "sessionid", "value": "masked", "domain": ".instagram.com", "path": "/", "secure": True},
            {"name": "other", "value": "ignored", "domain": ".example.com", "path": "/"},
        ])

        self.assertEqual({"imported": 1}, result)
        sent = next(payload for method, payload in calls if method == "Network.setCookies")
        self.assertEqual(1, len(sent["cookies"]))
        self.assertEqual(".instagram.com", sent["cookies"][0]["domain"])

    @patch("scripts.vps.internal_browser._with_page")
    def test_screenshot_reports_actual_image_dimensions(self, with_page):
        header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 1279, 756)

        class Page:
            def call(self, method, _payload=None):
                return {} if method == "Page.enable" else {"data": base64.b64encode(header).decode("ascii")}

        with_page.side_effect = lambda callback: callback(Page())

        image = internal_browser.screenshot()

        self.assertEqual(1279, image["width"])
        self.assertEqual(756, image["height"])
