"""Guards for the ContentPanel role table (T-028).

Two things must stay true:

1. Every role name resolves to a button set, and read-only roles never offer
   destructive actions (`clear`) or editing (`paste`) — the audit found exactly this
   kind of drift scattered across six hand-written lists.
2. The repository's own call sites pass a role, not a `buttons=[...]` list, so the
   table stays the single source of truth. The escape hatch exists for plugins only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pentool.tui.widgets.content_panel import ContentPanel

ROOT = Path(__file__).resolve().parents[3]

READ_ONLY_ROLES = ("text-readonly", "diff")


def test_every_role_has_a_button_set() -> None:
    for role, buttons in ContentPanel.ROLES.items():
        assert buttons, f"role {role!r} maps to an empty set"
        assert all(isinstance(button, str) for button in buttons)


def test_read_only_roles_cannot_clear_or_paste() -> None:
    for role in READ_ONLY_ROLES:
        buttons = set(ContentPanel.ROLES[role])
        assert "clear" not in buttons, f"read-only role {role!r} offers clear"
        assert "paste" not in buttons, f"read-only role {role!r} offers paste"


def test_unknown_role_is_rejected_loudly() -> None:
    with pytest.raises(ValueError, match="unknown ContentPanel role"):
        ContentPanel("x", role="no-such-role")


def test_role_resolves_to_the_table() -> None:
    panel = ContentPanel("Log", widget_type="richlog", role="log")
    assert panel._buttons == list(ContentPanel.ROLES["log"])


def test_repository_call_sites_use_roles() -> None:
    """No screen may hand-pick its own button list any more."""
    offenders: list[str] = []
    for base in (ROOT / "pentool" / "tui", ROOT / "pro" / "pentool" / "tui"):
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            # Arguments inside ContentPanel/HttpView/RequestEditor/ResponseViewer calls.
            for match in re.finditer(r"buttons=\[", text):
                line_no = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(ROOT)}:{line_no}")
    assert not offenders, "pass role=... instead of buttons=[...]:\n  " + "\n  ".join(offenders)
