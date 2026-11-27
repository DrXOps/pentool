"""ADR-3 as a guard: no `@on(...)` handlers inside mixins.

ADR-3 says Textual only introspects the direct App/Widget class for `@on` handlers, so a handler
living in a mixin is silently never dispatched — the symptom is "the event does nothing". Until
now that rule lived in a document; this test makes it fail loudly. Docstring mentions of `@on`
are not handlers, so the check walks the AST instead of grepping.
"""

from __future__ import annotations

import ast
from pathlib import Path

MIXINS = Path(__file__).resolve().parents[3] / "pentool/tui/mixins"


def _handler_decorators(node: ast.AST) -> list[str]:
    decorators = []
    for decorator in node.decorator_list:  # type: ignore[attr-defined]
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id in {"on", "watch", "work"}:
            decorators.append(target.id)
    return decorators


def test_no_textual_handlers_live_in_mixins() -> None:
    offenders: list[str] = []
    for path in sorted(MIXINS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in _handler_decorators(node):
                if decorator == "work":
                    continue  # `@work` is fine in a mixin: the method is called, not dispatched
                offenders.append(f"{path.name}:{node.lineno} {node.name} @{decorator}")

    assert not offenders, (
        "ADR-3: обработчики Textual не диспетчеризуются из миксинов — "
        "перенесите их в прямой класс App/Widget:\n  " + "\n  ".join(offenders)
    )


def _call_counts(tree: ast.AST) -> tuple[int, int]:
    """Count real .subscribe(...) calls and every unsubscribe variant."""
    subs = unsubs = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        name = node.func.attr
        if name == "subscribe":
            subs += 1
        elif name in {"unsubscribe", "unsubscribe_all"}:
            unsubs += 1
    return subs, unsubs


def test_global_subscriptions_are_released() -> None:
    """ADR-12: a global subscription must have a matching release.

    Counted on the AST, not by grep: events_handlers.py only *mentions* subscribe(...) in
    its docstring, and pp.py releases with unsubscribe_all (a different name, same
    contract), so a text search reports a false asymmetry.
    """
    offenders: list[str] = []
    for path in sorted(MIXINS.parent.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        subs, unsubs = _call_counts(tree)
        if subs and unsubs < subs:
            offenders.append(f"{path.relative_to(MIXINS.parents[1]).as_posix()}: subscribe={subs}, release={unsubs}")

    assert not offenders, "ADR-12: подписка без снятия — событие живёт дольше экрана:\n  " + "\n  ".join(offenders)
