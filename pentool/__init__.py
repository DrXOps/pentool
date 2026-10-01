"""Pentool — professional web security testing toolkit with Textual TUI."""

import importlib.metadata
from pathlib import Path

# Single source of truth: version lives ONLY in pyproject.toml.
# In an installed package (wheel) we read it from the dist-info metadata.
# In a source checkout (pyproject.toml exists next to the package dir)
# we fall back to reading it from there so development versions are always
# current without manual stamping.
_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
__version__: str = "0.0.0"  # type-safe init
try:
    __version__ = importlib.metadata.version("pentool")
except importlib.metadata.PackageNotFoundError:
    try:
        import tomllib
        with open(_PYPROJECT, "rb") as _f:
            __version__ = tomllib.load(_f)["project"]["version"]
    except Exception:
        import logging
        logging.getLogger("pentool").warning(
            "failed to read version from pyproject.toml, falling back to 0.0.0",
            exc_info=True,
        )
        __version__ = "0.0.0"  # last resort

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

        # --- Phase 1: extend __path__ entries BEFORE any PRO import ---
        # This ensures pro/ modules are discoverable even if compatibility
        # check or other early imports trigger sub-package imports (e.g.
        # pentool.plugins.builtin.scanner_pro).
        _all_subpaths: dict[str, list[str]] = {
            "": [str(_pro_pkg)],
            "api": [str(_pro_pkg / "api")],
            "plugins": [str(_pro_pkg / "plugins")],
            "plugins.builtin": [str(_pro_pkg / "plugins" / "builtin")],
            "tui.widgets": [str(_pro_pkg / "tui" / "widgets")],
            "tui.dialogs": [str(_pro_pkg / "tui" / "dialogs")],
            "tui.screens": [str(_pro_pkg / "tui" / "screens")],
            "tui.screens.scanner": [str(_pro_pkg / "tui" / "screens" / "scanner")],
        }

        # 1a. Top-level pentool.__path__
        for _extra in _all_subpaths[""]:
            if _extra not in _self.__path__:
                _self.__path__.append(_extra)

        # 1b. Sub-packages (import on demand to extend __path__ so
        #     subsequent imports find pro/ modules)
        for _subkey, _extras in _all_subpaths.items():
            if not _subkey:
                continue
            _modname = f"pentool.{_subkey}"
            try:
                _mod = __import__(_modname, fromlist=[""])
                for _extra in _extras:
                    if _extra not in _mod.__path__:
                        _mod.__path__.append(_extra)
            except ImportError:
                pass  # sub-package not yet importable — skip silently

        # --- Phase 2: version compatibility check ---
        if _pro_pkg == _installed_pro_pkg:
            try:
                from pentool.core.license import is_pro_package_compatible
                _compatible, _warning = is_pro_package_compatible()
            except Exception:
                import logging
                logging.getLogger("pentool").debug(
                    "PRO compatibility check in bootstrap failed, assuming compatible",
                    exc_info=True,
                )
                _compatible, _warning = True, ""  # never block startup
            if not _compatible:
                print(f"[pentool] {_warning}", file=sys.stderr)
                continue
            if _warning:
                print(f"[pentool] {_warning}", file=sys.stderr)

        # --- Phase 3: codeenigma_runtime in sys.path ---
        _pro_root = _pro_pkg.parent
        if str(_pro_root) not in sys.path:
            sys.path.append(str(_pro_root))


_bootstrap_pro()
