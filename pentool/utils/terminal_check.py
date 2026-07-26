"""Terminal type detection at startup."""

from __future__ import annotations

import os

MODERN_TERMINALS = {"kitty", "alacritty", "wezterm", "iterm.app", "ghostty", "tmux"}
LEGACY_TERMINALS = {"xterm", "rxvt", "linux", "vt100", "dumb"}


def check_terminal() -> tuple[str, bool]:
    term = (
        os.environ.get("TERM_PROGRAM")
        or os.environ.get("TERMINAL_EMULATOR")
        or os.environ.get("TERM", "unknown")
    )
    term_lower = term.lower()
    is_modern = any(t in term_lower for t in MODERN_TERMINALS)
    return term, is_modern


def get_terminal_warning() -> str | None:
    """Returns None if the terminal is modern, otherwise returns a warning message."""
    term, is_modern = check_terminal()
    if not is_modern:
        return (
            f"Terminal '{term}' may have limited support. "
            "For best experience use: kitty, alacritty, WezTerm, or iTerm2. "
            "All features remain available."
        )
    return None
