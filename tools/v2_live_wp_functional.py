"""Playwright functional run of the Work, Replay and Projects pages: saved views and the project picker in the address, counts, the detail pane, j/k, the Undo toast,
the Replay modes, sections and opening step, the project tabs and sort, the Attention strip. Run:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_wp_functional.py"""
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
        def page(hash, w=1440, h=900, extra=''):
            ctx = br.new_context(viewport={'width': w, 'height': h}); pg = ctx.new_page()
            errs = []; pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
            pg.goto(base + '?sim=paused&motion=reduced&theme=dark' + extra + '#/' + hash, wait_until='load'); pg.wait_for_timeout(450)
            return ctx, pg, errs
        n = lambda pg, s: pg.locator(s).count()

        # ---- Work: saved views, counts, filter ----
        ctx, pg, errs = page('work')
        counts = pg.evaluate("[...document.querySelectorAll('.wk-tab .tn')].map((e) => Number(e.textContent))")
        check('five saved views with counts, All is the sum', len(counts) == 5 and counts[4] == sum(counts[:4]))
        pg.click('[data-key="work-view-running"]'); pg.wait_for_timeout(250)
        check('a view is in the address and marked', pg.evaluate('location.hash') == '#/work?view=running' and pg.get_attribute('[data-key="work-view-running"]', 'aria-current') == 'true')
        rows = n(pg, '.work-list .mrow')
        check('the list shows only that view and the count line says so', rows == counts[1] and 'Showing %d of %d' % (rows, counts[4]) in pg.inner_text('[data-key="work-count"]'))
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark#/work?view=blocked&project=notes', wait_until='load'); pg.wait_for_timeout(400)
        check('a deep link restores the view and the project', pg.get_attribute('[data-key="work-view-blocked"]', 'aria-current') == 'true' and pg.get_attribute('[data-key="work-p-notes"]', 'aria-pressed') == 'true')
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark#/work?view=done', wait_until='load'); pg.wait_for_timeout(400)
        check('a view with no work shows an empty state with a next action, or lists rows', n(pg, '[data-key="work-empty-action"]') == 1 or n(pg, '.work-list .mrow') > 0)
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark#/work?view=nonsense&project=zzz', wait_until='load'); pg.wait_for_timeout(400)
        check('an invalid view or project falls back to All', pg.get_attribute('[data-key="work-view-all"]', 'aria-current') == 'true')
        check('rows carry a relative time with the exact time on hover', pg.evaluate("[...document.querySelectorAll('.mrow-time')].every((t) => /^(now|\\d+[mhd] ago)$/.test(t.textContent) && /\\d\\d:\\d\\d/.test(t.title))"))
        # the pane and the keys
        pg.keyboard.press('j'); pg.wait_for_timeout(150)
        focus = pg.evaluate("document.activeElement.closest('[data-peek-id]')?.dataset.peekId")
        check('j moves to a row and the pane follows it', bool(focus) and pg.evaluate("document.querySelector('[data-peek=true]')?.dataset.peekId") == focus and n(pg, '.wk-pane .wk-pane-t, .wk-pane .card') >= 1)
        check('the pane says what Archeus did', len(pg.inner_text('.wk-pane')) > 20 and ('What Archeus did' in pg.inner_text('.wk-pane') or n(pg, '.wk-pane .ax-eyebrow') == 1))
        check('no console errors on Work', not errs)
        ctx.close()

        # ---- Work at 100 projects: a picker, not chips ----
        ctx, pg, errs = page('work', extra='&story=huge')
        check('100 projects: one picker button, no project chips', n(pg, '[data-key="work-project"]') == 1 and n(pg, '[data-key^="work-p-"]') == 0)
        pg.click('[data-key="work-project"]'); pg.wait_for_timeout(100)
        check('the picker lists every project with a count and opens searchable', n(pg, '.pick-opt') == 101 and pg.evaluate("document.activeElement.classList.contains('pick-search')"))
        pg.fill('.pick-search', 'atlas'); pg.wait_for_timeout(100)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(100)
        check('Esc closes the picker and returns focus to its button', pg.evaluate("document.activeElement.dataset.key") == 'work-project' and not pg.is_visible('.pick-pop'))
        pg.click('[data-key="work-project"]'); pg.click('.pick-opt >> nth=1'); pg.wait_for_timeout(300)
        check('choosing a project puts it in the address', 'project=' in pg.evaluate('location.hash') and 'of' in pg.inner_text('[data-key="work-count"]'))
        check('no console errors at 100 projects', not errs)
        ctx.close()

        # ---- Work: undo toast on Pause ----
        ctx, pg, errs = page('work')
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark#/work?view=running', wait_until='load'); pg.wait_for_timeout(400)
        pg.hover('[data-key="m-m-date"]'); pg.wait_for_timeout(350)
        if n(pg, '[data-key="work-pause"]'):
            pg.click('[data-key="work-pause"]'); pg.wait_for_timeout(250)
            check('Pause is announced with an Undo', n(pg, '[data-key="toast-undo"]') == 1 and 'Pausing' in pg.inner_text('.toast'))
            pg.click('[data-key="toast-undo"]'); pg.evaluate("window.v2live.sim.advance(600000)"); pg.wait_for_timeout(1500)
            check('Undo on a pause still landing waits for the halt, then resumes', pg.evaluate("window.v2live.sim.state.missions['m-date'].state") in ('RESUMED', 'EXECUTING') and 'not paused' not in pg.inner_text('body'))
        else:
            check('the pane offers Pause for a running mission', False)
        ctx.close()

        # ---- Replay: modes, sections, opening step ----
        ctx, pg, errs = page('replay/m-export')
        check('a mission that waits on you opens on its blocked step', pg.evaluate("document.querySelector('.rp-event[aria-pressed=true]')?.textContent.includes('BLOCKED')"))
        check('the what-changed line says a step needs a look', '1 step needs a look' in pg.inner_text('[data-key="rp-changed"]'))
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark#/replay/m-date?mode=compact&detail=verbose', wait_until='load'); pg.wait_for_timeout(450)
        check('Compact merges neighbouring steps and Verbose adds the trigger line', pg.evaluate("document.querySelectorAll('.rp-event').length") < 10 and 'seq' in pg.inner_text('.rp-events'))
        check('both modes are marked in the address-driven controls', pg.get_attribute('[data-key="rp-mode-compact"]', 'aria-current') == 'true' and pg.get_attribute('[data-key="rp-detail-verbose"]', 'aria-current') == 'true')
        pg.click('[data-key="rp-nav-recovery"]'); pg.wait_for_timeout(500)
        check('a section link changes the address and lights the section', 'section=recovery' in pg.evaluate('location.hash') and pg.get_attribute('[data-key="rp-nav-recovery"]', 'aria-current') == 'true')
        check('the sticky nav stays in view at the section', pg.evaluate("document.querySelector('.rp-nav').getBoundingClientRect().top") < 120)
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark#/replay/m-date?section=reference', wait_until='load'); pg.wait_for_timeout(500)
        check('a deep link to a section opens and scrolls to it', pg.evaluate("document.getElementById('rp-reference').open") and pg.evaluate("document.getElementById('rp-reference').getBoundingClientRect().top") < 300)
        check('no console errors in Replay', not errs)
        ctx.close()

        # ---- Projects: sort, tabs in the address ----
        ctx, pg, errs = page('projects')
        check('Attention groups the projects, Name lists them in one', n(pg, '.pgroup') >= 2)
        pg.click('[data-key="projects-sort-name"]'); pg.wait_for_timeout(250)
        names = pg.evaluate("[...document.querySelectorAll('.pcell .pc-open')].map((e) => e.textContent)")
        check('Name sorts alphabetically in one list', names == sorted(names, key=str.casefold) and 'all projects' in pg.inner_text('.pgroup >> nth=0').lower())
        pg.reload(); pg.wait_for_timeout(500)
        check('the sort is remembered', pg.get_attribute('[data-key="projects-sort-name"]', 'aria-pressed') == 'true')
        pg.click('[data-key="projects-sort-attention"]')
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark#/projects/prj-archeus/missions', wait_until='load'); pg.wait_for_timeout(450)
        check('a project tab is in the address and selected', pg.get_attribute('.project-inspector .tab[aria-selected=true]', 'role') == 'tab' and 'Missions' in pg.inner_text('.project-inspector .tab[aria-selected=true]'))
        pg.click('.project-inspector .tab:has-text("Activity")'); pg.wait_for_timeout(250)
        check('clicking a tab updates the address', pg.evaluate('location.hash') == '#/projects/prj-archeus/activity' and n(pg, '.project-activity li') > 0)
        check('five tabs with counts on Missions and Ideas', n(pg, '.project-inspector .tab') == 5 and n(pg, '.project-inspector .tab .tn') == 2)
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark#/work/m-date/plan', wait_until='load'); pg.wait_for_timeout(450)
        check('a mission tab is deep-linkable too', 'Plan' in pg.inner_text('.tab[aria-selected=true]'))
        check('no console errors on Projects', not errs)
        ctx.close()

        # ---- Overview: the Attention strip ----
        ctx, pg, errs = page('now')
        check('the strip lists the projects that need you', n(pg, '.att-chip') >= 1 and n(pg, '.att-chip') <= 3)
        pg.click('.att-chip >> nth=0'); pg.wait_for_timeout(450)
        check('a chip focuses that project on the map', pg.is_visible('.am-focus') and n(pg, '.am-focus-name') == 1)
        ctx.close()
        ctx, pg, errs = page('now', extra='&story=calm')
        check('the strip is absent when nothing needs the owner', n(pg, '.att-strip') == 0)
        check('no console errors on the Overview', not errs)
        ctx.close()
        br.close()
finally:
    srv.terminate()
print('\n%d passed, %d failed' % (len(ok), len(bad)))
sys.exit(1 if bad else 0)
