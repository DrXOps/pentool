"""JSONL audit log for MCP AI requests/responses.

Writes one JSON line per ``generate()`` call to
``~/.pentool/ai/audit.jsonl``.

Each line is a complete request-response cycle:

.. code:: json

    {
        "ts": "2026-09-19T14:30:00.123456",
        "task": "choose_checks",
        "request": {
            "system_prompt_preview": "<first 200 chars>",
            "context_preview": "<first 500 chars>",
            "context_full_truncated": true,
            "max_tokens": 512,
            "temperature": 0.7
        },
        "response": {
            "raw": "<full raw LLM output>",
            "parsed": { ... },
            "error": null
        }
    }

Usage::

    from pentool.services.ai.audit_log import audit

    audit.log(
        task="choose_checks",
        prompt_data={...},
        raw_response="...",
        parsed_response={...},
        error=None,
    )
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

_AUDIT_FILE: Path | None = None
_AUDIT_FD: Any = None  # TextIOWrapper, opened lazily


def _get_audit_path() -> Path:
    """Return the path to the AI audit JSONL file.

    Shared location: ~/.config/pentool/logs/ai_audit.jsonl
    (same LOGS_DIR as pentool.log, see config.py).
    """
    from pentool.core.config import LOGS_DIR
    return LOGS_DIR / "ai_audit.jsonl"


def _ensure_fd() -> Any:
    """Open the audit file lazily, return the file descriptor."""
    global _AUDIT_FILE, _AUDIT_FD
    if _AUDIT_FD is not None:
        return _AUDIT_FD
    _AUDIT_FILE = _get_audit_path()
    _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _AUDIT_FD = open(_AUDIT_FILE, "a", encoding="utf-8")
    _log.info("AI audit log opened: %s", _AUDIT_FILE)
    return _AUDIT_FD


def _trunc(text: str | None, max_len: int) -> str:
    """Truncate text to max_len chars, appending '...' if longer."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def close() -> None:
    """Close the audit file descriptor (cleanup on shutdown)."""
    global _AUDIT_FD, _AUDIT_FILE
    if _AUDIT_FD is None:
        return
    try:
        _AUDIT_FD.close()
    except Exception:
        pass
    _AUDIT_FD = None
    _AUDIT_FILE = None


def log(
    task: str,
    prompt_data: dict[str, Any] | None = None,
    raw_response: str | None = None,
    parsed_response: Any = None,
    error: str | None = None,
) -> None:
    """Write one audit record to ``~/.pentool/ai/audit.jsonl``.

    Args:
        task: имя задачи (choose_checks / crawl_endpoints / ...).
        prompt_data: данные, отправленные в MCP (system_prompt, context, ...).
        raw_response: сырой ответ LLM (текст до парсинга).
        parsed_response: распаршенный JSON (dict/list/None).
        error: строка ошибки, если была.
    """
    try:
        fd = _ensure_fd()
    except Exception as exc:
        _log.warning("AI audit: cannot open log file: %s", exc)
        return

    request_block: dict[str, Any] = {}

    if prompt_data:
        ctx = prompt_data.get("context")
        context_json = json.dumps(ctx, ensure_ascii=False) if ctx is not None else ""

        request_block = {
            "system_prompt_preview": _trunc(
                prompt_data.get("system_prompt", ""), 200
            ),
            "context_preview": _trunc(context_json, 500),
            "context_full_truncated": len(context_json) > 500,
            "max_tokens": prompt_data.get("max_tokens"),
            "temperature": prompt_data.get("temperature"),
        }

    response_block: dict[str, Any] = {
        "raw": raw_response or "",
        "error": error,
    }
    if not error and parsed_response is not None:
        response_block["parsed"] = parsed_response

    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "task": task,
        "request": request_block,
        "response": response_block,
    }

    try:
        line = json.dumps(record, ensure_ascii=False, default=str)
        fd.write(line + "\n")
        fd.flush()
    except Exception as exc:
        _log.warning("AI audit: write failed: %s", exc)


__all__ = ["log", "close"]