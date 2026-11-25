"""Guard: the app and the project manager do not reach into screen internals.

`ProjectManager` used to `match module_id` and call `screen._reload_from_storage`,
`screen._get_or_create_api`, `screen._populate_from_db`, `screen._load_findings_worker`,
`screen._clear_scan_logs`, `screen._target_api`, `screen._selected_req_id` — 188
`# type: ignore[attr-defined]` in the layer mostly came from this, and one path could
write into a database that was already closed (REPORT.md, E6/F-014).

Screens that own project data now implement `ProjectReloadable`
(`reload_from_project` / `reset_for_new_project` / `close_storage`), and that is the only
way in. This test keeps it that way.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TUI = ROOT / "pentool/tui"

#: Files that talk to screens and therefore must not touch their privates.
CALLERS = ("project_manager.py", "app.py")

#: The one attribute the app legitimately pokes: saving in-flight workers is a Textual
#: concern, not project data.
ALLOWED = {"_cancel_save_workers"}


def _private_screen_access(path: Path) -> list[str]:
    """Attribute reads/writes on screen variables, e.g. ``screen._api``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if not node.attr.startswith("_"):
            continue
        if node.attr in ALLOWED:
            continue
        value = node.value
        name = ""
        if isinstance(value, ast.Name):
            name = value.id
        elif isinstance(value, ast.Attribute):
            name = value.attr
        # `textual.screen.Screen` is the framework class (the app monkey-patches its
        # event methods on purpose); only instances of our screens are of interest.
        if name == "Screen" or not name.lower().endswith("screen"):
            continue
        found.append(f"{path.name}:{node.lineno}: {name}.{node.attr}")
    return found


@pytest.mark.parametrize("filename", CALLERS)
def test_no_private_screen_access(filename: str) -> None:
    offenders = _private_screen_access(TUI / filename)
    assert not offenders, (
        "the app/manager reads screen internals again — add a public method or the "
        f"ProjectReloadable contract instead: {offenders}"
    )


def test_reloadable_screens_implement_the_contract() -> None:
    """Every module the manager reloads can actually be reloaded through the contract."""
    from pentool.tui.project_manager import _RELOADABLE_MODULES
    from pentool.tui.screen_registry import get_screen_class

    missing: list[str] = []
    for module_id in _RELOADABLE_MODULES:
        if module_id == "scanner":
            # PRO: the class only exists when the package is installed; the contract
            # lives in pro/pentool/tui/screens/scanner/screen.py.
            from pentool.tui.screens import SCANNER_SCREEN_AVAILABLE

            if not SCANNER_SCREEN_AVAILABLE:
                continue
        cls = get_screen_class(module_id)
        if cls is None:
            continue
        for method in ("reload_from_project", "reset_for_new_project"):
            if not callable(getattr(cls, method, None)):
                missing.append(f"{module_id}.{method}")
    assert not missing, f"reloadable screens missing the ProjectReloadable contract: {missing}"


def test_contract_is_structural() -> None:
    """`ProjectReloadable` is a runtime-checkable Protocol, not a base class to inherit."""
    from pentool.tui.screens.module_screen import ProjectReloadable

    class _Screen:
        async def reload_from_project(self, db_path: str) -> None:
            return None

        async def reset_for_new_project(self) -> None:
            return None

        async def close_storage(self) -> None:
            return None

    assert isinstance(_Screen(), ProjectReloadable)
