"""LE-5 measurements: the motion middle in the real Qt shell and in headed Chromium.

Reuses the V2-U0 drivers unchanged (prototypes/v2-u0/tools/measure_qt.py, measure_browser.py)
with this lab's server, so the numbers are comparable with PR-1…PR-6. Adds an input pass in
headed Chromium: real CDP clicks and keys, timed by the Event Timing API (input → next paint),
including input that lands mid-animation. Prototype tooling.

    py motion_measure.py qt | browser | input | all
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'v2-u0', 'tools'))
import serve as later_serve  # noqa: E402

SCEN = ['press', 'reveal', 'tooltip', 'count', 'disclose', 'collapse', 'disclose_css', 'reorder', 'confirm', 'refuse', 'nav', 'push', 'release', 'interrupt']


def jobs():
    j = [{'page': 'motion.html', 'scenario': s, 'reps': 8, 'gap': 250} for s in SCEN]
    j += [{'page': 'motion.html', 'q': 'motion=reduced', 'scenario': s, 'reps': 4, 'gap': 200} for s in ('disclose', 'reorder', 'count', 'push', 'release', 'confirm')]
    j += [{'page': 'motion.html', 'scenario': s, 'reps': 6, 'size': [390, 844]} for s in ('push', 'release', 'disclose')]
    return j


def qt():
    import measure_qt
    measure_qt.serve = later_serve.serve
    return measure_qt.run(jobs())


def browser():
    import measure_browser
    measure_browser.serve = later_serve.serve
    return measure_browser.run(jobs())


INPUT_JS = r'''() => { window.__ev = []; new PerformanceObserver(l => { for (const e of l.getEntries()) if (e.interactionId)
  window.__ev.push({ name: e.name, dur: e.duration, wait: +(e.processingStart - e.startTime).toFixed(1), work: +(e.processingEnd - e.processingStart).toFixed(1) }); })
  .observe({ type: 'event', durationThreshold: 16, buffered: true }); }'''


def input_pass():
    """Each interaction 20 times; 'mid' clicks land 60-90 ms into a running disclosure."""
    from playwright.sync_api import sync_playwright
    base, srv = later_serve.serve()
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False)
        for mode in ('', 'motion=reduced'):
            c = b.new_context(viewport={'width': 1440, 'height': 900})
            pg = c.new_page()
            pg.bring_to_front()
            pg.goto(base + 'motion.html?clean=1&' + mode)
            pg.wait_for_timeout(500)
            pg.evaluate(INPUT_JS)
            res = {}

            def run(name, fn, n=20):
                pg.evaluate('window.__ev = []')
                for _ in range(n):
                    fn()
                    pg.wait_for_timeout(320)
                ev = pg.evaluate('window.__ev')
                # Event Timing reports only interactions slower than 16 ms; the rest were faster
                d = sorted(e['dur'] for e in ev)
                res[name] = {'n': n, 'over_16ms': len(d), 'max_ms': d[-1] if d else '<16', 'entries': ev[:6]}

            tog = pg.locator('#missions [data-toggle]').first
            run('disclose toggle (click)', lambda: tog.click())
            run('press (click Pause all)', lambda: pg.locator('#bPress').click())
            run('menu open/close (click)', lambda: (pg.locator('#bMenu').click(), pg.keyboard.press('Escape')))
            run('tab switch (click)', lambda: pg.locator('#tabs [data-p="1"]').click())
            run('approve (click, focus advances)', lambda: (pg.evaluate('document.querySelector("#decide").innerHTML=""'), pg.evaluate('LAB.reset()'), pg.locator('#decide [data-verb]').first.click()), 12)

            def mid():
                pg.evaluate('LAB.reset()')
                pg.locator('#missions [data-toggle]').first.click()
                pg.wait_for_timeout(70)
                pg.locator('#missions .row:nth-of-type(4) [data-toggle]').click()
            run('click mid-disclosure (interrupt)', mid, 12)
            # keystrokes during the confirm transition land on the next row
            pg.evaluate('LAB.reset()')
            pg.locator('#decide [data-verb]').first.click()
            pg.keyboard.press('Enter')
            res['keystroke_during_confirm'] = pg.evaluate('''() => [...document.querySelectorAll('#decide [data-verb]')].map(b => b.textContent)''')
            out[mode or 'system'] = res
            c.close()
        b.close()
    srv.shutdown()
    return out


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    R = {}
    if what in ('input', 'all'):
        R['input'] = input_pass()
        json.dump(R['input'], open(later_serve.results('le5', 'input.json'), 'w', encoding='utf-8'), indent=1)
    if what in ('browser', 'all'):
        R['browser'] = browser()
        json.dump(R['browser'], open(later_serve.results('le5', 'browser.json'), 'w', encoding='utf-8'), indent=1)
    if what in ('qt', 'all'):
        R['qt'] = qt()
        json.dump(R['qt'], open(later_serve.results('le5', 'qt.json'), 'w', encoding='utf-8'), indent=1)
    print('done')
