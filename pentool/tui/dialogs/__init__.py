"""tui.dialogs package: modal dialogs shared across screens.

extend_path lets the PRO package (pro/pentool/tui/dialogs/, e.g.
checks_dialog.py) merge into this namespace the same way
pentool.tui/pentool.tui.screens already do — see pentool/tui/__init__.py
and pentool/tui/screens/__init__.py for the same pattern.
"""
import pkgutil
__path__ = pkgutil.extend_path(__path__, __name__)
