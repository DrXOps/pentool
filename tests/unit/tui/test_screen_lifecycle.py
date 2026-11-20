"""Unit tests for the lazy screen lifecycle — no TUI is mounted.

The point of :mod:`pentool.tui.screen_lifecycle` is that the *decisions* live
outside Textual: the planner is a pure function and the manager talks to the DOM
through a small protocol, so a fake host covers the whole behaviour. Mounting a
real app to test "which screen got unmounted" would cost seconds per case and
tell us nothing about the policy.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pentool.tui.app import PentoolApp
from pentool.tui.screen_lifecycle import (
    LazyScreenManager,
    ScreenHost,
    SwitchPlan,
    plan_switch,
    screen_id,
)

# ── The fake host: records every DOM call the manager makes ──────────────────


class FakeHost:
    """In-memory stand-in for ``ContentSwitcher`` + screens."""

    def __init__(self, mounted: tuple[str, ...] = ()) -> None:
        self._screens: dict[str, Any] = {module: object() for module in mounted}
        self.calls: list[tuple[str, str]] = []
        self.visible: str | None = None

    # ScreenHost protocol -------------------------------------------------------
    def mounted_modules(self) -> frozenset[str]:
        return frozenset(self._screens)

    def get_module(self, module_id: str) -> Any | None:
        return self._screens.get(module_id)

    async def mount_module(self, module_id: str, screen_class: type) -> Any:
        self.calls.append(("mount", module_id))
        widget = screen_class(module_id)
        self._screens[module_id] = widget
        return widget

    async def unmount_module(self, module_id: str) -> None:
        self.calls.append(("unmount", module_id))
        self._screens.pop(module_id, None)

    def show_module(self, module_id: str) -> None:
        self.calls.append(("show", module_id))
        self.visible = module_id


class FakeScreen:
    """Registered screen class: remembers which module it renders."""

    def __init__(self, module_id: str) -> None:
        self.module_id = module_id


def _registry(module_id: str) -> type | None:
    return None if module_id in {"recon-unavailable", "settings"} else FakeScreen


def test_screen_id_is_prefixed_once() -> None:
    assert screen_id("proxy") == "screen-proxy"


def test_fake_host_satisfies_the_protocol() -> None:
    """The protocol is the contract the app implements — keep it checkable."""
    assert isinstance(FakeHost(), ScreenHost)


# ── Planner: pure decisions ──────────────────────────────────────────────────


def test_first_switch_mounts_the_target_and_keeps_the_start_screen() -> None:
    plan = plan_switch("proxy", {"dashboard"})
    assert plan == SwitchPlan(target="proxy", to_mount=True, to_unmount=("dashboard",))


def test_switching_back_remounts_what_was_dropped() -> None:
    plan = plan_switch("dashboard", {"proxy"})
    assert plan.to_mount is True
    assert plan.to_unmount == ("proxy",)


def test_switching_to_the_mounted_screen_mounts_nothing() -> None:
    plan = plan_switch("proxy", {"proxy"})
    assert plan.to_mount is False
    assert plan.to_unmount == ()


def test_keep_alive_survives_the_switch() -> None:
    plan = plan_switch("proxy", {"dashboard", "settings"}, keep_alive=frozenset({"dashboard"}))
    assert plan.to_unmount == ("settings",)


def test_keep_alive_of_the_target_does_not_double_mount() -> None:
    plan = plan_switch("dashboard", {"dashboard"}, keep_alive=frozenset({"dashboard"}))
    assert (plan.to_mount, plan.to_unmount) == (False, ())


def test_unmount_order_is_stable() -> None:
    """Sorted output keeps logs and tests deterministic."""
    plan = plan_switch("proxy", {"settings", "dashboard", "intruder"})
    assert plan.to_unmount == ("dashboard", "intruder", "settings")


# ── Manager: applies the plan through the host ──────────────────────────────


@pytest.mark.asyncio
async def test_activate_mounts_then_shows_and_drops_the_previous_screen() -> None:
    host = FakeHost(mounted=("dashboard",))
    manager = LazyScreenManager(host, registry=_registry)

    screen = await manager.activate("proxy")

    # Order matters: the new screen becomes visible *before* the old one is
    # dropped, otherwise the switcher points at a removed child for a frame.
    assert host.calls == [("mount", "proxy"), ("show", "proxy"), ("unmount", "dashboard")]
    assert host.visible == "proxy"
    assert screen is host.get_module("proxy")
    assert manager.is_mounted("proxy")


@pytest.mark.asyncio
async def test_activate_of_a_mounted_screen_only_shows_it() -> None:
    """Switching back must be instant: no mount, no reload."""
    host = FakeHost(mounted=("proxy",))
    manager = LazyScreenManager(host, registry=_registry)

    await manager.activate("proxy")

    assert host.calls == [("show", "proxy")]


@pytest.mark.asyncio
async def test_activate_unknown_module_mounts_nothing_and_returns_none() -> None:
    host = FakeHost()
    manager = LazyScreenManager(host, registry=_registry)

    assert await manager.activate("recon-unavailable") is None
    assert host.calls == []


@pytest.mark.asyncio
async def test_keep_alive_screen_is_not_unmounted() -> None:
    host = FakeHost(mounted=("dashboard", "proxy"))
    manager = LazyScreenManager(host, registry=_registry, keep_alive=frozenset({"dashboard"}))

    await manager.activate("proxy")

    assert ("unmount", "dashboard") not in host.calls


@pytest.mark.asyncio
async def test_concurrent_activations_do_not_mount_twice() -> None:
    """Two clicks in a row (or a hotkey racing the tab) must mount once."""
    host = FakeHost()
    manager = LazyScreenManager(host, registry=_registry)

    await asyncio.gather(manager.activate("proxy"), manager.activate("proxy"))

    mounts = [call for call in host.calls if call == ("mount", "proxy")]
    assert len(mounts) == 1


# ── Staleness: reload is deferred to the next mount ─────────────────────────


@pytest.mark.asyncio
async def test_keep_recent_keeps_the_previous_screen_alive() -> None:
    """Switching back must not pay the mount again — that is what keep_recent is for.

    Measured trade-off (2026-11-20): a mounted screen costs ~50-110 ms on every
    action, a re-mount costs ~600-1100 ms. One spare screen is the default.
    """
    host = FakeHost(mounted=("dashboard",))
    manager = LazyScreenManager(host, registry=_registry, keep_recent=1)

    await manager.activate("proxy")
    assert host.mounted_modules() == frozenset({"dashboard", "proxy"})

    await manager.activate("repeater")
    # proxy is the "recent" one now, dashboard is dropped.
    assert host.mounted_modules() == frozenset({"proxy", "repeater"})

    calls_before = list(host.calls)
    await manager.activate("proxy")
    assert host.calls == calls_before + [("show", "proxy")], "coming back must not re-mount"


@pytest.mark.asyncio
async def test_keep_recent_zero_drops_everything_but_the_target() -> None:
    host = FakeHost(mounted=("dashboard",))
    manager = LazyScreenManager(host, registry=_registry)

    await manager.activate("proxy")

    assert host.mounted_modules() == frozenset({"proxy"})


@pytest.mark.asyncio
async def test_stale_screen_reloads_once_when_it_is_mounted() -> None:
    host = FakeHost()
    reloaded: list[tuple[str, Any]] = []

    async def reload(module_id: str, screen: Any) -> None:
        reloaded.append((module_id, screen))

    manager = LazyScreenManager(host, registry=_registry, reload=reload)
    manager.mark_stale("proxy")

    await manager.activate("proxy")

    assert reloaded == [("proxy", host.get_module("proxy"))]
    assert manager.stale_modules == frozenset()


@pytest.mark.asyncio
async def test_failed_reload_keeps_the_screen_stale_for_the_next_attempt() -> None:
    """A failed reload must not be swallowed: the screen keeps other data."""
    host = FakeHost()
    attempts: list[str] = []

    async def reload(module_id: str, screen: Any) -> None:
        attempts.append(module_id)
        raise OSError("disk gone")

    manager = LazyScreenManager(host, registry=_registry, reload=reload)
    manager.mark_stale("proxy")

    await manager.activate("proxy")

    assert attempts == ["proxy"]
    assert manager.stale_modules == frozenset({"proxy"})


@pytest.mark.asyncio
async def test_mounted_screen_is_not_reloaded_on_activate() -> None:
    """Reloading already-live screens is the project manager's job, not ours."""
    host = FakeHost(mounted=("proxy",))
    reloaded: list[str] = []

    async def reload(module_id: str, screen: Any) -> None:
        reloaded.append(module_id)

    manager = LazyScreenManager(host, registry=_registry, reload=reload)
    manager.mark_stale("proxy")  # even then: it is mounted, so nothing to defer

    await manager.activate("proxy")

    assert reloaded == []


# ── `ensure`: mount without showing (T-031) ─────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_mounts_without_showing() -> None:
    """A background mount must not steal the screen the user is looking at.

    This is the bug the user saw at startup: the `--url` seed asked for the
    Target screen, `ensure_module_screen()` called `activate()`, and Target was
    *shown* on top of the Dashboard (T-031).
    """
    host = FakeHost(mounted=("dashboard",))
    manager = LazyScreenManager(host, registry=_registry)

    screen = await manager.ensure("target")

    assert screen is not None
    assert host.calls == [("mount", "target")], "ensure must mount and nothing else"
    assert host.visible is None, "ensure must not change the visible module"
    assert "target" in host.mounted_modules()


@pytest.mark.asyncio
async def test_ensure_is_a_no_op_for_a_mounted_screen() -> None:
    host = FakeHost(mounted=("dashboard", "target"))
    manager = LazyScreenManager(host, registry=_registry)

    await manager.ensure("target")

    assert host.calls == []
    assert host.visible is None


@pytest.mark.asyncio
async def test_ensure_does_not_evict_the_visible_screen() -> None:
    """keep_recent must not turn a background mount into an unmount of the UI."""
    host = FakeHost(mounted=("dashboard",))
    manager = LazyScreenManager(host, registry=_registry, keep_recent=1)

    await manager.ensure("target")

    assert ("unmount", "dashboard") not in host.calls
    assert "dashboard" in host.mounted_modules()


# ── The app's screen API must not shadow Textual's ──────────────────────────


def test_app_screen_api_does_not_shadow_textual() -> None:
    """Naming a helper `get_screen` broke every dialog — pin the rule.

    Textual's `App.get_screen(name_or_class)` is part of the screen-stack API and
    `push_screen()` calls it internally. A `PentoolApp.get_screen(module_id)`
    override therefore received a `Screen` *instance* and turned it into the
    selector `#screen-ModalScreen()`, so `push_screen(ModalScreen())` died with
    `InvalidQueryFormat`. The module-screen helpers are prefixed with
    `module_` for exactly that reason.
    """
    from textual.app import App

    # Public Textual App members the app must never override by accident.
    reserved = {
        "get_screen",
        "push_screen",
        "pop_screen",
        "switch_screen",
        "install_screen",
        "uninstall_screen",
        "is_screen_installed",
        "query_one",
        "screen",
        "screen_stack",
    }
    own = set(PentoolApp.__dict__)
    shadowed = sorted(own & (reserved & set(dir(App))))
    assert not shadowed, f"PentoolApp shadows Textual's public API: {shadowed} — rename the helper"


def test_module_screen_api_is_prefixed() -> None:
    """The three sanctioned lookups exist under their `module_` names."""
    for name in ("module_screen", "require_module_screen", "ensure_module_screen"):
        assert callable(getattr(PentoolApp, name, None)), f"PentoolApp.{name} is missing"
