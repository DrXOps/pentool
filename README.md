# 🔒 Pentool — Professional TUI Web Pentesting Toolkit

[![PyPI version](https://img.shields.io/pypi/v/pentool)](https://pypi.org/project/pentool/)
[![Python versions](https://img.shields.io/pypi/pyversions/pentool)](https://pypi.org/project/pentool/)
[![CI](https://github.com/docxqwerty/pentool/actions/workflows/tests.yml/badge.svg)](https://github.com/docxqwerty/pentool/actions)
[![License](https://img.shields.io/github/license/docxqwerty/pentool)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/pentool)](https://pypi.org/project/pentool/)

🌐 **Languages:** [English](README.md) · [Русский](README_RU.md) · [中文](README_ZH.md) · [हिन्दी](README_HI.md)

---

**Pentool** is a terminal-based (TUI) security toolkit for penetration testers and security researchers.  
It combines HTTP interception, vulnerability scanning, automated attacks, and data analysis — all inside your terminal.  
Fast, transparent, and built for real-world testing.

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

## 📸 Screenshots

> Screenshots and GIFs coming soon.

| Dashboard | Proxy | Intruder |
|-----------|-------|----------|
| *(coming soon)* | *(coming soon)* | *(coming soon)* |

---

## 📚 Documentation

- [Quick Start Guide](docs/i18n/en/QUICKSTART.md)
- [User Guide](docs/i18n/en/USER_GUIDE.md)
- [Installation](docs/i18n/en/INSTALLATION.md)
- [Plugin Development](docs/API_CONTRACTS.md)

Full docs: **[pentool.pro](https://pentool.pro)**

---

## 💰 Support the Project

Pentool is built and maintained in spare time by a solo developer.  
If it helps your work, consider supporting — it directly funds new features, bug fixes, and faster releases.

- ⭐ [Star on GitHub](https://github.com/docxqwerty/pentool) — free and helps a lot
- 💳 [GitHub Sponsors](https://github.com/sponsors/docxqwerty)
- 🔑 Purchase a PRO license — unlocks advanced features and supports development

Every contribution matters. Thank you for supporting open-source security tooling. 🙌

---

## 🤝 Contributing

Contributions are welcome!  
Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.

---

## 📄 License

Distributed under the **AGPL-3.0** license. See [LICENSE](LICENSE) for details.  
PRO extensions are available under a commercial license.

---

## 📬 Contact

- **Website:** [pentool.pro](https://pentool.pro)
- **Telegram:** [@sudores](https://t.me/sudores)
- **Email:** akashtanov2020@gmail.com
- **Author:** Anatoly Kashtanov (DoctorX)

---

⭐ If Pentool saves you time, a GitHub star helps the project grow — thanks!
