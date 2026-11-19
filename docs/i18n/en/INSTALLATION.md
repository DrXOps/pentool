# 📦 Pentool Installation Guide

Complete installation instructions for all platforms.

---

## System Requirements

### Minimum
- Python 3.10 or higher
- 512 MB RAM
- 100 MB disk space
- Linux, macOS, or Windows

### Recommended
- Python 3.11+
- 2 GB RAM
- 500 MB disk space (with history)
- Modern terminal with Unicode support

---

## Installation Methods

### Method 1: uv tool (Recommended)

[uv](https://docs.astral.sh/uv/) installs pentool in an isolated environment —
no virtual environment setup, no conflicts with system Python.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh   # Linux/macOS
# Windows: winget install --id=astral-sh.uv -e

# Install pentool
uv tool install pentool

# Verify
pentool --version
```

### Method 2: pip (Alternative)

```bash
# Create virtual environment (recommended to avoid conflicts)
python3 -m venv pentool-env
source pentool-env/bin/activate  # Linux/macOS
# or
pentool-env\Scripts\activate     # Windows

# Install
pip install pentool

# Verify
pentool --version
```

### Method 3: From Source (Development)

```bash
# Clone repository
git clone https://github.com/DrXOps/pentool.git
cd pentool

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies (uv creates .venv automatically)
uv sync

# Verify
uv run pentool --version
```

---

## JS Rendering (optional, but recommended)

Pentool's crawler can execute JavaScript to discover SPA/level-3 pages and
hidden API endpoints. The default engine is **Lightpanda** — a fast, light
browser (~20 MB RAM per run) that needs no full Chromium or Node.

Install the Lightpanda binary (Linux/macOS x86_64 / aarch64 release asset):

```bash
# 1. download the release binary for your platform from the Lightpanda repo
#    (lightpanda-io/browser), e.g. on Linux x86_64:
curl -L -o lightpanda \
  https://github.com/lightpanda-io/browser/releases/download/0.3.7/lightpanda-x86_64-linux
chmod +x lightpanda
# 2. put it somewhere on PATH, e.g.:
mkdir -p ~/.local/bin && mv lightpanda ~/.local/bin/
```

Pentool auto-detects the binary on `PATH` (or via `~/.local/bin`, `/usr/local/bin`,
`/usr/bin`, or the `LIGHTPANDA_BIN` env var). Without it, crawling still works but
does not execute JavaScript (falls back to plain HTTP).

> **`--smart` mode** (loading a page through the proxy) also uses Lightpanda
> for headless browsing — no separate Playwright/Chromium installation needed.
> Lightpanda handles JS rendering for the `--smart` CLI mode and the Spider module.
> If it is missing, `pentool --smart` asks before downloading it (about 150 MiB, one time). Non-interactive runs (CI) never download: use `--install-browser` or skip JS rendering (plain HTTP fallback).

---

## Platform-Specific Instructions

### Linux (Ubuntu/Debian)

```bash
# Install system Python (if needed)
sudo apt update
sudo apt install python3

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install pentool
uv tool install pentool

# Run
pentool
```

### macOS

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install uv via Homebrew
brew install uv
# or directly:
# curl -LsSf https://astral.sh/uv/install.sh | sh

# Install pentool
uv tool install pentool

# Run
pentool
```

### Windows

```powershell
# Install uv
winget install --id=astral-sh.uv -e
# or via PowerShell:
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Install pentool
uv tool install pentool

# Run
pentool
```

> **The TUI needs WSL2 on Windows.** The PowerShell commands above are enough for
> the CLI and headless scans (`--headless`). For the interactive interface — proxy,
> ANSI frames, hooks — use WSL2: see [Running on Windows via WSL2](#running-on-windows-via-wsl2).

---

## Running on Windows via WSL2

The TUI expects a POSIX terminal: the proxy, the hooks and the ANSI box-drawing
UI all rely on a UTF-8 locale. Inside WSL2 (Ubuntu) everything works as on Linux.
Run the commands from the **WSL shell**, not from PowerShell.

### 1. Install WSL2 (PowerShell, as Administrator)

```powershell
wsl --install -d Ubuntu-24.04
wsl --set-default-version 2
wsl --update
wsl --status
```

### 2. Locale and UTF-8 — this is what makes box-drawing characters work

```bash
sudo apt update
sudo apt install -y locales
sudo locale-gen en_US.UTF-8 ru_RU.UTF-8
sudo update-locale LANG=en_US.UTF-8
exec bash
echo $LANG    # must print en_US.UTF-8, not C and not POSIX
```

`LANG=C`, `POSIX` or an empty value is the usual reason for `?` instead of
frames and for mojibake in Cyrillic.

### 3. A font that actually has the glyphs

**Windows side** (for Windows Terminal): install **JetBrains Mono Nerd Font** or
**Cascadia Code NF**, then select it in the terminal profile. Emoji glyphs
(`▶ ✖ 💥 🧭`) are taken from **Segoe UI Emoji** as a fallback.

**WSL side** (for Kitty):

```bash
sudo apt install -y unzip curl fonts-noto-color-emoji
mkdir -p ~/.local/share/fonts && cd ~/.local/share/fonts
curl -LO https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip
unzip -o JetBrainsMono.zip && fc-cache -fv
```

### 4. Kitty (optional — Windows Terminal also works)

```bash
sudo apt install -y kitty
```

`~/.config/kitty/kitty.conf`:

```conf
font_family JetBrainsMono Nerd Font
font_size 12.0
# box drawing
symbol_map U+2500-U+257F JetBrainsMono Nerd Font
# emoji
symbol_map U+1F300-U+1FAFF Noto Color Emoji
# WSLg smoother defaults
sync_to_monitor no
repaint_delay 8
```

Start it with `kitty pentool`, or from Windows: `wsl.exe -e kitty pentool`.

If some panel icons are missing in your font, switch the icon set in
**Settings → Interface → Panel icons** (`unicode` / `ascii` / `emoji`).

### 5. Verify that the symbols are in place

```bash
python3 -c "print('┌────┬────┐\n│ OK │ 42 │\n└────┴────┘')"
printf '█ ▓ ▒ ░  →  ✔ ✖ ⚠\n'
infocmp -1 | head -3    # TERM must be *-256color, not dumb
```

### 6. If something still looks wrong

| Symptom | Cause | Fix |
|---|---|---|
| Frames of `?` or `+---+` | no UTF-8 locale | step 2, `export LANG=en_US.UTF-8` |
| Mojibake in Cyrillic | `LANG=C` / `POSIX` | step 2 |
| Wide frames, layout drifts | font lacks box-drawing glyphs | step 3 |
| Icons as squares | no emoji / Nerd font | step 3, or `ascii` icon set |
| TUI refuses to start | `TERM=dumb` | `export TERM=xterm-256color` |
| No colours | 8-colour terminal | Windows Terminal or Kitty |

## Development Installation

For contributing to Pentool:

```bash
# Clone with dev dependencies
git clone https://github.com/DrXOps/pentool.git
cd pentool

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project + all dev tools (.venv is created automatically)
uv sync

# Install pre-commit hooks
uv run pre-commit install

# Run tests
uv run pytest tests/unit/

# Run with coverage
uv run pytest tests/ --cov=pentool --cov-report=html
```

---

## Dependencies

Pentool installs these automatically:

### Core Dependencies
- `textual>=8.0.0` — TUI framework
- `aiohttp>=3.9.0` — Async HTTP client
- `aiosqlite>=0.19.0` — Async SQLite
- `cryptography>=41.0.0` — SSL/TLS support
- `click>=8.1.0` — CLI framework
- `pyyaml>=6.0` — Config files

### Optional Dependencies
- `pytest` — Testing (dev)
- `pytest-asyncio` — Async tests (dev)
- `pytest-cov` — Coverage (dev)

---

## Troubleshooting

### ImportError: No module named 'textual'

```bash
uv tool upgrade pentool
# or with pip:
pip install --upgrade textual
```

### Permission denied

```bash
# Use uv tool install — never touches system Python
uv tool install pentool
```

### Command not found: pentool

```bash
# Linux/macOS — add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"

# Or let uv manage it:
uv tool update-shell
```

### SSL certificate verify failed

```bash
uv tool install pentool --no-cache
```

---

## Updating

```bash
# uv
uv tool upgrade pentool

# pip
pip install --upgrade pentool
```

---

## Uninstallation

```bash
# uv
uv tool uninstall pentool

# pip
pip uninstall pentool

# Remove all data
rm -rf ~/.config/pentool
rm -rf ~/.local/share/pentool
```

---

## Next Steps

- Read [Quick Start Guide](QUICKSTART.md)
- Configure your first project
- Join [Telegram community](https://t.me/sudores)

---

**Need help?** Open an issue on [GitHub](https://github.com/DrXOps/pentool/issues)
