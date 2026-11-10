"""ADR-6 ratchet: silent ``except Exception: pass`` must not grow.

``tools/check_silent_except.py`` freezes the per-file count of handlers that
swallow an exception without logging. Hundreds of historical breaches stay (the
policy fixes them at next touch), but a new one fails the check. These tests
prove both halves: the repository baseline holds, and a planted handler is
counted.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_TOOL = _ROOT / "tools" / "check_silent_except.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("check_silent_except", _TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_not_exceeded() -> None:
    result = subprocess.run([sys.executable, str(_TOOL)], cwd=_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, "a new silent `except Exception: pass` was added (ADR-6):\n" + result.stderr


def test_silent_and_logged_handlers_are_distinguished() -> None:
    import ast

    tool = _load_tool()

    def count(source: str) -> int:
        return tool.count_silent(ast.parse(source))

    assert count("try:\n    a()\nexcept Exception:\n    pass\n") == 1
    assert count("try:\n    a()\nexcept Exception:\n    ...\n") == 1
    # Logged or handled handlers are not silent.
    assert count("try:\n    a()\nexcept Exception:\n    logger.exception('x')\n") == 0
    assert count("try:\n    a()\nexcept Exception:\n    raise\n") == 0
    # Narrow exceptions are not the blind-except problem this ratchet tracks.
    assert count("try:\n    a()\nexcept ValueError:\n    pass\n") == 0
