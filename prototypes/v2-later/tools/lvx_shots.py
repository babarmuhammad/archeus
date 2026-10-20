"""LV2-X: capture every direction x state x device, and fail on dishonest or broken screens.
  py prototypes/v2-later/tools/lvx_shots.py [a b c]
Writes results/lvx/<d>_<dev>_<state>.png and results/lvx/check.txt. Prototype tooling.
"""
import os
import sys

from playwright.sync_api import sync_playwright
from serve import serve, results

STATES = [('home', 'v=home'), ('live', 'v=live&id=m-4c1e'), ('decide', 'v=decide&id=m-91d2'),
          ('mission', 'v=mission&id=m-c3e9'), ('primed', 'v=home&s=primed'), ('stopped', 'v=home&s=stopped'),
          ('idle', 'v=home&s=idle')]
DEVS = [('desk', 1440, 900), ('phone', 390, 844)]
# fixture facts Core does not record: they may never be rendered (LE-2 §2, DR-2/4/6, T-10)
FORBIDDEN = ['deploys to staging', 'changes 14 files', 'github.com', 'gitlab.com', 'Into main', 'into main',
             'pytest tests/', 'run 31 of 50', 'read 31 files']
CHECK_JS = r"""() => {
  const out = {};
  const txt = document.body.innerText;
  out.armed = /\barmed\b/i.test(txt.replace(/disarmed/gi, ''));
  out.unsourced = [...document.querySelectorAll('.f')].filter(e => !e.dataset.src || !e.dataset.k).length;
  out.facts = document.querySelectorAll('.f').length;
  out.overflowX = document.documentElement.scrollWidth - innerWidth;
  out.text = txt;
  const small = [];
  if (innerWidth < 600) for (const e of document.querySelectorAll('a[href],button')) {
    const r = e.getBoundingClientRect();
    if (r.width && r.height && r.top < innerHeight && (r.height < 44 && r.width < 44 || r.height < 32)) small.push((e.innerText || e.getAttribute('aria-label') || e.className).slice(0, 30) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
  }
  out.small = small;
  return out;
}"""


def main():
    dirs = sys.argv[1:] or ['a', 'b', 'c']
    out = results('lvx', 'x')[:-2]
    base, _srv = serve()
    base = base.replace('/lab/', '/lvx/')
    lines, bad = [], 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        for d in dirs:
            for dev, w, h in DEVS:
                ph = w < 600
                c = b.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2 if ph else 1,
                                  is_mobile=ph, has_touch=ph, color_scheme='dark')
                for name, q in STATES:
                    pg = c.new_page()
                    errs = []
                    pg.on('pageerror', lambda e, errs=errs: errs.append(str(e)))
                    pg.goto('%sindex.html?d=%s&%s&shot=1' % (base, d, q))
                    pg.wait_for_timeout(250)
                    stem = '%s_%s_%s' % (d, dev, name)
                    pg.screenshot(path=os.path.join(out, stem + '.png'))
                    if ph and name in ('home', 'decide', 'live'):
                        pg.screenshot(path=os.path.join(out, stem + '_full.png'), full_page=True)
                    r = pg.evaluate(CHECK_JS)
                    probs = []
                    if errs:
                        probs.append('errors %s' % errs)
                    if r['armed']:
                        probs.append('the word "armed" is on screen')
                    if r['unsourced']:
                        probs.append('%d facts without a source' % r['unsourced'])
                    if r['overflowX'] > 0:
                        probs.append('sideways overflow %dpx' % r['overflowX'])
                    for f in FORBIDDEN:
                        if f in r['text']:
                            probs.append('unrecorded fact rendered: %r' % f)
                    if r['small']:
                        probs.append('targets under 44px: %s' % r['small'][:4])
                    bad += bool(probs)
                    lines.append('%-22s facts %3d  %s' % (stem, r['facts'], '; '.join(probs) or 'ok'))
                    pg.close()
                c.close()
        b.close()
    lines.append('FAILURES: %s' % (bad or 'none'))
    open(os.path.join(out, 'check_%s.txt' % ''.join(dirs)), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
