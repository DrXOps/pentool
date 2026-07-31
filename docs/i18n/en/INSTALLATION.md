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

### Method 1: PyPI (Recommended)

```bash
# Create virtual environment (recommended)
python3 -m venv pentool-env
source pentool-env/bin/activate  # Linux/macOS
# or
pentool-env\Scripts\activate  # Windows

# Install
pip install pentool

# Verify
pentool --version
```

### Method 2: From Source

```bash
# Clone repository
git clone https://github.com/docxqwerty/pentool.git
cd pentool

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows

# Install in editable mode
pip install -e ".[dev]"

# Verify
pentool --version
```

### Method 3: pipx (Isolated Install)

```bash
# Install pipx
pip install pipx

# Install pentool
pipx install pentool

# Run
pentool
```

---

## Platform-Specific Instructions

### Linux (Ubuntu/Debian)

```bash
# Install system dependencies
sudo apt update
sudo apt install python3 python3-pip python3-venv

# Install pentool
pip3 install pentool

# Run
pentool
```

### macOS

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python@3.11

# Install pentool
pip3 install pentool

# Run
pentool
```

### Windows

```powershell
# Download Python from python.org (3.10+)
# Check "Add Python to PATH" during installation

# Open PowerShell or CMD
python -m pip install pentool

# Run
pentool
```

---

## Virtual Environment Setup

### Why use venv?
- Isolate dependencies
- Avoid conflicts with system Python
- Easy to remove (just delete folder)

### Create venv

```bash
# Linux/macOS
python3 -m venv ~/.pentool-venv
source ~/.pentool-venv/bin/activate

# Windows
python -m venv %USERPROFILE%\.pentool-venv
%USERPROFILE%\.pentool-venv\Scripts\activate
```

### Auto-activate (optional)

**Linux/macOS (.bashrc or .zshrc):**
```bash
alias pentool="source ~/.pentool-venv/bin/activate && pentool"
```

**Windows (PowerShell profile):**
```powershell
function pentool {
    & $env:USERPROFILE\.pentool-venv\Scripts\Activate.ps1
    & pentool
}
```

---

## Development Installation

For contributing to Pentool:

```bash
# Clone with dev dependencies
git clone https://github.com/docxqwerty/pentool.git
cd pentool

# Create venv
python3 -m venv venv
source venv/bin/activate

# Install with dev tools
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/unit/

# Run with coverage
pytest tests/ --cov=pentool --cov-report=html
```

---

## Dependencies

Pentool installs these automatically:

### Core Dependencies
- `textual>=0.40.0` — TUI framework
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

**Solution:**
```bash
pip install --upgrade textual
```

### Permission denied

**Linux/macOS:**
```bash
pip install --user pentool
# or use venv (recommended)
```

**Windows (Admin):**
Run PowerShell as Administrator

### SSL certificate verify failed

**Solution:**
```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org pentool
```

### Command not found: pentool

**Check PATH:**
```bash
# Linux/macOS
echo $PATH
# Should include ~/.local/bin or venv/bin

# Add to PATH if needed
export PATH="$HOME/.local/bin:$PATH"
```

**Windows:**
```powershell
# Check PATH
$env:PATH

# Add to PATH (Control Panel → System → Environment Variables)
```

### Performance issues

**Increase buffer sizes:**
```bash
# Set environment variable
export PENTOOL_BUFFER_SIZE=8192
pentool
```

**Disable animations:**
```bash
pentool --no-animations
```

---

## Updating

### PyPI install
```bash
pip install --upgrade pentool
```

### Source install
```bash
cd pentool
git pull
pip install -e ".[dev]"
```

---

## Uninstallation

### PyPI install
```bash
pip uninstall pentool
```

### Source install
```bash
pip uninstall pentool
rm -rf ~/pentool  # Remove source directory
```

### Remove all data
```bash
rm -rf ~/.config/pentool  # Config
rm -rf ~/.local/share/pentool  # Projects
```

---

## Docker (Experimental)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install -e .

CMD ["pentool"]
```

```bash
docker build -t pentool .
docker run -it -p 8888:8888 pentool
```

---

## Next Steps

- Read [Quick Start Guide](QUICKSTART.md)
- Configure your first project
- Join [Discord community](https://t.me/sudores)

---

**Need help?** Open an issue on [GitHub](https://github.com/docxqwerty/pentool/issues)
