"""Load a lab page headless, report console errors and run one or more scenarios.
Prototype tooling.  py prototypes/v2-later/tools/smoke.py motion.html press reveal ...
"""
import json
import sys

from serve import serve
from playwright.sync_api import sync_playwright

page_name, scen = sys.argv[1], sys.argv[2:]
base, srv = serve()
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 1440, 'height': 900})
    errs = []
    pg.on('console', lambda m: m.type == 'error' and errs.append(m.text))
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(base + page_name + '?clean=1')
    pg.wait_for_timeout(300)
    for s in scen:
        try:
            pg.evaluate('s => window.SCENARIOS[s]()', s)
            print(s, 'ok')
        except Exception as e:  # noqa: BLE001
            print(s, 'FAIL', str(e)[:300])
    print('extra', json.dumps(pg.evaluate('window.LAB_EXTRA ? LAB_EXTRA() : null'))[:1500])
    print('errors', errs)
    b.close()
