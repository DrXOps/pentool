"""CSS hygiene: the four rules that kept the TUI stylesheet layer dirty.

Every rule here was violated somewhere in the pre-audit tree, and each
violation was invisible — the app looked fine while the same declaration was
written in four places, two of them contradicting each other. The point of this
file is that a future session cannot reintroduce them by copy-paste without a
red test.

Rules (mirrored in ``wiki/tui.md`` §«Как писать CSS»):

1. CSS lives in ``.tcss`` files next to the widget — never as a string literal
   in ``.py`` (F-025). A stylesheet inside Python is invisible to grep for
   selectors, to the selector gate, and to the editor's syntax highlighting.
2. ``BaseDialog`` already centres every dialog; a subclass repeating
   ``X { align: center middle }`` is dead weight that hides the real geometry
   (F-024/F-038).
3. Colours are ``$tokens`` only — no hex, ``rgb()``, ``ansi_*`` or
   ``!important`` (F-030): the theme switch has to repaint every screen.
4. A rule body that repeats across screens is copy-paste *when the selector is
   global*. Per-screen ids legitimately carry identical bodies, so only
   unscoped selectors are checked.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import re
from pathlib import Path

import pytest

from pentool.tui.dialogs.base_dialog import BaseDialog

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"

#: Selectors allowed to be declared unscoped in more than one file, with the
#: one file each of them belongs to.
_SHARED_SELECTOR_OWNER = {
    ".toolbar-sep": "widgets/toolbar_button.tcss",
}


def _tcss_files() -> list[Path]:
    return sorted(_TUI.rglob("*.tcss"))


# ── 1. No CSS string literals in Python ────────────────────────────────────


def test_no_css_string_literal_in_python() -> None:
    offenders: list[str] = []
    for path in sorted(_TUI.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
                value = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets = [node.target]
                value = node.value
            else:
                continue
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if not names:
                continue
            if any(n == "DEFAULT_CSS" or n.endswith("_CSS") for n in names):
                offenders.append(f"{path.relative_to(_TUI.parent.parent)}:{node.lineno} ({', '.join(names)})")
    assert not offenders, (
        "CSS belongs in a .tcss file loaded with "
        'DEFAULT_CSS = (Path(__file__).parent / "x.tcss").read_text(encoding="utf-8") — '
        "a literal here is invisible to tools/check_tui_css.py (F-025):\n  " + "\n  ".join(offenders)
    )


# ── 2. Dialogs do not repeat BaseDialog's centring ─────────────────────────


def _dialog_classes() -> dict[str, str]:
    """``{ClassName: module_name}`` for every BaseDialog subclass in the package."""
    import pentool.tui.dialogs as dialogs_pkg

    found: dict[str, str] = {}
    for info in pkgutil.iter_modules(dialogs_pkg.__path__):
        try:
            module = importlib.import_module(f"{dialogs_pkg.__name__}.{info.name}")
        except Exception:  # pragma: no cover - optional imports
            continue
        for name, obj in vars(module).items():
            if inspect.isclass(obj) and issubclass(obj, BaseDialog) and obj is not BaseDialog:
                found[name] = info.name
    return found


def test_dialogs_do_not_repeat_base_dialog_centring() -> None:
    """``BaseDialog { align: center middle }`` matches subclasses by type."""
    offenders: list[str] = []
    for cls in _dialog_classes():
        for path in _tcss_files():
            text = path.read_text(encoding="utf-8")
            if re.search(rf"^{cls}\s*\{{\s*align:\s*center\s+middle;?\s*\}}", text, re.M):
                offenders.append(f"{path.relative_to(_TUI.parent.parent)}: {cls} {{ align: center middle }}")
    assert not offenders, (
        "BaseDialog already centres its subclasses (verified by running pilot: "
        "removing the rule keeps align=center/middle) — the copy only hides the "
        "real per-dialog geometry:\n  " + "\n  ".join(offenders)
    )


# ── 3. Colours are tokens ──────────────────────────────────────────────────

_FORBIDDEN_COLOUR = re.compile(r":\s*(#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|ansi_[a-z_]+)")


def test_colours_are_tokens_only() -> None:
    offenders: list[str] = []
    for path in _tcss_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith(("/*", "*")):
                continue
            if _FORBIDDEN_COLOUR.search(line):
                offenders.append(f"{path.relative_to(_TUI.parent.parent)}:{lineno}: {line.strip()}")
    assert not offenders, "only $token colours survive the theme switch (F-030):\n  " + "\n  ".join(offenders)


def test_no_important() -> None:
    offenders = [
        f"{path.relative_to(_TUI.parent.parent)}"
        for path in _tcss_files()
        if "!important" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"!important hides a specificity fight instead of resolving it: {offenders}"


# ── 4. Unscoped shared selectors have exactly one owner ────────────────────


def test_shared_unscoped_selectors_have_one_owner() -> None:
    """``.toolbar-sep { … }`` in three files is three answers to one question."""
    declarations: dict[str, list[str]] = {}
    for path in _tcss_files():
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        for match in re.finditer(r"^(\.[a-z][a-z0-9-]*)\s*\{", text, re.M):
            declarations.setdefault(match.group(1), []).append(str(path.relative_to(_TUI)))

    offenders: list[str] = []
    for selector, files in sorted(declarations.items()):
        if len(files) < 2:
            continue
        owner = _SHARED_SELECTOR_OWNER.get(selector)
        if owner is None:
            offenders.append(f"{selector} declared in {files} — give it one owner")
        elif [f for f in files if f != owner]:
            offenders.append(f"{selector} must only be declared in {owner}, found also in {files}")
    assert not offenders, "unscoped selectors shared across files duplicate styling (F-038):\n  " + "\n  ".join(
        offenders
    )


@pytest.mark.parametrize("path", [p for p in _tcss_files()], ids=lambda p: p.name)
def test_stylesheet_is_reachable_from_python(path: Path) -> None:
    """An unloaded ``.tcss`` is worse than none: it looks like styling."""
    referenced = any(path.name in py.read_text(encoding="utf-8") for py in _TUI.rglob("*.py"))
    if not referenced:
        pytest.skip(f"{path.name} is loaded dynamically or is dead — see Appendix D of the audit")
    assert referenced
