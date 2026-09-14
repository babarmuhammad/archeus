"""Dev-only: generate the docs site's Open Graph / Twitter card image.

    py tools/make_og_card.py

1200x630 is the size every social preview crops to. Palette and gradient helper
are the app icon's (tools/make_icon.py) so the card, the favicon and the GUI all
read as one product. Fonts are Windows-shipped with a DejaVu fallback so a Linux
CI run still produces something rather than dying — the file is committed, so
this normally runs on the author's machine only.

The banner (`docs/assets/wordmark.png`) used to be generated here too — a tile
beside ARCHEUS set in cyan. It is the supplied gold lockup now, artwork rather
than output, and this file no longer writes it.

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
#: The banner, READ (never written) — the card composes it, and it is artwork:
#: the gold lockup, not something this file could regenerate.
MARK_SRC = os.path.join(ROOT, 'docs', 'assets', 'wordmark.png')
#: `docs/assets/wordmark.png` is NOT written here any more, and must not be:
#: the banner is now the supplied gold lockup, a hand-drawn master exactly like
#: `logo.png`, so a generator that rebuilt a cyan one from a font would simply
#: overwrite the artwork the next time anyone ran this file.
W, H = 1200, 630

NAVY_TOP = (16, 32, 60)
NAVY_BOT = (5, 8, 16)
CYAN = (125, 207, 255)
VIOLET = (138, 92, 246)
TXT = (219, 228, 243)
DIM = (125, 138, 165)

TITLE = 'archeus'
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

    # No `archeus` title any more: the mark on the right IS the name, set in the
    # brand's own letterforms and twice the size a font could give it here, so a
    # cyan word beside it was the same word twice. The tagline leads instead.
    x = 88
    tag_lines = _wrap(d, TAG, mid, TAG_W)
    y = 196
    for line in tag_lines:
        d.text((x, y), line, font=mid, fill=TXT)
        y += 48

    y = 336
    for b in BULLETS:
        d.ellipse([x + 3, y + 13, x + 13, y + 23], fill=VIOLET)
        d.text((x + 30, y), b, font=small, fill=DIM)
        y += 42

    d.text((x, H - 62), 'github.com/babarmuhammad/archeus', font=small, fill=CYAN)

    # The banner artwork, in whatever space the text actually leaves. It is the
    # SAME file the README shows (docs/assets/wordmark.png), so the card cannot
    # drift away from the mark — the card is a composition, the mark is not
    # redrawn here. It is transparent gold over a dark shadow, which is why it
    # can sit straight on the navy: the shadow vanishes and the gold does not.
    #
    # Sized from the measured text, not from a chosen number: a fixed width goes
    # wrong the moment a tagline line gets longer, which is how an earlier
    # version landed the mark on top of the text.
    try:
        right = max(max(d.textbbox((x, 0), t, font=mid)[2] for t in tag_lines),
                    max(d.textbbox((x + 30, 0), b, font=small)[2] for b in BULLETS))
        margin = 44
        avail_w = W - right - 2 * margin
        avail_h = H - 2 * margin
        if avail_w >= 200:                      # below that it reads as a smudge
            mark = Image.open(MARK_SRC).convert('RGBA')
            k = min(avail_w / mark.width, avail_h / mark.height)
            mark = mark.resize((round(mark.width * k), round(mark.height * k)),
                               Image.LANCZOS)
            img.alpha_composite(mark, (W - mark.width - margin,
                                       (H - mark.height) // 2))
        else:
            print('mark skipped: only %dpx of clear space' % avail_w)
    except Exception as e:                      # Pillow missing, or no source
        print('mark skipped:', e)

    flat = img.convert('RGB')
    for out in OUTS:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        flat.save(out, 'PNG', optimize=True)
        print('wrote', out, img.size)


if __name__ == '__main__':
    draw_card()
