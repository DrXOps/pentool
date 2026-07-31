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

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/pentool.git
cd pentool

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run tests to verify setup
pytest tests/unit/ -v
```

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
# All unit tests
pytest tests/unit/ -v

# Specific test file
pytest tests/unit/modules/test_proxy.py -v

# With coverage
pytest tests/unit/ --cov=pentool --cov-report=html

# Integration tests (if applicable)
pytest tests/integration/ -v
```

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
