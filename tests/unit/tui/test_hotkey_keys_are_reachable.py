"""Every bound key must be one Textual's own parser can actually produce.

The hotkey table spells keys as plain strings. A string no terminal produces is
accepted by ``Binding``, shows up in the footer, and does nothing when pressed —
the same "written but never executes" defect as the rest of this suite, one
layer down. Worse, ``pilot.press("ctrl+at")`` passes the name through verbatim,
so a test can "prove" a binding that a real terminal can never trigger.

The authority here is ``XTermParser``, not a list written by hand:

* a classic terminal maps Ctrl+Space to NUL, which Textual turns into
  ``ctrl+@`` (``_ansi_sequences``: ``"\\x00": (Keys.ControlAt,)``);
* a Kitty-protocol terminal sends ``CSI 32;5u``, parsed to ``ctrl+space``;
* neither ever produces ``ctrl-at``, which is what the table used to bind —
  Repeater's "Ctrl+Space = Send" therefore only ever worked in pilot tests;
* ``ctrl+i`` and ``ctrl+h`` are unreachable the same way: those bytes are Tab
  and Backspace, and dispatch does not expand ``KEY_ALIASES``.

``_KNOWN_UNREACHABLE`` is a ratchet, in the same spirit as
``tools/check_silent_except.py``: the entries below are debt that is *reported*
in F-052 rather than silently accepted, and the set may only shrink. A newly
added dead spelling fails the test outright.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from textual import events
from textual._ansi_sequences import ANSI_SEQUENCES_KEYS
from textual._xterm_parser import XTermParser

from pentool.tui.hotkeys.defaults import (
    _COMPARER_ENTRIES,
    _DASHBOARD_ENTRIES,
    _DECODER_ENTRIES,
    _GLOBAL_ENTRIES,
    _INTRUDER_ENTRIES,
    _MODULE_ENTRIES,
    _PROXY_ENTRIES,
    _REPEATER_ENTRIES,
    _SCANNER_ENTRIES,
    _SEQUENCER_ENTRIES,
    _TARGET_ENTRIES,
)

_GROUPS = {
    "global": _GLOBAL_ENTRIES,
    "module": _MODULE_ENTRIES,
    "proxy": _PROXY_ENTRIES,
    "repeater": _REPEATER_ENTRIES,
    "intruder": _INTRUDER_ENTRIES,
    "scanner": _SCANNER_ENTRIES,
    "target": _TARGET_ENTRIES,
    "dashboard": _DASHBOARD_ENTRIES,
    "decoder": _DECODER_ENTRIES,
    "comparer": _COMPARER_ENTRIES,
    "sequencer": _SEQUENCER_ENTRIES,
}

#: Bytes that a classic terminal sends for Ctrl+I / Ctrl+H — the key names
#: ``ctrl+i``/``ctrl+h`` never occur in an event.
_ALIASED_AWAY = {"ctrl+i": "tab", "ctrl+h": "backspace"}

#: Keys bound today that no terminal produces. Reported as F-052; this set may
#: only shrink. Removing an entry from the table removes it here.
_KNOWN_UNREACHABLE = {
    "ctrl+i": "global+proxy — a classic terminal sends Tab, and dispatch does not expand KEY_ALIASES",
    "ctrl+h": "global+proxy — a classic terminal sends Backspace",
    "F5": "scanner — Textual emits lowercase 'f5'; binding keys are matched verbatim",
    "F6": "scanner — same as F5",
}

_KITTY_SEQUENCES = (
    "\x1b[9;5u",  # ctrl+tab
    "\x1b[13;5u",  # ctrl+enter
    "\x1b[32;5u",  # ctrl+space
    "\x1b[64;5u",  # ctrl+@ (the Kitty spelling of the same NUL)
    "\x1b[44;5u",  # ctrl+comma
    "\x1b[115;6u",  # ctrl+shift+s
    "\x1b[111;6u",  # ctrl+shift+o
    "\x1b[15~",  # f5
    "\x1b[17~",  # f6
)

_DEFAULTS = Path(__file__).resolve().parents[3] / "pentool" / "tui" / "hotkeys" / "defaults.py"


def keys_the_parser_can_produce() -> set[str]:
    """Every key name Textual's parser emits for something a terminal sends.

    Four sources, all read from the installed Textual rather than retyped: the
    ANSI sequence table, a parse of every control byte, printable ASCII, and a
    handful of Kitty sequences for keys a classic terminal cannot express.

    Deliberately **not** the ``Keys`` enum: it carries ``ControlSpace =
    "ctrl-at"`` as a backward-compatibility alias, so the enum contains exactly
    the spelling this test exists to reject.
    """
    parser = XTermParser(debug=False)
    producible: set[str] = set()

    for value in ANSI_SEQUENCES_KEYS.values():
        if isinstance(value, tuple):
            producible |= {key.value for key in value}
        elif isinstance(value, str):
            producible.add(value)

    for code in range(0x00, 0x20):
        producible |= {event.key for event in parser._sequence_to_key_events(chr(code))}

    producible |= {chr(code) for code in range(0x20, 0x7F)}

    for sequence in _KITTY_SEQUENCES:
        producible |= {event.key for event in parser._sequence_to_key_events(sequence)}

    return producible


@pytest.fixture(scope="module")
def producible() -> set[str]:
    return keys_the_parser_can_produce()


def _bound_keys() -> dict[str, set[str]]:
    """``key -> {group, …}`` for every entry in the table."""
    bound: dict[str, set[str]] = {}
    for group, entries in _GROUPS.items():
        for entry in entries:
            bound.setdefault(entry.keys, set()).add(group)
    return bound


def test_no_new_unreachable_key_is_added(producible: set[str]) -> None:
    dead = sorted({key for key in _bound_keys() if key not in producible} - set(_KNOWN_UNREACHABLE))
    assert not dead, (
        "these keys are bound but no terminal produces them — the binding can never fire. "
        f"Ctrl+Space arrives as 'ctrl+@', never 'ctrl-at'. Offenders: {dead}"
    )


def test_the_known_list_has_no_stale_entries(producible: set[str]) -> None:
    """The ratchet must shrink: a fixed key may not stay listed as broken."""
    fixed = sorted({key for key in _KNOWN_UNREACHABLE if key in producible or key not in _bound_keys()})
    assert not fixed, f"already fixed or no longer bound — delete from _KNOWN_UNREACHABLE: {fixed}"


def test_the_probe_itself_can_say_no(producible: set[str]) -> None:
    """A guard that always passes is worse than none — pin the reference cases."""
    assert "ctrl+@" in producible, "a classic terminal's Ctrl+Space must be producible"
    assert "ctrl+space" in producible, "a Kitty terminal's Ctrl+Space must be producible"
    assert "ctrl-at" not in producible, "the hyphenated spelling never occurs in any protocol"
    assert "ctrl+i" not in producible, "Ctrl+I arrives as 'tab'"
    assert "F5" not in producible, "Textual emits 'f5' lowercase"


def test_aliased_keys_really_are_aliased_away(producible: set[str]) -> None:
    """The reason ``ctrl+i``/``ctrl+h`` are listed as dead, checked not assumed."""
    for name, arrives_as in _ALIASED_AWAY.items():
        assert name not in producible, f"{name} must not be producible"
        assert arrives_as in producible, f"{arrives_as} is what the terminal sends instead"


async def test_a_bound_key_the_parser_never_emits_does_not_fire() -> None:
    """End to end: post the event a terminal really produces.

    ``pilot.press("ctrl+i")`` injects ``Key("ctrl+i")`` verbatim and the
    binding fires — which is exactly how a dead binding looks healthy in a
    test. A terminal sends ``0x09``, the parser names it ``tab``, and the
    ``ctrl+i`` binding is simply not consulted. This asserts that difference
    on a live app, because that is what decides whether the feature exists
    for a user.
    """
    from pentool.tui.app import PentoolApp

    app = PentoolApp()
    app._skip_project_guard = True
    proxy_hits: list[tuple] = []
    send_hits: list[tuple] = []
    original_proxy = PentoolApp.action_proxy_tab
    original_send = PentoolApp.action_repeater_send
    PentoolApp.action_proxy_tab = lambda _self, *args: proxy_hits.append(args)
    PentoolApp.action_repeater_send = lambda _self, *args: send_hits.append(args)
    try:
        async with app.run_test(size=(200, 50)) as pilot:
            await pilot.pause()

            # What a terminal sends for Ctrl+I: the parser calls it Tab, and
            # dispatch does not expand KEY_ALIASES. The binding stays silent.
            app.post_message(events.Key("tab", "\t"))
            await pilot.pause()
            assert not proxy_hits, "Tab fired the Ctrl+I binding — the parser was bypassed"

            # Guard the guard: the name pilot would have injected does fire, so
            # the silence above is about the key *name*, not an unreachable screen.
            proxy_hits.clear()
            app.post_message(events.Key("ctrl+i", None))
            await pilot.pause()
            assert proxy_hits, "ctrl+i no longer fires at all — the test proves nothing"

            # Ctrl+Space in a classic terminal arrives as ctrl+@, which is now
            # bound. This is the spelling the old table was missing.
            app.post_message(events.Key("ctrl+@", "\x00"))
            await pilot.pause()
            assert send_hits, "Ctrl+Space (as ctrl+@) did not reach action_repeater_send"
    finally:
        PentoolApp.action_proxy_tab = original_proxy
        PentoolApp.action_repeater_send = original_send


def test_the_table_has_no_duplicate_key_action_pair() -> None:
    """Same key, same action twice: the second copy can never fire."""
    for group, entries in _GROUPS.items():
        pairs = [(entry.keys, entry.action) for entry in entries]
        duplicated = {pair for pair in pairs if pairs.count(pair) > 1}
        assert not duplicated, f"{group} binds the same key to the same action twice: {duplicated}"


def test_the_file_has_one_note_per_known_dead_key() -> None:
    """Each ratchet entry must be explained where a reader will meet it."""
    source = _DEFAULTS.read_text(encoding="utf-8")
    for key in _KNOWN_UNREACHABLE:
        assert key in source, f"{key} is in the ratchet but no longer in defaults.py — prune the set"
