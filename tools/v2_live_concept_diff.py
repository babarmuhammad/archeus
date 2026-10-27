"""V2 Live concept diff: screenshot an app route and write a side-by-side PNG (concept left, app right, same size) so the build can be judged against the approved concept.

  py -I tools\\v2_live_concept_diff.py now                      # presets: now, mission, calm, phone, now-2000, now-light, calm-light, mission-phone
  py -I tools\\v2_live_concept_diff.py --hash work/m-date --concept 03-mission.png --size 1440x900 --theme dark --name mine
Outputs go to .pv20-out\\diff\\<name>.png (side by side) and <name>_app.png (the app alone). The concept is scaled to fit the same box and centred on the ground colour.
Serves clients/v2-live on its own port (default 8895) and stops only that server.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2_live_layout_probe as P
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = P.ROOT
CONCEPTS = os.path.join(ROOT, 'docs', 'design', 'v2-concepts')
OUT = os.path.join(ROOT, '.pv20-out', 'diff')
PRESETS = {
    'now': dict(hash='now', concept='02-now.png', size='1440x900', theme='dark'),
    'now-2000': dict(hash='now', concept='02-now.png', size='2000x930', theme='dark'),
    'now-light': dict(hash='now', concept='08-day-attention.png', size='1440x900', theme='light'),
    'calm': dict(hash='now', concept='07-calm.png', size='1440x900', theme='dark', extra='&story=calm'),
    'calm-light': dict(hash='now', concept='07-calm.png', size='1440x900', theme='light', extra='&story=calm'),
    'mission': dict(hash='work/m-date', concept='03-mission.png', size='1440x900', theme='dark'),
    'mission-light': dict(hash='work/m-date', concept='08-day-attention.png', size='1440x900', theme='light'),
    'phone': dict(hash='now', concept='10-phone-needs-you.png', size='390x844', theme='dark'),
    'mission-phone': dict(hash='work/m-date', concept='12-phone-mission.png', size='390x844', theme='dark'),
    'map': dict(hash='map', concept='02-now.png', size='1440x900', theme='dark'),
}
GROUND = {'dark': (9, 8, 12), 'light': (253, 252, 248)}


def contain(img, w, h, ground):
    s = min(w / img.width, h / img.height)
    img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    canvas = Image.new('RGB', (w, h), ground)
    canvas.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('preset', nargs='?')
    ap.add_argument('--hash'); ap.add_argument('--concept'); ap.add_argument('--size'); ap.add_argument('--theme'); ap.add_argument('--extra', default='')
    ap.add_argument('--name'); ap.add_argument('--port', type=int, default=8895); ap.add_argument('--wait', type=int, default=500)
    a = ap.parse_args()
    cfg = dict(PRESETS.get(a.preset or '', {}))
    for k in ('hash', 'concept', 'size', 'theme', 'extra'):
        if getattr(a, k):
            cfg[k] = getattr(a, k)
    cfg.setdefault('extra', ''); cfg.setdefault('theme', 'dark'); cfg.setdefault('size', '1440x900')
    name = a.name or a.preset or 'diff'
    w, h = map(int, cfg['size'].split('x'))
    os.makedirs(OUT, exist_ok=True)
    srv = P.start_server(a.port)
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            ctx = br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=1)
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
            pg.goto('http://127.0.0.1:%d/index.html?sim=paused&motion=reduced&theme=%s&lang=en%s#/%s' % (a.port, cfg['theme'], cfg['extra'], cfg['hash']), wait_until='load')
            pg.wait_for_timeout(a.wait)
            app_png = os.path.join(OUT, name + '_app.png')
            pg.screenshot(path=app_png)
            br.close()
    finally:
        srv.terminate()
    ground = GROUND[cfg['theme']]
    left = contain(Image.open(os.path.join(CONCEPTS, cfg['concept'])).convert('RGB'), w, h, ground)
    right = Image.open(app_png).convert('RGB')
    both = Image.new('RGB', (w * 2 + 6, h), (200, 60, 60))
    both.paste(left, (0, 0)); both.paste(right, (w + 6, 0))
    out = os.path.join(OUT, name + '.png')
    both.save(out)
    print(out)
    if errs:
        print('console/page errors:', errs[:5])


if __name__ == '__main__':
    main()
