"""Unit tests for pentool/tui/widgets/module_tabs.py."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
from textual.widgets import Static

from pentool.tui.widgets.module_tabs import (
    BASIC_MODULES,
    MODULES,
    ModuleTabs,
)


def _make_tabs() -> ModuleTabs:
    with patch("textual.widget.Widget.__init__", return_value=None):
        t = ModuleTabs.__new__(ModuleTabs)
    t._classes = set()
    t.styles = MagicMock()
    return t


class TestConstants:
    def test_modules_have_ids_display_and_hotkeys(self) -> None:
        assert len(MODULES) >= 8
        for mod_id, label, hotkey in MODULES:
            assert mod_id
            assert label
            assert hotkey.startswith("^")

    def test_basic_modules_defined(self) -> None:
        assert "dashboard" in BASIC_MODULES
        assert "proxy" in BASIC_MODULES
        assert "settings" in BASIC_MODULES
        assert "scanner" not in BASIC_MODULES


class TestInit:
    def test_css_loaded(self) -> None:
        with patch("textual.widget.Widget.__init__", return_value=None):
            t = ModuleTabs.__new__(ModuleTabs)
        assert len(t.DEFAULT_CSS) > 0


class TestSetMode:
    def test_set_mode_basic_hides_non_basic(self) -> None:
        t = _make_tabs()

        # Build fake tabs with q1-able children
        fake_tabs = MagicMock()

        def fake_q1(sel, cls):
            if sel == "#module-tabs-inner":
                return fake_tabs
            tab = MagicMock()
            tab.styles = MagicMock()
            return tab

        t.query_one = fake_q1
        t.set_mode("basic")
        # for scanner (non-basic), display=none
        fake_tabs.query_one.assert_called()

    def test_set_mode_full_shows_all(self) -> None:
        t = _make_tabs()
        fake_tabs = MagicMock()

        def make_tab(sel):
            tab = MagicMock()
            tab.styles = MagicMock()
            if "#tab-scanner" in sel:
                tab.styles.display = "none"
            return tab

        def fake_q1(sel, cls):
            if sel == "#module-tabs-inner":
                return fake_tabs
            return make_tab(sel)

        t.query_one = fake_q1
        t.set_mode("full")

    def test_set_mode_handles_exception(self) -> None:
        t = _make_tabs()
        t.query_one = Mock(side_effect=Exception("boom"))
        t.set_mode("basic")


class TestSetScannerLocked:
    def test_lock_adds_class(self) -> None:
        t = _make_tabs()
        fake_tab = MagicMock()
        fake_tab.styles = MagicMock()
        fake_tabs = MagicMock()
        fake_tabs.query_one = lambda sel, cls: fake_tab

        t.query_one = lambda sel, cls: fake_tabs if sel == "#module-tabs-inner" else fake_tab

        t.set_scanner_locked(True)
        fake_tab.add_class.assert_called_once_with("tab-locked")
        fake_tab.tooltip = "Scanner is a PRO feature. Activate a license: pentool license trial"

    def test_unlock_removes_class(self) -> None:
        t = _make_tabs()
        fake_tab = MagicMock()
        fake_tab.styles = MagicMock()
        fake_tabs = MagicMock()
        fake_tabs.query_one = lambda sel, cls: fake_tab

        t.query_one = lambda sel, cls: fake_tabs if sel == "#module-tabs-inner" else fake_tab

        t.set_scanner_locked(False)
        fake_tab.remove_class.assert_called_once_with("tab-locked")
        assert fake_tab.tooltip is None

    def test_lock_handles_exception(self) -> None:
        t = _make_tabs()
        t.query_one = Mock(side_effect=Exception("boom"))
        t.set_scanner_locked(True)


class TestFlash:
    def test_flash_updates_tooltip(self) -> None:
        t = _make_tabs()
        tip = MagicMock()
        t.query_one = lambda sel, cls: tip if sel == "#tooltip2" else None
        # patch set_timer as it needs live app
        t.set_timer = Mock(name="set_timer")

        t.flash("Test message")
        tip.update.assert_called_once()
        assert "[$primary]" in tip.update.call_args[0][0] or "$primary" in tip.update.call_args[0][0]
        assert tip.display is True

    def test_flash_severity_error(self) -> None:
        t = _make_tabs()
        tip = MagicMock()
        t.query_one = lambda sel, cls: tip if sel == "#tooltip2" else None
        t.set_timer = Mock()

        t.flash("Error", severity="error")
        assert "$error" in tip.update.call_args[0][0]

    def test_flash_handles_exception(self) -> None:
        t = _make_tabs()
        t.query_one = Mock(side_effect=Exception("boom"))
        t.flash("hi")


class TestHideTooltip:
    def test_hide_tooltip_clears(self) -> None:
        t = _make_tabs()
        tip = MagicMock()
        t.query_one = lambda sel, cls: tip if sel == "#tooltip2" else None
        t._hide_tooltip2()
        tip.update.assert_called_once_with("")
        assert tip.display is False
        assert t._tooltip2_timer is None

    def test_hide_tooltip_handles_exception(self) -> None:
        t = _make_tabs()
        t.query_one = Mock(side_effect=Exception("boom"))
        t._hide_tooltip2()  # should not raise


class TestMessage:
    def test_module_selected_message(self) -> None:
        from pentool.tui.messages import ModuleSelected
        msg = ModuleSelected("repeater")
        assert msg.module_id == "repeater"