"""Exit-reason logging in main (pentool/__main__.py).

Guards that a quiet/anon shutdown writes an explicit cause line to
pentool_exit_dump.log, so it's always visible WHY the app exited
(signal/SystemExit, crash exception, or the clean-return path).
"""

from __future__ import annotations

from pathlib import Path

from pentool import __main__ as m


def test_log_exit_reason_writes_marker(tmp_path, monkeypatch):
    monkeypatch.setattr("pentool.core.config.DEFAULT_CONFIG_DIR", tmp_path)
    m._log_exit_reason("crash: RuntimeError: boom")
    log = tmp_path / "pentool_exit_dump.log"
    assert log.exists()
    content = log.read_text()
    assert "EXIT: crash: RuntimeError: boom" in content


def test_log_exit_reason_signal():
    # No config dir override -> writes to real ~/.config; just ensure no raise.
    try:
        m._log_exit_reason("signal/SystemExit")
    except Exception as exc:  # pragma: no cover
        assert False, f"_log_exit_reason raised: {exc}"
