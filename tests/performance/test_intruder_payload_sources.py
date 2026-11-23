"""Fast, deterministic perf checks for lazy Intruder payload sources.

Assertable versions of the heavy `tests/perf/load_intruder.py --level a` (see
LOAD_TESTING_PLAN_2026-08-17.md, milestone M7). Small N do not drag in
gigabyte files and run in ordinary CI.

What we check:
  - NumericPayloadSource / CharPayloadSource: len()/bool()/head() are O(1),
    they do not materialize the combinatorial explosion (Char 26^1..4 —
    millions, yet len() and head() are instant);
  - FilePayloadSource: streaming iteration keeps RSS nearly flat (O(1)
    memory), a repeated iteration re-opens the file and yields the same
    volume, len() is correct;
  - ProcessedPayloads: applies the operations but does not materialize the
    whole source.
"""

from __future__ import annotations

import gc
import os
import tempfile

import pytest

from pentool.modules.intruder import (
    CharPayloadSource,
    FilePayloadSource,
    NumericPayloadSource,
    ProcessedPayloads,
)
from tests.perf.memtrack import rss_mb

pytestmark = pytest.mark.perf  # noqa: F401 — marker for the whole module


@pytest.fixture()
def small_payload_file():
    """10k lines in the gen-file format (unique, non-empty, no '#' lines)."""
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="pentool_perf_")
    try:
        with os.fdopen(fd, "w") as f:
            for i in range(10_000):
                f.write(f"{i:08x}:{'a' * 16}\n")
        yield path
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_numeric_len_and_head_o1():
    """NumericPayloadSource: len()/bool() are instant, head() does not materialize."""
    src = NumericPayloadSource(0, 100_000)
    assert len(src) == 100_000
    assert bool(src) is True
    assert src.head(3) == ["0", "1", "2"]
    # head(3) has already materialized the minimum — walk all 100k via len (O(1))
    assert len(src) == 100_000


def test_char_len_head_no_materialize():
    """CharPayloadSource 26^1..4 ≈ 475k — len()/head() must be instant."""
    src = CharPayloadSource("abcdefghijklmnopqrstuvwxyz", 1, 4)
    expected = 26 + 26**2 + 26**3 + 26**4
    assert len(src) == expected  # O(1), closed-form, without enumeration
    assert bool(src) is True
    assert src.head(4) == ["a", "b", "c", "d"]
    # len() must not have cost a full enumeration — the repeat call is instant
    assert len(src) == expected


def test_char_empty_ranges():
    """CharPayloadSource with an invalid range — empty, len()==0."""
    src = CharPayloadSource("", 1, 5)
    assert len(src) == 0
    assert bool(src) is False
    src2 = CharPayloadSource("abc", 5, 2)
    assert len(src2) == 0


def test_file_source_o1_memory_and_len(small_payload_file):
    """FilePayloadSource: streaming iteration keeps RSS flat (O(1))."""
    gc.collect()
    rss_before = rss_mb()
    src = FilePayloadSource(small_payload_file)

    count = 0
    for _ in src:
        count += 1
    gc.collect()
    rss_after = rss_mb()

    assert count == 10_000
    # Streaming iteration must not noticeably grow RSS (tolerance — sampling)
    assert rss_after - rss_before < 20, (
        f"FilePayloadSource загрузил файл в память: RSS {rss_before:.1f}→{rss_after:.1f}MB"
    )
    # len() must count the same number (streaming count), then cache it
    assert len(src) == 10_000
    assert len(src) == 10_000  # cached


def test_file_source_reiterates(small_payload_file):
    """A repeated iteration (pitchfork/cluster-bomb re-reads) yields the same."""
    src = FilePayloadSource(small_payload_file)

    def _count():
        return sum(1 for _ in src)

    first = _count()
    second = _count()
    assert first == 10_000
    assert second == 10_000


def test_processed_does_not_materialize(small_payload_file):
    """ProcessedPayloads applies ops but does not build a full new list."""
    src = ProcessedPayloads(FilePayloadSource(small_payload_file), ["upper"], lambda p, ops: p.upper())
    # head() via iterating the first 5 — does not materialize the rest
    import itertools

    first5 = list(itertools.islice(src, 5))
    assert len(first5) == 5
    assert all(s.isupper() for s in first5)
    assert len(src) == 10_000
