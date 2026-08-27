"""Unit tests for the screen registry (Этап 5.1)."""

from __future__ import annotations

from pentool.tui.screen_registry import SCREEN_MAP, get_screen_class


class TestScreenRegistry:
    def test_all_expected_modules_mapped(self):
        expected = {
            "dashboard", "proxy", "repeater", "intruder", "scanner", "target",
            "decoder", "comparer", "sequencer", "extensions", "terminal", "settings",
        }
        assert set(SCREEN_MAP.keys()) == expected

    def test_get_screen_class_known(self):
        from pentool.tui.screens.proxy.screen import ProxyScreen

        assert get_screen_class("proxy") is ProxyScreen

    def test_get_screen_class_unknown_returns_none(self):
        assert get_screen_class("nope") is None

    def test_classes_are_widget_types(self):
        for module_id, cls in SCREEN_MAP.items():
            assert isinstance(cls, type), f"{module_id} -> {cls!r} is not a class"
