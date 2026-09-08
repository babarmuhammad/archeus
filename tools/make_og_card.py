"""Dev-only: generate the docs site's Open Graph / Twitter card image.

    py tools/make_og_card.py

1200x630 is the size every social preview crops to. Palette and gradient helper
are the app icon's (tools/make_icon.py) so the card, the favicon and the GUI all
read as one product. Fonts are Windows-shipped with a DejaVu fallback so a Linux
CI run still produces something rather than dying — the file is committed, so
this normally runs on the author's machine only.

Requires Pillow. Writes the card to BOTH sites (not docs/img, which holds only
tool-generated screenshots — see tests/test_demo_fixtures.py). Both, because
this used to write the docs copy and leave `www/public/` to be updated by hand,
and the two had already drifted apart by a kilobyte — the same one-source rule
`make_icon.py` follows for the favicons.
"""

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTS = [os.path.join(ROOT, 'docs', 'assets', 'og-card.png'),
        os.path.join(ROOT, 'www', 'public', 'og-card.png')]
OUT = OUTS[0]
W, H = 1200, 630

NAVY_TOP = (16, 32, 60)
NAVY_BOT = (5, 8, 16)
CYAN = (125, 207, 255)
VIOLET = (138, 92, 246)
TXT = (219, 228, 243)
DIM = (125, 138, 165)

TITLE = 'archeus'
TAG = 'The workspace layer for Claude Code'
BULLETS = ['Persistent project memory',
           'Browsable session archive',
           'MCP awareness  ·  architecture graph',
           'Zero runtime dependencies']


def _vgradient(size, top, bot):
    w, h = size
    g = Image.new('RGB', size)
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / (h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    return g


def _font(names, size):
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_card():
    img = _vgradient((W, H), NAVY_TOP, NAVY_BOT).convert('RGBA')
    d = ImageDraw.Draw(img)

    # Accent rule down the left edge, cyan->violet, the app's --grad.
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (10, y)],
               fill=tuple(int(CYAN[i] + (VIOLET[i] - CYAN[i]) * t) for i in range(3)))

    bold = _font(['bahnschrift.ttf', 'segoeuib.ttf', 'DejaVuSans-Bold.ttf'], 108)
    mid = _font(['segoeui.ttf', 'DejaVuSans.ttf'], 44)
    small = _font(['consola.ttf', 'DejaVuSansMono.ttf'], 30)

    x = 88
    d.text((x, 132), TITLE, font=bold, fill=CYAN)
    d.text((x, 268), TAG, font=mid, fill=TXT)

    y = 356
    for b in BULLETS:
        d.ellipse([x + 3, y + 13, x + 13, y + 23], fill=VIOLET)
        d.text((x + 30, y), b, font=small, fill=DIM)
        y += 44

    d.text((x, H - 62), 'github.com/babarmuhammad/archeus', font=small, fill=CYAN)

    # The mark, in whatever space the text actually leaves. Same source and the
    # same crop as the app icon (make_icon.master), so the card cannot drift
    # away from the icon.
    #
    # Sized from the measured text, not from a chosen number: the first attempt
    # used a fixed 360px and the tile landed on top of the tagline, and any
    # fixed value goes wrong again the moment a line gets longer.
    try:
        from make_icon import master
        right = max(d.textbbox((x, 0), TAG, font=mid)[2],
                    d.textbbox((x, 0), TITLE, font=bold)[2],
                    max(d.textbbox((x + 30, 0), b, font=small)[2] for b in BULLETS))
        margin = 48
        side = min(H - 2 * margin, W - right - 2 * margin)
        if side >= 160:                         # below that it reads as a smudge
            mark = master(side)
            img.alpha_composite(mark, (W - side - margin, (H - side) // 2))
        else:
            print('logo skipped: only %dpx of clear space' % side)
    except Exception as e:                      # Pillow missing, or no source
        print('logo skipped:', e)

    flat = img.convert('RGB')
    for out in OUTS:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        flat.save(out, 'PNG', optimize=True)
        print('wrote', out, img.size)


if __name__ == '__main__':
    draw_card()
