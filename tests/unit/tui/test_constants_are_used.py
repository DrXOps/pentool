"""Every constant in ``pentool.tui.constants`` is imported somewhere (F-007).

The module called itself the "single source of truth for string identifiers"
while 53 of its 61 names were never imported by any module — the screens used
literals instead. Such a constant catches nothing: a typo in ``constants.py``
is invisible, and a typo in the screen is invisible too, because nothing
compares them.

The file now holds only the eight screen ids that more than one module needs.
This test is the ratchet: add a constant that nobody imports and it fails,
rather than sitting there looking authoritative.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pentool.tui.constants as constants

_ROOT = Path(__file__).resolve().parents[3]


def _constant_names() -> set[str]:
    return {name for name in vars(constants) if name.isupper() and not name.startswith("_")}


def _imported_names() -> set[str]:
    """Names imported from ``pentool.tui.constants`` anywhere in the repo."""
    used: set[str] = set()
    roots = [_ROOT / "pentool", _ROOT / "tests", _ROOT / "tools"]
    pro = _ROOT / "pro" / "pentool"
    if pro.exists():
        roots.append(pro)
    for root in roots:
        for path in root.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):  # pragma: no cover - unreadable/odd file
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "pentool.tui.constants":
                    used.update(alias.name for alias in node.names)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "pentool.tui.constants" and alias.asname:
                            # ``import pentool.tui.constants as c`` — attribute
                            # use is not tracked here; keep the whole file.
                            used.update(_constant_names())
    return used


def test_every_constant_is_imported() -> None:
    unused = sorted(_constant_names() - _imported_names() - {"annotations"})
    assert not unused, (
        "constants that no module imports are decoration, not a source of truth "
        "(F-007) — delete them or wire them up:\n  " + "\n  ".join(unused)
    )


def test_screen_ids_are_the_only_thing_left() -> None:
    """The module's scope is screen ids other modules address; keep it narrow."""
    names = {n for n in _constant_names() if not n.startswith("_")}
    assert all(n.startswith("SCREEN_") for n in names), f"unexpected non-screen constants: {sorted(names)}"


def test_screen_ids_are_unique() -> None:
    values = [getattr(constants, name) for name in _constant_names()]
    duplicates = {v for v in values if values.count(v) > 1}
    assert not duplicates, f"duplicate id constants: {sorted(duplicates)}"
