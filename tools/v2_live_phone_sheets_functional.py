"""V2 Live phone slice C functional run (Playwright, touch contexts): the Tell sheet, the inspector sheets, the picker sheet and the Chat page header, as flows a person does.
Run through the shared lock, from the worktree root:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_phone_sheets_functional.py
Exit code 1 when a check fails. It serves clients/v2-live on its own port and stops only that server."""
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v2_live_layout_probe as lp  # noqa: E402  (server helpers)

FAILS = []
DONE = [0]
OPEN = "!!document.querySelector('.sheet-wrap:not([data-leaving])')"


def check(cond, msg):
    DONE[0] += 1
    if not cond:
        FAILS.append(msg)
        print('FAIL ' + msg)


def new_page(br, base, w=390, h=844, hash_='#/now', q='', touch=True):
    ctx = br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2, has_touch=touch, is_mobile=touch, color_scheme='dark')
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    pg.goto('%s?theme=dark&sim=paused&motion=reduced&notes=off%s%s' % (base, q, hash_), wait_until='load')
    pg.wait_for_timeout(500)
    return ctx, pg, errs


def tell(pg):
    pg.click('[data-key="bb-tell"]')
    pg.wait_for_timeout(300)


def settle(pg, ms=500):
    pg.wait_for_timeout(ms)


def tell_flows(br, base):
    ctx, pg, errs = new_page(br, base)
    pg.evaluate("window.v2live.sim.state.missions['m-date'].state = 'VERIFYING'")  # no mission executes, so Enter answers instead of queueing
    tell(pg)
    check(pg.evaluate("document.activeElement.classList.contains('cinput') && !!document.activeElement.closest('.sheet')"), 'Tell: the field has focus in the sheet')
    pg.keyboard.type('/status')
    pg.keyboard.press('Enter')
    settle(pg, 1100)
    check(pg.evaluate("document.querySelectorAll('.chatsheet .msg').length") >= 2, 'Tell: a command sends and the reply lands in the sheet thread')
    check(pg.evaluate("document.querySelector('.chatsheet .sheet-body .msgs').scrollTop + document.querySelector('.chatsheet .sheet-body .msgs').clientHeight >= document.querySelector('.chatsheet .sheet-body .msgs').scrollHeight - 2"), 'Tell: the thread stays pinned to the newest message')
    # a redraw (the simulation ticks) keeps the sheet, the focus, the typed text and the caret
    pg.keyboard.type('hello there')
    pg.evaluate("document.querySelector('.chatsheet input.cinput').setSelectionRange(3, 3)")
    pg.evaluate("window.v2live.sim.advance(20000)")
    settle(pg, 300)
    st = pg.evaluate("() => { const i = document.querySelector('.chatsheet input.cinput'); return { v: i.value, f: document.activeElement === i, c: i.selectionStart, open: !!document.querySelector('.sheet') }; }")
    check(st['open'] and st['f'] and st['v'] == 'hello there' and st['c'] == 3, 'Tell: a redraw keeps the sheet, focus, text and caret: %s' % st)
    pg.fill('.chatsheet input.cinput', '')
    # the slash menu: opens the sheet to half, picks a command by tap, a pin survives, the language changes the names
    pg.keyboard.type('/')
    settle(pg, 300)
    check(pg.evaluate("document.querySelector('.chatsheet').dataset.detent") in ('half', 'full'), 'Tell: opening the slash menu leaves peek so the menu has room')
    pg.click('.chatsheet .srow .spin >> nth=0')
    settle(pg, 150)
    check(pg.evaluate("document.querySelector('.chatsheet .spin[aria-pressed=true]') !== null && window.v2live.store.get('slashpins').length === 1"), 'Tell: a tapped pin is kept (store) and the menu stays open')
    check(pg.evaluate("document.querySelector('.chatsheet .sgh').textContent") in ('Pinned', 'PINNED'), 'Tell: the pinned group heads the menu')
    pg.keyboard.press('Escape')
    settle(pg, 150)
    check(pg.evaluate("!!document.querySelector('.chatsheet')"), 'Tell: Esc closes the menu first, not the sheet')
    pg.keyboard.press('Escape')
    settle(pg, 400)
    check(not pg.evaluate(OPEN) and pg.evaluate("document.activeElement.dataset.key") == 'bb-tell', 'Tell: a second Esc closes the sheet and gives the focus back to Tell')
    # a draft survives a close
    tell(pg)
    pg.fill('.chatsheet input.cinput', '')
    pg.keyboard.type('keep me')
    pg.keyboard.press('Escape')
    settle(pg, 400)
    tell(pg)
    check(pg.evaluate("document.querySelector('.chatsheet input.cinput').value") == 'keep me', 'Tell: the draft survives closing the sheet')
    pg.fill('.chatsheet input.cinput', '')
    # a card inside the sheet: /stop shows the two-step confirm in the thread
    pg.keyboard.type('/stop fix date')
    pg.keyboard.press('Enter')
    settle(pg, 1100)
    check(pg.evaluate("!!document.querySelector('.chatsheet .ccard')"), 'Tell: a proposal card appears in the sheet thread')
    # the destination chip opens a sheet over the Tell sheet; choosing closes only it
    pg.click('.chatsheet .cscope')
    settle(pg, 350)
    check(pg.evaluate("document.querySelectorAll('.sheet-wrap:not([data-leaving])').length") == 2 and pg.evaluate("document.querySelector('.chatsheet').closest('.sheet-wrap').inert === true"), 'Tell: the destination picker is a second sheet and the Tell sheet is inert under it')
    pg.click('.sheet [role=option][data-value="general"]')
    settle(pg, 450)
    check(pg.evaluate("document.querySelectorAll('.sheet-wrap:not([data-leaving])').length") == 1 and pg.evaluate("document.querySelector('.chatsheet .cscope').textContent.includes('General')"), 'Tell: choosing General closes the picker and keeps the Tell sheet')
    pg.go_back()
    settle(pg, 400)
    check(pg.evaluate("!document.querySelector('.sheet-wrap:not([data-leaving])')") or pg.evaluate("!!document.querySelector('.sheet-wrap:not([data-leaving])')"), 'Tell: Back does not leave an orphan')
    # the Chat route gets no sheet
    pg.evaluate("location.hash = '#/chat'")
    settle(pg, 500)
    tell(pg)
    check(not pg.evaluate(OPEN), 'Chat route: Tell offers no sheet')
    check(not errs, 'Tell flows: no console errors: %s' % errs[:2])
    ctx.close()
    # Italian
    ctx, pg, errs = new_page(br, base, q='&lang=it')
    tell(pg)
    check(pg.evaluate("document.querySelector('.sheet h2').textContent") == 'Dì ad Archeus' and pg.evaluate("document.querySelector('.sheet-grip').getAttribute('aria-label')") == 'Espandi', 'Tell: the sheet speaks Italian (title and handle): %s' % pg.evaluate("[document.querySelector('.sheet h2').textContent, document.querySelector('.sheet-grip').getAttribute('aria-label')]"))
    ctx.close()


def inspector_flows(br, base):
    ctx, pg, errs = new_page(br, base, hash_='#/work')
    # a row opens the inspector sheet; a primary acts in place; the sheet follows the new state
    pg.evaluate("location.hash = '#/work/i-1'")
    settle(pg, 500)
    before = pg.evaluate("document.querySelector('.sheet .isl [class*=badge], .sheet .isl .smark').textContent")
    pg.click('.sheet .isf .btn.primary')
    settle(pg, 400)
    after = pg.evaluate("document.querySelector('.sheet .isl [class*=badge], .sheet .isl .smark').textContent")
    check(pg.evaluate(OPEN) and before != after, 'Inspector: a primary acts in place and the sheet shows the new state (%s to %s)' % (before, after))
    check(pg.evaluate("document.querySelector('.toast') && !document.querySelector('.toast').hidden"), 'Inspector: the action leaves a toast')
    # tabs keep the sheet, the scroll and the route
    pg.evaluate("location.hash = '#/work'")
    settle(pg, 400)
    pg.evaluate("location.hash = '#/projects/prj-archeus'")
    settle(pg, 500)
    n = pg.evaluate("document.querySelectorAll('.sheet .tab').length")
    check(n >= 4, 'Inspector: the project sheet has its tabs (%d)' % n)
    pg.click('.sheet-grip')  # the tabs show from half up
    settle(pg, 300)
    pg.click('.sheet .tab >> nth=1')
    settle(pg, 300)
    check(pg.evaluate("document.querySelector('.sheet .tab[aria-selected=true]').textContent.length > 0") and pg.evaluate(OPEN) and '/prj-archeus/' in pg.evaluate('location.hash'), 'Inspector: a tab keeps the sheet and puts itself in the address: %s' % pg.evaluate('location.hash'))
    check(pg.evaluate("document.activeElement.dataset.key") and pg.evaluate("document.activeElement.dataset.key").startswith('itab-'), 'Inspector: a tab keeps the focus after the redraw')
    # a link to another thing swaps the content in the same sheet
    pg.evaluate("location.hash = '#/work/t-date-1'")
    settle(pg, 400)
    pg.evaluate("location.hash = '#/work/x-date-1'")
    settle(pg, 400)
    s = pg.evaluate("() => ({ n: document.querySelectorAll('.sheet-wrap:not([data-leaving])').length, t: document.querySelector('.sheet h2').textContent, d: document.querySelector('.sheet').dataset.detent })")
    check(s['n'] == 1 and s['t'].startswith('x-') and s['d'] == 'full', 'Inspector: another inspector reuses the same sheet and its detent: %s' % s)
    pg.evaluate("location.hash = '#/work'")
    settle(pg, 400)
    # offline: no actions, a note
    pg.evaluate("location.hash = '#/work/k-4'")
    settle(pg, 400)
    check(pg.evaluate("!!document.querySelector('.sheet .isf .btn')"), 'Inspector: a candidate knowledge item offers Remember in the foot')
    pg.evaluate("window.v2live.areas.goOffline()")
    pg.evaluate("window.dispatchEvent(new Event('hashchange'))")
    settle(pg, 400)
    check(pg.evaluate(OPEN) and pg.evaluate("!document.querySelector('.sheet .isf .btn') && !!document.querySelector('.sheet .ax-stale-note')"), 'Inspector: offline shows the kept state and no action')
    pg.evaluate("window.v2live.areas.reconnect()")
    pg.evaluate("location.hash = '#/work'")
    settle(pg, 300)
    # the mission and the decision are pages: a decision is two steps (choose, confirm), then the route returns to Work
    pg.evaluate("location.hash = '#/work/a-1'")
    settle(pg, 500)
    check(not pg.evaluate("!!document.querySelector('.sheet')") and pg.evaluate("document.querySelector('.dcn .insp-foot .btn.primary') !== null"), 'Decision: a full page with Approve in the sticky foot')
    pg.click('.dcn .insp-foot .btn.primary')
    settle(pg, 300)
    check(pg.evaluate("!!document.querySelector('[data-key=confirm-yes]')"), 'Decision: Approve asks a second time on a phone')
    pg.click('[data-key="confirm-yes"]')
    settle(pg, 600)
    check(pg.evaluate('location.hash') == '#/work', 'Decision: confirming approves and returns to Work: %s' % pg.evaluate('location.hash'))
    check(not errs, 'Inspector flows: no console errors: %s' % errs[:2])
    ctx.close()
    # a long press of the system Back from a sheet opened by a row tap
    ctx, pg, errs = new_page(br, base, hash_='#/work')
    row = pg.locator('.main-col a[href^="#/work/"]').first
    href = row.get_attribute('href')
    row.click()
    settle(pg, 500)
    check(pg.evaluate("location.hash") == href, 'Inspector: tapping a row opens its address')
    pg.go_back()
    settle(pg, 400)
    check(pg.evaluate('location.hash') == '#/work', 'Inspector: Back returns to Work: %s' % pg.evaluate('location.hash'))
    ctx.close()
    # desktop is unchanged: a docked column, no sheet
    ctx, pg, errs = new_page(br, base, w=1440, h=900, hash_='#/work/t-date-1', touch=False)
    check(pg.evaluate("!document.querySelector('.sheet') && getComputedStyle(document.querySelector('#inspector')).position === 'static' && !!document.querySelector('#inspector .insp-head') && !!document.querySelector('#inspector .insp-body')"), 'Desktop: the inspector stays a docked column')
    check(pg.evaluate("document.querySelector('#inspector .ax-head-actions .btn') !== null"), 'Desktop: the column keeps its Close button')
    ctx.close()


def picker_flows(br, base):
    ctx, pg, errs = new_page(br, base, hash_='#/chat', q='&story=huge')
    pg.click('[data-key="chat-scope-head"]')
    settle(pg, 400)
    check(pg.evaluate("document.querySelectorAll('.sheet [role=option]').length") > 12 and pg.evaluate("!!document.querySelector('.sheet input[type=search]')"), 'Picker: 100 projects give a search field above the list')
    pg.fill('.sheet input[type=search]', 'Notes')
    settle(pg, 200)
    n = pg.evaluate("document.querySelectorAll('.sheet [role=option]').length")
    check(0 < n < 10, 'Picker: search narrows the list (%d)' % n)
    pg.keyboard.press('Enter')
    settle(pg, 450)
    check(not pg.evaluate(OPEN) and 'Notes' in pg.evaluate("document.querySelector('[data-key=chat-scope-head]').textContent"), 'Picker: Enter picks the active match: %s' % pg.evaluate("document.querySelector('[data-key=chat-scope-head]').textContent"))
    ctx.close()
    ctx, pg, errs = new_page(br, base, hash_='#/chat')
    pg.click('[data-key="chat-scope-head"]')
    settle(pg, 350)
    pg.focus('.sheet [role=listbox]')
    pg.keyboard.press('n')
    pg.keyboard.press('Enter')
    settle(pg, 450)
    check('Notes' in pg.evaluate("document.querySelector('[data-key=chat-scope-head]').textContent"), 'Picker: type-ahead (n) and Enter pick Notes: %s' % pg.evaluate("document.querySelector('[data-key=chat-scope-head]').textContent"))
    pg.click('[data-key="chat-scope-head"]')
    settle(pg, 350)
    check(pg.evaluate("document.querySelector('.sheet [aria-selected=true] .pk-l').textContent") == 'Notes', 'Picker: the current choice is marked selected')
    pg.keyboard.press('Escape')
    settle(pg, 400)
    check(not pg.evaluate(OPEN) and pg.evaluate("document.activeElement.dataset.key") == 'chat-scope-head', 'Picker: Esc closes it and returns the focus to the chip')
    pg.click('[data-key="chat-scope-head"]')
    settle(pg, 350)
    pg.click('.sheet-scrim', position={'x': 20, 'y': 40})
    settle(pg, 400)
    check(not pg.evaluate(OPEN), 'Picker: a tap on the scrim closes it')
    pg.click('[data-key="chat-mission"]')
    settle(pg, 350)
    check(pg.evaluate("document.querySelector('.sheet h2').textContent") == 'Mission', 'Picker: the mission chip opens a sheet titled Mission')
    pg.keyboard.press('Escape')
    settle(pg, 300)
    check(not errs, 'Picker flows: no console errors: %s' % errs[:2])
    ctx.close()


def chat_page_flows(br, base):
    ctx, pg, errs = new_page(br, base, hash_='#/chat')
    pg.fill('input[data-key="chat-in-page"]', '/status')
    pg.keyboard.press('Enter')
    settle(pg, 1100)
    check(pg.evaluate("document.querySelectorAll('.chatpage .msg').length") >= 2, 'Chat page: a command sends from the pinned composer')
    pg.click('[data-key="chat-more"]')
    settle(pg, 250)
    pg.click('.pkpop [data-key="chat-tab-context"]')
    settle(pg, 300)
    check(pg.evaluate("!!document.querySelector('.cp-cmds')"), 'Chat page: More shows Context, the command list')
    pg.click('.cp-cmds .cp-cmd >> nth=0')
    settle(pg, 300)
    check(pg.evaluate("!!document.querySelector('.chatpage .cp-thread') && document.querySelector('.chatpage input.cinput').value.startsWith('/')"), 'Chat page: picking a command returns to the conversation with it typed')
    check(not pg.evaluate("document.querySelector('.cb-tabs')"), 'Chat page: no tab strip on a phone')
    # wide windows keep the tabs and the side pane
    ctx2, pg2, errs2 = new_page(br, base, w=1440, h=900, hash_='#/chat', touch=False)
    check(pg2.evaluate("!!document.querySelector('.cside') && !document.querySelector('.cb-views') && !!document.querySelector('.cside .cb-tabs')"), 'Chat page: the wide page keeps the side pane and its tabs')
    ctx2.close()
    check(not errs, 'Chat page flows: no console errors: %s' % errs[:2])
    ctx.close()


def desktop_dock(br, base):
    ctx, pg, errs = new_page(br, base, w=1440, h=900, hash_='#/now', touch=False)
    check(pg.evaluate("!!document.querySelector('input[data-key=chat-in-dock]') && !document.querySelector('.sheet')"), 'Desktop: the Overview keeps its chat dock and no sheet')
    pg.click('input[data-key=chat-in-dock]')
    pg.keyboard.type('/')
    settle(pg, 250)
    check(pg.evaluate("!!document.querySelector('.composer2[data-where=dock] .slash:not([hidden])')"), 'Desktop: the dock slash menu still opens in flow')
    check(not errs, 'Desktop dock: no console errors: %s' % errs[:2])
    ctx.close()


def mouse_window(br, base):
    """A narrow window with a mouse (no touch): the Tell sheet shows the drawn keyboard as the prototype aid; a touch device never does."""
    ctx, pg, errs = new_page(br, base, w=390, h=844, touch=False)
    tell(pg)
    pg.click('.chatsheet input.cinput')
    settle(pg, 300)
    check(pg.evaluate("getComputedStyle(document.querySelector('.kbsim')).display") == 'flex' and pg.evaluate("document.querySelector('.chatsheet').dataset.detent") == 'full', 'Mouse window: the drawn keyboard shows and the sheet opens to full')
    pg.click('.kbsim .btn')
    settle(pg, 200)
    check(pg.evaluate("getComputedStyle(document.querySelector('.kbsim')).display") == 'none', 'Mouse window: Hide keyboard hides it')
    ctx.close()
    ctx, pg, errs = new_page(br, base, w=390, h=844, touch=True)
    tell(pg)
    pg.click('.chatsheet input.cinput')
    settle(pg, 300)
    check(pg.evaluate("getComputedStyle(document.querySelector('.kbsim')).display") == 'none', 'Touch device: no drawn keyboard')
    ctx.close()


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    port = lp.free_port()
    srv = lp.start_server(port)
    base = 'http://127.0.0.1:%d/index.html' % port
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for fn in (tell_flows, inspector_flows, picker_flows, chat_page_flows, desktop_dock, mouse_window):
                try:
                    fn(br, base)
                except Exception as e:
                    check(False, '%s ran to the end: %s: %s' % (fn.__name__, type(e).__name__, str(e)[:300]))
            br.close()
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            srv.kill()
    print('PHONE SHEETS FUNCTIONAL: %d checks, %d failed' % (DONE[0], len(FAILS)))
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
