"""Baselines belong to the tests that read them (F-031/F-032).

A whole screen is compared, so a stale baseline is indistinguishable from a real
visual regression: the tests stayed silent for months when the "Recon" tab
appeared in the modules panel, and nobody regenerated the baseline.

Three cheap invariants keep the catalog honest:

* every test has a baseline, and every baseline has a test — an orphaned file
  means a deleted or renamed test, that is, silently shrunken coverage;
* baselines are not byte-for-byte copies of each other — a copied baseline
  would pass forever;
* every baseline shows the frozen clock (`12:00:00`). This checks not the
  library but the seam: the time in the status bar is not cut out by a regex,
  so a change in the time format breaks the baseline, as it should.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SNAP_DIR = Path(__file__).resolve().parent / "__snapshots__" / "test_screens"
_TEST_FILE = Path(__file__).resolve().parent / "test_screens.py"

#: Frozen clock time from tests/snapshot/helpers.py.
_FROZEN_TIME = "12:00:00"


def _test_names() -> set[str]:
    """Names of the tests declared in test_screens.py."""
    source = _TEST_FILE.read_text(encoding="utf-8")
    return set(re.findall(r"^def (test_\w+)\(", source, re.M))


def _baseline_names() -> set[str]:
    """Names of the baselines on disk (without the .raw extension)."""
    return {path.stem for path in _SNAP_DIR.glob("*.raw")}


def test_every_test_has_a_baseline() -> None:
    missing = sorted(_test_names() - _baseline_names())
    assert not missing, f"у теста нет эталона — прогон молча создаст его: {missing}"


def test_no_orphaned_baselines() -> None:
    orphans = sorted(_baseline_names() - _test_names())
    assert not orphans, (
        "эталоны, которые никто не читает: удалённый или переименованный тест "
        f"оставил их, а каталог выглядит как покрытие, которого уже нет — удалить: {orphans}"
    )


def test_baselines_are_not_copies_of_one_screen() -> None:
    digests = {path.stem: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(_SNAP_DIR.glob("*.raw"))}
    seen: dict[str, list[str]] = {}
    for name, digest in digests.items():
        seen.setdefault(digest, []).append(name)
    duplicates = {digest: names for digest, names in seen.items() if len(names) > 1}
    assert not duplicates, f"эталоны побайтово совпадают: {sorted(duplicates.values())}"


def test_baselines_show_the_frozen_clock() -> None:
    """The time is not cut from the snapshot: the clock seam must be visible in the baseline."""
    without_clock = []
    for path in sorted(_SNAP_DIR.glob("*.raw")):
        if _FROZEN_TIME not in path.read_text(encoding="utf-8"):
            without_clock.append(path.stem)
    assert not without_clock, (
        "в эталоне нет замороженных часов — значит время либо нормализуется из "
        f"SVG, либо шов PentoolApp(now=...) перестал работать: {without_clock}"
    )
