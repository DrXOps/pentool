"""Guards for the marketing site.

The site is generated (``tools/site/build.py``) from four language modules, so the
checks here are about the properties a generator is supposed to guarantee and a
hand-written page set kept losing:

* every language has the same pages with the same structure (no half-translated blocks);
* every page has exactly one ``<h1>``, a matching ``lang``, a canonical URL and
  ``hreflang`` links to all four languages;
* every internal link points at a file the build actually writes;
* no page repeats a claim the product does not implement (the reason this site was
  rewritten: "10x", ``pentool scan active``, a CryptoProc provider, a trial command);
* the markup is balanced (no stray closing tag silently breaking the layout).
"""

from __future__ import annotations

import html.parser
import re
from pathlib import Path

import pytest

from tools.site import build as site_build
from tools.site import config
from tools.site.content import MODULES, check_parity

ROOT = Path(__file__).resolve().parents[2]

#: Claims that must never come back. They were in the old pages and were not true.
FORBIDDEN = (
    "cryptoproc",
    "scan active",
    "license trial",
    "10×",
    "10x",
    "phone home",
    "звонит домой",
    "async из коробки",
    "без java",
    "получить pro-триал",
    "get pro trial",
    "keep-alive + пул соединений",  # droplet of the old "10x" feature card
)

#: Paths served from docs/ as hand-maintained files (not produced by the generator).
STATIC_PREFIXES = ("assets/", "icons/", "screens/")

VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _Balance(html.parser.HTMLParser):
    """Collect tag-nesting errors (a stray closing tag is a silent layout bug)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if not self.stack:
            self.errors.append(f"unexpected </{tag}>")
            return
        if self.stack[-1] != tag:
            self.errors.append(f"</{tag}> closes <{self.stack[-1]}>")
            self.stack.pop()
            return
        self.stack.pop()


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the whole site into a temporary directory (docs/ is not touched)."""
    output = tmp_path_factory.mktemp("site")
    original = site_build.OUTPUT
    site_build.OUTPUT = output
    try:
        assert site_build.build() == 0
    finally:
        site_build.OUTPUT = original
    return output


def _written_pages() -> list[tuple[str, str, str]]:
    """(language, page, relative path) for every generated page."""
    rows: list[tuple[str, str, str]] = []
    for lang in MODULES:
        for page, template in config.PAGES.items():
            rows.append((lang, page, template.format(prefix=config.page_prefix(lang))))
    return rows


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── Content ───────────────────────────────────────────────────────────────────


def test_languages_describe_the_same_structure() -> None:
    problems = check_parity()
    assert not problems, "translations differ from the reference language:\n" + "\n".join(problems)


def test_every_language_has_every_page() -> None:
    assert set(MODULES) == {code for code, _native, _short in config.LANGS}
    for lang, module in MODULES.items():
        assert set(module.PAGES) == set(config.PAGES), f"{lang}: page set differs"


# ── Generated pages ───────────────────────────────────────────────────────────


def test_every_page_is_written(site: Path) -> None:
    for lang, page, relative in _written_pages():
        path = site / relative
        assert path.is_file(), f"{lang}/{page}: {relative} was not written"
        assert path.stat().st_size > 2000, f"{lang}/{page}: suspiciously small"


@pytest.mark.parametrize(("lang", "page", "relative"), _written_pages())
def test_page_structure(site: Path, lang: str, page: str, relative: str) -> None:
    text = _text(site / relative)
    assert text.count("<h1") == 1, "a page must have exactly one <h1>"
    assert f'<html lang="{lang}">' in text, "the html lang attribute must match the page"
    assert f'<body data-page="{page}"' in text
    assert '<link rel="canonical" href="https://pentool.pro' in text
    for code, _native, _short in config.LANGS:
        assert f'hreflang="{code}"' in text, f"missing hreflang for {code}"
    assert '<meta name="description" content="' in text


@pytest.mark.parametrize(("lang", "page", "relative"), _written_pages())
def test_markup_is_balanced(site: Path, lang: str, page: str, relative: str) -> None:
    parser = _Balance()
    parser.feed(_text(site / relative))
    assert not parser.errors, f"{lang}/{page}: {parser.errors[:5]}"
    assert not parser.stack, f"{lang}/{page}: unclosed tags {parser.stack[:5]}"


@pytest.mark.parametrize(("lang", "page", "relative"), _written_pages())
def test_internal_links_resolve(site: Path, lang: str, page: str, relative: str) -> None:
    text = _text(site / relative)
    targets = set(re.findall(r'href="(/[^"#?]*)(?:[#?][^"]*)?"', text))
    for target in targets:
        stripped = target.lstrip("/")
        if stripped.startswith(STATIC_PREFIXES):
            # Stylesheets, icons and screenshots are maintained by hand in docs/.
            candidate = ROOT / config.OUTPUT_DIR / stripped
        else:
            candidate = site / stripped
            if target.endswith("/"):
                candidate = candidate / "index.html"
        assert candidate.is_file(), f"{lang}/{page}: dead internal link {target}"


def test_no_client_side_translation(site: Path) -> None:
    """Languages are separate pages now; the old JS dictionary must not come back."""
    for _lang, _page, relative in _written_pages():
        text = _text(site / relative)
        assert "data-i18n" not in text
        assert "pentool_lang" not in text


def test_old_claims_are_gone(site: Path) -> None:
    offenders: list[str] = []
    for _lang, _page, relative in _written_pages():
        haystack = _text(site / relative).lower()
        for phrase in FORBIDDEN:
            if phrase in haystack:
                offenders.append(f"{relative}: {phrase!r}")
    assert not offenders, "claims that are not true in the product:\n" + "\n".join(offenders)


def test_pricing_page_is_wired_to_checkout(site: Path) -> None:
    for lang in MODULES:
        relative = config.PAGES["pricing"].format(prefix=config.page_prefix(lang))
        text = _text(site / relative)
        assert config.CHECKOUT_API in text
        assert f'data-price-first="{config.PRICE_FIRST_SLOT}"' in text
        assert f'data-price-extra="{config.PRICE_EXTRA_SLOT}"' in text
        assert 'id="buy-modal"' in text
        assert 'data-buy="pro"' in text
        for slots in config.SLOT_CHOICES:
            assert f'data-slots="{slots}"' in text
        assert f"${config.PRICE_FIRST_SLOT}" in text


def test_language_switcher_links_every_language(site: Path) -> None:
    for lang in MODULES:
        relative = config.PAGES["pricing"].format(prefix=config.page_prefix(lang))
        text = _text(site / relative)
        for code in MODULES:
            expected = render_page_path("pricing", code)
            assert f'href="{expected}"' in text, f"{lang}: switcher misses {code}"


def render_page_path(page: str, lang: str) -> str:
    """Public path of a page (uses the same helper as the generator)."""
    from tools.site.render import page_path

    return page_path(page, lang)


def test_legacy_urls_still_work(site: Path) -> None:
    for path, target in config.LEGACY_REDIRECTS.items():
        stub = site / path
        assert stub.is_file(), f"old address {path} disappeared"
        text = _text(stub)
        assert f"url={target}" in text, f"{path}: must redirect to {target}"
        # The payment provider calls these two exact addresses.
    for path in (config.PAYMENT_SUCCESS_PATH, config.PAYMENT_FAIL_PATH):
        assert (site / path).is_file(), f"payment return URL {path} is missing"
