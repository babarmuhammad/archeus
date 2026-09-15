"""What the two published sites are allowed to weigh.

Page weight is the whole Core Web Vitals story here — the sites ship no webfont,
no analytics and no third-party script, so an image is the only thing that can
make a page slow. And image weight arrives quietly: a screenshot pass regenerates
nine files at once, and nobody reads nine numbers in a diff.

Three things are asserted, and they are three different failures:

- **A budget per directory.** Cheap, blunt, and the only thing that catches "the
  new capture is fine, it is just 900 KB".
- **No format that has no business being published.** A GIF of a UI animation is
  a tenfold cost for nothing; `tools/capture_graph_gif.py` writes WebP.
- **Every image a docs page links actually exists, and is the small one.** The
  WebP siblings are pointless if the markdown still names the PNG, which is
  exactly the state the repo was in before `tools/optimize_images.py` existed.

The numbers are ceilings with headroom, not measurements of today. A ceiling that
tracks the current size to the byte fails on every legitimate change and gets
raised without being read, which is the same as not having one.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')

#: `directory -> KB ceiling for everything directly inside it`.
#:
#: docs/img holds a PNG master and a WebP derivative for most screenshots; the
#: PNG is what README.md embeds for PyPI and the WebP is what the manual links.
#: www/public/img holds PNG only — next/image negotiates the format per request
#: there, so a second source file would be re-encoded on the way out.
BUDGET_KB = {
    os.path.join('docs', 'img'): 3000,
    # Nearly all of this is two masters no page serves: the 1254px logo every
    # icon is cut from, and the wordmark, which stays truecolour+alpha because
    # it composites onto three different grounds.
    os.path.join('docs', 'assets'): 1400,
    os.path.join('www', 'public'): 700,
    os.path.join('www', 'public', 'img'): 2400,
}

#: The ceiling for one image a reader actually downloads. 600 KB is the
#: architecture-graph animation at 538 KB plus room to breathe; it was 5770 KB
#: as a GIF.
#:
#: This is deliberately a cap on what is LINKED, not on what is stored. Two
#: files in the repo are over it and both are masters no page requests:
#: `docs/assets/logo.png` (1254px, the source every icon is cut from, and
#: `exclude_docs` keeps it out of the build) and `gui-skin-crt.png` (a CRT skin
#: is scanline noise, which PNG cannot compress and a palette cannot survive —
#: the manual links its 77 KB WebP). A cap on storage would have to grant both
#: an exemption and would then be a list of exemptions.
BIGGEST_LINKED_KB = 600


def _files(rel):
    d = os.path.join(ROOT, rel)
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, n) for n in os.listdir(d)
            if os.path.isfile(os.path.join(d, n))]


def test_no_published_directory_is_over_its_weight_budget():
    over = []
    for rel, ceiling in BUDGET_KB.items():
        kb = sum(os.path.getsize(p) for p in _files(rel)) // 1024
        if kb > ceiling:
            over.append('%s is %d KB, budget %d' % (rel, kb, ceiling))
    assert not over, ('run `py tools/optimize_images.py`, or raise the budget '
                      'deliberately: %s' % over)


def test_nothing_published_is_a_gif():
    """GIF has no interframe compression worth the name. The one animation
    either site publishes was 5770 KB as a 96-colour GIF and is 538 KB as
    animated WebP — same frames, same duration, more colours."""
    bad = []
    for rel in ('docs', os.path.join('docs', 'img'), os.path.join('www', 'public'),
                os.path.join('www', 'public', 'img')):
        bad += [os.path.relpath(p, ROOT) for p in _files(rel) if p.lower().endswith('.gif')]
    assert not bad, 'published as GIF: %s' % bad


def _linked_images():
    """Every image file a reader is actually served, resolved to a real path.

    Two sources, because they are served by two different things: the manual's
    markdown (MkDocs copies the file and links it) and README.md (GitHub and
    PyPI fetch it from raw.githubusercontent, uncompressed and unresized)."""
    out = set()
    for name in sorted(os.listdir(DOCS)):
        if not name.endswith('.md'):
            continue
        with open(os.path.join(DOCS, name), encoding='utf-8') as f:
            for src in re.findall(r'!\[[^\]]*\]\(([^)\s]+)\)', f.read()):
                if '://' not in src:
                    out.add(os.path.join(DOCS, src.replace('/', os.sep)))
    with open(os.path.join(ROOT, 'README.md'), encoding='utf-8') as f:
        for src in re.findall(r'src="([^"]+)"', f.read()):
            if '/main/' in src and 'shields.io' not in src:
                out.add(os.path.join(ROOT, src.split('/main/', 1)[1].replace('/', os.sep)))
    return {p for p in out if os.path.isfile(p)}


def test_no_image_a_reader_downloads_is_enormous():
    big = ['%s is %d KB' % (os.path.relpath(p, ROOT), os.path.getsize(p) // 1024)
           for p in sorted(_linked_images())
           if os.path.getsize(p) // 1024 > BIGGEST_LINKED_KB]
    assert not big, 'over %d KB each: %s' % (BIGGEST_LINKED_KB, big)


def test_every_image_the_readme_shows_exists():
    """The README embeds by absolute raw.githubusercontent URL so PyPI renders
    it, which means a renamed or deleted file is a broken image on the project's
    front page and on its package page, and nothing local notices."""
    missing = []
    with open(os.path.join(ROOT, 'README.md'), encoding='utf-8') as f:
        for src in re.findall(r'src="([^"]+)"', f.read()):
            if '/main/' not in src or 'shields.io' in src:
                continue
            rel = src.split('/main/', 1)[1]
            if not os.path.isfile(os.path.join(ROOT, rel.replace('/', os.sep))):
                missing.append(rel)
    assert not missing, 'README embeds files that are not in the repo: %s' % missing


def test_every_image_a_docs_page_links_exists_and_is_the_light_one():
    """MkDocs copies a linked file and serves it raw — there is no optimizer in
    front of it, so the markdown naming the PNG while a WebP sits beside it is a
    page that is four times heavier for nothing. `--strict` does not see this:
    an image link is not a page link."""
    missing, heavy = [], []
    for name in sorted(os.listdir(DOCS)):
        if not name.endswith('.md'):
            continue
        with open(os.path.join(DOCS, name), encoding='utf-8') as f:
            text = f.read()
        for src in re.findall(r'!\[[^\]]*\]\(([^)\s]+)\)', text):
            if '://' in src:
                continue
            path = os.path.join(DOCS, src.replace('/', os.sep))
            if not os.path.isfile(path):
                missing.append('%s -> %s' % (name, src))
                continue
            webp = path[:-4] + '.webp'
            if path.endswith('.png') and os.path.isfile(webp) \
                    and os.path.getsize(webp) < os.path.getsize(path):
                heavy.append('%s links %s, but %s is smaller'
                             % (name, src, os.path.basename(webp)))
    assert not missing, 'broken image links: %s' % missing
    assert not heavy, heavy


def test_every_image_a_docs_page_links_declares_its_size():
    """An image with no width/height reserves no space, so the text under it
    jumps when the image lands — Cumulative Layout Shift, and the manual is all
    text with a screenshot in the middle of it."""
    bad = []
    for name in sorted(os.listdir(DOCS)):
        if not name.endswith('.md'):
            continue
        with open(os.path.join(DOCS, name), encoding='utf-8') as f:
            text = f.read()
        for line in text.splitlines():
            m = re.match(r'!\[[^\]]*\]\([^)\s]+\)(.*)', line.strip())
            if not m:
                continue
            attrs = m.group(1)
            if 'width=' not in attrs or 'height=' not in attrs:
                bad.append('%s: %s' % (name, line.strip()))
    assert not bad, 'no intrinsic size declared: %s' % bad
