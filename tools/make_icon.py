"""Dev-only: build every icon archeus ships, from ONE source image.

    py tools/make_icon.py

The master is `docs/assets/logo.png` — a hand-drawn mark, not a generated one,
which is why this file no longer draws anything. It replaced a pair of scripts
that each drew their own variant programmatically: a navy-tile mark for the TUI
and an inverted bright-tile one for the GUI. Two marks for one product is two
things to keep in step, and the answer to "which is the logo" was "it depends
where you are looking", which is not an answer.

Written from that one source:

    archeus.ico              the app icon — Qt window, shortcuts, taskbar pin
    docs/assets/favicon.ico  the documentation site
    www/public/favicon.ico   the marketing site

Two things this does to the source, and both matter:

- **Crops to the tile.** The export is 1254px with the artwork off-centre and a
  soft drop shadow running to the canvas edge. An icon must not carry a baked
  shadow — every OS draws its own — and an off-centre one looks wrong the
  moment it sits next to another icon in a taskbar. The crop is taken from the
  alpha channel at a threshold that keeps the tile and drops the shadow, then
  padded back to square so the mark stays centred.

- **Saves from the LARGEST frame.** Passing `sizes` alongside a small base
  silently keeps only 16x16 — a trap this file has carried a comment about
  since the first icon.

Requires Pillow.
"""

import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'docs', 'assets', 'logo.png')
SIZES = [16, 32, 48, 64, 128, 256]

#: every place the icon has to exist, relative to the repo root.
#:
#: The app icon lives INSIDE the package, not at the repo root where it used to
#: sit. package-data ships it from there, and `gui_qt._icon_path` already looked
#: alongside the package as its second candidate — so until now every pip and
#: pipx install ran the desktop window with no icon at all, and only a dev
#: checkout ever had one. One copy, in the only place that works for both.
TARGETS = [
    os.path.join('claude_sessions', 'archeus.ico'),
    os.path.join('docs', 'assets', 'favicon.ico'),
    os.path.join('www', 'public', 'favicon.ico'),
]

#: alpha at or above this is the tile; below it is the drop shadow. Measured on
#: the source: the tile edge sits at 250+, the shadow trails off well under 128.
_TILE_ALPHA = 128
#: a few pixels of the antialiased edge kept, so the crop is not a hard cut
_FEATHER = 4


def master(size=1024):
    """The source, cropped to its tile, squared and centred."""
    im = Image.open(SRC).convert('RGBA')
    solid = im.getchannel('A').point(lambda v: 255 if v >= _TILE_ALPHA else 0)
    box = solid.getbbox()
    if not box:
        raise SystemExit('%s is fully transparent' % SRC)
    l, t, r, b = box
    l, t = max(0, l - _FEATHER), max(0, t - _FEATHER)
    r, b = min(im.width, r + _FEATHER), min(im.height, b + _FEATHER)
    tile = im.crop((l, t, r, b))

    side = max(tile.size)
    square = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    square.alpha_composite(tile, ((side - tile.width) // 2, (side - tile.height) // 2))
    return square.resize((size, size), Image.LANCZOS)


def main():
    big = master()
    for rel in TARGETS:
        out = os.path.join(ROOT, rel)
        big.save(out, format='ICO', sizes=[(s, s) for s in SIZES])
        print('wrote %s  (%s)' % (rel, ', '.join(str(s) for s in SIZES)))


if __name__ == '__main__':
    main()
