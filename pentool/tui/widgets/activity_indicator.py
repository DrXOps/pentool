"""ActivityIndicator — small emoji-based "what's running right now" strip.

Sits in StatusBar, to the right of the existing proxy/project/time fields.
Each tracked background process gets one emoji glyph that is bright (its
normal color) while active and dim/grey while idle — Proxy 🌐, Spider 🕷,
Scanner 🔍, Intruder 💥. Hovering shows a tooltip listing exactly which
processes are currently running (or "All idle").

Deliberately implemented as polling rather than another EventBus
subscription: every module already tracks its own running/scanning state
in a plain attribute (ProxyServer.is_running, SpiderScreen._running,
ScannerScreen._tabs[*].scanning, IntruderScreen._running) — wiring up
start/stop events for four more places would touch a lot of module code
for a purely cosmetic feature. Reading those attributes off a 1s timer
(the same cadence StatusBar already uses for the clock) is simpler and
cannot get out of sync with reality the way a missed event could.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

_CSS = (Path(__file__).parent / "activity_indicator.tcss").read_text(encoding="utf-8")


@dataclass
class _Tracked:
    key: str
    emoji: str
    label: str
    # () -> bool | None — None means "could not determine" (module screen
    # not mounted / PRO scanner unavailable / etc.), treated as idle.
    is_active: Callable[[], bool | None]


class ActivityIndicator(Widget):
    """Emoji strip showing which background processes are currently active."""

    DEFAULT_CSS = _CSS

    def __init__(self, app_ref, **kwargs) -> None:
        """
        Args:
            app_ref: the PentoolApp instance (passed explicitly rather than
                relying on self.app, which is only available once mounted —
                the checker callables below are built at construction time).
        """
        super().__init__(**kwargs)
        self._checkers: list[_Tracked] = self._build_checkers(app_ref)

    # ── checker construction ────────────────────────────────────────────────

    def _build_checkers(self, app_ref) -> list[_Tracked]:
        from pentool.tui.constants import (
            SCREEN_INTRUDER,
            SCREEN_PROXY,
            SCREEN_SCANNER,
            SCREEN_SPIDER,
        )

        def _proxy_active() -> bool | None:
            try:
                proxy = getattr(app_ref, "_proxy", None)
                if proxy is None:
                    return False
                return bool(proxy.is_running)
            except Exception:
                return None

        def _spider_active() -> bool | None:
            try:
                from pentool.tui.screens.spider.screen import SpiderScreen
                screen = app_ref.query_one(SCREEN_SPIDER, SpiderScreen)
                return bool(getattr(screen, "_running", False))
            except Exception:
                return None

        def _scanner_active() -> bool | None:
            try:
                from pentool.tui.screens import SCANNER_SCREEN_AVAILABLE
                if not SCANNER_SCREEN_AVAILABLE:
                    return False
                from pentool.tui.screens.scanner.screen import ScannerScreen
                screen = app_ref.query_one(SCREEN_SCANNER, ScannerScreen)
                tabs = getattr(screen, "_tabs", None)
                if not tabs:
                    return False
                return any(getattr(t, "scanning", False) for t in tabs)
            except Exception:
                return None

        def _intruder_active() -> bool | None:
            try:
                from pentool.tui.screens.intruder.screen import IntruderScreen
                screen = app_ref.query_one(SCREEN_INTRUDER, IntruderScreen)
                return bool(getattr(screen, "_running", False))
            except Exception:
                return None

        return [
            _Tracked("proxy",    "🌐", "Proxy",    _proxy_active),
            _Tracked("spider",   "🕷", "Spider",   _spider_active),
            _Tracked("scanner",  "🔍", "Scanner",  _scanner_active),
            _Tracked("intruder", "💥", "Intruder", _intruder_active),
        ]

    # ── compose / refresh ────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        for t in self._checkers:
            yield Static(t.emoji, id=f"activity-{t.key}", classes="activity-glyph idle")

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(1.0, self._refresh)

    def _refresh(self) -> None:
        active_labels: list[str] = []
        for t in self._checkers:
            try:
                active = bool(t.is_active())
            except Exception:
                active = False
            try:
                widget = self.query_one(f"#activity-{t.key}", Static)
            except Exception:
                continue
            if active:
                widget.remove_class("idle")
                widget.add_class("active")
                active_labels.append(t.label)
            else:
                widget.remove_class("active")
                widget.add_class("idle")

        tooltip = ", ".join(active_labels) if active_labels else "All idle"
        self.tooltip = tooltip
