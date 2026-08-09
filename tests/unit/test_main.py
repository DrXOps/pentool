"""Unit tests for pentool.__main__.main() — the PRO self-heal-before-exit path.

Regression coverage for the bug where a bare `pentool` launch (no args, no
--unsafe-skip-pro-compat-check) with an incompatible PRO package would
raise SystemExit(1) before ever getting a chance to call
check_and_update_pro_package() — the same function that TUI startup and
`pentool update` use to repair a broken install. That meant a plain
`pentool` invocation could never self-heal, only `pentool license
activate <key>` (or --unsafe-skip-pro-compat-check, which disables PRO
entirely) could recover.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest


def _run_main_with_argv(argv):
    """Run pentool.__main__.main() with a given sys.argv, always short-
    circuiting before it would actually launch the Textual app (patched to
    raise KeyboardInterrupt immediately so main() returns/raises cleanly)."""
    import pentool.__main__ as main_mod

    with patch.object(sys, "argv", argv), \
         patch("pentool.tui.app.PentoolApp") as mock_app_cls:
        mock_app_cls.return_value.run.side_effect = KeyboardInterrupt()
        try:
            main_mod.main()
        except KeyboardInterrupt:
            pass  # expected — this is how we stop short of a real TUI run


class TestMainProSelfHeal:
    def test_incompatible_package_healed_by_redownload_does_not_exit(self, capsys):
        """check_and_update_pro_package() successfully re-downloads →
        main() must proceed to start the TUI instead of exiting."""
        import pentool.core.license as lic_mod

        async def _fake_check(*a, **kw):
            return lic_mod.ProSyncResult(updated=True, warning="")

        with patch("pentool.core.license.is_pro_package_compatible",
                   return_value=(False, "stale metadata")), \
             patch("pentool.core.license.check_and_update_pro_package", _fake_check), \
             patch("pentool.core.crash_reporter.send_first_run_ping"):
            _run_main_with_argv(["pentool"])

        captured = capsys.readouterr()
        assert "re-downloaded successfully" in captured.err

    def test_incompatible_package_healed_with_matching_build_id_does_not_exit(self, capsys):
        """check_and_update_pro_package() returns updated=False, warning=""
        (the case where it just repaired an already-broken package whose
        build_id happened to match the remote) — main() must re-check
        is_pro_package_compatible() and proceed if it now passes, not exit."""
        import pentool.core.license as lic_mod

        async def _fake_check(*a, **kw):
            return lic_mod.ProSyncResult(updated=False, warning="")

        call_count = {"n": 0}

        def _fake_compatible():
            call_count["n"] += 1
            # First call (before self-heal attempt): incompatible.
            # Second call (after self-heal attempt): now compatible.
            return (False, "stale metadata") if call_count["n"] == 1 else (True, "")

        with patch("pentool.core.license.is_pro_package_compatible", side_effect=_fake_compatible), \
             patch("pentool.core.license.check_and_update_pro_package", _fake_check), \
             patch("pentool.core.crash_reporter.send_first_run_ping"):
            _run_main_with_argv(["pentool"])

        # Must not have printed the "doesn't record which version" exit warning.
        captured = capsys.readouterr()
        assert "stale metadata" not in captured.err

    def test_still_incompatible_after_heal_attempt_exits(self, capsys):
        """Self-heal attempt runs but the package is still incompatible
        (e.g. offline, download failed) — must still exit with the warning,
        same as before this fix existed."""
        async def _fake_check(*a, **kw):
            import pentool.core.license as lic_mod
            return lic_mod.ProSyncResult(updated=False, warning="still broken")

        with patch("pentool.core.license.is_pro_package_compatible",
                   return_value=(False, "still broken")), \
             patch("pentool.core.license.check_and_update_pro_package", _fake_check):
            with pytest.raises(SystemExit) as exc_info:
                _run_main_with_argv(["pentool"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "still broken" in captured.err

    def test_self_heal_exception_falls_through_to_original_warning(self, capsys):
        """If the self-heal attempt itself raises (e.g. asyncio.run fails
        in a nested-loop edge case), main() must not crash — it falls back
        to the original warning/exit behavior."""
        with patch("pentool.core.license.is_pro_package_compatible",
                   return_value=(False, "original warning")), \
             patch("pentool.core.license.check_and_update_pro_package",
                   side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc_info:
                _run_main_with_argv(["pentool"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "original warning" in captured.err

    def test_unsafe_flag_still_bypasses_after_failed_heal(self, capsys):
        """--unsafe-skip-pro-compat-check must still work as an escape hatch
        even when the self-heal attempt didn't fix anything."""
        async def _fake_check(*a, **kw):
            import pentool.core.license as lic_mod
            return lic_mod.ProSyncResult(updated=False, warning="still broken")

        with patch("pentool.core.license.is_pro_package_compatible",
                   return_value=(False, "still broken")), \
             patch("pentool.core.license.check_and_update_pro_package", _fake_check), \
             patch("pentool.core.crash_reporter.send_first_run_ping"):
            _run_main_with_argv(["pentool", "--unsafe-skip-pro-compat-check"])

        captured = capsys.readouterr()
        assert "UNSAFE" in captured.err

    def test_compatible_package_never_attempts_heal(self):
        """The common case: package already compatible — no self-heal call
        should even be attempted (nothing to fix)."""
        with patch("pentool.core.license.is_pro_package_compatible",
                   return_value=(True, "")), \
             patch("pentool.core.license.check_and_update_pro_package") as mock_check, \
             patch("pentool.core.crash_reporter.send_first_run_ping"):
            _run_main_with_argv(["pentool"])

        mock_check.assert_not_called()
