"""Главная группа CLI-команд."""

from __future__ import annotations

import click

from pentool.core.config import get_config
from pentool.core.logging import setup_logging


@click.group()
@click.version_option(package_name="pentool")
@click.option("--config", "config_path", default=None, help="Путь к файлу конфигурации.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Подробный вывод (DEBUG).")
@click.pass_context
def cli(ctx: click.Context, config_path: str | None, verbose: bool) -> None:
    """Pentool — консольный инструмент для пентестинга веб-приложений.

    Запустите без аргументов для открытия TUI:

        pentool

    Или используйте команды ниже для работы из командной строки.
    """
    ctx.ensure_object(dict)

    cfg = get_config()
    if config_path:
        from pentool.core.config import Config
        cfg = Config.load(config_path)

    log_level = "DEBUG" if verbose else cfg.log_level
    setup_logging(cfg.log_file, log_level)

    ctx.obj["config"] = cfg


# Импорт и регистрация групп команд
from pentool.cli.project import project  # noqa: E402

cli.add_command(project)


from pentool.cli.proxy import proxy  # noqa: E402

cli.add_command(proxy)


@cli.group()
def repeater() -> None:
    """Модуль Repeater: ручная отправка запросов."""


@repeater.command("send")
@click.option("--request-file", required=True, type=click.Path(exists=True), help="Файл с HTTP-запросом.")
def repeater_send(request_file: str) -> None:
    click.echo(f"Repeater send {request_file} — not implemented yet.")


@cli.group()
def intruder() -> None:
    """Модуль Intruder: автоматизированные атаки."""


@intruder.command("run")
@click.option("--request", "request_file", required=True, type=click.Path(exists=True))
@click.option("--payloads", required=True, type=click.Path(exists=True))
@click.option("--attack", default="sniper", show_default=True,
              type=click.Choice(["sniper", "battering_ram", "pitchfork", "cluster_bomb"]))
def intruder_run(request_file: str, payloads: str, attack: str) -> None:
    click.echo(f"Intruder run [{attack}] — not implemented yet.")


from pentool.cli.scan import scan  # noqa: E402

cli.add_command(scan)


@cli.command("decode")
@click.argument("operation", type=click.Choice([
    "url_encode", "url_decode",
    "base64_encode", "base64_decode",
    "base64url_encode", "base64url_decode",
    "html_encode", "html_decode",
    "hex_encode", "hex_decode",
    "unicode_escape", "unicode_unescape",
    "md5", "sha1", "sha256",
]))
@click.argument("text")
def decode_cmd(operation: str, text: str) -> None:
    """Кодировать/декодировать/хэшировать текст."""
    from pentool.utils.coder import apply_operation
    try:
        result = apply_operation(operation, text)
        click.echo(result)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc
