"""Dev-only: generate archeus's app icon. NOT a runtime dependency — run
manually to regenerate:

    py tools/make_icon.py

Design (per 2025 app-icon best practice: one dominant element, legible at 16px,
rounded square, gradient depth, brand colour):
  - rounded-square tile, deep-navy → near-black vertical gradient
  - one bold cyan "A" (archeus) with round caps
  - three glowing nodes at its apex and feet — a nod to the connections graph
  - soft outer glow for depth

Requires Pillow. Writes archeus.ico (multi-size) at the repo root.
"""

import math
import os

from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'archeus.ico')
SS = 1024
SIZES = [16, 32, 48, 64, 128, 256]

NAVY_TOP = (16, 32, 60)      # #10203c
NAVY_BOT = (5, 8, 16)        # #050810
CYAN = (92, 200, 255)        # #5cc8ff
CYAN_HI = (170, 226, 255)    # highlight


def _rounded_mask(size, radius):
    m = Image.new('L', (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def _gradient(size, top, bot):
    g = Image.new('RGB', (size, size))
    px = g.load()
    for y in range(size):
        t = y / (size - 1)
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        for x in range(size):
            px[x, y] = c
    return g


def draw_mark(d, cx, cy, w, ink, node_ink, size=SS):
    """The "A" — two legs, a crossbar, three nodes. Shared by both icons.

    The nodes at the apex and the feet are not decoration: they are the same
    nod to the connections graph the previous mark carried, and the one thing
    about that icon that was about this project rather than about its initial.
    The letter itself is what had to change.

    The crossbar sits low (0.66 of the way down) and slightly narrower than the
    legs, because the icon has to stay legible at 16px — a centred bar closes
    the counter into a solid triangle at that size.
    """
    hw, hh = size * 0.26, size * 0.27
    apex = (cx, cy - hh)
    feet = [(cx - hw, cy + hh), (cx + hw, cy + hh)]
    # one polyline, so the apex is a mitred join rather than two overlapping caps
    d.line([feet[0], apex, feet[1]], fill=ink, width=w, joint='curve')
    t = 0.66
    ybar = apex[1] + (feet[0][1] - apex[1]) * t
    d.line([(cx - hw * t, ybar), (cx + hw * t, ybar)], fill=ink, width=int(w * 0.8))
    nodes = [apex] + feet
    for (nx, ny) in nodes:                   # round caps
        d.ellipse([nx - w / 2, ny - w / 2, nx + w / 2, ny + w / 2], fill=ink)
    nr = w * 0.42                            # bright cores
    for (nx, ny) in nodes:
        d.ellipse([nx - nr, ny - nr, nx + nr, ny + nr], fill=node_ink)


def draw_icon():
    pad = int(SS * 0.04)
    inner = SS - pad * 2
    radius = int(SS * 0.22)

    # ── background tile (gradient + rounded mask + faint top sheen) ──
    base = Image.new('RGBA', (SS, SS), (0, 0, 0, 0))
    tile = _gradient(inner, NAVY_TOP, NAVY_BOT).convert('RGBA')
    tile.putalpha(_rounded_mask(inner, radius))
    sheen = Image.new('RGBA', (inner, inner), (0, 0, 0, 0))
    ImageDraw.Draw(sheen).rounded_rectangle([0, 0, inner - 1, int(inner * 0.5)],
                                            radius=radius, fill=(255, 255, 255, 16))
    tile = Image.alpha_composite(tile, sheen)
    base.alpha_composite(tile, (pad, pad))

    # ── the mark + nodes, drawn on a transparent layer for glow ──
    layer = Image.new('RGBA', (SS, SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = cy = SS / 2
    draw_mark(d, cx, cy, int(SS * 0.12), CYAN, CYAN_HI)

    glow = layer.filter(ImageFilter.GaussianBlur(SS * 0.02))
    base = Image.alpha_composite(base, glow)
    base = Image.alpha_composite(base, layer)

    # clip everything to the rounded tile so the glow doesn't bleed past corners
    full_mask = Image.new('L', (SS, SS), 0)
    full_mask.paste(_rounded_mask(inner, radius), (pad, pad))
    base.putalpha(full_mask)

    # Save from the LARGEST frame; PIL downscales to every requested size.
    # (Passing `sizes` together with a small base silently keeps only 16×16.)
    big = base.resize((max(SIZES), max(SIZES)), Image.LANCZOS)
    big.save(OUT, format='ICO', sizes=[(s, s) for s in SIZES])
    print(f"wrote {OUT}  ({', '.join(str(s) for s in SIZES)})")


if __name__ == '__main__':
    draw_icon()
