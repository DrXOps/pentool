"""Фабрика AI-бэкендов и утилиты установки."""

from __future__ import annotations

import logging
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


# Активный AI-бэкенд на процесс. Храним здесь (а не где-то в TUI), чтобы и
# TUI, и CLI имели общую ссылку для start/stop/health — раньше вместо этого
# был «TODO: хранить ссылку на активный бэкенд».
_ACTIVE_BACKEND: "MCPBackend | None" = None


def is_ai_running() -> bool:
    """True, если MCP-бэкенд создан и его subprocess жив."""
    global _ACTIVE_BACKEND
    b = _ACTIVE_BACKEND
    if b is None:
        return False
    try:
        from pentool.services.ai.provider import is_mcp_running
        return is_mcp_running()
    except Exception:  # noqa: BLE001
        return False


async def start_ai(config: Config) -> bool:
    """Поднять MCP-сервер (если модель есть и AI включён). Лениво-идемпотентно."""
    global _ACTIVE_BACKEND
    if _ACTIVE_BACKEND is not None:
        return True
    if not config.ai_enabled:
        return False
    backend = get_ai(config)
    if backend is None:
        log.warning("AI: start_ai — модель не найдена, AI недоступен")
        return False
    try:
        ok = await backend.start()
    except Exception as exc:  # noqa: BLE001
        log.error("AI: start_ai failed: %s", exc)
        return False
    if ok:
        _ACTIVE_BACKEND = backend
        log.info("AI: MCP-сервер запущен")
    return ok


async def stop_ai() -> None:
    """Остановить MCP-сервер, если он запущен."""
    global _ACTIVE_BACKEND
    b = _ACTIVE_BACKEND
    _ACTIVE_BACKEND = None
    if b is not None:
        try:
            await b.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("AI: stop_ai close error: %s", exc)


def get_active_backend() -> "MCPBackend | None":
    """Вернуть активный (запущенный) AI-бэкенд, если он поднят."""
    return _ACTIVE_BACKEND


def _build_mcp_cmd(model_path: str) -> list[str]:
    """Собрать команду запуска MCP-сервера.

    Приоритет:
      1. Установленный PyPI-пакет `pentool-mcp-server` (entry point
         `pentool-mcp-server`) — предпочтительный вариант.
      2. Локальный скрипт ~/.pentool/ai/mcp_server/server.py (fallback,
         старый inline-механизм).
      3. Заглушка `echo`, если сервер не установлен.
    """
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
    """Вернуть примерный размер GGUF-файла модели в MB для показа пользователю.

    LFM2.5-350M-heretic конвертируется в llama.cpp GGUF-Q8_0 — размер близок
    к официальному LiquidAI/LFM2.5-350M-Q8_0 (361.7 MB), округляем до 363.
    """
    return 363


def get_ai_system_requirements() -> dict[str, str]:
    """Вернуть системные требования AI-модели для показа в вводном сообщении.

    Значения взяты из карточек LFM2.5-350M-heretic (Liquid AI + GGUF-репо
    FadedRedStar): 350M параметров, контекст 131 072 токенов, работает на CPU
    под 1 GB RAM — edge/on-device deployment, день-1 поддержка llama.cpp.
    """
    return {
        "parameters": "350M",
        "context_len": "131072",
        "ram": "< 1 GB",
        "accelerator": "CPU only (no GPU required)",
        "quant": "GGUF-Q8_0",
        "prompt_format": "ChatML",
    }


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

    # 2. Скачать готовый GGUF-файл модели (пользователь ничего не
    #    конвертирует — квантизация уже готова и хостится на HuggingFace).
    #    Никаких мнимых "успехов": при сетевой ошибке/404/неверном размере
    #    возвращаем False, и вызывающий показывает ошибку пользователю.
    model_path = AI_MODELS_DIR / "lfm-2.5-350m-heretic.gguf"
    if not model_path.exists():
        if not await _download_gguf(model_path, progress_cb=progress_cb):
            return False

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
    """Вернуть URL для скачивания готового GGUF-файла модели.

    Квантизация LFM2.5-350M-heretic уже готова (пользователь ничего не
    конвертирует) и хостится на HuggingFace: FadedRedStar/LFM2.5-350M-heretic-GGUF.
    Берём near-lossless Q8_0 (~362 MB) — лучшая точность для задач
    instruction-following / структурной генерации payload.
    """
    return (
        "https://huggingface.co/FadedRedStar/LFM2.5-350M-heretic-GGUF/"
        "resolve/main/LFM2.5-350M-heretic-Q8_0.gguf"
    )


async def _download_gguf(dest: Path, progress_cb: Any = None) -> bool:
    """Скачать готовый GGUF-файл модели в dest с проверкой результата.

    Возвращает True только после успешной загрузки непустого файла с
    ожидаемым (минимальным) размером. При любом сбое частичный файл
    удаляется, возвращается False — чтобы не подсунуть повреждённую модель.
    """
    import urllib.request

    url = _get_model_download_url()
    if progress_cb:
        progress_cb(f"Downloading LFM2.5-350M-heretic GGUF (~{get_model_size_mb()} MB)...")

    tmp = dest.with_suffix(".gguf.part")
    try:
        # Follow redirects (HuggingFace -> CDN), with a timeout.
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            while True:
                chunk = resp.read(1 << 20)  # 1 MB
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total:
                    pct = downloaded * 100 // total
                    progress_cb(f"Downloading model... {pct}%")
        # Minimum sanity check (Q8_0 is ~362 MB; anything far smaller is bad).
        if not tmp.exists() or tmp.stat().st_size < 100_000_000:
            log.error("AI: скачанный GGUF слишком мал или равен 0: %s", tmp.stat().st_size if tmp.exists() else -1)
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(dest)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("AI: не удалось скачать модель %s: %s", url, exc)
        tmp.unlink(missing_ok=True)
        return False


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
