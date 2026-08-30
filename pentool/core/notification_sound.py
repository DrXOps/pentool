"""Lightweight, dependency-free notification sounds.

Deliberately does NOT pull in a new pip dependency (simpleaudio/playsound/
sounddevice etc.) — those add binary wheels per-platform, which has bitten
this project before (see the CodeEnigma Windows-build fork in
pentool-pro).

2026-08-30 (stability): the Linux/macOS players relied on `subprocess.run`
(a fork of `paplay`/`afplay` fed the whole sine-tone WAV on stdin). Under
rapid-fire notifications (e.g. clicking a filter-bar Apply repeatedly) that
spawned many daemon threads stuck in `_fork_exec`, which both stalled the UI
and produced the "run() returned cleanly (not via action_quit)" abnormal
exits we kept seeing. Per a deliberate product decision, Linux/macOS now
fall back to the terminal BEL only (no subprocess, no fork) — sound is a
nice-to-have and must never threaten process stability. Windows keeps
`winsound.Beep()`, which is stdlib and does not fork.

All playback is still non-blocking and best-effort; any error here is
swallowed — a missing sound system must never crash the app or break
notifications themselves.
"""

from __future__ import annotations

import sys
import threading

from pentool.core.logging import get_logger

logger = get_logger(__name__)

# Throttle: a notification sound must never stack one thread per event.
# When rapid-fire notifications arrive (e.g. clicking a filter-bar Apply
# repeatedly), we drop the sound for events while a playback is already in
# flight instead of spawning an unbounded pile of daemon threads. This is
# what froze the UI before the subprocess players were removed.
_BUSY = threading.Lock()


def play_notification_sound(severity: str = "information") -> None:
    """Best-effort, non-blocking notification sound for `severity`.

    Fully swallows any error — sound is a nice-to-have, never a hard
    dependency of the notification itself. Runs the (cheap, non-forking)
    playback on a daemon thread so it never blocks the Textual event loop.
    Skips playback entirely if a previous sound is still in flight.
    """
    # Atomically claim the single-playback slot; if another sound is still
    # playing, drop this one instead of stacking another thread.
    if not _BUSY.acquire(blocking=False):
        return
    try:
        thread = threading.Thread(
            target=_play_blocking, args=(severity,), daemon=True
        )
        thread.start()
    except Exception as exc:
        _BUSY.release()
        logger.debug("play_notification_sound: could not start thread: %s", exc)


def _play_blocking(severity: str) -> None:
    try:
        # One bell per severity tier, escalating on urgency — also used on
        # Windows as a fallback when win sound is unavailable.
        count = {"information": 1, "success": 1, "warning": 2, "error": 2, "critical": 3}.get(severity, 1)
        if sys.platform.startswith("win"):
            _play_windows(severity)
        else:
            _terminal_bell(count)
    except Exception as exc:
        logger.debug("_play_blocking(%s): %s", severity, exc)
    finally:
        # Free the single-playback slot regardless of outcome.
        try:
            _BUSY.release()
        except Exception:
            pass


def _play_windows(severity: str) -> None:
    try:
        import winsound  # stdlib, Windows-only

        # Short single beep per severity tier (frequency varies a little);
        # winsound is in-process (no subprocess), so it is safe to keep.
        freq = {"information": 880, "success": 1175, "warning": 660, "error": 440, "critical": 330}.get(severity, 880)
        winsound.Beep(freq, 80)  # type: ignore[attr-defined]  # platform-specific win module
        return
    except Exception:
        # No audio device / unsupported — fall back to the terminal bell.
        _terminal_bell(1)


def _terminal_bell(count: int) -> None:
    try:
        sys.stdout.write("\a" * count)
        sys.stdout.flush()
    except Exception:
        pass
