# 🔒 Pentool — Professional TUI Web Pentesting Toolkit

> **🚧 Active Development — Public Demo/Beta.** Core modules are stable and fully usable. PRO features are under active development. Feedback and bug reports are welcome.

[![PyPI version](https://img.shields.io/pypi/v/pentool)](https://pypi.org/project/pentool/)
[![Python versions](https://img.shields.io/pypi/pyversions/pentool)](https://pypi.org/project/pentool/)
[![CI](https://github.com/docxqwerty/pentool/actions/workflows/tests.yml/badge.svg)](https://github.com/docxqwerty/pentool/actions)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/pentool)](https://pypi.org/project/pentool/)

🌐 **Languages:** [English](README.md) · [Русский](docs/i18n/ru/README.md) · [中文](docs/i18n/zh/README.md) · [हिन्दी](docs/i18n/hi/README.md)

---

**Pentool** is a terminal-based (TUI) security toolkit for penetration testers and security researchers.  
It combines HTTP interception, vulnerability scanning, automated attacks, and data analysis — all inside your terminal.  
Fast, transparent, and built for real-world testing.

> ⚠️ **Use a modern terminal emulator.** Pentool's TUI relies on mouse support, true color, and modern rendering (built on the [Textual](https://github.com/Textualize/textual) framework). Legacy terminals (e.g. Windows `cmd.exe`) will render incorrectly. Recommended: **Windows Terminal**, **iTerm2** (macOS), **GNOME Terminal / Kitty / Alacritty / WezTerm** (Linux). On Windows, running inside **WSL** gives the best experience.

---

## 📸 Screenshots

| Dashboard | Scanner |
|:---------:|:-------:|
| ![Dashboard](screens/dashboard.png) | ![Scanner](screens/scaner.png) |

| Proxy | Repeater |
|:-----:|:--------:|
| ![Proxy](screens/proxy.png) | ![Repeater](screens/repeater.png) |

| Intruder | Settings |
|:--------:|:--------:|
| ![Intruder](screens/intruder.png) | ![Settings](screens/settings.png) |

---

## ✨ Features

- **🌐 Proxy**  
  Intercept and modify HTTP/HTTPS traffic in real time. Manage scope, apply Match & Replace rules, capture WebSocket messages.

- **🔄 Repeater**  
  Replay requests with any modifications. Save tabs between sessions and switch between scenarios instantly.

- **💥 Intruder**  
  Run automated payload attacks with four strategies: Sniper, Battering Ram, Pitchfork, Cluster Bomb.  
  Turbo Mode delivers 10× speed via Keep-Alive and connection pooling.

- **🔍 Scanner**  
  Active and passive vulnerability analysis: SQLi, XSS, SSTI, LFI, RCE, SSRF, XXE, CORS, JWT flaws, and more.  
  Smart context-aware payloads, WAF bypass, time-based and boolean-blind techniques.

- **🕷 Spider**  
  Crawl targets automatically — collect pages, forms, API endpoints, and JS files.  
  JavaScript rendering via Playwright is supported.

- **🎯 Target / Site Map**  
  Build a site map from proxy traffic, manage testing scope, and filter hosts directly from the UI.

- **🔐 Decoder · Comparer · Sequencer**  
  - **Decoder** — 19 encode/decode/hash operations with chaining support  
  - **Comparer** — side-by-side diff with change highlighting  
  - **Sequencer** — entropy analysis of tokens (sessions, CSRF, JWT) with FIPS tests

- **🧩 Plugin System**  
  Extend functionality without touching the core. PRO plugins add advanced scanners, smart payloads, and report generators.

- **⚡ Async Core**  
  Fully async engine handles thousands of concurrent connections and hundreds of requests per second.

- **📦 One-line Install**  
  `pip install pentool` — no complex setup, works on Linux, macOS, and Windows (WSL).

- **🆓 Open Source + PRO Extensions**  
  The base version is free and open. PRO extensions unlock exclusive features and support the project.

---

## 🚀 Quick Start

```bash
# Install
pip install pentool

# Launch TUI
pentool

# Start proxy on custom port
pentool proxy start --port 8080

# Active scan
pentool scan active --url https://example.com

# Check for updates
pentool update --check
```

---

---

## 📚 Documentation

- [🚀 First Run: Certificate & First Intercept](docs/i18n/en/FIRST_RUN.md) — start here
- [Quick Start Guide](docs/i18n/en/QUICKSTART.md)
- [User Guide](docs/i18n/en/USER_GUIDE.md)
- [Installation](docs/i18n/en/INSTALLATION.md)
- [Plugin Development](docs/i18n/en/PLUGIN_DEVELOPMENT.md)
- [Plugin API Reference](docs/API_CONTRACTS.md)

Full docs: **[pentool.pro](https://pentool.pro)**

---

## 🧪 Beta / Testing Mode

> **Pentool is currently in public beta.**  
> All **free modules are fully functional**. PRO features are actively being built — a **14-day trial** is available so you can evaluate everything upfront.

### 🎙 For Bloggers & Content Creators

Running a **security blog, YouTube channel, or Telegram channel?**  
Write an honest review and recommend Pentool to your audience — we'll give you a **permanent PRO license, completely free.**

No minimum follower count. We value quality over reach.  
→ Reach out: **[@sudores](https://t.me/sudores)** on Telegram

---

## 💰 Support the Project

Pentool is built and maintained by a solo developer in spare time.  
If it saves you hours on a pentest — consider giving back. Every contribution directly funds new features, fixes, and faster releases.

- ⭐ **[Star on GitHub](https://github.com/docxqwerty/pentool)** — free, takes 2 seconds, helps visibility enormously
- 🔑 **PRO license** — get early access and support development → **[@sudores](https://t.me/sudores)**
- 💬 **Share** — tell a colleague, post a review, or mention Pentool in your writeups

> Building tools is lonely work. A star or a kind word genuinely matters. Thank you. 🙏

---

## 🤝 Contributing

Contributions are welcome!  
Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.

---

## 🙏 Acknowledgments

Special thanks to:

- **[codeby.net](https://codeby.net/)** — For community support and feedback

---

## 📄 License

Distributed under the **AGPL-3.0** license. See [LICENSE](LICENSE) for details.  
PRO extensions are available under a commercial license.

---

## 📬 Contact

- **Website:** [pentool.pro](https://pentool.pro)
- **Telegram:** [@sudores](https://t.me/sudores)
- **Email:** support@pentool.pro
- **Author:** Anatoly Kashtanov (DoctorX)

---

⭐ If Pentool saves you time, a GitHub star helps the project grow — thanks!
