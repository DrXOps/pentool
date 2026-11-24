"""Build the static site into ``docs/``.

Usage:

    python tools/site/build.py            # write the pages
    python tools/site/build.py --check    # verify content parity only

The generated files are committed: GitHub Pages serves ``docs/`` as is, and the
deploy workflow in ``.github/workflows/pages.yml`` only uploads that directory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python tools/site/build.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.site import config, render  # noqa: E402
from tools.site.content import MODULES, check_parity  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT = ROOT / config.OUTPUT_DIR


def redirect_html(target: str, title: str, label: str, lang: str = "en") -> str:
    """A tiny page that moves the visitor to a new address (kept for old links)."""
    url = config.DOMAIN + target
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{render.esc(title)}</title>
<link rel="canonical" href="{render.esc(url)}" />
<meta http-equiv="refresh" content="0; url={render.esc(target)}" />
<meta name="robots" content="noindex" />
<style>body{{background:#0a0e14;color:#e8eef6;font:16px/1.6 system-ui,sans-serif;margin:0;
display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:2rem}}
a{{color:#22d3ee}}</style>
</head>
<body>
<main>
<p>{render.esc(title)}</p>
<p><a href="{render.esc(target)}">{render.esc(label)}</a></p>
</main>
</body>
</html>
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" on purpose: the repository stores LF, and Windows would otherwise
    # turn every regenerated page into a "modified" file (CRLF) after each build.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    try:
        shown = path.relative_to(ROOT).as_posix()
    except ValueError:
        # Tests build into a temporary directory: print the path that was given.
        shown = path.as_posix()
    print(f"  {shown}")


def build() -> int:
    """Render every page of every language plus the legacy redirects."""
    problems = check_parity()
    if problems:
        print("build: content parity failed — the pages would differ between languages:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    ui_text = {code: module.UI for code, module in MODULES.items()}
    render.set_ui_text(ui_text)

    for code, module in MODULES.items():
        prefix = config.page_prefix(code)
        for page in config.PAGES:
            html = render.render_page(
                page=page,
                lang=code,
                pages=module.PAGES,
                nav=module.NAV,
                footer=module.FOOTER,
            )
            _write(OUTPUT / config.PAGES[page].format(prefix=prefix), html)

    for stale in config.REMOVE_STALE:
        target = OUTPUT / stale
        if target.is_file():
            target.unlink()
            print(f"  removed {target.relative_to(ROOT).as_posix()}")

    labels = {
        "pricing.ru.html": ("Страница переехала — Pentool PRO", "Перейти к ценам", "ru"),
        "privacy.ru.html": ("Страница переехала — Pentool", "Перейти к политике", "ru"),
        "terms.ru.html": ("Страница переехала — Pentool", "Перейти к соглашению", "ru"),
        "upgrade.html": ("Pentool PRO lives on the pricing page", "Continue to pricing", "en"),
        "pricing/index.html": ("Pentool — pricing", "Continue to pricing", "en"),
    }
    for path, target in config.LEGACY_REDIRECTS.items():
        title, label, lang = labels[path]
        _write(OUTPUT / path, redirect_html(target, title, label, lang))

    print(f"build: {len(MODULES) * len(config.PAGES)} pages + {len(config.LEGACY_REDIRECTS)} redirects")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="only verify that languages have the same structure")
    args = parser.parse_args(argv)
    if args.check:
        problems = check_parity()
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    return build()


if __name__ == "__main__":
    raise SystemExit(main())
