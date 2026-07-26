"""Snapshot infrastructure without pytest-textual-snapshot.

Principle:
- Snapshots are stored in tests/snapshot/snaps/*.svg
- First run: baseline is created automatically, test passes
- Subsequent runs: SVG is compared to baseline byte by byte
- pytest --snapshot-update: force update baseline

Always use size=(200, 50) — full window without clipping.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SNAPS_DIR = Path(__file__).parent / "snaps"
SNAPS_DIR.mkdir(exist_ok=True)

# Patterns removed before comparison (unstable values)
_UNSTABLE_PATTERNS = [
    # Unique terminal class hash — changes every run
    (re.compile(r'terminal-\d+-'), 'terminal-HASH-'),
    # Date/time in title if present
    (re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'), 'TIMESTAMP'),
    # Time HH:MM:SS and HH:MM in SVG text (dynamic UI values)
    (re.compile(r'\d{2}:\d{2}:\d{2}'), 'HH:MM:SS'),
    (re.compile(r'\b\d{2}:\d{2}\b'), 'HH:MM'),
    # Any path /home/... and /tmp/...
    (re.compile(r'/(?:home|tmp)/\S+'), '/PATH'),
    # textLength — may change due to different terminal content
    (re.compile(r'textLength="[\d.]+"'), 'textLength="X"'),
    # Entire line with terminal-screen content (unstable bash output)
    (re.compile(r'(?<=>)bash[^<]*'), 'bash...'),
    # Style CSS classes — may differ in count/order for different content
    (re.compile(r'\.terminal-HASH-r\d+ \{ [^}]+ \}'), '.terminal-HASH-rX { STYLE }'),
    # HTML entities and escape characters in terminal output
    (re.compile(r'&#\d+;'), 'CHAR'),
]


def _normalize(svg: str) -> str:
    """Remove unstable parts from SVG before comparison."""
    for pattern, replacement in _UNSTABLE_PATTERNS:
        svg = pattern.sub(replacement, svg)
    return svg


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


def _make_diff(baseline: str, actual: str, context: int = 3) -> str:
    """Show first differences between two SVG strings."""
    b_lines = baseline.splitlines()
    a_lines = actual.splitlines()
    diffs = []
    for i, (b, a) in enumerate(zip(b_lines, a_lines)):
        if b != a:
            start = max(0, i - context)
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
            snap_path.write_text(normalized, encoding="utf-8")
            action = "updated" if snap_path.exists() else "created"
            pytest.skip(f"Snapshot {action}: {snap_path.name}")
            return

        baseline = snap_path.read_text(encoding="utf-8")
        if normalized != baseline:
            raise SnapshotMismatch(name, snap_path, normalized, baseline)

    return _assert


def pytest_addoption(parser):
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        default=False,
        help="Update baseline SVG snapshots.",
    )
