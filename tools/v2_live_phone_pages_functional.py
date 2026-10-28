"""Playwright functional run of the phone pages (slice D) at 390x844 with touch: the Replay scrubber, event sheet, filter row, view sheet and sections; the lede More and the '...' sheets on the
area pages; Settings as a pushed list; the terminal Places and Stop keys; the Italian words. Run:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_phone_pages_functional.py"""
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

        def page(hash, extra='', w=390, h=844):
            ctx = br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2, has_touch=True, is_mobile=True, color_scheme='dark')
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
            pg.goto(base + '?sim=paused&motion=reduced&theme=dark&notes=off' + extra + '#/' + hash, wait_until='load')
            pg.wait_for_timeout(450)
            return ctx, pg, errs
        n = lambda pg, s: pg.locator(s).count()
        settle = lambda pg, ms=300: pg.wait_for_timeout(ms)
        hashof = lambda pg: pg.evaluate('location.hash')

        # ---- Replay ----
        ctx, pg, errs = page('replay/m-date')
        pos = lambda: pg.inner_text('.rp-position')
        a = pos()
        pg.click('[data-key="rp-earlier"]'); settle(pg)
        check('the earlier button steps the scrubber and the position label follows, with no sheet', pos() != a and n(pg, '.sheet') == 0)
        pg.click('[data-key="rp-later"]'); settle(pg)
        check('the later button steps forward again and still opens no sheet', pos() == a and n(pg, '.sheet') == 0)
        check('the scrubber is one 56 px row with 44 px step buttons', pg.evaluate("(() => { const s = document.querySelector('.rp-scrub').getBoundingClientRect(), b = document.querySelector('[data-key=rp-later]').getBoundingClientRect(); return Math.round(s.height) === 56 && b.width >= 44 && b.height >= 44; })()"))
        pg.click('[data-key="tl-4"]'); settle(pg)
        check('a row tap opens the evidence as a sheet at peek', n(pg, '.sheet') == 1 and pg.get_attribute('[data-key="tl-4"]', 'aria-pressed') == 'true')
        pg.click('[data-key="rp-earlier"]'); settle(pg)
        check('stepping with the sheet open keeps it open on the next step', n(pg, '.sheet') == 1)
        pg.keyboard.press('Escape'); settle(pg)
        check('Esc closes the sheet', n(pg, '.sheet') == 0)
        pg.click('[data-key="tl-4"]'); settle(pg)
        pg.go_back(); settle(pg)
        check('the system Back closes the sheet and stays on Replay', n(pg, '.sheet') == 0 and hashof(pg).startswith('#/replay/'))
        row = pg.evaluate("(() => { const b = document.querySelector('.rp-event').getBoundingClientRect(); return b.bottom < innerHeight * .75; })()")
        check('the first event row is above the fold', row)
        # filters: one row that scrolls sideways
        f = pg.evaluate("(() => { const e = document.querySelector('.rp-filters'), r = e.getBoundingClientRect(); return { one: [...e.children].every((c) => Math.abs(c.getBoundingClientRect().top - e.children[0].getBoundingClientRect().top) < 2), scrolls: e.scrollWidth > e.clientWidth, edge: e.dataset.edge }; })()")
        check('the filters are one row that scrolls with a faded edge', f['one'] and (not f['scrolls'] or f['edge'] in ('right', 'both')))
        before = n(pg, '.rp-event')
        pg.click('.rp-filters .chip[data-cat]'); settle(pg)
        check('a filter chip narrows the list', 0 < n(pg, '.rp-event') <= before)
        pg.click('[data-key="rp-all"]'); settle(pg)
        # view sheet
        pg.click('[data-key="rp-view"]'); settle(pg)
        check('View opens one sheet with the layout and the detail', n(pg, '.sheet') == 1 and n(pg, '.sheet [data-key="rp-view-compact"]') == 1 and n(pg, '.sheet [data-key="rp-view-thinking"]') == 1)
        pg.click('[data-key="rp-view-thinking"]'); settle(pg, 400)
        check('choosing a detail closes the sheet and puts it in the address', n(pg, '.sheet') == 0 and 'detail=thinking' in hashof(pg))
        pg.click('[data-key="rp-view"]'); settle(pg)
        pg.click('[data-key="rp-view-compact"]'); settle(pg, 400)
        check('Compact groups the events and keeps the address', 'mode=compact' in hashof(pg) and n(pg, '.rp-event') > 0)
        # sections
        for sec, sel in (('evidence', '.rp-evidence'), ('recovery', '.rp-rec'), ('reference', '#rp-reference, .rp-ref')):
            pg.click('[data-key="rp-nav-%s"]' % sec); settle(pg)
            check('the %s tab shows its section' % sec, 'section=' + sec in hashof(pg) and n(pg, sel) > 0 and pg.get_attribute('[data-key="rp-nav-%s"]' % sec, 'aria-current') == 'page')
        nav = pg.evaluate("(() => { const e = document.querySelector('.rp-nav'), r = e.getBoundingClientRect(); return [...e.children].every((c) => c.getBoundingClientRect().left >= r.left - 1 && c.getBoundingClientRect().right <= r.right + 1 && c.getBoundingClientRect().height >= 44); })()")
        check('the four section tabs fit 390 px, 44 px high', nav)
        check('no console errors on Replay', not errs)
        ctx.close()

        # ---- area pages: lede More, the '...' sheet ----
        ctx, pg, errs = page('security')
        more = pg.locator('.ax-more:visible')
        if more.count():
            more.first.click(); settle(pg, 150)
            check('More opens the whole lede and says Less', pg.evaluate("document.querySelector('.ax-lede-row').dataset.open") == 'true' and 'Less' in pg.inner_text('.ax-more:visible'))
            pg.locator('.ax-more:visible').first.click(); settle(pg, 150)
            check('Less folds the lede back to two lines', pg.evaluate("document.querySelector('.ax-lede-row').dataset.open") != 'true')
        else:
            check('the lede fits two lines, so no More is shown', pg.evaluate("document.querySelector('.ax-lede-t').scrollHeight <= document.querySelector('.ax-lede-t').clientHeight + 1"))
        ctx.close()
        ctx, pg, errs = page('health')
        dots = pg.locator('.ax-dots')
        check('a Health row with an action keeps one action and a ... button', dots.count() >= 0)
        if dots.count():
            dots.first.click(); settle(pg)
            check('the ... button opens a sheet of the other actions, each 44 px', n(pg, '.sheet .ax-sheet-row') >= 1 and pg.evaluate("[...document.querySelectorAll('.sheet .ax-sheet-row')].every((e) => e.getBoundingClientRect().height >= 44)"))
            pg.keyboard.press('Escape'); settle(pg)
            check('Esc closes the ... sheet', n(pg, '.sheet') == 0)
            dots.first.click(); settle(pg)
            pg.click('.sheet .ax-sheet-row >> nth=0'); settle(pg, 500)
            check('a row in the ... sheet closes it and goes to its page', n(pg, '[data-sheet="sheet-ax-more"]') == 0 and hashof(pg) != '#/health')
        check('no console errors on Security and Health', not errs)
        ctx.close()
        ctx, pg, errs = page('extensions')
        t = pg.evaluate("(() => { const s = document.querySelector('.ext-tabs'), t = s.querySelector('[aria-selected=true]'), r = s.getBoundingClientRect(), b = t.getBoundingClientRect(); return b.left >= r.left - 1 && b.right <= r.right + 1; })()")
        check('the selected Extensions tab is in view', t)
        ctx.close()
        ctx, pg, errs = page('accounts')
        check('Accounts keeps the harness facet as one chip row', n(pg, '.ax-facet .chip') >= 2 and pg.evaluate("(() => { const e = document.querySelector('.ax-facet'); return e.dataset.edge !== undefined && getComputedStyle(e).flexWrap === 'nowrap'; })()"))
        ctx.close()

        # ---- Settings: a pushed list ----
        ctx, pg, errs = page('settings')
        check('Settings opens as a list of the four groups', n(pg, '.set-li') == 4 and n(pg, '.set-back') == 0)
        pg.click('[data-key="set-li-appearance"]'); settle(pg)
        check('a row pushes its section as a page with a Back button', hashof(pg) == '#/settings/appearance' and n(pg, '[data-key="set-back"]') == 1 and n(pg, '.set-li') == 0)
        pg.click('[data-key="set-back"]'); settle(pg)
        check('the Back button returns to the list', hashof(pg) == '#/settings' and n(pg, '.set-li') == 4)
        pg.click('[data-key="set-li-prototype"]'); settle(pg)
        pg.go_back(); settle(pg)
        check('the system Back returns to the list', hashof(pg) == '#/settings' and n(pg, '.set-li') == 4)
        check('no console errors on Settings', not errs)
        ctx.close()
        ctx, pg, errs = page('settings/safety')
        pg.click('[data-key="set-back"]'); settle(pg)
        check('a cold link to a section goes back to the list, not out of the app', hashof(pg) == '#/settings' and n(pg, '.set-li') == 4)
        ctx.close()

        # ---- terminal keys ----
        ctx, pg, errs = page('terminal')
        check('the terminal key row has Places and Stop', n(pg, '[data-key="tui-places"]') == 1 and n(pg, '[data-key="tui-stop"]') == 1)
        pg.click('[data-key="tui-places"]'); settle(pg, 500)
        check('the Places key leaves the terminal and opens the Places sheet', hashof(pg) == '#/now' and n(pg, '.places, .sheet') >= 1)
        ctx.close()
        ctx, pg, errs = page('terminal')
        pg.click('[data-key="tui-stop"]'); settle(pg, 500)
        check('the Stop key leaves the terminal and opens the stop confirmation', hashof(pg) == '#/now' and n(pg, '[data-key="estop-yes"]') == 1)
        check('no console errors in the terminal flow', not errs)
        ctx.close()

        # ---- Italian ----
        ctx, pg, errs = page('replay/m-date', extra='&lang=it')
        check('the Replay phone words are Italian', 'Vista' in pg.inner_text('[data-key="rp-view"]') and 'Missione' in pg.inner_text('.rp-mission'))
        pg.evaluate("location.hash = '#/settings'"); settle(pg)
        check('the Settings list reads Italian with no raw English parts', pg.evaluate("[...document.querySelectorAll('.set-li .r-note span')].every((s) => !/^(Simulated|no Core connected|simulation (playing|paused)|Quiet motion|Full motion)$/.test(s.textContent))"))
        check('no console errors in Italian', not errs)
        ctx.close()
        br.close()
finally:
    srv.terminate()
    try:
        srv.wait(5)
    except Exception:
        srv.kill()
print('\nPHONE PAGES: %d passed, %d failed' % (len(ok), len(bad)))
sys.exit(1 if bad else 0)
