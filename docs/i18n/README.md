# Pentool Documentation Translations

This directory contains translations of Pentool documentation.

## Available Languages

- **English** (default) — `docs/*.md` OR `docs/i18n/en/*.md`
- **Russian** (Русский) — `docs/i18n/ru/*.md`
- **Chinese** (中文) — `docs/i18n/zh/*.md`
- **Hindi** (हिन्दी) — `docs/i18n/hi/*.md`

## Required Documents

Each language should have translations for:

1. **INSTALLATION.md** — Installation instructions for all platforms
2. **QUICKSTART.md** — 5-minute quick start guide
3. **USER_GUIDE.md** — Complete user manual with all modules
4. **API_CONTRACTS.md** — API documentation for plugin developers

## Translation Status

### Core Documentation

| Document | English | Russian | Chinese | Hindi |
|----------|---------|---------|---------|-------|
| INSTALLATION.md | ✅ | ✅ | ✅ | ✅ |
| QUICKSTART.md | ✅ | ✅ | ✅ | ✅ |
| USER_GUIDE.md | ✅ | ✅ | ✅ | ✅ |
| API_CONTRACTS.md | ✅ | ✅ | ✅ | ✅ |

**Total:** 16 files across 4 languages

Legend:
- ✅ Complete
- 🚧 In progress
- ⬜ Not started

## Contributing Translations

1. Copy the English version from `docs/*.md` to `docs/i18n/{lang}/`
2. Translate all user-facing text
3. Keep code examples unchanged
4. Keep command examples unchanged
5. Maintain markdown formatting
6. Update this README with translation status

## Translation Guidelines

### Do Translate
- All headings and body text
- Descriptions and explanations
- Error messages
- UI element descriptions

### Don't Translate
- Code examples (Python, bash, etc.)
- File paths and URLs
- Command-line arguments
- Technical terms (API, HTTP, JSON, etc.)
- Product names (Pentool, Burp Suite, etc.)

### Example

**English:**
```markdown
# Installation

Install Pentool using uv:

\`\`\`bash
uv tool install pentool
\`\`\`
```

**Russian:**
```markdown
# Установка

Установите Pentool через uv:

\`\`\`bash
uv tool install pentool
\`\`\`
```

## Directory Structure

```
docs/
├── INSTALLATION.md (English original)
├── QUICKSTART.md (English original)
├── USER_GUIDE.md (English original)
├── API_CONTRACTS.md (English original)
└── i18n/
    ├── README.md (this file)
    ├── en/ (English - optional mirror)
    ├── ru/ (Russian - Русский)
    │   ├── INSTALLATION.md
    │   ├── QUICKSTART.md
    │   ├── USER_GUIDE.md
    │   └── API_CONTRACTS.md
    ├── zh/ (Chinese - 中文)
    │   ├── INSTALLATION.md
    │   ├── QUICKSTART.md
    │   ├── USER_GUIDE.md
    │   └── API_CONTRACTS.md
    └── hi/ (Hindi - हिन्दी)
        ├── INSTALLATION.md
        ├── QUICKSTART.md
        ├── USER_GUIDE.md
        └── API_CONTRACTS.md
```

## Language Codes

- `en` — English
- `ru` — Russian (Русский)
- `zh` — Chinese (中文)
- `hi` — Hindi (हिन्दी)

## Notes

- All code in the project (Python files, comments) must be in English only
- Only user-facing documentation should be translated
- Keep technical accuracy when translating
- If unsure about a technical term, keep it in English
