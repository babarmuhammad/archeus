"""Dev-only: make every published image cost what it is worth.

    py tools/optimize_images.py            # rewrite anything oversized
    py tools/optimize_images.py --check    # CI: fail if something is not optimized

Two jobs, because the two published sites carry two different problems.

**The screenshots** under `docs/img/` and `www/public/img/` are written by
`tools/shot_gui.py` and `tools/shot_tui.py` as true-colour PNGs. A UI screenshot
is flat: the nine here average about 12,000 unique colours over 1.6M pixels, so a
256-entry palette is a near-lossless description of one and a 24-bit buffer is
not. Measured, the set goes 2341 KB -> 488 KB. Plain `optimize=True` gets
2341 -> 2280, which is why this quantizes instead of just recompressing.

`RMSE_MAX` is the safety rail, and it earns its keep: six of the nine
screenshots score 4.1-5.0 and are REFUSED, because at that error the palette
bands the dark gradient behind the cards — invisible in the chrome and the text,
plainly visible as a horizontal step across the background. Measured by looking
at it, not by trusting the number. So palettizing is the free half only.

**The lossy half is a WebP sibling, and only where it wins.** Each screenshot
also gets `<name>.webp` when WebP is smaller than the PNG, and the docs markdown
points at whichever file is actually smaller. Three of the nine are already
palette PNGs that WebP cannot beat, and for those no sibling is written — a
`.webp` that is bigger than the `.png` beside it is a slower page and a second
file to keep in step.

The PNG always stays, and is the master: `README.md` embeds these by
raw.githubusercontent URL so PyPI renders them, and the two sites are the only
consumers that get the WebP. `www/public/img` gets no WebP at all — `next/image`
negotiates AVIF/WebP per request there, so a second source file would be
converted right back.

**The architecture-graph animation** was the single heaviest asset either site
shipped, at 5770 KB, because it was a GIF and GIF has no interframe compression
worth the name. `tools/capture_graph_gif.py` writes animated WebP now — the same
frames, 538 KB — so there is nothing left here to convert, and this only mirrors
the one capture into `www/public/` so the two sites cannot drift onto two
different recordings of the graph.

Requires Pillow.
"""

import io
import math
import os
import sys

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Directories whose PNGs are screenshots — flat UI, safe to palettize.
PNG_DIRS = [
    os.path.join('docs', 'img'),
    os.path.join('www', 'public', 'img'),
]

#: Screenshots here are served RAW: MkDocs copies the file and links it. This is
#: the only place a WebP sibling buys anything, and it is where the weight was —
#: `docs/desktop.md` alone carried 1470 KB of PNG.
WEBP_DIR = os.path.join('docs', 'img')

#: WebP quality for a screenshot. At 80 the text in a 1600px UI capture is
#: indistinguishable from the PNG at a quarter of the bytes; the artefacts WebP
#: makes are in gradients, which is exactly where the palette failed.
WEBP_QUALITY = 80

#: Loose PNGs worth the same treatment. Brand artwork, so each is named rather
#: than swept up by directory: `og-card.png` must stay a PNG at 1200x630 because
#: that is what the social scrapers fetch, and the icons are written by
#: tools/make_icon.py from the master.
#: NOT here, and it is the one that looks like it belongs:
#: `docs/assets/wordmark.png`. Palettizing it costs 180 KB and its alpha CHANNEL
#: — a palette PNG carries one transparency value per entry, so the
#: antialiased edge of the mark goes from a smooth ramp to a hard cut. That
#: banner composites onto a light GitHub page, a dark one and the navy OG card,
#: and `test_the_banner_is_artwork_the_card_only_reads` asserts colour type 6
#: for exactly that reason. It caught this on the first run.
PNG_FILES = [
    os.path.join('www', 'public', 'icon-512.png'),
    os.path.join('www', 'public', 'icon-192.png'),
    os.path.join('www', 'app', 'apple-icon.png'),
    os.path.join('docs', 'assets', 'logo-256.png'),
    os.path.join('docs', 'assets', 'og-card.png'),
    os.path.join('www', 'public', 'og-card.png'),
]

#: Files published on both sites from one source, `(source, copy)`. The
#: architecture-graph capture is written once by `tools/capture_graph_gif.py`
#: and the marketing site reads that byte-for-byte; it used to hold its own
#: 4.5 MB copy of an older capture, which is two captures to keep in step and
#: was already out of step.
MIRRORS = [
    (os.path.join('docs', 'graph-real.webp'),
     os.path.join('www', 'public', 'graph-real.webp')),
]

#: Root-mean-square error, 0-255 per channel, above which a rewrite is refused.
#: Measured on this set: a clean palettization of a UI screenshot scores under 2.
RMSE_MAX = 4.0

#: Don't rewrite for nothing. A file already within this of its optimized size is
#: left alone, which is what makes `--check` stable across runs.
MIN_GAIN = 0.05


def _rmse(a, b):
    """Root-mean-square difference between two images, over every band they have.

    Alpha is compared like any other channel rather than discarded: an icon is
    mostly transparent, so a rewrite that flattened it would score a perfect
    zero on RGB alone."""
    diff = ImageChops.difference(a, b.convert(a.mode))
    hist = diff.histogram()
    total = sq = 0
    for band in range(len(a.getbands())):
        for value, count in enumerate(hist[band * 256:(band + 1) * 256]):
            total += count
            sq += count * value * value
    return math.sqrt(sq / total) if total else 0.0


def _has_alpha(im):
    """Whether dropping the alpha channel would lose anything.

    A palette PNG carries its transparency as an `info` key rather than a band,
    so `getbands()` alone reports ('P',) and converting straight to RGB both
    loses it and warns."""
    return 'A' in im.getbands() or 'transparency' in im.info


def _optimized_png(path):
    """The smallest honest PNG for this file, or None if it cannot be improved."""
    original = Image.open(path)
    alpha = _has_alpha(original)
    src = original.convert('RGBA' if alpha else 'RGB')
    # MAXCOVERAGE picks the palette from the whole colour cube rather than from
    # the median cut, which matters for UI: a screenshot's rare colours are its
    # accents and its state badges, the exact things a reader is looking at.
    # Pillow only offers FASTOCTREE for an image with alpha, and it is the
    # transparent brand artwork that lands there rather than any screenshot.
    method = Image.FASTOCTREE if alpha else Image.MAXCOVERAGE
    palette = src.quantize(colors=256, method=method)
    buf = io.BytesIO()
    palette.save(buf, 'PNG', optimize=True)
    if _rmse(src, palette) > RMSE_MAX:
        return None
    if buf.tell() > os.path.getsize(path) * (1 - MIN_GAIN):
        return None
    return buf.getvalue()


def _webp_sibling(path):
    """The screenshot as WebP, or None if the PNG beside it is already smaller."""
    src = Image.open(path)
    im = src.convert('RGBA' if _has_alpha(src) else 'RGB')
    buf = io.BytesIO()
    im.save(buf, 'WEBP', quality=WEBP_QUALITY, method=6)
    return buf.getvalue() if buf.tell() < os.path.getsize(path) else None


def _targets():
    """Every `(kind, path)` job this tool is responsible for.

    `png` rewrites the file in place; `webp` writes a `.webp` sibling and
    `mirror` copies a file to its second home, both leaving the source alone."""
    out = []
    for rel in PNG_DIRS:
        d = os.path.join(ROOT, rel)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith('.png'):
                continue
            out.append(('png', os.path.join(rel, name)))
            if rel == WEBP_DIR:
                out.append(('webp', os.path.join(rel, name)))
    for rel in PNG_FILES:
        if os.path.isfile(os.path.join(ROOT, rel)):
            out.append(('png', rel))
    for src, _ in MIRRORS:
        if os.path.isfile(os.path.join(ROOT, src)):
            out.append(('mirror', src))
    return out


def _write(out_rel, src_rel, data, stale, saved, check, note):
    """Write a derived file, or retire it when `data` is None."""
    out = os.path.join(ROOT, out_rel)
    if data is None:
        # WebP lost to the PNG. A stale sibling from an earlier run would be
        # published and linked, so it goes rather than being left to rot.
        if os.path.isfile(out):
            stale.append(out_rel)
            if not check:
                os.remove(out)
                print('%-34s removed — the PNG beside it is smaller' % out_rel)
        return saved
    if os.path.isfile(out) and abs(os.path.getsize(out) - len(data)) <= 1024:
        return saved
    before = os.path.getsize(os.path.join(ROOT, src_rel))
    stale.append(out_rel)
    if not check:
        with open(out, 'wb') as f:
            f.write(data)
        print('%-34s %6d -> %6d KB  (%s)'
              % (out_rel, before // 1024, len(data) // 1024, note))
    return saved + max(0, before - len(data))


def main(check=False):
    stale, saved = [], 0
    for kind, rel in _targets():
        path = os.path.join(ROOT, rel)
        if kind == 'png':
            data = _optimized_png(path)
            if data is None:
                continue
            before = os.path.getsize(path)
            stale.append(rel)
            saved += before - len(data)
            if not check:
                with open(path, 'wb') as f:
                    f.write(data)
                print('%-34s %6d -> %6d KB' % (rel, before // 1024, len(data) // 1024))
        elif kind == 'webp':
            saved = _write(rel[:-4] + '.webp', rel, _webp_sibling(path),
                           stale, saved, check, 'q%d' % WEBP_QUALITY)
        else:
            with open(path, 'rb') as f:
                data = f.read()
            for src, copy in MIRRORS:
                if src == rel:
                    saved = _write(copy, rel, data, stale, saved, check, 'copy of ' + rel)

    if check:
        if stale:
            print('not optimized (run `py tools/optimize_images.py`):')
            for rel in stale:
                print('  ' + rel)
            print('%d KB recoverable' % (saved // 1024))
            return 1
        print('images optimized: %d checked' % len(_targets()))
        return 0
    print('\n%d rewritten, %d KB saved' % (len(stale), saved // 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main(check='--check' in sys.argv))
