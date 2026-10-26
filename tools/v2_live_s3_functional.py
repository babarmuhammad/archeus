"""Playwright functional run of the S3 interactions (breakers, hooks, tabs, pins, two-step decision, offline, usage, accounts, digest, Italian). Run: py D:\Archeus\.collab\testlock.py -- py -I tools\v2_live_s3_functional.py"""
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
        def page(w=1440, h=900, extra=''):
            ctx = br.new_context(viewport={'width': w, 'height': h}); pg = ctx.new_page()
            errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
            pg.goto(base + '?sim=paused&motion=reduced&notes=off' + extra, wait_until='load'); pg.wait_for_timeout(300)
            return ctx, pg, errs
        T = lambda pg, s: pg.inner_text('body')
        # 1 breakers
        ctx, pg, errs = page(); pg.evaluate("location.hash='#/security'"); pg.wait_for_timeout(250)
        pg.click('[data-key="trip-claude_code"]'); pg.click('.ax-inline-confirm .btn.danger'); pg.wait_for_timeout(300)
        check('trip breaker opens it', pg.evaluate("window.v2live.sim.state.harnesses[0].breaker.state") == 'open' and 'Open: cannot start' in T(pg, 0))
        pg.click('[data-key="reset-claude_code"]'); pg.click('.ax-inline-confirm .btn.primary'); pg.wait_for_timeout(300)
        check('reset breaker closes it', pg.evaluate("window.v2live.sim.state.harnesses[0].breaker.state") == 'closed')
        # 2 hook off + approval gating
        pg.evaluate("location.hash='#/extensions'"); pg.wait_for_timeout(250)
        pg.click('[data-key="sw-h-1"]'); pg.wait_for_timeout(200)
        check('sensitive hook asks to confirm', pg.locator('.ax-inline-confirm').count() == 1 and pg.evaluate("window.v2live.areas.hookAllows('h-1')"))
        pg.click('.ax-inline-confirm .btn.danger'); pg.wait_for_timeout(250)
        check('hook switched off', not pg.evaluate("window.v2live.areas.hookAllows('h-1')"))
        pg.evaluate("location.hash='#/security'"); pg.wait_for_timeout(250)
        check('privilege p5 unguarded', 'Unguarded' in T(pg, 0))
        check('locked hook cannot switch', pg.evaluate("window.v2live.areas.toggleHook('h-live-5').ok") is False)
        # 3 mission inspector tabs and pin
        pg.evaluate("location.hash='#/work/m-date'"); pg.wait_for_timeout(300)
        for tab in ['Why', 'Relations', 'Timeline', 'Plan', 'Now', 'Evidence']:
            pg.click('.tab:has-text("%s")' % tab); pg.wait_for_timeout(120)
            check('tab ' + tab, pg.locator('.insp-body .ax-body').count() == 1)
        pg.click('.ax-ih ~ .ax-head-actions .btn:has-text("Pin")'); pg.wait_for_timeout(250)
        pg.evaluate("location.hash='#/work'"); pg.wait_for_timeout(250)
        check('pinned mission listed', pg.locator('.ax-pinned .mrow').count() == 1)
        pg.evaluate("window.v2live.areas.togglePin('m-date')")
        # relation link opens task inspector
        pg.evaluate("location.hash='#/work/m-date'"); pg.wait_for_timeout(250); pg.click('.tab:has-text("Relations")'); pg.click('.ax-ent:has-text("Run the date suite")'); pg.wait_for_timeout(250)
        check('relation opens task', pg.evaluate("location.hash").startswith('#/work/t-date-1'))
        errs and print(errs); check('no page errors (desktop)', not errs); ctx.close()
        # 4 phone decision two step
        ctx, pg, errs = page(390, 844); pg.evaluate("location.hash='#/attention/a-1'"); pg.wait_for_timeout(300)
        pg.click('.insp-foot .btn:has-text("Approve")'); pg.wait_for_timeout(200)
        check('phone approve needs a second step', pg.locator('.ax-confirm-q').count() == 1 and pg.evaluate("window.v2live.sim.state.approvals['a-1'].state") == 'PENDING')
        pg.click('[data-key="confirm-yes"]'); pg.wait_for_timeout(300)
        check('confirm approves', pg.evaluate("window.v2live.sim.state.approvals['a-1'].state") in ('APPROVED', 'CONSUMED'))
        ctx.close()
        # 5 request changes
        ctx, pg, errs = page(); pg.evaluate("location.hash='#/attention/a-1'"); pg.wait_for_timeout(300)
        pg.click('.insp-foot .btn:has-text("Request changes")'); pg.wait_for_timeout(300)
        check('request changes sends plan back', pg.evaluate("window.v2live.sim.state.missions['m-search'].state") == 'PLANNING')
        pg.evaluate("window.v2live.sim.advance(40000)"); pg.wait_for_timeout(400)
        check('new decision follows', pg.evaluate("window.v2live.sim.state.missions['m-search'].state") == 'APPROVAL_REQUIRED')
        # 6 offline
        pg.evaluate("location.hash='#/now'"); pg.wait_for_timeout(200)
        pg.click('[data-tb="sim"]'); pg.click('.menu .btn:has-text("Go offline")'); pg.wait_for_timeout(300)
        check('offline banner and stale sentence', pg.locator('.ax-offline').count() >= 1 and pg.locator('.ax-stale-sentence').count() == 1)
        pg.evaluate("window.v2live.sim.advance(300000)"); pg.wait_for_timeout(300)
        check('offline read stays stale', 'Offline: last seen' in T(pg, 0))
        pg.keyboard.press('Escape'); pg.click('.ax-offline .btn:has-text("Reconnect")'); pg.wait_for_timeout(300)
        check('reconnect shows live', pg.locator('.ax-offline').count() == 0)
        # 7 usage live
        pg.evaluate("location.hash='#/usage'"); pg.wait_for_timeout(250)
        before = pg.inner_text('[data-ax-ring="acc-work:session"] .big')
        pg.evaluate("window.v2live.sim.play(); window.v2live.sim.advance(20*60000)"); pg.wait_for_timeout(500)
        after = pg.inner_text('[data-ax-ring="acc-work:session"] .big')
        check('usage ring moves with the simulation (%s -> %s)' % (before, after), before != after)
        # 8 accounts
        pg.evaluate("location.hash='#/accounts'"); pg.wait_for_timeout(250)
        pg.click('[data-key="md-claude-opus"] .btn'); pg.wait_for_timeout(250)
        check('make default model', pg.evaluate("window.v2live.areas.defaultModel()") == 'claude-opus')
        pg.select_option('[data-key="ln-h-archeus"]', 'codex'); pg.wait_for_timeout(250)
        check('launch harness change updates preview', 'Codex' in pg.inner_text('[data-key="ln-archeus"] .ln-prev'))
        pg.click('[aria-label="Move Claude Code, personal up"]'); pg.wait_for_timeout(250)
        check('failover order changes', pg.evaluate("window.v2live.areas.failover().order[0]") == 'acc-personal')
        # 9 digest
        pg.evaluate("location.hash='#/now'"); pg.wait_for_timeout(300)
        check('digest has items', pg.locator('.ax-dig li').count() > 0)
        pg.click('.ax-digest .btn:has-text("Mark as seen")'); pg.wait_for_timeout(250)
        check('mark as seen empties the digest', pg.locator('.ax-dig li').count() == 0)
        # emergency stop blocks new dispatch until it is re-armed (owner decision 2026-10-26)
        ctx2, pg2, errs2 = page(1440, 900, '&advance=60'); pg2.evaluate("location.hash='#/settings'"); pg2.wait_for_timeout(300)
        pg2.click('[data-key="estop"]'); pg2.click('[data-key="estop-yes"]'); pg2.wait_for_timeout(300)
        check('emergency stop engages and the panel offers Re-arm', pg2.evaluate("window.v2live.sim.state.estop.engaged") and pg2.locator('[data-key="rearm"]').count() == 1 and pg2.locator('[data-key="estop-note"]').count() == 1)
        pg2.evaluate("location.hash='#/security'"); pg2.wait_for_timeout(250)
        check('Security shows the stop as engaged', 'Engaged: nothing new starts' in T(pg2, 0))
        pg2.evaluate("location.hash='#/settings'"); pg2.wait_for_timeout(250)
        pg2.click('[data-key="rearm"]'); check('re-arm asks first', pg2.locator('[data-key="rearm-yes"]').count() == 1 and pg2.evaluate("window.v2live.sim.state.estop.engaged"))
        pg2.click('[data-key="rearm-yes"]'); pg2.wait_for_timeout(300)
        check('re-arm releases the stop', not pg2.evaluate("window.v2live.sim.state.estop.engaged") and pg2.locator('[data-key="rearm"]').count() == 0)
        check('no page errors (estop)', not errs2); ctx2.close()
        ctx2, pg2, errs2 = page(1440, 900, '&advance=60&lang=it'); pg2.evaluate("location.hash='#/settings'"); pg2.wait_for_timeout(300)
        pg2.click('[data-key="estop"]'); pg2.click('[data-key="estop-yes"]'); pg2.wait_for_timeout(300)
        check('Italian emergency stop panel', 'riarmi' in T(pg2, 0) and 'Riarma' in T(pg2, 0))
        check('no page errors (estop it)', not errs2); ctx2.close()
        # 10 italian
        pg.evaluate("location.hash='#/security'"); pg.click('[data-tb="lang"]'); pg.wait_for_timeout(400)
        t = T(pg, 0)
        check('italian security', 'Due confini' in t and 'Interruttori di avvio' in t)
        pg.evaluate("location.hash='#/health'"); pg.wait_for_timeout(300)
        check('italian health', 'Richiedono attenzione' in T(pg, 0))
        check('no page errors (rest)', not errs); ctx.close()
        br.close()
finally:
    srv.terminate()
print(len(ok), 'passed', len(bad), 'failed', bad)
sys.exit(1 if bad else 0)
