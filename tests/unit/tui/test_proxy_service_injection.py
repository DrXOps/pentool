"""ProxyScreen gets its service through the constructor, not by field injection.

F-012: ``PentoolApp.on_mount`` did ``proxy_screen._proxy_service =
self._proxy_service`` — a private field of a mounted widget assigned from
outside. Consequences: the screen could be used before the assignment and every
call site had to guard ``if self._proxy_service is None``; a test could not pass
a fake through the constructor even though ``ProxyScreen.__init__`` already
accepted one.

The service is now built in ``PentoolApp.__init__`` (its constructor touches no
event loop — only ``init_storage`` opens the database) and handed to
``compose``. These tests pin the two halves and refuse the old pattern by
scanning the AST for writes to ``._proxy_service`` outside the screen class.
"""

from __future__ import annotations

import ast
from pathlib import Path

from pentool.tui.screens.proxy.screen import ProxyScreen

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"


def test_screen_accepts_service_through_constructor() -> None:
    """The constructor is the only supported way in."""
    sentinel = object()
    screen = ProxyScreen(proxy_service=sentinel)  # type: ignore[arg-type]
    assert screen._proxy_service is sentinel


def test_screen_stays_usable_without_service() -> None:
    """Default stays ``None`` so the screen can be built standalone in tests."""
    assert ProxyScreen()._proxy_service is None


def test_service_is_not_assigned_from_outside_the_screen() -> None:
    """No module writes ``.<x>._proxy_service`` except ProxyScreen.__init__."""
    offenders: list[str] = []
    for path in sorted(_TUI.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "_proxy_service"
                    and not (isinstance(target.value, ast.Name) and target.value.id == "self")
                ):
                    offenders.append(f"{path.relative_to(_TUI.parent.parent)}:{node.lineno}")
    assert not offenders, (
        "ProxyService must be injected through ProxyScreen(proxy_service=…), "
        "not assigned to a private field from outside (F-012):\n  " + "\n  ".join(offenders)
    )
