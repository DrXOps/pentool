"""ActivityIndicator — emoji strip showing what is running, fed by ActivityState.

Sits in the StatusBar, to the right of the proxy/project/time fields. Each tracked
process has a glyph that blinks while active and is dimmed while idle; each glyph carries
its own tooltip ("Spider: idle" / "Spider: running").

**Why events now (T-030).** The strip used to re-read every module's attribute once a
second, forever. That cost a repaint per second, polled screens that were not even
mounted, and could not distinguish "stopped" from "could not read the state". Producers
now report transitions through `pentool.core.activity.get_activity_state()`, and this
widget repaints on the event only.

Polling did not disappear: it slowed down to `_STATE_POLL_INTERVAL` (5 s) and became a
fallback that

* discovers state for sources with no event (AI-backend availability, config toggles), and
* repairs a module that forgot to report (a `set()` that never ran still shows up within
  a few seconds instead of showing "idle" for a running scan).

Blinking stays: most terminals render emoji as fixed-colour glyphs, so a static bright/dim
swap is easy to miss. Toggling the cell *background* reads as a blinking LED regardless,
and the on/off amplitude swing covers terminals that do honour colours.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Static

from pentool.core.activity import ActivityState, get_activity_state
from pentool.core.event_bus import get_event_bus
from pentool.core.events import ActivityChanged
from pentool.core.logging import get_logger

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "activity_indicator.tcss").read_text(encoding="utf-8")

# How fast an active glyph blinks (full on/off cycles per second).
_BLINK_HZ = 2.0
# Fallback polling: state changes arrive by event, this only fills the gaps (AI backend,
# config toggles) and repairs a producer that never reported.
_STATE_POLL_INTERVAL = 5.0
# How often the blink phase itself is re-applied — must be faster than the poll so the
# glyph visibly flashes.
_BLINK_TICK_INTERVAL = 1.0 / (_BLINK_HZ * 2)


@dataclass
class _Tracked:
    key: str
    # U+FE0F (VARIATION SELECTOR-16, "render as emoji") where the base codepoint would
    # otherwise render narrow: the Spider emoji defaults to text presentation, which made
    # its glyph visibly narrower than the others and broke the strip's spacing.
    emoji: str
    label: str
    # () -> bool | None — None means "could not determine" (screen not mounted, PRO
    # unavailable), treated as "no change" by the fallback poll.
    is_active: Callable[[], bool | None]


class ActivityIndicator(Widget):
    """Emoji strip showing which background processes are currently active."""

    DEFAULT_CSS = _CSS

    def __init__(self, app_ref, **kwargs) -> None:
        """
        Args:
            app_ref: the PentoolApp instance (passed explicitly rather than relying on
                `self.app`, which only exists once mounted — the checker callables are
                built at construction time).
        """
        super().__init__(**kwargs)
        # Shared look of a panel header: one line, dark backing, side padding (F-038).
        self.add_class("panel-title")
        self._checkers: list[_Tracked] = self._build_checkers(app_ref)
        self._state: ActivityState = get_activity_state()
        #: Cached state from the registry; the blink tick reads this instead of querying.
        self._active_state: dict[str, bool] = self._state.snapshot()
        #: Last AI-config value seen by `_poll_state`.
        self._ai_cfg_on: bool = False
        #: True once the idle shortcut cleared the blink classes after activity stopped.
        self._blink_cleared: bool = True
        #: EventBus handler bound in on_mount, removed in on_unmount.
        self._bus_subscribed: bool = False

    # ── checker construction ────────────────────────────────────────────────

    def _build_checkers(self, app_ref) -> list[_Tracked]:
        """Fallback readers: consulted by the slow poll, not on every repaint."""

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
                return bool(app_ref.is_spider_active())
            except Exception:
                return None

        def _scanner_active() -> bool | None:
            try:
                from pentool.tui.screens import SCANNER_SCREEN_AVAILABLE

                if not SCANNER_SCREEN_AVAILABLE:
                    return False
                from pentool.tui.screens.scanner.screen import ScannerScreen

                screen = app_ref.require_module_screen("scanner", ScannerScreen)
                tabs = getattr(screen, "_tabs", None)
                if not tabs:
                    return False
                return any(getattr(t, "scanning", False) for t in tabs)
            except Exception:
                return None

        def _intruder_active() -> bool | None:
            try:
                from pentool.tui.screens.intruder.screen import IntruderScreen

                screen = app_ref.require_module_screen("intruder", IntruderScreen)
                return bool(getattr(screen, "_attack_running", False))
            except Exception:
                return None

        def _ai_active() -> bool | None:
            try:
                from pentool.services.ai.provider import is_mcp_busy

                return is_mcp_busy()
            except Exception:
                return None

        def _recon_active() -> bool | None:
            try:
                from pentool.tui.screens.recon.screen import ReconScreen

                screen = app_ref.module_screen("recon", ReconScreen)
                if screen is None:
                    return None
                # `_runner` is None while idle and a DiscoveryRunner during a run.
                return screen._runner is not None
            except (ImportError, AttributeError):
                return None

        return [
            # Only the two magnifiers were an issue: 🔍 and 🔎 are hard to tell apart and
            # the microscope 🔬 was missing from the font, so Scanner is 🔍 and Recon a
            # compass 🧭 (exploring terrain).
            _Tracked("proxy", "🌐", "Proxy", _proxy_active),
            _Tracked("spider", "🕷️", "Spider", _spider_active),
            _Tracked("scanner", "🔍", "Scanner", _scanner_active),
            _Tracked("intruder", "💥", "Intruder", _intruder_active),
            _Tracked("recon", "🧭", "Recon", _recon_active),
            _Tracked("ai", "🤖", "AI MCP", _ai_active),
        ]

    # ── compose / lifecycle ─────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        for i, t in enumerate(self._checkers):
            if i > 0:
                # Static, non-blinking separator between glyphs — distinct from the
                # blinking glyphs so it never draws the eye.
                yield Static("┊", classes="activity-sep")
            yield Static(t.emoji, id=f"activity-{t.key}", classes="activity-glyph idle")

    def on_mount(self) -> None:
        get_event_bus().subscribe(ActivityChanged, self._on_activity_changed)
        self._bus_subscribed = True
        self._active_state = self._state.snapshot()
        self._poll_state()
        if os.environ.get("PENTOOL_SNAPSHOT") == "1":
            # Snapshots must not depend on the blink phase: `_apply_blink` derives it from
            # time.monotonic(), so two runs produced different baselines.
            self._apply_blink(blink_on=True)
            return
        self.set_interval(_STATE_POLL_INTERVAL, self._poll_state)
        self.set_interval(_BLINK_TICK_INTERVAL, self._apply_blink)

    def on_unmount(self) -> None:
        if self._bus_subscribed:
            get_event_bus().unsubscribe(ActivityChanged, self._on_activity_changed)
            self._bus_subscribed = False

    # ── event path ──────────────────────────────────────────────────────────

    def _on_activity_changed(self, event: ActivityChanged) -> None:
        """A producer reported a transition: repaint immediately."""
        module, active = event.module, event.active
        self._active_state[module] = active
        if self.app is not None and threading.get_ident() != getattr(self.app, "_thread_id", threading.get_ident()):
            # A producer running on its own thread (the in-memory proxy loop) must not
            # touch widgets: hop to the app's thread.
            self.app.call_from_thread(self._apply_state)
            return
        self._apply_state()

    # ── repaint ─────────────────────────────────────────────────────────────

    def _apply_state(self) -> None:
        """Push the cached state into glyph classes and tooltips."""
        for t in self._checkers:
            active = bool(self._active_state.get(t.key, False))
            try:
                widget = self.query_one(f"#activity-{t.key}", Static)
            except NoMatches as exc:
                # Glyph absent from the tree — usual during a partial build.
                logger.debug("activity: glyph %s not found: %s", t.key, exc)
                continue
            widget.tooltip = f"{t.label}: {'running' if active else 'idle'}"
            if t.key == "ai":
                widget.display = True
                widget.set_class(not self._ai_cfg_on, "ai-disabled")
        if not any(self._active_state.values()):
            # Nothing runs: clear the blink classes once and stop touching the layout.
            self._blink_cleared = True
            for t in self._checkers:
                try:
                    widget = self.query_one(f"#activity-{t.key}", Static)
                except NoMatches:
                    continue
                widget.set_class(False, "active-on")
                widget.set_class(False, "active-off")
                widget.set_class(True, "idle")
            return
        self._blink_cleared = False
        self._apply_blink()

    # ── fallback poll ───────────────────────────────────────────────────────

    def _poll_state(self) -> None:
        """Slow sweep: feed AI/config state and repair a module that never reported."""
        ai_cfg_on = False
        try:
            from pentool.core.config import get_config

            ai_cfg_on = bool(getattr(get_config(), "ai_enabled", False))
        except Exception as exc:
            # Treat AI as disabled — the glyph gets dimmed. Runs every 5 s; log on
            # failure only, otherwise the journal fills with repeats.
            logger.debug("activity: ai_enabled not read, assuming off: %s", exc)

        ai_cfg_changed = ai_cfg_on != self._ai_cfg_on
        self._ai_cfg_on = ai_cfg_on

        # AI has no event source: `is_mcp_busy()` is the only answer.
        for tracked in self._checkers:
            if tracked.key != "ai":
                continue
            try:
                value = tracked.is_active()
            except (AttributeError, ImportError, KeyError, TypeError, RuntimeError) as exc:
                logger.debug("activity: state of %s not read: %s", tracked.key, exc)
                continue
            if value is not None:
                self._state.set(tracked.key, bool(value))

        # Repair pass for the modules that *do* publish: a missed `set()` (an old code
        # path, an exception between start and the report) would otherwise leave the
        # glyph dark while the module runs. `None` means "cannot tell" — leave it alone.
        for tracked in self._checkers:
            if tracked.key in ("ai",):
                continue
            try:
                value = tracked.is_active()
            except (AttributeError, ImportError, KeyError, TypeError, RuntimeError) as exc:
                logger.debug("activity: fallback state of %s not read: %s", tracked.key, exc)
                continue
            if value is None:
                continue
            if bool(value) != self._state.is_active(tracked.key):
                logger.debug(
                    "activity: %s reported %s but registry says %s — repairing",
                    tracked.key,
                    bool(value),
                    self._state.is_active(tracked.key),
                )
                self._state.set(tracked.key, bool(value))

        if ai_cfg_changed:
            self._apply_state()

    # ── blink ───────────────────────────────────────────────────────────────

    def _apply_blink(self, blink_on: bool | None = None) -> None:
        """Toggle the blink phase and (re)apply the CSS classes (~2 Hz tick).

        ``blink_on`` is passed explicitly in snapshot mode: a phase derived from the
        clock makes the baseline nondeterministic.

        Idle shortcut: every class change makes Textual recompute the layout, and this
        tick runs ~4x/s for the whole session. When nothing is active there is nothing to
        blink, so the tick returns at once.
        """
        if blink_on is None and not any(self._active_state.values()):
            if not self._blink_cleared:
                self._blink_cleared = True
                for t in self._checkers:
                    try:
                        widget = self.query_one(f"#activity-{t.key}", Static)
                    except NoMatches as exc:
                        logger.debug("activity: idle glyph %s not found: %s", t.key, exc)
                        continue
                    widget.set_class(False, "active-on")
                    widget.set_class(False, "active-off")
                    widget.set_class(True, "idle")
            return
        self._blink_cleared = False
        if blink_on is None:
            # int(now * _BLINK_HZ) alternates 0/1 every half-cycle.
            blink_on = int(time.monotonic() * _BLINK_HZ * 2) % 2 == 0
        for t in self._checkers:
            try:
                widget = self.query_one(f"#activity-{t.key}", Static)
            except NoMatches as exc:
                logger.debug("activity: blink glyph %s not found: %s", t.key, exc)
                continue
            active = self._active_state.get(t.key, False)
            widget.set_class(not active, "idle")
            widget.set_class(active and blink_on, "active-on")
            widget.set_class(active and not blink_on, "active-off")
