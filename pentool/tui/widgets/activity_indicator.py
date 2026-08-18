"""ActivityIndicator — small emoji-based "what's running right now" strip.

Sits in StatusBar, to the right of the existing proxy/project/time fields.
Each tracked background process gets one emoji glyph that blinks while
active and is dimmed/greyed while idle — Proxy 🌐, Spider 🕷️, Scanner 🔍,
Intruder 💥. Hovering over an individual glyph shows a tooltip for that
specific process (e.g. "Spider: idle" / "Spider: running") — each Static
glyph sets its own `.tooltip`, rather than one shared tooltip on the whole
strip listing every active process, so hovering Proxy doesn't show you
Spider's state.

Blinking (not just a static bright/dim swap) is deliberate: most terminals
render emoji as fixed-color glyphs from the font/emoji-font, largely
ignoring the ANSI foreground color and dim/bold text-style Textual would
otherwise apply — so a purely color-based "bright vs dim" distinction was
easy to miss. Toggling the glyph's cell *background* between a highlighted
and a plain state (like a blinking LED) is visible regardless of how the
terminal colors the emoji itself, and is combined with an on/off amplitude
swing so it also reads correctly on terminals that do respect it.

Deliberately implemented as polling rather than another EventBus
subscription: every module already tracks its own running/scanning state
in a plain attribute (ProxyServer.is_running, ScannerScreen._tabs[*].scanning,
IntruderScreen._attack_running) — wiring up start/stop events for four more
places would touch a lot of module code for a purely cosmetic feature.
Reading those attributes off a timer cannot get out of sync with reality
the way a missed event could.

Spider is the one exception: it's tracked via PentoolApp.is_spider_active()
(a shared counter on the app), not a single screen's attribute. There is no
dedicated SpiderScreen/module-tab — crawling runs only from TargetScreen's
"Crawl scope"/"Crawl selected host" convenience triggers, which build their
own SpiderAPI instance (see TargetScreen._crawl_hosts_worker).

Note on the non-Spider attribute names: none of them is `_running` — that
name collides with textual.message_pump.MessagePump._running, an internal
attribute every Widget already has (true while its own message loop is
active, i.e. essentially always once mounted — nothing to do with whether
an attack/pty is actually in progress). IntruderScreen used to shadow it
under that exact name, which made this indicator's glyphs read "active"
almost immediately at startup, before Start was ever pressed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

_CSS = (Path(__file__).parent / "activity_indicator.tcss").read_text(encoding="utf-8")

# How fast an active glyph blinks (full on/off cycles per second).
_BLINK_HZ = 2.0
# How often we re-check each module's running-state attribute — separate
# from the blink toggle rate above so a fast blink doesn't mean re-querying
# ProxyServer/ScannerScreen/etc. several times a second for no reason.
_STATE_POLL_INTERVAL = 1.0
# How often the blink phase itself is re-applied — needs to be faster than
# _STATE_POLL_INTERVAL so the glyph actually visibly flashes.
_BLINK_TICK_INTERVAL = 1.0 / (_BLINK_HZ * 2)


@dataclass
class _Tracked:
    key: str
    # U+FE0F (VARIATION SELECTOR-16, "render as emoji") appended where the
    # base codepoint would otherwise render as a narrow (1-cell) glyph in
    # most terminals — the Spider emoji (U+1F577) defaults to text/narrow
    # presentation without it, while Proxy/Scanner/Intruder's emoji are
    # already wide by default. Without the explicit VS16, Spider's glyph
    # rendered visibly narrower than the other three, throwing off the
    # even spacing across the strip.
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
        # Cached from the last _poll_state() run — the blink tick reads this
        # instead of re-invoking is_active() every ~0.25s.
        self._active_state: dict[str, bool] = {t.key: False for t in self._checkers}

    # ── checker construction ────────────────────────────────────────────────

    def _build_checkers(self, app_ref) -> list[_Tracked]:
        from pentool.tui.constants import (
            SCREEN_INTRUDER,
            SCREEN_PROXY,
            SCREEN_SCANNER,
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
            # No dedicated SpiderScreen/module-tab anymore — crawling runs
            # only from TargetScreen's "Crawl scope"/"Crawl selected host"
            # triggers (which build their own SpiderAPI instance — see
            # TargetScreen._crawl_hosts_worker). PentoolApp.is_spider_active()
            # is the single shared counter that path increments/decrements,
            # so this glyph tracks the real crawl regardless of host.
            try:
                return bool(app_ref.is_spider_active())
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
                return bool(getattr(screen, "_attack_running", False))
            except Exception:
                return None

        return [
            _Tracked("proxy",    "🌐", "Proxy",    _proxy_active),
            _Tracked("spider",   "🕷️", "Spider",   _spider_active),
            _Tracked("scanner",  "🔍", "Scanner",  _scanner_active),
            _Tracked("intruder", "💥", "Intruder", _intruder_active),
        ]

    # ── compose / refresh ────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        for i, t in enumerate(self._checkers):
            if i > 0:
                # Static, non-blinking separator between glyphs — distinct
                # from the blinking active glyphs so it never draws the eye,
                # and gives each glyph's cell a fixed, equal-width neighbor
                # instead of relying on margin alone for spacing.
                yield Static("┊", classes="activity-sep")
            yield Static(t.emoji, id=f"activity-{t.key}", classes="activity-glyph idle")

    def on_mount(self) -> None:
        self._poll_state()
        self.set_interval(_STATE_POLL_INTERVAL, self._poll_state)
        self.set_interval(_BLINK_TICK_INTERVAL, self._apply_blink)

    def _poll_state(self) -> None:
        """Re-read each module's running-state attribute (cheap, ~1/s) and
        set each glyph's own tooltip — individually, not one shared tooltip
        for the whole strip, so hovering one glyph doesn't show the others'
        state."""
        for t in self._checkers:
            try:
                active = bool(t.is_active())
            except Exception:
                active = False
            self._active_state[t.key] = active
            try:
                widget = self.query_one(f"#activity-{t.key}", Static)
            except Exception:
                continue
            widget.tooltip = f"{t.label}: {'running' if active else 'idle'}"

    def _apply_blink(self) -> None:
        """Toggle blink phase and (re)apply CSS classes (~%.2gHz tick)."""
        # int(now * _BLINK_HZ) alternates 0/1 every half-cycle — same pattern
        # used by the Dashboard's finding-blink (see live_dashboard.py).
        blink_on = int(time.monotonic() * _BLINK_HZ * 2) % 2 == 0
        for t in self._checkers:
            try:
                widget = self.query_one(f"#activity-{t.key}", Static)
            except Exception:
                continue
            active = self._active_state.get(t.key, False)
            widget.set_class(not active, "idle")
            widget.set_class(active and blink_on, "active-on")
            widget.set_class(active and not blink_on, "active-off")
