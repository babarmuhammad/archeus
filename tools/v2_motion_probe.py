"""Desktop motion checks. Run on port 8818 through testlock; no network beyond localhost.
The core breath runs on art/desktop-now-core.webp, a layer cut from the approved base art.
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


CORE = "document.querySelector('.desk-core')"
OTHERS = "document.getAnimations().filter(a => a.effect.target !== %s).length" % CORE
CORE_ANIMS = "%s.getAnimations().length" % CORE
SCALE = "new DOMMatrix(getComputedStyle(%s).transform).a" % CORE


def send(pg, text):
    pg.fill('#chat-input', text)
    pg.press('#chat-input', 'Enter')
    pg.wait_for_timeout(1000)


def core_check(pg, mode):
    if mode != 'full':
        check(pg.evaluate(CORE_ANIMS) == 0 and pg.evaluate(SCALE) == 1, mode + ': core is static at scale 1')
        check(pg.evaluate(CORE + '.dataset.core') == 'running-static', mode + ': static running mark state')
        return
    pg.evaluate("window.dispatchEvent(new Event('focus'))")
    check(pg.evaluate(CORE_ANIMS) == 1, 'full: one core animation while running is confirmed')
    t = pg.evaluate("(() => { const e = %s.getAnimations()[0].effect; return [e.getTiming().duration, e.getTiming().iterations, e.getKeyframes().map(k => [k.transform, k.computedOffset, k.easing])]; })()" % CORE)
    check(t[0] == 6000 and t[1] in (None, float('inf')), 'full: 6000 ms cycle, repeating')
    check([k[0] for k in t[2]] == ['scale(1)', 'scale(1.018)', 'scale(1)'] and [k[1] for k in t[2]] == [0, 0.5, 1] and t[2][0][2] == 'ease-in-out' and t[2][1][2] == 'ease-in-out', 'full: 1 to 1.018 to 1, 3000 out and 3000 in, ease-in-out')
    check(pg.evaluate("(() => { const k = %s.getAnimations()[0].effect.getKeyframes(); return k.every(f => f.opacity === undefined || f.opacity === 1 || f.opacity === '') && k.every(f => f.filter === undefined && f.color === undefined); })()" % CORE), 'full: no colour, filter or opacity keyframe')
    samples = []
    for _ in range(14):
        samples.append(pg.evaluate(SCALE))
        pg.wait_for_timeout(450)
    check(min(samples) >= 1 - 1e-9 and max(samples) <= 1.018 + 1e-9 and max(samples) > 1.012, 'full: scale stays in [1, 1.018], peak seen (max %.4f)' % max(samples))
    check(pg.evaluate("getComputedStyle(%s).transformOrigin" % CORE) == '640px 317px', 'full: fixed centre')
    pg.locator('#chat-input').focus()
    pg.keyboard.type('hello')
    check(pg.evaluate(CORE_ANIMS) == 1, 'full: typing does not stop the breath')
    pg.evaluate("document.dispatchEvent(new WheelEvent('wheel', {bubbles: true}))")
    check(pg.evaluate(CORE_ANIMS) == 0, 'full: scroll parks the breath at once')
    pg.wait_for_timeout(500)
    check(pg.evaluate(CORE_ANIMS) == 1, 'full: breath resumes after scroll')
    for fact in ['stale', 'unknown', 'none']:
        pg.evaluate("window.ArchFixture.execFact('%s')" % fact)
        check(pg.evaluate(CORE_ANIMS) == 0 and pg.evaluate(SCALE) == 1 and pg.evaluate(CORE + '.dataset.core') == 'idle', 'full: ' + fact + ' stops the breath at once, core back at scale 1')
    pg.evaluate("window.ArchFixture.execFact('fresh')")
    check(pg.evaluate(CORE_ANIMS) == 1, 'full: fresh running fact restarts the breath')


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
            check(pg.evaluate(OTHERS) == 0, mode + ': zero other animations during record arrival')
        pg.wait_for_timeout(900)
        facts.append(pg.locator('#rec-list').inner_text())
        check('Needs you' in facts[-1], mode + ': obligation fact visible in reserved slot')
        check(pg.evaluate(OTHERS) == 0, mode + ': zero other animations at rest')
        pg.evaluate("window.dispatchEvent(new Event('blur'))")
        check(pg.evaluate(OTHERS) == 0, mode + ': blur parks animations')
        pg.evaluate("window.dispatchEvent(new Event('focus')); window.ArchFixture.reconnect()")
        check(pg.evaluate(OTHERS) == 0, mode + ': reconnect has no choreography')
        core_check(pg, mode)
        pg.screenshot(path=os.path.join(OUT, 'motion-' + mode + '.png'))
        ctx.close()
    check(facts[0] == facts[1] == facts[2], 'full / R / Q preserve identical creation and obligation text')
    browser.close()

raise SystemExit(1 if failures else 0)
