import unittest
import base64
import re
import struct
from unittest.mock import patch

from scripts.vps import internal_browser
from scripts.vps.internal_browser import COMMENT_TEXTS


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
    def test_engagement_metadata_returns_only_control_locations(self, evaluate):
        evaluate.return_value = {
            "path": "/p/abc123/",
            "post": {"x": 640, "y": 300},
            "follow": {"x": 900, "y": 120},
            "like": {"x": 700, "y": 600},
            "comment": {"x": 760, "y": 600},
            "comment_field": {"x": 640, "y": 740},
            "comment_post": {"x": 957, "y": 740},
            "share": {"x": 820, "y": 600},
            "repost": {"x": 640, "y": 420},
            "private_text": "não pode sair",
        }

        result = internal_browser.engagement_metadata()

        self.assertEqual("/p/abc123/", result["path"])
        self.assertEqual({"x": 700.0, "y": 600.0}, result["like"])
        self.assertEqual({"x": 957.0, "y": 740.0}, result["comment_post"])
        self.assertEqual({"x": 820.0, "y": 600.0}, result["share"])
        self.assertEqual({"x": 640.0, "y": 420.0}, result["repost"])
        self.assertNotIn("private_text", result)

    @patch("scripts.vps.internal_browser.evaluate")
    def test_engagement_metadata_drops_out_of_bounds_locations(self, evaluate):
        evaluate.return_value = {
            "path": "/",
            "like": {"x": 5000, "y": 600},
            "share": {"x": 200, "y": -30},
            "comment": "inválido",
        }

        result = internal_browser.engagement_metadata()

        self.assertIsNone(result["like"])
        self.assertIsNone(result["share"])
        self.assertIsNone(result["comment"])

    @patch("scripts.vps.internal_browser.evaluate")
    def test_engagement_metadata_exposes_confirmable_states(self, evaluate):
        evaluate.return_value = {
            "path": "/p/abc123/",
            "ready": True,
            "viewport": {"width": 1280, "height": 800},
            "follow_state": "following",
            "like_state": "liked",
            "repost_state": "reposted",
            "comment_present": True,
            "comment_count": 2,
            "like": {"x": 700.0, "y": 600.0},
            "repost_confirm": {"x": 237.0, "y": 557.0},
        }

        result = internal_browser.engagement_metadata()

        self.assertTrue(result["ready"])
        self.assertEqual({"width": 1280, "height": 800}, result["viewport"])
        self.assertEqual("following", result["follow_state"])
        self.assertEqual("liked", result["like_state"])
        self.assertEqual("reposted", result["repost_state"])
        self.assertEqual({"x": 237.0, "y": 557.0}, result["repost_confirm"])
        self.assertTrue(result["comment_present"])
        self.assertEqual(2, result["comment_count"])

    @patch("scripts.vps.internal_browser.evaluate")
    def test_engagement_metadata_detects_every_approved_comment_variant(self, evaluate):
        evaluate.return_value = {"comment_present": False, "comment_count": 0}

        internal_browser.engagement_metadata()

        expression = evaluate.call_args.args[0]
        for text in COMMENT_TEXTS:
            self.assertIn(re.escape(text), expression)
        self.assertNotIn("__COMMENT_MARKERS__", expression)

    @patch("scripts.vps.internal_browser.evaluate")
    def test_engagement_metadata_normalizes_invalid_states(self, evaluate):
        evaluate.return_value = {
            "follow_state": "queryset([danger])",
            "like_state": 123,
            "repost_state": None,
            "comment_count": "muitos",
            "viewport": {"width": "largo", "height": -5},
        }

        result = internal_browser.engagement_metadata()

        self.assertEqual("unknown", result["follow_state"])
        self.assertEqual("unknown", result["like_state"])
        self.assertEqual("unknown", result["repost_state"])
        self.assertEqual(0, result["comment_count"])
        self.assertEqual({"width": 0, "height": 0}, result["viewport"])

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
        self.assertIn("__salesAgentFrontEventsV3", evaluate.call_args.args[0])
        self.assertIn("Boolean(s&&s.observer", evaluate.call_args.args[0])

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
        self.assertEqual("keyDown", calls[0][1]["type"])
        self.assertEqual("keyDown", calls[1][1]["type"])

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

    @patch("scripts.vps.internal_browser._with_page")
    def test_login_state_reports_rate_limit_without_private_page_text(self, with_page):
        expressions = []

        class Page:
            def call(self, method, payload=None):
                if method == "Runtime.evaluate":
                    expressions.append(str((payload or {}).get("expression") or ""))
                    return {"result": {"value": {
                        "path": "/",
                        "hasOneTap": True,
                        "hasChallenge": False,
                        "hasLoginForm": False,
                        "authenticated": False,
                        "blockedText": False,
                        "probe": 429,
                    }}}
                return {}

        with_page.side_effect = lambda callback: callback(Page())

        result = internal_browser.login_state()

        self.assertEqual("rate_limited", result["state"])
        self.assertTrue(result["rate_limited"])
        self.assertEqual(429, result["probe"])
        self.assertTrue(result["one_tap"])
        self.assertNotIn("text", result)
        self.assertTrue(any("/accounts/login/" in item for item in expressions))

    @patch("scripts.vps.internal_browser._with_page")
    def test_login_state_classifies_authenticated_surface(self, with_page):
        class Page:
            def call(self, method, payload=None):
                if method == "Runtime.evaluate":
                    return {"result": {"value": {
                        "path": "/direct/inbox/",
                        "hasOneTap": False,
                        "hasChallenge": False,
                        "hasLoginForm": False,
                        "authenticated": True,
                        "blockedText": False,
                        "probe": 200,
                    }}}
                return {}

        with_page.side_effect = lambda callback: callback(Page())

        result = internal_browser.login_state()

        self.assertEqual("authenticated", result["state"])
        self.assertFalse(result["rate_limited"])

    @patch("scripts.vps.internal_browser.time.sleep")
    @patch("scripts.vps.internal_browser._with_page")
    def test_action_confirm_profile_dispatches_native_mouse_at_live_coordinates(self, with_page, _sleep):
        calls = []

        class Page:
            def call(self, method, payload=None):
                calls.append((method, payload))
                if method == "Runtime.evaluate":
                    return {"result": {"value": {"x": 900, "y": 412, "label": "Continue erpclinicatea"}}}
                return {}

        with_page.side_effect = lambda callback: callback(Page())

        result = internal_browser.action({"kind": "confirm_profile"})

        self.assertEqual({"ok": True, "clicked": True, "x": 900.0, "y": 412.0}, result)
        mouse = [(method, payload) for method, payload in calls if method == "Input.dispatchMouseEvent"]
        self.assertEqual(3, len(mouse))
        self.assertEqual("mousePressed", mouse[1][1]["type"])
        self.assertEqual("mouseReleased", mouse[2][1]["type"])
        self.assertEqual(900.0, mouse[1][1]["x"])
        self.assertEqual(412.0, mouse[1][1]["y"])

    @patch("scripts.vps.internal_browser._http")
    def test_cleanup_stale_tabs_closes_only_accounts_center_pages(self, request):
        request.return_value = [
            {"id": "home", "type": "page", "url": "https://www.instagram.com/"},
            {"id": "aux", "type": "page", "url": "https://accountscenter.instagram.com/accounts/"},
            {"id": "browser-ui", "type": "browser_ui", "url": "https://accountscenter.instagram.com/"},
        ]

        result = internal_browser.cleanup_stale_tabs()

        self.assertEqual({"closed": 1}, result)
        self.assertTrue(any("/json/close/aux" in str(call) for call in request.call_args_list))

    def test_browser_task_lock_is_usable_as_context_manager(self):
        with internal_browser.browser_task_lock(timeout=0.1) as acquired:
            self.assertIsInstance(acquired, bool)
