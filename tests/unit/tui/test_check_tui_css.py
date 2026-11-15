"""The CSS gate must stay green and must still catch a dead selector.

``tools/check_tui_css.py`` is the guard for REPORT.md F-008: eleven selectors
in the TUI stylesheets addressed ids/classes/classes-of-the-wrong-kind that no
Python code ever set, so those styles silently never applied. Two tests here:

1. the real tree passes (run as ``python tools/check_tui_css.py`` in CI);
2. a selector planted in a temporary copy of the tree is reported — so a
   future refactor of the checker cannot quietly turn it into a no-op.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_TOOL = _ROOT / "tools" / "check_tui_css.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("check_tui_css", _TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_css_is_consistent() -> None:
    result = subprocess.run(
        [sys.executable, str(_TOOL)],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "CSS/selectors drifted from the DOM (tools/check_tui_css.py):\n" + result.stderr


def test_checker_reports_a_dead_class(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Point the checker at a throwaway tree and require it to fail."""
    tool = _load_tool()

    tui = tmp_path / "tui"
    tui.mkdir()
    # A stylesheet whose selector names a class no Python sets, and one that
    # matches a class Python does set — only the first must be reported.
    (tui / "screen.tcss").write_text(
        ".ghost-class { height: 1; }\n.known-class { height: 2; }\n",
        encoding="utf-8",
    )
    (tui / "screen.py").write_text(
        'CSS_PATH = "screen.tcss"\nWIDGET = SomeWidget(classes="known-class")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(tool, "TUI", tui)
    monkeypatch.setattr(tool, "ROOT", tmp_path)

    code = tool.main([])
    captured = capsys.readouterr().err
    assert code == 1, f"dead selector not reported (stderr: {captured!r})"
    assert "ghost-class" in captured
    assert "known-class" not in captured


def test_attribute_selectors_are_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Textual 8 cannot parse ``[id^=…]`` — the gate must say so, not pass it."""
    tool = _load_tool()

    tui = tmp_path / "tui"
    tui.mkdir()
    (tui / "screen.tcss").write_text('Static[id^="some-id-"] { height: 1; }\n', encoding="utf-8")
    (tui / "screen.py").write_text('CSS_PATH = "screen.tcss"\nX = Y(id="some-id", classes="c")\n', encoding="utf-8")
    monkeypatch.setattr(tool, "TUI", tui)
    monkeypatch.setattr(tool, "ROOT", tmp_path)

    code = tool.main([])
    captured = capsys.readouterr().err
    assert code == 1, "attribute selector slipped through the gate"
    assert "not supported by Textual 8" in captured


def test_duplicate_id_on_one_path_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two widgets with one id in the same compose make ``query_one`` ambiguous.

    ``ComparerScreen`` had exactly this: a ``Vertical`` and the ``ContentPanel``
    inside it both carried ``id="cmp-diff-area"``, so
    ``query_one("#cmp-diff-area", ContentPanel)`` raised ``WrongType`` into a
    swallowed ``except`` and the diff never rendered.
    """
    tool = _load_tool()

    tui = tmp_path / "tui"
    tui.mkdir()
    (tui / "screen.py").write_text(
        "def compose():\n" "    with Vertical(id='dup'):\n" "        yield ContentPanel(id='dup')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tool, "TUI", tui)
    monkeypatch.setattr(tool, "ROOT", tmp_path)

    code = tool.main([])
    captured = capsys.readouterr().err
    assert code == 1, "a duplicated id slipped through the gate"
    assert "query_one becomes ambiguous" in captured


def test_same_id_in_exclusive_branches_is_allowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``if textarea: … else: RichLog`` may reuse the id — only one mounts.

    ``ContentPanel.compose`` relies on this: ``#cp-body-widget`` names the
    TextArea in one arm and the RichLog in the other.
    """
    tool = _load_tool()

    tui = tmp_path / "tui"
    tui.mkdir()
    (tui / "screen.py").write_text(
        "def compose():\n"
        "    if kind == 'textarea':\n"
        "        yield TextArea(id='body')\n"
        "    else:\n"
        "        yield RichLog(id='body')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tool, "TUI", tui)
    monkeypatch.setattr(tool, "ROOT", tmp_path)

    code = tool.main([])
    captured = capsys.readouterr().err
    assert code == 0, f"mutually exclusive ids were reported as a duplicate: {captured!r}"
