"""AI-backend providers.

AIBackend — abstract base class.
MCPBackend — an implementation backed by an external MCP server (llama-cpp-python + mcp SDK).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from pentool.services.ai.prompts import REGISTRY, AITask

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
    """Abstract AI backend."""

    @abstractmethod
    async def generate(self, task_name: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Call AI for task_name with the given context.

        Returns the parsed JSON response, or None on error/timeout.
        """

    @abstractmethod
    async def health(self) -> bool:
        """Check the backend is alive and responding."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""


class MCPBackend(AIBackend):
    """MCP client: talks to an external MCP server over stdio (JSON-RPC)."""

    def __init__(self, mcp_cmd: list[str] | None = None) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._mcp_cmd = mcp_cmd
        self._stdin: Any = None  # asyncio StreamWriter (process stdin)
        self._stdout: Any = None  # asyncio StreamReader (process stdout)

    async def start(self) -> bool:
        """Start the MCP server as a subprocess."""
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
            # Use the subprocess's buffered binary I/O directly, NOT an
            # asyncio.StreamWriter/StreamReader over the pipe: the latter
            # needs a live event loop at construction and crashed with
            # "'NoneType' object has no attribute 'create_future'" when no
            # loop was bound. Read/write are done blocking in to_thread.
            self._stdin = self._process.stdin
            self._stdout = self._process.stdout
            global _MCP_PROCESS_PID
            _MCP_PROCESS_PID = self._process.pid
            log.info("MCP-сервер запущен (PID=%s)", self._process.pid)
            return True
        except Exception as exc:
            log.error("MCPBackend: не удалось запустить сервер: %s", exc)
            return False

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        """Call an MCP-server tool over JSON-RPC."""
        if not self._stdin or not self._stdout:
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
            # process.stdin/stdout from create_subprocess_exec are asyncio
            # StreamWriter/StreamReader, correctly bound to the event loop.
            self._stdin.write((payload + "\n").encode("utf-8"))
            await self._stdin.drain()

            line = await asyncio.wait_for(self._stdout.readline(), timeout=60.0)
            if not line:
                return None
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
        """Call the MCP server for task_name.

        MCP tools/call returns {"content": [{"type":"text","text":"<json>"}]} —
        we pull out and parse `text` so the client gets a clean dict/items.
        """
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

        resp = await self._call_tool("generate_payload", prompt_data)
        if not resp:
            return None
        # tools/call → {"content": [{"type":"text","text":"<json>"}], ...}
        try:
            content = resp.get("content") or []
            text = ""
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text += str(item.get("text", ""))
            parsed = json.loads(text) if text.strip() else None
            return parsed if isinstance(parsed, dict) else {"items": parsed} if isinstance(parsed, list) else None
        except Exception as exc:  # noqa: BLE001
            log.error("MCPBackend: не удалось распарсить ответ: %s", exc)
            return None

    async def health(self) -> bool:
        """Check the MCP server health.

        The `health` tool exists on the server (returns {ok, ...}) — use it
        rather than the JSON-RPC `ping` method.
        """
        try:
            result = await self._call_tool("health", {})
            if not result:
                return False
            content = result.get("content") or []
            text = "".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
            try:
                data = json.loads(text) if text.strip() else {}
                return bool(data.get("ok", False))
            except Exception:  # noqa: BLE001
                return False
        except Exception:
            return False

    async def close(self) -> None:
        """Stop the MCP server."""
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
            self._stdin = None
            self._stdout = None
