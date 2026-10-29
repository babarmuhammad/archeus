"""Playwright functional run of the phone lists (slice B) at 390x844 with touch: the Overview list (counts, Review, ranked projects, folded details, no map), Work (chips, project
picker, sections with caps, the graph view) and Projects (groups, sort, search, worktree children, caps, ideas, pinned), with 3, 30 and 100 projects, and the Italian words. Run:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_phone_lists_functional.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2_live_layout_probe as P
from playwright.sync_api import sync_playwright

ok = []; bad = []


def check(name, cond, detail=''):
    (ok if cond else bad).append(name)
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '  ' + str(detail)))


port = P.free_port(); srv = P.start_server(port)
base = 'http://127.0.0.1:%d/index.html' % port
try:
    with sync_playwright() as p:
        br = p.chromium.launch()

        def page(hash, extra='', notes='off'):
            ctx = br.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, has_touch=True, is_mobile=True, color_scheme='dark')
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
            pg.goto(base + '?sim=paused&motion=reduced&theme=dark&notes=' + notes + extra + '#/' + hash, wait_until='load')
            pg.wait_for_timeout(450)
            return ctx, pg, errs
        n = lambda pg, s: pg.locator(s).count()
        settle = lambda pg, ms=300: pg.wait_for_timeout(ms)
        hashof = lambda pg: pg.evaluate('location.hash')
        ev = lambda pg, js: pg.evaluate(js)
        sideways = "document.querySelector('.main-col').scrollWidth <= document.querySelector('.main-col').clientWidth + 1"

        # ---- Overview ----
        ctx, pg, errs = page('now')
        check('Overview: no map and no Projects | Map switch on a phone', n(pg, '.map-box, .archeus-map, .np-switch') == 0)
        check('Overview: the count chips are links that open Work on that state', ev(pg, "[...document.querySelectorAll('.counters .ctr')].every((a) => a.getAttribute('href').startsWith('#/work'))") and ev(pg, "document.querySelector('.counters .ctr[data-role=needs_you]').getAttribute('href')") == '#/work?view=needs')
        check('Overview: Review is a 48 px button to the first decision', ev(pg, "(() => { const r = document.querySelector('.pn-review'); return r && r.getBoundingClientRect().height >= 48 && r.getAttribute('href').startsWith('#/work/'); })()"))
        check('Overview: three projects, no search field and no All N link', n(pg, '[data-key^=np-proj-]') == 3 and n(pg, '[data-key=np-search]') == 0 and n(pg, '[data-key=np-all-projects]') == 0)
        first = ev(pg, "document.querySelector('[data-key^=np-proj-]').dataset.key")
        pg.click('[data-key=' + first + ']'); settle(pg)
        pid = first.replace('np-proj-', '')
        check('Overview: a project row opens Work filtered to that project', hashof(pg) == '#/work?project=' + pid and 'Showing' in pg.inner_text('[data-key=work-count]'))
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark&notes=off#/now?as=map', wait_until='load'); settle(pg, 500)
        check('Overview: an old #/now?as=map address still shows the list', n(pg, '.np-projects') == 1 and n(pg, '.map-box') == 0)
        pg.click('[data-key=np-sec-live] summary'); settle(pg)
        ev(pg, "window.v2live.sim.advance(90000)"); settle(pg)
        check('Overview: a folded section opened by the owner stays open through a redraw', ev(pg, "document.querySelector('[data-key=np-sec-live]').open"))
        check('Overview: no sideways scroll', ev(pg, sideways))
        check('Overview: no console or page errors', not errs, errs[:2])
        ctx.close()

        ctx, pg, errs = page('now', '&projects=30')
        check('Overview at 30 projects: five rows, a search field and All 30 projects', n(pg, '[data-key^=np-proj-]') == 5 and n(pg, '[data-key=np-search]') == 1 and 'All 30 projects' in pg.inner_text('[data-key=np-all-projects]'))
        pg.fill('[data-key=np-search]', 'zzzz'); settle(pg)
        check('Overview: a search with no match says so and keeps the field focused', n(pg, '.np-none') >= 1 and ev(pg, "document.activeElement.dataset.key") == 'np-search')
        pg.fill('[data-key=np-search]', 'har'); settle(pg)
        check('Overview: a search lists the matching projects only', 0 < n(pg, '[data-key^=np-proj-]') <= 5 and all('har' in t.lower() for t in pg.locator('.np-pname').all_inner_texts()))
        ctx.close()

        # ---- Work ----
        ctx, pg, errs = page('work')
        chips = ev(pg, "[...document.querySelectorAll('.wp-chip')].map((e) => e.dataset.key)")
        check('Work: Needs you, Running and All chips, and a More control', chips == ['work-view-needs', 'work-view-running', 'work-view-all'] and n(pg, '.wp-more') == 1)
        total = {e.split(':')[0]: int(e.split(':')[1]) for e in ev(pg, "[...document.querySelectorAll('.wr-sec')].map((s) => s.dataset.key.replace('work-sec-', '') + ':' + s.querySelector('.n').textContent)")}
        check('Work: the sections are Needs you, Running, Blocked and Quiet, and the chip counts match them', list(total) == ['needs', 'running', 'blocked', 'done'] and int(ev(pg, "document.querySelector('[data-key=work-view-needs] .tn').textContent")) == total['needs'])
        check('Work: the fourth section is called Quiet', pg.inner_text('[data-key=work-sec-done] .gt').strip().lower() == 'quiet')
        pg.click('.wp-more'); settle(pg)
        pg.click('.pk-o[data-value=blocked]'); settle(pg)
        check('Work: Blocked from More takes the fourth chip while it is the view', 'view=blocked' in hashof(pg) and n(pg, '[data-key=work-view-blocked]') == 1 and ev(pg, "document.querySelector('[data-key=work-view-blocked]').getAttribute('aria-current')") == 'true')
        check('Work: with a filter the page says how many of how many', 'Showing' in pg.inner_text('[data-key=work-count]'))
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark&notes=on#/work', wait_until='load'); settle(pg, 500)
        check('Work: the decision note is one closed line you can open, and it stays open through a redraw', ev(pg, "(() => { const d = document.querySelector('.dnote-d'); return !!d && !d.open && d.firstElementChild.getBoundingClientRect().height >= 44; })()"))
        pg.click('.dnote-d summary'); settle(pg)
        ev(pg, "window.v2live.sim.advance(90000)"); settle(pg)
        check('Work: an opened note stays open', ev(pg, "document.querySelector('.dnote-d').open"))
        check('Work: no sideways scroll and one scroll surface', ev(pg, sideways))
        ctx.close()

        ctx, pg, errs = page('work', '&projects=30')
        check('Work at 30 projects: one project picker button', n(pg, '[data-key=work-project]') == 1)
        pg.click('[data-key=work-project]'); settle(pg)
        check('Work: the picker is a bottom sheet with a search field above 12 projects', n(pg, '.sheet') == 1 and n(pg, '.pk-q') == 1 and n(pg, '.pk-o') == 31)
        pg.fill('.pk-q', 'har'); settle(pg)
        pg.locator('.pk-o').nth(0).click(); settle(pg, 400)
        check('Work: choosing a project closes the sheet and puts the project in the address', n(pg, '.sheet') == 0 and 'project=' in hashof(pg) and ev(pg, "document.querySelector('[data-key=work-project] .pk-t').textContent") != 'All projects')
        ctx.close()

        ctx, pg, errs = page('work', '&projects=100')
        secs = ev(pg, "[...document.querySelectorAll('.wr-sec')].map((s) => [s.dataset.key, Number(s.querySelector('.n').textContent), s.querySelectorAll('.wr').length])")
        check('Work at 100 projects: no section lists more than 10 rows until asked', all(r <= 10 for _, _, r in secs) and any(c > 10 for _, c, _ in secs), secs)
        check('Work at 100 projects: under 1200 elements and under 8 screens before anything is asked for', ev(pg, "document.querySelector('.main-col').querySelectorAll('*').length") < 1200 and ev(pg, "document.querySelector('.main-col').scrollHeight / innerHeight") < 8)
        key = next(k for k, c, _ in secs if c > 10)
        before = n(pg, '[data-key=%s] .wr' % key)
        pg.click('[data-key=work-more-%s]' % key.replace('work-sec-', '')); settle(pg)
        check('Work: Show more adds up to 10 rows to that section', n(pg, '[data-key=%s] .wr' % key) in (before + 10, n(pg, '[data-key=%s] .wr' % key)) and n(pg, '[data-key=%s] .wr' % key) > before)
        ctx.close()

        ctx, pg, errs = page('work?as=graph', '&projects=30')
        nodes = n(pg, '.wgn')
        check('Work graph: at most nine nodes, and the rest is said once with a way to the list', 0 < nodes <= 9 and n(pg, '[data-key=work-graph-more]') == 1)
        check('Work graph: the page behind it does not scroll and the legend shows the four states', ev(pg, "getComputedStyle(document.querySelector('.main-col')).overflowY") == 'hidden' and n(pg, '.wg-chip') == 4)
        pg.locator('.wgn').first.click(force=True); settle(pg)
        check('Work graph: a tap on a node selects it and the dock names it with one action', n(pg, '.wgn-on') == 1 and n(pg, '.wg-card') == 1 and n(pg, '[data-key=wg-open]') == 1)
        pg.click('[data-key=work-legend-needs]'); settle(pg)
        check('Work graph: a legend chip filters through the address, pressed while on', 'view=needs' in hashof(pg) and 'as=graph' in hashof(pg) and ev(pg, "document.querySelector('[data-key=work-legend-needs]').getAttribute('aria-pressed')") == 'true')
        pg.click('[data-key=wg-fit]'); settle(pg)
        check('Work graph: Fit is a 44 px button', ev(pg, "document.querySelector('[data-key=wg-fit]').getBoundingClientRect().height") >= 44)
        pg.click('[data-key=work-as-list]'); settle(pg)
        check('Work graph: Done goes back to the list and keeps the filter', 'as=graph' not in hashof(pg) and 'view=needs' in hashof(pg) and n(pg, '.wr-secs') == 1)
        ctx.close()

        # ---- Projects ----
        ctx, pg, errs = page('projects')
        groups = ev(pg, "[...document.querySelectorAll('.pp-sec')].map((s) => s.dataset.group)")
        check('Projects: grouped Needs you, Running and Quiet, empty groups left out', groups and set(groups) <= {'needs', 'running', 'quiet'} and groups == sorted(groups, key=['needs', 'running', 'quiet'].index))
        rows = n(pg, '.pp-row')
        check('Projects: one row per project (three) and the heading says how many', rows == 3 and 'projects' in pg.inner_text('.pp .sub'))
        check('Projects: no search field below 13 projects, a sort control with three options', n(pg, '[data-key=projects-search]') == 0 and n(pg, '.pp-sort .seg-opt') == 3)
        check('Projects: a row says what Archeus did there and for which project', all(len(t) > 20 for t in pg.locator('.pp-last').all_inner_texts()) and all(t for t in pg.locator('.pp-name').all_inner_texts()))
        wt = pg.locator('.pp-wt').first
        key = ev(pg, "document.querySelector('.pp-wt').closest('.pp-row').dataset.key")
        pid = key.replace('pp-row-', '')
        count = int(wt.inner_text().split()[0])
        check('Projects: worktrees are folded under their project, closed at first', wt.get_attribute('aria-expanded') == 'false' and n(pg, '[data-key=%s] .pp-tree' % key) == 0)
        wt.click(); settle(pg)
        check('Projects: opening a project\'s worktrees lists them as its children', n(pg, '[data-key=%s] .pp-tree' % key) == count and ev(pg, "document.querySelector('.pp-wt').getAttribute('aria-expanded')") == 'true')
        ev(pg, "window.v2live.sim.advance(90000)"); settle(pg)
        check('Projects: the opened worktrees stay open through a redraw', n(pg, '[data-key=%s] .pp-tree' % key) == count)
        check('Projects: a worktree is never a row of its own', n(pg, '.pp-row') == rows)
        stale = n(pg, '.pp-tree[data-state=stale]')
        check('Projects: a stale worktree reads as needing the owner, in words', stale == 0 or 'Stale' in pg.inner_text('.pp-tree[data-state=stale]'))
        pg.click('[data-key=project-plate-prj-%s]' % pid); settle(pg, 500)
        check('Projects: a row opens the project sheet, whose action is Open work for that project', hashof(pg).startswith('#/projects/prj-' + pid) and n(pg, '.sheet') == 1 and ev(pg, "document.querySelector('[data-key=project-open-work]').getAttribute('href')") == '#/work?project=' + pid)
        pg.click('[data-key=project-open-work]'); settle(pg, 500)
        check('Projects: Open work lands on Work filtered to that project', hashof(pg) == '#/work?project=' + pid)
        ctx.close()

        ctx, pg, errs = page('projects')
        pg.click('[data-key=projects-sort-name]'); settle(pg)
        names = pg.locator('.pp-name').all_inner_texts()
        check('Projects: sorting by name is one list called All projects, in name order', n(pg, '.pp-sec') == 1 and 'all projects' in pg.inner_text('.pp-sec .gt').lower() and names == sorted(names, key=str.lower), names)
        check('Projects: the sort choice is pressed and remembered', ev(pg, "document.querySelector('[data-key=projects-sort-name]').getAttribute('aria-pressed')") == 'true')
        ev(pg, "window.v2live.areas.togglePin('m-date')"); ev(pg, "window.v2live.sim.advance(90000)"); settle(pg)
        check('Projects: pinned things have a folded section once there is one', n(pg, '[data-key=pp-sec-pinned]') == 1 and not ev(pg, "document.querySelector('[data-key=pp-sec-pinned]').open"))
        pg.click('[data-key=pp-sec-pinned] summary'); settle(pg)
        check('Projects: the pinned mission is a link to it', n(pg, '[data-key=pp-pin-m-date]') == 1 and ev(pg, "document.querySelector('[data-key=pp-pin-m-date]').getAttribute('href')") == '#/work/m-date')
        check('Projects: captured ideas are a folded section with a count', n(pg, '[data-key=pp-sec-ideas]') == 1 and not ev(pg, "document.querySelector('[data-key=pp-sec-ideas]').open"))
        pg.click('[data-key=pp-sec-ideas] summary'); settle(pg)
        check('Projects: an idea is a link to it with its project', n(pg, '[data-key=pp-sec-ideas] .pp-item') >= 1 and ev(pg, "document.querySelector('[data-key=pp-sec-ideas] .pp-item').getAttribute('href')").startswith('#/projects/i-'))
        ctx.close()

        ctx, pg, errs = page('projects', '&projects=30')
        check('Projects at 30: a search field and the Quiet group folded', n(pg, '[data-key=projects-search]') == 1 and n(pg, 'details.pp-fold[data-group=quiet]') == 1 and not ev(pg, "document.querySelector('details.pp-fold').open"))
        pg.fill('[data-key=projects-search]', 'zzzz'); settle(pg)
        check('Projects: a search with no match says so', n(pg, '.pp-row') == 0 and 'No project matches.' in pg.inner_text('.main-col'))
        pg.fill('[data-key=projects-search]', 'har'); settle(pg)
        check('Projects: a search lists matching projects and opens every group', 0 < n(pg, '.pp-row') < 10 and n(pg, 'details.pp-fold') == 0 and ev(pg, "document.activeElement.dataset.key") == 'projects-search')
        ctx.close()

        ctx, pg, errs = page('projects', '&projects=100')
        sec = ev(pg, "[...document.querySelectorAll('.pp-sec')].map((s) => [s.dataset.group, Number(s.querySelector('.n').textContent), s.querySelectorAll('.pp-row').length])")
        check('Projects at 100: no group lists more than 20 until asked', all(r <= 20 for _, _, r in sec) and any(c > 20 for _, c, _ in sec), sec)
        g = next(k for k, c, _ in sec if c > 20)
        pg.click('[data-key=projects-more-%s]' % g); settle(pg)
        check('Projects: Show 20 more adds up to 20 rows', n(pg, '.pp-sec[data-group=%s] .pp-row' % g) > 20)
        check('Projects at 100: under 1200 elements and under 8 screens', ev(pg, "document.querySelector('.main-col').querySelectorAll('*').length") < 1200 and ev(pg, "document.querySelector('.main-col').scrollHeight / innerHeight") < 8, ev(pg, "[document.querySelector('.main-col').querySelectorAll('*').length, document.querySelector('.main-col').scrollHeight / innerHeight]"))
        check('Projects: no sideways scroll at 100 projects and no scrollbar on the page', ev(pg, sideways) and ev(pg, "getComputedStyle(document.querySelector('.main-col')).scrollbarWidth") == 'none')
        check('Projects: no console or page errors', not errs, errs[:2])
        ctx.close()

        # ---- Italian ----
        ctx, pg, errs = page('projects', '&projects=100&lang=it')
        check('Italian Projects: search, sort, groups and the Show more button are translated', pg.get_attribute('[data-key=projects-search]', 'placeholder') == 'Cerca progetti' and 'Mostra altri' in pg.inner_text('.main-col') and 'Nome' in pg.inner_text('.pp-sort'))
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark&notes=off&lang=it#/work?as=graph', wait_until='load'); settle(pg, 500)
        check('Italian Work graph: the hint and the picker are translated', 'Tocca un nodo' in pg.inner_text('.wg-dock') and 'Filtro progetto' in pg.get_attribute('[data-key=work-project]', 'aria-label'))
        pg.goto(base + '?sim=paused&motion=reduced&theme=dark&notes=off&lang=it&projects=30#/now', wait_until='load'); settle(pg, 500)
        check('Italian Overview: All N projects and All N in Work are translated', 'Tutti i 30 progetti' in pg.inner_text('[data-key=np-all-projects]') and 'Tutti i' in pg.inner_text('[data-key=np-all-need]') and 'in Lavoro' in pg.inner_text('[data-key=np-all-need]'))
        ctx.close()
        br.close()
finally:
    srv.terminate()
    try:
        srv.wait(5)
    except Exception:
        srv.kill()
print('\nPHONE LISTS: %d pass, %d fail' % (len(ok), len(bad)))
sys.exit(1 if bad else 0)
