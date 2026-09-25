"""Default hotkey layout for Pentool.

Every binding in the application is declared here in one place so the full
keyboard map is auditable without reading every screen file.

To add a new hotkey:
  1. Add a ``HotkeyEntry(…)`` to the appropriate ``_make_*()`` function.
  2. Call the function in ``init_hotkeys()``.
  3. Wire ``action_<name>`` in the Screen that handles it.
  4. If the Screen overrides ``BINDINGS = […]``, replace with
     ``self._bindings = registry.get_bindings("<group>")`` in ``on_mount``.
"""

from __future__ import annotations

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


# ── module switcher letters ──────────────────────────────────────────────
MODULE_KEYS = [
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


def _make_global() -> list[HotkeyEntry]:
    return [
        _e("ctrl+q",         "quit",              "Quit",          show=True,  priority=True),
        _e("ctrl+s",         "save_project",      "Save .db",      show=False, priority=True),
        _e("ctrl+o",         "open_project",      "Open .db",      show=False, priority=True),
        _e("ctrl+n",         "new_project",       "New",           show=False, priority=True),
        _e("ctrl+shift+s",   "save_project_json", "Save JSON",     show=False, priority=True),
        _e("ctrl+shift+o",   "open_project_json", "Open JSON",     show=False, priority=True),
        _e("ctrl+comma",     "switch_module('settings')", "Settings", show=False, priority=True),
        # Proxy sub-tabs via Ctrl+H/I/W
        _e("ctrl+h",         "proxy_tab('http')",     "HTTP History",  show=False, priority=True),
        _e("ctrl+i",         "proxy_tab('intercept')","Intercept",     show=False, priority=True),
        _e("ctrl+w",         "proxy_tab('ws')",       "WS History",    show=False, priority=True),
        # Repeater send — ctrl+space = ctrl-at in most terminals
        _e("ctrl-at",        "repeater_send",     "Send",          show=False, priority=True),
        _e("ctrl+space",     "repeater_send",     "Send",          show=False, priority=True),
        # Select all
        _e("ctrl+a",         "select_all",        "Select All",    show=False, priority=True),
        # Module switcher
        *MODULE_KEYS,
    ]


def _make_proxy() -> list[HotkeyEntry]:
    return [
        _e("i",              "toggle_inspector",     "Inspector",     show=True),
        _e("h",              "focus_tab_history",    "HTTP History",  show=False),
        _e("n",              "focus_tab_intercept",  "Intercept",     show=False),
        _e("w",              "focus_tab_ws",         "WS History",    show=False),
        _e("ctrl+h",         "focus_tab_history",    "HTTP History",  show=False),
        _e("ctrl+n",         "focus_tab_intercept",  "Intercept",     show=False),
        _e("ctrl+w",         "focus_tab_ws",         "WS History",    show=False),
        _e("ctrl+r",         "send_to_repeater",     "Send to Repeater", show=True),
        _e("ctrl+u",         "copy_url",             "Copy URL",      show=True),
        _e("ctrl+b",         "open_in_browser",      "Open in Browser", show=True, priority=True),
        _e("ctrl+shift+b",   "open_in_browser",      "",                show=False, priority=True),
        _e("ctrl+s",         "send_to_scanner",      "Send to Scanner",  show=True),
        _e("m",              "context_menu",         "Context Menu",  show=False),
        _e("escape",         "hide_detail",          "Hide Detail",   show=True),
    ]


def _make_repeater() -> list[HotkeyEntry]:
    return [
        _e("ctrl+enter",     "send",                 "Send",          show=True, priority=True),
        _e("ctrl+at",        "send",                 "Send",          show=False, priority=True),
        _e("ctrl+space",     "send",                 "Send",          show=False, priority=True),
        _e("ctrl+f",         "toggle_search",        "Search",        show=True,  priority=True),
        _e("ctrl+d",         "toggle_diff",          "Diff",          show=True,  priority=True),
        _e("ctrl+b",         "open_in_browser",      "Open in Browser", show=True, priority=True),
        _e("ctrl+shift+b",   "open_in_browser",      "",                show=False, priority=True),
        _e("ctrl+s",         "send_to_scanner",      "Send to Scanner",  show=True),
        _e("ctrl+tab",       "next_tab",             "Next Tab",      show=False),
    ]


def _make_intruder() -> list[HotkeyEntry]:
    return [
        _e("ctrl+enter",     "start_attack",         "Start Attack",  show=True),
        _e("ctrl+p",         "toggle_pause",         "Pause/Resume",  show=True),
        _e("escape",         "hide_detail",          "Hide Detail",   show=True),
        _e("ctrl+b",         "open_in_browser",      "Open in Browser", show=True, priority=True),
    ]


def _make_scanner() -> list[HotkeyEntry]:
    return [
        _e("F5",             "start_scan",           "Start Scan",    show=True,  priority=True),
        _e("F6",             "stop_scan",            "Stop Scan",     show=True,  priority=True),
        _e("ctrl+enter",     "start_scan",           "Start Scan",    show=False, priority=True),
        _e("r",              "send_to_repeater",     "Send to Repeater", show=True),
    ]


def _make_target() -> list[HotkeyEntry]:
    return [
        _e("m",              "context_menu",         "Context Menu",  show=False),
    ]


def _make_dashboard() -> list[HotkeyEntry]:
    return [
        _e("r",              "refresh_dash",         "Refresh",       show=True),
    ]


def _make_decoder() -> list[HotkeyEntry]:
    return [
        _e("ctrl+enter",     "run_chain",            "Run",           show=True),
        _e("ctrl+l",         "clear_all",            "Clear",         show=False),
        _e("ctrl+c",         "copy_result",          "Copy",          show=False),
    ]


def _make_comparer() -> list[HotkeyEntry]:
    return [
        _e("ctrl+enter",     "compare",              "Compare",       show=True),
        _e("ctrl+l",         "clear",                "Clear",         show=False),
    ]


def _make_sequencer() -> list[HotkeyEntry]:
    return [
        _e("ctrl+enter",     "analyze",              "Analyze",       show=True),
        _e("ctrl+l",         "clear_tokens",         "Clear",         show=False),
    ]


# ── public API ───────────────────────────────────────────────────────────
def init_hotkeys() -> None:
    """Register all default hotkeys into the global registry.

    Call once at application startup (``App.on_mount``).
    """
    registry.register("global",    _make_global())
    registry.register("proxy",     _make_proxy())
    registry.register("repeater",  _make_repeater())
    registry.register("intruder",  _make_intruder())
    registry.register("scanner",   _make_scanner())
    registry.register("target",    _make_target())
    registry.register("dashboard", _make_dashboard())
    registry.register("decoder",   _make_decoder())
    registry.register("comparer",  _make_comparer())
    registry.register("sequencer", _make_sequencer())