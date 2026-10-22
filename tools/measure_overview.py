"""Overview 1:1 measure, the merge-round harness (kept in tools so the numbers can be rerun).
Renders the desktop Overview (1296 x 729, DPR 1) and the phone Overview (804 x 1373, DPR 2) in headless Chromium,
reduced motion, fonts awaited, and prints the mean absolute RGB difference against the concept rasters (0 to 255).
Run through a static server on BASE (default http://127.0.0.1:8765), e.g.
  BASE=http://127.0.0.1:8766 OUT=<dir> py -I tools/measure_overview.py <tag> desktop,phone
"""
import sys, json, io, os
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

import os
BASE = os.environ.get('BASE', 'http://127.0.0.1:8765') + '/index.html'
C = 'D:/hub-concepts-codex4/'
OUT = os.environ.get('OUT', '.') + '/'
SURF = {
  'desktop': dict(vw=1296, vh=755, dpr=1, hash='#/now', master=C + 'desktop-1-now-v2.png'),
  'phone':   dict(vw=402, vh=687, dpr=2, hash='#/now', master=C + 'phone-1-now-v2.png', phone=True),
  'replay':  dict(vw=1440, vh=836, dpr=1, hash='#/replay/m-date', master=C + 'replay-2-desktop-v2.png'),
  'terminal':dict(vw=1600, vh=900, dpr=1, hash='#/terminal', master=C + 'terminal-1-overview-v2.png'),
  'mission': dict(vw=1244, vh=855, dpr=1, hash='#/mission/m-date', master=C + 'refs/03-mission.webp'),
  'shared':  dict(vw=1382, vh=948, dpr=1, hash='#/shared', master=C + 'refs/06-shared.webp'),
}

def metric(a, b):
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    mean = d.mean()
    pct = (d.max(axis=2) > 24).mean() * 100
    return mean, pct

def run(names, tag):
    res = {}
    with sync_playwright() as p:
        br = p.chromium.launch()
        for n in names:
            s = SURF[n]
            ctx = br.new_context(viewport={'width': s['vw'], 'height': s['vh']}, device_scale_factor=s['dpr'], reduced_motion='reduce', color_scheme='dark')
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            pg.goto(BASE + s['hash'], wait_until='load')
            pg.evaluate('document.fonts.ready.then(() => true)')
            pg.wait_for_timeout(900)
            png = pg.screenshot(full_page=False)
            r = Image.open(io.BytesIO(png)).convert('RGB')
            m = Image.open(s['master'])
            if s['master'].endswith('.webp'):
                m = m.convert('RGB')
            else:
                m = m.convert('RGB')
            mw, mh = m.size
            if s['dpr'] == 2:
                r = r.crop((0, 0, mw, mh))
            else:
                r = r.crop((0, 0, mw, mh))
            a = np.asarray(r); b = np.asarray(m)
            mean, pct = metric(a, b)
            r.save(OUT + f'{tag}_{n}_render.png')
            res[n] = {'mean': round(float(mean), 2), 'pct24': round(float(pct), 2), 'size': [mw, mh], 'errors': errs[:3]}
            print(n, res[n], flush=True)
            ctx.close()
        br.close()
    json.dump(res, open(OUT + f'{tag}.json', 'w'), indent=1)

if __name__ == '__main__':
    run(sys.argv[2].split(','), sys.argv[1])
