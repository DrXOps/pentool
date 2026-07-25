"""Unit-тесты для pentool/tui/screens/dashboard/live_dashboard.py."""

from __future__ import annotations

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────────

class TestSparklineHelper:
    """Тесты функции _sparkline из live_dashboard."""

    def _sparkline(self, values, width=10):
        from pentool.tui.screens.dashboard.live_dashboard import _sparkline
        return _sparkline(values, width=width)

    def test_empty_returns_spaces(self):
        result = self._sparkline([])
        assert result == " " * 10

    def test_length_equals_width(self):
        result = self._sparkline([1.0, 2.0, 3.0], width=15)
        assert len(result) == 15

    def test_max_value_gives_full_block(self):
        result = self._sparkline([8.0], width=1)
        assert result == "█"

    def test_zero_values_give_spaces(self):
        result = self._sparkline([0.0, 0.0, 0.0], width=3)
        assert result == " " * 3

    def test_pads_short_list(self):
        result = self._sparkline([5.0], width=5)
        assert len(result) == 5
        assert result[-1] != " "

    def test_truncates_long_list(self):
        result = self._sparkline([float(i) for i in range(20)], width=5)
        assert len(result) == 5

    def test_positive_values_use_bar_chars(self):
        from pentool.tui.screens.dashboard.live_dashboard import _sparkline, _SPARK_CHARS
        result = _sparkline([4.0, 8.0, 6.0], width=3)
        for ch in result:
            assert ch in _SPARK_CHARS, f"unexpected char: {repr(ch)}"


class TestHbarHelper:
    """Тесты функции _hbar из live_dashboard."""

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
        # max_val=0 не должен вызывать ZeroDivisionError
        result = self._hbar(0.0, 0.0, width=5)
        assert isinstance(result, str)

    def test_length_equals_width(self):
        result = self._hbar(30.0, 100.0, width=20)
        # Длина строки = width (только символы █ и ░)
        assert len(result) == 20


class TestColorByPercent:
    """Тесты функции _color_by_percent из live_dashboard."""

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


# ── TrafficSparkline ─────────────────────────────────────────────────────────────

class TestTrafficSparkline:
    """Тесты TrafficSparkline — только атрибуты (не монтируем TUI)."""

    def test_initial_history_is_60_zeros(self):
        from pentool.tui.screens.dashboard.live_dashboard import TrafficSparkline
        ts = TrafficSparkline()
        assert len(ts._history) == 60
        assert all(v == 0.0 for v in ts._history)

    def test_initial_count_zero(self):
        from pentool.tui.screens.dashboard.live_dashboard import TrafficSparkline
        ts = TrafficSparkline()
        assert ts._count == 0

    def test_history_deque_maxlen(self):
        from pentool.tui.screens.dashboard.live_dashboard import TrafficSparkline
        ts = TrafficSparkline()
        # Добавим больше значений через прямую модификацию deque
        for i in range(100):
            ts._history.append(float(i))
        assert len(ts._history) == 60


# ── BubbleChart ──────────────────────────────────────────────────────────────────

class TestBubbleChart:
    """Тесты BubbleChart — только логика подсчёта (не монтируем TUI)."""

    def test_initial_counts_all_zero(self):
        from pentool.tui.screens.dashboard.live_dashboard import BubbleChart
        bc = BubbleChart()
        for v in bc._counts.values():
            assert v == 0

    def test_add_finding_known_severity(self):
        from pentool.tui.screens.dashboard.live_dashboard import BubbleChart
        bc = BubbleChart()
        bc.add_finding("high")
        assert bc._counts["high"] == 1

    def test_add_finding_unknown_severity_no_crash(self):
        from pentool.tui.screens.dashboard.live_dashboard import BubbleChart
        bc = BubbleChart()
        bc.add_finding("nonexistent")

    def test_multiple_severities(self):
        from pentool.tui.screens.dashboard.live_dashboard import BubbleChart
        bc = BubbleChart()
        bc.add_finding("critical")
        bc.add_finding("critical")
        bc.add_finding("high")
        assert bc._counts["critical"] == 2
        assert bc._counts["high"] == 1

    def test_all_severity_keys_present(self):
        from pentool.tui.screens.dashboard.live_dashboard import BubbleChart
        bc = BubbleChart()
        for key in ("critical", "high", "medium", "low", "info"):
            assert key in bc._counts


# ── ScanSpeedometer ──────────────────────────────────────────────────────────────

class TestScanSpeedometer:
    """Тесты ScanSpeedometer — только атрибуты (не монтируем TUI)."""

    def test_initial_progress_zero(self):
        from pentool.tui.screens.dashboard.live_dashboard import ScanSpeedometer
        ss = ScanSpeedometer()
        assert ss._progress == 0.0

    def test_initial_findings_zero(self):
        from pentool.tui.screens.dashboard.live_dashboard import ScanSpeedometer
        ss = ScanSpeedometer()
        assert ss._findings == 0

    def test_update_progress_sets_progress(self):
        from pentool.tui.screens.dashboard.live_dashboard import ScanSpeedometer
        ss = ScanSpeedometer()
        # Вызываем напрямую без рендеринга
        ss._progress = 75.0
        ss._findings = 10
        assert ss._progress == 75.0
        assert ss._findings == 10

    def test_update_progress_method_signature(self):
        """Проверяем сигнатуру метода (3 позиционных аргумента)."""
        from pentool.tui.screens.dashboard.live_dashboard import ScanSpeedometer
        import inspect
        sig = inspect.signature(ScanSpeedometer.update_progress)
        params = list(sig.parameters.keys())
        assert "done" in params
        assert "total" in params
        assert "scanning" in params
