"""Playwright functional run of the S1 shell: sidebar (Overview label, 11 items, no Map, PROJECTS filter), the safety popover with its ask-first
steps, Stop and Re-arm, the Tell overlay, the collapsed tool strip and the Notes toggle. Run:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_s1_functional.py"""
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
        def page(w=1440, h=900, extra='', hash='now'):
            ctx = br.new_context(viewport={'width': w, 'height': h}); pg = ctx.new_page()
            errs = []; pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
            pg.goto(base + '?sim=paused&motion=reduced&theme=dark' + extra + '#/' + hash, wait_until='load'); pg.wait_for_timeout(400)
            return ctx, pg, errs
        ctx, pg, errs = page()
        navs = pg.evaluate("() => [...document.querySelectorAll('.rail .nav-item')].map((e) => e.textContent.replace(/[0-9]/g, '').trim())")
        check('the nav is in three labelled groups (Work, Govern, Configure) and Now is Overview', navs == ['Overview', 'Work', 'Chat', 'Replay', 'Terminal view', 'Security', 'Health', 'Usage', 'Accounts', 'Extensions', 'Settings'] and pg.evaluate("() => [...document.querySelectorAll('.rail .rail-grp')].map((g) => g.getAttribute('aria-label'))") == ['Work', 'Govern', 'Configure'])  # owner round two 2026-10-28: grouped rail
        check('the route of Overview is still #/now', pg.get_attribute('.rail [data-route="now"]', 'href') == '#/now')
        check('the Overview shows one territory per project', pg.locator('.now-view .am-cell').count() >= 3)
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark#/map', wait_until='load'); pg.wait_for_timeout(400)
        check('#/map redirects to #/now', pg.evaluate('location.hash') == '#/now' and pg.get_attribute('.rail [data-route="now"]', 'aria-current') == 'page')
        w = pg.evaluate("document.querySelector('.rail').getBoundingClientRect().width")
        check('sidebar is 176 to 208 px wide at 1440', 176 <= w <= 208)
        check('PROJECTS lists the three sim projects', pg.locator('.proj-item').count() == 3)
        check('the tool strip is collapsed: Tools shown, Device hidden, SIMULATED visible', pg.is_visible('[data-tb="tools"]') and not pg.is_visible('[data-tb="device"]') and pg.is_visible('.sim-badge'))
        pg.click('[data-tb="tools"]'); check('Tools opens the tray', pg.is_visible('[data-tb="device"]') and pg.is_visible('[data-tb="notes"]'))
        pg.click('[data-tb="tools"]'); check('Tools closes it again', not pg.is_visible('[data-tb="device"]'))
        check('decision notes are hidden on Overview by default', not pg.is_visible('.dnote'))
        pg.click('[data-tb="tools"]'); pg.click('[data-tb="notes"]'); pg.wait_for_timeout(100)
        check('the Notes toggle shows them', pg.locator('.dnote').count() > 0 and pg.is_visible('.dnote'))
        # safety popover
        pg.click('[data-key="safety"]'); pg.wait_for_timeout(100)
        check('the status button opens Pause all, Resume all and Emergency stop', all(pg.locator('.safety-pop [data-key="%s"]' % k).count() == 1 for k in ('pause-all', 'resume-all', 'estop')))
        pg.keyboard.press('Escape'); pg.wait_for_timeout(100)
        check('Esc closes the popover', pg.locator('.safety-pop').count() == 0)
        pg.click('[data-key="stop"]'); pg.wait_for_timeout(150)
        check('Stop asks first and nothing is stopped yet', pg.locator('.safety-pop [data-key="estop-yes"]').count() == 1 and not pg.evaluate('window.v2live.sim.state.estop.engaged'))
        pg.click('.safety-pop [data-key="estop-back"]'); pg.wait_for_timeout(100)
        check('Back returns to the buttons', pg.locator('.safety-pop [data-key="estop"]').count() == 1)
        pg.click('.safety-pop [data-key="estop"]'); pg.click('.safety-pop [data-key="estop-yes"]'); pg.wait_for_timeout(200)
        check('the second step engages the stop and the cluster says so', pg.evaluate('window.v2live.sim.state.estop.engaged') and 'Stopped' in pg.inner_text('.safety-btn') and pg.inner_text('[data-key="stop"]') == 'Re-arm')
        pg.click('[data-key="stop"]'); pg.click('.safety-pop [data-key="rearm-yes"]'); pg.wait_for_timeout(200)
        check('Re-arm asks, then releases the stop', not pg.evaluate('window.v2live.sim.state.estop.engaged') and pg.inner_text('[data-key="stop"]') == 'Stop')
        # Tell overlay
        check('the Overview carries its own Tell dock, the app level overlay stays closed', pg.is_visible('.tell-dock input[data-key="chat-in-dock"]') and not pg.is_visible('#chatdock'))
        check('the Overview has no top bar Tell button, its own dock is the composer', pg.locator('.topbar [data-key="tell"]').count() == 0)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(100)
        check('Esc closes the Tell overlay', not pg.is_visible('#chatdock'))
        # project filter
        pg.click('.proj-item[data-proj="notes"]'); pg.wait_for_timeout(250)
        check('a project opens Work filtered with the Show all chip', pg.evaluate('location.hash') == '#/work' and pg.locator('[data-key="work-all"]').count() == 1)
        check('the filter chip is pressed and the graph shows only that project', pg.get_attribute('[data-key="work-p-notes"]', 'aria-pressed') == 'true' and pg.evaluate("[...document.querySelectorAll('.work-graph .wg-node')].length") == 2)
        pg.click('[data-key="work-all"]'); pg.wait_for_timeout(250)
        # one Work page: Attention redirects, the graph and the list stay in sync
        pg.evaluate("location.hash = '#/attention/a-1'"); pg.wait_for_timeout(400)
        check('#/attention/<id> redirects to #/work/<id> and opens the inspector', pg.evaluate('location.hash') == '#/work/a-1' and pg.locator('#inspector .insp-foot').count() == 1)
        check('the Work nav item carries the count and there is no Attention item', pg.locator('.rail [data-route="attention"]').count() == 0 and pg.locator('.rail [data-route="work"] .count').inner_text() == str(pg.evaluate("window.v2live.sim.attention().filter((a) => a.kind !== 'knowledge').length")))
        pg.evaluate("location.hash = '#/work'"); pg.wait_for_timeout(300)
        pg.click('.work-graph .am-hit[data-node-id="m-date"]', force=True); pg.wait_for_timeout(400)
        check('a graph node opens its inspector and marks its row', pg.evaluate('location.hash') == '#/work/m-date' and pg.locator('.work-list [data-link~="m-date"][aria-current="true"]').count() == 1 and pg.locator('.work-graph .wg-node.am-selected').count() == 1)
        pg.evaluate("location.hash = '#/work'"); pg.wait_for_timeout(300)
        pg.click('.work-list a.mrow >> nth=0'); pg.wait_for_timeout(400)
        check('a row marks its node', pg.evaluate('location.hash').startswith('#/work/m-') and pg.locator('.work-graph .wg-node.am-selected[data-node-id="' + pg.evaluate('location.hash')[7:] + '"]').count() == 1)
        check('no page errors', not errs)
        ctx.close()
        ctx, pg, errs = page(w=390, h=844)
        check('phone: the top bar has the status button and no Stop duplicate', pg.is_visible('[data-key="safety"]') and not pg.is_visible('.topbar [data-key="stop"]'))
        bar = pg.evaluate("() => [...document.querySelectorAll('.bottombar .bb-item')].map((e) => [e.textContent.replace(/[0-9]/g, '').trim(), e.getBoundingClientRect().height, e.getBoundingClientRect().width])")
        check('phone: the bottom bar is Tell | Places | Stop, each 44 px or more', [b[0] for b in bar] == ['Tell', 'Places', 'Stop'] and all(b[1] >= 44 and b[2] >= 44 for b in bar))
        pg.click('[data-key="bb-places"]'); pg.wait_for_timeout(250)
        rows = pg.evaluate("() => [...document.querySelectorAll('.places .pl-item')].map((e) => [e.textContent.replace(/[0-9]/g, '').trim(), e.getBoundingClientRect().height])")
        check('phone: Places lists the 10 destinations, Terminal view and the projects, 56 px rows', [r[0] for r in rows][:10] == ['Overview', 'Work', 'Replay', 'Chat', 'Security', 'Health', 'Usage', 'Accounts', 'Extensions', 'Settings'] and rows[10][0] == 'Terminal view' and len(rows) == 14 and all(r[1] >= 56 for r in rows))
        pg.click('.places [data-route="replay"]'); pg.wait_for_timeout(250)
        check('phone: a Places row opens its page and closes the sheet', pg.evaluate('location.hash') == '#/replay' and pg.locator('.places').count() == 0)
        check('phone: Stop stays visible on every page and opens the two-step ask', pg.is_visible('.bb-stop'))
        pg.click('[data-key="bb-stop"]'); pg.wait_for_timeout(250)
        check('phone: Stop asks before stopping', pg.is_visible('.safety-pop [data-key="estop-yes"]') and not pg.evaluate('window.v2live.sim.state.estop.engaged'))
        check('no page errors (phone)', not errs)
        ctx.close()
        br.close()
finally:
    srv.terminate()
print('\n%d passed, %d failed' % (len(ok), len(bad)))
sys.exit(1 if bad else 0)
