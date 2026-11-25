"""Guard: sub-tab chips sit above the action buttons, not beside them.

Reported from the UI: in Utils the Analyze/Load/Clear/Copy/Export buttons were on the same
line as the Decoder/Comparer/Sequencer chips. The header now has two rows — chips on their
own line, actions below — and the second row collapses for modules without chips, so no
empty line appears.

Structural assertions on purpose: they do not depend on terminal size or timing.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "pentool/tui/app.py"
CSS = ROOT / "pentool/tui/app.tcss"


def _compose_tree() -> ast.ClassDef:
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and any("compose" == getattr(item, "name", "") for item in node.body)
    )


def test_chips_and_actions_live_in_different_rows() -> None:
    source = APP.read_text(encoding="utf-8")
    assert 'id="hdr-row-tabs"' in source, "нет отдельной строки для чипов подвкладок"
    assert 'id="hdr-row-main"' in source, "нет отдельной строки для действий"
    # The chips block must come before the actions block inside the header.
    tabs_at = source.index('id="hdr-row-tabs"')
    actions_at = source.index('id="hdr-actions"')
    assert tabs_at < actions_at, "чипы должны быть выше действий в разметке"


def test_chip_row_is_conditional() -> None:
    source = APP.read_text(encoding="utf-8")
    assert 'header.set_class(has_chips, "with-chips")' in source, (
        "строка чипов должна включаться только у модулей с подвкладками — иначе у остальных появится пустая строка"
    )
    css = CSS.read_text(encoding="utf-8")
    assert "#hdr-row-tabs" in css and "#module-header.with-chips #hdr-row-tabs" in css, (
        "в CSS нет правила, показывающего строку чипов только при with-chips"
    )


def test_header_query_matches_the_new_container_type() -> None:
    # `#module-header` became a Vertical; a stale Horizontal query raises WrongType in
    # every screen test, so pin the expected type here.
    source = APP.read_text(encoding="utf-8")
    assert 'self.query_one("#module-header", Vertical)' in source
    assert 'self.query_one("#module-header", Horizontal)' not in source
