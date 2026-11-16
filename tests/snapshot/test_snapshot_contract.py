"""Эталоны принадлежат тестам, которые их читают (F-031/F-032).

Сравнивается целый экран, поэтому устаревший эталон неотличим от настоящей
визуальной регрессии: тесты молчали месяцами, когда в панели модулей появилась
вкладка «Recon», и никто не пересоздал baseline.

Три дешёвых инварианта держат каталог честным:

* у каждого теста есть эталон, и у каждого эталона есть тест — осиротевший файл
  это удалённый или переименованный тест, то есть молча ужавшееся покрытие;
* эталоны не являются побайтовыми копиями друг друга — скопированный эталон
  проходил бы вечно;
* в каждом эталоне видно замороженные часы (`12:00:00`). Это проверка не
  библиотеки, а шва: время в статус-баре не вырезается регуляркой, поэтому
  изменение формата времени сломает эталон, как и должно.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SNAP_DIR = Path(__file__).resolve().parent / "__snapshots__" / "test_screens"
_TEST_FILE = Path(__file__).resolve().parent / "test_screens.py"

#: Время замороженных часов из tests/snapshot/helpers.py.
_FROZEN_TIME = "12:00:00"


def _test_names() -> set[str]:
    """Имена тестов, объявленных в test_screens.py."""
    source = _TEST_FILE.read_text(encoding="utf-8")
    return set(re.findall(r"^def (test_\w+)\(", source, re.M))


def _baseline_names() -> set[str]:
    """Имена эталонов на диске (без расширения .raw)."""
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
    """Время не вырезается из снимка: шов часов должен быть виден в эталоне."""
    without_clock = []
    for path in sorted(_SNAP_DIR.glob("*.raw")):
        if _FROZEN_TIME not in path.read_text(encoding="utf-8"):
            without_clock.append(path.stem)
    assert not without_clock, (
        "в эталоне нет замороженных часов — значит время либо нормализуется из "
        f"SVG, либо шов PentoolApp(now=...) перестал работать: {without_clock}"
    )
