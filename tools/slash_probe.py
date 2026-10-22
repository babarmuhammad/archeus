"""T-153 slash menu, browser probe: keyboard, filter, Escape, effects as cards only, 44 px targets, label overlap,
phone placement and screenshots. Headless Chromium on localhost, reduced motion, fonts awaited.

Run (serve the prototype first, e.g. py -m http.server 8766 --bind 127.0.0.1 in clients/v2-prototype):
  BASE=http://127.0.0.1:8766 OUT=<dir for screenshots> py -I tools/slash_probe.py
Exit code 1 on any failed check. Prints one line per check.
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get('BASE', 'http://127.0.0.1:8766') + '/index.html'
OUT = os.environ.get('OUT', '.')
fails = []


def check(ok, msg):
    print(('ok   ' if ok else 'FAIL ') + msg, flush=True)
    if not ok:
        fails.append(msg)


STATE = """(inputId) => { const m = document.getElementById('slash-menu'); const a = document.activeElement;
  const rows = [...document.querySelectorAll('#slash-list .slash-row')];
  return { hidden: m.hidden, expanded: document.getElementById(inputId).getAttribute('aria-expanded'),
    names: rows.map(r => { const n = r.querySelector('.slash-name'); return n ? n.textContent : r.textContent.trim(); }),
    alias: rows.map(r => { const n = r.querySelector('.slash-alias'); return n ? n.textContent : ''; }),
    heights: rows.map(r => r.getBoundingClientRect().height),
    active: document.getElementById(inputId).getAttribute('aria-activedescendant'),
    selected: rows.map(r => r.getAttribute('aria-selected')),
    focus: a ? a.id : '', value: document.getElementById(inputId).value,
    note: document.getElementById('slash-note').textContent, noteHidden: document.getElementById('slash-note').hidden,
    arg: document.getElementById('slash-arg').textContent, argHidden: document.getElementById('slash-arg').hidden }; }"""

OVERLAP = """() => { let bad = 0; document.querySelectorAll('#slash-list .slash-row').forEach(r => {
  const parts = [...r.querySelectorAll('.slash-name,.slash-alias,.slash-chip,.slash-desc')].map(e => e.getBoundingClientRect()).filter(b => b.width > 0);
  for (let a = 0; a < parts.length; a++) for (let b = a + 1; b < parts.length; b++) { const p = parts[a], q = parts[b];
    if (p.left < q.right - 0.5 && q.left < p.right - 0.5 && p.top < q.bottom - 0.5 && q.top < p.bottom - 0.5) bad++; } }); return bad; }"""

MSGS = "() => document.querySelectorAll('#msgs > li').length"
LAST = "(sel) => { const l = document.querySelectorAll('#msgs > li.' + sel); return l.length ? l[l.length - 1].textContent : ''; }"
LASTANY = "() => { const l = document.querySelectorAll('#msgs > li'); return l.length ? l[l.length - 1].textContent : ''; }"


def open_page(br, width, height, dpr, path):
    ctx = br.new_context(viewport={'width': width, 'height': height}, device_scale_factor=dpr,
                         reduced_motion='reduce', color_scheme='dark')
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(BASE + path, wait_until='load')
    pg.evaluate('document.fonts.ready.then(() => true)')
    pg.wait_for_timeout(900)
    return ctx, pg, errs


def desktop(br):
    ctx, pg, errs = open_page(br, 1296, 755, 1, '#/now')
    inp = '#chat-input'
    total = pg.evaluate('window.ArchSlash.COMMANDS.length')
    st = pg.evaluate(STATE, 'chat-input')
    check(st['hidden'] and st['expanded'] == 'false', 'desktop: menu closed on load, combobox aria-expanded false')
    pg.focus(inp)
    pg.keyboard.type('/')
    st = pg.evaluate(STATE, 'chat-input')
    check(not st['hidden'] and st['expanded'] == 'true', 'desktop: "/" opens the menu')
    check(len(st['names']) == 6 and st['names'][5].startswith('+'), 'desktop: five command rows then one +N more row')
    more = pg.locator('#slash-list .slash-more').inner_text()
    check(more.strip() == '+%d more' % (total - 5), 'desktop: +N more counts the rest (%s)' % more.strip())
    check(all(h >= 44 for h in st['heights']), 'desktop: every row at least 44 px (%s)' % ','.join('%.0f' % h for h in st['heights']))
    check(pg.evaluate(OVERLAP) == 0, 'desktop: label overlap zero in the open menu')
    check(st['focus'] == 'chat-input' and st['active'] == 'slash-opt-0', 'desktop: focus stays in the composer, first row active')
    pg.keyboard.press('ArrowDown')
    st = pg.evaluate(STATE, 'chat-input')
    check(st['active'] == 'slash-opt-1' and st['selected'][1] == 'true' and st['focus'] == 'chat-input', 'desktop: ArrowDown moves the active row, focus stays')
    pg.keyboard.press('ArrowUp')
    check(pg.evaluate(STATE, 'chat-input')['active'] == 'slash-opt-0', 'desktop: ArrowUp moves back')
    pg.keyboard.type('sta')
    st = pg.evaluate(STATE, 'chat-input')
    check(st['names'][0] == '/status' and '/start' in st['names'] and '/projects' not in st['names'], 'desktop: filter "sta" keeps status and start, drops projects (%s)' % st['names'])
    pg.keyboard.press('Escape')
    st = pg.evaluate(STATE, 'chat-input')
    check(st['hidden'] and st['value'] == '/sta', 'desktop: Escape closes and keeps the text')
    pg.keyboard.type('to')
    st = pg.evaluate(STATE, 'chat-input')
    check(not st['hidden'] and st['names'][0] == '/status' and st['alias'][0] == '/stato', 'desktop: alias /stato shown on the status row')
    pg.keyboard.press('Enter')
    check(pg.evaluate(LASTANY).find('Core: fixtures') >= 0, 'desktop: Enter on a READ row runs it as a chat card (status)')
    st = pg.evaluate(STATE, 'chat-input')
    check(st['hidden'] and st['value'] == '', 'desktop: menu closes and the composer clears after a command')
    # effect commands yield cards only
    pg.fill(inp, '/stop')
    pg.keyboard.press('Enter')
    card = pg.evaluate(LAST, 'msg-card')
    check('Proposed' in card and 'Stop all running work' in card, 'desktop: /stop gives a proposal card')
    check(not pg.evaluate("document.getElementById('confirm').open"), 'desktop: /stop opens no confirm by itself')
    pg.fill(inp, '/start Search provenance')
    pg.keyboard.press('Enter')
    check('Start and plan Search provenance' in pg.evaluate(LAST, 'msg-card'), 'desktop: /start with a mission gives its proposal card, runs nothing')
    check('Plan v1 is ready' not in pg.evaluate(LASTANY), 'desktop: /start does not run the Start card action')
    before = pg.evaluate(MSGS)
    pg.fill(inp, '/xyz')
    pg.keyboard.press('Enter')
    st = pg.evaluate(STATE, 'chat-input')
    check(st['note'] == 'Unknown command /xyz. Type / for the list, or //xyz to send the text as a message.' and not st['noteHidden'], 'desktop: unknown command shows the spec line')
    check(pg.evaluate(MSGS) == before and st['value'] == '/xyz', 'desktop: unknown command sends nothing and keeps the text')
    pg.keyboard.press('Escape')
    pg.fill(inp, '//idea x')
    pg.keyboard.press('Enter')
    check(pg.evaluate(LAST, 'msg-you') == '/idea x', 'desktop: // escape sends /idea x as plain text')
    pg.wait_for_timeout(900)
    check(pg.evaluate(MSGS) > before + 1, 'desktop: plain text gets the chat reply')
    pg.fill(inp, '?')
    pg.keyboard.press('Enter')
    helpcard = pg.evaluate(LASTANY)
    check('READ' in helpcard and '/status' in helpcard and 'PROPOSE' in helpcard, 'desktop: "?" lists the commands by class')
    pg.fill(inp, '/usage')
    pg.keyboard.press('Enter')
    check('Usage: unknown' in pg.evaluate(LASTANY), 'desktop: /usage answers unknown, never 0')
    pg.fill(inp, '/account x')
    pg.keyboard.press('Enter')
    st = pg.evaluate(STATE, 'chat-input')
    check(st['note'] == 'Needs an admin device. Not on this device.', 'desktop: /account refused with its reason')
    pg.fill(inp, '')
    pg.keyboard.type('/')
    pg.keyboard.type('mission')
    pg.keyboard.press('Enter')
    st = pg.evaluate(STATE, 'chat-input')
    check(st['value'] == '/mission ' and not st['argHidden'] and 'Mission in one line: ____' in st['arg'], 'desktop: /mission without text opens the argument step, sends nothing')
    before = pg.evaluate(MSGS)
    pg.keyboard.press('Enter')
    check(pg.evaluate(MSGS) == before, 'desktop: Enter on an empty argument step sends nothing')
    pg.keyboard.press('Escape')
    st = pg.evaluate(STATE, 'chat-input')
    check(st['value'] == '' and st['hidden'], 'desktop: Escape cancels the argument step and clears it')
    pg.fill(inp, '/missione Draft test')
    pg.keyboard.press('Enter')
    check(pg.evaluate(LAST, 'msg-you') == '/missione Draft test', 'desktop: alias /missione echoes as typed')
    pg.wait_for_timeout(900)
    check(pg.evaluate(LASTANY) != '' and pg.evaluate(MSGS) > before, 'desktop: /missione takes the scripted new-work path (a reply)')
    pg.fill(inp, '/')
    pg.wait_for_timeout(50)
    pg.screenshot(path=os.path.join(OUT, 'slash_desktop_menu.png'))
    pg.fill(inp, '')
    st = pg.evaluate(STATE, 'chat-input')
    check(st['hidden'], 'desktop: menu closed with an empty composer')
    recent = pg.evaluate("() => localStorage.getItem('archeus.v2.slashRecent')")
    check(recent is not None and recent.startswith('["mission"') and recent.count(',') <= 4, 'desktop: recent commands stored per device, newest first, at most five (names only)')
    check(not errs, 'desktop: no page errors %s' % (errs[:2],))
    ctx.close()


def phone(br):
    ctx, pg, errs = open_page(br, 402, 687, 2, '#/now')
    inp = '#chat-input'
    pg.click(inp)
    pg.keyboard.type('/')
    st = pg.evaluate(STATE, 'chat-input')
    check(not st['hidden'], 'phone: "/" opens the menu above the chat bar')
    check(all(h >= 44 for h in st['heights']) and all(h >= 48 for h in st['heights']), 'phone: rows 48 px (%s)' % ','.join('%.0f' % h for h in st['heights']))
    box = pg.evaluate("() => { const r = document.getElementById('slash-menu').getBoundingClientRect(); return [r.left, r.right, r.top, r.bottom]; }")
    check(box[0] >= 0 and box[1] <= 402 and box[2] >= 0 and box[3] <= 687, 'phone: menu inside the 402 x 687 viewport %s' % [round(v) for v in box])
    check(pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'phone: no horizontal page scroll with the menu open')
    check(pg.evaluate(OVERLAP) == 0, 'phone: label overlap zero')
    pg.keyboard.type('st')
    pg.screenshot(path=os.path.join(OUT, 'slash_phone_menu.png'))
    pg.keyboard.press('Escape')
    check(pg.evaluate(STATE, 'chat-input')['hidden'], 'phone: Escape closes')
    pg.fill(inp, '')
    pg.keyboard.type('hello')
    check(pg.evaluate(STATE, 'chat-input')['hidden'], 'phone: plain text opens no menu')
    pg.fill(inp, '')
    # the phone sheet chat (decision sheet) has its own composer: same menu
    pg.goto(BASE + '#/plan/m-search', wait_until='load')
    pg.evaluate('document.fonts.ready.then(() => true)')
    pg.wait_for_timeout(700)
    if pg.locator('#ph2-input').is_visible():
        pg.click('#ph2-input')
        pg.keyboard.type('/')
        check(not pg.evaluate(STATE, 'ph2-input')['hidden'], 'phone sheet: "/" opens the same menu in the sheet composer')
        pg.keyboard.press('Escape')
    else:
        print('skip phone sheet composer: #ph2-input not visible at this size')
    check(not errs, 'phone: no page errors %s' % (errs[:2],))
    ctx.close()


def main():
    with sync_playwright() as p:
        br = p.chromium.launch()
        desktop(br)
        phone(br)
        br.close()
    if fails:
        print('FAILED %d' % len(fails))
        sys.exit(1)
    print('OK slash probe')


if __name__ == '__main__':
    main()
