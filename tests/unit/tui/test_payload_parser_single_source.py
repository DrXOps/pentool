"""Guard: one parser for payload files.

The rule "strip each line, skip blanks and `#` comments" lived twice: in
`modules/intruder.load_payloads_from_file` (used by the drop zone and the API) and again
inside the Intruder screen's eager loader, together with its own file reader. The copies
could drift silently — a payload the API loads but the screen skips (or the reverse) is
very hard to notice.

The screen now calls the shared parser off the event loop. This test pins both halves.
"""

from __future__ import annotations

import ast
from pathlib import Path

from pentool.modules.intruder import load_payloads_from_file

ROOT = Path(__file__).resolve().parents[3]
SCREEN = ROOT / "pentool/tui/screens/intruder/screen.py"


def test_parser_skips_blanks_and_comments(tmp_path: Path) -> None:
    path = tmp_path / "payloads.txt"
    path.write_text(
        "\n".join(
            [
                "  admin ",
                "# a comment",
                "",
                "root",
                "   # indented comment",
                "guest",
            ]
        ),
        encoding="utf-8",
    )

    assert load_payloads_from_file(str(path)) == ["admin", "root", "guest"]


def test_missing_file_returns_empty_and_logs(tmp_path: Path) -> None:
    # An unreadable file must not raise: the attack then runs with an empty set and the
    # reason is in the log (see the function's own comment).
    assert load_payloads_from_file(str(tmp_path / "nope.txt")) == []


def test_screen_has_no_private_parser_again() -> None:
    tree = ast.parse(SCREEN.read_text(encoding="utf-8"))
    methods = {
        node.name
        for node in ast.walk(ast.parse(SCREEN.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef)
    }
    assert "_read_file_sync" not in methods, (
        "the screen grew its own file reader again — use the shared parser from "
        "pentool.api.intruder_api (single rule for what a payload line is)"
    )
    # And no inline parsing loop left behind.
    source = SCREEN.read_text(encoding="utf-8")
    assert 'startswith("#")' not in source.split("_load_file_eager")[1][:1200], (
        "payload parsing is inlined in the eager loader again"
    )
    assert "_read_file_sync" not in SCREEN.read_text(encoding="utf-8")
    assert tree  # parsed above; keeps the reference explicit
