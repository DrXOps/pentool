"""The snapshot layer must fail on the things it exists to catch.

``tests/snapshot/conftest.py`` once normalised timestamps, colour rules and
character entities out of the SVG before comparing. That made the baselines
reliable and blind at the same time: a changed time format, a wrong colour or
a broken glyph could not fail a test, because the comparison never saw them.
The clock is frozen at the source now, so the surviving normalisation list has
to stay short — this test states what must remain visible.
"""

from __future__ import annotations

import re

from tests.snapshot.conftest import _UNSTABLE_PATTERNS, _normalize

#: Fragments that must survive normalisation untouched.
_VISIBLE = [
    "12:00:00",  # the clock — frozen by PentoolApp(now=...), not erased
    "fill: #ff0000",  # a colour rule — a palette change must fail the baseline
    "&#160;",  # a character entity — a wrong glyph must fail
    "GET / HTTP/1.1",  # cell text
    'textLength="97.6"',  # cell width — different text width must fail
    "/home/docx/project",  # an absolute path must stay readable in the diff
]


def test_visually_meaningful_content_survives_normalisation() -> None:
    sample = "\n".join(
        [
            '<text class="terminal-12345-r1" textLength="97.6">12:00:00</text>',
            ".terminal-12345-r2 { fill: #ff0000 }",
            "<text>&#160;GET / HTTP/1.1</text>",
            "<title>/home/docx/project</title>",
        ]
    )
    normalized = _normalize(sample)
    for fragment in _VISIBLE:
        assert fragment in normalized, (
            f"normalisation erases {fragment!r} — the baseline stops protecting it. "
            "Fix the source of the instability (frozen clock, settled frame) instead."
        )


def test_normalisation_is_idempotent_and_touches_only_internal_ids() -> None:
    sample = '<text class="terminal-42-r7" textLength="97.6">GET</text>'
    once = _normalize(sample)
    assert once == _normalize(once), "normalisation must be stable under a second pass"
    assert "terminal-42-r7" not in once
    assert "terminal-HASH-r7" in once
    # One pattern, one reason: no broad catch-all crept in.
    assert len(_UNSTABLE_PATTERNS) == 1, (
        "a new normalisation rule hides a class of regression — freeze the value at its source instead: "
        f"{[pattern.pattern for pattern, _ in _UNSTABLE_PATTERNS]}"
    )


def test_clock_is_frozen_in_the_snapshot_suite() -> None:
    """``PentoolApp(now=...)`` is the seam; a real clock would drift per run."""
    from tests.snapshot.test_screens import _FrozenClock

    assert _FrozenClock.now().strftime("%H:%M:%S") == "12:00:00"
    # Other classmethods must keep working — widgets format file mtimes.
    assert _FrozenClock.fromtimestamp(0).year == 1970
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", _FrozenClock.now().strftime("%Y-%m-%d"))
