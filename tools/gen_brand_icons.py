"""Ten different Pentool marks — different geometry and idea, not recolours.

Each function draws its own concept; the shared part is only the palette.
Output: docs/icons/ — PNG 512 + SVG for every concept.

01 hex-caret     — hexagon cell + terminal caret + AI core (network terminal)
02 graph-p       — letter P built from graph nodes (data structure)
03 terminal-window — terminal window frame, prompt, block cursor, AI dot
04 ai-eye        — an eye whose iris is a targeting ring (AI that watches)
05 circuit-p     — letter P routed as PCB traces with pads
06 crosshair     — diamond reticle: four ticks, node corners, core dot
07 code-brackets — [ > ] frame with the core between the brackets
08 glitch-shield — armour shield cut by glitch slashes, prompt inside
09 neural-spark  — five connected nodes as a spark (neural network)
10 radar-sweep   — radar rings with a sweep wedge and a target blip
"""

from __future__ import annotations

import math
from pathlib import Path

import cairosvg

OUT = Path("/mnt/d/PROJECTS/pentool/docs/icons")
OUT.mkdir(parents=True, exist_ok=True)

INK = "#080b10"
PLATE = "#101722"
CYAN = "#22d3ee"
BLUE = "#3b82f6"
GREEN = "#39ff9e"
WHITE = "#f2f7fb"

DEFS = (
    "<defs>"
    f'<linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    f'<stop offset="0" stop-color="{CYAN}"/><stop offset="1" stop-color="{BLUE}"/></linearGradient>'
    f'<radialGradient id="halo"><stop offset="0" stop-color="{CYAN}" stop-opacity="0.85"/>'
    f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient>'
    "</defs>"
)


def wrap(body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
        + DEFS
        + body
        + "</svg>"
    )


def hex_points(cx: float, cy: float, radius: float, flat_top: bool = False) -> str:
    start = 0 if flat_top else -90
    return " ".join(
        f"{cx + radius * math.cos(math.radians(start + index * 60)):.1f},"
        f"{cy + radius * math.sin(math.radians(start + index * 60)):.1f}"
        for index in range(6)
    )


def plate_circle(colour: str = PLATE, radius: int = 250) -> str:
    return f'<circle cx="256" cy="256" r="{radius}" fill="{colour}"/>'


def plate_hex(colour: str = PLATE) -> str:
    return f'<polygon points="{hex_points(256, 256, 250)}" fill="{colour}"/>'


# ── 01: hexagon cell + terminal caret + AI core ─────────────────────────────
def c01_hex_caret() -> str:
    nodes = "".join(
        f'<line x1="{256 + 238 * math.cos(math.radians(-90 + i * 60)):.1f}" '
        f'y1="{256 + 238 * math.sin(math.radians(-90 + i * 60)):.1f}" '
        f'x2="{256 + 150 * math.cos(math.radians(-90 + i * 60)):.1f}" '
        f'y2="{256 + 150 * math.sin(math.radians(-90 + i * 60)):.1f}" '
        f'stroke="{CYAN}" stroke-width="5" opacity="0.3"/>'
        f'<circle cx="{256 + 238 * math.cos(math.radians(-90 + i * 60)):.1f}" '
        f'cy="{256 + 238 * math.sin(math.radians(-90 + i * 60)):.1f}" r="12" fill="{CYAN}" opacity="0.6"/>'
        for i in range(6)
    )
    return wrap(
        plate_hex()
        + f'<polygon points="{hex_points(256, 256, 236)}" fill="none" stroke="{CYAN}" stroke-width="14" stroke-linejoin="round"/>'
        + nodes
        + f'<path d="M192 190 L268 256 L192 322" fill="none" stroke="{WHITE}" stroke-width="34" stroke-linecap="round"/>'
        + '<circle cx="324" cy="256" r="60" fill="url(#halo)"/>'
        + f'<circle cx="324" cy="256" r="25" fill="{CYAN}"/>'
    )


# ── 02: letter P from graph nodes ───────────────────────────────────────────
def c02_graph_p() -> str:
    joints = [(176, 148), (176, 364), (268, 148), (268, 320), (356, 234)]
    edges = [(176, 148, 268, 148), (176, 148, 176, 364), (268, 148, 268, 320), (268, 320, 176, 320)]
    lines = "".join(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{CYAN}" stroke-width="18" stroke-linecap="round" opacity="0.85"/>'
        for x1, y1, x2, y2 in edges
    )
    arc = f'<path d="M268 148 A86 86 0 0 1 268 320" fill="none" stroke="{WHITE}" stroke-width="18" stroke-linecap="round"/>'
    dots = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{18 if (cx, cy) != (356, 234) else 22}" fill="{CYAN if (cx, cy) == (356, 234) else WHITE}"/>'
        for cx, cy in joints
    )
    return wrap(
        plate_circle()
        + f'<circle cx="256" cy="256" r="238" fill="none" stroke="{CYAN}" stroke-width="6" opacity="0.35"/>'
        + lines
        + arc
        + '<circle cx="356" cy="234" r="52" fill="url(#halo)"/>'
        + dots
    )


# ── 03: terminal window ─────────────────────────────────────────────────────
def c03_terminal_window() -> str:
    return wrap(
        plate_circle()
        + f'<rect x="88" y="132" width="336" height="248" rx="26" fill="{INK}" stroke="{CYAN}" stroke-width="10"/>'
        + f'<line x1="88" y1="186" x2="424" y2="186" stroke="{CYAN}" stroke-width="8" opacity="0.7"/>'
        + "".join(
            f'<circle cx="{120 + i * 30}" cy="159" r="8" fill="{c}" opacity="0.9"/>'
            for i, c in enumerate((CYAN, BLUE, GREEN))
        )
        + f'<path d="M132 232 L188 274 L132 316" fill="none" stroke="{GREEN}" stroke-width="20" stroke-linecap="round" stroke-linejoin="round"/>'
        + f'<rect x="212" y="296" width="96" height="26" rx="6" fill="{CYAN}" opacity="0.85"/>'
        + f'<path d="M212 232 L300 232" stroke="{WHITE}" stroke-width="16" stroke-linecap="round" opacity="0.8"/>'
        + '<circle cx="356" cy="252" r="44" fill="url(#halo)"/>'
        + f'<circle cx="356" cy="252" r="17" fill="{CYAN}"/>'
    )


# ── 04: AI eye with targeting iris ──────────────────────────────────────────
def c04_ai_eye() -> str:
    return wrap(
        plate_circle()
        + f'<path d="M76 256 Q256 108 436 256 Q256 404 76 256 Z" fill="none" stroke="{CYAN}" stroke-width="16" stroke-linejoin="round"/>'
        + f'<circle cx="256" cy="256" r="86" fill="none" stroke="{WHITE}" stroke-width="12" opacity="0.9"/>'
        + f'<circle cx="256" cy="256" r="54" fill="none" stroke="{CYAN}" stroke-width="8" opacity="0.75"/>'
        + '<circle cx="256" cy="256" r="70" fill="url(#halo)"/>'
        + f'<circle cx="256" cy="256" r="24" fill="{CYAN}"/>'
        + "".join(
            f'<line x1="{256 + 96 * math.cos(math.radians(a)):.1f}" y1="{256 + 96 * math.sin(math.radians(a)):.1f}" '
            f'x2="{256 + 128 * math.cos(math.radians(a)):.1f}" y2="{256 + 128 * math.sin(math.radians(a)):.1f}" '
            f'stroke="{CYAN}" stroke-width="8" opacity="0.8"/>'
            for a in (0, 90, 180, 270)
        )
    )


# ── 05: letter P as PCB traces ──────────────────────────────────────────────
def c05_circuit_p() -> str:
    pads = [(150, 128), (150, 384), (150, 256), (262, 128), (262, 256), (330, 192)]
    trace = (
        f'<path d="M150 384 L150 128 L232 128 Q300 128 300 192 Q300 256 232 256 L150 256" '
        f'fill="none" stroke="{CYAN}" stroke-width="16" stroke-linecap="square" stroke-linejoin="miter"/>'
    )
    pad_marks = "".join(
        f'<rect x="{cx - 20}" y="{cy - 20}" width="40" height="40" rx="8" fill="{INK}" stroke="{CYAN}" stroke-width="9"/>'
        for cx, cy in pads
    )
    return wrap(plate_circle() + trace + pad_marks)


# ── 06: diamond reticle ─────────────────────────────────────────────────────
def c06_crosshair() -> str:
    diamond = "256,60 452,256 256,452 60,256"
    return wrap(
        plate_circle()
        + f'<polygon points="{diamond}" fill="none" stroke="{CYAN}" stroke-width="14" stroke-linejoin="round" opacity="0.9"/>'
        + f'<polygon points="256,120 392,256 256,392 120,256" fill="none" stroke="{WHITE}" stroke-width="7" opacity="0.5"/>'
        + "".join(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{WHITE}" stroke-width="10" opacity="0.85"/>'
            for x1, y1, x2, y2 in (
                (256, 130, 256, 214),
                (256, 298, 256, 382),
                (130, 256, 214, 256),
                (298, 256, 382, 256),
            )
        )
        + '<circle cx="256" cy="256" r="64" fill="url(#halo)"/>'
        + f'<circle cx="256" cy="256" r="26" fill="{CYAN}"/>'
        + f'<circle cx="256" cy="256" r="52" fill="none" stroke="{CYAN}" stroke-width="6" opacity="0.6"/>'
    )


# ── 07: code brackets with the core between them ────────────────────────────
def c07_code_brackets() -> str:
    return wrap(
        plate_circle()
        + f'<path d="M196 112 L108 256 L196 400" fill="none" stroke="{WHITE}" stroke-width="26" stroke-linecap="round" stroke-linejoin="round"/>'
        + f'<path d="M316 112 L404 256 L316 400" fill="none" stroke="{WHITE}" stroke-width="26" stroke-linecap="round" stroke-linejoin="round"/>'
        + '<circle cx="256" cy="256" r="78" fill="url(#halo)"/>'
        + f'<circle cx="256" cy="256" r="34" fill="{CYAN}"/>'
        + f'<circle cx="256" cy="256" r="58" fill="none" stroke="{CYAN}" stroke-width="7" opacity="0.7"/>'
        + f'<line x1="256" y1="150" x2="256" y2="190" stroke="{CYAN}" stroke-width="8" opacity="0.7"/>'
        + f'<line x1="256" y1="322" x2="256" y2="362" stroke="{CYAN}" stroke-width="8" opacity="0.7"/>'
    )


# ── 08: glitch shield ───────────────────────────────────────────────────────
def c08_glitch_shield() -> str:
    shield = "256,64 424,128 424,272 Q424,392 256,448 Q88,392 88,272 L88,128 Z"
    return wrap(
        plate_circle()
        + f'<path d="{shield}" fill="none" stroke="{CYAN}" stroke-width="14" stroke-linejoin="round"/>'
        + "".join(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{INK}"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{GREEN}" opacity="0.5"/>'
            for x, y, w, h in ((96, 196, 320, 14), (96, 246, 240, 10), (200, 300, 216, 12), (96, 346, 160, 8))
        )
        + f'<path d="M196 208 L262 256 L196 304" fill="none" stroke="{WHITE}" stroke-width="26" stroke-linecap="round" stroke-linejoin="round"/>'
        + '<circle cx="318" cy="256" r="48" fill="url(#halo)"/>'
        + f'<circle cx="318" cy="256" r="20" fill="{CYAN}"/>'
    )


# ── 09: neural spark — connected nodes ──────────────────────────────────────
def c09_neural_spark() -> str:
    pts = [(256, 92), (146, 200), (366, 200), (196, 356), (316, 356), (256, 256)]
    edges = [
        (0, 1),
        (0, 2),
        (1, 3),
        (2, 4),
        (3, 5),
        (4, 5),
        (1, 2),
        (3, 4),
        (0, 5),
    ]
    return wrap(
        plate_circle()
        + "".join(
            f'<line x1="{pts[a][0]}" y1="{pts[a][1]}" x2="{pts[b][0]}" y2="{pts[b][1]}" '
            f'stroke="{CYAN}" stroke-width="{9 if (a, b) in ((0, 5), (1, 2), (3, 4)) else 6}" '
            f'opacity="{0.85 if (a, b) in ((0, 5), (1, 2), (3, 4)) else 0.45}"/>'
            for a, b in edges
        )
        + '<circle cx="256" cy="256" r="74" fill="url(#halo)"/>'
        + "".join(
            f'<circle cx="{cx}" cy="{cy}" r="{22 if (cx, cy) == (256, 256) else 15}" '
            f'fill="{CYAN if (cx, cy) == (256, 256) else WHITE}"/>'
            for cx, cy in pts
        )
    )


# ── 10: radar sweep ─────────────────────────────────────────────────────────
def c10_radar_sweep() -> str:
    rings = "".join(
        f'<circle cx="256" cy="256" r="{r}" fill="none" stroke="{CYAN}" stroke-width="6" opacity="{0.25 + i * 0.15:.2f}"/>'
        for i, r in enumerate((210, 150, 90))
    )
    sweep = f'<path d="M256 256 L256 46 A210 210 0 0 1 404 100 Z" fill="{CYAN}" opacity="0.22"/>'
    blend = f'<line x1="256" y1="256" x2="404" y2="100" stroke="{CYAN}" stroke-width="8" opacity="0.8"/>'
    blips = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{CYAN}" opacity="{o}"/>'
        for cx, cy, r, o in ((330, 168, 14, 0.95), (188, 320, 10, 0.8), (300, 360, 8, 0.6), (196, 176, 7, 0.5))
    )
    cross = (
        f'<line x1="256" y1="46" x2="256" y2="466" stroke="{CYAN}" stroke-width="4" opacity="0.25"/>'
        f'<line x1="46" y1="256" x2="466" y2="256" stroke="{CYAN}" stroke-width="4" opacity="0.25"/>'
    )
    return wrap(
        plate_circle()
        + rings
        + cross
        + sweep
        + blend
        + blips
        + f'<circle cx="256" cy="256" r="16" fill="{WHITE}"/>'
        + '<circle cx="256" cy="256" r="46" fill="url(#halo)"/>'
    )


# ── 11: terminal window with a radar inside and a neural core ───────────────
def c11_ai_terminal_radar() -> str:
    """The console *is* the radar: window chrome on top, rings and a sweep below,
    a neural core in the middle and the prompt on the bottom line."""
    cx, cy = 256, 286
    rings = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{CYAN}" stroke-width="6" opacity="{0.22 + i * 0.16:.2f}"/>'
        for i, r in enumerate((96, 66, 36))
    )
    sweep = (
        f'<path d="M{cx} {cy} L{cx} {cy - 96} A96 96 0 0 1 {cx + 83} {cy - 48} Z" fill="{CYAN}" opacity="0.2"/>'
        f'<line x1="{cx}" y1="{cy}" x2="{cx + 83}" y2="{cy - 48}" stroke="{CYAN}" stroke-width="7" opacity="0.85"/>'
    )
    blips = "".join(
        f'<circle cx="{bx}" cy="{by}" r="{r}" fill="{CYAN}" opacity="{o}"/>'
        for bx, by, r, o in ((cx + 52, cy - 62, 10, 0.95), (cx - 58, cy + 34, 8, 0.7), (cx + 22, cy + 56, 6, 0.5))
    )
    # Neural core: four nodes wired to the centre.
    neural = "".join(
        f'<line x1="{cx}" y1="{cy}" x2="{nx}" y2="{ny}" stroke="{CYAN}" stroke-width="4" opacity="0.5"/>'
        f'<circle cx="{nx}" cy="{ny}" r="9" fill="{WHITE}" opacity="0.85"/>'
        for nx, ny in ((cx - 46, cy - 30), (cx + 40, cy - 34), (cx - 36, cy + 44), (cx + 46, cy + 38))
    )
    prompt = (
        f'<path d="M140 372 L172 390 L140 408" fill="none" stroke="{GREEN}" stroke-width="12" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<rect x="188" y="386" width="46" height="14" rx="3" fill="{CYAN}" opacity="0.9"/>'
        f'<path d="M250 393 L316 393" stroke="{WHITE}" stroke-width="9" stroke-linecap="round" opacity="0.55"/>'
    )
    return wrap(
        plate_circle()
        + f'<rect x="70" y="112" width="372" height="300" rx="26" fill="{INK}" stroke="{CYAN}" stroke-width="9"/>'
        + f'<line x1="70" y1="160" x2="442" y2="160" stroke="{CYAN}" stroke-width="7" opacity="0.6"/>'
        + "".join(
            f'<circle cx="{102 + i * 28}" cy="136" r="7" fill="{c}" opacity="0.9"/>'
            for i, c in enumerate((CYAN, BLUE, GREEN))
        )
        + rings
        + sweep
        + blips
        + neural
        + '<circle cx="256" cy="286" r="54" fill="url(#halo)"/>'
        + f'<circle cx="{cx}" cy="{cy}" r="15" fill="{CYAN}"/>'
        + prompt
    )


# ── 12: radar whose centre *is* the prompt ──────────────────────────────────
def c12_radar_caret() -> str:
    """Rings and a sweep, but the beam leaves the tip of a big caret — the scan is
    started by the prompt. Nodes of the network sit on the outer ring."""
    cx, cy = 256, 256
    rings = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{CYAN}" stroke-width="{7 if r > 120 else 5}" '
        f'opacity="{0.2 + i * 0.14:.2f}"/>'
        for i, r in enumerate((212, 152, 96, 44))
    )
    cross = (
        f'<line x1="{cx}" y1="30" x2="{cx}" y2="482" stroke="{CYAN}" stroke-width="3" opacity="0.18"/>'
        f'<line x1="30" y1="{cy}" x2="482" y2="{cy}" stroke="{CYAN}" stroke-width="3" opacity="0.18"/>'
    )
    sweep = (
        f'<path d="M{cx} {cy} L{cx} {cy - 212} A212 212 0 0 0 {cx - 150} {cy - 150} Z" fill="{CYAN}" opacity="0.16"/>'
    )
    nodes = "".join(
        f'<line x1="{cx}" y1="{cy}" x2="{nx}" y2="{ny}" stroke="{CYAN}" stroke-width="3" opacity="0.35"/>'
        f'<circle cx="{nx}" cy="{ny}" r="10" fill="{CYAN}" opacity="0.8"/>'
        for nx, ny in (
            (cx + 152, cy),
            (cx - 152, cy),
            (cx, cy - 152),
            (cx + 107, cy + 107),
            (cx - 107, cy + 107),
        )
    )
    caret = (
        f'<path d="M214 204 L286 256 L214 308" fill="none" stroke="{WHITE}" stroke-width="30" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<rect x="300" y="244" width="34" height="24" rx="4" fill="{CYAN}"/>'
    )
    blips = f'<circle cx="{cx + 128}" cy="{cy - 96}" r="9" fill="{WHITE}" opacity="0.9"/>'
    return wrap(
        plate_circle()
        + rings
        + cross
        + sweep
        + nodes
        + '<circle cx="256" cy="256" r="86" fill="url(#halo)"/>'
        + caret
        + blips
    )


# ── 13: console line wrapped by radar arcs and a neural branch ──────────────
def c13_neural_console() -> str:
    """A console line inside a radar ring: prompt + block cursor on the left, a
    three-node neural branch on the right, signal arcs above and below."""
    arcs = (
        f'<path d="M96 256 A160 160 0 0 1 416 256" fill="none" stroke="{CYAN}" stroke-width="7" opacity="0.55"/>'
        f'<path d="M132 256 A124 124 0 0 1 380 256" fill="none" stroke="{CYAN}" stroke-width="5" opacity="0.35"/>'
        f'<path d="M96 256 A160 160 0 0 0 416 256" fill="none" stroke="{CYAN}" stroke-width="7" opacity="0.35"/>'
    )
    prompt = (
        f'<path d="M120 226 L164 256 L120 286" fill="none" stroke="{GREEN}" stroke-width="16" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<rect x="182" y="246" width="52" height="20" rx="4" fill="{CYAN}" opacity="0.95"/>'
    )
    neural = (
        f'<line x1="262" y1="256" x2="322" y2="214" stroke="{CYAN}" stroke-width="5" opacity="0.7"/>'
        f'<line x1="262" y1="256" x2="332" y2="256" stroke="{CYAN}" stroke-width="5" opacity="0.7"/>'
        f'<line x1="262" y1="256" x2="322" y2="298" stroke="{CYAN}" stroke-width="5" opacity="0.7"/>'
        f'<circle cx="322" cy="214" r="13" fill="{WHITE}" opacity="0.9"/>'
        f'<circle cx="332" cy="256" r="13" fill="{WHITE}" opacity="0.9"/>'
        f'<circle cx="322" cy="298" r="13" fill="{WHITE}" opacity="0.9"/>'
        + f'<circle cx="262" cy="256" r="11" fill="{CYAN}"/>'
    )
    blips = (
        f'<circle cx="150" cy="140" r="8" fill="{CYAN}" opacity="0.75"/>'
        f'<circle cx="372" cy="372" r="7" fill="{CYAN}" opacity="0.6"/>'
        f'<circle cx="196" cy="392" r="5" fill="{WHITE}" opacity="0.5"/>'
    )
    return wrap(
        plate_circle()
        + f'<circle cx="256" cy="256" r="230" fill="none" stroke="{CYAN}" stroke-width="6" opacity="0.25"/>'
        + arcs
        + blips
        + '<circle cx="256" cy="256" r="96" fill="url(#halo)"/>'
        + prompt
        + neural
    )


# ── 14: radar dome above, terminal plate below, caret branching into neurons ─
def c14_radar_terminal(compact: bool = False) -> str:
    """The composition: top half is the radar (dome arcs, sweep, blips), bottom is a
    terminal plate where the prompt caret splits into a neural tree.

    ``compact`` keeps the same idea with fewer, thicker elements — the form has to
    stay readable at 128 px and below.
    """
    cx, radar_y = 256, 244
    radii = (196, 148) if compact else (196, 148, 100)
    dome = "".join(
        f'<path d="M{cx - r} {radar_y} A{r} {r} 0 0 1 {cx + r} {radar_y}" fill="none" '
        f'stroke="{CYAN}" stroke-width="{8 if compact else 6}" opacity="{0.28 + i * 0.18:.2f}"/>'
        for i, r in enumerate(radii)
    )
    cross = (
        f'<line x1="{cx}" y1="{radar_y - 196}" x2="{cx}" y2="{radar_y - 96}" stroke="{CYAN}" '
        f'stroke-width="4" opacity="0.22"/>'
        f'<line x1="{cx - 196}" y1="{radar_y}" x2="{cx + 196}" y2="{radar_y}" stroke="{CYAN}" '
        f'stroke-width="4" opacity="0.16"/>'
    )
    sweep = (
        f'<path d="M{cx} {radar_y} L{cx + 128} {radar_y - 148} A196 196 0 0 1 {cx + 196} {radar_y} Z" '
        f'fill="{CYAN}" opacity="0.14"/>'
        f'<line x1="{cx}" y1="{radar_y}" x2="{cx + 128}" y2="{radar_y - 148}" stroke="{CYAN}" '
        f'stroke-width="6" opacity="0.75"/>'
    )
    blips = "".join(
        f'<circle cx="{bx}" cy="{by}" r="{r}" fill="{CYAN}" opacity="{o}"/>'
        for bx, by, r, o in (
            (cx + 132, radar_y - 104, 10, 0.95),
            (cx - 150, radar_y - 44, 8, 0.7),
            (cx + 56, radar_y - 168, 6, 0.55),
        )
    )
    # The radar's core sits exactly above the prompt tip: one axis, one story.
    core = (
        f'<circle cx="{cx}" cy="{radar_y}" r="40" fill="url(#halo)"/>'
        f'<circle cx="{cx}" cy="{radar_y}" r="12" fill="{CYAN}"/>'
        f'<line x1="{cx}" y1="{radar_y + 12}" x2="{cx}" y2="318" stroke="{CYAN}" stroke-width="5" opacity="0.55"/>'
    )

    # Terminal plate: dark, framed, with the three status dots of a console.
    plate = (
        f'<rect x="68" y="318" width="376" height="150" rx="22" fill="{INK}" stroke="{CYAN}" stroke-width="8" opacity="0.97"/>'
        f'<line x1="68" y1="352" x2="444" y2="352" stroke="{CYAN}" stroke-width="5" opacity="0.45"/>'
        + "".join(
            f'<circle cx="{96 + i * 24}" cy="335" r="6" fill="{c}" opacity="0.9"/>'
            for i, c in enumerate((CYAN, BLUE, GREEN))
        )
    )

    # Prompt caret, splitting into the neural tree.
    caret_tip = (176, 412)
    caret = (
        f'<path d="M126 380 L176 412 L126 444" fill="none" stroke="{GREEN}" '
        f'stroke-width="{20 if compact else 18}" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    primary = [(300, 372), (330, 412), (300, 452)]
    secondary = [(362, 352), (382, 412), (362, 470)]
    tree_lines = [
        f'<line x1="{caret_tip[0]}" y1="{caret_tip[1]}" x2="{nx}" y2="{ny}" stroke="{CYAN}" '
        f'stroke-width="{5 if compact else 4}" opacity="0.8"/>'
        for nx, ny in primary
    ]
    tree_lines += (
        [
            f'<line x1="{primary[index][0]}" y1="{primary[index][1]}" x2="{sx}" y2="{sy}" stroke="{CYAN}" '
            f'stroke-width="3" opacity="0.55"/>'
            for index, (sx, sy) in enumerate(secondary)
        ]
        if not compact
        else []
    )
    nodes = "".join(f'<circle cx="{nx}" cy="{ny}" r="10" fill="{WHITE}"/>' for nx, ny in primary)
    nodes += (
        ""
        if compact
        else "".join(f'<circle cx="{sx}" cy="{sy}" r="7" fill="{CYAN}" opacity="0.9"/>' for sx, sy in secondary)
    )

    return wrap(plate_circle() + dome + cross + sweep + blips + core + plate + "".join(tree_lines) + caret + nodes)


CONCEPTS = {
    "01-hex-caret": c01_hex_caret,
    "02-graph-p": c02_graph_p,
    "03-terminal-window": c03_terminal_window,
    "04-ai-eye": c04_ai_eye,
    "05-circuit-p": c05_circuit_p,
    "06-crosshair": c06_crosshair,
    "07-code-brackets": c07_code_brackets,
    "08-glitch-shield": c08_glitch_shield,
    "09-neural-spark": c09_neural_spark,
    "10-radar-sweep": c10_radar_sweep,
    "11-ai-terminal-radar": c11_ai_terminal_radar,
    "12-radar-caret": c12_radar_caret,
    "13-neural-console": c13_neural_console,
    "14-radar-terminal": c14_radar_terminal,
    "14-radar-terminal-compact": lambda: c14_radar_terminal(compact=True),
}

for name, builder in CONCEPTS.items():
    svg = builder()
    (OUT / f"mark-{name}.svg").write_text(svg, encoding="utf-8")
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"), write_to=str(OUT / f"mark-{name}.png"), output_width=512, output_height=512
    )
    size = (OUT / f"mark-{name}.png").stat().st_size
    print(f"  mark-{name}.png  {size:6d} bytes")
