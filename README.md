# 🔒 Pentool — Professional TUI Web Pentesting Toolkit

> **🚧 Active Development — Public Demo/Beta.** Core modules are stable and fully usable. PRO features are under active development. Feedback and bug reports are welcome.

[![PyPI version](https://img.shields.io/pypi/v/pentool)](https://pypi.org/project/pentool/)
[![Python versions](https://img.shields.io/pypi/pyversions/pentool)](https://pypi.org/project/pentool/)
[![CI](https://github.com/DrXOps/pentool/actions/workflows/tests.yml/badge.svg)](https://github.com/DrXOps/pentool/actions)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/pentool)](https://pypi.org/project/pentool/)

🌐 **Languages:** [English](README.md) · [Русский](docs/i18n/ru/README.md) · [中文](docs/i18n/zh/README.md) · [हिन्दी](docs/i18n/hi/README.md)

---

## 💸 Support & Pricing

> Pentool is open-source and free to use. If it saves you time on a pentest — consider supporting development.  
> Full pricing details and sponsorship options: **[pentool.pro](https://pentool.pro)**

| | | |
|---|---|---|
| ⭐ **Sponsor (individual)** | **$5** one-time or /month | [Sponsor on GitHub](https://github.com/sponsors/DrXOps) |
| 🏢 **Sponsor (company)** | **$50** one-time or /month | Logo in README + website · [pentool.pro/sponsor](https://pentool.pro/sponsor) |
| 🔑 **PRO License — Early Access** | **$29** *(beta price, until Dec 31 2026)* | After release: $99/year |

> **🎁 Beta loyalty discount:** Everyone who buys PRO for $29 gets a **lifetime 50% discount on annual renewal** (i.e. $49.50/year instead of $99).  
> This discount applies **only to first buyers during the beta — until December 31, 2026**.

**PRO license is issued manually during beta.**  
To purchase, contact: **[@sudores](https://t.me/sudores)** (Telegram) · **dev@pentool.pro**

---

**Pentool** is a terminal-based (TUI) security toolkit for penetration testers and security researchers.  
It combines HTTP interception, vulnerability scanning, automated attacks, and data analysis — all inside your terminal.  
Fast, transparent, and built for real-world testing.

> ⚠️ **Use a modern terminal emulator.** Pentool's TUI relies on mouse support, true color, and modern rendering (built on the [Textual](https://github.com/Textualize/textual) framework). Legacy terminals (e.g. Windows `cmd.exe`) will render incorrectly. Recommended: **Windows Terminal**, **iTerm2** (macOS), **GNOME Terminal / Kitty / Alacritty / WezTerm** (Linux). On Windows, running inside **WSL** gives the best experience.

---

## 📸 Screenshots

| Dashboard | Scanner |
|:---------:|:-------:|
| ![Dashboard](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/dashboard.png) | ![Scanner](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/scaner.png) |

| Proxy | Repeater |
|:-----:|:--------:|
| ![Proxy](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/proxy.png) | ![Repeater](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/repeater.png) |

| Intruder | Settings |
|:--------:|:--------:|
| ![Intruder](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/intruder.png) | ![Settings](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/settings.png) |

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

# Start a 14-day PRO trial (unlocks Scanner + other PRO features)
# Run this BEFORE first launching the TUI — if the TUI is already open,
# restart it afterwards so it picks up the new license.
pentool license trial

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

- ⭐ **[Star on GitHub](https://github.com/DrXOps/pentool)** — free, takes 2 seconds, helps visibility enormously
- 💸 **[Sponsor the project](https://pentool.pro/sponsor)** — $5 (individual) or $50 (company, includes logo placement)
- 🔑 **[PRO license — $29 beta price](https://pentool.pro)** — early access + lifetime loyalty discount
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
- **Telegram channel:** [t.me/pentool_pro](https://t.me/pentool_pro)
- **Telegram:** [@sudores](https://t.me/sudores)
- **Email:** support@pentool.pro
- **Author:** Anatoly Kashtanov (DoctorX)

---

⭐ If Pentool saves you time, a GitHub star helps the project grow — thanks!
