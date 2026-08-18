"""TUI screens package."""
import pkgutil
__path__ = pkgutil.extend_path(__path__, __name__)

from pentool.tui.screens.comparer.screen import ComparerScreen
from pentool.tui.screens.dashboard.screen import DashboardScreen
from pentool.tui.screens.decoder.screen import DecoderScreen
from pentool.tui.screens.extensions.screen import ExtensionsScreen
from pentool.tui.screens.intruder.screen import IntruderScreen
from pentool.tui.screens.proxy.screen import ProxyScreen
from pentool.tui.screens.repeater.screen import RepeaterScreen
from pentool.tui.screens.sequencer.screen import SequencerScreen
from pentool.tui.screens.settings.screen import SettingsScreen
from pentool.tui.screens.target.screen import TargetScreen
from pentool.tui.screens.terminal.screen import TerminalScreen

# Scanner is a PRO-only module, downloaded separately into ~/.pentool/pro/
# (see 'pentool license trial'/'activate'). Absent on a bare pip install —
# import it defensively so the rest of the TUI still works without it.
# FileNotFoundError: screen.tcss may also be missing on CI runners that
# do not have the PRO submodule checked out.
try:
    from pentool.tui.screens.scanner.screen import ScannerScreen
    SCANNER_SCREEN_AVAILABLE = True
except (ImportError, FileNotFoundError):
    from pentool.tui.screens.scanner_unavailable import ScannerUnavailableScreen as ScannerScreen
    SCANNER_SCREEN_AVAILABLE = False

__all__ = [
    "DashboardScreen",
    "ProxyScreen",
    "RepeaterScreen",
    "IntruderScreen",
    "ScannerScreen",
    "SCANNER_SCREEN_AVAILABLE",
    "TargetScreen",
    "DecoderScreen",
    "ComparerScreen",
    "SequencerScreen",
    "ExtensionsScreen",
    "SettingsScreen",
    "TerminalScreen",
]
