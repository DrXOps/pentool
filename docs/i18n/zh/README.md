# 🔒 Pentool — 专业的 Web 渗透测试 TUI 工具包

> **🚧 积极开发中 — 公开演示/测试版。** 核心模块稳定且完全可用。PRO 功能正在积极开发中。欢迎反馈和错误报告。

[![PyPI version](https://img.shields.io/pypi/v/pentool)](https://pypi.org/project/pentool/)
[![Python versions](https://img.shields.io/pypi/pyversions/pentool)](https://pypi.org/project/pentool/)
[![CI](https://github.com/DrXOps/pentool/actions/workflows/tests.yml/badge.svg)](https://github.com/DrXOps/pentool/actions)
[![License](https://img.shields.io/github/license/DrXOps/pentool)](../../../LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/pentool)](https://pypi.org/project/pentool/)

🌐 **语言：** [English](../../../README.md) · [Русский](../ru/README.md) · [中文](README.md) · [हिन्दी](../hi/README.md)

---

**Pentool** 是一款基于终端界面（TUI）的 Web 安全测试工具，专为渗透测试人员和安全研究人员设计。  
它将 HTTP 拦截、漏洞扫描、自动化攻击和数据分析集成于一个终端中。  
高效、透明、专为实战设计。

> ⚠️ **请使用现代终端模拟器。** Pentool 的 TUI 基于 [Textual](https://github.com/Textualize/textual) 框架构建，依赖鼠标支持、真彩色和现代渲染。传统终端（如 Windows 的 `cmd.exe`）会显示异常。推荐使用：**Windows Terminal**、**iTerm2**（macOS）、**GNOME Terminal / Kitty / Alacritty / WezTerm**（Linux）。在 Windows 上，在 **WSL** 中运行可获得最佳体验。

---

## ✨ 功能特性

- **🌐 代理（Proxy）**  
  实时拦截和修改 HTTP/HTTPS 流量。管理测试范围（scope）、应用 Match & Replace 规则、捕获 WebSocket 消息。

- **🔄 Repeater（重放器）**  
  随意修改并重发请求。跨会话保存标签页，在不同测试场景间即时切换。

- **💥 Intruder（入侵器）**  
  自动化 payload 攻击，支持四种策略：Sniper、Battering Ram、Pitchfork、Cluster Bomb。  
  Turbo 模式通过 Keep-Alive 和连接池实现 10 倍速度提升。

- **🔍 Scanner（扫描器）**  
  主动与被动漏洞分析：SQLi、XSS、SSTI、LFI、RCE、SSRF、XXE、CORS、JWT 缺陷等。  
  智能上下文感知 payload、WAF 绕过、基于时间和布尔盲注技术。

- **🕷 Spider（爬虫）**  
  自动爬取目标——收集页面、表单、API 端点和 JS 文件。  
  支持通过 Playwright 进行 JavaScript 渲染。

- **🎯 Target / Site Map（目标/站点地图）**  
  基于代理流量构建站点地图，直接在界面中管理测试范围和过滤主机。

- **🔐 Decoder · Comparer · Sequencer**  
  - **Decoder** — 19 种编码/解码/哈希操作，支持链式处理  
  - **Comparer** — 带变更高亮的并排差异对比  
  - **Sequencer** — 令牌熵分析（会话、CSRF、JWT），包含 FIPS 测试

- **🧩 插件系统**  
  无需修改核心代码即可扩展功能。PRO 插件提供高级扫描器、智能 payload 和报告生成器。

- **⚡ 异步核心**  
  全异步引擎，支持数千并发连接和每秒数百个请求。

- **📦 一行安装**  
  `pip install pentool` — 无需复杂配置，支持 Linux、macOS 和 Windows（WSL）。

- **🆓 开源 + PRO 扩展**  
  基础版完全免费开源。PRO 许可证解锁独家功能并支持项目发展。

---

## 🚀 快速开始

```bash
# 安装
pip install pentool

# 开始 14 天 PRO 试用（解锁 Scanner 及其他 PRO 功能）
# 请在首次启动 TUI 之前运行此命令 — 如果 TUI 已经打开，
# 激活后请重启它以加载新的许可证。
pentool license trial

# 启动 TUI
pentool

# 在自定义端口启动代理
pentool proxy start --port 8080

# 主动扫描
pentool scan active --url https://example.com

# 检查更新
pentool update --check
```

---

## 📸 截图

| 仪表板 | 扫描器 |
|:---------:|:-------:|
| ![Dashboard](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/dashboard.png) | ![Scanner](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/scaner.png) |

| 代理 | Repeater |
|:-----:|:--------:|
| ![Proxy](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/proxy.png) | ![Repeater](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/repeater.png) |

| Intruder | 设置 |
|:--------:|:--------:|
| ![Intruder](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/intruder.png) | ![Settings](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/settings.png) |

---

## 📚 文档

- [🚀 首次运行：证书与首次拦截](FIRST_RUN.md) — 从这里开始
- [快速开始指南](QUICKSTART.md)
- [用户手册](USER_GUIDE.md)
- [安装说明](INSTALLATION.md)
- [插件开发](PLUGIN_DEVELOPMENT.md)
- [Plugin API 参考](../../API_CONTRACTS.md)

完整文档：**[pentool.pro](https://pentool.pro)**

---

## 🧪 演示 / 测试模式

> **Pentool 目前处于公开演示/测试阶段。**  
> 所有**免费模块均完全可用**。PRO 功能正在积极开发中——提供 **14 天试用**，让你可以提前评估一切。

### 🎙 面向博主与内容创作者

正在运营**安全博客、YouTube 频道或 Telegram 频道**？  
写一篇真实的评测并向你的受众推荐 Pentool——我们将免费提供**永久 PRO 许可证**。

无最低粉丝数要求。我们看重质量而非规模。  
→ 联系我们：**[@sudores](https://t.me/sudores)**（Telegram）

---

## 💰 支持项目

Pentool 由一位开发者在业余时间独立开发维护。  
如果它为你节省了渗透测试的时间——欢迎回馈支持。每一份贡献都直接资助新功能、修复和更快的发布。

- ⭐ **[在 GitHub 上加星](https://github.com/DrXOps/pentool)** — 免费，只需 2 秒，极大提升项目曝光度
- 🔑 **PRO 许可证** — 获得早期访问权限并支持开发 → **[@sudores](https://t.me/sudores)**
- 💬 **分享** — 告诉同事、发布评测，或在你的文章中提及 Pentool

> 打造工具是一项孤独的工作。一颗星或一句善意的话真的很重要。谢谢。🙏

---

## 🤝 参与贡献

欢迎贡献代码！  
提交 PR 前请阅读 [CONTRIBUTING.md](../../../CONTRIBUTING.md)。

---

## 🙏 致谢

特别感谢：

- **[codeby.net](https://codeby.net/)** — 社区支持与反馈

---

## 📄 许可证

采用 **AGPL-3.0** 许可证发布。详情见 [LICENSE](../../../LICENSE)。  
PRO 扩展采用商业许可证。

---

## 📬 联系方式

- **网站：** [pentool.pro](https://pentool.pro)
- **Telegram 频道：** [t.me/pentool_pro](https://t.me/pentool_pro)
- **Telegram：** [@sudores](https://t.me/sudores)
- **邮箱：** support@pentool.pro
- **作者：** Anatoly Kashtanov（DoctorX）

---

⭐ 如果 Pentool 为你节省了时间，在 GitHub 上加星有助于项目成长——谢谢！
