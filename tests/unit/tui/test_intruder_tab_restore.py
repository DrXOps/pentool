"""Restoring Intruder tabs from the project DB.

``IntruderScreen._do_load_tabs_from_db`` reads the dicts produced by
``IntruderStorage.get_tabs()``. That dict is built with the key ``tab_name``,
but the restore path asked for ``td.get("name", …)`` — a key that is never
there. Nothing failed: ``dict.get`` with a default is silent by construction,
so every restored tab came back called the same fallback and a project with
five tabs reopened as five identical labels.

The same shape of mistake is one keystroke away for every other key, so
``test_every_key_read_here_is_produced_there`` compares the two halves
statically. A behaviour test alone would not catch a *new* key: it would only
cover the keys someone thought to write a fixture for.

The second half of the file covers what the tab actually contains after a
restore — the payload list and the attack type — because "the name is right"
is not the same claim as "the tab came back as it was saved".
"""

from __future__ import annotations

import ast
from pathlib import Path

from textual.app import App, ComposeResult

from pentool.api.intruder_api import AttackType, CharPayloadSource
from pentool.api.payload_serialization import serialize_payloads
from pentool.storage.intruder_storage import IntruderStorage
from pentool.tui.screens.intruder.screen import IntruderScreen
from pentool.tui.widgets.toolbar_button import ToolbarButton

_SCREEN = Path(__file__).resolve().parents[3] / "pentool" / "tui" / "screens" / "intruder" / "screen.py"
_STORAGE = Path(__file__).resolve().parents[3] / "pentool" / "storage" / "intruder_storage.py"

#: Keys ``_do_load_tabs_from_db`` is allowed to read on top of the storage
#: contract: ``id`` is the older field name kept for compatibility.
_EXTRA_READS = {"id", "name", "_state"}


class _App(App):
    def compose(self) -> ComposeResult:
        yield IntruderScreen()


def _function(path: Path, name: str) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def _keys_read_from_rows() -> set[str]:
    """String keys ``_do_load_tabs_from_db`` pulls out of a tab row."""
    keys: set[str] = set()
    for node in ast.walk(_function(_SCREEN, "_do_load_tabs_from_db")):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
    return keys


def _keys_produced_by_get_tabs() -> set[str]:
    """String keys the ``return`` dict of ``get_tabs`` is built with."""
    keys: set[str] = set()
    for node in ast.walk(_function(_STORAGE, "get_tabs")):
        if isinstance(node, ast.Dict):
            keys |= {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return keys


def test_every_key_read_here_is_produced_there() -> None:
    """A restore path reading a key the storage never sets is dead code."""
    read = _keys_read_from_rows()
    produced = _keys_produced_by_get_tabs()
    assert produced, "could not find the row dict in IntruderStorage.get_tabs — did it change shape?"
    assert read, "could not find any td.get(...) calls in _do_load_tabs_from_db"
    ghosts = sorted(read - produced - _EXTRA_READS)
    assert not ghosts, (
        "these keys are read from a tab row but IntruderStorage.get_tabs() never sets them — "
        f"the .get() default wins silently: {ghosts}"
    )


class TestRestoreFromStorage:
    async def test_a_saved_project_reopens_with_its_tabs_intact(self, tmp_path: Path) -> None:
        """One save round trip through the real storage, then a real restore."""
        from pentool.core.db_schema import init_db as init_schema

        db = str(tmp_path / "project.db")
        await init_schema(db)
        storage = IntruderStorage(db_path=db)
        try:
            await storage.save_state(
                tab_name="Battering",
                template="GET /a HTTP/1.1\r\nHost: a\r\n\r\nx=§1§",
                attack_type="battering_ram",
                payloads=serialize_payloads([CharPayloadSource("ab", 1, 1)]),
                tab_uid="uid-a",
            )
            await storage.save_state(
                tab_name="Pitchfork",
                template="POST /b HTTP/1.1\r\nHost: b\r\n\r\ny=§1§",
                attack_type="pitchfork",
                payloads=serialize_payloads([["p+q", "r+s"]]),
                tab_uid="uid-b",
            )
            rows = await storage.get_tabs()
        finally:
            await storage.close()

        # Ordering is by ``updated_at`` with one-second resolution, so two rows
        # written in the same second come back in either order; the test asserts
        # on the set and looks rows up by uid.
        assert {r["tab_name"] for r in rows} == {"Pitchfork", "Battering"}

        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            screen = pilot.app.query_one(IntruderScreen)
            panel = screen._tc_panel

            await screen._do_load_tabs_from_db(_StubApi(rows))
            for _ in range(6):
                await pilot.pause()

            # Screen.mount() creates its own default tab (uuid4 uid); the
            # restored ones are the two the storage just handed over.
            restored = [s for s in panel.all_states if s.tab_uid in {"uid-a", "uid-b"}]
            assert {s.name for s in restored} == {"Pitchfork", "Battering"}, (
                f"restored tabs take their names from the DB's tab_name — got {[s.name for s in restored]}"
            )
            by_uid = {s.tab_uid: s for s in restored}
            assert by_uid["uid-a"].attack_type == AttackType.BATTERING_RAM
            assert by_uid["uid-b"].attack_type == AttackType.PITCHFORK
            assert by_uid["uid-a"].template_text.startswith("GET /a")

            # Every restored tab has a tab_id of its own, matching a mounted pane.
            assert len({s.tab_id for s in restored}) == 2
            for state in restored:
                pane = panel.tabs_content.get_pane(state.tab_id)
                assert pane is not None, f"{state.name} has no pane — its body mounted under another id"

            # The last tab of the batch is active and painted without a click.
            active = by_uid["uid-b"]
            assert panel.active_tab_id == active.tab_id
            listing = screen.query_one(f"#payload-list-{active.tab_id}")
            assert len(listing.children) == 2, (
                f"the active restored tab painted {len(listing.children)} payload rows, expected 2"
            )
            button = screen.query_one(f"#btn-attack-type-{active.tab_id}", ToolbarButton)
            assert "Pitchfork" in button.label

            # The other one loads when opened.
            panel.switch_to(by_uid["uid-a"].tab_id)
            for _ in range(6):
                await pilot.pause()
            listing = screen.query_one(f"#payload-list-{by_uid['uid-a'].tab_id}")
            assert len(listing.children) == 2, (
                f"opening a restored tab must paint its own payloads, got {len(listing.children)} rows"
            )
            button = screen.query_one(f"#btn-attack-type-{by_uid['uid-a'].tab_id}", ToolbarButton)
            assert "Battering Ram" in button.label


class _StubApi:
    """Just the one method the restore path calls."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def get_tabs(self) -> list[dict]:
        return self._rows
