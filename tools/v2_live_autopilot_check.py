"""Playwright run of the whole Autopilot tour (AP01 to AP12) at 1440x900 and 390x844, at 8x (test-only speed): it must finish, reach every chapter, raise no console or page error,
skip no step that is not marked optional, leave every setting as it found it, and stop on a key or a click. Prints the time of each chapter.
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_autopilot_check.py [--speed 8] [--viewports 1440x900,390x844] [--shots DIR]
--shots DIR writes one screenshot per chapter (taken when the chapter starts). --speed 1 gives the real durations of the tour."""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2_live_layout_probe as P
from playwright.sync_api import sync_playwright

ok = []
bad = []


def check(name, cond, detail=''):
    (ok if cond else bad).append(name)
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '  ' + str(detail)))


SNAP = """() => { const v = window.v2live, s = v.store, k = ['theme', 'motion', 'device', 'lang', 'notes', 'heronotes', 'tools', 'overview', 'slashpins', 'slashrecent', 'projsort'];
  return { prefs: Object.fromEntries(k.map((x) => [x, JSON.stringify(s.get(x))])), playing: v.sim.state.playing, speed: v.sim.state.speed, estop: v.sim.state.estop.engaged, offline: v.areas.isOffline(),
    search: location.search, bar: !!document.querySelector('.apbar'), ap: document.body.hasAttribute('data-ap') } }"""
STATE = "() => ({ active: window.v2live.autopilot.active(), chapter: window.v2live.autopilot.chapter(), last: window.v2live.autopilot.last })"


def safe(pg, js, default=None):
    """A page reload (a project count) destroys the evaluation context for a moment: treat that as 'not ready'."""
    try:
        return pg.evaluate(js)
    except Exception:
        return default


def fresh(br, w, h, base, extra=''):
    ctx = br.new_context(viewport={'width': w, 'height': h})
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + (getattr(e, 'stack', None) or str(e))))
    pg.on('console', lambda m: errs.append('console: ' + m.text) if m.type == 'error' else None)
    pg.goto(base + '?' + extra, wait_until='load')
    pg.wait_for_function('window.v2live && window.v2live.autopilot')
    pg.wait_for_timeout(500)
    return ctx, pg, errs


def tour(br, w, h, base, speed, shots, ids):
    tag = '%dx%d' % (w, h)
    ctx, pg, errs = fresh(br, w, h, base)
    before = pg.evaluate(SNAP)
    t0 = time.time()
    pg.evaluate('window.v2live.autopilot.start({ speed: %s })' % speed)
    seen = -1
    last = None
    while time.time() - t0 < 600:
        st = safe(pg, STATE)
        if st is None:
            time.sleep(0.2)
            continue
        if st['chapter'] != seen and st['chapter'] >= 0:
            seen = st['chapter']
            if shots:
                try:
                    pg.screenshot(path=os.path.join(shots, 'ap-%s-%02d-%s.png' % (tag, seen + 1, ids[seen])))
                except Exception:
                    pass
        if not st['active'] and st['last']:
            last = st['last']
            break
        time.sleep(0.1)
    elapsed = time.time() - t0
    pg.wait_for_timeout(600)
    after = safe(pg, SNAP, {})
    check('%s: the tour finishes (%.0f s at %sx)' % (tag, elapsed, speed), bool(last) and last['why'] == 'finished', last and last['why'])
    times = (last or {}).get('times') or {}
    check('%s: every chapter was reached (%d of %d)' % (tag, len(times), len(ids)), set(times) == set(ids), sorted(set(ids) - set(times)))
    log = (last or {}).get('log') or []
    missed = [(e['ch'], e['do'], e['target']) for e in log if e['r'] == 'miss']
    check('%s: no step skipped that is not optional' % tag, not missed, missed)
    opt = [(e['ch'], e['target']) for e in log if e['r'] == 'optional']
    if opt:
        print('INFO %s: optional steps that found nothing: %s' % (tag, opt))
    check('%s: no console or page error' % tag, not errs, errs[:3])
    check('%s: every setting is back as it was' % tag, after.get('prefs') == before['prefs'] and after.get('playing') == before['playing'] and after.get('speed') == before['speed']
          and after.get('estop') == before['estop'] and after.get('offline') == before['offline'] and after.get('search') == before['search'], (before, after))
    check('%s: the bar and the page row are gone' % tag, after.get('bar') is False and after.get('ap') is False)
    print('chapter times at %sx (s, real):' % speed)
    for i in ids:
        t = times.get(i, {})
        print('  %-18s %6.1f  skipped %d' % (i, t.get('ms', 0) / 1000.0, t.get('skipped', 0)))
    ctx.close()


def stops(br, w, h, base):
    tag = '%dx%d' % (w, h)
    for how in ('key', 'click', 'escape'):
        ctx, pg, errs = fresh(br, w, h, base)
        before = pg.evaluate(SNAP)
        pg.evaluate('window.v2live.autopilot.start({ speed: 2 })')
        pg.wait_for_selector('.apbar')
        pg.wait_for_timeout(1200)
        if how == 'key':
            pg.keyboard.press('x')
        elif how == 'click':
            pg.mouse.click(w // 2, h // 2)
        else:
            pg.keyboard.press('Escape')
        pg.wait_for_timeout(1200)
        st = pg.evaluate(STATE)
        check('%s: a %s stops the tour' % (tag, how), not st['active'] and st['last'] and st['last']['why'] in ('input', 'button'), st)
        check('%s: the stop says so in a notice' % tag, pg.locator('.toast').count() == 1 and 'Autopilot stopped' in pg.inner_text('.toast'))
        pg.wait_for_timeout(300)
        after = pg.evaluate(SNAP)
        check('%s: stopped by a %s, settings are back' % (tag, how), after['prefs'] == before['prefs'] and after['search'] == before['search'] and not after['bar'], (before['prefs'], after['prefs']))
        check('%s: no error when stopped by a %s' % (tag, how), not errs, errs[:3])
        ctx.close()
    # a stop in the middle of a chapter that changes the theme puts the theme back
    ctx, pg, errs = fresh(br, w, h, base)
    pg.evaluate('window.v2live.autopilot.start({ speed: 1 })')
    pg.wait_for_selector('.apbar')
    pg.click('[data-key="ap-chapters"]')
    pg.click('[data-key="ap-ch-themes"]')
    pg.wait_for_function("window.v2live.store.get('theme') !== 'dark'", timeout=30000)
    pg.keyboard.press('x')
    pg.wait_for_timeout(800)
    check('%s: a stop in the middle of the themes chapter restores the theme' % tag, pg.evaluate("window.v2live.store.get('theme')") == 'dark')
    ctx.close()


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser()
    ap.add_argument('--speed', default='8')
    ap.add_argument('--viewports', default='1440x900,390x844')
    ap.add_argument('--shots', default='')
    ap.add_argument('--no-stops', action='store_true')
    a = ap.parse_args()
    if a.shots:
        os.makedirs(a.shots, exist_ok=True)
    port = P.free_port()
    srv = P.start_server(port)
    base = 'http://127.0.0.1:%d/index.html' % port
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            ctx, pg, _ = fresh(br, 1440, 900, base)
            ids = pg.evaluate("import('./js/autopilot-script.js').then((m) => m.CHAPTERS.map((c) => c.id))")
            ctx.close()
            for vp in a.viewports.split(','):
                w, h = (int(x) for x in vp.split('x'))
                tour(br, w, h, base, a.speed, a.shots, ids)
                if not a.no_stops:
                    stops(br, w, h, base)
            br.close()
    finally:
        srv.terminate()
    print('\n%d passed, %d failed' % (len(ok), len(bad)))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
