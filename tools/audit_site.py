"""Load every published page on a phone, a tablet and a desktop, and fail if
anything sticks out of the viewport or any line of prose runs too long.

    py -m mkdocs build --strict && py tools/audit_site.py
    py tools/audit_site.py --www          # also the marketing site (needs a build)

"Mobile responsive" is the kind of claim that is made by looking at two pages and
is wrong on the third. This measures it: every page of the manual at 390x844 —
the iPhone 14/15 viewport, and the narrowest common phone — reporting anything
whose box extends past the viewport, plus the one signal that covers everything
at once, `documentElement.scrollWidth > innerWidth`.

A page that scrolls sideways on a phone is not a cosmetic problem. It is a Core
Web Vitals input (horizontal overflow is what INP and CLS measure against), it is
what "mobile usability" means in Search Console, and the fix is nearly always one
element: a code block, a wide table, or an image with an intrinsic width.

Intrinsic width is why this exists at the moment it does. The manual's images now
declare `width` and `height` so the browser can reserve their box and the page
does not reflow when they land — and a declared `width="1600"` is exactly the
shape that overflows a 390px viewport if the theme's `img { max-width: 100% }` is
not doing what it is assumed to be doing. Assumed, until something measures it.

Requires playwright + chromium (the same ones tools/smoke_gui.py uses):
    pip install playwright && playwright install chromium
"""

import http.server
import os
import socketserver
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')

#: iPhone 14/15 CSS pixels. Narrow enough to be the real constraint, wide enough
#: that a failure here is a failure everywhere.
VIEWPORT = {'width': 390, 'height': 844}

#: ...except that it is NOT a failure everywhere, which is how the site header
#: scrolled sideways from 768 to 895px for as long as this file has existed. A
#: phone gets the disclosure menu and a desktop has room for the full nav; the
#: tablet band is the only width where the whole bar is laid out inline in a
#: viewport too narrow for it, so it is the one width a 390px probe cannot see.
#: 768x1024 is the iPad portrait viewport and the `md` breakpoint exactly.
TABLET = {'width': 768, 'height': 1024}

#: Sub-pixel layout rounding puts a full-bleed element a hair over the viewport
#: on most pages. 2px is below anything a reader can see and above the noise.
SLOP = 2

#: The width the prose measure is judged at. Neither of the other two can see
#: it: a phone and a tablet column are narrow enough that any measure fits, and
#: the failure is a line that gets LONGER as the viewport does.
DESKTOP = {'width': 1440, 'height': 900}

#: The longest line of prose either site may set, in characters.
#:
#: Typographic practice is 45-75 for a single column and the frontend brief this
#: site was built to says under 80. This is not that number: it is a CEILING
#: over what the sites actually set, so a page that drifts past every other page
#: fails and a page merely at the site's own measure does not. What it caught on
#: its first run: `.spine-zigzag` set its copy column to 54rem — 100 characters,
#: on /support, /changelog, /contributing, /code-of-conduct and every blog post
#: — while the four other spine layouts held theirs between 44 and 52rem; and
#: `BlockView`'s paragraph had no cap at all, so on the legal pages it ran the
#: full max-w-4xl column at 102 characters UNDER a lead that stopped 114px short
#: of it. Two right edges in one column is the visible half of the same bug.
#:
#: mkdocs-material's own content column measures 93 here and is not ours to
#: argue with, which is what sets the number.
MAX_MEASURE_CH = 96

#: Prose shorter than this is a label, a caption or a stub; its width says
#: nothing about how the page reads.
MEASURE_MIN_CHARS = 160

#: Every paragraph and list item wider than the ceiling, measured with the
#: element's OWN font rather than an assumed advance — the two sites set
#: different faces at different sizes, and a 0.5em guess is out by a fifth.
#:
#: An element with block-level children is skipped: a `<li>` that contains a
#: whole section is a container whose width is a layout fact, not a measure.
MEASURE_JS = """
() => {
  const out = [];
  const cv = document.createElement('canvas').getContext('2d');
  const blocky = e => [...e.children].some(k => {
    const d = getComputedStyle(k).display;
    return d === 'block' || d === 'flex' || d === 'grid' || d === 'table' || d === 'list-item';
  });
  for (const el of document.querySelectorAll('main p, main li, article p, article li')) {
    const txt = (el.textContent || '').trim();
    if (txt.length < MIN_CHARS || blocky(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
    cv.font = cs.fontSize + ' ' + cs.fontFamily;
    const adv = cv.measureText('0').width || parseFloat(cs.fontSize) * 0.5;
    const ch = Math.round(r.width / adv);
    if (ch > MAX_CH) out.push({ch, w: Math.round(r.width),
      cls: (el.className && el.className.toString().slice(0, 44)) || el.tagName.toLowerCase(),
      text: txt.slice(0, 46)});
  }
  return {probed: document.querySelectorAll('main p, main li, article p, article li').length,
          items: out.slice(0, 4)};
}
""".replace('MIN_CHARS', str(MEASURE_MIN_CHARS)).replace('MAX_CH', str(MAX_MEASURE_CH))

#: A run that probes fewer paragraphs than this measured nothing and should say
#: so rather than printing "clean" — the lesson tools/smoke_gui.py carries.
MEASURE_FLOOR = 400

#: A site with fewer pages than this means the walk broke, not that the manual
#: shrank. Same floor discipline as tools/smoke_gui.py, which once printed
#: "FAILURES: none" while running zero checks.
PAGE_FLOOR = 25
#: The apex is 12 apex routes plus 7 blog posts.
WWW_PAGE_FLOOR = 15

#: Returns every element that sticks out, with enough of its markup to find it.
#: Runs in the page rather than over the HTML because overflow is a LAYOUT fact:
#: a 1600px image inside `max-width:100%` does not overflow and an 80-character
#: unbroken code line in a 320px column does.
OVERFLOW_JS = """
() => {
  const vw = document.documentElement.clientWidth;
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    // A hidden element's box is still measurable. The theme's "copied to
    // clipboard" dialog sits 11px past the right edge with opacity 0 until
    // something is copied, which is not a layout defect and is not something a
    // reader can ever see.
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
    // An element inside its own scroller is allowed to be wider than the
    // viewport — that is what the scroller is for. Walk up and skip it.
    let scrolled = false;
    for (let p = el.parentElement; p; p = p.parentElement) {
      const o = getComputedStyle(p).overflowX;
      if (o === 'auto' || o === 'scroll') { scrolled = true; break; }
    }
    if (scrolled) continue;
    // Only the RIGHT edge. An element parked off-screen to the left is the
    // normal resting state of a closed navigation drawer and of the search
    // overlay — on this theme that is six elements on every one of thirty
    // pages, which is 180 reports of nothing and a check nobody would read
    // twice. If an off-canvas element ever does make the document scrollable,
    // `scrollWidth > innerWidth` below says so, which is the fact that matters.
    if (r.right > vw + SLOP) {
      out.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className && el.className.toString().slice(0, 60)) || '',
        right: Math.round(r.right), left: Math.round(r.left), vw,
        text: (el.textContent || '').trim().slice(0, 50),
      });
    }
  }
  return {
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    items: out.slice(0, 6),
  };
}
""".replace('SLOP', str(SLOP))


def _serve(directory):
    """A static server on an ephemeral port, in a daemon thread."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=directory, **kw)

        def log_message(self, *a):
            pass

    httpd = socketserver.TCPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, 'http://127.0.0.1:%d' % httpd.server_address[1]


def _paths():
    """Every built page, as a URL path."""
    out = []
    for dirpath, _dirs, files in os.walk(SITE):
        if 'index.html' in files:
            rel = os.path.relpath(dirpath, SITE).replace(os.sep, '/')
            out.append('/' if rel == '.' else '/%s/' % rel)
    return sorted(out)


WWW = os.path.join(ROOT, 'www')


def _www_paths():
    """The apex site's routes, read from its own sitemap rather than listed here.

    Same reason tools/smoke_gui.py takes its page list from `NAV`: a hand-written
    copy of a route table falls a page behind and the gate goes on passing."""
    path = os.path.join(WWW, '.next', 'server', 'app', 'sitemap.xml.body')
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8') as f:
        body = f.read()
    import re
    out = []
    for loc in re.findall(r'<loc>([^<]+)</loc>', body):
        rest = loc.split('//', 1)[-1]
        out.append(rest[rest.index('/'):] if '/' in rest else '/')
    return sorted(set(out))


def _serve_www():
    """`next start` on an ephemeral port. Returns (stop, base) or (None, '')."""
    import socket
    import subprocess
    import time
    import urllib.error
    import urllib.request

    if not os.path.isdir(os.path.join(WWW, '.next')):
        print('www/.next is missing — run `npm run build` in www/ first')
        return None, ''
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(['npx', 'next', 'start', '-p', str(port)], cwd=WWW,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            shell=os.name == 'nt')
    base = 'http://127.0.0.1:%d' % port
    for _ in range(120):
        try:
            urllib.request.urlopen(base + '/', timeout=1).read(1)
            return proc, base
        except (urllib.error.URLError, OSError):
            if proc.poll() is not None:
                print('next start exited before it served anything')
                return None, ''
            time.sleep(0.5)
    proc.kill()
    print('next start did not come up in 60s')
    return None, ''


#: filled by _measure(); a run that probed fewer than MEASURE_FLOOR says so.
MEASURED = [0]


def _measure(page, base, paths, label, problems):
    """Does the prose stay inside a readable measure at desktop width?"""
    for path in paths:
        page.goto(base + path, wait_until='load')
        r = page.evaluate(MEASURE_JS)
        MEASURED[0] += r['probed']
        for it in r['items']:
            problems.append('%s%s  %dch (%dpx) <%s> %r'
                            % (label, path, it['ch'], it['w'], it['cls'], it['text']))


def _walk(page, base, paths, label, problems):
    for path in paths:
        page.goto(base + path, wait_until='load')
        r = page.evaluate(OVERFLOW_JS)
        where = label + path
        if r['scrollWidth'] > r['innerWidth'] + SLOP:
            problems.append('%s scrolls sideways: %dpx of content in a %dpx viewport'
                            % (where, r['scrollWidth'], r['innerWidth']))
        for it in r['items']:
            problems.append('%s  <%s class=%r> right=%d vw=%d  %r'
                            % (where, it['tag'], it['cls'], it['right'],
                               it['vw'], it['text']))


def main(argv):
    if not os.path.isdir(SITE):
        print('no site/ — run `py -m mkdocs build --strict` first')
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('needs playwright:\n  pip install playwright\n  playwright install chromium')
        return 1

    want_www = '--www' in argv
    paths = _paths()
    www_paths = _www_paths() if want_www else []
    httpd, base = _serve(SITE)
    www_proc = www_base = None
    if www_paths:
        www_proc, www_base = _serve_www()
        if not www_base:
            return 1

    problems = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=['--use-angle=swiftshader',
                                              '--enable-unsafe-swiftshader'])
            for vp, mobile in ((VIEWPORT, True), (TABLET, False)):
                page = browser.new_page(viewport=vp, device_scale_factor=2,
                                        is_mobile=mobile, has_touch=mobile)
                tag = '%dpx ' % vp['width']
                _walk(page, base, paths, tag + 'docs', problems)
                if www_base:
                    _walk(page, www_base, www_paths, tag + 'www', problems)
                page.close()
            page = browser.new_page(viewport=DESKTOP)
            _measure(page, base, paths, 'docs', problems)
            if www_base:
                _measure(page, www_base, www_paths, 'www', problems)
            page.close()
            browser.close()
    finally:
        httpd.shutdown()
        if www_proc:
            www_proc.kill()

    total = len(paths) + len(www_paths)
    print('checked %d pages at %dx%d and %dx%d, and %d paragraphs at %dpx'
          % (total, VIEWPORT['width'], VIEWPORT['height'],
             TABLET['width'], TABLET['height'], MEASURED[0], DESKTOP['width']))
    if len(paths) < PAGE_FLOOR:
        print('only %d docs pages found — the walk is broken, not the site' % len(paths))
        return 1
    if want_www and len(www_paths) < WWW_PAGE_FLOOR:
        print('only %d apex pages found — the sitemap is not being read' % len(www_paths))
        return 1
    if MEASURED[0] < MEASURE_FLOOR:
        print('only %d paragraphs measured — the probe found nothing to read'
              % MEASURED[0])
        return 1
    if problems:
        print('\n%d problems:' % len(problems))
        for prob in problems:
            print('  ' + prob)
        return 1
    print('nothing overflows, nothing runs past %dch' % MAX_MEASURE_CH)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
