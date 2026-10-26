"""V2 Live All devices probe: the four panes (phone, tablet, desktop, terminal) of the All devices view, each a scaled iframe.

Checks, per window size:
  panes    all four panes are visible, inside the window and do not overlap each other
  hit      five points in each pane: the top document hands the point to that pane's iframe (nothing sits on top of it) and the frame's own
           element at that point is real content, not the bare page
  click    a real mouse click on a navigation link inside the phone, tablet and desktop panes changes that pane's route, and only that pane's
  shared   every pane uses the parent's simulation object; an emergency stop made by clicking in the desktop pane shows up in the phone pane's sentence
  error    a page error or console error

Run through the shared lock from the worktree root:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_alldevices_probe.py [--viewports 1600x900,1280x720] [--theme dark] [--lang en] [--shots dir]
Serves clients/v2-live from its own http.server on a free port and stops it. Exit 1 on any defect.
"""
import argparse
import importlib.util
import os
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location('layout_probe', os.path.join(ROOT, 'tools', 'v2_live_layout_probe.py'))
_lp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lp)

VIEWPORTS = ['1024x768', '1280x720', '1440x900', '1600x900', '1920x1080', '2560x1440']
PANES = {'phone': 390, 'tablet': 820, 'desktop': 1440, 'terminal': 640}
NAV = {'phone': ('work', '.bottombar [data-route="work"]'), 'tablet': ('attention', '[data-route="attention"]'), 'desktop': ('replay', '.rail [data-route="replay"]')}
REAL = "(p) => { const e = document.elementFromPoint(p[0], p[1]); return !!e && e !== document.documentElement && e !== document.body && !!e.closest('.app, .term-wrap, .tui, #app'); }"
ROUTE_OF = "() => location.hash.replace(/^#\\/?/, '').split('/')[0]"


def pane_box(pg, name):
    return pg.evaluate("(n) => { const f = document.querySelector('[data-pane=\"' + n + '\"] iframe'); const r = f.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, k: r.width / f.width }; }", name)


def frame_of(pg, name):
    h = pg.query_selector('[data-pane="%s"] iframe' % name)
    return h.content_frame()


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser()
    ap.add_argument('--viewports', default=','.join(VIEWPORTS))
    ap.add_argument('--theme', default='dark')
    ap.add_argument('--lang', default='en')
    ap.add_argument('--shots', default='')
    a = ap.parse_args()
    port = _lp.free_port()
    srv = _lp.start_server(port)
    base = 'http://127.0.0.1:%d/index.html' % port
    bad, checks = [], 0

    def fail(vp, kind, msg):
        bad.append('%s %s: %s' % (vp, kind, msg))

    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for vp in a.viewports.split(','):
                w, h = [int(x) for x in vp.split('x')]
                ctx = br.new_context(viewport={'width': w, 'height': h}, color_scheme='light' if a.theme == 'light' else 'dark')
                pg = ctx.new_page()
                errs = []
                pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
                pg.on('console', lambda m: errs.append('console: ' + m.text) if m.type == 'error' else None)
                pg.goto('%s?theme=%s&lang=%s&notes=off&motion=reduced#/now' % (base, a.theme, a.lang), wait_until='load')
                pg.wait_for_timeout(300)
                pg.click('[data-tb="device"]')
                pg.click('[data-device="all"]')
                pg.wait_for_function("() => document.querySelectorAll('[data-pane] iframe').length === 4 && [...document.querySelectorAll('[data-pane] iframe')].every((f) => f.contentWindow && f.contentWindow.v2live)", timeout=15000)
                pg.wait_for_timeout(1500)
                boxes = {n: pane_box(pg, n) for n in PANES}
                # panes: visible, inside the window, not overlapping
                names = list(PANES)
                for n in names:
                    b = boxes[n]; checks += 1
                    if b['w'] < 20 or b['h'] < 20 or b['x'] < -1 or b['y'] < -1 or b['x'] + b['w'] > w + 1:
                        fail(vp, 'panes', '%s pane outside the window or empty: %s' % (n, {k: round(v, 1) for k, v in b.items()}))
                for i, m in enumerate(names):
                    for n in names[i + 1:]:
                        A, B = boxes[m], boxes[n]; checks += 1
                        if A['x'] < B['x'] + B['w'] - 1 and B['x'] < A['x'] + A['w'] - 1 and A['y'] < B['y'] + B['h'] - 1 and B['y'] < A['y'] + A['h'] - 1:
                            fail(vp, 'panes', '%s and %s panes overlap' % (m, n))
                # hit: five points per pane
                for n in names:
                    b = boxes[n]; fr = frame_of(pg, n)
                    vis_h = min(b['h'], h - b['y'])  # a pane may run below the fold; test only what is on screen
                    if vis_h < 40:
                        continue
                    for fx, fy in [(.5, .5), (.2, .2), (.8, .2), (.2, .8), (.8, .8)]:
                        gx, gy = b['x'] + b['w'] * fx, b['y'] + min(b['h'], vis_h) * fy
                        checks += 1
                        top = pg.evaluate("(p) => { const e = document.elementFromPoint(p[0], p[1]); return e ? (e.tagName === 'IFRAME' ? e.closest('[data-pane]').dataset.pane : e.tagName + '.' + e.className) : null; }", [gx, gy])
                        if top != n:
                            fail(vp, 'hit', 'at %.0f,%.0f the top document returns %s, not the %s pane' % (gx, gy, top, n))
                            continue
                        lx, ly = (gx - b['x']) / b['k'], (gy - b['y']) / b['k']
                        if not fr.evaluate(REAL, [lx, ly]):
                            fail(vp, 'hit', '%s pane has no content at %.0f,%.0f' % (n, lx, ly))
                # click: a real mouse click on a nav link changes that pane's route only
                before = {n: frame_of(pg, n).evaluate(ROUTE_OF) for n in names}
                for n, (route, sel) in NAV.items():
                    b = boxes[n]; fr = frame_of(pg, n)
                    r = fr.evaluate("(s) => { const e = [...document.querySelectorAll(s)].find((x) => x.offsetParent !== null); if (!e) return null; e.scrollIntoView({ block: 'nearest' }); const q = e.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2 }; }", sel)
                    checks += 1
                    if not r:
                        fail(vp, 'click', 'no visible %s link in the %s pane' % (route, n)); continue
                    gx, gy = b['x'] + r['x'] * b['k'], b['y'] + r['y'] * b['k']
                    if gy > h - 2 or gx > w - 2:
                        continue  # that link is below the fold of this window size
                    pg.mouse.click(gx, gy)
                    pg.wait_for_timeout(300)
                    now = {m: frame_of(pg, m).evaluate(ROUTE_OF) for m in names}
                    if now[n] != route:
                        fail(vp, 'click', 'clicking %s in the %s pane left its route at %s' % (route, n, now[n]))
                    for m in names:
                        if m != n and now[m] != before[m]:
                            fail(vp, 'click', 'clicking in the %s pane changed the %s pane to %s' % (n, m, now[m]))
                    before = now
                # shared: one simulation object, and a stop in one pane shows in another
                same = pg.evaluate("() => [...document.querySelectorAll('[data-pane] iframe')].every((f) => f.contentWindow.v2live.sim === window.v2live.sim)")
                checks += 1
                if not same:
                    fail(vp, 'shared', 'a pane has its own simulation object')
                dfr, pfr = frame_of(pg, 'desktop'), frame_of(pg, 'phone')
                dfr.evaluate("() => { location.hash = '#/now'; }")
                pfr.evaluate("() => { location.hash = '#/now'; }")
                pg.wait_for_timeout(400)
                s0 = pfr.evaluate("() => document.querySelector('.state-sentence').textContent")
                dfr.evaluate("() => document.querySelector('[data-key=\"estop\"]').click()")
                pg.wait_for_timeout(200)
                dfr.evaluate("() => document.querySelector('[data-key=\"estop-yes\"]').click()")
                pg.wait_for_timeout(900)
                s1 = pfr.evaluate("() => document.querySelector('.state-sentence').textContent")
                s2 = dfr.evaluate("() => document.querySelector('.state-sentence').textContent")
                engaged = pg.evaluate("() => window.v2live.sim.state.estop.engaged")
                checks += 1
                if not engaged or s1 == s0 or s1 != s2:
                    fail(vp, 'shared', 'stop in the desktop pane: engaged=%s, phone sentence "%s" -> "%s", desktop "%s"' % (engaged, s0, s1, s2))
                if a.shots:
                    os.makedirs(a.shots, exist_ok=True)
                    pg.screenshot(path=os.path.join(a.shots, 'alldevices_%s_%s.png' % (vp, a.theme)))
                for e in errs:
                    fail(vp, 'error', e)
                ctx.close()
            br.close()
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            srv.kill()
    for b in bad:
        print('DEFECT ' + b)
    print('All devices probe: %d checks, %d defects (%s)' % (checks, len(bad), a.viewports))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
