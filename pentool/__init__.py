"""Pentool — professional web security testing toolkit with Textual TUI."""

__version__ = "0.2.6"
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

    Also adds the PRO package's *root* dir (the parent of pro/pentool/) to
    sys.path — this is where CodeEnigma's obfuscated build places
    `codeenigma_runtime/`, a compiled Cython extension package that the
    obfuscated pentool/**/*.py files import from at module load time
    (`from codeenigma_runtime import execute_secure_code`). Without this,
    every obfuscated PRO module fails to import with
    `ModuleNotFoundError: No module named 'codeenigma_runtime'` even though
    pentool/ itself resolves fine via __path__ extension above.

    The installed (~/.pentool/pro/) PRO package is skipped entirely — not
    even added to __path__ — if it was built for a different FREE version
    than this one (core.license.is_pro_package_compatible()). This is the
    scenario where a FREE upgrade (`pip install --upgrade pentool` /
    `pentool update`) succeeded but the PRO package's own re-sync
    afterwards failed or never ran (e.g. offline, or an unrelated version
    check like the GitHub release lookup errored out first and stopped the
    whole `pentool update` command before it got to the PRO sync step).
    Loading a mismatched PRO build there risks a hard-to-diagnose crash: it
    ships a compiled Cython extension, and an ABI/version mismatch can
    segfault the process instead of raising a catchable Python exception.
    The dev `pro/` submodule checkout is never version-mismatched (same
    source tree as the running FREE code) and is always loaded normally.
    A warning is printed to stderr so the user isn't left with unexplained
    missing PRO features and no context.
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
