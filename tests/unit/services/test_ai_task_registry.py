"""Guard: every AI task the code asks for exists in the prompt registry.

Why: ``MCPBackend.generate`` looks the task up in ``REGISTRY`` and returns ``None`` for
an unknown name. Nothing failed loudly, so Recon spent months calling
``generate("discovery", ...)`` for a task that was never registered — the AI half of
Recon silently produced zero candidates. A string literal is checkable, so it is
checked here instead of being discovered by a user.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pentool.services.ai.prompts import REGISTRY

ROOT = Path(__file__).resolve().parents[3]

#: Where AI tasks are requested. ``pro`` is optional (submodule may be absent).
SOURCE_DIRS = [ROOT / "pentool", ROOT / "pro" / "pentool"]

#: ``backend.generate("task_name", …)`` and ``await backend.generate("task_name")``.
CALL = re.compile(r'\.generate\(\s*"([a-z][a-z0-9_]*)"')


def _python_files() -> list[Path]:
    files: list[Path] = []
    for directory in SOURCE_DIRS:
        if directory.is_dir():
            files.extend(sorted(directory.rglob("*.py")))
    return files


def _requested_tasks() -> dict[str, list[str]]:
    """Task name → files that request it."""
    usage: dict[str, list[str]] = {}
    for path in _python_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for name in CALL.findall(text):
            usage.setdefault(name, []).append(path.relative_to(ROOT).as_posix())
    return usage


def test_requested_tasks_are_registered() -> None:
    unknown = {name: files for name, files in _requested_tasks().items() if name not in REGISTRY}
    assert not unknown, "AI tasks requested from code but missing in pentool/services/ai/prompts.py: " + ", ".join(
        f"{name} ({', '.join(files)})" for name, files in sorted(unknown.items())
    )


def test_registry_is_not_empty() -> None:
    assert REGISTRY, "the AI prompt registry is empty — every generate() call would fail"


@pytest.mark.parametrize("task_name", sorted(REGISTRY))
def test_task_has_a_usable_prompt(task_name: str) -> None:
    task = REGISTRY[task_name]
    assert task.system_prompt.strip(), f"{task_name}: empty system prompt"
    assert 0 <= task.temperature <= 1, f"{task_name}: temperature out of range"
    assert task.max_tokens > 0, f"{task_name}: max_tokens must be positive"
