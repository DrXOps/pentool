# 🧩 Writing a Pentool Plugin

Pentool's plugin system lets you extend the toolkit without touching core
code — add a new TUI screen, a CLI command, a custom active scanner, or a
passive check that runs on every proxy request.

---

## Where plugins live

| Location | Purpose |
|---|---|
| `~/.pentool/plugins/` | Your own plugins — auto-loaded on every startup (`PluginManager.load_user_plugins()`) |
| `pentool/plugins/builtin/` | Plugins shipped with the FREE package |
| PRO package (`~/.pentool/pro/pentool/plugins/builtin/`) | Plugins downloaded via `pentool license trial`/`activate` |

Drop a `.py` file into `~/.pentool/plugins/` and Pentool picks it up
automatically the next time it starts. Filenames starting with `_` are
skipped.

> ⚠️ Plugins from non-standard/untrusted paths trigger a warning log —
> only load code you trust; a plugin runs with full process privileges.

---

## Minimal plugin

Every plugin is a single Python file with two things:

1. A class inheriting from `BasePlugin` — metadata only.
2. A module-level `register(hook: PluginHook)` function — the entry point
   Pentool calls once the file is loaded.

```python
"""My first plugin."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from pentool.core.plugin_manager import BasePlugin, PluginHook


class HelloScreen(Widget):
    """A simple screen added by the plugin."""

    def compose(self) -> ComposeResult:
        yield Static("Hello from my plugin!")


class MyPlugin(BasePlugin):
    name = "my_plugin"          # unique ID, snake_case
    version = "1.0"
    author = "you"
    description = "My first Pentool plugin"
    api_version = 1              # current Plugin API version
    required_feature = ""        # "" = free plugin, no PRO license needed


def register(hook: PluginHook) -> None:
    """Called once when the plugin is loaded."""
    hook.register_screen("My Screen", HelloScreen)
```

Save this as `~/.pentool/plugins/my_plugin.py` and restart Pentool — a new
entry appears in the module switcher.

See the full working example shipped with Pentool:
`pentool/plugins/example_plugin.py` (+ `example_plugin.tcss` for styling
with Textual CSS).

---

## `BasePlugin` attributes

| Attribute | Type | Meaning |
|---|---|---|
| `name` | `str` | Unique plugin ID (snake_case) |
| `version` | `str` | Version string, e.g. `"1.0"` |
| `author` | `str` | Author name |
| `description` | `str` | Short description |
| `api_version` | `int` | Plugin API version this plugin targets. Plugins declaring a version newer than Pentool's `CURRENT_API_VERSION` are rejected as incompatible |
| `required_feature` | `str` | Empty string = free plugin. Set to a license feature name (e.g. `"scanner_pro"`) to gate the plugin behind a PRO license — checked via `get_session_license()` |

---

## What you can register via `PluginHook`

```python
def register(hook: PluginHook) -> None:
    hook.register_screen(name, widget_class, hotkey=None)
    hook.register_cli_command(group_name, click_command)
    hook.register_scanner(scanner_class)       # subclass of BaseScanner
    hook.register_passive_check(check_class)   # subclass of BaseCheck
```

### `register_screen(name, widget_class, hotkey=None)`
Adds a new module/screen to the TUI's module switcher. `widget_class` must
be a `textual.widget.Widget` subclass (see `HelloScreen` above).

### `register_cli_command(group_name, command)`
Adds a `click.Command` under an existing CLI command group (e.g. `scan`,
`proxy`) — extends `pentool <group> <your-command>`.

### `register_scanner(scanner_class)`
Registers a scanner plugin — a `BaseScanner` subclass that groups one or
more `BaseCheck`s under one name:

```python
from pentool.core.plugin_manager import BaseScanner, BaseCheck

class MyCheck(BaseCheck):
    name = "my_check"
    description = "Detects something custom"
    severity = "medium"      # critical | high | medium | low | info
    passive = False          # True = runs automatically on every proxy request

    async def scan(self, target, http_client, **kwargs) -> list:
        findings = []
        # ... your detection logic ...
        return findings

class MyScanner(BaseScanner):
    name = "my_scanner"
    checks = [MyCheck]
```

### `register_passive_check(check_class)`
Registers a standalone passive `BaseCheck` that runs on every request
passing through the proxy (no active scan needed) — useful for lightweight
always-on detections (info leaks, secrets, header issues).

---

## PRO-gated plugins

Set `required_feature` to a license feature string to require a PRO
license:

```python
class MyProPlugin(BasePlugin):
    name = "my_pro_plugin"
    required_feature = "scanner_pro"
```

If the active license doesn't cover `"scanner_pro"`, the plugin is skipped
with a WARNING log line — the rest of Pentool keeps working normally.

---

## Testing your plugin

There's no special test harness — plugins are plain Python. Write regular
unit tests against your `BaseCheck.scan()`/`BasePlugin` classes, and do a
manual smoke test by dropping the file into `~/.pentool/plugins/` and
restarting Pentool. Check the log (`~/.config/pentool/pentool.log`) for
`Plugin '<name>': registered ...` lines confirming it loaded.

---

## See also

- [Plugin API reference / all module APIs](../../API_CONTRACTS.md) —
  ProxyAPI, ScannerAPI, IntruderAPI, SpiderAPI, RepeaterAPI, TargetAPI,
  DecoderAPI, ComparerAPI, SequencerAPI
- `pentool/core/plugin_manager.py` — full source of `BasePlugin`,
  `BaseCheck`, `BaseScanner`, `PluginHook`, `PluginManager`
- `pentool/plugins/example_plugin.py` — complete working example
