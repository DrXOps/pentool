"""Generate the social icons (Telegram channel, GitHub account) for the project.

Draws the official Simple Icons silhouettes (CC0) in three styles and rasterises
them with cairosvg. Output goes to docs/icons/ — see the README there.

Usage:
    uv pip install cairosvg        # tooling only, not a project dependency
    .venv/bin/python tools/gen_social_icons.py [--check]

The script only writes docs/icons/*.{svg,png}; it never touches other files and
never publishes anything.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "icons"

#: brand → (Simple Icons svg url, brand colour)
BRANDS: dict[str, tuple[str, str]] = {
    "telegram": ("https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/telegram.svg", "#29a1e2"),
    "github": ("https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/github.svg", "#181717"),
}

#: Project palette, same values as the TUI theme.
DARK = "#0f1115"
ACCENT = "#0178d4"

#: Official marks live in a 24×24 box; render them at 300 px inside a 512 px disc.
GLYPH_BOX = 24.0
GLYPH_SIZE = 300.0
CANVAS = 512

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
{body}
</svg>
"""


def fetch_glyph(url: str) -> str:
    """Return the ``d`` attribute of a Simple Icons SVG, caching the download."""
    cache = Path("/tmp") / url.rsplit("/", 1)[-1]
    if not cache.is_file():
        subprocess.run(["curl", "-s", "-o", str(cache), url], check=True)
    match = re.search(r'<path d="([^"]+)"', cache.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit(f"no path found in {url}")
    return match.group(1)


def _glyph(glyph_path: str, colour: str) -> str:
    offset = (CANVAS - GLYPH_SIZE) / 2
    scale = GLYPH_SIZE / GLYPH_BOX
    return (
        f'  <g fill="{colour}" transform="translate({offset:.2f} {offset:.2f}) scale({scale:.4f})">'
        f'<path d="{glyph_path}"/></g>'
    )


def build_svg(glyph_path: str, style: str, brand_colour: str) -> str:
    """One icon as SVG: brand colour disc, project palette, or white on transparent."""
    if style == "brand":
        body = f'  <circle cx="256" cy="256" r="250" fill="{brand_colour}"/>\n' + _glyph(glyph_path, "#ffffff")
    elif style == "pentool":
        body = (
            f'  <circle cx="256" cy="256" r="250" fill="{DARK}"/>\n'
            f'  <circle cx="256" cy="256" r="227" fill="none" stroke="{ACCENT}" stroke-width="16"/>\n'
            + _glyph(glyph_path, ACCENT)
        )
    else:  # mono
        body = _glyph(glyph_path, "#ffffff")
    return SVG.format(body=body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Telegram/GitHub icons.")
    parser.add_argument("--check", action="store_true", help="fail when a rendered PNG looks empty")
    args = parser.parse_args(argv)

    try:
        import cairosvg
    except ImportError:
        print("cairosvg is missing: run `uv pip install cairosvg` first", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    made: list[str] = []
    for brand, (url, brand_colour) in BRANDS.items():
        glyph_path = fetch_glyph(url)
        for style in ("brand", "pentool", "mono"):
            svg_text = build_svg(glyph_path, style, brand_colour)
            (OUT / f"{brand}-{style}.svg").write_text(svg_text, encoding="utf-8")
            made.append(f"{brand}-{style}.svg")
            for size in (512, 128):
                png = OUT / f"{brand}-{style}-{size}.png"
                cairosvg.svg2png(
                    bytestring=svg_text.encode("utf-8"),
                    write_to=str(png),
                    output_width=size,
                    output_height=size,
                )
                made.append(png.name)
                if args.check and png.stat().st_size < 500:
                    print(f"{png.name} looks empty ({png.stat().st_size} bytes)", file=sys.stderr)
                    return 1

    print(f"generated {len(made)} files in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
