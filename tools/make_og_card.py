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
#: the light lockup on its own, for the README header and anywhere a banner is
#: wanted without the card's tagline and bullets (brand study 5.2).
WORDMARK_OUT = os.path.join(ROOT, 'docs', 'assets', 'wordmark.png')
W, H = 1200, 630

NAVY_TOP = (16, 32, 60)
NAVY_BOT = (5, 8, 16)
CYAN = (125, 207, 255)
VIOLET = (138, 92, 246)
TXT = (219, 228, 243)
DIM = (125, 138, 165)

TITLE = 'archeus'
#: The wordmark. Upper case ONLY here and in the TUI header — the product is
#: `archeus` in prose (brand study 4.5), and this is the image, not the word.
MARK = 'ARCHEUS'
# The canonical sentence, verbatim (tests/test_brand_copy.py). It is 51 chars
# against the old line's 35, and one line at 44px measured 1155px of a 1200px
# card — which both crowds the right edge and, because the mark is sized from
# the measured text, left under the 160px floor and dropped the logo entirely.
# So it wraps (TAG_W) at one size down. TAG stays ONE string: the gate greps
# this file for the sentence, and a hand-split literal would hide it.
TAG = 'The memory and workspace layer for AI coding agents.'
#: wrap width for TAG. 600 is chosen, not arbitrary — it breaks after "layer",
#: which is the only break in this sentence that does not split a phrase.
TAG_W = 600
BULLETS = ['Persistent per-project memory',
           'Every session you have ever had',
           'Control over what the next one costs',
           'Works with Claude Code today']


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


def _wrap(d, text, font, maxw):
    """Greedy word wrap. Pillow's own multiline_text needs the breaks already
    in the string, and the string here is the canonical sentence."""
    lines, cur = [], ''
    for word in text.split():
        trial = (cur + ' ' + word).strip()
        if cur and d.textlength(trial, font=font) > maxw:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def draw_card():
    img = _vgradient((W, H), NAVY_TOP, NAVY_BOT).convert('RGBA')
    d = ImageDraw.Draw(img)

    # Accent rule down the left edge, cyan->violet, the app's --grad.
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (10, y)],
               fill=tuple(int(CYAN[i] + (VIOLET[i] - CYAN[i]) * t) for i in range(3)))

    bold = _font(['bahnschrift.ttf', 'segoeuib.ttf', 'DejaVuSans-Bold.ttf'], 108)
    mid = _font(['segoeui.ttf', 'DejaVuSans.ttf'], 40)
    small = _font(['consola.ttf', 'DejaVuSansMono.ttf'], 30)

    x = 88
    d.text((x, 120), TITLE, font=bold, fill=CYAN)

    tag_lines = _wrap(d, TAG, mid, TAG_W)
    y = 252
    for line in tag_lines:
        d.text((x, y), line, font=mid, fill=TXT)
        y += 48

    y = 372
    for b in BULLETS:
        d.ellipse([x + 3, y + 13, x + 13, y + 23], fill=VIOLET)
        d.text((x + 30, y), b, font=small, fill=DIM)
        y += 42

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
        right = max(max(d.textbbox((x, 0), t, font=mid)[2] for t in tag_lines),
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


def draw_wordmark(word_px=200, tile_px=210, pad=52, gap=44):
    """The lockup alone: the tile, then ARCHEUS set large beside it.

    The card (above) is this lockup plus a tagline, bullets and a URL; the
    README wants the lockup on its own. Same source tile as the icon, via
    `make_icon.master` — that function already crops the baked drop shadow off
    by alpha bounding box, and a second cropper is a second answer to "which is
    the logo".

    The canvas is measured, never chosen: `textbbox` gives the ink box of the
    word in whichever font the ladder found, so a DejaVu fallback on Linux CI
    produces a wider, uncropped banner rather than a clipped one.
    """
    from make_icon import master
    bold = _font(['bahnschrift.ttf', 'segoeuib.ttf', 'DejaVuSans-Bold.ttf'], word_px)
    l, t, r, b = ImageDraw.Draw(Image.new('RGB', (1, 1))).textbbox((0, 0), MARK, font=bold)
    tw, th = r - l, b - t

    w = pad + tile_px + gap + tw + pad
    h = max(tile_px, th) + 2 * pad
    img = _vgradient((w, h), NAVY_TOP, NAVY_BOT).convert('RGBA')

    # Accent rule down the left edge, cyan->violet: the card's, so the two read
    # as one family rather than two logos.
    d = ImageDraw.Draw(img)
    for y in range(h):
        k = y / (h - 1)
        d.line([(0, y), (8, y)],
               fill=tuple(int(CYAN[i] + (VIOLET[i] - CYAN[i]) * k) for i in range(3)))

    img.alpha_composite(master(tile_px), (pad, (h - tile_px) // 2))
    d.text((pad + tile_px + gap - l, (h - th) // 2 - t), MARK, font=bold, fill=CYAN)

    os.makedirs(os.path.dirname(WORDMARK_OUT), exist_ok=True)
    img.convert('RGB').save(WORDMARK_OUT, 'PNG', optimize=True)
    print('wrote', WORDMARK_OUT, img.size)


if __name__ == '__main__':
    draw_card()
    draw_wordmark()
