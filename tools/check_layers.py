#!/usr/bin/env python3
"""Проверка нарушений правила слоёв (Layer Rule) в проекте PenTool.

Правило:
    utils ← core ← modules ← api ← tui / cli / plugins

Запрещённые импорты:
    - tui/ → modules/  (должно быть через api/)
    - tui/ → core/     (через api/ или допустимо только get_config/get_logger)
    - modules/ → tui/
    - modules/ → api/
    - core/ → modules/
    - utils/ → любой другой слой pentool
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


# Корень пакета
PACKAGE_ROOT = Path(__file__).parent.parent / "pentool"

# Правила: (слой, запрещённые импорты из этого слоя)
FORBIDDEN_IMPORTS: list[tuple[str, list[str]]] = [
    # tui/ не должен импортировать modules/ напрямую
    ("tui", ["pentool.modules"]),
    # modules/ не должен импортировать tui/, api/, cli/
    ("modules", ["pentool.tui", "pentool.api", "pentool.cli"]),
    # core/ не должен импортировать modules/, tui/, api/
    ("core", ["pentool.modules", "pentool.tui", "pentool.api", "pentool.cli"]),
    # utils/ не должен импортировать ничего из pentool (кроме utils/ самого себя)
    ("utils", ["pentool.modules", "pentool.tui", "pentool.api", "pentool.cli", "pentool.core", "pentool.storage"]),
    # storage/ не должен импортировать modules/, tui/, api/
    ("storage", ["pentool.modules", "pentool.tui", "pentool.api", "pentool.cli"]),
]


def get_imports(file_path: Path) -> list[str]:
    """Извлечь все импортируемые модули из Python-файла."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as e:
        print(f"  ⚠️  SyntaxError в {file_path}: {e}")
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def check_file(file_path: Path, forbidden: list[str]) -> list[str]:
    """Проверить один файл. Вернуть список нарушений."""
    violations: list[str] = []
    imported = get_imports(file_path)
    for imp in imported:
        for forbidden_prefix in forbidden:
            if imp == forbidden_prefix or imp.startswith(forbidden_prefix + "."):
                violations.append(f"  ❌ {file_path.relative_to(PACKAGE_ROOT.parent)}: "
                                   f"запрещённый импорт '{imp}' (нарушает правило слоёв)")
    return violations


def main() -> int:
    """Запустить проверку. Вернуть 0 если нарушений нет, 1 иначе."""
    all_violations: list[str] = []
    checked_files = 0

    for layer, forbidden in FORBIDDEN_IMPORTS:
        layer_dir = PACKAGE_ROOT / layer
        if not layer_dir.exists():
            continue

        for py_file in layer_dir.rglob("*.py"):
            if "__pycache__" in py_file.parts:
                continue
            checked_files += 1
            violations = check_file(py_file, forbidden)
            all_violations.extend(violations)

    print(f"🔍 Проверено файлов: {checked_files}")

    if all_violations:
        print(f"\n💥 Нарушений правила слоёв: {len(all_violations)}\n")
        for v in all_violations:
            print(v)
        print("\nИсправьте нарушения согласно docs/architecture.md")
        return 1
    else:
        print("✅ Нарушений правила слоёв не найдено.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
