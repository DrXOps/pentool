"""CLI-команды для управления AI-помощником."""

from __future__ import annotations

import asyncio
import sys

import click

from pentool.core.config import get_config


@click.group()
def ai() -> None:
    """AI-помощник: установка, запуск, управление."""


@ai.command("setup")
@click.option("--force", is_flag=True, default=False, help="Переустановить даже если уже есть.")
def ai_setup(force: bool) -> None:
    """Установить LLM-модель и подготовить MCP-сервер."""
    from pentool.services.ai.factory import (
        AI_MODELS_DIR,
        ai_setup_required,
        get_model_size_mb,
        install_ai_components,
    )

    if not force and not ai_setup_required():
        click.echo("AI-компоненты уже установлены. Используй --force для переустановки.")
        return

    click.echo(f"Установка AI-помощника (модель ~{get_model_size_mb()} MB)...")
    click.echo("Модель будет загружена в " + str(AI_MODELS_DIR))
    click.echo()
    click.echo("⚠️  Это займёт некоторое время в зависимости от скорости интернета.")
    click.echo()

    if not click.confirm("Продолжить установку?"):
        click.echo("Установка отменена.")
        return

    cfg = get_config()

    async def _run() -> bool:
        def progress(msg: str) -> None:
            click.echo(f"  {msg}")
        return await install_ai_components(cfg, progress_cb=progress)

    try:
        success = asyncio.run(_run())
        if success:
            click.echo()
            click.echo("✅ AI-помощник установлен!")
            click.echo()
            click.echo("Теперь можно:")
            click.echo("  pentool ai status   — проверить статус")
            click.echo("  pentool ai start    — запустить MCP-сервер")
            click.echo("  pentool             — запустить TUI и включить AI в настройках")
        else:
            click.echo("❌ Ошибка при установке.", err=True)
            sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nУстановка прервана.")
        sys.exit(1)


@ai.command("status")
def ai_status() -> None:
    """Показать статус AI-помощника и MCP-сервера."""
    from pentool.services.ai.factory import AI_MODELS_DIR

    cfg = get_config()
    model_exists = AI_MODELS_DIR.exists() and any(AI_MODELS_DIR.iterdir())

    click.echo("🔮 AI-помощник")
    click.echo(f"  Статус:     {'✅ Включён' if cfg.ai_enabled else '❌ Отключён'}")
    click.echo(f"  Модель:     {'установлена' if model_exists else 'не установлена'}")
    if cfg.ai_mcp_model_path:
        click.echo(f"  Путь:       {cfg.ai_mcp_model_path}")
    click.echo(f"  MCP-порт:   {cfg.ai_mcp_port or 'stdio (подпроцесс)'}")
    click.echo()
    if not model_exists:
        click.echo("  💡 Установи: pentool ai setup")


@ai.command("start")
def ai_start() -> None:
    """Запустить MCP-сервер (если не запущен)."""
    cfg = get_config()
    if not cfg.ai_enabled:
        click.echo("AI-помощник отключён. Включи в настройках или используй pentool ai setup.")
        return

    from pentool.services.ai.factory import get_ai

    backend = get_ai(cfg)
    if backend is None:
        click.echo("Не удалось создать AI-бэкенд. Проверь установку модели.", err=True)
        sys.exit(1)

    if hasattr(backend, "start"):
        async def _start() -> bool:
            return await backend.start()
        ok = asyncio.run(_start())
        if ok:
            click.echo("✅ MCP-сервер запущен.")
        else:
            click.echo("❌ Не удалось запустить MCP-сервер.", err=True)
            sys.exit(1)
    else:
        click.echo("Текущий бэкенд не поддерживает ручной запуск.")


@ai.command("stop")
def ai_stop() -> None:
    """Остановить MCP-сервер."""
    from pentool.services.ai.provider import MCPBackend
    # Для остановки используем прямой вызов, т.к. бэкенд мог уже быть создан
    # TODO: хранить ссылку на активный бэкенд в глобальном менеджере
    click.echo("MCP-сервер будет остановлен при выходе из pentool.")


@ai.command("remove")
@click.confirmation_option(prompt="Удалить LLM-модель и MCP-сервер?")
def ai_remove() -> None:
    """Удалить LLM-модель и зависимости MCP-сервера."""
    import shutil
    from pathlib import Path

    from pentool.services.ai.factory import AI_MODELS_DIR, AI_MCP_DIR

    cfg = get_config()
    cfg.ai_enabled = False
    cfg.ai_mcp_model_path = ""

    for d in [AI_MODELS_DIR, AI_MCP_DIR]:
        if d.exists():
            shutil.rmtree(d)
            click.echo(f"  Удалено: {d}")

    click.echo("✅ AI-компоненты удалены.")
