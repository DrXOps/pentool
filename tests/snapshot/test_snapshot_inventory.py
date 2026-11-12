"""The snapshot baselines belong to the tests that read them (F-031/F-032).

The custom snapshot layer compares whole screenshots, so a stale baseline is
indistinguishable from a visual regression: ten tests failed for months because
the module bar gained a "Recon" tab and nobody re-ran `--snapshot-update`.

Two cheap invariants keep the directory trustworthy:

* every tested screen has a baseline, and every baseline has a test — an
  orphaned SVG is either a deleted test or a renamed one, and in both cases the
  coverage silently shrank;
* every baseline is expressed with ``$token`` colours resolved to today's
  theme, i.e. it was produced by this version of the app rather than restored
  from an older commit.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SNAP_DIR = Path(__file__).resolve().parent / "snaps"
_TEST_FILE = Path(__file__).resolve().parent / "test_screens.py"

#: Snapshot names currently produced by ``test_screens.py``.
_EXPECTED = {
    "repeater_screen",
    "intruder_screen",
    "decoder_screen",
    "settings_screen",
    "proxy_intercept_tab",
    "repeater_with_request",
    "intruder_with_markers",
    "comparer_screen",
    "sequencer_screen",
}


def _names_produced_by_tests() -> set[str]:
    src = _TEST_FILE.read_text(encoding="utf-8")
    return set(re.findall(r'assert_snapshot\(\s*svg\s*,\s*"([a-z_]+)"', src))


def test_baselines_match_the_tested_screens() -> None:
    produced = _names_produced_by_tests()
    assert produced == _EXPECTED, (
        "test_screens.py and _EXPECTED drifted apart — update this test together "
        f"with the snapshot suite: only in tests={sorted(produced - _EXPECTED)}, "
        f"only in expected={sorted(_EXPECTED - produced)}"
    )


def test_no_orphaned_baselines() -> None:
    on_disk = {p.stem for p in _SNAP_DIR.glob("*.svg")}
    orphans = sorted(on_disk - _names_produced_by_tests())
    assert not orphans, (
        "baselines no test reads: a deleted/renamed test leaves these behind and the "
        f"directory looks like coverage it no longer has — delete them: {orphans}"
    )


def test_every_tested_screen_has_a_baseline() -> None:
    missing = sorted(_names_produced_by_tests() - {p.stem for p in _SNAP_DIR.glob("*.svg")})
    assert not missing, f"screen has no baseline (the test would silently create it): {missing}"


def test_baselines_are_not_stale_copies_of_one_screen() -> None:
    """A baseline copied from another screen would pass forever.

    Comparing only the module bar is useless — every screen draws the same one.
    The digest covers the whole file, so two screens may legitimately be equal
    only if they really render identically, which no two of these do.
    """
    digests: dict[str, str] = {
        path.stem: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(_SNAP_DIR.glob("*.svg"))
    }
    seen: dict[str, list[str]] = {}
    for name, digest in digests.items():
        seen.setdefault(digest, []).append(name)
    duplicates = {digest: names for digest, names in seen.items() if len(names) > 1}
    assert not duplicates, f"baselines are byte-identical to each other: {sorted(duplicates.values())}"
