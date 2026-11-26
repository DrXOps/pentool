"""Regression guard: every name-based ``on_*`` handler must be reachable.

Textual resolves a handler declared *without* ``@on`` by its derived name:
``Message.handler_name`` is ``on_`` + the snake_case of the message class's
qualified name, so ``ProxyDataTable.ScrolledToTop`` → ``on_proxy_data_table_scrolled_to_top``.

Handlers written as ``on__proxy_data_table_scrolled_to_top`` (double
underscore) are **never** dispatched. That exact typo silently disabled
infinite-scroll history loading and the comment-icon click in the Proxy
screen (docs/audit/2026-11-21-tui-report.md, F-041), and the same class of typo killed
``on_input_blur`` (the message is ``Input.Blurred`` → ``on_input_blurred``,
F-042), ``on_static_click`` (``Static`` posts no click message, F-043) and
``on_data_table_row_activated`` (no such message in Textual 8, F-044).

This test walks the real ``pentool.tui`` AST, so it sees handlers regardless
of whether their host module can be imported in the test process.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest
from textual.message import Message

_TUI_ROOT = Path(__file__).resolve().parents[3] / "pentool" / "tui"

# Lifecycle handlers dispatched by Textual itself (event names that are not
# derived from a Message subclass in the modules we import).
_LIFECYCLE = {
    "on_app_blur",
    "on_app_focus",
    "on_blur",
    "on_click",
    "on_descendant_blur",
    "on_descendant_focus",
    "on_enter",
    "on_event",
    "on_focus",
    "on_hide",
    "on_idle",
    "on_key",
    "on_leave",
    "on_load",
    "on_mount",
    "on_mouse_capture",
    "on_mouse_down",
    "on_mouse_move",
    "on_mouse_release",
    "on_mouse_scroll_down",
    "on_mouse_scroll_up",
    "on_mouse_up",
    "on_paste",
    "on_print",
    "on_prune",
    "on_ready",
    "on_resize",
    "on_screen_resume",
    "on_screen_suspend",
    "on_show",
    "on_unmount",
}

_TEXTUAL_MODULES = (
    "textual",
    "textual.app",
    "textual.containers",
    "textual.events",
    "textual.screen",
    "textual.widget",
    "textual.widgets",
    "textual.widgets._button",
    "textual.widgets._checkbox",
    "textual.widgets._content_switcher",
    "textual.widgets._data_table",
    "textual.widgets._input",
    "textual.widgets._list_view",
    "textual.widgets._option_list",
    "textual.widgets._select",
    "textual.widgets._switch",
    "textual.widgets._tabs",
    "textual.widgets._text_area",
    "textual.widgets._toggle_button",
    "textual.widgets._tree",
    "textual.worker",
    "textual_fastdatatable",
    "textual_fastdatatable.data_table",
)


def _add_message_names(obj: object, names: set[str], depth: int = 0) -> None:
    if not inspect.isclass(obj):
        return
    if issubclass(obj, Message) and obj is not Message:
        handler_name = getattr(obj, "handler_name", None)
        if handler_name:
            names.add(handler_name)
    if depth >= 2:
        return
    for member in vars(obj).values():
        if inspect.isclass(member):
            _add_message_names(member, names, depth + 1)


@pytest.fixture(scope="module")
def known_handler_names() -> set[str]:
    names: set[str] = set(_LIFECYCLE)
    for module_name in _TEXTUAL_MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception:  # pragma: no cover - optional dependency
            continue
        for member in vars(module).values():
            _add_message_names(member, names)

    import pentool

    for info in pkgutil.walk_packages(pentool.__path__, "pentool."):
        try:
            module = importlib.import_module(info.name)
        except Exception:  # pragma: no cover - optional/PRO packages
            continue
        for member in vars(module).values():
            _add_message_names(member, names)
    return names


def _name_based_handlers() -> list[tuple[str, int, str, str]]:
    """(file, lineno, class, handler) for every ``on_*`` declared by name."""
    found: list[tuple[str, int, str, str]] = []
    for path in sorted(_TUI_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if not item.name.startswith("on_"):
                    continue
                decorators = {ast.unparse(d) for d in item.decorator_list}
                if any(d == "on" or d.startswith("on(") for d in decorators):
                    continue  # @on(...) — registered by type, not by name
                rel = path.relative_to(_TUI_ROOT.parent.parent)
                found.append((str(rel), item.lineno, node.name, item.name))
    return found


def test_every_name_based_handler_is_reachable(known_handler_names: set[str]) -> None:
    """A handler whose name matches no message is dead code — or a typo."""
    unreachable = [
        f"{path}:{lineno} {cls}.{handler}"
        for path, lineno, cls, handler in _name_based_handlers()
        if handler not in known_handler_names
    ]
    assert not unreachable, "Name-based Textual handlers that no message can reach:\n  " + "\n  ".join(unreachable)


def test_mixin_handlers_are_reachable_by_name(known_handler_names: set[str]) -> None:
    """Mixins must use the naming convention, and those names must resolve.

    ``@on`` declared in a plain mixin is collected into the *mixin's* class
    dict, which Textual never consults (ADR-3). The naming convention is
    resolved over the MRO, so this is the only workable form there.
    """
    mixins_dir = _TUI_ROOT / "mixins"
    for path in sorted(mixins_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                decorators = {ast.unparse(d) for d in item.decorator_list}
                assert not any(d == "on" or d.startswith("on(") for d in decorators), (
                    f"{path.name}:{item.lineno} {node.name}.{item.name} uses @on() "
                    "inside a mixin — Textual will not register it (see ADR-3)"
                )
                if item.name.startswith("on_") and not item.name.startswith("on_" + "_"):
                    assert item.name in known_handler_names, (
                        f"{path.name}:{item.lineno} {node.name}.{item.name} matches "
                        "no Textual message — the handler can never fire"
                    )
