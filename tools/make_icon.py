"""Dev-only: generate archeus's app icon. NOT a runtime dependency — run
manually to regenerate:

    py tools/make_icon.py

Design (per 2025 app-icon best practice: one dominant element, legible at 16px,
rounded square, gradient depth, brand colour):
  - rounded-square tile, deep-navy → near-black vertical gradient
  - one bold cyan "C" (archeus) with round caps
  - three glowing nodes on the arc — a subtle nod to the connections graph
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

    # ── the "C" mark + nodes, drawn on a transparent layer for glow ──
    layer = Image.new('RGBA', (SS, SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = cy = SS / 2
    R = SS * 0.27
    w = int(SS * 0.12)                       # stroke width
    box = [cx - R, cy - R, cx + R, cy + R]
    a0, a1 = 52, 308                          # open on the right (a "C")
    d.arc(box, a0, a1, fill=CYAN, width=w)
    # round caps + endpoint nodes
    nodes = []
    for ang in (a0, a1, 180):                 # two caps + left middle
        nx = cx + R * math.cos(math.radians(ang))
        ny = cy + R * math.sin(math.radians(ang))
        nodes.append((nx, ny))
        d.ellipse([nx - w / 2, ny - w / 2, nx + w / 2, ny + w / 2], fill=CYAN)
    # bright node cores
    nr = w * 0.42
    for (nx, ny) in nodes:
        d.ellipse([nx - nr, ny - nr, nx + nr, ny + nr], fill=CYAN_HI)

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
