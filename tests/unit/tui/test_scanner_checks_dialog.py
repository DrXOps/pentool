"""ChecksDialog AI-controls visibility: hidden when global AI is disabled.

User report: the '🤖 Select AI' button and '🤖 AI bypass' checkbox were shown
even when AI was OFF in Settings. They are AI-only — hide them when
Config.ai_enabled is False.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
import pytest_asyncio
from textual.app import App
from textual.widgets import Static

pro_available = False
try:
    sys.path.insert(0, "pro")
    from pentool.tui.dialogs.checks_dialog import ChecksDialog
    pro_available = True
except Exception:
    pro_available = False


pytestmark = pytest.mark.skipif(not pro_available, reason="pro/ submodule not available")


def _make_dialog(ai_enabled):
    import types
    # Force get_config() -> cfg with ai_enabled for the compose-time read.
    patcher = patch(
        "pentool.core.config.get_config",
        return_value=types.SimpleNamespace(ai_enabled=ai_enabled),
    )
    patcher.start()
    dlg = ChecksDialog(
        get_values=lambda: {},
        set_value=lambda k, v: None,
        target_url="http://x/",
        on_ai_select=lambda *a: None,
    )
    return dlg, patcher


class _Host(App[None]):
    def __init__(self, dialog):
        super().__init__()
        self._dialog = dialog

    def compose(self):
        yield Static("host")
        yield self._dialog


async def _mounted_ids(ai_enabled):
    dlg, patcher = _make_dialog(ai_enabled)
    app = _Host(dlg)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            ids = set()
            for node in app.query("*"):
                nid = node.id
                if nid:
                    ids.add(nid)
            return ids
    finally:
        patcher.stop()


@pytest.mark.asyncio
async def test_ai_controls_hidden_when_ai_disabled():
    ids = await _mounted_ids(ai_enabled=False)
    assert "btn-ai-select" not in ids
    assert "chk-ai-bypass" not in ids
    assert "btn-select-all" in ids
    assert "btn-close" in ids


@pytest.mark.asyncio
async def test_ai_controls_shown_when_ai_enabled():
    ids = await _mounted_ids(ai_enabled=True)
    assert "btn-ai-select" in ids
    assert "chk-ai-bypass" in ids
