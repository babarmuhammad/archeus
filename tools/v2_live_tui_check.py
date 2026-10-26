"""V2 Live terminal view: a functional run in a real browser (keys, commands, mouse, looks, resize, motion, Italian, All devices).
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")

It serves clients/v2-live from its own http.server and drives the terminal view the way a person does. Run through the shared lock:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_tui_check.py
Exit code 1 when a check fails.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, 'clients', 'v2-live')
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + str(detail)) if detail and not ok else ''))


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(port):
    proc = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', APP_DIR], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/index.html' % port, timeout=1).read(10)
            return proc
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    raise SystemExit('server did not start')


def text(pg):
    return pg.evaluate("[...document.querySelectorAll('.tui-grid .r')].map(r => r.textContent).join('\\n')")


def state(pg, expr):
    return pg.evaluate('(() => { const s = window.v2live.sim.state, t = window.v2live.ui.tui.ctl.state; return ' + expr + '; })()')


def open_term(br, base, w=1280, h=800, query='', hash_='#/terminal', scheme='dark', wait=True):
    ctx = br.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme, reduced_motion='no-preference')
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.on('console', lambda m: errs.append('console: ' + m.text) if m.type == 'error' else None)
    pg.goto('%s?theme=dark&sim=paused&advance=400%s%s' % (base, ('&' + query) if query else '', hash_), wait_until='load')
    pg.evaluate('document.fonts.ready.then(() => true)')
    if wait:
        pg.wait_for_selector('.tui-grid .r')
    pg.wait_for_timeout(300)
    return ctx, pg, errs


def main():
    port = free_port()
    srv = start_server(port)
    base = 'http://127.0.0.1:%d/index.html' % port
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()

            ctx, pg, errs = open_term(br, base, query='motion=reduced')
            t = text(pg)
            check('the first line says SIMULATED and no Core connected', 'SIMULATED' in t.split('\n')[0] and 'no Core connected' in t.split('\n')[0])
            check('the grid is focused on entry', pg.evaluate("document.activeElement.classList.contains('tui-grid')"))
            check('Now shows the map, the spine and the state line', all(s in t for s in ['ARCHEUS', 'RUNNING 1', 'NEEDS YOU', '\u2713\u2713\u25c6\u25cb\u25cb\u25cb Approval', 'need you']))
            check('the layout tier at 1280 is the 160 column one', pg.evaluate("document.querySelector('.tui').dataset.tier") == '160')
            check('no animation runs in the terminal (reduced motion)', pg.evaluate('document.getAnimations().length') == 0)

            pg.keyboard.press('2')
            check('2 goes to Work', state(pg, "t.screen") == 'work' and 'BLOCKED' in text(pg))
            pg.keyboard.press('j'); pg.keyboard.press('j'); pg.keyboard.press('Enter')
            check('j j Enter opens a mission', state(pg, "t.screen") == 'mission' and 'FACTS' in text(pg))
            check('the address follows the screen', pg.evaluate('location.hash').startswith('#/terminal/m-'))
            for key, word in [('p', 'TASKS'), ('n', 'EXECUTIONS'), ('e', 'VERIFICATION'), ('w', 'WHY IT IS IN THIS STATE'), ('t', 'LAST RECORDED STEPS'), ('r', 'RECORDED RELATIONS'), ('o', 'FACTS')]:
                pg.keyboard.press(key)
                check('mission tab ' + key + ' shows ' + word, word in text(pg).upper())
            pg.keyboard.press('Tab'); pg.keyboard.press('Shift+Tab')
            pg.keyboard.press('Escape')
            check('Esc goes back', state(pg, "t.screen") == 'work')

            pg.keyboard.press('a'); pg.keyboard.press('Enter')
            check('Attention then Enter opens the decision card', state(pg, "t.screen") == 'decision' and 'Approve this plan?' in text(pg))
            pg.keyboard.press('Shift+A')
            check('A asks first and decides nothing', state(pg, "t.mode && t.mode.kind") == 'confirm' and state(pg, "s.approvals['a-1'].state") == 'PENDING')
            pg.keyboard.press('x')
            check('any other key cancels', state(pg, "t.mode") is None and state(pg, "s.approvals['a-1'].state") == 'PENDING')
            pg.keyboard.press('Shift+A'); pg.keyboard.press('y')
            check('A then y approves, and the mission moves', state(pg, "s.missions['m-search'].state") == 'APPROVED' and state(pg, "t.screen") == 'attention')
            check('the answer is on the status line', 'Approved (simulated)' in text(pg))

            pg.keyboard.press('Shift+Slash')
            check('? opens the help overlay', 'Keys and help' in text(pg) and '/status' in text(pg))
            pg.keyboard.press('x')
            check('any key closes help', state(pg, "t.mode") is None)

            pg.keyboard.press('Shift+Semicolon')
            check(': opens the command line and focuses its input', state(pg, "t.mode && t.mode.kind") == 'cmd' and pg.evaluate("document.activeElement.classList.contains('tui-input')"))
            pg.keyboard.type('/stat')
            check('typing shows the matching commands', '/status' in text(pg) and 'READ' in text(pg))
            recorded = state(pg, "s.messages.length")
            pg.keyboard.press('Tab')
            pg.keyboard.press('Enter')
            check('Enter on a slash command shows the reply with its card as text (the shared chat engine)', state(pg, "t.mode && t.mode.kind") == 'reply' and 'simulated reply' in text(pg) and 'waiting for you' in text(pg))
            pg.keyboard.press('x')
            check('a READ answer is a local echo and is not recorded, as in the chat', state(pg, "s.messages.length") == recorded)
            pg.keyboard.press('E')
            check('E asks before the emergency stop, and a key that is not y cancels it', state(pg, "t.mode && t.mode.kind") == 'confirm')
            pg.keyboard.press('n')
            check('nothing was stopped', state(pg, "s.missions['m-date'].state") == 'EXECUTING')
            pg.keyboard.press('Shift+Semicolon'); pg.keyboard.type('/pause fix'); pg.keyboard.press('Enter')
            check('/pause makes a card and decides nothing', state(pg, "s.missions['m-date'].state") == 'EXECUTING' and '[y] Confirm' in text(pg))
            pg.keyboard.press('y'); pg.evaluate("window.v2live.sim.advance(10000)")
            check('y on the card pauses the mission', state(pg, "s.missions['m-date'].state") == 'PAUSED')
            pg.keyboard.press('Shift+Semicolon'); pg.keyboard.type('/nope'); pg.keyboard.press('Enter')
            check('an unknown command keeps the draft', state(pg, "t.mode && t.mode.kind") == 'cmd' and state(pg, "t.mode.buf") == '/nope')
            pg.keyboard.press('Escape')
            check('Esc closes the command line and returns to the grid', state(pg, "t.mode") is None and pg.evaluate("document.activeElement.classList.contains('tui-grid')"))

            pg.keyboard.press('g'); pg.keyboard.press('s')
            check('g s opens Security', state(pg, "t.section") == 'security' and 'ISOLATION AND SWITCHES' in text(pg).upper())
            pg.keyboard.press('g'); pg.keyboard.press('h')
            check('g h opens Health', 'DISK SPACE' in text(pg).upper() and 'unknown' in text(pg).lower())
            pg.keyboard.press('g'); pg.keyboard.press('u')
            check('g u opens usage and accounts, with "unknown" and no zero', 'unknown' in text(pg) and '5 hour window' in text(pg))
            pg.keyboard.press('r')
            check('r opens Replay', state(pg, "t.screen") == 'replay' and 'MAY-HAVE-TAKEN-EFFECT' in text(pg))
            pg.keyboard.press('n')
            check('n moves to the next mission in Replay', state(pg, "t.replayMission") == 2)
            pg.keyboard.press('1')

            # mouse
            pg.keyboard.press('2')
            pg.click('.tui-grid [data-h^="mission:"] >> nth=2')
            first = state(pg, "t.sel['work:list']")
            pg.click('.tui-grid [data-h="%s"] >> nth=0' % first)
            check('click selects, a second click opens', state(pg, "t.screen") == 'mission')
            pg.click('.tui-grid [data-h="tab:plan"]')
            check('a click on a tab opens it', state(pg, "t.tab") == 'plan')
            pg.click('.tui-grid [data-h="nav:attention"]')
            check('a click on the navigation goes there', state(pg, "t.screen") == 'attention')

            # looks and modes
            pg.click('.tui-title .tui-btn >> nth=0')
            check('the Colours button cycles the look', pg.evaluate("document.querySelector('.tui').dataset.look") == 'ansi')
            pg.click('.tui-title .tui-btn >> nth=1')
            check('ASCII switches to ASCII glyphs only', pg.evaluate("/^[\\x20-\\x7e\\n]*$/.test([...document.querySelectorAll('.tui-grid .r')].map(r => r.textContent).join('\\n'))"))
            pg.click('.tui-title .tui-btn >> nth=1')
            pg.click('.tui-title .tui-btn >> nth=2')
            check('Read shows linear text with the selection marked', pg.evaluate("!document.querySelector('.tui-lin').hidden && document.querySelectorAll('.tui-lin h2').length > 0 && !!document.querySelector('.tui-lin [aria-current]')"))
            check('linear text has no box drawing characters', not pg.evaluate("/[\u2500-\u257f]/.test(document.querySelector('.tui-lin').textContent)"))
            pg.click('.tui-title .tui-btn >> nth=2')
            for _ in range(2):
                pg.click('.tui-title .tui-btn >> nth=0')
            check('the look is remembered in the browser', 'look' in (pg.evaluate("localStorage.getItem('archeus-v2-live-tui')") or ''))

            # Esc then Tab leaves the terminal, Tab alone does not
            pg.focus('.tui-grid')
            pg.wait_for_timeout(2700)
            pg.keyboard.press('Tab')
            check('Tab inside the grid is a terminal key (no focus change)', pg.evaluate("document.activeElement.classList.contains('tui-grid')"))
            pg.keyboard.press('Escape'); pg.keyboard.press('Tab')
            check('Esc then Tab leaves the grid, so there is no keyboard trap', not pg.evaluate("document.activeElement.classList.contains('tui-grid')"))
            check('no page errors', not errs, errs)
            ctx.close()

            # resize: 40, 80, 120 and 160+ columns of characters
            for w, h, lo, hi, tier in [(320, 640, 40, 47, '40'), (600, 800, 60, 109, '80'), (1024, 768, 110, 149, '120'), (1920, 1080, 150, 200, '160'), (2560, 1440, 150, 200, '160')]:
                ctx, pg, errs = open_term(br, base, w, h, query='motion=reduced')
                cols = pg.evaluate("Math.max(...[...document.querySelectorAll('.tui-grid .r')].map(r => r.textContent.length))")
                widest = pg.evaluate("document.querySelector('.tui-grid').getBoundingClientRect().width")
                fits = pg.evaluate("document.querySelector('.tui-grid').getBoundingClientRect().right <= innerWidth + 0.5 && document.documentElement.scrollWidth <= innerWidth")
                check('%dx%d: %d columns in tier %s' % (w, h, cols, tier), lo <= cols <= hi and pg.evaluate("document.querySelector('.tui').dataset.tier") == tier and fits, (cols, widest))
                ctx.close()

            # live work: the core mark swaps slowly under full motion and stays still under reduced motion
            ctx, pg, errs = open_term(br, base, query='motion=full')
            pg.evaluate("window.v2live.sim.play()")
            before = text(pg).split('\n')[3:12]
            has_core = any('\u25ce ARCHEUS' in r or '\u25c9 ARCHEUS' in r for r in before)
            pg.wait_for_timeout(3400)
            seen = text(pg)
            check('with live work and full motion the core glyph swaps (no CSS animation)', has_core and '\u25c9 ARCHEUS' in seen and pg.evaluate('document.getAnimations().length') == 0)
            pg.evaluate("window.v2live.store.set('motion', 'reduced')")
            pg.wait_for_timeout(3400)
            check('under reduced motion it is still', '\u25ce ARCHEUS' in text(pg))
            ctx.close()

            # Italian hints
            ctx, pg, errs = open_term(br, base, query='lang=it')
            t = text(pg)
            check('key hints and navigation are Italian', 'muovi' in t and 'Attenzione' in t and 'aiuto' in t, t.split('\n')[1])
            ctx.close()

            # deep links and the phone key bar
            ctx, pg, errs = open_term(br, base, 390, 844, hash_='#/terminal/m-date')
            check('a deep link opens the mission', state(pg, "t.screen") == 'mission' and 'Fix date test' in text(pg))
            check('the key bar is shown on a phone and its buttons are 44 px', pg.evaluate("[...document.querySelectorAll('.tui-keys .tui-btn')].every(b => b.getBoundingClientRect().height >= 43.5 && b.getBoundingClientRect().width >= 43.5) && document.querySelectorAll('.tui-keys .tui-btn').length >= 7"))
            pg.goto('%s?theme=dark&sim=paused&advance=400#/terminal/a-1' % base, wait_until='load')
            pg.wait_for_selector('.tui-grid .r')
            pg.click('.tui-keys .tui-btn.act >> nth=0')
            check('a key bar action asks for confirmation on a phone', state(pg, "t.mode && t.mode.kind") == 'confirm')
            pg.click('.tui-grid [data-h="act:y"]')
            check('tapping Yes on the card approves', state(pg, "s.approvals['a-1'].state") != 'PENDING')
            pg.click('.tui-keys .tui-btn[data-k=":"]')
            check('the : button opens the command line with its own input', pg.evaluate("!document.querySelector('.tui-cmd').hidden") and pg.evaluate("document.activeElement.classList.contains('tui-input')"))
            ctx.close()

            # All devices: the terminal pane
            ctx, pg, errs = open_term(br, base, 1600, 1000, hash_='#/now', wait=False)
            (pg.click('[data-tb="tools"]') if not pg.is_visible('[data-tb="device"]') else None, pg.click('[data-tb="device"]')); pg.click('[data-device="all"]')
            pg.wait_for_timeout(2500)
            fr = [f for f in pg.frames if f != pg.main_frame and f.evaluate("!!document.querySelector('.tui-grid')")]
            check('the All devices view has a terminal pane that draws the grid', len(fr) == 1 and fr[0].evaluate("document.querySelectorAll('.tui-grid .r').length") > 10)
            ctx.close()
            br.close()
    finally:
        srv.terminate()
    bad = [r for r in results if not r[1]]
    print('\n%d checks, %d failed' % (len(results), len(bad)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
