"""LV2-1 W0 (D-6): re-run PR-4's clipping check for the LE8 typography arm.

LE8's three deviations from A §F are tested on PR-4's OWN lab and metric, unmodified: the page is
loaded at PR-4's accepted `type=v2`, then LE8's values are injected as a stylesheet, so the only
difference from the accepted record is the arm itself:
    display tracking -0.012 em (§F -0.005 em) · phone display 24/30 (§F 30/36) · durations in the
    text face (§F Cascadia Mono).
Chromium: every PR-4 surface x view x environment, v2 and le8 side by side (PR-4 ran 288 such
combinations across three treatments; this is the same 96 per treatment). Qt: PR-4's three
agreement surfaces (now, mission, dense) on desktop and phone, through PR-4's own qt_eval.py.
Prototype tooling.   py prototypes/v2-later/tools/pr4_le8.py [--no-qt]
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
U0T = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'v2-u0', 'tools')
sys.path.insert(0, U0T)
import pr4  # noqa: E402  (PR-4's own page builder, environments and surfaces)
from serve import results  # noqa: E402

LE8_CSS = (":root[data-type] { --track: -0.012em; }"
           " html[data-type][data-view='phone'] { --t-display: 600 1.5rem/1.875rem var(--f-display); }"
           " html[data-type] .row .meta { font-family: var(--f-text); font-variant-numeric: tabular-nums; }")
INJECT = "(() => { const s = document.createElement('style'); s.textContent = %s; document.head.append(s); return true; })()" % json.dumps(LE8_CSS)
KEYS = ('lead_size', 'lead_lines', 'lead_h', 'first_row_top', 'rows_above_fold', 'scroll_px', 'row_titles_truncated')


def chromium():
    from playwright.sync_api import sync_playwright
    base, srv = pr4.serve()
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for view in ('desktop', 'phone'):
            for env in pr4.ENVS:
                for s in pr4.SURFACES:
                    row = {'view': view, 'env': env, 'surface': s}
                    for arm in ('v2', 'le8'):
                        pg = pr4.page_for(b, base, 'type=v2&surface=%s' % s, view, env)
                        if arm == 'le8':
                            pg.evaluate(INJECT)
                            pg.wait_for_timeout(80)
                        m = pg.evaluate('TYPEM()')
                        row[arm] = {k: m[k] for k in KEYS + ('clipped',)}
                        pg.context.close()
                    out.append(row)
        b.close()
    srv.shutdown()
    return out


def qt():
    res = {}
    for view, size in (('desktop', '1440x900'), ('phone', '390x844')):
        for s in ('now', 'mission', 'dense'):
            expr = "(() => { %s; return JSON.stringify(TYPEM()); })()" % INJECT[:-3].replace('(() => { ', '', 1).replace('; return true; }', '')
            dst = results('lv21', 'pr4-le8', 'qt-le8-%s-%s.json' % (view, s))
            subprocess.run([sys.executable, os.path.join(U0T, 'qt_eval.py'), 'pr4-type.html?clean=1&type=v2&view=%s&surface=%s' % (view, s), expr, dst, '--size', size],
                           check=True, timeout=120)
            r = json.load(open(dst, encoding='utf-8'))
            res['%s/%s' % (view, s)] = json.loads(r) if isinstance(r, str) else r
    return res


def main():
    rows = chromium()
    clipped = {arm: sum(len(r[arm]['clipped']) for r in rows) for arm in ('v2', 'le8')}
    diffs = [dict(view=r['view'], env=r['env'], surface=r['surface'], **{k: (r['v2'][k], r['le8'][k]) for k in KEYS if r['v2'][k] != r['le8'][k]})
             for r in rows if any(r['v2'][k] != r['le8'][k] for k in KEYS)]
    R = {'combinations_per_arm': len(rows), 'clipped_total': clipped, 'differences_v2_to_le8': diffs}
    if '--no-qt' not in sys.argv:
        R['qt'] = qt()
    json.dump(R, open(results('lv21', 'pr4-le8', 'pr4_le8.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in R.items() if k != 'differences_v2_to_le8'}, indent=1, ensure_ascii=False)[:3000])
    print('differences:', len(diffs))
    for d in diffs[:40]:
        print(' ', d)


if __name__ == '__main__':
    main()
