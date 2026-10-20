"""LV2-X.2: the light along the mission line, measured. Prototype tooling.
  py prototypes/v2-later/tools/lvx_motion.py
Writes results/lvx/motion/*.png (a filmstrip of the approve -> run travel) and results/lvx/motion/check.txt.
Fails on: a property other than transform/opacity animated; anything still animating after the travel;
any animation under reduced motion; a travel while the emergency stop is engaged; a peripheral line
animating longer than 160 ms; a travel longer than 600 + 240 ms.
"""
import json
import os

from playwright.sync_api import sync_playwright
from serve import serve, results

FRAMES = [0, 60, 150, 300, 450, 560, 620, 700, 840]
ANIMS = r"""() => document.getAnimations().map(a => ({
  props: [...new Set(a.effect.getKeyframes().flatMap(k => Object.keys(k)).filter(k => !['offset', 'easing', 'composite', 'computedOffset'].includes(k)))],
  dur: a.effect.getTiming().duration, iter: a.effect.getTiming().iterations, state: a.playState }))"""


def main():
    out = results('lvx', 'motion', 'x')[:-2]
    os.makedirs(out, exist_ok=True)
    base, _srv = serve()
    base = base.replace('/lab/', '/lvx/') + 'index.html?d=e2&'
    lines, bad = [], 0

    def verdict(name, ok, detail):
        nonlocal bad
        bad += not ok
        lines.append('%-34s %s  %s' % (name, 'ok  ' if ok else 'FAIL', detail))

    with sync_playwright() as p:
        b = p.chromium.launch()
        c = b.new_context(viewport={'width': 1440, 'height': 900}, color_scheme='dark')
        pg = c.new_page()
        for t in FRAMES:
            pg.goto(base + 'v=mission&id=m-91d2&did=approve&shot=1&t=%d' % t)
            pg.wait_for_timeout(120)
            box = pg.locator('.x-linecard').bounding_box()
            pg.screenshot(path=os.path.join(out, 'travel_%03d.png' % t), clip={'x': box['x'] + 360, 'y': box['y'], 'width': 560, 'height': box['height']})
        # live: what runs, and what is left once the light has landed
        pg.goto(base + 'v=mission&id=m-91d2&did=approve')
        pg.wait_for_timeout(50)
        a = pg.evaluate(ANIMS)
        props = sorted({x for an in a for x in an['props']})
        verdict('travel: properties', set(props) <= {'transform', 'opacity'}, props)
        verdict('travel: duration', max(x['dur'] for x in a) <= 840 and len(a) == 4, '%d animations, longest %d ms' % (len(a), max(x['dur'] for x in a)))
        pg.wait_for_timeout(1100)
        live = [x for x in pg.evaluate(ANIMS) if x['state'] == 'running']
        verdict('travel: still after it lands', not live, '%d running after 1.15 s' % len(live))
        # the same moment with the stop engaged: no light shares the stage with the stop
        pg.goto(base + 'v=mission&id=m-91d2&did=approve&s=stopped')
        pg.wait_for_timeout(50)
        verdict('stopped: no travel', not pg.evaluate(ANIMS), '%d animations' % len(pg.evaluate(ANIMS)))
        # the periphery: a row's segment fills in one quick step, no head
        pg.goto(base + 'v=missions&demo=row')
        pg.wait_for_timeout(30)
        r = pg.evaluate(ANIMS)
        verdict('row: progress only', bool(r) and all(x['dur'] <= 160 and x['props'] == ['transform'] for x in r), json.dumps(r))
        # an idle overview and a running mission page: nothing moves at rest
        for q in ('v=home', 'v=mission&id=m-4c1e', 'v=missions&corpus=x2', 'v=home&s=idle'):
            pg.goto(base + q)
            pg.wait_for_timeout(300)
            verdict('at rest: ' + q, not pg.evaluate(ANIMS), '%d animations' % len(pg.evaluate(ANIMS)))
        c.close()
        rc = b.new_context(viewport={'width': 1440, 'height': 900}, color_scheme='dark', reduced_motion='reduce')
        pg = rc.new_page()
        pg.goto(base + 'v=mission&id=m-91d2&did=approve')
        pg.wait_for_timeout(100)
        now = pg.evaluate("() => document.querySelector('.x-line-full .x-nd[data-i=\"3\"]').className")
        verdict('reduced motion: end state, no motion', not pg.evaluate(ANIMS) and 'now' in now, 'Run node: %s' % now)
        pg.goto(base + 'v=mission&id=m-c3e9&ask=explain')
        pg.wait_for_timeout(100)
        whole = pg.evaluate("() => document.querySelector('.x-typed').textContent.length")
        verdict('reduced motion: answer whole', whole > 100, '%d characters at once' % whole)
        b.close()
    lines.append('FAILURES: %s' % (bad or 'none'))
    open(os.path.join(out, 'check.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
