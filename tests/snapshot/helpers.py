"""Helpers for the screenshot suite.

Comparing and storing reference images is handled by `pytest-textual-snapshot` (F-032).
Only what the library cannot know lives here:

* **Frozen clock.** The status bar prints the time once per second, so two runs
  would never match byte for byte. The app receives the clock through the
  `PentoolApp(now=...)` seam; you cannot strip the time out of the SVG with a
  regex — a genuine time-format regression would disappear along with it.
* **Waiting for readiness and quiet.** The frame for the reference image is taken
  once the screen has already been assembled (`ready`) and has stopped changing
  (`quiet` identical exports in a row). A screenshot after a guessed number of
  `pilot.pause()` calls is a lottery: the body of the Repeater tab is assembled by
  a chain of `call_after_refresh`, and half of the runs photographed an empty
  editor.
"""

from __future__ import annotations

from datetime import datetime

#: Full window: no widget is clipped.
SNAP_SIZE = (200, 50)


class FrozenClock(datetime):
    """A ``datetime`` whose ``now()`` is fixed.

    Subclassing rather than monkeypatching the module: the remaining classmethods
    (`fromtimestamp`, `strptime`) keep working, so widgets that print file
    mtimes behave as they do in production.
    """

    @classmethod
    def now(cls, tz=None) -> datetime:
        return cls(2026, 1, 1, 12, 0, 0)


def make_app():
    """A fresh app on the frozen clock."""
    from pentool.tui.app import PentoolApp

    return PentoolApp(now=FrozenClock.now)


async def wait_for(pilot, predicate, *, frames: int = 60, what: str = "condition") -> None:
    """Wait for ``predicate()`` to hold, frame by frame."""
    for _ in range(frames):
        if predicate():
            return
        await pilot.pause()
    raise AssertionError(f"{what} did not become true within {frames} frames")


async def settle(pilot, ready=None, *, quiet: int = 3, frames: int = 60, what: str = "screen") -> None:
    """Wait for a frame that is worthy of becoming the reference.

    Both conditions are required. Readiness (`ready`) — because a motionless screen
    does not yet mean a correct one: an unassembled tab body is motionless too.
    Quiet (`quiet` identical exports in a row) — because otherwise the snapshot
    lands in the middle of an animation or a late layout.
    """
    if ready is not None:
        await wait_for(pilot, ready, frames=frames, what=f"{what} readiness")
    app = pilot.app
    previous = None
    stable = 0
    for _ in range(frames):
        await pilot.pause()
        current = app.export_screenshot()
        stable = stable + 1 if current == previous else 0
        if stable >= quiet:
            return
        previous = current
    raise AssertionError(
        f"{what} never held still for {quiet} frames in {frames} — a timer or animation is still running"
    )
