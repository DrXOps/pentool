"""Guards for the module catalog — the single list of top-level modules.

Before the catalog the same list lived in five places and disagreed with itself.
These tests fail when a new module is added to one consumer and forgotten in another.
"""

from __future__ import annotations

from pentool.tui import module_catalog
from pentool.tui.screen_registry import SCREEN_MAP, get_screen_class
from pentool.tui.widgets.module_tabs import BASIC_MODULES, MODULES

#: Modules whose screen ships with the PRO submodule; absent from a free install.
PRO_ONLY = {"recon"}


def test_ids_are_unique() -> None:
    ids = module_catalog.ids()
    assert len(ids) == len(set(ids))


def test_every_module_has_a_label_and_a_short_label() -> None:
    for module in module_catalog.CATALOG:
        assert module.label.strip(), f"{module.id}: empty label"
        assert module.short.strip(), f"{module.id}: empty short label"
        assert len(module.short) <= 8, f"{module.id}: short label is too long for the hint row"


def test_hotkey_letters_are_unique() -> None:
    letters = [module.hotkey for module in module_catalog.CATALOG if module.hotkey]
    assert len(letters) == len(set(letters)), f"duplicate switch letters: {letters}"
    utils_letters = [letter for _tab, _label, letter in module_catalog.UTILS_TABS]
    assert not set(letters) & set(utils_letters), "a Utils sub-tab letter collides with a module letter"


def test_tab_bar_follows_the_catalog() -> None:
    assert [module_id for module_id, _label in MODULES] == list(module_catalog.ids())
    assert BASIC_MODULES == module_catalog.basic_ids()


def test_every_module_has_a_screen_or_is_pro_only() -> None:
    """A tab that opens an empty window is the bug the registry was written for."""
    for module_id in module_catalog.ids():
        if module_id in PRO_ONLY:
            continue
        assert module_id in SCREEN_MAP, f"{module_id}: no screen in screen_registry.SCREEN_MAP"
        assert get_screen_class(module_id) is not None


def test_screen_registry_does_not_invent_modules() -> None:
    unknown = set(SCREEN_MAP) - set(module_catalog.ids())
    assert not unknown, f"screen_registry maps ids that are not in the catalog: {unknown}"


def test_switch_hotkeys_cover_every_module_that_has_a_letter() -> None:
    entries = module_catalog.switch_hotkeys()
    actions = {action for _key, action, _short in entries}
    for module in module_catalog.CATALOG:
        if module.hotkey:
            assert f"switch_module('{module.id}')" in actions, f"{module.id}: no switch hotkey"
    for tab, _label, _letter in module_catalog.UTILS_TABS:
        assert f"utils_tab('{tab}')" in actions, f"utils sub-tab {tab}: no hotkey"


def test_gating_sets_are_derived_from_the_catalog() -> None:
    free = module_catalog.free_ids()
    assert {"dashboard", "settings"} <= free
    # A module may be visible in Basic mode and still require a project; the two
    # flags are independent on purpose and both come from one entry each.
    assert BASIC_MODULES <= set(module_catalog.ids())
    assert set(module_catalog.reloadable_ids()) <= set(module_catalog.ids())


def test_pro_modules_declare_a_licence_feature() -> None:
    for module in module_catalog.CATALOG:
        if module.id in {"scanner", "recon"}:
            assert module.license_feature, f"{module.id}: PRO module without a licence feature"
