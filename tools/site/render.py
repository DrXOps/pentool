"""HTML rendering for the marketing site.

Two rules keep the site consistent:

* one page shell (``layout``) for every page — head, navigation, footer, language
  switcher — so a change of chrome happens in one place;
* pages are assembled from a small set of *blocks* (``BLOCKS`` below). Content
  modules describe blocks as data, never as raw page HTML, so the markup cannot
  drift between pages or between languages.

Content strings may contain inline HTML (``<strong>``, ``<code>``, ``<a>``) —
they are written by the project, not by visitors, and therefore are not escaped.
Everything else (URLs, attributes) goes through ``esc``.
"""

from __future__ import annotations

import html
import re
from typing import Any

from . import config

#: Inline tags allowed in content strings; anything else gets escaped.
_INLINE_TAGS = ("strong", "em", "code", "a", "br")


def esc(value: str) -> str:
    """Escape a string for use in an attribute or as plain text."""
    return html.escape(str(value), quote=True)


def page_path(page: str, lang: str) -> str:
    """Site-absolute path of a page, e.g. ``/ru/pricing.html``.

    The home page of a language is a directory: ``/`` for the default language and
    ``/ru/`` for the others — both are served by GitHub Pages without a redirect.
    """
    prefix = config.page_prefix(lang)
    if page == "index":
        return f"/{prefix}" if prefix else "/"
    return "/" + config.PAGES[page].format(prefix=prefix)


def resolve_href(href: str, lang: str) -> str:
    """Resolve a content link.

    ``@<page>``          another page of this site in the same language
    ``@<page>#anchor``   … with an anchor
    ``@link:<key>``      an outbound URL from ``config.LINKS``
    ``@docs:<page>``     a documentation page on GitHub in this language
    ``#anchor``          in-page anchor
    ``http…``/``mailto…`` absolute link, kept as is
    """
    if href.startswith("@link:"):
        return config.LINKS[href[len("@link:") :]]
    if href.startswith("@docs:"):
        return config.docs_url(lang, href[len("@docs:") :])
    if href.startswith("@"):
        rest = href[1:]
        page, _, anchor = rest.partition("#")
        if page not in config.PAGES:
            raise KeyError(f"unknown page in href: {href!r}")
        path = page_path(page, lang)
        return f"{path}#{anchor}" if anchor else path
    return href


def _href_attr(href: str, lang: str) -> str:
    url = resolve_href(href, lang)
    target = ""
    if url.startswith("http") and not url.startswith(config.DOMAIN):
        target = ' target="_blank" rel="noopener"'
    return f'href="{esc(url)}"{target}'


# ── Block renderers ───────────────────────────────────────────────────────────
# Every renderer takes (block, lang) and returns an HTML string.


def _render_p(block: dict[str, Any], lang: str) -> str:
    return f'<p class="prose">{block["text"]}</p>'


def _render_lead(block: dict[str, Any], lang: str) -> str:
    return f'<p class="prose prose-lead">{block["text"]}</p>'


def _render_list(block: dict[str, Any], lang: str) -> str:
    tag = "ol" if block.get("ordered") else "ul"
    items = "".join(f"<li>{item}</li>" for item in block["items"])
    return f'<{tag} class="prose-list">{items}</{tag}>'


def _render_cards(block: dict[str, Any], lang: str) -> str:
    cards = []
    for card in block["items"]:
        glyph = card.get("glyph", "")
        tag = card.get("tag", "")
        tag_html = f'<span class="tag tag-pro">{esc(tag)}</span>' if tag else ""
        glyph_html = f'<div class="card-glyph" aria-hidden="true">{glyph}</div>' if glyph else ""
        cards.append(
            f'<article class="card">{glyph_html}'
            f'<h3 class="card-title">{card["title"]}{tag_html}</h3>'
            f'<p class="card-text">{card["text"]}</p></article>'
        )
    return f'<div class="card-grid">{"".join(cards)}</div>'


def _render_modules(block: dict[str, Any], lang: str) -> str:
    cards = []
    for card in block["items"]:
        tag = card.get("tag", "")
        tag_html = f'<span class="tag tag-pro">{esc(tag)}</span>' if tag else ""
        cards.append(
            f'<article class="card card-module">'
            f'<h3 class="module-name">{esc(card["name"])}{tag_html}</h3>'
            f'<p class="card-text">{card["text"]}</p></article>'
        )
    note = f'<p class="note">{block["copy"]}</p>' if block.get("copy") else ""
    return f'<div class="card-grid card-grid-modules">{"".join(cards)}</div>{note}'


def _render_steps(block: dict[str, Any], lang: str) -> str:
    steps = []
    for index, step in enumerate(block["items"], start=1):
        steps.append(
            f'<div class="step"><div class="step-num">{index:02d}</div>'
            f'<h3 class="step-title">{step["title"]}</h3>'
            f'<p class="step-text">{step["text"]}</p></div>'
        )
    return f'<div class="steps">{"".join(steps)}</div>'


def _render_table(block: dict[str, Any], lang: str) -> str:
    head = "".join(f"<th>{cell}</th>" for cell in block["head"])
    rows = []
    for row in block["rows"]:
        cells = "".join(f"<td>{cell}</td>" for cell in row)
        rows.append(f"<tr>{cells}</tr>")
    note = f'<p class="note">{block["note"]}</p>' if block.get("note") else ""
    return (
        '<div class="table-wrap"><table class="compare">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>{note}"
    )


def _render_term(block: dict[str, Any], lang: str) -> str:
    lines = []
    for line in block["lines"]:
        kind = line.get("k", "out")
        lines.append(f'<div class="term-line term-{esc(kind)}">{line["text"]}</div>')
    title = esc(block.get("title", ""))
    copy = block.get("copy", "")
    return (
        '<div class="term">'
        f'<div class="term-bar"><span class="term-dot"></span><span class="term-dot"></span>'
        f'<span class="term-dot"></span><span class="term-title">{title}</span></div>'
        f'<div class="term-body">{"".join(lines)}</div></div>'
    ) + (f'<p class="note">{copy}</p>' if copy else "")


def _render_faq(block: dict[str, Any], lang: str) -> str:
    items = []
    for item in block["items"]:
        items.append(
            f'<details class="faq"><summary>{item["q"]}<span class="faq-mark" aria-hidden="true"></span>'
            f'</summary><div class="faq-body">{item["a"]}</div></details>'
        )
    return f'<div class="faq-list">{"".join(items)}</div>'


def _render_note(block: dict[str, Any], lang: str) -> str:
    return f'<aside class="callout">{block["text"]}</aside>'


def _render_buttons(block: dict[str, Any], lang: str) -> str:
    return render_buttons(block["items"], lang, center=block.get("center", False))


def _render_plans(block: dict[str, Any], lang: str) -> str:
    plans = []
    for plan in block["items"]:
        featured = " plan-featured" if plan.get("featured") else ""
        badge = f'<div class="plan-badge">{esc(plan["badge"])}</div>' if plan.get("badge") else ""
        features = "".join(
            f'<li class="plan-feature{" is-off" if not item["ok"] else ""}">'
            f'<span class="mark" aria-hidden="true">{"✓" if item["ok"] else "—"}</span>'
            f"<span>{item['text']}</span></li>"
            for item in plan["features"]
        )
        picker = _render_slot_picker(plan, lang) if plan.get("slots_picker") else ""
        note = f'<p class="plan-note">{plan["note"]}</p>' if plan.get("note") else ""
        if plan.get("price_from_config"):
            price = f'<span id="plan-price">${config.PRICE_FIRST_SLOT}</span>'
        else:
            price = plan.get("price", "")
        if plan.get("period_template"):
            first = config.SLOT_CHOICES[0]
            period = (
                f'<div class="plan-period" id="plan-period">{plan["period_template"].replace("{n}", str(first))}</div>'
            )
        elif plan.get("period"):
            period = f'<div class="plan-period">{plan["period"]}</div>'
        else:
            period = ""
        cta = _render_plan_cta(plan["cta"], lang)
        plans.append(
            f'<article class="plan{featured}">{badge}'
            f'<h3 class="plan-name">{esc(plan["name"])}</h3>'
            f'<div class="plan-price">{price}<span class="plan-suffix">{plan.get("suffix", "")}</span></div>'
            f"{period}{picker}"
            f'<ul class="plan-features">{features}</ul>{cta}{note}</article>'
        )
    return f'<div class="plans">{"".join(plans)}</div>'


def _render_slot_picker(plan: dict[str, Any], lang: str) -> str:
    # Prices arrive through data attributes so that config.py stays the only place
    # where money is defined; the script only formats them.
    buttons = "".join(
        f'<button type="button" class="slot-btn{" is-active" if slots == config.SLOT_CHOICES[0] else ""}" '
        f'data-slots="{slots}">{slots}</button>'
        for slots in config.SLOT_CHOICES
    )
    template = esc(plan.get("period_template", ""))
    return (
        f'<div class="slot-picker" data-period-template="{template}">'
        f'<div class="slot-label">{esc(UI_TEXT[lang]["slots_label"])}</div>'
        f'<div class="slot-buttons" role="group" aria-label="{esc(UI_TEXT[lang]["slots_label"])}">{buttons}</div>'
        f'<p class="slot-hint">{esc(UI_TEXT[lang]["slots_hint"])}</p></div>'
    )


def _render_plan_cta(cta: dict[str, Any], lang: str) -> str:
    style = cta.get("style", "ghost")
    attrs = ""
    if cta.get("id"):
        attrs += f' id="{esc(cta["id"])}"'
    if cta.get("action") == "buy":
        attrs += ' data-buy="pro"'
        return f'<button type="button" class="btn btn-{style} plan-cta"{attrs}>{cta["label"]}</button>'
    return f'<a class="btn btn-{style} plan-cta"{attrs} {_href_attr(cta["href"], lang)}>{cta["label"]}</a>'


def _render_cta(block: dict[str, Any], lang: str) -> str:
    buttons = render_buttons(block.get("buttons", []), lang, center=True)
    text = f'<p class="cta-text">{block["text"]}</p>' if block.get("text") else ""
    return f'<div class="cta-band"><h2 class="cta-title">{block["title"]}</h2>{text}{buttons}</div>'


BLOCKS = {
    "p": _render_p,
    "lead": _render_lead,
    "list": _render_list,
    "cards": _render_cards,
    "modules": _render_modules,
    "steps": _render_steps,
    "table": _render_table,
    "term": _render_term,
    "faq": _render_faq,
    "note": _render_note,
    "buttons": _render_buttons,
    "plans": _render_plans,
    "cta": _render_cta,
}


def render_blocks(blocks: list[dict[str, Any]], lang: str) -> str:
    """Render a list of content blocks."""
    parts = []
    for block in blocks:
        kind = block["t"]
        try:
            renderer = BLOCKS[kind]
        except KeyError:  # pragma: no cover - content error, fails loudly on build
            raise ValueError(f"unknown block type: {kind!r}") from None
        parts.append(renderer(block, lang))
    return "\n".join(parts)


def render_buttons(buttons: list[dict[str, Any]], lang: str, center: bool = False) -> str:
    """A row of call-to-action buttons."""
    items = []
    for button in buttons:
        style = button.get("style", "ghost")
        if button.get("action") == "buy":
            items.append(f'<button type="button" class="btn btn-{style}" data-buy="pro">{button["label"]}</button>')
        else:
            items.append(f'<a class="btn btn-{style}" {_href_attr(button["href"], lang)}>{button["label"]}</a>')
    cls = "btn-row is-center" if center else "btn-row"
    return f'<div class="{cls}">{"".join(items)}</div>'


def render_section(section: dict[str, Any], lang: str) -> str:
    """A page section: eyebrow, title, lead and blocks."""
    ident = f' id="{esc(section["id"])}"' if section.get("id") else ""
    eyebrow = f'<p class="eyebrow">{section["eyebrow"]}</p>' if section.get("eyebrow") else ""
    lead = f'<p class="section-lead">{section["lead"]}</p>' if section.get("lead") else ""
    title = f'<h2 class="section-title">{section["title"]}</h2>' if section.get("title") else ""
    head = f'<header class="section-head">{eyebrow}{title}{lead}</header>' if (eyebrow or title or lead) else ""
    return f'<section class="section"{ident}><div class="wrap">{head}{render_blocks(section["blocks"], lang)}</div></section>'


# ── Page shell ────────────────────────────────────────────────────────────────

#: Small strings that are the same on every page of a language.
#: Filled by ``content/__init__.py`` before rendering.
UI_TEXT: dict[str, dict[str, str]] = {}

_HEAD_EXTRA = {
    "success": '<meta name="robots" content="noindex" />',
    "fail": '<meta name="robots" content="noindex" />',
}


def _nav(page: str, lang: str, nav: dict[str, str]) -> str:
    links = [
        ("index#modules", nav["features"], "features"),
        ("index#install", nav["install"], "install"),
        ("pricing", nav["pricing"], "pricing"),
    ]
    items = []
    for target, label, key in links:
        active = ' class="is-active"' if key == page else ""
        items.append(f"<li><a{active} {_href_attr('@' + target, lang)}>{label}</a></li>")
    docs = config.docs_url(lang, "quickstart")
    items.append(f'<li><a href="{esc(docs)}" target="_blank" rel="noopener">{nav["docs"]}</a></li>')
    return "".join(items)


def _lang_switch(page: str, lang: str) -> str:
    items = []
    for code, native, short in config.LANGS:
        active = " is-active" if code == lang else ""
        current = ' aria-current="true"' if code == lang else ""
        items.append(
            f'<a class="lang{active}" href="{esc(page_path(page, code))}" hreflang="{code}"'
            f' lang="{code}" title="{esc(native)}"{current}>{esc(short)}</a>'
        )
    return f'<div class="langs" role="group" aria-label="Language">{"".join(items)}</div>'


def _footer(lang: str, footer: dict[str, Any]) -> str:
    groups = []
    for group in footer["groups"]:
        links = "".join(f"<li><a {_href_attr(link['href'], lang)}>{link['label']}</a></li>" for link in group["links"])
        groups.append(f'<div class="foot-col"><h2 class="foot-title">{group["title"]}</h2><ul>{links}</ul></div>')
    return (
        '<footer class="site-foot"><div class="wrap foot-grid">'
        f'<div class="foot-brand">{logo(lang, size="small")}'
        f'<p class="foot-blurb">{footer["blurb"]}</p></div>'
        f"{''.join(groups)}</div>"
        f'<div class="wrap foot-bottom"><p>{footer["legal"]}</p><p>{footer["built"]}</p></div></footer>'
    )


def logo(lang: str, size: str = "normal") -> str:
    """Brand mark + wordmark. One markup for the header and the footer."""
    dimension = 40 if size == "normal" else 32
    return (
        f'<a class="brand brand-{size}" href="{esc(page_path("index", lang))}">'
        f'<img class="brand-mark" src="/icons/mark-14-radar-terminal-compact.png" width="{dimension}" '
        f'height="{dimension}" alt="" />'
        f'<span class="brand-word">Pentool</span></a>'
    )


def layout(
    *,
    page: str,
    lang: str,
    content: dict[str, Any],
    nav: dict[str, str],
    footer: dict[str, Any],
    body: str,
    after_body: str = "",
) -> str:
    """The one page shell used by every page of the site."""
    title = content["title"]
    description = content["description"]
    canonical = config.DOMAIN + page_path(page, lang)
    alternates = "".join(
        f'<link rel="alternate" hreflang="{code}" href="{esc(config.DOMAIN + page_path(page, code))}" />'
        for code, _native, _short in config.LANGS
    )
    og_image = f"{config.DOMAIN}/icons/mark-14-radar-terminal-compact.png"
    extra_head = _HEAD_EXTRA.get(page, "")
    return f"""<!DOCTYPE html>
<html lang="{esc(lang)}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}" />
<link rel="canonical" href="{esc(canonical)}" />
{alternates}
<meta property="og:type" content="website" />
<meta property="og:site_name" content="{esc(config.BRAND)}" />
<meta property="og:title" content="{esc(title)}" />
<meta property="og:description" content="{esc(description)}" />
<meta property="og:url" content="{esc(canonical)}" />
<meta property="og:image" content="{esc(og_image)}" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="theme-color" content="#0a0e14" />
<link rel="icon" href="/icons/mark-14-radar-terminal-compact.png" />
<link rel="apple-touch-icon" href="/icons/mark-14-radar-terminal-compact.png" />{extra_head}
<link rel="stylesheet" href="/assets/site.css" />
</head>
<body data-page="{esc(page)}" data-lang="{esc(lang)}" data-checkout="{esc(config.CHECKOUT_API)}"
 data-price-first="{config.PRICE_FIRST_SLOT}" data-price-extra="{config.PRICE_EXTRA_SLOT}"
 data-msg-slots="{esc(UI_TEXT[lang]["buy_slots"])}" data-msg-email="{esc(UI_TEXT[lang]["err_email"])}"
 data-msg-fail="{esc(UI_TEXT[lang]["err_checkout"])}" data-msg-waiting="{esc(UI_TEXT[lang]["buy_waiting"])}">
<a class="skip" href="#main">{esc(UI_TEXT[lang]["skip"])}</a>
<header class="site-head"><div class="wrap head-row">
{logo(lang)}
<nav class="nav-links" aria-label="{esc(UI_TEXT[lang]["menu"])}"><ul>{_nav(page, lang, nav)}</ul></nav>
{_lang_switch(page, lang)}
<a class="btn btn-quiet nav-cta" {_href_attr("@link:github", lang)}>GitHub</a>
</div></header>
<main id="main">
{body}
</main>
{_footer(lang, footer)}
{after_body}
<script src="/assets/site.js" defer></script>
</body>
</html>
"""


def render_page(
    *,
    page: str,
    lang: str,
    pages: dict[str, dict[str, Any]],
    nav: dict[str, str],
    footer: dict[str, Any],
) -> str:
    """Render one page of one language into a full HTML document."""
    content = pages[page]
    if page == "index":
        body = (
            _render_hero(content["hero"], lang)
            + "\n"
            + "\n".join(render_section(section, lang) for section in content["sections"])
        )
    else:
        intro = _render_intro(content["intro"], lang) if content.get("intro") else ""
        body = intro + "\n" + "\n".join(render_section(section, lang) for section in content["sections"])
    return layout(
        page=page,
        lang=lang,
        content=content,
        nav=nav,
        footer=footer,
        body=body,
        after_body=build_modal(lang) if page == "pricing" else "",
    )


def _render_intro(intro: dict[str, Any], lang: str) -> str:
    """Page header of a non-home page: h1, lead, optional buttons and a note."""
    lead = f'<p class="page-lead">{intro["lead"]}</p>' if intro.get("lead") else ""
    buttons = render_buttons(intro["buttons"], lang, center=False) if intro.get("buttons") else ""
    note = f'<p class="page-note">{intro["note"]}</p>' if intro.get("note") else ""
    eyebrow = f'<p class="eyebrow">{intro["eyebrow"]}</p>' if intro.get("eyebrow") else ""
    return (
        f'<section class="page-intro"><div class="wrap">{eyebrow}'
        f'<h1 class="page-title">{intro["title"]}</h1>{lead}{buttons}{note}</div></section>'
    )


def _render_hero(hero: dict[str, Any], lang: str) -> str:
    meta = "".join(f"<li>{item}</li>" for item in hero.get("meta", []))
    meta_html = f'<ul class="hero-meta">{meta}</ul>' if meta else ""
    kicker = f'<p class="eyebrow">{hero["kicker"]}</p>' if hero.get("kicker") else ""
    return (
        '<section class="hero"><div class="wrap">'
        f'{kicker}<h1 class="hero-title">{hero["h1"]}</h1>'
        f'<p class="hero-lead">{hero["lead"]}</p>'
        f"{render_buttons(hero['buttons'], lang, center=True)}{meta_html}"
        "</div></section>"
    )


def set_ui_text(ui: dict[str, dict[str, str]]) -> None:
    """Install per-language UI strings (called once by the build)."""
    UI_TEXT.clear()
    UI_TEXT.update(ui)


def build_modal(lang: str) -> str:
    """Checkout dialog for one language (filled by ``set_ui_text``)."""
    text = UI_TEXT[lang]
    return f"""<dialog class="modal" id="buy-modal" aria-labelledby="buy-title">
<form method="dialog" class="modal-close-form"><button class="modal-close" aria-label="{esc(text["close"])}">×</button></form>
<h2 class="modal-title" id="buy-title">{esc(text["buy_title"])}</h2>
<p class="modal-text">{text["buy_text"]}</p>
<p class="modal-summary"><span id="buy-slots">{esc(text["buy_slots"].replace("{n}", str(config.SLOT_CHOICES[0])))}</span>
· <span id="buy-price">${config.PRICE_FIRST_SLOT}</span></p>
<label class="field"><span class="field-label">{esc(text["buy_email"])}</span>
<input type="email" id="buy-email" name="email" required placeholder="you@example.com" autocomplete="email" /></label>
<p class="modal-hint" id="buy-hint">{text["buy_hint"]}</p>
<div class="modal-actions">
<button type="button" class="btn btn-primary" id="buy-confirm">{esc(text["buy_confirm"])}</button>
<button type="button" class="btn btn-ghost" id="buy-cancel">{esc(text["close"])}</button>
</div>
</dialog>"""


def strip_tags(value: str) -> str:
    """Plain text of an inline-HTML string (for meta descriptions and tests)."""
    return re.sub(r"<[^>]+>", "", value)
