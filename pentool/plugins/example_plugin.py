"""Example plugin for Pentool."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from pentool.core.plugin_manager import BasePlugin, PluginHook

_CSS = (Path(__file__).parent / "example_plugin.tcss").read_text(encoding="utf-8")


class HelloScreen(Widget):
    """A simple example screen added by a plugin."""

    DEFAULT_CSS = _CSS

    def compose(self) -> ComposeResult:
        with Static(id="box"):
            yield Static("Hello from plugin!", classes="title")
            yield Static(
                "This screen was added by example_plugin.py.\n"
                "Place your plugin in plugins/custom/ to load it automatically.",
            )


class ExamplePlugin(BasePlugin):
    name = "example_plugin"
    version = "1.0"
    author = "Pentool"
    description = "Example plugin demonstrating the Plugin API"
    api_version = 1


def register(hook: PluginHook) -> None:
    """Plugin entry point. Called when the plugin is loaded."""
    hook.register_screen("Hello Plugin", HelloScreen)
