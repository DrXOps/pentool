# Changelog

All notable changes to Pentool will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.5] - 2026-07-27

### 🐛 Fixed
- **Critical: fresh `pip install pentool` still couldn't launch the TUI
  after 0.1.4.** Two separate packaging bugs:
  - `*.tcss` (Textual CSS) files — 33 of them, one next to nearly every
    screen/widget — were never included in the built wheel. setuptools
    only bundles `.py` files by default, so every screen crashed with
    `FileNotFoundError` on `Path(__file__).parent / "screen.tcss"` the
    moment it tried to load its own CSS. Added
    `[tool.setuptools.package-data]` so all `*.tcss` files ship in the
    wheel.
  - `pyproject.toml`'s `[project.dependencies]` was missing
    `textual-fastdatatable` and `pyarrow` (used unconditionally by the
    Proxy screen's DataTable backend) and `psutil` (used by the
    Dashboard). They were listed in `requirements.txt` but never made it
    into the actual PyPI package metadata, so `pip install pentool` alone
    didn't pull them in.
  - Verified by building the wheel locally and installing it into a
    fresh venv: all `.tcss` files are now present in the wheel and the
    dependency set matches what the code actually imports.

---

## [0.1.4] - 2026-07-27

### 🐛 Fixed
- **Critical: fresh `pip install pentool` couldn't launch the TUI at all.**
  Scanner (`pentool/api/scanner_api.py`, `pentool/modules/scanner/`,
  `pentool/tui/screens/scanner/`) is a PRO-only module distributed
  separately via `pentool license trial`/`activate` — it's gitignored and
  never shipped in the PyPI package. But `pentool/tui/app.py` unconditionally
  imported it at startup, so every FREE user hit `ModuleNotFoundError`
  before the TUI could even start (confirmed on a real VPS running 0.1.3).
  Now the import is optional: without the PRO package, the Scanner tab
  shows a short "Scanner is a PRO feature — run `pentool license trial`"
  message instead of crashing, and `pentool scan active/report` print the
  same hint and exit cleanly instead of raising.

---

## [0.1.3] - 2026-07-27

### 🐛 Fixed
- **Critical: `pentool` command didn't launch the TUI.** The PyPI package's
  console_script entry point pointed directly at the Click command group
  (`pentool.cli.main:cli`) instead of `pentool.__main__:main`, which contains
  the actual "no args → launch TUI" logic. Running bare `pentool` printed
  `--help` instead of starting the TUI on every fresh `pip install` —
  including on headless VPS installs. Now fixed: `pentool` with no
  arguments launches the TUI as documented.
- CI: public test workflows no longer attempt to check out the private
  `pentool-pro` submodule (which the default `GITHUB_TOKEN` can't access).

---

## [1.0.0] - 2026-08-01

### 🎉 Initial Release

First public release of Pentool - Modern Web Pentesting TUI.

### ✨ Features

#### Core Tools
- **Proxy** — HTTP/HTTPS interception with SSL/TLS support
- **Repeater** — Request modification and replay with tabs
- **Intruder** — Automated attacks with 4 attack types (Sniper, Battering Ram, Pitchfork, Cluster Bomb)
- **Decoder** — Encode/decode various formats (Base64, URL, HTML, Hex, etc.)
- **Comparer** — Side-by-side request/response comparison
- **Scanner** — 23 vulnerability checks (XSS, SQLi, SSRF, etc.)
- **Spider** — Automatic site crawling
- **Sequencer** — Token randomness analysis
- **WebSocket** — WebSocket interception and modification

#### Advanced Features
- **Turbo Mode Intruder** 🚀 — 10x speed boost with HTTP Keep-Alive and connection pooling (100-200 req/sec)
- **HTTPQL** — Powerful SQL-like filtering for request history
- **Match & Replace** — Automatic request/response modification
- **Target Scope** — Define testing boundaries
- **Plugin System** — Extensible architecture
- **Event-Driven Architecture** — Decoupled modules via EventBus

#### Commercial Plans
- **4 Pricing Tiers** — Free, Lite ($29/mo), Medium ($99/mo), Full ($299/mo)
- **20+ Feature Gates** — Automated feature and limit enforcement
- **License System** — Commercial license support

#### SaaS Ready (40%)
- **Storage Interface** — Abstract database layer (SQLite ↔ PostgreSQL)
- **API Documentation** — Complete API contracts for 9 modules
- **7-Phase Roadmap** — Clear path to full SaaS transformation

### 🔧 Technical

#### Architecture
- **Clean Architecture** — Core, Modules, API, Services, TUI layers
- **Async-First** — Full async/await support with asyncio
- **Type-Safe** — Complete type hints throughout codebase
- **Event-Driven** — EventBus for module communication

#### Testing
- **1,348 Unit Tests** — 99.1% passing
- **29% Code Coverage** — Core modules 90%+ coverage
- **Integration Tests** — For critical workflows
- **Snapshot Tests** — For TUI screens

#### Performance
- **Turbo Mode** — 10x faster attacks via connection pooling
- **Async I/O** — Non-blocking operations throughout
- **SQLite Backend** — Fast local storage

### 📚 Documentation
- Complete README with examples
- Quick Start guide
- Installation guide for all platforms
- API reference documentation
- Architecture audit (7.5/10 rating)
- Contributing guidelines

### 🐛 Known Issues
- Integration tests need debugging (Textual Pilot async issues)
- WebSocket intercept may have edge cases
- Dashboard layout needs alignment fixes
- Some TUI tests are flaky

### 🔮 Planned for v1.1
- **UX Improvements**:
  - Tab counters (History (42))
  - Better checkbox visibility
  - Cursor hover effects
  - Dashboard layout fixes
  - WebSocket history filtering
  - Syntax highlighting in Intruder
  - Ctrl+A select all everywhere
  
- **Smart Scanner** — WAF detection and adaptive payloads
- **AI-Powered Analysis** — GPT-4 vulnerability assessment
- **Advanced Reports** — HTML/PDF export
- **Collaboration Features** — Team projects and sharing

### 📊 Statistics
- **34,242 lines of code**
- **159 Python files**
- **23 scanner checks**
- **1,404 total tests**
- **7 hours of AI-assisted development**

### 🙏 Credits
- Developed with Claude Opus 4.8 (1M context)
- Inspired by Burp Suite
- Built with Textual framework
- Community feedback from beta testers

---

## [Unreleased]

### Added
- Nothing yet

### Changed
- Nothing yet

### Fixed
- Nothing yet

---

## Version History

- **1.0.0** (2026-08-01) — Initial release

---

**Note:** This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality
- **PATCH** version for backwards-compatible bug fixes

[1.0.0]: https://github.com/docxqwerty/pentool/releases/tag/v1.0.0
[Unreleased]: https://github.com/docxqwerty/pentool/compare/v1.0.0...HEAD
