"""ADR-6 ratchet: blind ``except Exception`` in ``pentool/`` must not grow.

``tools/check_broad_except.py`` freezes the per-file count of handlers that
catch ``Exception``/``BaseException`` without logging and without re-raising —
the shape ruff reports as ``BLE001`` and the two ADR-6 guards do not cover.
The backlog is 585 sites on 92 files; the ratchet lets it shrink and forbids
growth. These tests prove the baseline holds, that the count is ruff's own
verdict rather than a local heuristic, and that ``--update`` only ever lowers.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TOOL = _ROOT / "tools" / "check_broad_except.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("check_broad_except", _TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_baseline(path: Path, counts: dict[str, int]) -> None:
    path.write_text(json.dumps(counts), encoding="utf-8")


def test_baseline_not_exceeded() -> None:
    result = subprocess.run([sys.executable, str(_TOOL)], cwd=_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, (
        "a new blind `except Exception` that neither logs nor re-raises was added (ADR-6):\n" + result.stderr
    )


def test_scan_counts_only_the_shapes_adr6_rejects(tmp_path: Path) -> None:
    """The count must follow ruff: re-raise and logging are the accepted forms."""
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "sample.py").write_text(
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "\n"
        "def swallowed():\n"
        "    try:\n"
        "        a()\n"
        "    except Exception:\n"
        "        return None\n"
        "\n"
        "def swallowed_base():\n"
        "    try:\n"
        "        a()\n"
        "    except BaseException:\n"
        "        flag = True\n"
        "\n"
        "def logged():\n"
        "    try:\n"
        "        a()\n"
        "    except Exception as exc:\n"
        "        logger.exception('boom: %s', exc)\n"
        "\n"
        "def reraised():\n"
        "    try:\n"
        "        a()\n"
        "    except Exception:\n"
        "        raise\n"
        "\n"
        "def narrow():\n"
        "    try:\n"
        "        a()\n"
        "    except ValueError:\n"
        "        return None\n",
        encoding="utf-8",
    )

    tool = _load_tool()
    assert tool.scan(package, tmp_path) == {"pkg/sample.py": 2}


def test_growth_over_baseline_fails(tmp_path: Path, monkeypatch, capsys) -> None:
    tool = _load_tool()
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline, {"pentool/tui/app.py": 1})
    monkeypatch.setattr(tool, "BASELINE", baseline)
    monkeypatch.setattr(tool, "scan", lambda **_kw: {"pentool/tui/app.py": 2})

    assert tool.main([]) == 1
    assert "pentool/tui/app.py: 1 -> 2" in capsys.readouterr().err


def test_shrink_passes_and_update_lowers_but_never_raises(tmp_path: Path, monkeypatch) -> None:
    tool = _load_tool()
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline, {"paid_down.py": 3, "stubborn.py": 1})
    monkeypatch.setattr(tool, "BASELINE", baseline)
    # One file paid down, the other one grew: --update may only tighten.
    monkeypatch.setattr(tool, "scan", lambda **_kw: {"paid_down.py": 1, "stubborn.py": 5})

    assert tool.main(["--update"]) == 0
    assert json.loads(baseline.read_text(encoding="utf-8")) == {"paid_down.py": 1, "stubborn.py": 1}
    # Growth still fails afterwards, so --update cannot be used to launder it.
    monkeypatch.setattr(tool, "scan", lambda **_kw: {"stubborn.py": 2})
    assert tool.main([]) == 1
