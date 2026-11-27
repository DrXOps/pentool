#!/usr/bin/env python3
"""Check for layer rule violations in the PenTool project.

Rule:
    utils ← core ← modules ← api ← services ← tui / cli / plugins

Forbidden imports:
    - tui/ → modules/    (must go through api/)
    - tui/ → storage/    (through services/)
    - tui/ → core/db_schema (schema belongs to services; `services/project_settings.py` is the door)
    - tui/ → services/* outside the façade allowlist below
    - modules/ → tui/, api/, cli/
    - core/ → modules/, tui/, api/, cli/
    - utils/ → any other pentool layer
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Package root
PACKAGE_ROOT = Path(__file__).parent.parent / "pentool"

#: Service modules the TUI may import directly. Everything else in `pentool.services` is an
#: internal part of a façade: a screen that needs it gets a method on the façade, and this
#: list is edited deliberately (the guard fails on any other `pentool.services.*` import).
TUI_ALLOWED_SERVICES: tuple[str, ...] = (
    "pentool.services.ai",  # the AI façade (settings, factory, provider selection)
    "pentool.services.tech_detector",
    "pentool.services.proxy_service",
    "pentool.services.repeater_service",
    "pentool.services.project_settings",
)

# Rules: (layer, forbidden imports from that layer)
FORBIDDEN_IMPORTS: list[tuple[str, list[str]]] = [
    # tui/ must not import modules/ or storage/ directly: modules via api/, storage via
    # services/ (the screen talks to a service, the service owns the database). The schema
    # module is the data layer too — the service façade is `services/project_settings.py`.
    ("tui", ["pentool.modules", "pentool.storage", "pentool.core.db_schema"]),
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


def check_imports(
    imports: list[str],
    forbidden: list[str],
    allowed_services: tuple[str, ...] | None = None,
) -> list[str]:
    """Pure rule: violations for forbidden prefixes and for service imports outside the list.

    `allowed_services` is set only for the `tui` layer; with it, any `pentool.services.*`
    import not covered by the allowlist is a violation too.
    """
    violations: list[str] = []
    for imp in imports:
        if any(imp == prefix or imp.startswith(prefix + ".") for prefix in forbidden):
            violations.append(f"forbidden import '{imp}' (violates layer rule)")
            continue
        if allowed_services is not None and imp.startswith("pentool.services"):
            is_service = imp == "pentool.services" or imp.startswith("pentool.services.")
            if is_service and not any(imp == allowed or imp.startswith(allowed + ".") for allowed in allowed_services):
                violations.append(f"service '{imp}' is not in the TUI allowlist (add a façade method)")
    return violations


def check_file(
    file_path: Path,
    forbidden: list[str],
    allowed_services: tuple[str, ...] | None = None,
) -> list[str]:
    """Check a single file. Return a list of violations."""
    imported = get_imports(file_path)
    return [
        f"  ❌ {file_path.relative_to(PACKAGE_ROOT.parent)}: {violation}"
        for violation in check_imports(imported, forbidden, allowed_services)
    ]


def main() -> int:
    """Run the check. Return 0 if no violations found, 1 otherwise."""
    all_violations: list[str] = []
    checked_files = 0

    for layer, forbidden in FORBIDDEN_IMPORTS:
        layer_dir = PACKAGE_ROOT / layer
        if not layer_dir.exists():
            continue
        allowed_services = TUI_ALLOWED_SERVICES if layer == "tui" else None

        for py_file in layer_dir.rglob("*.py"):
            if "__pycache__" in py_file.parts:
                continue
            checked_files += 1
            violations = check_file(py_file, forbidden, allowed_services)
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
