"""The feature catalogue describes exactly what the code gates and nothing else.

Two failure modes are guarded here:

* a gate in the code asks for a feature the catalogue does not know (typo, or a feature
  that was renamed) — the check silently returns False and the customer paid for nothing;
* the catalogue advertises a feature nothing checks — the site then promises what the
  product does not deliver.

The previous revision of `core/features.py` invented `lite`/`medium`/`full` plans and 17
feature constants, of which the code used one. This test makes that impossible to repeat.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from pentool.core.features import (
    FEATURES,
    LIMITS,
    PLAN_ORDER,
    get_features_for_plan,
    get_limit,
    get_plan_info,
    has_feature,
)

ROOT = Path(__file__).resolve().parents[3]
CODE_ROOTS = (ROOT / "pentool", ROOT / "pro" / "pentool")

#: PRO features are gated inside the private submodule. A free checkout (CI has no
#: access to `DrXOps/pentool-pro`) cannot see those gates, so the "every feature is
#: checked somewhere" rule is only decidable with both trees present.
PRO_TREE = ROOT / "pro" / "pentool"

GATE_PATTERN = re.compile(r"""(?:has_feature|require_feature)\(\s*["']([a-z0-9_]+)["']""")


def _gates_used_in_code() -> dict[str, list[str]]:
    """Every feature string the application asks for, with the files asking for it."""
    gates: dict[str, list[str]] = {}
    for base in CODE_ROOTS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name not in {"has_feature", "require_feature"}:
                    continue
                # Skip the definitions in core/features.py and core/license.py.
                if path.name in {"features.py", "license.py"}:
                    continue
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    gates.setdefault(node.args[0].value, []).append(path.relative_to(ROOT).as_posix())
    return gates


def test_only_real_plans_exist() -> None:
    assert PLAN_ORDER == ("free", "pro", "enterprise")
    for invented in ("lite", "medium", "full", "team"):
        assert invented not in PLAN_ORDER, f"{invented!r} was a plan that never shipped"


def test_every_gate_in_code_is_declared() -> None:
    gates = _gates_used_in_code()
    unknown = sorted(set(gates) - set(FEATURES))
    assert not unknown, (
        "the code gates features that the catalogue does not declare (the gate silently "
        f"returns False): {unknown} — used in {[gates[name] for name in unknown]}"
    )


def test_every_declared_feature_is_checked_by_the_code() -> None:
    if not PRO_TREE.is_dir():
        pytest.skip("PRO submodule is not checked out: its feature gates live there")
    gates = _gates_used_in_code()
    unused = sorted(set(FEATURES) - set(gates))
    assert not unused, (
        f"the catalogue advertises features nothing checks — either implement the gate or remove the entry: {unused}"
    )


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_feature_unlocks_for_pro_and_enterprise_only(feature: str) -> None:
    assert has_feature(feature, "free") is False
    assert has_feature(feature, "pro") is True
    assert has_feature(feature, "enterprise") is True


def test_unknown_plan_or_feature_unlocks_nothing() -> None:
    assert has_feature("payloads_pro", "lite") is False
    assert has_feature("payloads_pro", "") is False
    assert has_feature("payloads_pro", None) is False  # type: ignore[arg-type]
    assert has_feature("no_such_feature", "enterprise") is False


def test_limits_match_the_intruder_ui() -> None:
    """The numbers the Intruder shows must come from the catalogue, not from literals."""
    assert get_limit("intruder_max_threads", "free") == 5
    assert get_limit("intruder_max_threads", "pro") == 200
    assert get_limit("intruder_min_delay_ms", "free") == 100
    assert get_limit("intruder_min_delay_ms", "pro") == 0

    screen_source = (ROOT / "pentool/tui/screens/intruder/screen.py").read_text(encoding="utf-8")
    assert "get_limit(" in screen_source, "Intruder must read its limits from core/features.py"
    assert "Max 5" not in screen_source, "the free thread cap must not be a literal in the screen"
    assert "Min 100" not in screen_source, "the free delay floor must not be a literal in the screen"


def test_plan_info_is_consistent() -> None:
    free = get_plan_info("free")
    pro = get_plan_info("pro")
    assert free["features_count"] == 0
    assert pro["features_count"] == len(FEATURES)
    assert set(pro["limits"]) == set(LIMITS)
    assert len(get_features_for_plan("enterprise")) == len(FEATURES)
