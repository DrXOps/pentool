"""CLI-команды для управления проектами."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import click

from pentool.core.config import Config, get_config
from pentool.core.database import init_db
from pentool.core.logging import get_logger

logger = get_logger(__name__)


@click.group()
def project() -> None:
    """Управление проектами: инициализация, список, открытие."""


@project.command("init")
@click.option("--name", default="default", show_default=True, help="Имя проекта.")
@click.option(
    "--path",
    default=None,
    help="Директория проекта (по умолчанию: ~/.config/pentool/projects/<name>).",
)
def project_init(name: str, path: str | None) -> None:
    cfg = get_config()

    if path is None:
        project_dir = Path.home() / ".config" / "pentool" / "projects" / name
    else:
        project_dir = Path(path) / name

    project_dir.mkdir(parents=True, exist_ok=True)

    db_path = str(project_dir / "pentool.db")
    log_file = str(project_dir / "pentool.log")
    cert_dir = str(project_dir / "certs")
    plugins_dir = str(project_dir / "plugins")

    # Обновить и сохранить конфиг проекта
    project_cfg = Config(
        proxy_host=cfg.proxy_host,
        proxy_port=cfg.proxy_port,
        cert_dir=cert_dir,
        db_path=db_path,
        log_file=log_file,
        log_level=cfg.log_level,
        plugins_dir=plugins_dir,
    )
    config_path = project_dir / "config.yaml"
    project_cfg.save(config_path)

    # Создать таблицы БД
    try:
        asyncio.run(init_db(db_path))
        click.echo(f"Project '{name}' initialized:")
        click.echo(f"  Directory : {project_dir}")
        click.echo(f"  Database  : {db_path}")
        click.echo(f"  Config    : {config_path}")
        click.echo(f"  Log file  : {log_file}")
        logger.info("Project '%s' initialized at %s", name, project_dir)
    except Exception as exc:
        click.echo(f"Error initializing database: {exc}", err=True)
        logger.error("Failed to initialize project '%s': %s", name, exc)
        raise SystemExit(1) from exc


@project.command("list")
def project_list() -> None:
    projects_dir = Path.home() / ".config" / "pentool" / "projects"
    if not projects_dir.exists():
        click.echo("No projects found.")
        return

    entries = [d for d in projects_dir.iterdir() if d.is_dir()]
    if not entries:
        click.echo("No projects found.")
        return

    click.echo(f"{'Name':<20} {'Path'}")
    click.echo("-" * 60)
    for entry in sorted(entries):
        click.echo(f"{entry.name:<20} {entry}")
