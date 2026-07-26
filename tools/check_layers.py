#!/usr/bin/env python3
"""Check for layer rule violations in the PenTool project.

Rule:
    utils ← core ← modules ← api ← tui / cli / plugins

Forbidden imports:
    - tui/ → modules/  (must go through api/)
    - tui/ → core/     (through api/, or only get_config/get_logger are allowed)
    - modules/ → tui/
    - modules/ → api/
    - core/ → modules/
    - utils/ → any other pentool layer
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


# Package root
PACKAGE_ROOT = Path(__file__).parent.parent / "pentool"

# Rules: (layer, forbidden imports from that layer)
FORBIDDEN_IMPORTS: list[tuple[str, list[str]]] = [
    # tui/ must not import modules/ directly
    ("tui", ["pentool.modules"]),
    # modules/ must not import tui/, api/, cli/
    ("modules", ["pentool.tui", "pentool.api", "pentool.cli"]),
    # core/ must not import modules/, tui/, api/
    ("core", ["pentool.modules", "pentool.tui", "pentool.api", "pentool.cli"]),
    # utils/ must not import anything from pentool (except utils/ itself)
    ("utils", ["pentool.modules", "pentool.tui", "pentool.api", "pentool.cli", "pentool.core", "pentool.storage"]),
    # storage/ must not import modules/, tui/, api/
    ("storage", ["pentool.modules", "pentool.tui", "pentool.api", "pentool.cli"]),
]


def get_imports(file_path: Path) -> list[str]:
    """Extract all imported modules from a Python file."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as e:
        print(f"  ⚠️  SyntaxError in {file_path}: {e}")
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
    """Check a single file. Return a list of violations."""
    violations: list[str] = []
    imported = get_imports(file_path)
    for imp in imported:
        for forbidden_prefix in forbidden:
            if imp == forbidden_prefix or imp.startswith(forbidden_prefix + "."):
                violations.append(f"  ❌ {file_path.relative_to(PACKAGE_ROOT.parent)}: "
                                   f"forbidden import '{imp}' (violates layer rule)")
    return violations


def main() -> int:
    """Run the check. Return 0 if no violations found, 1 otherwise."""
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

    print(f"🔍 Files checked: {checked_files}")

    if all_violations:
        print(f"\n💥 Layer rule violations: {len(all_violations)}\n")
        for v in all_violations:
            print(v)
        print("\nFix violations according to docs/architecture.md")
        return 1
    else:
        print("✅ No layer rule violations found.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
