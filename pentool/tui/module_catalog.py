"""One description of every top-level module.

Before this file the same catalog was written four times — the tab bar
(``widgets/module_tabs.MODULES``), the hotkey table
(``hotkeys/defaults._MODULE_ENTRIES``), the screen map
(``screen_registry.SCREEN_MAP``) and two gating sets (``PentoolApp._FREE_MODULES``,
``project_manager._RELOADABLE_MODULES``). They disagreed: the tab said
"Dashboard", the hint bar said "Dash"; a module could be added to one list and
forgotten in another; and the hint bar showed "—" for every module that had no
hint group, which after the Utils merge meant four modules out of ten.

Adding a module is now a single entry here. Everything else is derived:
tab bar, switch hotkeys, project guard, Basic-mode visibility, PRO gating,
project reload and the hint group.

What this module deliberately does **not** do: import Textual or screens. The
screen class lives in ``screen_registry`` (it needs the widget tree) and is
looked up by id.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    """Everything the app needs to know about one module."""

    id: str
    #: Label on the tab bar.
    label: str
    #: Shorter label for the hotkey hint row (space is scarce there).
    short: str
    #: Letter that switches to this module. ``None`` — no letter (Settings uses Ctrl+,).
    hotkey: str | None = None
    #: Visible in Basic mode (no project open).
    basic: bool = False
    #: Reachable without a project at all (the project guard lets it through).
    free: bool = False
    #: PRO feature required to open. ``None`` — available without a licence.
    license_feature: str | None = None
    #: Reloaded when another project is opened.
    reloadable: bool = False
    #: Hint group(s) shown in the bottom bar. Empty — only the global keys apply.
    hints: tuple[str, ...] = ()


#: Tab order, left to right. This tuple *is* the module list.
CATALOG: tuple[Module, ...] = (
    Module(
        id="dashboard",
        label="Dashboard",
        short="Dash",
        hotkey="H",
        basic=True,
        free=True,
        reloadable=True,
        hints=("dashboard",),
    ),
    Module(
        id="proxy",
        label="Proxy",
        short="Proxy",
        hotkey="P",
        basic=True,
        reloadable=True,
        hints=("proxy",),
    ),
    Module(
        id="repeater",
        label="Repeater",
        short="Rpt",
        hotkey="R",
        basic=True,
        reloadable=True,
        hints=("repeater",),
    ),
    Module(
        id="intruder",
        label="Intruder",
        short="Intrud",
        hotkey="I",
        basic=True,
        reloadable=True,
        hints=("intruder",),
    ),
    Module(
        id="scanner",
        label="Scanner",
        short="Scan",
        hotkey="S",
        license_feature="scanner_pro",
        reloadable=True,
        hints=("scanner",),
    ),
    Module(
        id="target",
        label="Target",
        short="Target",
        hotkey="T",
        reloadable=True,
        hints=("target",),
    ),
    # Decoder / Comparer / Sequencer are sub-tabs of Utils; see UTILS_TABS.
    Module(id="utils", label="Utils", short="Utils", hotkey="U"),
    Module(id="extensions", label="Extensions", short="Ext", hotkey="E"),
    Module(id="recon", label="Recon", short="Recon", hotkey="N", license_feature="ai_discovery"),
    Module(id="settings", label="Settings", short="Settings", basic=True, free=True),
)

#: Hotkeys that jump straight into a Utils sub-tab: (tab id, hint label, letter).
#: They keep working after the three tools were merged into one module.
UTILS_TABS: tuple[tuple[str, str, str], ...] = (
    ("decoder", "Decoder", "D"),
    ("comparer", "Comparer", "C"),
    ("sequencer", "Sequencer", "Q"),
)

_BY_ID: dict[str, Module] = {module.id: module for module in CATALOG}


def get(module_id: str) -> Module | None:
    """The module with this id, or ``None`` when the id does not exist."""
    return _BY_ID.get(module_id)


def ids() -> tuple[str, ...]:
    """Module ids in tab order."""
    return tuple(module.id for module in CATALOG)


def label(module_id: str) -> str:
    """Tab label of a module (the id itself for unknown ids)."""
    module = get(module_id)
    return module.label if module else module_id


def tab_entries() -> list[tuple[str, str]]:
    """``(id, label)`` for the tab bar."""
    return [(module.id, module.label) for module in CATALOG]


def basic_ids() -> frozenset[str]:
    """Modules visible in Basic mode."""
    return frozenset(module.id for module in CATALOG if module.basic)


def free_ids() -> frozenset[str]:
    """Modules reachable without an open project."""
    return frozenset(module.id for module in CATALOG if module.free)


def reloadable_ids() -> tuple[str, ...]:
    """Modules that reload when another project is opened."""
    return tuple(module.id for module in CATALOG if module.reloadable)


def license_feature(module_id: str) -> str | None:
    """PRO feature a module needs, or ``None`` when it is free."""
    module = get(module_id)
    return module.license_feature if module else None


def hints_groups(module_id: str) -> tuple[str, ...]:
    """Hint groups for the bottom bar (empty means "only the global keys")."""
    module = get(module_id)
    return module.hints if module else ()


def switch_hotkeys() -> list[tuple[str, str, str]]:
    """``(letter, action, short label)`` for every module that has a letter.

    The Utils sub-tab letters are inserted right after Utils so the hint row keeps
    its familiar order (… U, D, C, Q, E, N).
    """
    entries: list[tuple[str, str, str]] = []
    for module in CATALOG:
        if module.hotkey:
            entries.append((module.hotkey, f"switch_module('{module.id}')", module.short))
        if module.id == "utils":
            entries.extend((letter, f"utils_tab('{tab}')", short) for tab, short, letter in UTILS_TABS)
    return entries
