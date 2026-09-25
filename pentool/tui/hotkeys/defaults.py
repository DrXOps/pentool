"""Default hotkey layout for Pentool.

Single source of truth for every keybinding in the application.
Registry initialises at **import time** (not in ``App.on_mount``) so
that Screen classes can use exported ``PROXY_BINDINGS`` etc. as their
class-level ``BINDINGS = [...]`` attribute immediately.

Usage in a Screen::

    from pentool.tui.hotkeys.defaults import PROXY_BINDINGS

    class ProxyScreen(Widget):
        BINDINGS = PROXY_BINDINGS

To add / change a hotkey:
  1. Edit the appropriate ``_make_*()`` function below.
  2. Wire ``action_<name>`` in the Screen.
  3. ``BINDINGS`` constant updates automatically.
"""

from __future__ import annotations

from textual.binding import Binding, BindingsMap

from pentool.tui.hotkeys import HotkeyEntry, registry


# ── helpers ──────────────────────────────────────────────────────────────
def _e(
    keys: str,
    action: str,
    description: str,
    group: str = "global",
    show: bool = True,
    priority: bool = False,
) -> HotkeyEntry:
    return HotkeyEntry(keys, action, description, group, show, priority)


def _entries_to_bindings(entries: list[HotkeyEntry]) -> list[Binding]:
    return [e.to_binding() for e in entries]


# ── module switcher letters ──────────────────────────────────────────────
_MODULE_ENTRIES = [
    _e("H", "switch_module('dashboard')", "Dashboard"),
    _e("P", "switch_module('proxy')",     "Proxy"),
    _e("R", "switch_module('repeater')",  "Repeater"),
    _e("I", "switch_module('intruder')",  "Intruder"),
    _e("S", "switch_module('scanner')",   "Scanner"),
    _e("T", "switch_module('target')",    "Target"),
    _e("D", "switch_module('decoder')",   "Decoder"),
    _e("C", "switch_module('comparer')",  "Comparer"),
    _e("Q", "switch_module('sequencer')", "Sequencer"),
    _e("E", "switch_module('extensions')","Extensions"),
    # Shift+digit aliases
    _e("!",  "switch_module('proxy')",     "", show=False),
    _e("@",  "switch_module('repeater')",  "", show=False),
    _e("#",  "switch_module('intruder')",  "", show=False),
    _e("$",  "switch_module('scanner')",   "", show=False),
    _e("%",  "switch_module('decoder')",   "", show=False),
    _e("^",  "switch_module('comparer')",  "", show=False),
    _e("&",  "switch_module('sequencer')", "", show=False),
    _e("(",  "switch_module('extensions')","", show=False),
]

_GLOBAL_ENTRIES = [
    _e("ctrl+q",         "quit",              "Quit",          show=True,  priority=True),
    _e("ctrl+s",         "save_project",      "Save .db",      show=False, priority=True),
    _e("ctrl+o",         "open_project",      "Open .db",      show=False, priority=True),
    _e("ctrl+n",         "new_project",       "New",           show=False, priority=True),
    _e("ctrl+shift+s",   "save_project_json", "Save JSON",     show=False, priority=True),
    _e("ctrl+shift+o",   "open_project_json", "Open JSON",     show=False, priority=True),
    _e("ctrl+comma",     "switch_module('settings')", "Settings", show=False, priority=True),
    _e("ctrl+h",         "proxy_tab('http')",     "HTTP History",  show=False, priority=True),
    _e("ctrl+i",         "proxy_tab('intercept')","Intercept",     show=False, priority=True),
    _e("ctrl+w",         "proxy_tab('ws')",       "WS History",    show=False, priority=True),
    _e("ctrl-at",        "repeater_send",     "Send",          show=False, priority=True),
    _e("ctrl+space",     "repeater_send",     "Send",          show=False, priority=True),
    _e("ctrl+a",         "select_all",        "Select All",    show=False, priority=True),
    *_MODULE_ENTRIES,
]

_PROXY_ENTRIES = [
    _e("i",              "toggle_inspector",     "Inspector",     show=True),
    _e("h",              "focus_tab_history",    "HTTP History",  show=False),
    _e("n",              "focus_tab_intercept",  "Intercept",     show=False),
    _e("w",              "focus_tab_ws",         "WS History",    show=False),
    _e("ctrl+h",         "focus_tab_history",    "HTTP History",  show=False),
    _e("ctrl+n",         "focus_tab_intercept",  "Intercept",     show=False),
    _e("ctrl+w",         "focus_tab_ws",         "WS History",    show=False),
    _e("ctrl+r",         "send_to_repeater",     "Send to Repeater", show=True),
    _e("ctrl+u",         "copy_url",             "Copy URL",      show=True),
    _e("ctrl+shift+v",   "open_in_browser",      "View Browser",  show=True),
    _e("ctrl+b",         "open_in_browser",      "",              show=False),
    _e("ctrl+s",         "send_to_scanner",      "Send to Scanner",  show=True),
    _e("m",              "context_menu",         "Context Menu",  show=False),
    _e("escape",         "hide_detail",          "Hide Detail",   show=True),
]

_REPEATER_ENTRIES = [
    _e("ctrl+enter",     "send",                 "Send",          show=True, priority=True),
    _e("ctrl+at",        "send",                 "Send",          show=False, priority=True),
    _e("ctrl+space",     "send",                 "Send",          show=False, priority=True),
    _e("ctrl+f",         "toggle_search",        "Search",        show=True,  priority=True),
    _e("ctrl+d",         "toggle_diff",          "Diff",          show=True,  priority=True),
    _e("ctrl+shift+v",   "open_in_browser",      "View Browser",  show=True),
    _e("ctrl+b",         "open_in_browser",      "",              show=False),
    _e("ctrl+s",         "send_to_scanner",      "Send to Scanner",  show=True),
    _e("ctrl+tab",       "next_tab",             "Next Tab",      show=False),
]

_INTRUDER_ENTRIES = [
    _e("ctrl+enter",     "start_attack",         "Start Attack",  show=True),
    _e("ctrl+p",         "toggle_pause",         "Pause/Resume",  show=True),
    _e("escape",         "hide_detail",          "Hide Detail",   show=True),
    _e("ctrl+shift+v",   "open_in_browser",      "View Browser",  show=True),
    _e("ctrl+b",         "open_in_browser",      "",              show=False),
]

_SCANNER_ENTRIES = [
    _e("F5",             "start_scan",           "Start Scan",    show=True,  priority=True),
    _e("F6",             "stop_scan",            "Stop Scan",     show=True,  priority=True),
    _e("ctrl+enter",     "start_scan",           "Start Scan",    show=False, priority=True),
    _e("r",              "send_to_repeater",     "Send to Repeater", show=True),
]

_TARGET_ENTRIES = [
    _e("m",              "context_menu",         "Context Menu",  show=False),
]

_DASHBOARD_ENTRIES = [
    _e("r",              "refresh_dash",         "Refresh",       show=True),
]

_DECODER_ENTRIES = [
    _e("ctrl+enter",     "run_chain",            "Run",           show=True),
    _e("ctrl+l",         "clear_all",            "Clear",         show=False),
    _e("ctrl+c",         "copy_result",          "Copy",          show=False),
]

_COMPARER_ENTRIES = [
    _e("ctrl+enter",     "compare",              "Compare",       show=True),
    _e("ctrl+l",         "clear",                "Clear",         show=False),
]

_SEQUENCER_ENTRIES = [
    _e("ctrl+enter",     "analyze",              "Analyze",       show=True),
    _e("ctrl+l",         "clear_tokens",         "Clear",         show=False),
]


# ── Registry init (runs at import time) ────────────────────────────────
registry.register("global",    _GLOBAL_ENTRIES)
registry.register("proxy",     _PROXY_ENTRIES)
registry.register("repeater",  _REPEATER_ENTRIES)
registry.register("intruder",  _INTRUDER_ENTRIES)
registry.register("scanner",   _SCANNER_ENTRIES)
registry.register("target",    _TARGET_ENTRIES)
registry.register("dashboard", _DASHBOARD_ENTRIES)
registry.register("decoder",   _DECODER_ENTRIES)
registry.register("comparer",  _COMPARER_ENTRIES)
registry.register("sequencer", _SEQUENCER_ENTRIES)


# ── Build BindingsMap helpers for __init__ ────────────────────────────

def build_global_bindings() -> BindingsMap:
    from pentool.tui.hotkeys import build_bindings_map
    return build_bindings_map(_entries_to_bindings(_GLOBAL_ENTRIES))

def build_proxy_bindings() -> BindingsMap:
    from pentool.tui.hotkeys import build_bindings_map
    return build_bindings_map(_entries_to_bindings(_PROXY_ENTRIES))

def build_repeater_bindings() -> BindingsMap:
    from pentool.tui.hotkeys import build_bindings_map
    return build_bindings_map(_entries_to_bindings(_REPEATER_ENTRIES))

def build_intruder_bindings() -> BindingsMap:
    from pentool.tui.hotkeys import build_bindings_map
    return build_bindings_map(_entries_to_bindings(_INTRUDER_ENTRIES))

def build_scanner_bindings() -> BindingsMap:
    from pentool.tui.hotkeys import build_bindings_map
    return build_bindings_map(_entries_to_bindings(_SCANNER_ENTRIES))

def build_target_bindings() -> BindingsMap:
    from pentool.tui.hotkeys import build_bindings_map
    return build_bindings_map(_entries_to_bindings(_TARGET_ENTRIES))

def build_dashboard_bindings() -> BindingsMap:
    from pentool.tui.hotkeys import build_bindings_map
    return build_bindings_map(_entries_to_bindings(_DASHBOARD_ENTRIES))

def build_decoder_bindings() -> BindingsMap:
    from pentool.tui.hotkeys import build_bindings_map
    return build_bindings_map(_entries_to_bindings(_DECODER_ENTRIES))

def build_comparer_bindings() -> BindingsMap:
    from pentool.tui.hotkeys import build_bindings_map
    return build_bindings_map(_entries_to_bindings(_COMPARER_ENTRIES))

def build_sequencer_bindings() -> BindingsMap:
    from pentool.tui.hotkeys import build_bindings_map
    return build_bindings_map(_entries_to_bindings(_SEQUENCER_ENTRIES))