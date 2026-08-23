"""Lightweight, dependency-free notification sounds.

Deliberately does NOT pull in a new pip dependency (simpleaudio/playsound/
sounddevice etc.) — those add binary wheels per-platform, which has bitten
this project before (see the CodeEnigma Windows-build fork in
pentool-pro). Instead this uses each OS's own built-in sound facility:

- Windows: winsound.Beep() — stdlib, always available.
- macOS: `afplay` on one of the built-in system sound files (always present
  on a stock install).
- Linux: generates a short sine-tone WAV *in memory* (stdlib `wave`/`struct`,
  no assets to ship) and plays it through whichever of
  `paplay`/`aplay`/`ffplay` is on PATH. Falls back to the terminal BEL
  character only when no player is found (e.g. minimal/headless containers,
  SSH sessions without ALSA/PulseAudio).

All playback happens in a short-lived subprocess/thread so it never blocks
the Textual event loop. Any error here is swallowed — a missing sound
system must never crash the app or break notifications themselves.
"""

from __future__ import annotations

import io
import math
import shutil
import struct
import subprocess
import sys
import threading
import wave

from pentool.core.logging import get_logger

logger = get_logger(__name__)

# One "tone" per severity — (frequency_hz, duration_ms) pairs.
# Loosely modeled after the ICQ-style ascending/descending cues: info is a
# single short blip, success a quick double-up chirp, warning a two-tone
# alert, error/critical a longer, lower, more insistent tone. Shared by the
# Windows Beep() path and the Linux sine-tone generator.
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

_SAMPLE_RATE = 44100
_AMPLITUDE = 12000  # headroom so summed tones don't clip


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


def _render_sine_wav(tones: list[tuple[int, int]]) -> bytes:
    """Render the tone sequence to in-memory PCM WAV bytes (no temp file)."""
    # Concatenate each tone's samples with a tiny gap so they read as
    # distinct blips rather than one smear (ICQ-style).
    pcm = bytearray()
    gap = int(0.02 * _SAMPLE_RATE)
    for freq, dur_ms in tones:
        n = int(_SAMPLE_RATE * dur_ms / 1000)
        for i in range(n):
            sample = _AMPLITUDE * math.sin(2 * math.pi * freq * i / _SAMPLE_RATE)
            pcm += struct.pack("<h", int(sample))
        pcm += b"\x00\x00" * gap

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(bytes(pcm))
    return buf.getvalue()


def _play_linux(severity: str) -> None:
    """Play a real sine-tone notification instead of the terminal BEL.

    Preferred players in order; each reads a WAV stream from stdin so no
    temp file is needed and nothing is shiped on disk. Falls back to the
    BEL character only when no player exists.
    """
    player = shutil.which("paplay") or shutil.which("aplay") or shutil.which("ffplay")
    if not player:
        _terminal_bell(severity)
        return

    tones = _WIN_TONES.get(severity, _WIN_TONES["information"])
    wav = _render_sine_wav(tones)
    args = [player]
    if player.endswith("ffplay"):
        # ffplay wants its input flagged explicitly and nudged to quit alone.
        args += ["-nodisp", "-autoexit", "-i", "-"]
    else:
        args += ["-"]
    try:
        subprocess.run(
            args,
            input=wav,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        logger.debug("_play_linux(%s): player failed: %s", severity, exc)
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
