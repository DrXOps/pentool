"""AI-backend factory and install helpers."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from pentool.core.config import Config
from pentool.services.ai.provider import AIBackend, MCPBackend

log = logging.getLogger(__name__)

# Path to LLM models under ~/.pentool/ai/models/
AI_MODELS_DIR = Path.home() / ".pentool" / "ai" / "models"
AI_MCP_DIR = Path.home() / ".pentool" / "ai" / "mcp_server"


def get_ai(config: Config) -> AIBackend | None:
    """Return the configured AI backend, or None when AI is disabled.

    Args:
        config: current config carrying ai_enabled and the MCP parameters.
    """
    if not config.ai_enabled:
        return None

    if config.ai_mcp_port and config.ai_mcp_port > 0:
        # TCP mode — connect to an already-running server
        return MCPBackend()
    else:
        # stdio mode — launch the server as a subprocess
        model_path = config.ai_mcp_model_path or _find_default_model()
        if not model_path:
            log.warning("AI: модель не найдена, AI-помощник недоступен")
            return None
        mcp_cmd = _build_mcp_cmd(model_path)
        backend = MCPBackend(mcp_cmd=mcp_cmd)
        return backend


def _find_default_model() -> str | None:
    """Find a GGUF model under ~/.pentool/ai/models/."""
    if not AI_MODELS_DIR.exists():
        return None
    for f in AI_MODELS_DIR.iterdir():
        if f.suffix in (".gguf", ".bin"):
            return str(f)
    return None


# The active AI backend for this process, kept here (not inside the TUI) so
# both the TUI and the CLI share one reference for start/stop/health.
_ACTIVE_BACKEND: "MCPBackend | None" = None


def is_ai_running() -> bool:
    """True if an MCP backend was created and its subprocess is alive."""
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
    """Bring up the MCP server if a model exists and AI is enabled. Lazily idempotent."""
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
    """Stop the MCP server if it is running."""
    global _ACTIVE_BACKEND
    b = _ACTIVE_BACKEND
    _ACTIVE_BACKEND = None
    if b is not None:
        try:
            await b.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("AI: stop_ai close error: %s", exc)


def get_active_backend() -> "MCPBackend | None":
    """Return the active (running) AI backend, if one is up."""
    return _ACTIVE_BACKEND


def _build_mcp_cmd(model_path: str) -> list[str]:
    """Build the MCP-server launch command.

    Priority:
      1. Installed PyPI package `pentool-mcp-server` (entry point
         `pentool-mcp-server`) — preferred.
      2. Local script ~/.pentool/ai/mcp_server/server.py (fallback, the old
         inline mechanism).
      3. An `echo` stub when the server is not installed.
    """
    exe = shutil.which("pentool-mcp-server")
    if exe:
        return [exe, "--model", model_path]

    server_script = AI_MCP_DIR / "server.py"
    if server_script.exists():
        return ["python", str(server_script), "--model", model_path]
    # If the server is not installed — return the echo stub.
    return ["echo", "MCP-сервер не установлен"]


# ── AI component setup / re-setup ───────────────────────────────────────────


def ai_setup_required() -> bool:
    """Check whether a first-time AI install is required."""
    return not AI_MODELS_DIR.exists() or not list(AI_MODELS_DIR.iterdir())


def get_model_size_mb() -> int:
    """Return the approximate GGUF file size in MB shown to the user.

    LFM2.5-350M-heretic converts to llama.cpp GGUF-Q8_0 — its size is close to
    the official LiquidAI/LFM2.5-350M-Q8_0 (361.7 MB); we round to 363.
    """
    return 363


def get_ai_system_requirements() -> dict[str, str]:
    """Return the AI model's system requirements for the onboarding message.

    Values taken from the LFM2.5-350M-heretic cards (Liquid AI + GGUF repo
    FadedRedStar): 350M parameters, 131072-token context, runs on CPU under
    1 GB RAM — edge/on-device deployment, day-1 llama.cpp support.
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
    """Install AI components: download the model + prepare the MCP server.

    Args:
        config: config (will be updated with ai_enabled=True, ai_model_path)
        progress_cb: optional callback to surface progress

    Returns:
        True on a successful install
    """
    # 1. Create the directories.
    AI_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    AI_MCP_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Download the ready-made GGUF model file (the user does not convert
    #    anything — the quantization is already done and hosted on HuggingFace).
    #    No fake "success": on a network error / 404 / wrong size we return
    #    False, and the caller surfaces the error to the user.
    model_path = AI_MODELS_DIR / "lfm-2.5-350m-heretic.gguf"
    if not model_path.exists():
        if not await _download_gguf(model_path, progress_cb=progress_cb):
            return False

    # 3. MCP server: prefer the standalone PyPI package `pentool-mcp-server` —
    #    install it if missing and pip is available. When pip is unavailable
    #    (offline) fall back to the inline stub.
    if not _is_mcp_server_installed():
        if progress_cb:
            progress_cb("Установка MCP-сервера (pentool-mcp-server)...")
        if not _try_pip_install_mcp_server():
            _ensure_mcp_server_stub()
    elif progress_cb:
        progress_cb("MCP-сервер уже установлен")

    # 4. Update the config.
    config.ai_enabled = True
    config.ai_mcp_model_path = str(model_path)

    return True


def _is_mcp_server_installed() -> bool:
    """True if the `pentool-mcp-server` entry point is available."""
    return shutil.which("pentool-mcp-server") is not None


def _try_pip_install_mcp_server() -> bool:
    """Try to install the pentool-mcp-server package via the current pip/uv.

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
    """Create a minimal MCP server when none is present."""
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
