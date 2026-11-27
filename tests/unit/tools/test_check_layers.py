"""Layer guard: forbidden imports and the TUI service allowlist (step 10).

`tools/check_layers.py` walks the package; the decision itself is the pure `check_imports`,
so these tests exercise the rule without touching the tree: forbidden prefixes (exact and
dotted), the TUI service allowlist, and the fact that the allowlist applies to the TUI layer
only.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[3] / "tools" / "check_layers.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_layers", _TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


check_layers = _load()
FORBIDDEN = ["pentool.modules", "pentool.storage", "pentool.core.db_schema"]
ALLOWED = ("pentool.services.ai", "pentool.services.proxy_service", "pentool.services.project_settings")


def test_forbidden_import_is_reported_exactly_and_as_a_package() -> None:
    violations = check_layers.check_imports(["pentool.modules", "pentool.modules.scanner"], FORBIDDEN)
    assert len(violations) == 2
    assert all("forbidden import" in v for v in violations)


def test_untouched_layers_are_not_reported() -> None:
    imports = ["pentool.api.repeater_api", "pentool.core.config", "pentool.services.ai.factory"]
    assert check_layers.check_imports(imports, FORBIDDEN, ALLOWED) == []


def test_schema_module_is_forbidden_for_the_tui_layer() -> None:
    violations = check_layers.check_imports(["pentool.core.db_schema"], FORBIDDEN)
    assert violations, "core.db_schema — это слой данных, экран не должен импортировать его напрямую"


def test_service_outside_the_allowlist_is_reported() -> None:
    violations = check_layers.check_imports(["pentool.services.scan_service"], FORBIDDEN, ALLOWED)
    assert len(violations) == 1
    assert "allowlist" in violations[0]


def test_allowlisted_service_and_its_submodules_pass() -> None:
    imports = ["pentool.services.ai", "pentool.services.ai.factory", "pentool.services.project_settings"]
    assert check_layers.check_imports(imports, FORBIDDEN, ALLOWED) == []


def test_allowlist_does_not_apply_to_other_layers() -> None:
    # Without `allowed_services`, services are not the rule's business: other layers have
    # their own forbidden lists.
    assert check_layers.check_imports(["pentool.services.scan_service"], FORBIDDEN) == []


def test_services_import_with_outside_prefix_is_still_checked() -> None:
    violations = check_layers.check_imports(["pentool.services_extra"], FORBIDDEN, ALLOWED)
    assert violations == [], "похожее имя — не сервис; правило смотрит только на pentool.services"
