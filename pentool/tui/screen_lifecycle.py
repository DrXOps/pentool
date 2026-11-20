"""Lazy lifecycle for module screens: one mounted screen instead of thirteen.

Why this module exists
----------------------
Every module screen used to be mounted at startup and stayed in the DOM for the
whole session — 13 screens, ~1600 widgets. Textual's idle/refresh sweep costs
about five message dispatches *per mounted widget* on every interaction, so the
cost of any action grew with the size of the tree: a click on a filter toggle
measured 1444 ms with all screens mounted and 321 ms with only the active one
(2026-11-20, 120x40). That is the "one second per action" the user felt.

What lives here
---------------
* :func:`plan_switch` — a pure function deciding what a switch has to mount and
  unmount. No Textual, no DOM, trivially testable.
* :class:`LazyScreenManager` — applies the plan through a :class:`ScreenHost`,
  remembers which screens are stale after a project switch, and replays that
  reload when a stale screen is finally mounted.
* :class:`ScreenHost` — the small protocol the app implements (mount/unmount/
  show/list). Tests use a fake host, so the whole manager is covered without
  mounting a TUI.

What does *not* live here: how a given screen reloads its data. That is the
app's business (it owns the project manager), injected as the ``reload``
callback, which keeps this module free of per-module knowledge.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Protocol, runtime_checkable

from textual.css.query import NoMatches

from pentool.core.logging import get_logger

logger = get_logger(__name__)

SCREEN_ID_PREFIX = "screen-"


class ScreenNotMounted(NoMatches):
    """A module screen is not in the DOM (lazy mounting: it was never opened).

    Subclasses Textual's ``NoMatches`` on purpose: the handlers written before
    lazy mounting all look like ``try: screen = query_one(SCREEN_X) ... except
    NoMatches: log``. Raising the same family keeps that contract — the screen
    really is not there — while letting the lookup go through the lifecycle
    manager instead of the DOM.
    """


def screen_id(module_id: str) -> str:
    """DOM id of a module screen: ``proxy`` → ``screen-proxy``."""
    return f"{SCREEN_ID_PREFIX}{module_id}"


@runtime_checkable
class ScreenHost(Protocol):
    """What the manager needs from the DOM. Implemented by the app, faked in tests."""

    def mounted_modules(self) -> frozenset[str]:
        """Module ids whose screens are currently in the DOM."""
        ...

    def get_module(self, module_id: str) -> Any | None:
        """The mounted screen widget for *module_id*, or None."""
        ...

    async def mount_module(self, module_id: str, screen_class: type) -> Any:
        """Create and mount the screen for *module_id*, returning the widget."""
        ...

    async def unmount_module(self, module_id: str) -> None:
        """Take the screen off the DOM (unknown/absent ids are a no-op)."""
        ...

    def show_module(self, module_id: str) -> None:
        """Make the module's screen the visible one."""
        ...


@dataclass(frozen=True)
class SwitchPlan:
    """What has to change in the DOM for ``target`` to become visible."""

    target: str
    to_mount: bool
    to_unmount: tuple[str, ...] = ()
    missing: bool = False
    """True when no screen class is registered for ``target`` — nothing to do."""


def plan_switch(
    target: str,
    mounted: Iterable[str],
    *,
    keep_alive: frozenset[str] = frozenset(),
) -> SwitchPlan:
    """Decide mount/unmount for switching to *target*.

    ``keep_alive`` names modules that must stay mounted — a permanent set (cheap
    screens, or ones whose state is expensive to rebuild) plus whatever the
    manager adds for "keep the screen the user just came from". Everything else
    that is not the target is unmounted: releasing those widgets is the whole
    point of the manager.
    """
    mounted_set = frozenset(mounted)
    stay = keep_alive | {target}
    to_unmount = tuple(sorted(module for module in mounted_set if module not in stay))
    return SwitchPlan(
        target=target,
        to_mount=target not in mounted_set,
        to_unmount=to_unmount,
    )


class LazyScreenManager:
    """Mount module screens on demand, unmount the ones left behind."""

    def __init__(
        self,
        host: ScreenHost,
        *,
        registry: Callable[[str], type | None],
        keep_alive: frozenset[str] = frozenset(),
        keep_recent: int = 0,
        reload: Callable[[str, Any], Awaitable[None]] | None = None,
    ) -> None:
        self._host = host
        self._registry = registry
        self._keep_alive = keep_alive
        #: How many recently visited screens to keep mounted. Measured cost of a
        #: mounted screen: ~50-110 ms on *every* action (an idle sweep per
        #: widget), against ~600-1100 ms to mount it again after a switch. One
        #: spare screen buys instant switching back and forth; raise it only
        #: with numbers in hand.
        self._keep_recent = max(0, keep_recent)
        self._recent: list[str] = []
        self._reload = reload
        self._stale: set[str] = set()
        self._lock = asyncio.Lock()
        #: Module ids mounted by this manager (the host is the source of truth,
        #: this is only used for logging and for cheap ``is_mounted`` checks).
        self._mounted: set[str] = set()

    # ── Queries ───────────────────────────────────────────────────────────

    @property
    def stale_modules(self) -> frozenset[str]:
        """Modules that are not on screen and need a reload when they come back."""
        return frozenset(self._stale)

    def is_mounted(self, module_id: str) -> bool:
        return module_id in self._host.mounted_modules()

    def screen(self, module_id: str) -> Any | None:
        """Mounted screen widget, or None. Never mounts, never raises."""
        return self._host.get_module(module_id)

    def show(self, module_id: str) -> None:
        """Reveal an already-mounted module: no mount, no reload, no unmount.

        The fast path of a switch — coming back to a screen that is still in the
        DOM costs one visibility change.
        """
        self._host.show_module(module_id)

    # ── Staleness ─────────────────────────────────────────────────────────

    def mark_stale(self, module_id: str) -> None:
        """Remember that *module_id* must reload from storage before it is shown.

        Used on a project switch: screens that are not mounted cannot be
        reloaded right away, so the reload is deferred to the next mount.
        """
        self._stale.add(module_id)
        logger.debug("screens: %s marked stale (reload on next mount)", module_id)

    def clear_stale(self) -> None:
        self._stale.clear()

    # ── Transitions ───────────────────────────────────────────────────────

    async def ensure(self, module_id: str) -> Any | None:
        """Mount *module_id* if it is not mounted — **without showing it**.

        This is the "get-or-mount" half of `activate()`, for background callers:
        the `--url` seed has to create the Target screen to pre-fill it, and
        sending a request from a context menu has to reach a screen the user has
        not opened. Showing the screen from those paths was a real bug: at
        startup the Target module appeared on top of the Dashboard (T-031).

        Deliberately does not touch the visible module, the visit history or the
        unmount plan: a background mount must not evict what the user is looking
        at.
        """
        async with self._lock:
            if self._registry(module_id) is None:
                logger.warning("screens: %s has no registered screen class", module_id)
                return None
            screen = self._host.get_module(module_id)
            if screen is not None:
                return screen
            screen = await self._host.mount_module(module_id, self._registry(module_id))  # type: ignore[arg-type]
            self._mounted.add(module_id)
            logger.debug("screens: mounted %s in the background (not shown)", module_id)
            await self._replay_reload(module_id, screen)
            return self._host.get_module(module_id)

    async def activate(self, module_id: str) -> Any | None:
        """Make *module_id* visible, mounting it first if needed.

        Returns the screen widget, or None when the module has no registered
        screen class (the caller decides how to tell the user).
        """
        async with self._lock:
            if self._registry(module_id) is None:
                logger.warning("screens: %s has no registered screen class", module_id)
                return None
            if not self._recent:
                # The start screen was mounted by the app's compose(), not by us:
                # seed the visit history with it so `keep_recent` can protect it.
                self._recent = sorted(self._host.mounted_modules())
            plan = plan_switch(
                module_id,
                self._host.mounted_modules(),
                keep_alive=self._keep_alive | frozenset(self._recent[: self._keep_recent]),
            )
            if plan.to_mount:
                screen = await self._host.mount_module(module_id, self._registry(module_id))  # type: ignore[arg-type]
                self._mounted.add(module_id)
                logger.debug("screens: mounted %s", module_id)
                await self._replay_reload(module_id, screen)
            self._host.show_module(module_id)
            # Unmount *after* the new screen is visible: taking the current screen
            # away first would leave the switcher pointing at a child that no
            # longer exists for a frame, and the user would see a blank flash.
            for victim in plan.to_unmount:
                await self._host.unmount_module(victim)
                self._mounted.discard(victim)
                logger.debug("screens: unmounted %s", victim)
            self._remember(module_id)
            return self._host.get_module(module_id)

    def _remember(self, module_id: str) -> None:
        """Track visit order, most recent first, for the keep-recent policy."""
        if module_id in self._recent:
            self._recent.remove(module_id)
        self._recent.insert(0, module_id)
        del self._recent[50:]  # the history only needs to be longer than keep_recent

    async def _replay_reload(self, module_id: str, screen: Any) -> None:
        """Refresh a freshly mounted screen if it went stale while unmounted."""
        if module_id not in self._stale or self._reload is None:
            return
        try:
            await self._reload(module_id, screen)
        except Exception:
            # The screen is on, but with data from the previous project. Keep it
            # stale so the next attempt retries, and say so loudly: silently
            # showing another project's rows is the worst of both worlds.
            logger.error("screens: %s reload after mount failed", module_id, exc_info=True)
            return
        self._stale.discard(module_id)
