import unittest
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
