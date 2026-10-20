"""Screenshot lab pages. Prototype tooling.
  py shoot.py OUTDIR page.html?query@WxH[@full] ...
"""
import os
import sys

from serve import serve
from playwright.sync_api import sync_playwright

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
base, srv = serve()
with sync_playwright() as p:
    b = p.chromium.launch()
    for spec in sys.argv[2:]:
        parts = spec.split('@')
        url, size = parts[0], parts[1]
        full = len(parts) > 2 and parts[2] == 'full'
        w, h = map(int, size.split('x'))
        ph = w < 600
        c = b.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2 if ph else 1, is_mobile=ph, has_touch=ph)
        pg = c.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(base + url)
        pg.wait_for_timeout(500)
        name = url.replace('.html', '').replace('?', '_').replace('&', '_').replace('=', '-').replace('#', '_').replace('/', '-') + '_%dx%d' % (w, h)
        pg.screenshot(path=os.path.join(out, name + '.png'), full_page=full)
        print(name, 'height', pg.evaluate('document.documentElement.scrollHeight'), errs or '')
        c.close()
    b.close()
