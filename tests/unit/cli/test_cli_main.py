"""Unit tests for pentool.cli.main — the root Click group.

Проверяет только то, что реально существует в текущем CLI:
- клик группа cli() импортируется корректно
- --url --headless запускает headless скан
- --version работает
- --help работает
- без аргументов показывает помощь (не падает)
"""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from pentool.cli.main import cli


def test_cli_imports() -> None:
    """cli — click Group, корректно импортируется."""
    from pentool.cli.main import cli as _cli
    assert _cli is not None
    assert callable(_cli)


def test_cli_help() -> None:
    """--help показывает справку."""
    r = CliRunner().invoke(cli, ["--help"])
    assert r.exit_code == 0
    assert "Usage" in r.output


def test_cli_version() -> None:
    """--version показывает версию."""
    r = CliRunner().invoke(cli, ["--version"])
    assert r.exit_code == 0
    assert "version" in r.output or "pentool" in r.output


def test_cli_no_args_shows_help() -> None:
    """Без аргументов — помощь (не падает)."""
    r = CliRunner().invoke(cli)
    assert r.exit_code == 0
    assert "Usage" in r.output


def test_cli_url_headless_runs() -> None:
    """--url --headless запускает headless через run_headless_scan."""
    with patch("pentool.cli.headless.run_headless_scan") as run_scan:
        r = CliRunner().invoke(cli, ["--url", "https://example.com", "--headless"])
    assert r.exit_code == 0
    run_scan.assert_called_once()


def test_cli_verbose_flag() -> None:
    """--verbose устанавливает DEBUG логирование."""
    from pentool.core.config import Config
    cfg = Config()
    with patch("pentool.cli.main.get_config", return_value=cfg), \
         patch("pentool.cli.main.setup_logging") as set_log, \
         patch("pentool.cli.headless.run_headless_scan"):
        CliRunner().invoke(cli, ["--verbose", "--url", "https://x.test", "--headless"])
    assert set_log.call_args[0][1] == "DEBUG"


def test_cli_default_log_level() -> None:
    """Без --verbose уровень из конфига."""
    from pentool.core.config import Config
    cfg = Config(log_level="INFO")
    with patch("pentool.cli.main.get_config", return_value=cfg), \
         patch("pentool.cli.main.setup_logging") as set_log, \
         patch("pentool.cli.headless.run_headless_scan"):
        CliRunner().invoke(cli, ["--url", "https://x.test", "--headless"])
    assert set_log.call_args[0][1] == "INFO"
