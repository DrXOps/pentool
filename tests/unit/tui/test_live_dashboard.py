"""Unit tests for pentool/tui/screens/dashboard/live_dashboard.py."""

from __future__ import annotations


class TestHbarHelper:
    """Tests for the _hbar function from live_dashboard."""

    def _hbar(self, value, max_val=100.0, width=10):
        from pentool.tui.screens.dashboard.live_dashboard import _hbar
        return _hbar(value, max_val=max_val, width=width)

    def test_zero_value_returns_empty_bar(self):
        result = self._hbar(0.0, 100.0, width=10)
        assert "█" not in result

    def test_full_value_fills_bar(self):
        result = self._hbar(100.0, 100.0, width=10)
        assert result.count("█") == 10

    def test_half_value_fills_half(self):
        result = self._hbar(50.0, 100.0, width=10)
        filled = result.count("█")
        assert filled == 5

    def test_zero_max_val_no_crash(self):
        # max_val=0 should not raise ZeroDivisionError
        result = self._hbar(0.0, 0.0, width=5)
        assert isinstance(result, str)

    def test_length_equals_width(self):
        result = self._hbar(30.0, 100.0, width=20)
        # String length = width (only █ and ░ chars)
        assert len(result) == 20


class TestColorByPercent:
    """Tests for the _color_by_percent function from live_dashboard."""

    def _color(self, pct):
        from pentool.tui.screens.dashboard.live_dashboard import _color_by_percent
        return _color_by_percent(pct)

    def test_low_percent_green(self):
        assert self._color(10) == "green"

    def test_medium_percent_yellow(self):
        assert self._color(65) == "yellow"

    def test_high_percent_red(self):
        assert self._color(85) == "red"

    def test_zero_green(self):
        assert self._color(0) == "green"

    def test_hundred_red(self):
        assert self._color(100) == "red"

    def test_boundary_50_yellow(self):
        assert self._color(50) == "yellow"

    def test_boundary_80_red(self):
        assert self._color(80) == "red"
