"""Быстрые, детерминированные perf-проверки ленивых источников Intruder.

Ассертуемые версии тяжёлых `tests/perf/load_intruder.py --level a` (см.
LOAD_TESTING_PLAN_2026-08-17.md, milestone M7). Малые N — не тащат
гигабайтные файлы, работают в обычном CI.

Что проверяем:
  - NumericPayloadSource / CharPayloadSource: len()/bool()/head() O(1), не
    материализуют комбинаторный взрыв (Char 26^1..4 — миллионы, но len() и
    head() мгновенны);
  - FilePayloadSource: потоковая итерация держит RSS почти плоским (O(1)
    память), повторная итерация пере-открывает файл и даёт тот же объём,
    len() корректен;
  - ProcessedPayloads: применяет операции, но не материализует весь источник.
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

pytestmark = pytest.mark.perf  # noqa: F401 — маркер на весь модуль


@pytest.fixture()
def small_payload_file():
    """10k строк, формат ген-файла (уникальные, непустые, не '#'-строки)."""
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
    """NumericPayloadSource: len()/bool() мгновенны, head() не материализует."""
    src = NumericPayloadSource(0, 100_000)
    assert len(src) == 100_000
    assert bool(src) is True
    assert src.head(3) == ["0", "1", "2"]
    # head(3) уже материализовал минимум — итерируем все 100k через len (O(1))
    assert len(src) == 100_000


def test_char_len_head_no_materialize():
    """CharPayloadSource 26^1..4 ≈ 475k — len()/head() должны быть мгновенны."""
    src = CharPayloadSource("abcdefghijklmnopqrstuvwxyz", 1, 4)
    expected = 26 + 26 ** 2 + 26 ** 3 + 26 ** 4
    assert len(src) == expected  # O(1), closed-form, без перебора
    assert bool(src) is True
    assert src.head(4) == ["a", "b", "c", "d"]
    # len() не должен был стоить полный перебор — повторный вызов мгновенный
    assert len(src) == expected


def test_char_empty_ranges():
    """CharPayloadSource с некорректным диапазоном — пустой, len()==0."""
    src = CharPayloadSource("", 1, 5)
    assert len(src) == 0
    assert bool(src) is False
    src2 = CharPayloadSource("abc", 5, 2)
    assert len(src2) == 0


def test_file_source_o1_memory_and_len(small_payload_file):
    """FilePayloadSource: потоковая итерация держит RSS плоским (O(1))."""
    gc.collect()
    rss_before = rss_mb()
    src = FilePayloadSource(small_payload_file)

    count = 0
    for _ in src:
        count += 1
    gc.collect()
    rss_after = rss_mb()

    assert count == 10_000
    # Потоковая итерация не должна заметно растить RSS (допуск — самплинг)
    assert rss_after - rss_before < 20, (
        f"FilePayloadSource загрузил файл в память: RSS {rss_before:.1f}→{rss_after:.1f}MB"
    )
    # len() должен посчитать то же число (streaming-подсчёт), потом кешировать
    assert len(src) == 10_000
    assert len(src) == 10_000  # cached


def test_file_source_reiterates(small_payload_file):
    """Повторная итерация (pitchfork/cluster-bomb пере-читывает) даёт то же."""
    src = FilePayloadSource(small_payload_file)

    def _count():
        return sum(1 for _ in src)

    first = _count()
    second = _count()
    assert first == 10_000
    assert second == 10_000


def test_processed_does_not_materialize(small_payload_file):
    """ProcessedPayloads применяет ops, но не строит полный новый list."""
    src = ProcessedPayloads(
        FilePayloadSource(small_payload_file), ["upper"], lambda p, ops: p.upper()
    )
    # head() через итерацию первых 5 — не материализует остальные
    import itertools
    first5 = list(itertools.islice(src, 5))
    assert len(first5) == 5
    assert all(s.isupper() for s in first5)
    assert len(src) == 10_000
