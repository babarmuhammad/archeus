"""Dev-only: generate the DESKTOP GUI app icon (distinct from the TUI's
navy-tile archeus.ico — this is the GUI brand inverted: the app's cyan→violet
gradient tile carrying the same mark in dark ink). Run manually to regenerate:

    py tools/make_gui_icon.py

The geometry comes from make_icon.build_mark, so the two icons cannot drift
apart. Only the inking differs, and it has to: the TUI tile is dark, so the
letter is a cyan→violet ramp lit from the apex; this tile IS that ramp, so the
letter has to be dark against it and the neural core inverts to white cores on
dark nodes.

Requires Pillow. Writes archeus-gui.ico (multi-size) at the repo root.
"""

import os

from PIL import Image, ImageDraw, ImageFilter

from make_icon import _rounded_mask, apex_halo, build_mark, paint_mark, SIZES

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'archeus-gui.ico')
SS = 1024

CYAN = (125, 207, 255)       # #7dcfff — GUI gradient start
VIOLET = (138, 92, 246)      # #8a5cf6 — GUI gradient end
DARK = (13, 17, 23)          # #0d1117 — the GUI's --bg / on-accent ink
WHITE = (240, 246, 255)


def _diag_gradient(size, a, b):
    g = Image.new('RGB', (size, size))
    px = g.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return g


def draw_icon():
    pad = int(SS * 0.04)
    inner = SS - pad * 2
    radius = int(SS * 0.22)

    base = Image.new('RGBA', (SS, SS), (0, 0, 0, 0))
    tile = _diag_gradient(inner, CYAN, VIOLET).convert('RGBA')
    tile.putalpha(_rounded_mask(inner, radius))
    sheen = Image.new('RGBA', (inner, inner), (0, 0, 0, 0))
    ImageDraw.Draw(sheen).rounded_rectangle([0, 0, inner - 1, int(inner * 0.5)],
                                            radius=radius, fill=(255, 255, 255, 34))
    tile = Image.alpha_composite(tile, sheen)
    base.alpha_composite(tile, (pad, pad))

    mark = build_mark(SS)
    # dark ink, white node cores, and a stronger edge alpha — a thin dark line
    # on a saturated tile carries far less than the same line on near-black
    layer = paint_mark(mark, SS, DARK, DARK + (255,), WHITE + (255,), edge_alpha=190)
    # a white halo, not cyan: the apex has to lift OFF this tile, not blend into it
    base = Image.alpha_composite(base, apex_halo(mark, SS, WHITE, alpha=90, radius=0.115))
    base = Image.alpha_composite(base, layer.filter(ImageFilter.GaussianBlur(SS * 0.015)))
    base = Image.alpha_composite(base, layer)

    full_mask = Image.new('L', (SS, SS), 0)
    full_mask.paste(_rounded_mask(inner, radius), (pad, pad))
    base.putalpha(full_mask)

    big = base.resize((max(SIZES), max(SIZES)), Image.LANCZOS)
    big.save(OUT, format='ICO', sizes=[(s, s) for s in SIZES])
    print(f"wrote {OUT}  ({', '.join(str(s) for s in SIZES)})")


if __name__ == '__main__':
    draw_icon()
