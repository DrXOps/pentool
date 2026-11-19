# 🤝 Contributing to Pentool

Thank you for your interest in contributing to Pentool! This document provides guidelines for contributing.

---

## Getting Started

### Prerequisites
- Python 3.10+
- Git
- Basic understanding of async Python
- Familiarity with Textual framework (for TUI changes)

### Development Setup

The project uses [`uv`](https://docs.astral.sh/uv/) for dependency management —
a plain `pip install -e` does not reproduce the environment (Python version,
locked dependencies, ruff version used by the hooks).

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/pentool.git
cd pentool

# Install uv (once per machine)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create .venv from uv.lock and install dev dependencies
uv sync

# PRO modules (Scanner, Recon) live in a submodule — optional for FREE work
git submodule update --init --recursive

# Pre-commit hooks (format, lint, guards)
uvx pre-commit install

# Verify: the same gate CI runs
bash scripts/run-tests.sh
```

**Windows:** run everything inside WSL2 (Ubuntu), not in PowerShell — the hooks,
proxy tests and the TUI expect a POSIX environment. Setup steps (WSL, UTF-8
locale, fonts, Kitty) are in
[`docs/i18n/en/INSTALLATION.md`](docs/i18n/en/INSTALLATION.md#running-on-windows-via-wsl2).

`scripts/run-tests.sh` is the only supported way to run the suite: it runs the
same command as CI **and** writes a marker file that the local hook gate reads.
Calling `pytest` directly is fine while iterating, but a commit is only accepted
after the scripted run.

---

## Project Structure

```
pentool/
├── core/              # Core functionality (EventBus, license, features)
├── modules/           # Business logic (proxy, scanner, intruder)
├── api/               # Public API facades
├── services/          # Orchestration layer
├── storage/           # Database layer (SQLite)
├── tui/               # TUI interface (Textual)
│   ├── screens/       # Application screens
│   ├── widgets/       # Custom widgets
│   └── dialogs/       # Modal dialogs
├── cli/               # CLI commands
├── plugins/           # Plugin system
└── utils/             # Utilities

tests/
├── unit/              # Unit tests
├── integration/       # Integration tests
├── snapshot/          # Snapshot tests
└── performance/       # Performance benchmarks
```

---

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

**Branch naming:**
- `feature/` — new features
- `fix/` — bug fixes
- `refactor/` — code refactoring
- `docs/` — documentation changes
- `test/` — test additions/changes

### 2. Make Changes

**Code style:**
- Follow PEP 8
- Use type hints everywhere
- Write docstrings for public functions
- Keep functions small and focused

**Example:**
```python
async def send_request(
    self,
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> Response:
    """Send HTTP request.

    Args:
        url: Target URL
        method: HTTP method (default: GET)
        headers: Optional headers dict

    Returns:
        Response object

    Raises:
        RequestError: If request fails
    """
    # Implementation
```

### 3. Write Tests

**Required for all changes:**
```bash
# Add unit tests
touch tests/unit/modules/test_your_feature.py

# Write tests
pytest tests/unit/modules/test_your_feature.py -v

# Check coverage
pytest tests/unit/ --cov=pentool --cov-report=term
```

**Test structure:**
```python
import pytest
from pentool.modules.your_module import YourClass

class TestYourClass:
    """Test YourClass functionality."""

    def test_basic_functionality(self):
        """Test basic operation."""
        obj = YourClass()
        result = obj.method()
        assert result == expected

    @pytest.mark.asyncio
    async def test_async_method(self):
        """Test async method."""
        obj = YourClass()
        result = await obj.async_method()
        assert result is not None
```

### 4. Run Tests

```bash
# The project gate (unit suite + quality marker) — use this before a commit
bash scripts/run-tests.sh

# A single file while iterating
uv run pytest tests/unit/modules/test_proxy.py -v

# With coverage
uv run pytest tests/unit/ --cov=pentool --cov-report=html

# Snapshot baselines are NOT part of the unit gate — run them explicitly
uv run pytest tests/snapshot
```

`tests/snapshot` is a separate suite on purpose: it compares rendered TUI
screens (`pytest-textual-snapshot`). If a UI change is intentional, refresh the
baselines with `uv run pytest tests/snapshot --snapshot-update` and mention it in
the commit message.

### 5. Commit Changes

**Commit message format:**
```
<type>: <short description>

<detailed description if needed>

<footer: issue references, breaking changes>
```

**Types:**
- `feat` — new feature
- `fix` — bug fix
- `refactor` — code refactoring
- `docs` — documentation
- `test` — tests
- `chore` — maintenance

**Example:**
```bash
git add .
git commit -m "feat: add Turbo Mode to Intruder

Implements HTTP Keep-Alive and connection pooling for 10x speed boost.

- Created pentool/modules/intruder_turbo.py
- Integrated into IntruderAPI
- Added turbo_mode parameter

Closes #123"
```

### 6. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create Pull Request on GitHub.

---

## Code Guidelines

### Automated guards (do not bypass)

Five checks run in pre-commit and CI. Each one exists because the same defect
came back more than once; each keeps a ratchet baseline that may only go down.

| Guard | Command | What it rejects |
|---|---|---|
| Silent handlers | `uv run python tools/check_silent_except.py` | `except ...: pass` with no record |
| Blind exception handling | `uv run python tools/check_broad_except.py` | new broad `except` that neither logs nor re-raises |
| Logging in data paths | `uv run python tools/check_logging_policy.py` | a broad `except` in `save/load/restore/...` that hides the cause |
| TUI CSS ↔ DOM | `uv run python tools/check_tui_css.py` | a `.tcss` selector with no widget behind it |
| Comment language | `uv run python tools/check_english_comments.py` | new Russian comments/docstrings in `.py` |

Two more hooks are about the repository itself:

- `tools/review_new_files.py` — every **added** file needs a decision in
  `.claude/state/new-file-decisions.tsv` (`keep` or `ignore`); `ignore` requires
  a matching `.gitignore` rule.
- `tests/unit/tui/test_toolbar_separators.py` — separators in toolbars are built
  with `Toolbar.row(...)` / `Toolbar.grouped(...)`, never with a hand-written
  `Static(" │ ", classes="toolbar-sep")`.

If a check fires on a line that is deliberately different, use the escape hatch
documented in that guard (`# logging-ok:`, `# i18n-ok:`), not `--no-verify`.

### Where the logs live

`~/.config/pentool/logs/pentool.log` (real runs) — the file is not rotated yet,
so it can grow large; delete it while the app is closed if it becomes unwieldy
(issue: `MYPLANS/tasks-pentool.md`, T-021).

### Python Style

```python
# Good
async def fetch_data(url: str, timeout: int = 30) -> dict:
    """Fetch data from URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=timeout) as response:
            return await response.json()

# Bad
def fetch_data(url,timeout=30):
    # No docstring, no type hints, not async
    pass
```

### Architecture Principles

1. **Separation of Concerns**
   - `modules/` — business logic, no UI
   - `api/` — thin facades
   - `tui/` — UI only, no business logic
   - `services/` — orchestration

2. **Event-Driven**
   - Use EventBus for module communication
   - No direct coupling between modules

3. **Async First**
   - Use async/await everywhere
   - No blocking operations in event loop

4. **Type Safety**
   - Type hints on all functions
   - Use dataclasses for data structures

---

## Adding New Features

### New Module

```bash
# 1. Create module
touch pentool/modules/your_module.py

# 2. Create API facade
touch pentool/api/your_module_api.py

# 3. Create service (if needed)
touch pentool/services/your_module_service.py

# 4. Create TUI screen
touch pentool/tui/screens/your_module/screen.py

# 5. Write tests
touch tests/unit/modules/test_your_module.py
touch tests/unit/api/test_your_module_api.py
```

### New Scanner Check

```python
# pentool/modules/scanner/checks/your_check.py
from pentool.modules.scanner.base import ScanCheck, Finding

class YourCheck(ScanCheck):
    """Check for your vulnerability."""

    name = "your_vuln"
    severity = "high"

    async def run(self, request, response):
        """Run the check."""
        if self._is_vulnerable(response):
            return Finding(
                type=self.name,
                name="Your Vulnerability",
                url=request.url,
                severity=self.severity,
                evidence="...",
            )
        return None
```

---

## Testing Guidelines

### Unit Tests
- Test one thing at a time
- Mock external dependencies
- Use fixtures for common setup
- Aim for >80% coverage

### Integration Tests
- Test module interactions
- Use real database (SQLite in memory)
- Test event flow

### Snapshot Tests
- For TUI screens
- Update with `--snapshot-update` when intentional

---

## Documentation

### Code Documentation
- Docstrings for all public functions
- Type hints everywhere
- Comments for complex logic

### User Documentation
- Update docs/ if adding user-facing features
- Add examples
- Update README.md if needed

---

## Pull Request Process

### Before Submitting

- [ ] Tests pass (`pytest tests/unit/`)
- [ ] Coverage maintained or improved
- [ ] Code follows style guidelines
- [ ] Docstrings added
- [ ] CHANGELOG.md updated (for features)
- [ ] Commits are clean and logical

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- Unit tests added: Yes/No
- Integration tests added: Yes/No
- Manual testing performed: Yes/No

## Checklist
- [ ] Code follows style guidelines
- [ ] Tests pass
- [ ] Documentation updated
- [ ] CHANGELOG updated

## Screenshots (if applicable)
```

### Review Process

1. Automated checks run (CI)
2. Maintainer reviews code
3. Address feedback
4. Approval and merge

---

## Release Process

(For maintainers)

```bash
# 1. Update version
# Edit pyproject.toml

# 2. Update CHANGELOG
# Add release notes

# 3. Create tag
git tag -a v1.x.x -m "Release 1.x.x"
git push origin v1.x.x

# 4. Build and publish
python -m build
twine upload dist/*

# 5. Create GitHub release
# With release notes
```

---

## Need Help?

- **Questions:** Open a Discussion on GitHub
- **Bugs:** Open an Issue
- **Chat:** Join Telegram
- **Email:** dev@pentool.pro

---

## Code of Conduct

- Be respectful
- Welcome newcomers
- Focus on constructive feedback
- Follow open source best practices

---

Thank you for contributing to Pentool! 🚀
