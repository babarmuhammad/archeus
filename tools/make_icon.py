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
    www/app/favicon.ico      the marketing site. Next.js's App Router serves
                             `app/favicon.ico` in preference to
                             `public/favicon.ico`, so a copy in `public/` is
                             never requested — it was 115 KB shipped on every
                             deploy for nothing, and is gone.
    www/app/apple-icon.png   180px, the iOS home-screen icon. A file-convention
                             name, so Next emits the `apple-touch-icon` link
                             itself and no metadata entry has to name it.
    www/public/icon-192.png  the two sizes `app/manifest.ts` declares. An ICO in
    www/public/icon-512.png  a web manifest is legal and useless: Android reads
                             PNG, and the ICO it was pointed at held one 256px
                             frame inside 115 KB.
    docs/assets/logo-256.png the MkDocs header logo, which renders about 30px
                             tall. It used to be the 1254px master — 998 KB on
                             every page of the manual.

**A favicon does not need a 256px frame.** The ICO carried 16/32/48/64/128/256
everywhere, which is right for the app icon (Windows draws shortcuts and the
taskbar from the large frames) and is most of 115 KB for a 16px browser tab.
`SIZES` is per target now.

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

#: the app icon: Windows draws a shortcut, a taskbar pin and an Alt-Tab card
#: from different frames, so it needs all of them.
APP_SIZES = [16, 32, 48, 64, 128, 256]
#: a favicon is drawn at 16 and, on a retina tab or a bookmark bar, at 32 or 48.
#: Nothing asks a favicon for 256.
FAVICON_SIZES = [16, 32, 48]

#: every place the icon has to exist, relative to the repo root, with the ICO
#: frames each one actually needs.
#:
#: The app icon lives INSIDE the package, not at the repo root where it used to
#: sit. package-data ships it from there, and `gui_qt._icon_path` already looked
#: alongside the package as its second candidate — so until now every pip and
#: pipx install ran the desktop window with no icon at all, and only a dev
#: checkout ever had one. One copy, in the only place that works for both.
TARGETS = [
    (os.path.join('claude_sessions', 'archeus.ico'), APP_SIZES),
    (os.path.join('docs', 'assets', 'favicon.ico'), FAVICON_SIZES),
    (os.path.join('www', 'app', 'favicon.ico'), FAVICON_SIZES),
]

#: PNG icons, `(path, pixel size)`. Each is written from the same master.
PNG_TARGETS = [
    (os.path.join('www', 'app', 'apple-icon.png'), 180),
    (os.path.join('www', 'public', 'icon-192.png'), 192),
    (os.path.join('www', 'public', 'icon-512.png'), 512),
    (os.path.join('docs', 'assets', 'logo-256.png'), 256),
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
    left, top, right, bottom = box
    left, top = max(0, left - _FEATHER), max(0, top - _FEATHER)
    right = min(im.width, right + _FEATHER)
    bottom = min(im.height, bottom + _FEATHER)
    tile = im.crop((left, top, right, bottom))

    side = max(tile.size)
    square = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    square.alpha_composite(tile, ((side - tile.width) // 2, (side - tile.height) // 2))
    return square.resize((size, size), Image.LANCZOS)


def main():
    big = master()
    for rel, sizes in TARGETS:
        out = os.path.join(ROOT, rel)
        big.save(out, format='ICO', sizes=[(s, s) for s in sizes])
        print('wrote %s  (%s)  %d KB'
              % (rel, ', '.join(str(s) for s in sizes), os.path.getsize(out) // 1024))
    for rel, size in PNG_TARGETS:
        out = os.path.join(ROOT, rel)
        big.resize((size, size), Image.LANCZOS).save(out, format='PNG', optimize=True)
        print('wrote %s  (%dpx)  %d KB' % (rel, size, os.path.getsize(out) // 1024))


if __name__ == '__main__':
    main()
