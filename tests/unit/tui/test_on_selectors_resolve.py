"""A message handler addressed to an id nobody creates is dead code.

Textual dispatches ``@on(SomeMessage, "#some-id")`` only when a widget with
that exact id exists. When it does not, nothing warns: the decorator is valid,
the module imports, the app starts — the handler simply never runs.

That is not hypothetical. Commit cb11bfd rewrote the Intruder global toolbar
and dropped "Clear results" and "Export CSV" while leaving both in the
dispatch table; the buttons were gone for five weeks and no test noticed.
A second case, ``#settings-save-ai``, made the MCP port and model path inputs
on the Settings → AI tab unsavable: they load from config, but the only code
that writes them back was behind a button that no longer existed.

Reading the app as source is enough to catch both, and it is cheaper than
booting every screen. For each ``@on(..., "#id")`` the id must be built
somewhere in ``pentool/tui`` — as an ``id=`` literal, as the second positional
argument of ``ToolbarButton`` (its id is positional), or as the static prefix
of an f-string (``ToolbarButton(lbl, f"cp-btn-{key}")`` yields ``cp-btn-``,
which covers ``cp-btn-special``).

Class selectors (``.foo``) are the CSS gate's business; this file only looks
at ids.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"

#: Constructors that take a widget id positionally: name → argument index.
#: ``ToolbarButton(label, id)`` passes it second; ``static_tabs(container_id, ...)``
#: passes it first, because the id names the TabbedContent it builds.
_POSITIONAL_ID_CTORS = {"ToolbarButton": 1, "static_tabs": 0}

#: Ids supplied by something outside this package's compose() calls.
_EXTERNAL_IDS = {
    # A selector that scopes a handler to messages raised under an ancestor
    # mounted by PentoolApp, not to a widget created here.
    "intruder-tabs",
}


def _module_files() -> list[Path]:
    return sorted(_TUI.rglob("*.py"))


def _add_id(target: set[str], prefixes: set[str], node: ast.AST) -> None:
    """Record an id expression: literal, f-string prefix, or constant."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        target.add(node.value)
    elif isinstance(node, ast.JoinedStr) and node.values:
        head = node.values[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            prefixes.add(head.value.rstrip("-"))


def _created_ids(files: list[Path]) -> tuple[set[str], set[str]]:
    """All (exact ids, id prefixes) built anywhere in the TUI."""
    ids: set[str] = set()
    prefixes: set[str] = set()
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "id":
                    _add_id(ids, prefixes, kw.value)
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            position = _POSITIONAL_ID_CTORS.get(name)
            if position is not None and len(node.args) > position:
                _add_id(ids, prefixes, node.args[position])
    return ids, prefixes


def _selector_ids(path: Path) -> list[str]:
    """Ids from ``@on(Message, "#the-id[:child]")`` decorators — via AST.

    Reading decorators structurally rather than by regex matters: a docstring
    that *mentions* ``@on(ToolbarButton.Pressed, "#btn-id")`` is not a handler,
    and a regex would demand a widget for the example in it.
    """
    found: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call) or len(deco.args) < 2:
                continue
            selector = deco.args[1]
            if not (isinstance(selector, ast.Constant) and isinstance(selector.value, str)):
                continue
            text = selector.value
            if not text.startswith("#"):
                continue
            head = text[1:].split(":", 1)[0]
            if head:
                found.append(head)
    return found


@pytest.mark.parametrize("path", _module_files(), ids=lambda p: str(p.relative_to(_TUI)))
def test_every_on_selector_has_a_widget(path: Path) -> None:
    selectors = _selector_ids(path)
    if not selectors:
        pytest.skip("no id-scoped @on selectors")

    ids, prefixes = _created_ids(_module_files())
    missing = sorted(
        {
            sel
            for sel in selectors
            if sel not in ids and sel not in _EXTERNAL_IDS and not any(sel.startswith(prefix) for prefix in prefixes)
        }
    )
    assert not missing, (
        f"{path.relative_to(_TUI.parent.parent)}: @on handlers address ids no widget creates — "
        f"they will never fire: {missing}. Either mount the widget or delete the handler."
    )


class TestTheGuardItself:
    """The guard is only worth its runtime if it fails on a planted orphan."""

    def test_planted_orphan_is_reported(self, tmp_path: Path) -> None:
        probe = tmp_path / "probe.py"
        probe.write_text(
            "from textual.widgets import Static\n"
            "class W(Static):\n"
            "    def compose(self):\n"
            '        yield Static("x", id="real-id")\n'
            '    @on(None, "#real-id")\n'
            "    def a(self): ...\n"
            '    @on(None, "#ghost-id")\n'
            "    def b(self): ...\n",
            encoding="utf-8",
        )
        assert _selector_ids(probe) == ["real-id", "ghost-id"]
        ids, _ = _created_ids([probe])
        assert "real-id" in ids
        assert "ghost-id" not in ids

    def test_docstring_example_is_not_a_handler(self, tmp_path: Path) -> None:
        """The false positive that a regex version produced on toolbar_button.py."""
        probe = tmp_path / "probe.py"
        probe.write_text(
            'class W:\n    """Allows @on(ToolbarButton.Pressed, "#btn-id") selectors."""\n',
            encoding="utf-8",
        )
        assert _selector_ids(probe) == []

    def test_dynamic_button_prefix_resolves_a_literal_selector(self, tmp_path: Path) -> None:
        """ContentPanel builds ``cp-btn-{key}`` in a loop; the literal must match."""
        probe = tmp_path / "probe.py"
        probe.write_text(
            'def compose(keys):\n    for k in keys:\n        yield ToolbarButton("lbl", f"cp-btn-{k}")\n',
            encoding="utf-8",
        )
        _, prefixes = _created_ids([probe])
        assert any("cp-btn-special".startswith(p) for p in prefixes)
