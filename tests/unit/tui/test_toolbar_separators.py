"""Разделители в тулбарах строятся только помощником, а не руками.

Причина гварда: `Toolbar.sep()` писали вручную, и при каждой правке тулбара
черту то забывали (Add и Clear слипались), то ставили в пустоту (черта перед
подписью «Payload set:»). Универсальность без проверки не держится.

Правило: `Static(" │ ", classes="toolbar-sep")` живёт **только** в
`widgets/toolbar.py`. Всё остальное — через `Toolbar.row(...)` (черта между
группами) или `Toolbar.grouped(...)` (между всеми парами).
"""

from __future__ import annotations

from pathlib import Path

from pentool.tui.widgets.toolbar import Toolbar, ToolbarButton

ROOT = Path(__file__).resolve().parents[3]
SEARCH_ROOTS = [ROOT / "pentool" / "tui", ROOT / "pro" / "pentool" / "tui"]
ALLOWED = {ROOT / "pentool" / "tui" / "widgets" / "toolbar.py"}

NEEDLE = 'Static(" │ ", classes="toolbar-sep")'


def test_no_hand_written_toolbar_separators() -> None:
    offenders: list[str] = []
    for root in SEARCH_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if path in ALLOWED:
                continue
            if NEEDLE in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(ROOT)))

    assert not offenders, (
        "разделитель собран вручную — используйте Toolbar.row(...) / Toolbar.grouped(...):\n  " + "\n  ".join(offenders)
    )


def test_row_puts_separators_between_groups_only() -> None:
    group_a = Toolbar.group_buttons(ToolbarButton("a", "a"), ToolbarButton("b", "b"))
    group_b = Toolbar.group_buttons(ToolbarButton("c", "c"))
    items = Toolbar.row(group_a, group_b)

    # 2 кнопки + черта + 1 кнопка = 4 элемента, и черта ровно одна
    assert len(items) == 4
    seps = [item for item in items if getattr(item, "classes", None) and "toolbar-sep" in str(item.classes)]
    assert len(seps) == 1


def test_grouped_puts_separators_between_every_pair() -> None:
    items = Toolbar.grouped(
        ToolbarButton("a", "a"),
        ToolbarButton("b", "b"),
        ToolbarButton("c", "c"),
    )
    assert len(items) == 5  # 3 кнопки + 2 черты
