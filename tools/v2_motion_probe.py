"""Desktop motion checks. Run on port 8818 through testlock; no network beyond localhost.
Core breath deliberately fails acceptance: desktop core remains baked raster art.
"""
import os
from playwright.sync_api import sync_playwright

BASE = os.environ.get('BASE', 'http://127.0.0.1:8818').rstrip('/')
OUT = os.environ.get('OUT', '.')
failures = []


def check(ok, label):
    print(('ok   ' if ok else 'FAIL ') + label, flush=True)
    if not ok:
        failures.append(label)


def send(pg, text):
    pg.fill('#chat-input', text)
    pg.press('#chat-input', 'Enter')
    pg.wait_for_timeout(1000)


with sync_playwright() as p:
    browser = p.chromium.launch()
    facts = []
    for mode in ['full', 'reduced', 'quiet']:
        ctx = browser.new_context(viewport={'width': 1440, 'height': 900},
                                  reduced_motion='reduce' if mode == 'reduced' else 'no-preference')
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: check(False, 'pageerror: ' + str(e)))
        pg.goto(BASE + '/index.html#/now', wait_until='load')
        pg.bring_to_front()
        if mode == 'quiet':
            pg.evaluate("localStorage.setItem('archeus.v2.motion', 'quiet')")
            pg.reload(wait_until='load')
        pg.wait_for_timeout(900)
        send(pg, 'Start a project called Atlas')
        send(pg, 'Create a mission called "Draft the brief" in Atlas')
        pg.locator('#chat-input').focus()
        # Focus holds arrival position; incoming obligation still updates facts immediately.
        pg.locator('.chat-feed [data-card="start"]').last.click()
        pg.wait_for_timeout(20)
        if mode != 'full':
            check(pg.evaluate('document.getAnimations().length') == 0, mode + ': zero animations during record arrival')
        pg.wait_for_timeout(900)
        facts.append(pg.locator('#rec-list').inner_text())
        check('Needs you' in facts[-1], mode + ': obligation fact visible in reserved slot')
        check(pg.evaluate('document.getAnimations().length') == 0, mode + ': zero animations at rest')
        pg.evaluate("window.dispatchEvent(new Event('blur'))")
        check(pg.evaluate('document.getAnimations().length') == 0, mode + ': blur parks animations')
        pg.evaluate("window.dispatchEvent(new Event('focus')); window.ArchFixture.reconnect()")
        check(pg.evaluate('document.getAnimations().length') == 0, mode + ': reconnect has no choreography')
        pg.screenshot(path=os.path.join(OUT, 'motion-' + mode + '.png'))
        ctx.close()
    check(facts[0] == facts[1] == facts[2], 'full / R / Q preserve identical creation and obligation text')
    check(False, 'BLOCKED: 6000 ms core-only breath needs separable desktop core geometry; baked art is static')
    browser.close()

raise SystemExit(1 if failures else 0)
