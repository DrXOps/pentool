"""Гвард логирования: проверка самого гварда, а не репозитория.

Правило (`tools/check_logging_policy.py`): внутри функции, чьё имя означает
работу с данными (`save`/`load`/`restore`/`apply`/…), широкий `except` обязан
либо пробрасывать исключение, либо писать в лог `warning`+ с трейсбеком.

Тесты проверяют три вещи, каждая из которых уже подводила в этом репозитории:

* правило действительно ловит нарушение (иначе гвард «зелёный и пустой»);
* правило не срабатывает на законных формах — `raise`, `logger.exception`,
  `exc_info=True`, явная прагма `# logging-ok: причина`;
* косметическая функция (`_apply_theme`) не попадает под правило, хотя в её
  имени есть глагол `apply`.

Плюс проверяется, что базовая линия на диске соответствует коду: иначе счётчик
разъедется с реальностью и трещотка начнёт врать в обе стороны.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import check_logging_policy as policy  # noqa: E402


def _count(source: str) -> int:
    return policy.count_violations(ast.parse(source), source)


def test_silent_handler_in_a_data_path_is_caught() -> None:
    source = """
def save_settings(values):
    try:
        write(values)
    except Exception:
        return False
"""
    assert _count(source) == 1


def test_debug_only_handler_in_a_data_path_is_caught() -> None:
    """`debug` — не честный лог: в обычном журнале причины не видно."""
    source = """
def _restore_tab(state):
    try:
        apply(state)
    except Exception as exc:
        logger.debug("restore failed: %s", exc)
"""
    assert _count(source) == 1


@pytest.mark.parametrize(
    "body",
    [
        "        raise",
        "        logger.exception('save failed')",
        "        logger.warning('save failed', exc_info=True)",
        "        logger.error('save failed', exc_info=True)",
    ],
)
def test_honest_forms_are_accepted(body: str) -> None:
    source = f"""
def save_tab(state):
    try:
        write(state)
    except Exception:
{body}
"""
    assert _count(source) == 0


def test_pragma_silences_the_handler_explicitly() -> None:
    source = """
def save_tab(state):
    try:
        write(state)
    except Exception:  # logging-ok: файл необязательный, шум в логе вреднее
        return
"""
    assert _count(source) == 0


def test_cosmetic_function_is_out_of_scope() -> None:
    """`_apply_theme` задевает глагол `apply`, но данных не касается."""
    source = """
def _apply_theme(name):
    try:
        set_theme(name)
    except Exception:
        pass
"""
    assert _count(source) == 0


def test_narrow_exception_is_out_of_scope() -> None:
    source = """
def save_tab(state):
    try:
        write(state)
    except OSError:
        return
"""
    assert _count(source) == 0


def test_baseline_matches_the_repository() -> None:
    """Базовая линия не должна врать: иначе трещотка пропустит рост."""
    baseline_path = ROOT / "tools" / "logging_policy_baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = policy.scan()
    grown = {path: (baseline.get(path, 0), n) for path, n in current.items() if n > baseline.get(path, 0)}
    assert not grown, f"долг вырос мимо базовой линии: {grown} — запустите check_logging_policy.py"
