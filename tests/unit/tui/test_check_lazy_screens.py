"""Tests for the lazy-screen guard (`tools/check_lazy_screens.py`).

The guard exists so the mistakes of 2026-11-20 cannot come back: a direct
`query_one(SCREEN_X)` for a screen that is no longer in the DOM, screens built
eagerly in `PentoolApp.compose()`, and a `module_screen()` result used without a
None check. Each rule is exercised on a synthetic file here — a checker that
never fires is worse than no checker, because everyone trusts its "OK".
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_TOOL = ROOT / "tools" / "check_lazy_screens.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("check_lazy_screens", _TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["check_lazy_screens"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load_tool()


def _scan_source(tool, tmp_path: Path, source: str) -> list[tuple[str, int, str]]:
    target = tmp_path / "under_test.py"
    target.write_text(source, encoding="utf-8")
    return tool.scan(roots=[tmp_path])


# ── Rule 1: no direct screen lookups ────────────────────────────────────────


def test_direct_query_one_with_screen_constant_is_flagged(tool, tmp_path: Path) -> None:
    findings = _scan_source(
        tool,
        tmp_path,
        """
from pentool.tui.constants import SCREEN_PROXY

class Screen:
    def handler(self, app):
        screen = app.query_one(SCREEN_PROXY, object)
        screen.refresh()
""",
    )
    assert len(findings) == 1
    assert "query_one(SCREEN_PROXY" in findings[0][2]
    assert "ensure_module_screen" in findings[0][2]


def test_literal_screen_selector_is_flagged(tool, tmp_path: Path) -> None:
    findings = _scan_source(
        tool,
        tmp_path,
        """
class Screen:
    def handler(self, app):
        return app.query_one("#screen-proxy", object)
""",
    )
    assert len(findings) == 1
    assert "#screen-proxy" in findings[0][2]


def test_lifecycle_api_is_not_flagged(tool, tmp_path: Path) -> None:
    """The three sanctioned ways must stay silent, or the rule gets worked around."""
    findings = _scan_source(
        tool,
        tmp_path,
        """
class Screen:
    async def handler(self, app):
        mounted = app.module_screen("proxy", object)
        if mounted is None:
            return
        mounted.refresh()
        other = await app.ensure_module_screen("target")
        if other is None:
            return
        other.refresh()
""",
    )
    assert findings == []


def test_lookup_by_screen_class_is_flagged(tool, tmp_path: Path) -> None:
    """`query_one(ScannerScreen)` — the by-type form the codemod almost missed."""
    findings = _scan_source(
        tool,
        tmp_path,
        """
class Screen:
    def handler(self, app):
        scanner = app.query_one(ScannerScreen)
        return scanner
""",
    )
    assert len(findings) == 1
    assert "ScannerScreen" in findings[0][2]


def test_lookup_of_a_non_screen_widget_is_fine(tool, tmp_path: Path) -> None:
    """Only module screens are lazy — an inner widget is still a plain query."""
    findings = _scan_source(
        tool,
        tmp_path,
        """
class Screen:
    def handler(self):
        return self.query_one("#proxy-subtabs", TabbedContent)
""",
    )
    assert findings == []


# ── Rule 2: compose() builds one screen ─────────────────────────────────────


def test_eager_mounting_in_compose_is_flagged(tool, tmp_path: Path) -> None:
    findings = _scan_source(
        tool,
        tmp_path,
        """
class PentoolApp:
    def compose(self):
        with Switcher():
            yield DashboardScreen(id="screen-dashboard")
            yield ProxyScreen(id="screen-proxy")
""",
    )
    assert len(findings) == 1
    assert "ProxyScreen" in findings[0][2]
    assert "LazyScreenManager" in findings[0][2]


def test_start_screen_in_compose_is_fine(tool, tmp_path: Path) -> None:
    findings = _scan_source(
        tool,
        tmp_path,
        """
class PentoolApp:
    def compose(self):
        with Switcher(initial="screen-dashboard"):
            yield DashboardScreen(id="screen-dashboard")
""",
    )
    assert findings == []


# ── Rule 3: module_screen() results are None-checked ───────────────────────────


def test_unchecked_get_screen_result_is_flagged(tool, tmp_path: Path) -> None:
    findings = _scan_source(
        tool,
        tmp_path,
        """
class Screen:
    def handler(self, app):
        proxy = app.module_screen("proxy", object)
        proxy.refresh()
""",
    )
    assert len(findings) == 1
    assert "may be None" in findings[0][2]
    assert "proxy.refresh" in findings[0][2]


def test_guard_after_assignment_is_accepted(tool, tmp_path: Path) -> None:
    findings = _scan_source(
        tool,
        tmp_path,
        """
class Screen:
    def handler(self, app):
        proxy = app.module_screen("proxy", object)
        if proxy is None:
            return
        proxy.refresh()
""",
    )
    assert findings == []


def test_early_return_guard_covers_later_uses(tool, tmp_path: Path) -> None:
    findings = _scan_source(
        tool,
        tmp_path,
        """
class Screen:
    def handler(self, app):
        proxy = app.module_screen("proxy", object)
        if not proxy:
            return
        proxy.refresh()
        proxy.reload()
""",
    )
    assert findings == []


def test_use_before_the_guard_is_flagged(tool, tmp_path: Path) -> None:
    """Order matters: checking after the access does not help."""
    findings = _scan_source(
        tool,
        tmp_path,
        """
class Screen:
    def handler(self, app):
        proxy = app.module_screen("proxy", object)
        proxy.refresh()
        if proxy is None:
            return
""",
    )
    assert len(findings) == 1
    assert findings[0][1] == 5  # the `proxy.refresh()` line


# ── The real tree ───────────────────────────────────────────────────────────


def test_repository_is_clean() -> None:
    """The guard must pass on the code it protects — otherwise it is just noise."""
    tool = _load_tool()
    findings = tool.scan()
    assert not findings, "lazy-screen guard findings:\n  " + "\n  ".join(f"{p}:{n}: {m}" for p, n, m in findings)


def test_main_exit_codes(tool, capsys: pytest.CaptureFixture[str]) -> None:
    assert tool.main([]) == 0
    assert "OK" in capsys.readouterr().out
