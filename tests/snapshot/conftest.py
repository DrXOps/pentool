"""Snapshot infrastructure without pytest-textual-snapshot.

Principle:
- Snapshots are stored in tests/snapshot/snaps/*.svg
- First run: baseline is created automatically, test passes
- Subsequent runs: SVG is compared to baseline byte by byte
- pytest --snapshot-update: force update baseline

Always use size=(200, 50) — full window without clipping.

Determinism is bought at the source, not by erasing pixels: the app runs on a
frozen clock (``PentoolApp(now=...)``), and a screenshot is taken only when
the screen has stopped changing (``settle``). Both exist because the previous
layer normalised timestamps and hashed terminal ids out of the SVG, which hid
real regressions — a change to the time format or to a colour class was
invisible by construction.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SNAPS_DIR = Path(__file__).parent / "snaps"
SNAPS_DIR.mkdir(exist_ok=True)

# Patterns removed before comparison. Deliberately short: every entry here is
# a class of regression the baseline can no longer catch. The old list also
# erased timestamps, colour rules (`.terminal-HASH-rN { … }` → `STYLE`),
# character entities (`&#160;` → `CHAR`) and anything containing the word
# "bash" — so a colour change, a broken glyph or a wrong space width was
# invisible. The clock and the mount race are fixed at the source instead.
_UNSTABLE_PATTERNS = [
    # Rich derives this id from an adler32 of the rendered segments plus the
    # title, so it changes with any content change. It is an internal class
    # name, not a pixel, and its value carries no meaning for a reader of the
    # baseline.
    (re.compile(r"terminal-\d+-"), "terminal-HASH-"),
]


def _normalize(svg: str) -> str:
    """Replace the one id that carries no visual meaning."""
    for pattern, replacement in _UNSTABLE_PATTERNS:
        svg = pattern.sub(replacement, svg)
    return svg


async def wait_for(pilot, predicate, *, frames: int = 60, what: str = "condition") -> None:
    """Wait until ``predicate()`` holds, frame by frame.

    The suite used to take a screenshot after a guessed number of
    ``pilot.pause()`` calls, so it captured whatever happened to be on screen
    at that instant. ``test_repeater_screen`` failed intermittently for exactly
    this reason: the tab body is built through a chain of
    ``call_after_refresh`` callbacks, and the request editor receives its text
    several frames after the module bar and the tab strip settle. Half the runs
    photographed an empty editor, half a loaded one — both genuine frames, only
    one of them matching the baseline.

    Waiting on a named condition states which frame the baseline is supposed
    to represent. A screen that never reaches it fails with the predicate name
    instead of silently committing an empty baseline.
    """
    for _ in range(frames):
        if predicate():
            return
        await pilot.pause()
    raise AssertionError(f"{what} did not become true within {frames} frames")


async def settle(app, pilot, *, ready=None, quiet: int = 3, frames: int = 60, what: str = "screen") -> str:
    """Screenshot the app once *ready* holds and the pixels stopped changing.

    Two conditions, both necessary:

    * ``ready`` — the screen really shows what the baseline depicts. Pixel
      quiescence alone is not enough: an unmounted tab body is perfectly
      still, so a "has anything changed?" poll returns immediately and
      photographs the wrong frame.
    * ``quiet`` consecutive identical exports — no animation, timer repaint or
      late layout is mid-flight, which would otherwise produce a screenshot
      taken halfway through a transition.
    """
    if ready is not None:
        await wait_for(pilot, ready, frames=frames, what=f"{what} readiness")
    previous = None
    stable = 0
    for _ in range(frames):
        await pilot.pause()
        current = app.export_screenshot()
        stable = stable + 1 if current == previous else 0
        if stable >= quiet:
            return current
        previous = current
    raise AssertionError(
        f"{what} never held still for {quiet} frames in {frames} — a timer or animation is still running"
    )


class SnapshotMismatch(AssertionError):
    """Snapshot does not match baseline."""

    def __init__(self, name: str, baseline_path: Path, actual: str, baseline: str) -> None:
        diff_lines = _make_diff(baseline, actual)
        super().__init__(
            f"\nSnapshot mismatch: '{name}'\n"
            f"Baseline: {baseline_path}\n"
            f"Run with --snapshot-update to accept new snapshot.\n\n"
            f"First differences:\n{diff_lines}"
        )


def _make_diff(baseline: str, actual: str) -> str:
    """Show the first differing lines between two SVG strings.

    Only mismatching lines are reported: an SVG line is a whole row of rects or
    a whole text run, so a ±one-character change already shows as a full line
    and surrounding rows add nothing but noise.
    """
    b_lines = baseline.splitlines()
    a_lines = actual.splitlines()
    diffs = []
    for i, (b, a) in enumerate(zip(b_lines, a_lines)):
        if b != a:
            diffs.append(f"  Line {i + 1}:")
            diffs.append(f"  - {b[:120]}")
            diffs.append(f"  + {a[:120]}")
            if len(diffs) > 30:
                diffs.append("  ... (truncated)")
                break
    if len(b_lines) != len(a_lines):
        diffs.append(f"  Line count: baseline={len(b_lines)}, actual={len(a_lines)}")
    return "\n".join(diffs) if diffs else "  (no line-level diff found)"


@pytest.fixture
def assert_snapshot(request):
    """Fixture for snapshot SVG comparison.

    Usage:
        async def test_foo(assert_snapshot):
            svg = app.export_screenshot()
            assert_snapshot(svg, "foo")

    Parameters:
        svg: str — output of app.export_screenshot()
        name: str — file name (without .svg)
    """
    update_mode = request.config.getoption("--snapshot-update", default=False)

    def _assert(svg: str, name: str) -> None:
        snap_path = SNAPS_DIR / f"{name}.svg"
        normalized = _normalize(svg)

        if update_mode or not snap_path.exists():
            # ``exists()`` has to be read BEFORE writing: after write_text() it
            # is always true and every run reported "updated", including the
            # first one that actually created the file.
            existed = snap_path.exists()
            snap_path.write_text(normalized, encoding="utf-8")
            pytest.skip(f"Snapshot {'updated' if existed else 'created'}: {snap_path.name}")
            return

        baseline = snap_path.read_text(encoding="utf-8")
        if normalized != baseline:
            raise SnapshotMismatch(name, snap_path, normalized, baseline)

    return _assert


def pytest_addoption(parser):
    # Idempotent: pytest may import this conftest module more than once during
    # collection (under `tests.snapshot.conftest` and a bare `conftest` alias),
    # which makes argparse fail with "conflicting option string". Registering
    # only once keeps a single --snapshot-update flag.
    try:
        parser.addoption(
            "--snapshot-update",
            action="store_true",
            default=False,
            help="Update baseline SVG snapshots.",
        )
    except (ValueError, Exception):
        # Option already registered by an earlier load of this conftest.
        pass
