"""Сохранение/загрузка проекта в JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def save_project(path: str | Path, project_data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        **project_data,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_project(path: str | Path) -> tuple[dict[str, Any], str]:
    path = Path(path)
    if not path.exists():
        return {}, f"File not found: {path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {}, f"JSON parse error: {e}"
    return data, ""
