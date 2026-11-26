"""Starting, stopping and supervising Intruder attacks — one responsibility, one file.

Extracted from `IntruderScreen` (docs/audit/2026-11-21-tui-report.md, step 5.6): the attack lifecycle
was ~200 lines in the middle of a 2 900-line screen, mixed with template editing, payload
lists and table rendering. The screen keeps the DOM it must draw; the lifecycle lives here.

Three invariants this module exists to protect (each of them broke once):

1. **The worker group** is ``ATTACK_WORKER_PREFIX + tab_id``. Closing a tab cancels the
   group, and ``on_worker_state_changed`` parses the name back into a tab id — producer and
   consumer share the constant, so they cannot drift apart.
2. **Results and progress are delivered through ``call_after_refresh``**: the callback
   comes from a worker and the tab's pane may already be gone.
3. **``attack.stop()`` is scheduled on the App, not on the screen**: during unmount the
   screen's own ``run_worker`` kills the task before it runs, and the attack keeps going.

The class talks to the screen through a narrow set of members; passing the screen keeps the
move mechanical. Tightening it into a full protocol is a separate change.
"""

from __future__ import annotations

from typing import Any

from pentool.core.activity import set_activity
from pentool.core.logging import get_logger

logger = get_logger(__name__)

#: Worker name and group of a tab's attack (``prefix + tab_id``).
ATTACK_WORKER_PREFIX = "intruder-attack-"


class AttackRunner:
    """Attack lifecycle of every tab of one Intruder screen."""

    def __init__(self, screen: Any) -> None:
        self._screen = screen

    # ── Worker identity ────────────────────────────────────────────────────

    @staticmethod
    def group(tab_id: str) -> str:
        return f"{ATTACK_WORKER_PREFIX}{tab_id}"

    # ── Start ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Validate the tab, build the config and launch the attack worker."""
        screen = self._screen
        tab = screen._active_tab
        if tab is None:
            return
        running = bool(tab and tab.running)
        logger.info("INTRUDER: action_start_attack called, running=%s", running)
        if running:
            return
        if tab.payload_load_in_progress:
            screen.app.notify(
                "A payload file is still being counted — wait for it to finish before starting",
                severity="warning",
                timeout=4,
            )
            return

        template = self._template_text()
        if template is None:
            return
        if not template.strip():
            screen.app.notify("Template is empty", severity="warning", timeout=3)
            return
        from pentool.api.intruder_api import count_markers

        if count_markers(template) == 0:
            screen.app.notify(
                "No §§ markers in template — use Auto §§ or Add §§ to mark positions first",
                severity="warning",
                timeout=5,
            )
            return
        logger.info("INTRUDER: action_start: attack_type=%s", tab.attack_type)

        payload_sets = self._payload_sets(tab)
        if payload_sets is None:
            return

        is_pro = self._is_pro()
        threads = self._thread_limit(is_pro)
        delay_ms = self._delay_limit(is_pro)
        turbo_mode = self._turbo_mode(is_pro)
        tab.turbo_mode = turbo_mode
        tab.thread_count = threads
        tab.delay_ms = delay_ms

        from pentool.api.intruder_api import IntruderConfig

        config = IntruderConfig(
            template=template,
            attack_type=tab.attack_type,
            payload_sets=payload_sets,
            threads=threads,
            delay_ms=delay_ms,
            follow_redirects=False,
            timeout=30,
        )

        api = screen._get_api()
        if api is None:
            screen.app.notify("No project open", severity="warning", timeout=3)
            return

        attack = api.make_attack(config, turbo_mode=turbo_mode)
        tab.attack = attack

        screen.refresh_header()
        tab.running = True
        tab.paused = False
        tab.all_results = []
        screen._clear_results()

        total_payloads = sum(len(ps) for ps in payload_sets)
        mode_label = " [⚡ Turbo]" if turbo_mode else ""
        limit_label = "" if is_pro else " [FREE: limited]"
        screen.app.notify(
            f"Attack started: {total_payloads} payload(s){mode_label}{limit_label}",
            severity="success",
            title="Intruder",
        )
        group = self.group(tab.tab_id)
        screen._live_attacks[tab.tab_id] = attack
        screen.run_worker(self.run(tab, attack), exclusive=False, name=group, group=group)

    def _template_text(self) -> str | None:
        screen = self._screen
        try:
            editor = screen._template_editor()
            widget = editor.content_widget
            from textual.widgets import TextArea

            template = widget.text if isinstance(widget, TextArea) else ""
        except Exception as exc:
            # Named explicitly: a typo in a field name must not look like "no tab".
            logger.exception("INTRUDER: cannot get template: %s", exc)
            return None
        logger.info("INTRUDER: template len=%d", len(template))
        return template

    def _payload_sets(self, tab: Any) -> list | None:
        """Processed payload sets for the attack, or ``None`` when nothing is configured."""
        screen = self._screen
        from pentool.api.intruder_api import ProcessedPayloads

        operations = screen._get_processing_ops()
        payload_sets = []
        for source in tab.payload_sources:
            if len(source) == 0:
                processed = [""]
            else:
                processed = ProcessedPayloads(source, operations, screen._apply_processing)
            payload_sets.append(processed)
        logger.info("INTRUDER: payload_sets sizes=%s", [len(ps) for ps in payload_sets])
        if not any(p.strip() for ps in payload_sets for p in ps):
            screen.app.notify("No payloads configured", severity="warning", timeout=3)
            return None
        return payload_sets

    def _is_pro(self) -> bool:
        from pentool.core.license import get_session_license

        info = get_session_license()
        return bool(info and info.is_pro())

    def _thread_limit(self, is_pro: bool) -> int:
        from textual.css.query import NoMatches
        from textual.widgets import Input

        try:
            threads = int(self._screen.query_one("#intruder-threads", Input).value or "10")
        except (NoMatches, ValueError) as exc:
            # The field is missing or not a number — the attack would silently run on a
            # different thread count than the screen shows.
            logger.debug("intruder: thread count not usable, falling back: %s", exc)
            return 10 if is_pro else 5
        return max(1, min(threads, 200)) if is_pro else max(1, min(threads, 5))

    def _delay_limit(self, is_pro: bool) -> int:
        from textual.css.query import NoMatches
        from textual.widgets import Input

        try:
            delay_ms = int(self._screen.query_one("#intruder-delay", Input).value or "0")
        except (NoMatches, ValueError) as exc:
            logger.debug("intruder: delay not usable, falling back: %s", exc)
            return 0 if is_pro else 100
        return max(0, delay_ms) if is_pro else max(100, delay_ms)

    def _turbo_mode(self, is_pro: bool) -> bool:
        from textual.css.query import NoMatches
        from textual.widgets import Checkbox

        try:
            checkbox = self._screen.query_one("#intruder-turbo", Checkbox)
        except NoMatches as exc:
            logger.debug("intruder: turbo checkbox missing: %s", exc)
            return False
        turbo = bool(checkbox.value) if is_pro else False
        if not is_pro:
            checkbox.value = False
        return turbo

    # ── Run ───────────────────────────────────────────────────────────────

    async def run(self, tab: Any, attack: Any) -> None:
        """Run one tab's isolated attack; results go into that tab, not the active one."""
        from pentool.core.error_guard import err

        screen = self._screen
        logger.info("INTRUDER: _run_attack started tab=%s type=%s", tab.tab_id, tab.attack_type)
        set_activity("intruder", True)

        def on_result(result: Any) -> None:
            screen.call_after_refresh(screen._on_result, result, tab)

        def on_progress(done: int, total: int) -> None:
            screen.call_after_refresh(self.progress, done, total, tab)

        try:
            tab.running = True
            await attack.run(on_result, on_progress)
        except Exception as exc:
            # The attack stopped unexpectedly: the user sees the notification, the log
            # keeps the traceback (BLE001 wants a logging call it can see).
            logger.exception("intruder: attack failed")
            err(exc, "Intruder attack error", screen, severity="error")
        finally:
            tab.running = False
            screen._live_attacks.pop(tab.tab_id, None)
            set_activity("intruder", bool(screen._live_attacks))
            tab.paused = False
            tab.attack = None
            logger.info("INTRUDER: _run_attack tab=%s finished, results=%d", tab.tab_id, len(tab.all_results))
            # Only the visible tab updates the header; background tabs sync on switch.
            if tab is screen._active_tab:
                screen.refresh_header()
                screen.app.notify(
                    f"Attack finished: {len(tab.all_results)} requests",
                    severity="information",
                    timeout=4,
                )

    def progress(self, done: int, total: int, tab: Any | None = None) -> None:
        """Move the tab's progress bar and "N/M" label."""
        from textual.css.query import NoMatches
        from textual.widgets import ProgressBar, Static

        screen = self._screen
        if tab is None:
            tab = screen._active_tab
        if tab is None:
            return
        try:
            bar = screen.query_one(f"#{screen._wid(tab.tab_id, screen._TabId.ATTACK_PROGRESS)}", ProgressBar)
            if done == 0:
                bar.update(total=max(1, total), progress=0)
            else:
                bar.advance(done - bar.progress)
        except NoMatches as exc:
            # The tab was closed mid-attack: the bar is gone, the attack is not.
            logger.debug("intruder progress bar: %s", exc)
        try:
            percent = f"{done / total * 100:.1f}%" if total > 0 else "0%"
            label = screen.query_one(f"#{screen._wid(tab.tab_id, screen._TabId.PROGRESS_LABEL)}", Static)
            label.update(f"{done}/{total} ({percent})")
        except NoMatches as exc:
            logger.debug("intruder progress label: %s", exc)

    # ── Pause / resume / stop ─────────────────────────────────────────────

    def toggle_pause(self) -> None:
        tab = self._screen._active_tab
        if tab is None or not tab.running or tab.attack is None:
            return
        should_pause = not tab.paused
        if should_pause:
            self._screen.run_worker(tab.attack.pause(), exit_on_error=False)
        else:
            self._screen.run_worker(tab.attack.resume(), exit_on_error=False)
        tab.paused = should_pause
        self._screen.refresh_header()
        self._screen.app.notify("Paused" if should_pause else "Resumed", timeout=2)

    def resume(self) -> None:
        """Resume goes through the screen action, so there is one way to start an attack."""
        self._screen.refresh_header()
        self._screen.action_start_attack()

    def stop(self) -> None:
        tab = self._screen._active_tab
        if tab is not None:
            self.stop_tab(tab)
        self._screen.refresh_header()
        self._screen.app.notify("Attack stopped", severity="warning")

    def stop_tab(self, tab: Any) -> None:
        """Cancel the worker first, then ask the attack to stop.

        The order matters: ``attack.stop()`` does not return at once on a long network
        loop, and a closed tab must not wait for it.
        """
        screen = self._screen
        try:
            screen.workers.cancel_group(screen, self.group(tab.tab_id))
        except Exception:
            # The worker survived: the closed tab keeps sending requests.
            logger.exception("ATTACK: cancel_group failed for %s", tab.tab_id)
        attack = getattr(tab, "attack", None)
        screen._live_attacks.pop(tab.tab_id, None)
        tab.running = False
        tab.paused = False
        if attack is None:
            return
        try:
            # On the App, not the screen: during unmount the screen's worker would be
            # killed before it ran, and the attack would stay alive.
            screen.app.run_worker(attack.stop(), exit_on_error=False)
        except Exception:
            # `tab.running` is already False yet the attack keeps running.
            logger.exception("ATTACK: attack.stop failed for %s", tab.tab_id)

    # ── Worker state ──────────────────────────────────────────────────────

    def handle_worker_state(self, event: Any) -> bool:
        """React to a finished attack worker; returns True when the event was ours."""
        from textual.worker import WorkerState

        name = getattr(event.worker, "name", "") or ""
        if not name.startswith(ATTACK_WORKER_PREFIX):
            return False
        tab = self._screen._tc_panel.get_state(name[len(ATTACK_WORKER_PREFIX) :])
        if event.state in (WorkerState.SUCCESS, WorkerState.CANCELLED, WorkerState.ERROR):
            if tab is not None and tab.running:
                tab.paused = False
                if tab is self._screen._active_tab:
                    self._screen.refresh_header()
        return True
