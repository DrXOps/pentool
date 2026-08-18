"""Провайдеры AI-бэкенда.

AIBackend — абстрактный базовый класс.
MCPBackend — реализация через внешний MCP-сервер (llama-cpp-python + mcp SDK).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from pentool.services.ai.prompts import AITask, REGISTRY

log = logging.getLogger(__name__)

# Module-level handle to the "currently alive" MCP subprocess PID, so the
# Dashboard's MCP status LED can show RUNNING without owning a backend
# instance. start()/close() keep it in sync; is_mcp_running() also verifies
# the PID is actually alive.
_MCP_PROCESS_PID: int | None = None


def is_mcp_running() -> bool:
    """True if an MCP subprocess is currently alive in this process."""
    global _MCP_PROCESS_PID
    pid = _MCP_PROCESS_PID
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        _MCP_PROCESS_PID = None  # stale — process died while we weren't looking
        return False


class AIBackend(ABC):
    """Абстрактный AI-бэкенд."""

    @abstractmethod
    async def generate(self, task_name: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Вызвать AI для задачи task_name с переданным контекстом.

        Возвращает распарсенный JSON-ответ или None при ошибке/таймауте.
        """

    @abstractmethod
    async def health(self) -> bool:
        """Проверить, что бэкенд жив и отвечает."""

    @abstractmethod
    async def close(self) -> None:
        """Освободить ресурсы."""


class MCPBackend(AIBackend):
    """MCP-клиент: общается с внешним MCP-сервером через stdio (JSON-RPC)."""

    def __init__(self, mcp_cmd: list[str] | None = None) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._mcp_cmd = mcp_cmd
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def start(self) -> bool:
        """Запустить MCP-сервер как подпроцесс."""
        if not self._mcp_cmd:
            log.error("MCPBackend: команда запуска MCP-сервера не задана")
            return False
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._mcp_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # Обёртка для удобства чтения/записи
            if self._process.stdin and self._process.stdout:
                self._reader = asyncio.StreamReader()
                protocol = asyncio.StreamReaderProtocol(self._reader)
                self._writer = asyncio.StreamWriter(self._process.stdin, protocol, None, None)
            global _MCP_PROCESS_PID
            _MCP_PROCESS_PID = self._process.pid
            log.info("MCP-сервер запущен (PID=%s)", self._process.pid)
            return True
        except Exception as exc:
            log.error("MCPBackend: не удалось запустить сервер: %s", exc)
            return False

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        """Вызвать tool MCP-сервера через JSON-RPC."""
        if not self._writer:
            log.warning("MCPBackend: сервер не запущен")
            return None
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        try:
            payload = json.dumps(req, ensure_ascii=False)
            self._writer.write((payload + "\n").encode("utf-8"))
            await self._writer.drain()

            if self._reader:
                line = await asyncio.wait_for(self._reader.readline(), timeout=60.0)
                resp = json.loads(line.decode("utf-8").strip())
                if "error" in resp:
                    log.error("MCP-сервер вернул ошибку: %s", resp["error"])
                    return None
                return resp.get("result")
        except asyncio.TimeoutError:
            log.warning("MCPBackend: таймаут при вызове tool %s", tool_name)
        except Exception as exc:
            log.error("MCPBackend: ошибка вызова tool %s: %s", tool_name, exc)
        return None

    async def generate(self, task_name: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Вызвать MCP-сервер для задачи task_name."""
        task = REGISTRY.get(task_name)
        if not task:
            log.warning("MCPBackend: неизвестная задача %s", task_name)
            return None

        prompt_data = {
            "task": task_name,
            "system_prompt": task.system_prompt,
            "max_tokens": task.max_tokens,
            "temperature": task.temperature,
        }
        if context:
            prompt_data["context"] = context

        return await self._call_tool("generate_payload", prompt_data)

    async def health(self) -> bool:
        """Проверить здоровье MCP-сервера."""
        try:
            result = await self._call_tool("ping", {})
            return result is not None
        except Exception:
            return False

    async def close(self) -> None:
        """Остановить MCP-сервер."""
        global _MCP_PROCESS_PID
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            log.info("MCP-сервер остановлен (PID=%s)", self._process.pid)
            if _MCP_PROCESS_PID == self._process.pid:
                _MCP_PROCESS_PID = None
            self._process = None
            self._writer = None
            self._reader = None
