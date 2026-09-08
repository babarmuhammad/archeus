"""Dev-only: generate archeus's app icon. NOT a runtime dependency — run
manually to regenerate:

    py tools/make_icon.py

The mark is an "A" that is also an apex and also a graph, because for this
project those are the same idea: an apex IS a vertex.

  - rounded-square tile, deep-navy → near-black vertical gradient
  - tapered legs — wide at the feet, narrow at the peak, so the silhouette has
    a direction instead of being an even monogram
  - a cyan→violet ramp running down the letter, so it reads as lit from its own
    apex rather than filled flat
  - one blazing node at the apex, with a soft halo
  - three linked nodes inside the counter: the neural core. It lives in the
    chamber the letter already has, which is why it reads at 256px and
    dissolves cleanly at 16px instead of turning into speckle — the failure
    mode of every version that scattered nodes across the strokes.

Requires Pillow. Writes archeus.ico (multi-size) at the repo root.
"""

import os
from collections import namedtuple

from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'archeus.ico')
SS = 1024
SIZES = [16, 32, 48, 64, 128, 256]

NAVY_TOP = (16, 32, 60)      # #10203c
NAVY_BOT = (5, 8, 16)        # #050810
CYAN = (125, 207, 255)       # #7dcfff — the GUI's gradient start
VIOLET = (138, 92, 246)      # #8a5cf6 — and its end
NODE = (215, 238, 255)
NODE_HI = (255, 255, 255)

#: geometry only — the two icons ink it completely differently (a ramp on the
#: dark tile, flat dark on the bright one), so colour is the caller's business.
Mark = namedtuple('Mark', 'letter apex core_pts core_edges')


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


def build_mark(size):
    """The letter as an 'L' mask, plus the points the caller draws on top.

    The crossbar spans centreline to centreline of the two legs rather than a
    fixed width. That is not a detail: the legs taper, so any fixed half-width
    leaves the bar floating in the counter with a visible gap at both ends.
    """
    cx = cy = size / 2
    hw, hh = size * 0.29, size * 0.30
    apex = (cx, cy - hh)
    thin, thick = size * 0.042, size * 0.092

    letter = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(letter)
    for s in (-1, 1):
        d.polygon([(cx - thin * .5, apex[1]), (cx + thin * .5, apex[1]),
                   (cx + s * hw + thick * .5, cy + hh),
                   (cx + s * hw - thick * .5, cy + hh)], fill=255)
    tbar = 0.72
    ybar = apex[1] + (cy + hh - apex[1]) * tbar
    d.rectangle([cx - hw * tbar, ybar, cx + hw * tbar, ybar + size * .050], fill=255)

    mid = (apex[1] + ybar) / 2 + size * .015
    spread = size * .066
    core = [(cx, mid - size * .045),
            (cx - spread, mid + size * .030), (cx + spread, mid + size * .030)]
    return Mark(letter, apex, core, [(core[i], core[(i + 1) % 3]) for i in range(3)])


def paint_mark(mark, size, ink, node, node_hi, edge_alpha=130):
    """The mark as one RGBA layer. *ink* is an image the size of the canvas
    (a gradient) or a flat colour tuple — whichever the tile calls for."""
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    if isinstance(ink, tuple):
        flat = Image.new('RGBA', (size, size), ink + (255,))
        flat.putalpha(mark.letter)
        layer = flat
    else:
        ink = ink.convert('RGBA')
        ink.putalpha(mark.letter)
        layer = ink

    d = ImageDraw.Draw(layer)
    for a, b in mark.core_edges:
        d.line([a, b], fill=node[:3] + (edge_alpha,), width=max(1, int(size * .009)))
    for (x, y) in mark.core_pts:
        r = size * .026
        d.ellipse([x - r, y - r, x + r, y + r], fill=node)
        r *= .45
        d.ellipse([x - r, y - r, x + r, y + r], fill=node_hi)
    ax, ay = mark.apex
    r = size * .050
    d.ellipse([ax - r, ay - r, ax + r, ay + r], fill=node)
    r *= .45
    d.ellipse([ax - r, ay - r, ax + r, ay + r], fill=node_hi)
    return layer


def apex_halo(mark, size, colour, alpha=50, radius=0.125):
    g = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ax, ay = mark.apex
    ImageDraw.Draw(g).ellipse([ax - size * radius, ay - size * radius,
                               ax + size * radius, ay + size * radius],
                              fill=colour[:3] + (alpha,))
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

    mark = build_mark(SS)
    layer = paint_mark(mark, SS, _gradient(SS, CYAN, VIOLET), NODE + (255,), NODE_HI + (255,))
    base = Image.alpha_composite(base, apex_halo(mark, SS, CYAN))
    base = Image.alpha_composite(base, layer.filter(ImageFilter.GaussianBlur(SS * 0.020)))
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
