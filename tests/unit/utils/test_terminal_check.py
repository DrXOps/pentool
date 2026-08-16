"""Unit tests: utils/terminal_check.py — terminal type detection."""
from __future__ import annotations

import os
from unittest.mock import patch

from pentool.utils.terminal_check import check_terminal, get_terminal_warning, MODERN_TERMINALS


def test_modern_kitty():
    with patch.dict(os.environ, {"TERM_PROGRAM": "kitty"}, clear=True):
        term, is_modern = check_terminal()
    assert is_modern is True
    assert term == "kitty"


def test_modern_alacritty_case_insensitive():
    with patch.dict(os.environ, {"TERM_PROGRAM": "Alacritty"}, clear=True):
        term, is_modern = check_terminal()
    assert is_modern is True


def test_modern_wezterm_via_emulator():
    with patch.dict(os.environ, {"TERMINAL_EMULATOR": "WezTerm"}, clear=True):
        term, is_modern = check_terminal()
    assert is_modern is True


def test_legacy_xterm():
    with patch.dict(os.environ, {"TERM": "xterm"}, clear=True):
        term, is_modern = check_terminal()
    assert is_modern is False


def test_legacy_unknown_fallback():
    with patch.dict(os.environ, {}, clear=True):
        term, is_modern = check_terminal()
    assert term == "unknown"
    assert is_modern is False


def test_tmux_detected_modern():
    with patch.dict(os.environ, {"TERM_PROGRAM": "tmux"}, clear=True):
        term, is_modern = check_terminal()
    assert is_modern is True


def test_warning_none_for_modern():
    with patch.dict(os.environ, {"TERM_PROGRAM": "kitty"}, clear=True):
        assert get_terminal_warning() is None


def test_warning_message_for_legacy():
    with patch.dict(os.environ, {"TERM": "xterm"}, clear=True):
        warn = get_terminal_warning()
    assert warn is not None
    assert "xterm" in warn


def test_modern_terminals_set_has_expected():
    assert "kitty" in MODERN_TERMINALS
    assert "alacritty" in MODERN_TERMINALS
