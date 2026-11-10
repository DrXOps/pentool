"""Regression guard: screens must inherit the mixin that provides the helpers they call.

``AppMixin`` supplies ``err``, ``_get_proxy``, ``_get_proxy_api``, ``_get_db_path``
and ``_send_to_decoder``. Six screens (``TargetScreen``, ``DashboardScreen``,
``ComparerScreen``, ``DecoderScreen``, ``SequencerScreen``, ``SettingsScreen``)
called ``self.err(...)`` without it, so **every error path raised
``AttributeError``** and masked the exception it was trying to report — the same
"written but unreachable" defect class as F-041..F-044, one layer below. The
calls sat in ``except`` branches, which no happy-path test reaches.

This guard imports every ``pentool.tui`` class and checks that each ``self.<helper>``
call resolves on the class MRO. A plain mixin (``RequestContextMenuMixin``) is
skipped: it is only ever used *through* a concrete screen that supplies the
helper, so its own MRO legitimately lacks them; only ``Screen``/``Widget``
subclasses are held to the rule.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest
from textual.widget import Widget

import pentool

# Attributes supplied by AppMixin (pentool/tui/mixins/app_mixin.py).
_APP_MIXIN_HELPERS = frozenset({"err", "_get_proxy", "_get_proxy_api", "_get_db_path", "_send_to_decoder"})


def _screen_classes() -> list[type[Widget]]:
    """Every importable Widget subclass under ``pentool.tui``."""
    classes: list[type[Widget]] = []
    seen: set[type[Widget]] = set()
    for info in pkgutil.walk_packages(pentool.__path__, "pentool."):
        if not info.name.startswith("pentool.tui"):
            continue
        try:
            module = importlib.import_module(info.name)
        except Exception:  # pragma: no cover - optional/PRO packages
            continue
        for member in vars(module).values():
            if (
                inspect.isclass(member)
                and issubclass(member, Widget)
                and member.__module__.startswith("pentool.tui")
                and member not in seen
            ):
                seen.add(member)
                classes.append(member)
    return classes


@pytest.fixture(scope="module")
def helper_calls_per_class() -> dict[type[Widget], set[str]]:
    """Map each TUI widget class to the AppMixin helpers it calls on ``self``.

    The AST is walked rather than ``inspect.getsource`` so the check survives
    classes whose ``__init__`` cannot run; ``ast.walk`` over the class body also
    picks up helpers used inside nested comprehensions/lambdas.
    """
    import ast
    from pathlib import Path

    calls: dict[type[Widget], set[str]] = {}
    root = Path(pentool.__file__).parent / "tui"
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            used = {
                n.func.attr
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "self"
                and n.func.attr in _APP_MIXIN_HELPERS
            }
            if not used:
                continue
            for cls in _screen_classes():
                if cls.__name__ == node.name and cls.__module__.endswith(path.stem):
                    calls.setdefault(cls, set()).update(used)
    return calls


def test_screens_that_call_app_mixin_helpers_inherit_them(
    helper_calls_per_class: dict[type[Widget], set[str]],
) -> None:
    """A helper call that resolves on no base class raises ``AttributeError`` at runtime."""
    problems: list[str] = []
    for cls, helpers in helper_calls_per_class.items():
        missing = sorted(h for h in helpers if not hasattr(cls, h))
        if missing:
            problems.append(
                f"{cls.__module__}.{cls.__name__} calls self.{', self.'.join(missing)} "
                "but inherits no class that defines it"
            )
    assert not problems, (
        "Screens call AppMixin helpers they do not inherit (add AppMixin to the bases "
        "or define the helper locally):\n  " + "\n  ".join(problems)
    )


def test_known_screens_have_app_mixin() -> None:
    """Explicit pin on the six screens this finding fixed.

    Kept separate from the generic check so the exact regression is named: a
    future base-class reshuffle that drops ``AppMixin`` fails here with the
    screen's name, not a generic MRO dump.
    """
    expected = (
        "TargetScreen",
        "DashboardScreen",
        "ComparerScreen",
        "DecoderScreen",
        "SequencerScreen",
        "SettingsScreen",
    )
    by_name = {cls.__name__: cls for cls in _screen_classes()}
    missing = [name for name in expected if not hasattr(by_name.get(name, object), "err")]
    assert not missing, f"screens lost AppMixin (self.err would raise): {missing}"
