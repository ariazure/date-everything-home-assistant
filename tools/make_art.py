#!/usr/bin/env python3
"""Builds the repo artwork from Material Design Icons (assets/mdi/, by the
Pictogrammers community, Apache License 2.0). The icons are used as-is,
placed on colored circles with title text.

The text uses the fonts Crayonest, KG She Persisted and Bugbear DEMO (free
for personal use, not included here). Install them on your computer before
rendering, or the banner falls back to another font.

Writes assets/banner.svg and assets/<character>.svg.
Render the banner to PNG with: python3 tools/svg2png.py assets/banner.svg assets/banner.png 1280 640
Run: python3 tools/make_art.py"""

import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
MDI = os.path.join(ROOT, "mdi")
INK = "#3b2a4d"

# character -> (Material Design Icon, circle color)
CAST = [
    ("hector", "hvac", "#4fc3a1"),
    ("dishy", "dishwasher", "#4aa8e8"),
    ("washford", "washing-machine", "#8c6cf0"),
    ("drysdale", "tumble-dryer", "#f08a5d"),
    ("airyn", "thermostat", "#f2b632"),
    ("lux", "lightbulb-on", "#ef6aa0"),
]


def path(name):
    with open(os.path.join(MDI, name + ".svg"), encoding="utf-8") as f:
        return re.search(r'<path d="([^"]+)"', f.read()).group(1)


def icon(name, x, y, size, color="#fff", opacity=1.0, rot=0):
    """Place a 24x24 Material Design Icon at (x, y), size px wide."""
    s = size / 24
    return (f'<path transform="translate({x:.1f} {y:.1f}) rotate({rot} {size/2:.1f} {size/2:.1f}) scale({s:.3f})" '
            f'd="{path(name)}" fill="{color}" opacity="{opacity}"/>')


def badge(name, cx, cy, r, color):
    """An icon in white on a colored circle with a soft ring."""
    return (f'<circle cx="{cx}" cy="{cy + r*0.08:.1f}" r="{r}" fill="{INK}" opacity=".12"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r - r*0.07:.1f}" fill="none" stroke="#fff" stroke-width="{r*0.05:.1f}" opacity=".55"/>'
            + icon(name, cx - r * 0.58, cy - r * 0.58, r * 1.16))


def svg(w, h, body, defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<defs>{defs}</defs>{body}</svg>\n')


DEFS = (
    '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#ffd3e6"/><stop offset=".55" stop-color="#e6d6ff"/><stop offset="1" stop-color="#cfe8ff"/>'
    '</linearGradient>'
    '<radialGradient id="glow" cx=".5" cy=".42" r=".55">'
    '<stop offset="0" stop-color="#fff" stop-opacity=".85"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>'
    '</radialGradient>'
)


def banner(w=1280, h=640):
    b = [f'<rect width="{w}" height="{h}" fill="url(#bg)"/>', f'<rect width="{w}" height="{h}" fill="url(#glow)"/>']
    # scattered hearts and sparkles (Material Design Icons: heart, star-four-points)
    for fx, fy, s, r in [(0.04, 0.08, 46, -15), (0.92, 0.06, 40, 12), (0.02, 0.8, 38, 10), (0.95, 0.82, 50, -10),
                         (0.31, 0.03, 28, 18), (0.66, 0.02, 32, -16), (0.47, 0.9, 26, 8)]:
        b.append(icon("heart", w * fx, h * fy, s, "#ff5c93", 0.5, r))
    for fx, fy, s in [(0.17, 0.05, 34), (0.8, 0.17, 26), (0.1, 0.46, 24), (0.89, 0.5, 30), (0.4, 0.86, 26), (0.58, 0.88, 32)]:
        b.append(icon("star-four-points", w * fx, h * fy, s, "#fff", 0.9))
    # pink sunglasses, a nod to the game's Dateviators (Material Design Icons: sunglasses)
    b.append(icon("sunglasses", w * 0.035, h * 0.13, h * 0.15, "#ff5c93", 1.0, -14))
    b.append(icon("sunglasses", w * 0.895, h * 0.12, h * 0.15, "#b48cff", 1.0, 12))
    # title
    ty = h * 0.31
    b.append(f'<text x="{w/2}" y="{ty}" text-anchor="middle" font-family="Crayonest" '
             f'font-size="{h*0.175:.0f}" word-spacing="{h*0.04:.0f}" letter-spacing="{h*0.004:.1f}" fill="#fff" stroke="{INK}" stroke-width="{h*0.024:.1f}" stroke-linejoin="round" '
             f'paint-order="stroke">D.A.T.E. your appliances!</text>')
    b.append(f'<text x="{w/2}" y="{ty + h*0.095:.0f}" text-anchor="middle" font-family="KG She Persisted" '
             f'font-size="{h*0.05:.0f}" fill="{INK}">Real voice lines from your dishwasher, laundry, range hood, thermostat and lights</text>')
    # the cast
    r = h * 0.12
    n = len(CAST)
    gap = (w - 2 * r * n) / (n + 1)
    cy = h * 0.66
    bob = [8, -10, 6, -6, 10, -8]
    for i, (_, mdi_name, color) in enumerate(CAST):
        cx = gap + r + i * (2 * r + gap)
        b.append(badge(mdi_name, cx, cy + bob[i], r, color))
    # speech bubbles (Material Design Icons: chat, heart, music-note)
    def bubble(cx, cy, inner, inner_color, flip=False):
        s = h * 0.13
        t = f' transform="scale(-1 1) translate({-2*cx:.1f} 0)"' if flip else ""
        return (f'<g{t}>{icon("chat", cx - s/2, cy - s/2, s, "#fff")}</g>'
                + icon(inner, cx - s * 0.2, cy - s * 0.26, s * 0.4, inner_color))
    first = gap + r
    step = 2 * r + gap
    b.append(bubble(first + r * 0.95, cy - r * 1.35, "heart", "#ff5c93"))
    b.append(bubble(first + 2 * step + r * 0.95, cy - r * 1.4, "music-note", "#7b5cff"))
    b.append(bubble(first + 4 * step - r * 0.95, cy - r * 1.3, "heart", "#ff5c93", flip=True))
    # footer
    b.append(f'<rect x="{w/2 - w*0.22:.0f}" y="{h*0.915:.0f}" width="{w*0.44:.0f}" height="{h*0.06:.0f}" rx="{h*0.03:.0f}" fill="{INK}"/>')
    b.append(f'<text x="{w/2}" y="{h*0.959:.0f}" text-anchor="middle" font-family="Bugbear DEMO" '
             f'font-size="{h*0.038:.0f}" fill="#fff">Unofficial fan-made kit for Home Assistant</text>')
    return svg(w, h, "".join(b), DEFS)


def character_icon(mdi_name, color):
    return svg(200, 200, badge(mdi_name, 100, 96, 90, color))


def main():
    with open(os.path.join(ROOT, "banner.svg"), "w", encoding="utf-8") as f:
        f.write(banner())
    for key, mdi_name, color in CAST:
        with open(os.path.join(ROOT, f"{key}.svg"), "w", encoding="utf-8") as f:
            f.write(character_icon(mdi_name, color))
    print("wrote assets/banner.svg and", len(CAST), "character icons")


if __name__ == "__main__":
    main()
