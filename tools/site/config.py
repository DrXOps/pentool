"""Single source of truth for the marketing site.

Everything a human may want to change lives here: URLs, contacts, prices, the
list of languages. Page texts live in ``tools/site/content/<lang>.py``; the
structure of those texts is identical for every language (a test enforces it).

Run the generator after editing:

    python tools/site/build.py
"""

from __future__ import annotations

#: Where the generated files go (GitHub Pages serves this directory).
OUTPUT_DIR = "docs"

#: Absolute site root. Used for canonical links and Open Graph.
DOMAIN = "https://pentool.pro"

#: Product identity.
BRAND = "Pentool"
TAGLINE_EN = "Web pentesting in your terminal"

#: Payment: Coinso issues the invoice. The amount is computed server-side by the
#: licence worker; the site only displays the price and forwards e-mail + slots.
CHECKOUT_API = "https://pentool-license.akashtanov2020.workers.dev/api/checkout"

#: PRO price, USD per year. First slot, then every additional slot.
PRICE_FIRST_SLOT = 29
PRICE_EXTRA_SLOT = 19

#: Largest number of slots the licence worker accepts (see /api/checkout).
MAX_SLOTS = 20

#: Slot counts offered in the picker.
SLOT_CHOICES = (1, 3, 5, 10)

#: Outbound links. Keys are used from content with the "@link:key" form.
LINKS = {
    "github": "https://github.com/DrXOps/pentool",
    "issues": "https://github.com/DrXOps/pentool/issues",
    "contributing": "https://github.com/DrXOps/pentool/blob/main/CONTRIBUTING.md",
    "license": "https://github.com/DrXOps/pentool/blob/main/LICENSE",
    "pypi": "https://pypi.org/project/pentool/",
    "license_portal": "https://license.pentool.pro/",
    "telegram_channel": "https://t.me/pentool_pro",
    "telegram_author": "https://t.me/sudores",
    "email": "mailto:support@pentool.pro",
    "ci_guide": "https://github.com/DrXOps/pentool/blob/main/docs/CI_CD.md",
    "plugin_api": "https://github.com/DrXOps/pentool/blob/main/docs/API_CONTRACTS.md",
}


#: Per-language documentation on GitHub (the i18n tree exists for all four).
def docs_url(lang: str, page: str) -> str:
    """GitHub URL of a documentation page in the requested language."""
    name = page.upper()
    return f"https://github.com/DrXOps/pentool/blob/main/docs/i18n/{lang}/{name}.md"


#: Languages, in the order they appear in the switcher. Code, native name, short label.
LANGS: tuple[tuple[str, str, str], ...] = (
    ("ru", "Русский", "RU"),
    ("en", "English", "EN"),
    ("zh", "中文", "ZH"),
    ("hi", "हिन्दी", "HI"),
)

#: The language served from the site root. Other languages live in <code>/<lang>/.
DEFAULT_LANG = "en"

#: Language of the site owner; used only to pick a fallback if content is missing.
FALLBACK_LANG = "en"

#: Pages and the file each one is written to, relative to OUTPUT_DIR.
#: "{prefix}" is the language directory ("" for DEFAULT_LANG, "ru/" otherwise).
PAGES: dict[str, str] = {
    "index": "{prefix}index.html",
    "pricing": "{prefix}pricing.html",
    "privacy": "{prefix}privacy.html",
    "terms": "{prefix}terms.html",
    "success": "{prefix}payment/success.html",
    "fail": "{prefix}payment/fail.html",
}


def page_prefix(lang: str) -> str:
    """Directory prefix of a language: ``""`` for the default language, ``"ru/"`` otherwise."""
    return "" if lang == DEFAULT_LANG else f"{lang}/"


#: Payment return URLs are hardcoded in the licence worker; the English pages
#: must stay at exactly these paths.
PAYMENT_SUCCESS_PATH = "payment/success.html"
PAYMENT_FAIL_PATH = "payment/fail.html"

#: Old addresses that must keep working (links in the app, in e-mails, in the wild).
LEGACY_REDIRECTS: dict[str, str] = {
    "pricing.ru.html": "/ru/pricing.html",
    "privacy.ru.html": "/ru/privacy.html",
    "terms.ru.html": "/ru/terms.html",
    "upgrade.html": "/pricing.html",
    # The desktop app opens https://pentool.pro/pricing (without .html).
    "pricing/index.html": "/pricing.html",
}

#: Files removed from docs/ when the site is rebuilt (superseded by generated pages).
REMOVE_STALE: tuple[str, ...] = ("pricing-block.html",)
