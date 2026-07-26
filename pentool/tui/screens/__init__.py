"""TUI screens package."""

from pentool.tui.screens.dashboard.screen import DashboardScreen
from pentool.tui.screens.proxy.screen import ProxyScreen
from pentool.tui.screens.repeater.screen import RepeaterScreen
from pentool.tui.screens.intruder.screen import IntruderScreen
from pentool.tui.screens.scanner.screen import ScannerScreen
from pentool.tui.screens.target.screen import TargetScreen
from pentool.tui.screens.decoder.screen import DecoderScreen
from pentool.tui.screens.comparer.screen import ComparerScreen
from pentool.tui.screens.sequencer.screen import SequencerScreen
from pentool.tui.screens.spider.screen import SpiderScreen
from pentool.tui.screens.extensions.screen import ExtensionsScreen
from pentool.tui.screens.settings.screen import SettingsScreen
from pentool.tui.screens.terminal.screen import TerminalScreen

__all__ = [
    "DashboardScreen",
    "ProxyScreen",
    "RepeaterScreen",
    "IntruderScreen",
    "ScannerScreen",
    "TargetScreen",
    "DecoderScreen",
    "ComparerScreen",
    "SequencerScreen",
    "SpiderScreen",
    "ExtensionsScreen",
    "SettingsScreen",
    "TerminalScreen",
]
