"""ADR-11 item 3: every long-running job carries a `group=`.

A worker without a group cannot be cancelled selectively — only via `cancel_all`,
that is together with foreign work: loading, saving, tech detection. That is
exactly how the site crawl in Target outlived leaving the screen: it ran for
minutes, held the network and the process pool, while the ActivityIndicator kept
glowing. Seven `@work` decorators in Target and one in Dashboard had no group at
all.

The guard is mechanical: AST over decorators, not a list of names. A list would
have to be maintained by hand, and it would drift from the code exactly the same
way the group and name of the Intruder attack worker drifted apart.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"


def _work_decorators() -> list[tuple[str, int, str]]:
    """(file, line, function) for every `@work` / `@work(...)` without group."""
    missing: list[tuple[str, int, str]] = []
    for path in sorted(_TUI.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                name = ""
                has_group = False
                if isinstance(dec, ast.Name):
                    name = dec.id
                elif isinstance(dec, ast.Call):
                    name = getattr(dec.func, "id", "") or getattr(dec.func, "attr", "")
                    has_group = any(kw.arg == "group" for kw in dec.keywords)
                if name == "work" and not has_group:
                    rel = path.relative_to(_TUI.parent.parent)
                    missing.append((str(rel), node.lineno, node.name))
    return missing


def test_every_work_worker_has_a_group() -> None:
    missing = _work_decorators()
    assert missing == [], (
        "воркеры без group= нельзя снять точечно (ADR-11 п.3); "
        "добавь group= по назначению:\n" + "\n".join(f"  {f}:{line}: {fn}()" for f, line, fn in missing)
    )


def test_the_guard_would_notice_a_new_ungrouped_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard mutation test: without it the guard could be empty and still green."""
    fake_tui = tmp_path / "tui"
    fake_tui.mkdir()
    (fake_tui / "screen.py").write_text(
        "from textual import work\n\n\nclass S:\n    @work\n    async def _load(self) -> None:\n        return None\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("tests.unit.tui.test_worker_groups._TUI", fake_tui)
    missing = _work_decorators()
    assert len(missing) == 1
    assert missing[0][2] == "_load"


def test_the_crawl_worker_is_cancelled_when_the_target_screen_goes_away() -> None:
    """The crawl is the only worker that must die together with the screen."""
    from pentool.tui.screens.target.screen import TargetScreen

    source = (_TUI / "screens" / "target" / "screen.py").read_text(encoding="utf-8")
    assert "@work(group=CRAWL_GROUP, exclusive=True)" in source, (
        "the crawl worker is not in TargetScreen.CRAWL_GROUP — on_unmount cannot cancel it"
    )
    unmount = TargetScreen.on_unmount.__code__
    assert "cancel_group" in unmount.co_names, (
        "TargetScreen.on_unmount does not cancel the crawl — a minutes-long crawl "
        "would keep running (and keep the spider spinner lit) after the user leaves"
    )
