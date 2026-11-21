"""Toolbars: one row of buttons, no divider glyphs (decision 2026-11-21).

History: `Toolbar.sep()` used to be written by hand, and every toolbar edit either
dropped the divider (Add and Clear glued together) or left it in empty space
(before the "Payload set:" label). Helpers `Toolbar.grouped/row` then inserted the
`│` automatically. Finally the user compared the Repeater header (no dividers) with
the rest and said the flat row reads better: buttons are separated by spacing, and
`│` chopped one row of equal actions into "groups" that do not exist in the model.

The rule now: **toolbars have no dividers**. The helpers stay for existing call
sites but add nothing; `Toolbar.sep()` must not appear in any screen.
"""

from __future__ import annotations

from pathlib import Path

from pentool.tui.widgets.toolbar import Toolbar, ToolbarButton

ROOT = Path(__file__).resolve().parents[3]
SEARCH_ROOTS = [ROOT / "pentool" / "tui", ROOT / "pro" / "pentool" / "tui"]

NEEDLE = 'Static(" │ ", classes="toolbar-sep")'
SEP_MARKER = "toolbar-sep"


def _classes(item: object) -> str:
    return str(getattr(item, "classes", ""))


def test_no_hand_written_toolbar_separators() -> None:
    """`Static(" │ ", …)` may only live in the helper module itself."""
    allowed = {ROOT / "pentool" / "tui" / "widgets" / "toolbar.py"}
    offenders: list[str] = []
    for root in SEARCH_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if path in allowed:
                continue
            if NEEDLE in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(ROOT)))

    assert not offenders, "divider built by hand -- toolbars have none now:\n  " + "\n  ".join(offenders)


def test_grouped_adds_no_separators() -> None:
    """`grouped()` kept for existing call sites, but it is a plain list now."""
    items = Toolbar.grouped(
        ToolbarButton("a", "a"),
        ToolbarButton("b", "b"),
        ToolbarButton("c", "c"),
    )
    assert len(items) == 3
    assert not [item for item in items if SEP_MARKER in _classes(item)]


def test_screens_do_not_call_sep() -> None:
    """No screen may put a divider back by hand."""
    offenders: list[str] = []
    for root in SEARCH_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("screen.py"):
            if "Toolbar.sep()" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, "toolbar dividers are back in screens:\n  " + "\n  ".join(offenders)
