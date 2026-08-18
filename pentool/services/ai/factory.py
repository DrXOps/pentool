"""Фабрика AI-бэкендов и утилиты установки."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from pentool.core.config import Config
from pentool.services.ai.provider import AIBackend, MCPBackend

log = logging.getLogger(__name__)

# Путь к моделям LLM в ~/.pentool/ai/models/
AI_MODELS_DIR = Path.home() / ".pentool" / "ai" / "models"
AI_MCP_DIR = Path.home() / ".pentool" / "ai" / "mcp_server"


def get_ai(config: Config) -> AIBackend | None:
    """Вернуть настроенный AI-бэкенд или None, если AI выключен.

    Args:
        config: текущий конфиг с ai_enabled и параметрами MCP.
    """
    if not config.ai_enabled:
        return None

    if config.ai_mcp_port and config.ai_mcp_port > 0:
        # TCP-режим — подключаемся к уже запущенному серверу
        return MCPBackend()
    else:
        # stdio-режим — запускаем сервер как подпроцесс
        model_path = config.ai_mcp_model_path or _find_default_model()
        if not model_path:
            log.warning("AI: модель не найдена, AI-помощник недоступен")
            return None
        mcp_cmd = _build_mcp_cmd(model_path)
        backend = MCPBackend(mcp_cmd=mcp_cmd)
        return backend


def _find_default_model() -> str | None:
    """Найти GGUF-модель в ~/.pentool/ai/models/."""
    if not AI_MODELS_DIR.exists():
        return None
    for f in AI_MODELS_DIR.iterdir():
        if f.suffix in (".gguf", ".bin"):
            return str(f)
    return None


def _build_mcp_cmd(model_path: str) -> list[str]:
    """Собрать команду запуска MCP-сервера.

    Приоритет:
      1. Установленный PyPI-пакет `pentool-mcp-server` (entry point
         `pentool-mcp-server`) — предпочтительный вариант.
      2. Локальный скрипт ~/.pentool/ai/mcp_server/server.py (fallback,
         старый inline-механизм).
      3. Заглушка `echo`, если сервер не установлен.
    """
    import shutil
    exe = shutil.which("pentool-mcp-server")
    if exe:
        return [exe, "--model", model_path]

    server_script = AI_MCP_DIR / "server.py"
    if server_script.exists():
        return ["python", str(server_script), "--model", model_path]
    # Если сервер не установлен — возвращаем заглушку
    return ["echo", "MCP-сервер не установлен"]


# ── Установка / доустановка AI-компонентов ─────────────────────────────────


def ai_setup_required() -> bool:
    """Проверить, требуется ли первичная установка AI."""
    return not AI_MODELS_DIR.exists() or not list(AI_MODELS_DIR.iterdir())


def get_model_size_mb() -> int:
    """Вернуть примерный размер модели в MB для показа пользователю."""
    return 750  # LFM2.5-350M-heretic ~750 MB


async def install_ai_components(config: Config, progress_cb: Any = None) -> bool:
    """Установить AI-компоненты: скачать модель + подготовить MCP-сервер.

    Args:
        config: конфиг (будет обновлён ai_enabled=True, ai_model_path)
        progress_cb: опциональный колбэк для отображения прогресса

    Returns:
        True при успешной установке
    """
    # 1. Создать директории
    AI_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    AI_MCP_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Скачать модель (заглушка — реальная загрузка будет позже)
    model_url = _get_model_download_url()
    model_path = AI_MODELS_DIR / "lfm-2.5-350m-heretic.gguf"

    if not model_path.exists():
        if progress_cb:
            progress_cb(f"Скачивание модели LFM2.5-350M (~{get_model_size_mb()} MB)...")
        # TODO: реальная загрузка через aiohttp / curl
        # Сейчас — заглушка, чтобы не блокировать разработку
        log.info("AI: модель будет скачана из %s в %s", model_url, model_path)

    # 3. MCP-сервер: предпочитаем отдельный PyPI-пакет `pentool-mcp-server`,
    #    если он не установлен и доступен pip — доустанавливаем. Если pip
    #    недоступен (оффлайн) — fallback на inline-заглушку.
    if not _is_mcp_server_installed():
        if progress_cb:
            progress_cb("Установка MCP-сервера (pentool-mcp-server)...")
        if not _try_pip_install_mcp_server():
            _ensure_mcp_server_stub()
    elif progress_cb:
        progress_cb("MCP-сервер уже установлен")

    # 4. Обновить конфиг
    config.ai_enabled = True
    config.ai_mcp_model_path = str(model_path)

    return True


def _is_mcp_server_installed() -> bool:
    """True, если доступен entry point `pentool-mcp-server`."""
    import shutil
    return shutil.which("pentool-mcp-server") is not None


def _try_pip_install_mcp_server() -> bool:
    """Попытаться установить пакет pentool-mcp-server текущим pip/uv.

    Возвращает True при успешной установке. При недоступности pip/сети
    возвращает False (вызывающий fallback на inline-заглушку).
    """
    import subprocess
    import sys
    try:
        installer = [sys.executable, "-m", "pip", "install", "pentool-mcp-server>=0.1.0"]
        proc = subprocess.run(
            installer,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return proc.returncode == 0
    except Exception as exc:  # noqa: BLE001
        log.info("pip install pentool-mcp-server failed: %s", exc)
        return False


def _get_model_download_url() -> str:
    """Вернуть URL для скачивания GGUF-модели."""
    # TODO: заменить на реальный URL после форка репозитория
    return "https://github.com/DrXOps/LFM-2.5-350M-heretic/releases/latest/download/lfm-2.5-350m-heretic.gguf"


def _ensure_mcp_server_stub() -> None:
    """Создать минимальный MCP-сервер, если его нет."""
    server_py = AI_MCP_DIR / "server.py"
    if server_py.exists():
        return

    server_py.write_text("""\
#!/usr/bin/env python3
\"\"\"MCP-сервер для Pentool AI. Заглушка для разработки.\"\"\"

import json
import sys


def handle_request(req: dict) -> dict:
    method = req.get("method", "")
    if method == "tools/call":
        return {"jsonrpc": "2.0", "id": req.get("id", 1), "result": {"content": []}}
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req.get("id", 1), "result": {"status": "ok"}}
    return {"jsonrpc": "2.0", "id": req.get("id", 1), "error": {"code": -32601, "message": "Method not found"}}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\\n")
            sys.stdout.flush()
        except json.JSONDecodeError:
            continue


if __name__ == "__main__":
    main()
""")
    log.info("MCP-сервер-заглушка создана: %s", server_py)
