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
        ]

        page = internal_browser._target()

        self.assertEqual("home", page["id"])

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
    def test_screenshot_reports_actual_image_dimensions(self, with_page):
        header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 1279, 756)

        class Page:
            def call(self, method, _payload=None):
                return {} if method == "Page.enable" else {"data": base64.b64encode(header).decode("ascii")}

        with_page.side_effect = lambda callback: callback(Page())

        image = internal_browser.screenshot()

        self.assertEqual(1279, image["width"])
        self.assertEqual(756, image["height"])
