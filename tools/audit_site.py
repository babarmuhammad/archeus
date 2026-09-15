"""Load every published page on a phone and fail if anything sticks out.

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

#: Sub-pixel layout rounding puts a full-bleed element a hair over the viewport
#: on most pages. 2px is below anything a reader can see and above the noise.
SLOP = 2

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
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=3,
                                    is_mobile=True, has_touch=True)
            _walk(page, base, paths, 'docs', problems)
            if www_base:
                _walk(page, www_base, www_paths, 'www', problems)
            browser.close()
    finally:
        httpd.shutdown()
        if www_proc:
            www_proc.kill()

    total = len(paths) + len(www_paths)
    print('checked %d pages at %dx%d' % (total, VIEWPORT['width'], VIEWPORT['height']))
    if len(paths) < PAGE_FLOOR:
        print('only %d docs pages found — the walk is broken, not the site' % len(paths))
        return 1
    if want_www and len(www_paths) < WWW_PAGE_FLOOR:
        print('only %d apex pages found — the sitemap is not being read' % len(www_paths))
        return 1
    if problems:
        print('\n%d problems:' % len(problems))
        for prob in problems:
            print('  ' + prob)
        return 1
    print('nothing overflows')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
