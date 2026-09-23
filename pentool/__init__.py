"""Pentool — professional web security testing toolkit with Textual TUI."""

import tomllib
from pathlib import Path

# Single source of truth: version lives ONLY in pyproject.toml.
# This file reads it at import time so there is one canonical value
# used by both the installed package metadata (pip setuptools-scm /
# manual stamping) and the source tree itself. No more fallback
# literals that drift out of sync.
_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
try:
    with open(_PYPROJECT, "rb") as _f:
        __version__: str = tomllib.load(_f)["project"]["version"]
except Exception:
    __version__ = "0.0.0"  # last resort — should never happen in a valid install

__author__ = "pentool"


def _bootstrap_pro() -> None:
    """Add pentool/__path__ entries for dev (pro/ submodule) or installed (~/.pentool/pro/) PRO package.

    Skips installed PRO if version-mismatched with FREE (ABI mismatch can segfault).
    Adds PRO root to sys.path for codeenigma_runtime Cython extensions.
    """
    import sys
    from pathlib import Path

    _pkg_dir = Path(__file__).resolve().parent   # .../pentool/pentool/
    _repo_root = _pkg_dir.parent                 # .../pentool/

    _installed_pro_pkg = Path.home() / ".pentool" / "pro" / "pentool"
    candidates: list[Path] = [
        _repo_root / "pro" / "pentool",                 # dev submodule
        _installed_pro_pkg,                              # installed PRO package
    ]

    import pentool as _self

    for _pro_pkg in candidates:
        if not _pro_pkg.exists():
            continue

        if _pro_pkg == _installed_pro_pkg:
            try:
                from pentool.core.license import is_pro_package_compatible
                _compatible, _warning = is_pro_package_compatible()
            except Exception:
                _compatible, _warning = True, ""  # never block startup over this check itself
            if not _compatible:
                print(f"[pentool] {_warning}", file=sys.stderr)
                continue

        # 1. Extend top-level pentool.__path__ so that sub-packages
        #    resolved via pkgutil.extend_path below will find pro/pentool/XXX.
        if str(_pro_pkg) not in _self.__path__:
            _self.__path__.append(str(_pro_pkg))

        # 2. If pentool.api is already imported, extend its __path__ too
        #    (it has no pkgutil.extend_path because its scanner_api.py lives
        #    only in pro/ — there is nothing to forward to from the public pkg).
        if "pentool.api" in sys.modules:
            _api = sys.modules["pentool.api"]
            _extra = str(_pro_pkg / "api")
            if _extra not in _api.__path__:
                _api.__path__.append(_extra)

        # 3. Make codeenigma_runtime/ (sibling of pentool/, one level up from
        #    _pro_pkg) importable — see docstring above.
        _pro_root = _pro_pkg.parent
        if str(_pro_root) not in sys.path:
            sys.path.append(str(_pro_root))


_bootstrap_pro()
