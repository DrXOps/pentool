"""Unit tests for pentool.cli.main — the root Click group.

Checks only what actually exists in the current CLI:
- the click group cli() imports correctly
- --url --headless starts a headless scan
- --version works
- --help works
- with no arguments it shows help (and does not crash)
"""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from pentool.cli.main import cli


def test_cli_imports() -> None:
    """cli — a click Group that imports correctly."""
    from pentool.cli.main import cli as _cli

    assert _cli is not None
    assert callable(_cli)


def test_cli_help() -> None:
    """--help shows the usage text."""
    r = CliRunner().invoke(cli, ["--help"])
    assert r.exit_code == 0
    assert "Usage" in r.output


def test_cli_version() -> None:
    """--version prints the version."""
    r = CliRunner().invoke(cli, ["--version"])
    assert r.exit_code == 0
    assert "version" in r.output or "pentool" in r.output


def test_cli_no_args_shows_help() -> None:
    """With no arguments it shows help (and does not crash)."""
    r = CliRunner().invoke(cli)
    assert r.exit_code == 0
    assert "Usage" in r.output


def test_cli_url_headless_runs() -> None:
    """--url --headless starts a headless run through run_headless_scan."""
    with patch("pentool.cli.headless.run_headless_scan") as run_scan:
        r = CliRunner().invoke(cli, ["--url", "https://example.com", "--headless"])
    assert r.exit_code == 0
    run_scan.assert_called_once()


def test_cli_verbose_flag() -> None:
    """--verbose sets up DEBUG logging."""
    from pentool.core.config import Config

    cfg = Config()
    with (
        patch("pentool.cli.main.get_config", return_value=cfg),
        patch("pentool.cli.main.setup_logging") as set_log,
        patch("pentool.cli.headless.run_headless_scan"),
    ):
        CliRunner().invoke(cli, ["--verbose", "--url", "https://x.test", "--headless"])
    assert set_log.call_args[0][1] == "DEBUG"


def test_cli_default_log_level() -> None:
    """Without --verbose the level comes from the config."""
    from pentool.core.config import Config

    cfg = Config(log_level="INFO")
    with (
        patch("pentool.cli.main.get_config", return_value=cfg),
        patch("pentool.cli.main.setup_logging") as set_log,
        patch("pentool.cli.headless.run_headless_scan"),
    ):
        CliRunner().invoke(cli, ["--url", "https://x.test", "--headless"])
    assert set_log.call_args[0][1] == "INFO"


def test_config_flag_becomes_the_process_config(tmp_path) -> None:
    """--config must reach PentoolApp, not just the log setup (T-024).

    `PentoolApp()` and everything behind it read `get_config()`. Before this the
    file passed with --config was loaded, used for the log level and then thrown
    away: a run configured for port 8099 still started on 8080 and killed the
    proxy daemon of an already running instance.
    """
    from pentool.core.config import get_config, set_config

    previous = get_config()
    path = tmp_path / "custom.yaml"
    path.write_text("proxy_port: 8099\nproxy_host: 127.0.0.1\n", encoding="utf-8")
    try:
        with patch("pentool.cli.main.setup_logging"):
            # No --url: the group prints help and never starts a scan, so this
            # stays a unit test (a headless run would go to the network).
            r = CliRunner().invoke(cli, ["--config", str(path)])
        assert r.exit_code == 0
        assert get_config().proxy_port == 8099, "the --config file did not become the process config"
    finally:
        set_config(previous)
