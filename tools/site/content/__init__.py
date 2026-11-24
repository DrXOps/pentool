"""Content of the site, one module per language.

Contract for every ``<lang>.py`` module:

``LANG``    language code (must match the module name)
``NAV``     navigation labels
``UI``      small interface strings (buttons, dialog texts)
``FOOTER``  footer blurb, link groups, legal line
``PAGES``   page key -> {"title", "description", "sections": [...]} (+ "hero" for index)

All four modules must describe exactly the same structure: ``signature()``
compares them and ``build.py`` refuses to write the site when a translation is
missing a block, a card or a table row. That is what keeps the pages in one shape
without hand-checking translations.

Text rules (they are the reason this site was rewritten):

* only facts that exist in the code — no invented benchmarks, no "10x", no
  features "coming soon" presented as shipped;
* human language: say what the tool does and what it does not do;
* no technical posturing ("async out of the box", "no bloat").
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

from . import en, hi, ru, zh

MODULES: dict[str, ModuleType] = {"en": en, "ru": ru, "zh": zh, "hi": hi}


def signature(node: Any) -> Any:
    """Structure of a content value: keys, list lengths and the shape of list items.

    Lengths are part of the signature on purpose: a translator who silently drops
    the fifth feature of a plan must fail the build instead of shipping a shorter page.
    """
    if isinstance(node, dict):
        return {key: signature(value) for key, value in node.items()}
    if isinstance(node, list):
        if node and isinstance(node[0], (dict, list)):
            heads = {repr(signature(item)) for item in node}
            return {"len": len(node), "items": sorted(heads)}
        return {"len": len(node), "scalars": True}
    return "text"


def _diff(expected: Any, actual: Any, path: str = "") -> list[str]:
    """Human-readable differences between two structures."""
    problems: list[str] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            if key not in actual:
                problems.append(f"{path}.{key}: missing")
            elif key not in expected:
                problems.append(f"{path}.{key}: unexpected")
            else:
                problems.extend(_diff(expected[key], actual[key], f"{path}.{key}"))
        return problems
    if isinstance(expected, list) and isinstance(actual, list):
        if expected != actual:
            problems.append(f"{path}: list items differ {expected} != {actual}")
        return problems
    if expected != actual:
        problems.append(f"{path}: {expected!r} != {actual!r}")
    return problems


def check_parity(lang: str = "en") -> list[str]:
    """Compare every language with ``lang``; empty list means parity."""
    reference = signature(MODULES[lang].PAGES)
    problems: list[str] = []
    for code, module in MODULES.items():
        if code == lang:
            continue
        for problem in _diff(reference, signature(module.PAGES), code):
            problems.append(problem)
    return problems
