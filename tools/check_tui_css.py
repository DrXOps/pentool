#!/usr/bin/env python3
"""Cross-check TUI CSS selectors against the Python that builds the DOM.

Why this exists
---------------
CSS and Python are written apart, so nothing catches the case where a selector
addresses an ``id``/``class`` no widget ever sets. REPORT.md F-008 documented
eleven such selectors: three were plain type mismatches (``.attack-type-desc``
in CSS vs ``id="attack-type-desc-<tab>"`` in Python — those styles never
applied), the rest were dead rules copied between screens. A grep after the fix
would pass, but the next copy-paste would silently re-introduce the same class
of bug — hence a mechanical check.

What it checks (all selectors, no allowlist)
--------------------------------------------
1. Every class token (``.foo``) appears in a ``classes=`` literal or in
   ``add_class``/``remove_class``/``set_classes``/``toggle_class`` anywhere in
   ``pentool/tui``.
2. Every id selector (``#foo``) appears as an ``id=`` literal, in a helper that
   builds ids, or as an attribute match ``[id^="prefix"]`` whose prefix an
   ``id=`` value starts with. Per-tab ids are built as ``f"{suffix}-{tab_id}"``
   (``IntruderScreen._wid``), so only the leading literal can be traced — hence
   prefix matching rather than requiring an exact id.
3. Every widget type selector (``IntruderFilterBar``, ``HttpView``) resolves to
   a class name defined in ``pentool`` (or a Textual base we cannot see, in
   which case it is reported as an unknown only if it also is not a known
   Textual widget).

Exit codes: 0 — clean, 1 — problems found (the CI gate).

Usage::

    python tools/check_tui_css.py            # exit 1 on problems
    python tools/check_tui_css.py --list     # print the extracted vocabularies
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import importlib
import pkgutil
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TUI = ROOT / "pentool" / "tui"

# Extract the CSS selector part before ``{``.
_SELECTOR_RE = re.compile(r"^\s*([^\n{}]+?)\s*\{", re.M)
# A token in a compound selector: tag, #id, .class, or a pseudo-class.
_TOKEN_RE = re.compile(
    r"""
    (?P<tag>[A-Za-z][A-Za-z0-9_]*)        # widget type / pseudo class name
    |\#(?P<id>[A-Za-z0-9_\-]+)            # id
    |\.(?P<cls>[A-Za-z\-][A-Za-z0-9_\-]*)  # class (may start with '-' as in .-on)
    """,
    re.X,
)
_ATTR_RE = re.compile(r'\[\s*id(?P<op>\^=|\*=|$=|=)\s*"(?P<value>[^"]*)"\s*\]')
# Textual pseudo-classes / pseudo-elements that are not widget types.
_PSEUDO = {
    "hover",
    "focus",
    "focus-within",
    "blur",
    "disabled",
    "enabled",
    "first-child",
    "last-child",
    "even",
    "odd",
    "dark",
    "light",
    "ansi",
    "nocolor",
    "inline",
    "initial",
    "active",
}
# Textual pseudo-elements — the part after ``::`` or the recognised single-colon
# spacing/border names. Anything after one of these markers is not a tag.
_PSEUDO_ELEMENT = {
    "scrollbar",
    "scrollbar-corner",
    "scrollbar-gutter",
    "scrollbar-thumb",
    "scrollbar-track",
    "block-cursor",
    "cursor",
    "background",
    "link",
}
_DEVNULL = open("/dev/null", "w")  # noqa: SIM115 - process-lifetime sink
_CLASS_ATTRS = {"classes"}
# Severity names shared by app.notify() and CustomNotifyCard; each maps to the
# ``-<severity>`` class the card sets (pentool/tui/widgets/custom_notify.py).
_SEVERITIES = (
    "information",
    "success",
    "warning",
    "error",
    "critical",
)  # constructor kwarg carrying class literals
_CLASS_METHODS = {"add_class", "remove_class", "set_class", "set_classes", "toggle_class"}
_ID_KW = "id"


def _iter_tcss() -> list[Path]:
    return sorted(TUI.rglob("*.tcss"))


def _strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _split_selector_list(selector: str) -> list[str]:
    """Split a comma-separated selector list into individual selectors."""
    return [part.strip() for part in selector.split(",") if part.strip()]


def _loaded_tcss_names() -> set[str]:
    """Names of ``.tcss`` files some Python module actually reads.

    Textual only applies a stylesheet a class loads (``DEFAULT_CSS = Path(...).
    read_text()`` or ``CSS_PATH``). Two files in the repo are loaded by nobody
    (``menu.tcss``, ``menu_bar.tcss`` — Appendix D), so their selectors cannot
    bite and checking them would only produce noise.
    """
    names: set[str] = set()
    for path in TUI.rglob("*.py"):
        for match in re.finditer(r"([A-Za-z0-9_\-]+\.tcss)", path.read_text(encoding="utf-8")):
            names.add(match.group(1))
    return names


def collect_css(selectors_out: list[tuple[str, int, str]]) -> list[str]:
    """Fill *selectors_out* with ``(file, lineno, selector)`` tuples.

    Returns the names of ``.tcss`` files nothing loads, so the caller can warn
    instead of treating their selectors as live.
    """
    loaded = _loaded_tcss_names()
    unloaded: list[str] = []
    for path in _iter_tcss():
        if path.name not in loaded:
            unloaded.append(path.name)
            continue
        raw = _strip_comments(path.read_text(encoding="utf-8"))
        for match in _SELECTOR_RE.finditer(raw):
            lineno = raw[: match.start(1)].count("\n") + 1
            for sel in _split_selector_list(match.group(1)):
                selectors_out.append((str(path.relative_to(ROOT)), lineno, sel))
    return unloaded


def _tokens(selector: str) -> tuple[set[str], set[str], set[str], set[str]]:
    """Return (tags, ids, classes, attr_prefixes) from one selector.

    Attribute selectors (``Static[id^="attack-type-desc-"]``) are blanked out
    before tokenising so ``attack``/``type``/``desc`` are not read as widget
    types. Pseudo-class/element suffixes are dropped: a name right after ``:``
    or ``::`` is never the widget type.
    """
    tags: set[str] = set()
    ids: set[str] = set()
    classes: set[str] = set()
    prefixes: set[str] = set()

    for m in _ATTR_RE.finditer(selector):
        prefixes.add(m.group("value"))
    # Blank attributes to spaces (keep indices so no other offsets matter).
    bare = _ATTR_RE.sub(lambda m: " " * len(m.group(0)), selector)

    for m in _TOKEN_RE.finditer(bare):
        if m.group("id"):
            ids.add(m.group("id"))
        elif m.group("cls"):
            classes.add(m.group("cls"))
        elif m.group("tag"):
            tag = m.group("tag")
            if tag in _PSEUDO or tag in _PSEUDO_ELEMENT:
                continue
            before = bare[: m.start()].rstrip()
            if before.endswith("::") or before.endswith(":"):
                continue
            tags.add(tag)
    return tags, ids, classes, prefixes


def _string_literals(tree: ast.AST) -> tuple[set[str], set[str], set[str]]:
    """Return (id_literals, id_prefixes, class_tokens) found in a module AST.

    ``id_prefixes`` come from f-strings: ``f"{suffix}-{tab_id}"`` yields the
    leading literal only, which is what an attribute prefix selector matches.
    """
    ids: set[str] = set()
    prefixes: set[str] = set()
    classes: set[str] = set()

    for node in ast.walk(tree):
        # keyword argument id="..."
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            for kw in node.keywords:
                if kw.arg == _ID_KW:
                    for value in _constant_strings(kw.value):
                        ids.add(value)
                if kw.arg in _CLASS_ATTRS:
                    # ``classes=`` is often a conditional expression
                    # (``"a" if cond else "b"``) — take every string in it.
                    for value in _constant_strings(kw.value):
                        classes.update(value.split())
            if func_name in _CLASS_METHODS:
                for arg in node.args:
                    for value in _constant_strings(arg):
                        classes.update(value.split())
        # dict-style kwargs: compose({...}) or dict(id="..."), rare but cheap.
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                    continue
                if k.value == _ID_KW and isinstance(v, ast.Constant) and isinstance(v.value, str):
                    ids.add(v.value)
                if k.value in _CLASS_ATTRS and isinstance(v, ast.Constant) and isinstance(v.value, str):
                    classes.update(v.value.split())
        # f-strings: collect the leading constant prefix and the full constants.
        if isinstance(node, ast.JoinedStr) and node.values:
            first = node.values[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                prefixes.add(first.value)
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    ids.add(part.value)
        # string constants used with .format(id=...) — treat as prefixes.
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.endswith("-") or node.value.endswith("_"):
                prefixes.add(node.value)
    return ids, prefixes, classes


def _constant_strings(node: ast.AST) -> list[str]:
    """Every string constant inside *node* (walks conditionals, tuples, f-strings)."""
    out: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            out.append(child.value)
    return out


def collect_python() -> tuple[set[str], set[str], set[str], set[str], set[int]]:
    """Return (ids, id_prefixes, classes, widget_type_names) from pentool/tui."""
    ids: set[str] = set()
    prefixes: set[str] = set()
    classes: set[str] = set()
    types: set[str] = set()
    id_arg_indexes: set[int] = set()
    id_calls: list[tuple[int, str]] = []  # (positional index, literal value)
    for path in sorted(TUI.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover - defensive
            print(f"ERROR: cannot parse {path}: {exc}", file=sys.stderr)
            continue
        i, p, c = _string_literals(tree)
        ids |= i
        prefixes |= p
        classes |= c
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                types.add(node.name)
                # A ``_Private`` widget styled by its public type name: the
                # module exports the alias (``Left = _Left``), and the CSS
                # selector uses ``Left``. Accept the de-underscored name too.
                if node.name.startswith("_") and not node.name.startswith("__"):
                    types.add(node.name.lstrip("_"))
            # Widgets imported under aliases (``NiceCheckbox as Checkbox``)
            # still count as known types under their alias.
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    types.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    types.add(alias.asname or alias.name.split(".")[-1])
            # Custom constructors: ``ToolbarButton(label, btn_id)`` forwards its
            # second positional argument into ``super().__init__(id=btn_id)``.
            # Record that index so ``ToolbarButton("Save", "settings-save")``
            # yields the id ``settings-save``.
            if isinstance(node, ast.FunctionDef) and node.name == "__init__":
                id_arg_indexes |= _super_id_arg_index(node)
            if isinstance(node, ast.Call):
                for idx, arg in enumerate(node.args):
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        id_calls.append((idx, arg.value))
    for idx, value in id_calls:
        if idx in id_arg_indexes:
            ids.add(value)
    # Notification severities become ``-<severity>`` classes (custom_notify.py:
    # ``SEVERITIES = ("information", …)`` and ``_card.add_class(f"-{severity}")``).
    for severity in _SEVERITIES:
        classes.add(f"-{severity}")
    return ids, prefixes, classes, types, id_arg_indexes


def _super_id_arg_index(func: ast.FunctionDef) -> set[int]:
    """Indices of ``__init__`` params forwarded as ``id=`` to ``super().__init__``."""
    params = [a.arg for a in func.args.args if a.arg != "self"]
    found: set[int] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        func_node = node.func
        is_super = (
            isinstance(func_node, ast.Attribute)
            and func_node.attr == "__init__"
            and isinstance(func_node.value, ast.Call)
            and isinstance(func_node.value.func, ast.Name)
            and func_node.value.func.id == "super"
        )
        if not is_super:
            continue
        for kw in node.keywords:
            if kw.arg == "id" and isinstance(kw.value, ast.Name) and kw.value.id in params:
                found.add(params.index(kw.value.id))
    return found


def _matches(kind: str, value: str, ids: set[str], prefixes: set[str]) -> bool:
    if kind == "id":
        if value in ids:
            return True
        return any(value.startswith(p) and p for p in prefixes)
    return False


def _textual_vocabulary() -> tuple[set[str], set[str]]:
    """Return (class_names, type_names) defined by Textual's own widgets.

    Textual composes its stylesheets in Python (``DEFAULT_CSS`` strings and
    ``COMPONENT_CLASSES`` sets), with no ``.tcss`` data files, so we walk the
    package and read both off the imported widget classes. This covers classes
    like ``toggle--button``, ``-information``, ``text-area--selection`` and types
    like ``Toast``/``ContentTabs`` that our own code never names. Without it the
    check would report every intentional Textual-internal style as a problem
    (REPORT.md Appendix D lists six such selectors).

    If Textual cannot be imported, the vocabularies are empty and only our own
    literals are trusted — the check degrades to stricter, never to silent.
    """
    classes: set[str] = set()
    types: set[str] = set()
    try:
        import textual
        from textual.widget import Widget
    except ImportError:  # pragma: no cover - textual is a hard dependency
        return classes, types

    # Walk the whole package (not just ``textual.widgets``): ``Toast``,
    # ``ContentTabs``, ``TabbedContent`` and friends live in private modules.
    modules = [textual]
    modules.extend(module for name in _textual_module_names() if (module := _safe_import(name)) is not None)
    for module in modules:
        for obj in vars(module).values():
            if not (isinstance(obj, type) and issubclass(obj, Widget)):
                continue
            if not obj.__module__.startswith("textual"):
                continue
            types.add(obj.__name__)
            css = getattr(obj, "DEFAULT_CSS", "")
            if isinstance(css, str):
                classes.update(re.findall(r"\.([A-Za-z\-][A-Za-z0-9_\-]*)", css))
            component_classes = getattr(obj, "COMPONENT_CLASSES", None)
            if component_classes:
                classes.update(component_classes)
    return classes, types


def _textual_module_names() -> list[str]:
    import textual

    return [name for _, name, _ in pkgutil.walk_packages(textual.__path__, "textual.")]


def _safe_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:  # pragma: no cover - optional deps inside textual
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print extracted vocabularies")
    args = parser.parse_args(argv)

    selectors: list[tuple[str, int, str]] = []
    collect_css(selectors)
    # Importing pentool modules and Textual's widget tree prints driver
    # diagnostics (``sleep=… clock=…``) to stderr; keep the report clean.
    with contextlib.redirect_stderr(_DEVNULL):
        ids, prefixes, classes, types, id_arg_indexes = collect_python()
        # Textual's own classes/types are legitimate targets too (Toast,
        # toggle--button, text-area--selection, …) — see _textual_vocabulary.
        textual_classes, textual_types = _textual_vocabulary()
    classes |= textual_classes
    types |= textual_types

    if args.list:
        print("ids:", sorted(ids)[:20], "..." if len(ids) > 20 else "")
        print("id prefixes:", sorted(prefixes))
        print("classes:", sorted(classes))
        print("types:", len(types))
        return 0

    problems: list[str] = []
    for file, lineno, selector in selectors:
        tags, sel_ids, sel_classes, attr_prefixes = _tokens(selector)
        for cls in sel_classes:
            if cls not in classes:
                problems.append(f"{file}:{lineno}: class .{cls} never set in Python")
        for sel_id in sel_ids:
            if not _matches("id", sel_id, ids, prefixes):
                problems.append(f"{file}:{lineno}: id #{sel_id} never set in Python")
        for prefix in attr_prefixes:
            # Textual 8 has no attribute selectors: ``[id^="x"]`` is a
            # tokenizer error, not a style that silently misses the DOM. Catch
            # it here so the failure names the file, not a crashed app.
            problems.append(
                f'{file}:{lineno}: attribute selector [id…="{prefix}"] is not supported '
                f"by Textual 8 — use a class instead"
            )
        for tag in tags:
            if tag not in types:
                problems.append(f"{file}:{lineno}: type {tag} is not a known class")

    if problems:
        print(f"check_tui_css: {len(problems)} problem(s)", file=sys.stderr)
        for line in problems:
            print("  " + line, file=sys.stderr)
        return 1

    print(f"check_tui_css: OK — {len(selectors)} selectors in {len(_iter_tcss())} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
