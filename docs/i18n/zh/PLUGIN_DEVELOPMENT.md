# 🧩 编写 Pentool 插件

Pentool 的插件系统让你无需修改核心代码即可扩展工具——添加新的 TUI 界面、
CLI 命令、自定义主动扫描器，或在每个代理请求上运行的被动检测。

---

## 插件存放位置

| 位置 | 用途 |
|---|---|
| `~/.pentool/plugins/` | 你自己的插件——每次启动时自动加载 (`PluginManager.load_user_plugins()`) |
| `pentool/plugins/builtin/` | 随 FREE 版本发布的插件 |
| PRO 包 (`~/.pentool/pro/pentool/plugins/builtin/`) | 通过 `pentool license trial`/`activate` 下载的插件 |

将 `.py` 文件放入 `~/.pentool/plugins/`，Pentool 下次启动时会自动加载它。
以 `_` 开头的文件名会被跳过。

> ⚠️ 来自非标准/不受信任路径的插件会记录警告日志——只加载你信任的代码，
> 插件以完整进程权限运行。

---

## 最小插件示例

每个插件都是一个 Python 文件，包含两部分：

1. 一个继承自 `BasePlugin` 的类——仅包含元数据。
2. 一个模块级函数 `register(hook: PluginHook)`——Pentool 在文件加载后调用
   的入口点。

```python
"""我的第一个插件。"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from pentool.core.plugin_manager import BasePlugin, PluginHook


class HelloScreen(Widget):
    """插件添加的简单界面。"""

    def compose(self) -> ComposeResult:
        yield Static("来自我的插件的问候！")


class MyPlugin(BasePlugin):
    name = "my_plugin"          # 唯一 ID，snake_case
    version = "1.0"
    author = "you"
    description = "我的第一个 Pentool 插件"
    api_version = 1              # 当前 Plugin API 版本
    required_feature = ""        # "" = 免费插件，无需 PRO 许可证


def register(hook: PluginHook) -> None:
    """插件加载时调用一次。"""
    hook.register_screen("My Screen", HelloScreen)
```

将其保存为 `~/.pentool/plugins/my_plugin.py` 并重启 Pentool——模块切换器
中会出现一个新条目。

请参阅 Pentool 自带的完整可运行示例：`pentool/plugins/example_plugin.py`
（以及用于 Textual CSS 样式的 `example_plugin.tcss`）。

---

## `BasePlugin` 属性

| 属性 | 类型 | 含义 |
|---|---|---|
| `name` | `str` | 唯一插件 ID（snake_case） |
| `version` | `str` | 版本字符串，例如 `"1.0"` |
| `author` | `str` | 作者名称 |
| `description` | `str` | 简短描述 |
| `api_version` | `int` | 此插件所针对的 Plugin API 版本。声明版本高于 Pentool 当前 `CURRENT_API_VERSION` 的插件将被视为不兼容而拒绝加载 |
| `required_feature` | `str` | 空字符串 = 免费插件。设置为许可证功能名称（如 `"scanner_pro"`）可将插件限制为需要 PRO 许可证——通过 `get_session_license()` 检查 |

---

## 通过 `PluginHook` 可以注册的内容

```python
def register(hook: PluginHook) -> None:
    hook.register_screen(name, widget_class, hotkey=None)
    hook.register_cli_command(group_name, click_command)
    hook.register_scanner(scanner_class)       # BaseScanner 的子类
    hook.register_passive_check(check_class)   # BaseCheck 的子类
```

### `register_screen(name, widget_class, hotkey=None)`
向 TUI 的模块切换器添加新模块/界面。`widget_class` 必须是
`textual.widget.Widget` 的子类（参见上方的 `HelloScreen`）。

### `register_cli_command(group_name, command)`
在现有的 CLI 命令组下添加一个 `click.Command`（例如 `scan`、`proxy`）——
扩展 `pentool <group> <你的命令>`。

### `register_scanner(scanner_class)`
注册一个扫描器插件——一个 `BaseScanner` 子类，将一个或多个 `BaseCheck`
归组在同一名称下：

```python
from pentool.core.plugin_manager import BaseScanner, BaseCheck

class MyCheck(BaseCheck):
    name = "my_check"
    description = "检测某种自定义漏洞"
    severity = "medium"      # critical | high | medium | low | info
    passive = False          # True = 在每个代理请求上自动运行

    async def scan(self, target, http_client, **kwargs) -> list:
        findings = []
        # ... 你的检测逻辑 ...
        return findings

class MyScanner(BaseScanner):
    name = "my_scanner"
    checks = [MyCheck]
```

### `register_passive_check(check_class)`
注册一个独立的被动 `BaseCheck`，它会在每个经过代理的请求上运行（无需主动
扫描）——适用于轻量级、常驻的检测（信息泄露、密钥、header 问题等）。

---

## 需要 PRO 许可证的插件

将 `required_feature` 设置为许可证功能字符串，即可要求 PRO 许可证：

```python
class MyProPlugin(BasePlugin):
    name = "my_pro_plugin"
    required_feature = "scanner_pro"
```

如果当前许可证不涵盖 `"scanner_pro"`，插件将被跳过并记录一条 WARNING
日志——Pentool 的其余部分照常运行。

---

## 测试你的插件

没有特殊的测试框架——插件就是普通的 Python 代码。为你的
`BaseCheck.scan()`/`BasePlugin` 类编写常规单元测试，并通过将文件放入
`~/.pentool/plugins/` 并重启 Pentool 进行手动冒烟测试。检查日志
（`~/.config/pentool/pentool.log`）中的 `Plugin '<name>': registered ...`
行以确认加载成功。

---

## 另请参阅

- [插件 API 参考 / 所有模块 API](../../API_CONTRACTS.md) —
  ProxyAPI、ScannerAPI、IntruderAPI、SpiderAPI、RepeaterAPI、TargetAPI、
  DecoderAPI、ComparerAPI、SequencerAPI
- `pentool/core/plugin_manager.py` — `BasePlugin`、`BaseCheck`、
  `BaseScanner`、`PluginHook`、`PluginManager` 的完整源码
- `pentool/plugins/example_plugin.py` — 完整可运行示例
