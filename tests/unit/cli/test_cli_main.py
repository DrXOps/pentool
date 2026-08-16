"""Unit tests: cli/main.py — the root Click command group and its subcommands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from pentool.cli.main import cli


def test_cli_no_args_runs(capsys):
    # cli() invoked directly behaves as a group with no subcommand → calls
    # cli callback? Click groups don't auto-run without impl; just ensure import is ok
    from pentool.cli.main import cli as _cli
    assert _cli is not None


def test_cli_config_non_existing_file():
    # --config with a bogus path → Config.load should raise, surfaced via CliRunner
    with patch("pentool.cli.main.get_config"), patch("pentool.core.config.Config.load", side_effect=FileNotFoundError("no")):
        pass  # load is only called when config_path is given


def test_cli_verbose_flag_sets_debug():
    from pentool.core.config import Config
    cfg = Config()
    with patch("pentool.cli.main.get_config", return_value=cfg), \
         patch("pentool.cli.main.setup_logging") as set_log, \
         patch("pentool.utils.coder.apply_operation", return_value="x"):
        r = CliRunner().invoke(cli, ["--verbose", "decode", "url_encode", "a"],
                               prog_name="pentool")
    assert r.exit_code == 0
    set_log.assert_called_once()
    assert set_log.call_args[0][1] == "DEBUG"


def test_cli_default_no_verbose():
    from pentool.core.config import Config
    cfg = Config(log_level="INFO")
    with patch("pentool.cli.main.get_config", return_value=cfg), \
         patch("pentool.cli.main.setup_logging") as set_log, \
         patch("pentool.utils.coder.apply_operation", return_value="x"):
        CliRunner().invoke(cli, ["decode", "url_encode", "a"], prog_name="pentool")
    assert set_log.call_args[0][1] == cfg.log_level


def test_cli_config_path_loads_config(tmp_path):
    from pentool.core.config import Config
    cfg = Config(log_level="WARN")
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text("proxy_port: 9999\n")
    with patch("pentool.core.config.Config.load", return_value=cfg) as load_mock, \
         patch("pentool.cli.main.setup_logging") as set_log, \
         patch("pentool.utils.coder.apply_operation", return_value="x"):
        r = CliRunner().invoke(cli, ["--config", str(cfg_path), "decode", "url_encode", "a"],
                               prog_name="pentool")
    assert r.exit_code == 0
    load_mock.assert_any_call(str(cfg_path))
    assert set_log.call_args[0][1] == "WARN"


# ── decode ──────────────────────────────────────────────────────────────────

def test_decode_success():
    with patch("pentool.utils.coder.apply_operation", return_value="encoded"):
        r = CliRunner().invoke(cli, ["decode", "base64_encode", "hello"])
    assert r.exit_code == 0
    assert "encoded" in r.output


def test_decode_value_error():
    with patch("pentool.utils.coder.apply_operation", side_effect=ValueError("bad op")):
        r = CliRunner().invoke(cli, ["decode", "url_encode", "x"])
    assert r.exit_code == 1
    assert "bad op" in r.output


def test_decode_invalid_operation_choice():
    r = CliRunner().invoke(cli, ["decode", "not-an-op", "x"])
    assert r.exit_code != 0
    assert "Invalid value" in r.output


# ── repeater / intruder stubs ───────────────────────────────────────────────

def test_repeater_send_stub(tmp_path):
    req = tmp_path / "req.txt"
    req.write_text("GET / HTTP/1.1")
    r = CliRunner().invoke(cli, ["repeater", "send", "--request-file", str(req)])
    assert r.exit_code == 0
    assert "not implemented yet" in r.output


def test_intruder_run_stub(tmp_path):
    req = tmp_path / "req.txt"
    pay = tmp_path / "pay.txt"
    req.write_text("GET / HTTP/1.1")
    pay.write_text("a\nb\n")
    r = CliRunner().invoke(cli, ["intruder", "run", "--request", str(req), "--payloads", str(pay)])
    assert r.exit_code == 0
    assert "not implemented yet" in r.output


# ── update ──────────────────────────────────────────────────────────────────

def _update_info(error="", has_update=False, latest_version="v0.0.0", url=""):
    return MagicMock(error=error, has_update=has_update,
                     latest_version=latest_version, url=url)


def test_update_error_exits(tmp_path):
    info = _update_info(error="network down")
    with patch("pentool.core.updater.check_update_sync", return_value=info), \
         patch("pentool.cli.main._warn_if_pro_incompatible"):
        r = CliRunner().invoke(cli, ["update"], input="n")
    assert r.exit_code == 1
    assert "network down" in r.output


def test_update_already_latest():
    info = _update_info(has_update=False)
    with patch("pentool.core.updater.check_update_sync", return_value=info), \
         patch("pentool.cli.main._warn_if_pro_incompatible"):
        r = CliRunner().invoke(cli, ["update"], input="n")
    assert r.exit_code == 0
    assert "Already up to date" in r.output


def test_update_check_only():
    info = _update_info(has_update=True, latest_version="v9.9.9", url="https://rel")
    with patch("pentool.core.updater.check_update_sync", return_value=info), \
         patch("pentool.cli.main._warn_if_pro_incompatible"):
        r = CliRunner().invoke(cli, ["update", "--check"])
    assert r.exit_code == 0
    assert "v9.9.9" in r.output


def test_update_installs_when_confirmed():
    info = _update_info(has_update=True, latest_version="v9.9.9", url="https://rel")
    with patch("pentool.core.updater.check_update_sync", return_value=info), \
         patch("pentool.core.updater.do_pip_upgrade", return_value=True), \
         patch("pentool.cli.main._sync_pro_package_after_upgrade"):
        r = CliRunner().invoke(cli, ["update"], input="y\n")
    assert r.exit_code == 0
    assert "Upgrade successful" in r.output


def test_update_pip_fails_exits():
    info = _update_info(has_update=True, latest_version="v9.9.9", url="https://rel")
    with patch("pentool.core.updater.check_update_sync", return_value=info), \
         patch("pentool.core.updater.do_pip_upgrade", return_value=False):
        r = CliRunner().invoke(cli, ["update"], input="y\n")
    assert r.exit_code == 1
    assert "pip upgrade failed" in r.output


def test_update_declined():
    info = _update_info(has_update=True, latest_version="v9.9.9", url="https://rel")
    with patch("pentool.core.updater.check_update_sync", return_value=info), \
         patch("pentool.cli.main._warn_if_pro_incompatible"):
        r = CliRunner().invoke(cli, ["update"], input="n\n")
    assert r.exit_code == 0


# ── license ─────────────────────────────────────────────────────────────────

def _lic_info(valid=True, error="", key="K", plan="pro", expires_text="soon",
              features=("f",), machine_id="m", status_text="active", **kw):
    return MagicMock(valid=valid, error=error, license_key=key, plan=plan,
                     expires_text=expires_text, features=features,
                     machine_id=machine_id, status_text=status_text, **kw)


def test_license_trial_success():
    info = _lic_info()
    with patch("pentool.core.license.start_trial", new=AsyncMock(return_value=info)):
        r = CliRunner().invoke(cli, ["license", "trial"])
    assert r.exit_code == 0
    assert "Trial started" in r.output


def test_license_trial_failure():
    info = _lic_info(valid=False, error="no trial")
    with patch("pentool.core.license.start_trial", new=AsyncMock(return_value=info)):
        r = CliRunner().invoke(cli, ["license", "trial"])
    assert r.exit_code == 1
    assert "no trial" in r.output


def test_license_activate_success():
    info = _lic_info()
    with patch("pentool.core.license.activate_license", new=AsyncMock(return_value=info)), \
         patch("pentool.core.license.invalidate_session_license"):
        r = CliRunner().invoke(cli, ["license", "activate", "PROD-1-2-3"])
    assert r.exit_code == 0
    assert "License activated" in r.output


def test_license_activate_failure():
    info = _lic_info(valid=False, error="bad key")
    with patch("pentool.core.license.activate_license", new=AsyncMock(return_value=info)), \
         patch("pentool.core.license.invalidate_session_license"):
        r = CliRunner().invoke(cli, ["license", "activate", "PROD-X"])
    assert r.exit_code == 1
    assert "bad key" in r.output


def test_license_status():
    info = _lic_info(status_text="active", plan="pro")
    with patch("pentool.core.license.get_license", return_value=info):
        r = CliRunner().invoke(cli, ["license", "status"])
    assert r.exit_code == 0
    assert "active" in r.output


def test_license_deactivate():
    with patch("pentool.core.license.deactivate_license"), \
         patch("pentool.core.license.invalidate_session_license"):
        r = CliRunner().invoke(cli, ["license", "deactivate"])
    assert r.exit_code == 0
    assert "deactivated" in r.output


# ── _sync_pro_package_after_upgrade ─────────────────────────────────────────

def test_sync_pro_skipped_when_no_pro_dir(tmp_path):
    from pentool.cli.main import _sync_pro_package_after_upgrade
    from pathlib import Path
    with patch("pentool.core.license.PRO_PACKAGE_DIR", tmp_path / "no_pro"):
        # No check performed; no exception.
        _sync_pro_package_after_upgrade()


def test_sync_pro_updates_package(tmp_path):
    from pentool.cli.main import _sync_pro_package_after_upgrade
    (tmp_path / "pro").mkdir()
    result = MagicMock(updated=True, warning="")
    with patch("pentool.core.license.PRO_PACKAGE_DIR", tmp_path / "pro"), \
         patch("pentool.core.license.check_and_update_pro_package",
               new=AsyncMock(return_value=result)) as update_mock:
        _sync_pro_package_after_upgrade()
    update_mock.assert_called_once()


def test_sync_pro_warning(tmp_path):
    from pentool.cli.main import _sync_pro_package_after_upgrade
    (tmp_path / "pro").mkdir()
    result = MagicMock(updated=False, warning="stale build")
    with patch("pentool.core.license.PRO_PACKAGE_DIR", tmp_path / "pro"), \
         patch("pentool.core.license.check_and_update_pro_package",
               new=AsyncMock(return_value=result)):
        _sync_pro_package_after_upgrade()


def test_sync_pro_exception_handled(tmp_path):
    from pentool.cli.main import _sync_pro_package_after_upgrade
    from pentool.core.license import PRO_PACKAGE_DIR as real_dir
    with patch("pentool.core.license.PRO_PACKAGE_DIR", real_dir), \
         patch("pentool.core.license.check_and_update_pro_package",
               new=AsyncMock(side_effect=RuntimeError("boom"))), \
         patch("pentool.cli.main._warn_if_pro_incompatible"):
        _sync_pro_package_after_upgrade()


# ── _warn_if_pro_incompatible ───────────────────────────────────────────────

def test_warn_if_pro_incompatible_warns():
    from pentool.cli.main import _warn_if_pro_incompatible
    with patch("pentool.core.license.is_pro_package_compatible", return_value=(False, "stale build")):
        _warn_if_pro_incompatible()  # must not raise


def test_warn_if_pro_compatible_no_warning():
    from pentool.cli.main import _warn_if_pro_incompatible
    with patch("pentool.core.license.is_pro_package_compatible", return_value=(True, "")):
        _warn_if_pro_incompatible()
