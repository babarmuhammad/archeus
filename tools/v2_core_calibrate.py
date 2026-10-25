"""Re-balance the desktop core layer so Chromium composites it back to the original base art exactly.
Chromium premultiplies and truncates the RGBA core layer, so the plain composite of the two layers comes out about one level
darker than art/desktop-now-base.webp across the whole cut disc, which shows as a faint ring at its edge. This renders the two
layers at 1:1 in Chromium, compares with the original and nudges the nocore base (where the core layer is mostly transparent)
or the core colour (where it is mostly opaque) by the measured error, a few rounds, writing both files back lossless.
  py -I tools/v2_core_calibrate.py [art directory]        (default clients/v2-prototype/art)
Needs the original art/desktop-now-base.webp next to the two layers."""
import io
import os
import sys

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

ART = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'clients', 'v2-prototype', 'art')
rd = lambda n: Image.open(os.path.join(ART, n))
base = np.asarray(rd('desktop-now-base.webp').convert('RGB')).astype(int)
nc = np.asarray(rd('desktop-now-base-nocore.webp').convert('RGB')).astype(int)
core = np.asarray(rd('desktop-now-core.webp').convert('RGBA')).astype(int)
alpha = core[..., 3:] / 255
zone = (core[..., 3] > 0)[..., None] & np.ones(3, bool)


def enc(im, mode):
    b = io.BytesIO()
    Image.fromarray(im.astype('uint8'), mode).save(b, 'WEBP', lossless=True, quality=100, method=6, exact=True)
    return b.getvalue()


with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(viewport={'width': 1296, 'height': 729})
    files = {}
    pg.route('http://cal.test/*', lambda r: r.fulfill(body=files[r.request.url.rsplit('/', 1)[1].split('?')[0]], content_type='image/webp'))
    last = 1 << 30
    for rnd in range(10):
        files = {'nc.webp': enc(nc, 'RGB'), 'core.webp': enc(core, 'RGBA')}
        pg.set_content('<body style="margin:0;background:#000"><img src="http://cal.test/nc.webp?%d" style="position:absolute;left:0;top:0"><img src="http://cal.test/core.webp?%d" style="position:absolute;left:0;top:0">' % (rnd, rnd))
        pg.wait_for_function('[...document.images].every(i => i.complete)')
        got = np.asarray(Image.open(io.BytesIO(pg.screenshot())).convert('RGB')).astype(int)
        d = (base - got) * zone
        off = (d != 0).any(2).sum()
        print('round %d: error in the cut zone, max %d, pixels off %d' % (rnd, np.abs(d).max(), off))
        if not off or off >= last:
            break
        last = off
        step = np.where(d == 0, 0, np.sign(d) * np.maximum(1, np.round(np.abs(d) / np.maximum(np.where(alpha < 0.5, 1 - alpha, alpha), 0.05))))
        nc = np.clip(nc + np.where(alpha < 0.5, step, 0), 0, 255).astype(int)
        core[..., :3] = np.clip(core[..., :3] + np.where(alpha >= 0.5, step, 0), 0, 255).astype(int)
    br.close()
open(os.path.join(ART, 'desktop-now-base-nocore.webp'), 'wb').write(enc(nc, 'RGB'))
open(os.path.join(ART, 'desktop-now-core.webp'), 'wb').write(enc(core, 'RGBA'))
