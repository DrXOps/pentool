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

---

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
