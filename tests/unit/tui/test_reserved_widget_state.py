"""No screen may keep its own state in `self._running` — that is Textual's pump flag.

`textual.message_pump.MessagePump` sets `_running` in `__init__` (False) and in
`_process_messages` (True); the flag tells the framework whether the pump is alive. A
screen that stores "the attack is running" there fights the framework: `action_stop()`
writing `_running = False` makes Textual believe the pump stopped.

Recon did exactly that (found while wiring "send to Recon"); the state is now
`_recon_active`. This test keeps the next screen from repeating it.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
#: Only the TUI tree: every class there inherits Textual's MessagePump, so the reserved
#: attributes are really the framework's. `pentool/modules/proxy.py` and
#: `pentool/proxy/client.py` also keep a `_running` flag, but they are plain classes.
CODE_ROOTS = (ROOT / "pentool" / "tui", ROOT / "pro" / "pentool" / "tui")

#: Names Textual owns in MessagePump/Widget; screens must not reuse them for their state.
RESERVED = {"_running": "Textual's MessagePump liveness flag"}


def _offenders() -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for base in CODE_ROOTS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                # Assignments to self._running inside a class method.
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                            and target.attr in RESERVED
                        ):
                            rows.append((path.relative_to(ROOT).as_posix(), node.lineno, target.attr))
    return rows


def test_no_screen_writes_textual_reserved_state() -> None:
    offenders = _offenders()
    assert not offenders, (
        "these assignments overwrite an attribute Textual owns for its own bookkeeping:\n  "
        + "\n  ".join(f"{path}:{line} → self.{attr}  ({RESERVED[attr]})" for path, line, attr in sorted(offenders))
    )
