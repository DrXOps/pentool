"""Journal rotation (T-021) and the hot-path log level rule (T-026).

T-021: the journal had no rotation — one file reached 4.7 GB in a week of work,
after which `grep` over it stopped being usable and every log record became I/O
on the critical path. `setup_logging` now installs a `RotatingFileHandler`
(50 MB × 10 archives by default, overridable for tests/CI).

T-026: the level rule for the TUI, enforced by AST over `pentool/tui`:
``INFO`` is for lifecycle (start/stop, project switch, reload), ``DEBUG`` is for
anything that happens *per unit of data* — a captured request, a tick, a flushed
batch. The three lines in the Proxy history hot path were ``INFO``, which is how
the journal grew linearly with traffic.
"""

from __future__ import annotations

import ast
import logging
import logging.handlers
from pathlib import Path

import pytest

from pentool.core.logging import DEFAULT_LOG_BACKUP_COUNT, DEFAULT_LOG_MAX_BYTES, setup_logging

TUI_DIRS = [
    Path(__file__).resolve().parents[3] / "pentool" / "tui",
    Path(__file__).resolve().parents[3] / "pro" / "pentool" / "tui",
]

#: Methods whose body runs once per captured item (request, row, tick, flush).
HOT_PATH_PREFIXES = ("add_", "update_", "_store_", "_flush_", "_on_bus_", "_tick", "push_request")


# ── T-021: rotation ─────────────────────────────────────────────────────────


def _file_handler(logger: logging.Logger) -> logging.Handler | None:
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            return handler
    return None


def test_setup_logging_rotates_the_journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logger = logging.getLogger("pentool")
    previous_handlers = list(logger.handlers)
    monkeypatch.setenv("PENTOOL_LOG_FILE", str(tmp_path / "pentool.log"))
    monkeypatch.delenv("PENTOOL_LOG_MAX_BYTES", raising=False)
    try:
        setup_logging(str(tmp_path / "pentool.log"), "INFO")
        handler = _file_handler(logger)
        assert isinstance(handler, logging.handlers.RotatingFileHandler), (
            "journal has no rotation — a single file grows until the disk fills (T-021)"
        )
        assert handler.maxBytes == DEFAULT_LOG_MAX_BYTES
        assert handler.backupCount == DEFAULT_LOG_BACKUP_COUNT
    finally:
        logger.handlers.clear()
        logger.handlers.extend(previous_handlers)


def test_rotation_can_be_switched_off_for_tests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`PENTOOL_LOG_MAX_BYTES=0` keeps a plain file — tests only need the writes."""
    logger = logging.getLogger("pentool")
    previous_handlers = list(logger.handlers)
    monkeypatch.setenv("PENTOOL_LOG_FILE", str(tmp_path / "pentool.log"))
    monkeypatch.setenv("PENTOOL_LOG_MAX_BYTES", "0")
    try:
        setup_logging(str(tmp_path / "pentool.log"), "INFO")
        handler = _file_handler(logger)
        assert handler is not None
        assert not isinstance(handler, logging.handlers.RotatingFileHandler)
    finally:
        logger.handlers.clear()
        logger.handlers.extend(previous_handlers)


# ── T-026: hot-path level rule ─────────────────────────────────────────────


def _hot_path_info_calls(path: Path) -> list[str]:
    """`logger.info(...)` inside per-item methods — the shape that floods the journal."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith(HOT_PATH_PREFIXES):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
                continue
            if child.func.attr != "info":
                continue
            receiver = ast.unparse(child.func.value).lower()
            if "log" not in receiver:
                continue
            offenders.append(f"{node.name}:{child.lineno} {ast.unparse(child)[:80]}")
    return offenders


def test_no_info_logging_on_the_hot_path() -> None:
    offenders: list[str] = []
    for root in TUI_DIRS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            offenders.extend(f"{path.name}:{entry}" for entry in _hot_path_info_calls(path))
    assert not offenders, (
        "per-item code logs at INFO — the journal grows with traffic (T-026/T-021); "
        "use DEBUG for per-request/per-tick lines:\n  " + "\n  ".join(offenders)
    )


def test_proxy_history_hot_path_is_debug() -> None:
    """The three lines that flooded the journal must stay DEBUG."""
    path = TUI_DIRS[0] / "screens" / "proxy" / "screen.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {
        "PROXY SCREEN: add_request_row:",
        "PROXY SCREEN: update_request_row:",
        "PROXY SCREEN: _store_request:",
    }
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        for argument in node.args:
            text = argument.value if isinstance(argument, ast.Constant) else ""
            if not isinstance(text, str):
                continue
            for fragment in wanted:
                if text.startswith(fragment):
                    found[fragment] = node.func.attr
    assert set(found) == wanted, f"hot-path log lines not found: {sorted(wanted - set(found))}"
    wrong = {fragment: level for fragment, level in found.items() if level != "debug"}
    assert not wrong, f"hot-path lines are not DEBUG: {wrong}"
