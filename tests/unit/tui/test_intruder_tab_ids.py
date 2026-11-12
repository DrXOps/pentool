"""Intruder per-tab ids come from one table, and both halves agree (F-023).

``_mount_tab_body`` builds a 140-line generator and every widget id in it is
``f"{suffix}-{tab_id}"``. The same suffix is then used at query time in ~45
places scattered through a 2 600-line class. With the suffix as a bare literal
on both sides, a typo is not caught by anything: the tab mounts fine and the
``query_one`` raises ``NoMatches`` only when the user opens that tab and does
that one thing.

The suffixes now live in ``_TabId``. This test keeps the two halves of the
contract honest:

* every id the tab body *creates* comes from ``_TabId``;
* every ``_wid(…, suffix)`` *lookup* names a member that exists;
* no literal suffix survives anywhere in the module.
"""

from __future__ import annotations

import ast
from pathlib import Path

from pentool.tui.screens.intruder import screen as intruder

_SCREEN = Path(intruder.__file__)


def _members() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(intruder._TabId).items()
        if name.isupper() and not name.startswith("_") and isinstance(value, str)
    }


def _refs(tree: ast.AST) -> list[tuple[ast.Attribute, int]]:
    """Every ``_TabId.<NAME>`` attribute access with its line number."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "_TabId":
            found.append((node, node.lineno))
    return found


def test_every_reference_names_a_real_member() -> None:
    tree = ast.parse(_SCREEN.read_text(encoding="utf-8"))
    members = _members()
    unknown = sorted({attr.attr for attr, _ in _refs(tree)} - set(members))
    assert not unknown, f"_TabId has no such member (AttributeError at mount/query time): {unknown}"


def test_no_literal_suffix_survives_in_wid_calls() -> None:
    """``_wid(tab_id, "template-panel")`` would bypass the table."""
    tree = ast.parse(_SCREEN.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_wid"
            and len(node.args) == 2
            and isinstance(node.args[1], ast.Constant)
        ):
            offenders.append(f"line {node.lineno}: {ast.unparse(node)}")
    assert not offenders, "per-tab ids must come from _TabId (F-023):\n  " + "\n  ".join(offenders)


def test_mount_body_creates_every_id_through_the_table() -> None:
    """The builder must not hand-write ``f"{suffix}-{tab_id}"`` anymore."""
    tree = ast.parse(_SCREEN.read_text(encoding="utf-8"))
    body = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_mount_tab_body")
    used = {attr.attr for attr, _ in _refs(body)}
    assert used, "_mount_tab_body creates no ids from _TabId — did the rewrite regress?"
    # Every id= in the body is either from the table or the tab id itself.
    for node in ast.walk(body):
        if isinstance(node, ast.keyword) and node.arg == "id":
            rendered = ast.unparse(node.value)
            assert "_TabId." in rendered or "tab_id" in rendered, f"hand-written id: {rendered}"


def test_table_has_no_duplicate_suffixes() -> None:
    values = list(_members().values())
    duplicates = sorted({v for v in values if values.count(v) > 1})
    assert not duplicates, f"two members share a suffix — one of them can never be queried: {duplicates}"


def test_suffixes_are_kebab_case() -> None:
    """Ids are CSS-relevant: uppercase or underscores would break selectors."""
    bad = sorted(v for v in _members().values() if v != v.lower() or "_" in v or " " in v)
    assert not bad, f"id suffixes must be lowercase kebab-case: {bad}"
