"""Mutation check for the LV2-0 lab gates: each probe must FAIL on the defect it exists to catch.
A gate nobody has watched fail is not a gate. Prototype tooling.   py mutate_gates.py
"""
import re

from serve import serve
from playwright.sync_api import sync_playwright
from ia_probe import MACHINE
from light_probe import PROV_JS

DUP_JS = '''() => { const seen = {}; document.querySelectorAll('.b-row.decide').forEach(e => { seen[e.dataset.id] = (seen[e.dataset.id] || 0) + 1; });
  return Object.values(seen).filter(n => n > 1).length; }'''
VIS_JS = '''() => { const m = document.querySelector('main'); const c = m.cloneNode(true);
  c.querySelectorAll('details:not([open]) > :not(summary), .raw, .sr').forEach(e => e.remove()); return c.innerText; }'''


def machine(txt):
    return sorted({lbl for rx, lbl in MACHINE if re.search(rx, txt)})


def main():
    base, srv = serve()
    rows = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        # 1. provenance: an unsourced mark must be counted
        pg.goto(base + 'light.html?r=lanes')
        clean = pg.evaluate(PROV_JS)['without_record']
        pg.evaluate('''() => document.querySelector('svg.daylight').insertAdjacentHTML('beforeend', '<circle cx="5" cy="5" r="3"/>')''')
        mut = pg.evaluate(PROV_JS)['without_record']
        rows.append(('provenance: unsourced mark', clean, mut, clean == 0 and mut == 1))
        pg.goto(base + 'light.html?r=hybrid')
        pg.evaluate('''() => { const l = document.querySelector('.daylight li'); l.dataset.src = 'mission:m-nope seq:9999'; }''')
        mut2 = pg.evaluate(PROV_JS)['without_record']
        rows.append(('provenance: mark citing an unknown record', 0, mut2, mut2 >= 1))
        # 2. machine language at the first two depths
        pg.goto(base + 'ia.html?v=b#now')
        clean = machine(pg.evaluate(VIS_JS))
        pg.evaluate('''() => document.querySelector('.sub').append(' expires 2026-10-06T09:54:11.148Z')''')
        mut = machine(pg.evaluate(VIS_JS))
        pg.goto(base + 'ia.html?v=b#d/m-91d2')
        raw_hidden = machine(pg.evaluate(VIS_JS))  # the policy record exists, inside a closed <details>
        rows.append(('machine language: ISO on Now', clean, mut, clean == [] and 'ISO timestamp' in mut))
        rows.append(('machine language: raw record at depth 3 is not counted', '-', raw_hidden, raw_hidden == []))
        # 3. the same decision twice on one screen
        pg.goto(base + 'ia.html?v=b#now')
        clean = pg.evaluate(DUP_JS)
        pg.evaluate('''() => { const r = document.querySelector('.b-row.decide'); r.parentElement.append(r.cloneNode(true)); }''')
        mut = pg.evaluate(DUP_JS)
        rows.append(('duplicate decision', clean, mut, clean == 0 and mut == 1))
        b.close()
    for r in rows:
        print('%-58s clean=%-6s mutant=%-28s %s' % (r[0], r[1], r[2], 'KILLED' if r[3] else 'SURVIVED'))
    return 0 if all(r[3] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
