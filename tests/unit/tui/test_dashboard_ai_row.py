"""Dashboard AI/MCP status: AI shown inline under MCP, no separate AI block.

User request: remove the standalone 'AI STATUS' panel; show an 'AI
enabled/disabled' row directly under MCP inside the STATUS block.
"""

from __future__ import annotations

import types
from unittest.mock import patch

import pytest
from textual.app import App
from textual.widgets import Static

from pentool.tui.screens.dashboard.screen import DashboardScreen


class _Host(App[None]):
    def __init__(self):
        super().__init__()
        self._cfg = types.SimpleNamespace(ai_enabled=True, notifications_sound_enabled=False)

    def compose(self):
        self.mount(DashboardScreen())
        yield from []


async def _ids_with(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        ids = {n.id for n in app.query("*") if n.id}
        texts = {}
        for n in app.query("*"):
            if n.id and n.id.startswith("led-"):
                texts[n.id] = getattr(n, "render", lambda: "")() or ""
                try:
                    texts[n.id] = n._content or ""
                except Exception:
                    pass
        return ids, texts


def test_status_block_has_ai_row_and_no_ai_panel():
    import asyncio
    app = _Host()
    # heavy dashboard startup hooks are background/no-op-safe here
    with patch.object(DashboardScreen, "_load_stats_bg", lambda self: None), \
         patch.object(DashboardScreen, "_populate_projects", lambda self, *a, **k: None):
        ids, texts = asyncio.run(_ids_with(app))
    assert "led-ai-bar" in ids, "expected AI row under MCP in STATUS block"
    assert "led-mcp-bar" in ids
    assert "ai-status-panel" not in ids, "standalone AI STATUS block should be gone"
