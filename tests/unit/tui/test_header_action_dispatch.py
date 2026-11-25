"""Guard: one header-action dispatch for the whole layer.

`header_action` used to be an `if action_id == …` chain in every screen that has a header.
Six copies drifted apart (different refresh rules, different logging, one chain forgot the
`stop` branch entirely). The replacement is a table — `ModuleScreen.ACTIONS` — and this
test keeps the chains from growing back and keeps the tables honest:

* a screen may override `header_action`, but not with a chain of string comparisons;
* every method named in `ACTIONS` must exist on the class (a typo would otherwise be a
  header button that silently does nothing);
* action ids offered by `header_spec()` must be mapped.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from pentool.tui.screens.module_screen import ModuleScreen

ROOT = Path(__file__).resolve().parents[3]
SCREENS_DIR = ROOT / "pentool/tui/screens"

#: Screens still carrying an if/elif chain. Empty since step 2b finished; a screen that
#: regresses shows up as a failure of `test_no_new_header_action_chains`.
PENDING_CHAINS: set[str] = set()


def _screen_files() -> list[Path]:
    return sorted(SCREENS_DIR.rglob("screen.py"))


def _rel(path: Path) -> str:
    return path.relative_to(SCREENS_DIR).as_posix()


def _header_action_node(tree: ast.Module) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "header_action":
            return node
    return None


def _has_action_chain(func: ast.FunctionDef) -> bool:
    """True when the function compares `action_id` against string literals."""
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if not (isinstance(left, ast.Name) and left.id == "action_id"):
            continue
        if any(isinstance(op, ast.Eq) for op in node.ops):
            return True
    return False


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    return ".".join(relative.parts)


def _classes(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.name for node in tree.body if isinstance(node, ast.ClassDef) and node.name.endswith("Screen")]


def test_no_new_header_action_chains() -> None:
    offenders: list[str] = []
    for path in _screen_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        func = _header_action_node(tree)
        if func is None or not _has_action_chain(func):
            continue
        if _rel(path) in PENDING_CHAINS:
            continue
        offenders.append(f"{_rel(path)}")
    assert not offenders, (
        "header_action is a chain of `if action_id == …` again — use ModuleScreen.ACTIONS "
        f"(or override and delegate): {offenders}"
    )


def test_allowlisted_chains_are_still_pending() -> None:
    """Keeps the allowlist honest: a migrated screen must leave the set."""
    stale: list[str] = []
    for relative in sorted(PENDING_CHAINS):
        path = SCREENS_DIR / relative
        tree = ast.parse(path.read_text(encoding="utf-8"))
        func = _header_action_node(tree)
        if func is None or not _has_action_chain(func):
            stale.append(relative)
    assert not stale, f"these screens no longer have a chain — drop them from PENDING_CHAINS: {stale}"


@pytest.mark.parametrize("path", _screen_files(), ids=_rel)
def test_actions_table_points_at_real_methods(path: Path) -> None:
    module = importlib.import_module(_module_name(path))
    for class_name in _classes(path):
        cls = getattr(module, class_name, None)
        if not isinstance(cls, type) or not issubclass(cls, ModuleScreen):
            continue
        for action_id, method_name in getattr(cls, "ACTIONS", {}).items():
            assert hasattr(cls, method_name), f"{class_name}.ACTIONS[{action_id!r}] → missing method {method_name!r}"


def test_header_spec_actions_are_mapped_by_the_table() -> None:
    """Static check: the ids a screen *offers* appear as keys of its ACTIONS table."""
    problems: list[str] = []
    for path in _screen_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offered = {
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "HeaderAction"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        mapped = {
            key.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "ACTIONS" for target in node.targets)
            and isinstance(node.value, ast.Dict)
            for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        if not offered or _rel(path) in PENDING_CHAINS:
            continue
        missing = sorted(offered - mapped)
        if missing:
            problems.append(f"{_rel(path)}: {missing}")
    assert not problems, "header actions offered but not mapped in ACTIONS: " + "; ".join(problems)
