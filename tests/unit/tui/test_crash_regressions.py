"""Regression guards for the two crashes reported from the field (server crash log).

Both were "tests green, app dead": the Intruder started an attack and the Scanner toggled
passive mode, and the exception only appeared at runtime because it lived in a code path no
test executed. These tests walk those paths.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INTRUDER = ROOT / "pentool/tui/screens/intruder"
PANEL = ROOT / "pentool/tui/widgets/tab_panel.py"
SCANNER = ROOT / "pro/pentool/tui/screens/scanner/screen.py"


def _method_body(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(path.read_text(encoding="utf-8"), node) or ""
    return ""


def test_attack_runner_only_uses_attributes_the_screen_has() -> None:
    """`screen._TabId` crashed every attack start: everything used must exist."""
    import re

    from pentool.tui.screens.intruder.screen import IntruderScreen

    assert hasattr(IntruderScreen, "_TabId"), "экран должен отдавать суффиксы id как атрибут класса"
    assert IntruderScreen._TabId.ATTACK_PROGRESS

    source = (INTRUDER / "attack_runner.py").read_text(encoding="utf-8")
    used = {match.group(1) for match in re.finditer(r"screen\.(_[A-Za-z_][A-Za-z0-9_]*)", source)}
    from inspect import getattr_static

    screen = IntruderScreen()  # instance: _live_attacks is created in __init__

    def _exists(name: str) -> bool:
        # getattr_static: a property must not be *called* just to prove it exists
        # (some of them query the DOM and raise NoMatches outside an app).
        try:
            getattr_static(screen, name)
        except AttributeError:
            return False
        return True

    missing = sorted(name for name in used if not _exists(name))
    assert not missing, f"attack_runner обращается к несуществующим атрибутам экрана: {missing}"


def test_tab_active_assignments_are_guarded_against_both_exceptions() -> None:
    """Textual raises ValueError for an unmounted pane, NoMatches for a removed one."""
    source = PANEL.read_text(encoding="utf-8")
    assert "def _set_active" in source, "нужен один помощник вместо прямых присваиваний"
    assert "except (NoMatches, ValueError)" in source, "ValueError от validate_active должен ловиться"
    # No unguarded `tc.active = ...` outside the helper.
    body = _method_body(PANEL, "_set_active")
    assert "tc.active = tab_id" in body
    rest = source.replace(body, "")
    assert "tc.active = " not in rest.replace("tc.active = new_id", "").replace("``tc.active = tab_id``", ""), (
        "прямое присваивание active вне _set_active снова появится как краш"
    )


def test_scanner_passive_toggle_does_not_query_a_removed_button() -> None:
    if not SCANNER.is_file():
        return  # PRO tree absent — nothing to guard
    body = _method_body(SCANNER, "action_toggle_passive")
    assert 'query_one("#btn-passive"' not in body, (
        "кнопка переехала в меню шапки: toggle работает от состояния, а не от виджета"
    )
    assert "_passive_enabled" in body
