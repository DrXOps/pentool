"""Pentool — professional web security testing toolkit with Textual TUI."""

__version__ = "0.1.8"
__author__ = "pentool"


def _bootstrap_pro() -> None:
    """Extend pentool package __path__ entries with the PRO package.

    Supports two scenarios:
    1. Dev checkout: repo_root/pro/pentool/ (git submodule)
    2. End-user: ~/.pentool/pro/pentool/ (downloaded via 'pentool license activate')

    Only adds pro/pentool to pentool.__path__ and (if already loaded)
    pentool.api.__path__. Intentionally does NOT import pentool.tui or
    pentool.tui.screens here — those packages extend themselves via
    pkgutil.extend_path in their own __init__.py files, and importing
    them early would freeze their __path__ before the pro/ directory
    is appended.
    """
    import sys
    from pathlib import Path

    _pkg_dir = Path(__file__).resolve().parent   # .../pentool/pentool/
    _repo_root = _pkg_dir.parent                 # .../pentool/

    candidates: list[Path] = [
        Path.home() / ".pentool" / "pro" / "pentool",  # installed PRO package
        _repo_root / "pro" / "pentool",                 # dev submodule
    ]

    import pentool as _self

    for _pro_pkg in candidates:
        if not _pro_pkg.exists():
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


_bootstrap_pro()
