"""Logging guard: verifying the guard itself, not the repository.

Rule (`tools/check_logging_policy.py`): inside a function whose name implies
working with data (`save`/`load`/`restore`/`apply`/…), a broad `except` must
either re-raise the exception or log at `warning`+ with a traceback.

The tests check three things, each of which has already let this repository down:

* the rule really catches a violation (otherwise the guard is "green and empty");
* the rule does not fire on legitimate forms — `raise`, `logger.exception`,
  `exc_info=True`, the explicit pragma `# logging-ok: reason`;
* a cosmetic function (`_apply_theme`) is out of scope even though its name
  contains the verb `apply`.

It also verifies that the baseline on disk matches the code: otherwise the counter
will drift away from reality and the ratchet will start lying in both directions.
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
    """`debug` is not honest logging: a normal journal does not show the cause."""
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
    """`_apply_theme` does touch the verb `apply`, but it does not touch data."""
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
    """The baseline must not lie: otherwise the ratchet will let growth pass."""
    baseline_path = ROOT / "tools" / "logging_policy_baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = policy.scan()
    grown = {path: (baseline.get(path, 0), n) for path, n in current.items() if n > baseline.get(path, 0)}
    assert not grown, f"долг вырос мимо базовой линии: {grown} — запустите check_logging_policy.py"
