# 🔒 Pentool — 专业的 Web 渗透测试 TUI 工具包

[![PyPI version](https://img.shields.io/pypi/v/pentool)](https://pypi.org/project/pentool/)
[![Python versions](https://img.shields.io/pypi/pyversions/pentool)](https://pypi.org/project/pentool/)
[![CI](https://github.com/docxqwerty/pentool/actions/workflows/tests.yml/badge.svg)](https://github.com/docxqwerty/pentool/actions)
[![License](https://img.shields.io/github/license/docxqwerty/pentool)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/pentool)](https://pypi.org/project/pentool/)

🌐 **语言：** [English](README.md) · [Русский](README_RU.md) · [中文](README_ZH.md) · [हिन्दी](README_HI.md)

---

**Pentool** 是一款基于终端界面（TUI）的 Web 安全测试工具，专为渗透测试人员和安全研究人员设计。  
它将 HTTP 拦截、漏洞扫描、自动化攻击和数据分析集成于一个终端中。  
高效、透明、专为实战设计。

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

> 截图和 GIF 演示即将推出。

| 仪表板 | 代理 | Intruder |
|--------|------|----------|
| *(即将推出)* | *(即将推出)* | *(即将推出)* |

---

## 📚 文档

- [快速开始指南](docs/i18n/en/QUICKSTART.md)
- [用户手册](docs/i18n/en/USER_GUIDE.md)
- [安装说明](docs/i18n/en/INSTALLATION.md)
- [插件开发](docs/API_CONTRACTS.md)

完整文档：**[pentool.pro](https://pentool.pro)**

---

## 🧪 测试模式（Beta）

> **Pentool 目前处于公开 Beta 测试阶段。**  
> 所有**免费模块均可正常使用**。付费（PRO）插件仍在开发中——目前仅提供**试用版本**。  
>
> 但如果你拥有**信息安全领域的博客或频道**，并愿意帮助推广本项目——请私信我们，我们将免费为你提供**私有 PRO 密钥**。
>
> 📬 联系：**[@sudores](https://t.me/sudores)**（Telegram）

---

## 💰 支持项目

Pentool 由一位开发者在业余时间独立开发维护。  
如果它对你的工作有帮助，欢迎给予支持——这将直接推动新功能的开发和 Bug 修复。

- ⭐ [在 GitHub 上加星](https://github.com/docxqwerty/pentool) — 免费且帮助很大
- ☕ [通过 TryBit 捐款](https://donate.trybit.com/KY1ECKA5) — 加密货币一次性支持
- 🔑 PRO 许可证 — 即将推出；现可试用

每一份支持都意义重大。感谢你对开源安全工具的贡献！🙌

---

## 🤝 参与贡献

欢迎贡献代码！  
提交 PR 前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 📄 许可证

采用 **AGPL-3.0** 许可证发布。详情见 [LICENSE](LICENSE)。  
PRO 扩展采用商业许可证。

---

## 📬 联系方式

- **网站：** [pentool.pro](https://pentool.pro)
- **Telegram：** [@sudores](https://t.me/sudores)
- **邮箱：** support@pentool.pro
- **作者：** Anatoly Kashtanov（DoctorX）

---

⭐ 如果 Pentool 为你节省了时间，在 GitHub 上加星有助于项目成长——谢谢！
