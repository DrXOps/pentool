"""Snapshot-инфраструктура без pytest-textual-snapshot.

Принцип:
- Снимки хранятся в tests/snapshot/snaps/*.svg
- Первый запуск: baseline создаётся автоматически, тест проходит
- Повторный запуск: SVG сравнивается с baseline побайтово
- pytest --snapshot-update: принудительно обновить baseline

Всегда используем size=(200, 50) — полное окно без обрезки.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SNAPS_DIR = Path(__file__).parent / "snaps"
SNAPS_DIR.mkdir(exist_ok=True)

# Паттерны, которые убираем перед сравнением (нестабильные значения)
_UNSTABLE_PATTERNS = [
    # Уникальный хэш класса терминала — меняется при каждом запуске
    (re.compile(r'terminal-\d+-'), 'terminal-HASH-'),
    # Дата/время в title если есть
    (re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'), 'TIMESTAMP'),
    # Время HH:MM:SS и HH:MM в SVG-тексте (динамические значения в UI)
    (re.compile(r'\d{2}:\d{2}:\d{2}'), 'HH:MM:SS'),
    (re.compile(r'\b\d{2}:\d{2}\b'), 'HH:MM'),
    # Любой путь /home/... и /tmp/...
    (re.compile(r'/(?:home|tmp)/\S+'), '/PATH'),
    # textLength — может меняться из-за разного контента терминала
    (re.compile(r'textLength="[\d.]+"'), 'textLength="X"'),
    # Вся строка с terminal-screen содержимым (нестабильный bash вывод)
    (re.compile(r'(?<=>)bash[^<]*'), 'bash...'),
    # CSS классы стилей — могут различаться по количеству/порядку при разном контенте
    (re.compile(r'\.terminal-HASH-r\d+ \{ [^}]+ \}'), '.terminal-HASH-rX { STYLE }'),
    # HTML-entities и escape-символы в terminal output
    (re.compile(r'&#\d+;'), 'CHAR'),
]


def _normalize(svg: str) -> str:
    """Убрать нестабильные части SVG перед сравнением."""
    for pattern, replacement in _UNSTABLE_PATTERNS:
        svg = pattern.sub(replacement, svg)
    return svg


class SnapshotMismatch(AssertionError):
    """Снимок не совпадает с baseline."""

    def __init__(self, name: str, baseline_path: Path, actual: str, baseline: str) -> None:
        diff_lines = _make_diff(baseline, actual)
        super().__init__(
            f"\nSnapshot mismatch: '{name}'\n"
            f"Baseline: {baseline_path}\n"
            f"Run with --snapshot-update to accept new snapshot.\n\n"
            f"First differences:\n{diff_lines}"
        )


def _make_diff(baseline: str, actual: str, context: int = 3) -> str:
    """Показать первые отличия между двумя строками SVG."""
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
    """Фикстура для snapshot-сравнения SVG.

    Использование:
        async def test_foo(assert_snapshot):
            svg = app.export_screenshot()
            assert_snapshot(svg, "foo")

    Параметры:
        svg: str — вывод app.export_screenshot()
        name: str — имя файла (без .svg)
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
        help="Обновить baseline SVG-снимки.",
    )
