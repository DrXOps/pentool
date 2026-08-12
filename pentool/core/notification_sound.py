"""Lightweight, dependency-free notification sounds.

Deliberately does NOT pull in a new pip dependency (simpleaudio/playsound/
sounddevice etc.) — those add binary wheels per-platform, which has bitten
this project before (see the CodeEnigma Windows-build fork in
pentool-pro). Instead this uses each OS's own built-in sound facility:

- Windows: winsound.Beep() — stdlib, always available.
- macOS: `afplay` on one of the built-in system sound files (always present
  on a stock install).
- Linux: whichever of `paplay`/`aplay`/`play` is on PATH, falling back to
  the terminal BEL character if none are found (e.g. minimal/headless
  containers, SSH sessions without ALSA/PulseAudio).

All playback happens in a short-lived subprocess/thread so it never blocks
the Textual event loop. Any error here is swallowed — a missing sound
system must never crash the app or break notifications themselves.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading

from pentool.core.logging import get_logger

logger = get_logger(__name__)

# One "tone" per severity — Windows Beep(frequency_hz, duration_ms) pairs.
# Loosely modeled after the ICQ-style ascending/descending cues: info is a
# single short blip, success a quick double-up chirp, warning a two-tone
# alert, error/critical a longer, lower, more insistent tone.
_WIN_TONES: dict[str, list[tuple[int, int]]] = {
    "information": [(880, 80)],
    "success":     [(880, 60), (1175, 90)],
    "warning":     [(660, 90), (660, 90)],
    "error":       [(440, 160)],
    "critical":    [(440, 160), (330, 200)],
}

# macOS built-in system sounds (present on every stock macOS install).
_MAC_SOUNDS: dict[str, str] = {
    "information": "/System/Library/Sounds/Tink.aiff",
    "success":     "/System/Library/Sounds/Glass.aiff",
    "warning":     "/System/Library/Sounds/Ping.aiff",
    "error":       "/System/Library/Sounds/Basso.aiff",
    "critical":    "/System/Library/Sounds/Sosumi.aiff",
}


def play_notification_sound(severity: str = "information") -> None:
    """Best-effort, non-blocking notification sound for `severity`.

    Fully swallows any error (missing player, no audio device, unsupported
    platform) — sound is a nice-to-have, never a hard dependency of the
    notification itself.
    """
    try:
        thread = threading.Thread(
            target=_play_blocking, args=(severity,), daemon=True
        )
        thread.start()
    except Exception as exc:
        logger.debug("play_notification_sound: could not start thread: %s", exc)


def _play_blocking(severity: str) -> None:
    try:
        if sys.platform.startswith("win"):
            _play_windows(severity)
        elif sys.platform == "darwin":
            _play_macos(severity)
        else:
            _play_linux(severity)
    except Exception as exc:
        logger.debug("_play_blocking(%s): %s", severity, exc)


def _play_windows(severity: str) -> None:
    import winsound  # stdlib, Windows-only
    for freq, dur in _WIN_TONES.get(severity, _WIN_TONES["information"]):
        try:
            winsound.Beep(freq, dur)
        except Exception:
            # Some environments (e.g. no audio device) raise RuntimeError —
            # fall back to the terminal bell for the rest of this call.
            _terminal_bell()
            return


def _play_macos(severity: str) -> None:
    sound_file = _MAC_SOUNDS.get(severity, _MAC_SOUNDS["information"])
    afplay = shutil.which("afplay")
    if not afplay:
        _terminal_bell()
        return
    subprocess.run(
        [afplay, sound_file],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )


def _play_linux(severity: str) -> None:
    # No universal built-in system sound file across distros — use the
    # terminal bell (\a), which every terminal emulator supports and which
    # works over SSH with no audio subsystem required. This keeps the
    # feature dependency-free rather than shipping our own WAV assets.
    _terminal_bell(severity)


def _terminal_bell(severity: str = "information") -> None:
    try:
        # Multiple bells for higher-severity events, matching the
        # short/insistent pattern used for Windows tones above.
        count = {"information": 1, "success": 1, "warning": 2, "error": 2, "critical": 3}.get(severity, 1)
        sys.stdout.write("\a" * count)
        sys.stdout.flush()
    except Exception:
        pass
