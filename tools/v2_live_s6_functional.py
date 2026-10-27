"""Playwright functional run of the S6 finishing work: keyboard model and help, phone counters, the Now control strip with ask-first, toasts
(info leaves, error and action stay until Dismiss), the No Undo banner, the two-row phone spine, Italian. Run:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_s6_functional.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2_live_layout_probe as P
from playwright.sync_api import sync_playwright

ok = []; bad = []
def check(name, cond):
    (ok if cond else bad).append(name)
    print(('PASS ' if cond else 'FAIL ') + name)

port = P.free_port(); srv = P.start_server(port)
base = 'http://127.0.0.1:%d/index.html' % port
try:
    with sync_playwright() as p:
        br = p.chromium.launch()
        def page(w=1440, h=900, extra='', hash='now', clock=False):
            ctx = br.new_context(viewport={'width': w, 'height': h}); pg = ctx.new_page()
            errs = []; pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
            if clock: pg.clock.install()
            pg.goto(base + '?sim=paused&motion=reduced&notes=off&theme=dark' + extra + '#/' + hash, wait_until='load'); pg.wait_for_timeout(400)
            return ctx, pg, errs
        active = "() => { const e = document.activeElement; return e ? (e.dataset.key || '') : ''; }"
        # 1 keyboard in a list
        ctx, pg, errs = page(hash='work')
        pg.keyboard.press('j'); k1 = pg.evaluate(active)
        pg.keyboard.press('j'); k2 = pg.evaluate(active)
        pg.keyboard.press('k'); k3 = pg.evaluate(active)
        check('j moves to the first row, j to the next, k back', k1.startswith('m-') and k2.startswith('m-') and k1 != k2 and k3 == k1)
        ring = pg.evaluate("() => { const c = getComputedStyle(document.activeElement); return [c.outlineColor, parseFloat(c.outlineWidth), c.outlineStyle]; }")
        check('the focused row shows the dark focus colour #FFF3CF, 3 px', ring[0] == 'rgb(255, 243, 207)' and ring[1] >= 3 and ring[2] == 'solid')
        pg.keyboard.press('Space'); pg.wait_for_timeout(250)
        check('Space opens the focused row', pg.evaluate('location.hash') == '#/work/' + k1[2:])
        pg.keyboard.press('Escape'); pg.wait_for_timeout(250)
        check('Esc closes the details', pg.evaluate('location.hash') == '#/work')
        pg.evaluate("location.hash = '#/attention'"); pg.wait_for_timeout(300)
        pg.keyboard.press('j'); pg.keyboard.press('Enter'); pg.wait_for_timeout(300)
        check('Enter on a focused attention card does its primary action', pg.evaluate('location.hash').startswith('#/attention/'))
        # 2 help overlay
        pg.keyboard.press('Escape'); pg.wait_for_timeout(200); pg.keyboard.press('?'); pg.wait_for_timeout(200)
        check('? opens the shortcut list with a heading and the focus order', pg.locator('.helpbox h2').inner_text() == 'Keyboard shortcuts' and 'Focus order' in pg.locator('.helpbox').inner_text())
        check('help is a modal dialog and its button has the focus', pg.evaluate("() => document.querySelector('.helpbox').getAttribute('aria-modal') === 'true' && document.activeElement.closest('.helpbox') !== null"))
        pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
        check('Esc closes the help', pg.locator('.helpbox').count() == 0)
        pg.evaluate("location.hash = '#/chat'"); pg.wait_for_timeout(300); pg.click('input.cinput'); pg.keyboard.type('what?'); pg.wait_for_timeout(100)
        check('? typed in the chat box is text, not a shortcut', pg.locator('.helpbox').count() == 0 and pg.input_value('input.cinput') == 'what?')
        pg.evaluate("location.hash = '#/now'"); pg.wait_for_timeout(300); (pg.click('[data-tb="tools"]') if not pg.is_visible('[data-tb="theme"]') else None, pg.click('[data-tb="theme"]')); pg.wait_for_selector('.menu'); pg.keyboard.press('Escape'); pg.wait_for_timeout(100)
        check('Esc closes a toolbar menu', pg.locator('.menu').count() == 0)
        check('no page errors (keyboard)', not errs)
        ctx.close()
        # 3 Now: safety popover with ask-first, and toasts
        ctx, pg, errs = page(clock=True)
        op = lambda: None if pg.locator('.safety-pop').count() else pg.click('[data-key="safety"]')
        op()
        check('the safety popover carries the controls', pg.locator('.safety-pop [data-key="estop"]').count() == 1 and pg.locator('.safety-pop [data-key="pause-all"]').count() == 1 and pg.locator('.safety-pop [data-key="resume-all"]').count() == 1)
        op(); pg.click('.safety-pop [data-key="estop"]'); pg.wait_for_timeout(100)
        check('Emergency stop asks first and nothing is stopped yet', pg.locator('[data-key="estop-yes"]').count() == 1 and not pg.evaluate('window.v2live.sim.state.estop.engaged'))
        pg.keyboard.press('Escape'); pg.wait_for_timeout(100)
        check('Esc cancels the question', pg.locator('[data-key="estop-yes"]').count() == 0 and not pg.evaluate('window.v2live.sim.state.estop.engaged'))
        op(); pg.click('.safety-pop [data-key="resume-all"]'); pg.wait_for_timeout(150); op(); pg.click('.safety-pop [data-key="resume-all"]'); pg.wait_for_timeout(150)
        check('a refused action raises an error toast', pg.locator('.toast[data-kind="error"]').is_visible() and pg.locator('.toast').get_attribute('role') == 'alert')
        pg.clock.run_for(6000); pg.wait_for_timeout(100)
        check('the error toast stays after 6 s', pg.locator('.toast').is_visible())
        pg.click('.toast [data-key="toast-x"]'); pg.wait_for_timeout(100)
        check('Dismiss closes it', not pg.locator('.toast').is_visible())
        op(); pg.click('.safety-pop [data-key="pause-all"]'); pg.wait_for_timeout(150)
        check('an info toast shows without an action', pg.locator('.toast[data-kind="info"]').is_visible())
        pg.clock.run_for(5000); pg.wait_for_timeout(100)
        check('the info toast leaves after about 4.5 s', not pg.locator('.toast').is_visible())
        op(); pg.click('.safety-pop [data-key="estop"]'); pg.click('.safety-pop [data-key="estop-yes"]'); pg.wait_for_timeout(200)
        check('the stop engages after the second step', pg.evaluate('window.v2live.sim.state.estop.engaged'))
        pg.clock.run_for(8000); pg.wait_for_timeout(100)
        check('a toast with an action stays until Dismiss, and carries it', pg.locator('.toast').is_visible() and pg.locator('.toast a.btn').inner_text() == 'Open Settings')
        pg.click('.toast [data-key="toast-x"]')
        op(); pg.click('.safety-pop [data-key="rearm"]'); pg.click('.safety-pop [data-key="rearm-yes"]'); pg.wait_for_timeout(200)
        check('re-arm from Now releases it', not pg.evaluate('window.v2live.sim.state.estop.engaged'))
        op(); pg.click('.safety-pop [data-key="estop"]'); pg.click('.safety-pop [data-key="estop-yes"]'); pg.wait_for_timeout(200)
        check('the stop can be engaged again, also when nothing runs', pg.evaluate('window.v2live.sim.state.estop.engaged'))
        check('no page errors (Now)', not errs)
        ctx.close()
        # 4 phone: counters, No Undo, two-row spine
        ctx, pg, errs = page(390, 844)
        c = pg.evaluate("() => [...document.querySelectorAll('.counters .ctr')].map((e) => [e.querySelector('span').textContent, e.querySelector('b').textContent, e.getBoundingClientRect().height, e.getBoundingClientRect().width])")
        check('phone Now has the four counters needs you, running, stopped, verifying', [x[0] for x in c] == ['needs you', 'running', 'stopped', 'verifying'])
        want = pg.evaluate("() => { const s = window.v2live.sim, ms = Object.values(s.state.missions); return [s.attention().filter((i) => i.kind !== 'knowledge').length, s.liveWork().length, ms.filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED').length, ms.filter((m) => /VERIFYING/.test(m.state)).length]; }")
        check('the counters equal the simulation counts', [int(x[1]) for x in c] == want)
        check('every visible counter is at least 44 px', all(x[2] >= 44 and x[3] >= 44 for x in c if x[2] > 0))
        check('Stop stays in the bottom bar on the phone', pg.is_visible('.bottombar .bb-stop'))
        pg.evaluate("location.hash = '#/attention/a-1'"); pg.wait_for_timeout(400)
        check('the decision sheet has the No Undo banner', pg.locator('.noundo').count() == 1 and 'No Undo.' in pg.locator('.noundo').inner_text())
        pg.evaluate("location.hash = '#/work/m-date'"); pg.wait_for_timeout(400)
        ys = pg.evaluate("() => [...document.querySelectorAll('.inspector .spine-insp li')].map((e) => Math.round(e.getBoundingClientRect().top))")
        check('the phone mission spine is two rows of three', len(ys) == 6 and len(set(ys[:3])) == 1 and len(set(ys[3:])) == 1 and ys[3] > ys[0])
        check('the narrow spine shows the short names', 'Understand' in pg.locator('.inspector .spine-insp').inner_text())
        check('no page errors (phone)', not errs)
        ctx.close()
        # 5 Italian
        ctx, pg, errs = page(390, 844, extra='&lang=it')
        check('Italian counters', pg.evaluate("() => [...document.querySelectorAll('.counters .ctr span')].map((e) => e.textContent)") == ['ti servono', 'in corso', 'fermi', 'in verifica'])
        pg.keyboard.press('?'); pg.wait_for_timeout(200)
        check('Italian help', pg.locator('.helpbox h2').inner_text() == 'Scorciatoie da tastiera' and 'Ordine del focus' in pg.locator('.helpbox').inner_text())
        pg.keyboard.press('Escape')
        pg.evaluate("location.hash = '#/attention/a-1'"); pg.wait_for_timeout(400)
        check('Italian No Undo', 'Non si annulla.' in pg.locator('.noundo').inner_text())
        check('no page errors (it)', not errs)
        ctx.close()
        br.close()
finally:
    srv.terminate()
print('\n%d passed, %d failed' % (len(ok), len(bad)))
sys.exit(1 if bad else 0)
