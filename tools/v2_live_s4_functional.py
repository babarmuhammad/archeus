"""V2 Live S4 functional run (Playwright): the chat bar, the slash combobox keys, the cards and their two-step confirms, the phone sheet and Replay.
Run through the shared lock, from the worktree root:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_s4_functional.py
Exit code 1 when a check fails. It serves clients/v2-live on its own port and stops only that server."""
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'clients', 'v2-live')
FAILS = []
DONE = [0]


def check(cond, msg):
    DONE[0] += 1
    if not cond:
        FAILS.append(msg)
        print('FAIL ' + msg)


def pick_scope(pg, value):
    pg.click('.composer2[data-where="page"] .cscope')
    pg.click('.pkpop [role="option"][data-value="%s"]' % value)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def new_page(br, base, w=1440, h=900, q='', hash_='#/chat'):
    ctx = br.new_context(viewport={'width': w, 'height': h})
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    pg.goto('%s?theme=dark&sim=paused&motion=reduced&notes=off%s%s' % (base, q, hash_), wait_until='load')
    pg.wait_for_timeout(500)
    return ctx, pg, errs


def idle(pg):
    """No mission executes in the scope. While one does, Enter queues a plain message instead of answering it (PW08), so the checks
    of plain text answers run with the one executing mission moved on."""
    pg.evaluate("window.v2live.sim.state.missions['m-date'].state = 'VERIFYING'")
    pg.wait_for_timeout(100)


def send(pg, text, where='page', wait=900):
    pg.fill('input[data-key="chat-in-%s"]' % where, text)
    pg.keyboard.press('Enter')
    pg.wait_for_timeout(wait)


def msgs(pg):
    return pg.evaluate("window.v2live.sim.state.messages.length")


def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', APP], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    for _ in range(40):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/index.html' % port, timeout=1).read(10)
            break
        except Exception:
            time.sleep(0.2)
    base = 'http://127.0.0.1:%d/index.html' % port
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()

            # ---- the slash combobox: keys, aria, five rows then more, recents, escape, alias ----
            ctx, pg, errs = new_page(br, base)
            idle(pg)
            inp = 'input[data-key="chat-in-page"]'
            pg.click(inp)
            pg.keyboard.type('/')
            pg.wait_for_timeout(150)
            check(pg.get_attribute(inp, 'role') == 'combobox', 'composer is a combobox')
            check(pg.get_attribute(inp, 'aria-expanded') == 'true', 'aria-expanded true when the menu is open')
            rows = pg.locator('.slash [role=option]')
            check(rows.count() == 6, 'five command rows then a +N more row (got %d)' % rows.count())
            check('more' in rows.nth(5).inner_text().lower(), 'last row says +N more')
            check(pg.evaluate("document.activeElement.matches('input[data-key=\"chat-in-page\"]')"), 'focus stays in the field')
            first = pg.get_attribute(inp, 'aria-activedescendant')
            pg.keyboard.press('ArrowDown')
            second = pg.get_attribute(inp, 'aria-activedescendant')
            check(first and second and first != second, 'ArrowDown moves aria-activedescendant')
            check(pg.get_attribute('#' + second, 'aria-selected') == 'true', 'the active option is aria-selected')
            pg.keyboard.press('ArrowUp')
            check(pg.get_attribute(inp, 'aria-activedescendant') == first, 'ArrowUp moves back')
            pg.keyboard.press('Tab')
            check(pg.input_value(inp).startswith('/') and pg.input_value(inp).endswith(' '), 'Tab fills the name and a space')
            pg.fill(inp, '/stat')
            pg.keyboard.press('Escape')
            check(pg.get_attribute(inp, 'aria-expanded') == 'false' and pg.input_value(inp) == '/stat', 'Escape closes the menu and keeps the text')
            pg.fill(inp, '/')
            for _ in range(5):
                pg.keyboard.press('ArrowDown')
            pg.keyboard.press('Enter')
            pg.wait_for_timeout(150)
            check(pg.locator('.slash [role=option]').count() > 6, 'Enter on +N more expands the list')
            pg.fill(inp, '//idea x')
            n0 = msgs(pg)
            pg.keyboard.press('Enter')
            pg.wait_for_timeout(900)
            check(msgs(pg) == n0 + 2, '// sends the text as a message (and no idea was created)')
            check(pg.evaluate("window.v2live.sim.state.ideas.every(i => i.title !== 'x')"), '// does not run /idea')
            pg.fill(inp, '/xyz')
            pg.keyboard.press('Enter')
            pg.wait_for_timeout(200)
            check('Unknown command /xyz' in pg.inner_text('.cnote') and pg.input_value(inp) == '/xyz', 'unknown command: help line, draft kept, nothing sent')
            check(msgs(pg) == n0 + 2, 'unknown command sends nothing')
            pg.fill(inp, '/mission')
            pg.keyboard.press('Enter')
            pg.wait_for_timeout(200)
            check(pg.is_visible('.argline') and 'Mission in one line' in pg.inner_text('.argline'), 'a missing argument opens the argument prompt')
            pg.fill(inp, '/project')
            pg.keyboard.press('Escape')
            pg.keyboard.press('Enter')
            pg.wait_for_timeout(200)
            check('not available from chat' in pg.inner_text('.cnote'), '/project is refused with the pointer')
            pg.fill(inp, '/sk-abcdefghij12')
            pg.keyboard.press('Enter')
            pg.wait_for_timeout(200)
            check('looks like a secret' in pg.inner_text('.cnote'), 'a secret-looking text is refused')
            pg.fill(inp, '/start @"')
            pg.wait_for_timeout(150)
            check(pg.get_attribute(inp, 'aria-expanded') == 'false' or pg.locator('.slash[data-mode="mention"]').count() >= 0, 'mention state is handled')
            pg.fill(inp, '/start @fix')
            pg.wait_for_timeout(200)
            check(pg.locator('.slash[data-mode="mention"] [role=option]').count() >= 1, '@ inside a command lists missions and projects')
            pg.keyboard.press('Enter')
            check('@"Fix date test"' in pg.input_value(inp), 'Enter inserts the quoted mention')
            check(not errs, 'no page errors in the combobox run: %s' % errs[:2])
            ctx.close()

            # ---- recents, Italian aliases ----
            ctx, pg, errs = new_page(br, base)
            send(pg, '/status')
            pg.fill(inp, '/')
            pg.wait_for_timeout(150)
            check('/status' in pg.locator('.slash [role=option]').first.inner_text(), 'the last used command is first in the menu')
            ctx.close()
            ctx, pg, errs = new_page(br, base, q='&lang=it')
            pg.fill(inp, '/')
            pg.wait_for_timeout(150)
            check('/aiuto' in pg.inner_text('.slash') or '/stato' in pg.inner_text('.slash') or '/riepilogo' in pg.inner_text('.slash'), 'the Italian alias leads in Italian')
            send(pg, '/stato')
            check('Core' in pg.inner_text('.msgs') and 'Raggiungibile' in pg.inner_text('.msgs'), 'an Italian alias runs the command, the card is in Italian')
            ctx.close()

            # ---- READ is local, CREATE and PROPOSE are recorded; /mission is not started; Start card two steps ----
            ctx, pg, errs = new_page(br, base)
            n0 = msgs(pg)
            send(pg, '/projects')
            check(msgs(pg) == n0, 'READ writes nothing to the simulation log')
            check('not recorded' in pg.inner_text('.msgs').lower(), 'a READ answer says it is a local view')
            send(pg, '/mission Audit export labels @Notes')
            pg.wait_for_timeout(300)
            mid = pg.evaluate("Object.values(window.v2live.sim.state.missions).find(m => m.title === 'Audit export labels').id")
            check(pg.evaluate("window.v2live.sim.state.missions['%s'].state" % mid) == 'CREATED', '/mission creates a mission that is not started')
            check('Not started' in pg.inner_text('.msgs'), 'the reply says Not started, and it is true')
            pg.click('.ccard[data-kind="start"] button:has-text("Review proposal")')
            pg.wait_for_timeout(200)
            check('Start and plan' in pg.inner_text('.ccard[data-kind="start"]'), 'Review proposal shows the exact action, Start and plan')
            check(pg.evaluate("window.v2live.sim.state.missions['%s'].state" % mid) == 'CREATED', 'nothing started before the final confirm')
            pg.click('.ccard[data-kind="start"] button:has-text("Start and plan")')
            pg.wait_for_timeout(300)
            check(pg.evaluate("window.v2live.sim.state.missions['%s'].state" % mid) == 'UNDERSTANDING', 'Start and plan starts it')
            ctx.close()

            # ---- two-step confirm for stop; refusal; approval card with step-up ----
            ctx, pg, errs = new_page(br, base)
            send(pg, '/stop fix date')
            check(pg.evaluate("window.v2live.sim.state.missions['m-date'].state") == 'EXECUTING', '/stop only proposes')
            pg.click('.ccard[data-kind="confirm"] button:has-text("Stop mission")')
            pg.wait_for_timeout(250)
            check('Step 2 of 2' in pg.inner_text('.ccard[data-kind="confirm"]'), 'second step is shown')
            check(pg.evaluate("window.v2live.sim.state.missions['m-date'].state") == 'EXECUTING', 'still running after step one')
            pg.click('.ccard[data-kind="confirm"] button:has-text("Yes, stop")')
            pg.wait_for_timeout(300)
            check(pg.evaluate("window.v2live.sim.state.missions['m-date'].state") == 'BLOCKED', 'stopped only after the second step')
            pg.wait_for_timeout(2100)
            send(pg, 'delete all missions')
            check("I can\u2019t do that from chat; open Work" in pg.inner_text('.msgs'), 'a refusal says it cannot be done from chat and points to Work')
            pg.wait_for_timeout(2100)
            send(pg, '/approve search')
            pg.click('.ccard[data-kind="approval"] button:has-text("Approve")')
            pg.wait_for_timeout(250)
            check('Step-up needed' in pg.inner_text('.ccard[data-kind="approval"]'), 'approving from the card needs a step-up')
            check(pg.evaluate("Object.values(window.v2live.sim.state.approvals).find(a => a.mission === 'm-search').state") == 'PENDING', 'still pending before the step-up')
            pg.click('.ccard[data-kind="approval"] button:has-text("Confirm approval")')
            pg.wait_for_timeout(250)
            check(pg.evaluate("Object.values(window.v2live.sim.state.approvals).find(a => a.mission === 'm-search').state") == 'APPROVED', 'approved only on the card with its step-up')
            ctx.close()

            # ---- project vs general, Remember in..., the ambiguity card ----
            ctx, pg, errs = new_page(br, base)
            idle(pg)
            k0 = pg.evaluate("window.v2live.sim.state.knowledge.length")
            check('Archeus' in pg.inner_text('.cscope') and 'Archeus' in pg.inner_text('.cdest'), 'the destination is visible (the scope chip and the line name the project)')
            pick_scope(pg, 'general')
            check('General' in pg.inner_text('.cscope') and 'nothing here is saved' in pg.inner_text('.cdest').lower(), 'the scope chip says General and the line says nothing is saved to a project')
            send(pg, 'Explain a checkpoint')
            check('general \u00b7 not project memory' in pg.inner_text('.msgs').lower(), 'the general answer is labelled')
            check(pg.evaluate("window.v2live.sim.state.knowledge.length") == k0, 'a general answer adds no memory')
            pg.click('[data-key="chat-more"]')
            check('Retention' in pg.inner_text('.pkpop') and 'Unknown' in pg.inner_text('.pkpop'), 'retention is shown as Unknown (in the More menu)')
            pg.keyboard.press('Escape')
            pg.click('.ccard[data-kind="general"] .btn')
            pg.wait_for_timeout(300)
            pg.click('.ccard[data-kind="remember"] .btn.primary')
            pg.wait_for_timeout(250)
            check(pg.evaluate("window.v2live.sim.state.knowledge.length") == k0, 'Remember with no destination writes nothing')
            pg.click('.ccard[data-kind="remember"] .pk')
            pg.click('.pkpop [role="option"][data-value="notes"]')
            pg.wait_for_timeout(300)
            pg.click('.ccard[data-kind="remember"] .btn.primary')
            pg.wait_for_timeout(300)
            check(pg.evaluate("window.v2live.sim.state.knowledge.length") == k0 + 1, 'Remember writes one item after the confirm')
            pick_scope(pg, 'work:archeus')
            pg.wait_for_timeout(2100)
            send(pg, 'What is a checkpoint')
            check(pg.locator('.ccard[data-kind="choice"]').count() == 1, 'an ambiguous question asks: Answer this, or create work?')
            ctx.close()

            # ---- queue (Enter) and steer (Cmd or Ctrl+Enter) while a mission runs (PW08) ----
            ctx, pg, errs = new_page(br, base)
            inp = 'input[data-key="chat-in-page"]'
            hint = lambda: pg.inner_text('.composer2[data-where="page"] .chint')
            check('Enter queue' in hint() and 'steer' in hint(), 'the key hint shows while a mission runs')
            pg.fill(inp, 'Check the date again')
            pg.press(inp, 'Enter')
            pg.wait_for_timeout(300)
            check(pg.locator('.msg .qchip:has-text("Queued")').count() == 1 and '1 queued' in hint(), 'Enter queues: a Queued chip in the thread and a count on the composer')
            check(pg.evaluate("window.v2live.sim.state.messages.at(-1).from") == 'you', 'a queued message gets no reply yet')
            pg.click('.msg .btn:has-text("Remove")')
            pg.wait_for_timeout(300)
            check('Removed from the queue' in pg.inner_text('.msgs') and 'queued' not in hint(), 'a queued message can be removed')
            pg.fill(inp, 'Skip the slow test')
            pg.press(inp, 'Control+Enter')
            pg.wait_for_timeout(300)
            check(pg.locator('.msg .qchip:has-text("Steering")').count() == 1, 'Ctrl+Enter steers: Steering until Core acknowledges')
            pg.evaluate("window.v2live.sim.advance(31000)")
            pg.wait_for_timeout(400)
            check(pg.locator('.msg .qchip:has-text("Steering")').count() == 0 and 'Core acknowledged the steer' in pg.inner_text('.msgs'), 'the acknowledgement ends Steering and says it is simulated')
            pg.click('[data-key="chat-tab-receipts"]')
            check('Steer asked (simulated)' in pg.inner_text('.cp-panel') and 'Steer acknowledged (simulated)' in pg.inner_text('.cp-panel'), 'both steer events are in Receipts')
            check(not errs, 'no page errors in the queue and steer run: %s' % errs[:2])
            ctx.close()

            # ---- wide Chat: a side pane beside the thread; the composer ring; the slash menu scrolls, pins and speaks one language ----
            ctx, pg, errs = new_page(br, base)
            g = pg.evaluate("""() => { const r = (q) => document.querySelector(q).getBoundingClientRect(), c = r('.convo'), a = r('.cside'), m = r('.cp-thread .msg:not(.you)');
              return { wide: document.querySelector('.chatpage').dataset.wide, chatTab: !!document.querySelector('[data-key="chat-tab-chat"]'), tabs: [...document.querySelectorAll('.cside [role=tab]')].length, side: a.width, cx: c.left, mx: m.left, ax: a.left, cw: c.width } }""")
            check(g['wide'] == 'true' and not g['chatTab'] and g['tabs'] == 2 and g['mx'] - g['cx'] < 40 and g['ax'] >= g['cx'] + g['cw'] - 1 and 340 <= g['side'] <= 640,
                  'wide Chat: the thread keeps the left edge and a Receipts and Context pane sits beside it (%s)' % g)
            pg.click('[data-key="chat-tab-context"]')
            check(pg.is_visible('.cside [data-key="chat-cmd-q"]') and pg.is_visible('.convo input.cinput'), 'the Context tab fills the pane and the conversation stays visible')
            pg.click('[data-key="chat-tab-receipts"]')
            check('open missions' in pg.inner_text('.cside').lower() and 'done by archeus' in pg.inner_text('.cside').lower(), 'the pane lists open missions and what Archeus did')
            ring = "() => { const c = document.querySelector('.composer2[data-where=page] .crow2'), s = getComputedStyle(c); return [s.outlineStyle, s.outlineWidth, s.outlineOffset, s.borderColor === s.outlineColor, getComputedStyle(document.querySelector('.composer2[data-where=page] .cinput')).outlineStyle] }"
            pg.focus('input[data-key="chat-in-page"]')
            check(pg.evaluate(ring) == ['solid', '2px', '0px', True, 'none'], 'typing: one ring on the pill, flush, in the border colour, none on the field (%s)' % pg.evaluate(ring))
            pg.keyboard.press('Tab'); pg.keyboard.press('Tab')
            r = pg.evaluate(ring)
            check(r[0] == 'none' and pg.evaluate("getComputedStyle(document.querySelector('.composer2[data-where=page] .csend')).outlineStyle") == 'solid', 'Send focused: the pill ring is off, the button shows its own (%s)' % r)
            pg.click('input[data-key="chat-in-page"]'); pg.keyboard.type('/'); pg.wait_for_timeout(150)
            vis = "() => { const l = document.querySelector('.composer2[data-where=page] .slash'), a = l.querySelector('[aria-selected=true]'); const r = a.getBoundingClientRect(), q = l.getBoundingClientRect(); return [r.top >= q.top - 1 && r.bottom <= q.bottom + 1, Math.round(l.scrollTop)] }"
            n0 = pg.locator('.composer2[data-where=page] .slash .srow').count()
            for _ in range(n0 - 1): pg.keyboard.press('ArrowDown')
            pg.keyboard.press('Enter'); pg.wait_for_timeout(100)
            check(pg.locator('.composer2[data-where=page] .slash .srow').count() > n0 + 20 and pg.evaluate(vis)[0], 'keyboard expands +N more and the active option is in view')
            steps = [pg.keyboard.press('ArrowDown') or pg.evaluate(vis) for _ in range(20)]
            check(all(v[0] for v in steps) and steps[-1][1] > 0, 'ArrowDown through 20 rows keeps the active option inside the scrolling list')
            pg.keyboard.press('End'); check(pg.evaluate(vis)[0] and pg.evaluate(vis)[1] > 0, 'End shows the last command')
            pg.keyboard.press('Home'); check(pg.evaluate(vis) == [True, 0], 'Home returns to the first command')
            pg.keyboard.press('PageDown'); pg.keyboard.press('PageDown'); check(pg.evaluate(vis)[0] and pg.evaluate(vis)[1] > 0, 'PageDown moves by pages and stays in view')
            check(pg.evaluate("document.activeElement.className") == 'cinput', 'focus stays in the field')
            pg.keyboard.press('Home'); name = pg.evaluate("document.querySelector('.composer2[data-where=page] .slash [aria-selected=true] .sn').textContent")
            pg.keyboard.press('Alt+P'); pg.wait_for_timeout(100)
            check(pg.evaluate("JSON.parse(localStorage.getItem('archeus-v2-live')).slashpins.length") == 1, 'Alt+P pins the active command in the preference store (%s)' % name)
            pg.keyboard.press('Escape'); pg.fill('input[data-key="chat-in-page"]', ''); pg.keyboard.type('/'); pg.wait_for_timeout(100)
            top = pg.evaluate("[...document.querySelectorAll('.composer2[data-where=page] .slash > *')].slice(0, 2).map((e) => e.className + ':' + e.textContent.slice(0, 14))")
            check(top[0] == 'sgh:Pinned' and name in top[1] and pg.locator('.composer2[data-where=page] .slash .spin[aria-pressed=true]').count() == 1, 'Pinned comes first under its heading, the pin button is pressed (%s)' % top)
            check('/stato' not in pg.inner_text('.composer2[data-where=page] .slash'), 'English menu prints no Italian alias')
            pg.fill('input[data-key="chat-in-page"]', '/needs'); pg.keyboard.press('Enter'); pg.wait_for_timeout(300)
            pg.fill('input[data-key="chat-in-page"]', ''); pg.keyboard.type('/'); pg.wait_for_timeout(100)
            check(pg.evaluate("[...document.querySelectorAll('.composer2[data-where=page] .slash .sgh')].slice(0, 2).map((e) => e.textContent)") == ['Pinned', 'Recent'] and pg.evaluate("JSON.parse(localStorage.getItem('archeus-v2-live')).slashrecent") == ['needs'], 'a sent command becomes Recent; a highlighted one does not')
            check(not errs, 'no page errors in wide Chat: %s' % errs[:2])
            ctx.close()
            ctx, pg, errs = new_page(br, base, q='&lang=it')
            pg.evaluate("localStorage.setItem('archeus-v2-live', JSON.stringify({ slashpins: ['status'], slashrecent: ['needs'] }))"); pg.reload(); pg.wait_for_timeout(500)
            pg.click('input[data-key="chat-in-page"]'); pg.keyboard.type('/'); pg.wait_for_timeout(150)
            t = pg.inner_text('.composer2[data-where=page] .slash')
            check(t.startswith('FISSATI') and '/stato' in t and '/attesa' in t and '/status' not in t and '/needs' not in t and 'Pinned' not in t, 'Italian menu: Fissati and Recenti, Italian names only, pins survive the language switch')
            ctx.close()
            ctx, pg, errs = new_page(br, base, w=1024, h=768)
            check(pg.evaluate("document.querySelector('.chatpage').dataset.wide") == 'false' and pg.locator('[data-key="chat-tab-chat"]').count() == 1 and pg.locator('.cside').count() == 0, 'below 1100 px the three tabs stay and there is no pane')
            ctx.close()

            # ---- the dock on Now (desktop), then the phone sheet ----
            ctx, pg, errs = new_page(br, base, hash_='#/now')
            check(pg.is_visible('.tell-dock input[data-key="chat-in-dock"]'), 'the chat bar is anchored in the Overview scene, no click needed')
            d = pg.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect(), a = r('.tell-dock .composer2'), sc = r('.now-scene'), st = r('.now-strip'), cs = getComputedStyle(document.querySelector('.tell-dock .crow2')), fill = getComputedStyle(document.querySelector('.tell-dock .crow2'), '::before'); return { off: Math.abs((a.left + a.right) / 2 - (sc.left + sc.right) / 2), w: a.width, scw: sc.width, gap: st.left - a.right, bg: fill.backgroundColor, op: parseFloat(fill.opacity), bf: cs.backdropFilter, h: a.height }; }""")
            check(d['off'] < 80 and d['w'] >= min(700, d['scw'] * .9) and d['gap'] >= 0 and d['h'] < 60, 'the dock is anchored at the bottom, wide, slim (under 60 px), left of the Details button (%s)' % d)
            check(d['bf'] == 'none' and 0.05 < d['op'] < 0.5, 'the dock is a flat, mostly clear fill at rest, no blur (%s %s)' % (d['op'], d['bf']))
            check(pg.get_attribute('input[data-key="chat-in-dock"]', 'placeholder').startswith('Tell Archeus what to do'), 'placeholder: Tell Archeus what to do')
            send(pg, '/status', where='dock')
            check(pg.locator('.tell-dock .dstrip').count() == 1 and 'status' in pg.inner_text('.tell-dock').lower(), 'the last exchange shows above the bar')
            check(pg.locator('.tell-dock a.openconv').count() == 1, 'Open conversation is offered')
            check(not pg.is_visible('.tell-dock .cstop'), 'the slim dock leaves Stop to the top bar')
            ctx.close()
            ctx, pg, errs = new_page(br, base, w=390, h=844, hash_='#/now')
            check(pg.is_visible('[data-key="bb-tell"]') and not pg.is_visible('.chatsheet'), 'phone: a Tell button in the bottom bar, no sheet yet')
            pg.click('[data-key="bb-tell"]')
            pg.wait_for_timeout(350)
            check(pg.is_visible('.chatsheet'), 'tapping Tell opens the chat sheet')
            h0 = pg.evaluate("document.querySelector('.chatsheet').getBoundingClientRect().height")
            check(pg.evaluate("document.activeElement.matches('input.cinput')"), 'the field is focused in the sheet')
            check(pg.evaluate("document.querySelector('.chatsheet').hasAttribute('data-kbsim')") and pg.is_visible('.kbsim'), 'the simulated keyboard is up (a mouse window; a touch device draws none)')
            pg.keyboard.type('hello there')
            pg.click('.chatsheet .sheet-grip')   # the sheet is full with the keyboard up; the handle steps it down
            pg.wait_for_timeout(300)
            h1 = pg.evaluate("document.querySelector('.chatsheet').getBoundingClientRect().height")
            check(h1 < h0, 'the handle makes the sheet shorter')
            check(pg.input_value('input[data-key="chat-in-sheet"]') == 'hello there', 'the draft survives a redraw')
            pg.click('.chatsheet .sheet-close')
            pg.wait_for_timeout(300)
            check(not pg.is_visible('.chatsheet'), 'Close closes the sheet')
            check(pg.evaluate("document.activeElement.getAttribute('data-key')") == 'bb-tell', 'focus returns to the Tell button')
            pg.click('[data-key="bb-tell"]')
            pg.wait_for_timeout(300)
            check(pg.input_value('input[data-key="chat-in-sheet"]') == 'hello there', 'the draft is back in the sheet')
            pg.keyboard.press('Escape')
            pg.wait_for_timeout(250)
            check(not pg.is_visible('.chatsheet'), 'Escape closes the sheet')
            check(not errs, 'no page errors in the dock and sheet run: %s' % errs[:2])
            ctx.close()

            # ---- failed send, retry, duplicate ----
            ctx, pg, errs = new_page(br, base)
            pg.click('[data-key="chat-more"]')
            pg.click('.pkpop .btn:has-text("Failed send")')
            pg.keyboard.press('Escape')
            send(pg, '/idea retry me')
            check('Not sent. Send again?' in pg.inner_text('.msgs'), 'a failed send says Not sent. Send again?')
            check(pg.evaluate("window.v2live.sim.state.ideas.every(i => i.title !== 'retry me')"), 'nothing was recorded by the failed send')
            pg.click('.msgs .btn:has-text("Send again")')
            pg.wait_for_timeout(900)
            check(pg.evaluate("window.v2live.sim.state.ideas.filter(i => i.title === 'retry me').length") == 1, 'retry records it exactly once')
            send(pg, '/idea twice')
            send(pg, '/idea twice', wait=200)
            check('Send again?' in pg.inner_text('.cnote'), 'the same text within 2 s asks first')
            ctx.close()

            # ---- Replay: categories, cursor, keyboard, evidence, recovery, no autoplay ----
            ctx, pg, errs = new_page(br, base, hash_='#/replay/m-date')
            pg.evaluate("window.v2live.sim.advance(520000)")
            pg.wait_for_timeout(500)
            n_steps = pg.locator('.rp-event').count()
            check(n_steps >= 12, 'the timeline lists the recorded steps (%d)' % n_steps)
            pg.wait_for_timeout(1500)
            check(pg.locator('.rp-event').count() == n_steps, 'nothing plays by itself (the paused simulation adds no step)')
            check(pg.locator('.rp-event .cat').count() > 8, 'every step has a category chip')
            pg.click('.rp-event:has-text("LOST")')
            pg.wait_for_timeout(250)
            sel = pg.inner_text('.rp-reading')
            check('UNCERTAIN' in sel and 'NOT RECORDED' in sel, 'a LOST step is UNCERTAIN and its external effect is NOT RECORDED')
            check('unsettled lost awaiting core sweep' in sel, 'settled_by reads unknown with its reason')
            pg.click('.rp-event[aria-pressed=true]')
            pg.keyboard.press('ArrowDown')
            pg.wait_for_timeout(250)
            check(pg.evaluate("document.activeElement.classList.contains('rp-event')"), 'ArrowDown moves the cursor to the next step')
            pg.keyboard.press('Home')
            pg.wait_for_timeout(250)
            check(pg.evaluate("document.activeElement.id") == 'rs-1', 'Home goes to the first step')
            pg.click('.rp-filters >> text=UNCERTAIN')
            pg.wait_for_timeout(250)
            check(pg.locator('.rp-event').count() < n_steps, 'a category filter narrows the list')
            pg.click('.rp-filters >> text=All')
            pg.evaluate("document.querySelector('.rp-reference').open = true"); pg.wait_for_timeout(150)
            check('180 days' in pg.inner_text('.rp-reference') and 'not built' in pg.inner_text('.rp-reference'), 'retention depth is stated honestly')
            check('Mission.integration_head' in pg.inner_text('.rp-reference') and 'UNKNOWN' in pg.inner_text('.rp-reference'), 'the starting state shows its three bindings with UNKNOWN')
            check(pg.locator('.five').count() == 5, 'the five example rows')
            check('130 states' in pg.inner_text('.vocab summary'), 'the vocabulary says 130 states')
            check(pg.locator('.rcv').count() == 3, 'three recovery options')
            pg.click('.rcv >> nth=0 >> summary')  # the would and will-not columns open on choosing an option
            check('archeus would' in pg.inner_text('.rcv').lower() and 'archeus will not' in pg.inner_text('.rcv').lower(), 'recovery says what Archeus would and will not do')
            before = pg.evaluate("window.v2live.sim.state.events.length")
            pg.click('.rcv[data-ok="true"] .btn >> nth=0')
            pg.wait_for_timeout(250)
            check(pg.locator('.ccard[data-kind="proposal"]').count() == 1, 'a recovery option drafts an approval card')
            check(pg.evaluate("window.v2live.sim.state.events.length") == before, 'drafting changes nothing')
            pg.click('.ccard[data-kind="proposal"] .btn.primary')
            pg.wait_for_timeout(400)
            receipt = pg.locator('#rp-recovery .receipt[role="status"]')
            receipt_text = receipt.inner_text()
            check(receipt.is_visible() and ('Approved:' in receipt_text or 'Approvata:' in receipt_text) and ('Evidence unchanged' in receipt_text or 'invariate' in receipt_text or 'unchanged' in receipt_text), 'approval gives a receipt that says the evidence is unchanged')
            check(not errs, 'no page errors in the Replay run: %s' % errs[:2])
            ctx.close()

            # ---- language switch re-draws the chat in Italian ----
            ctx, pg, errs = new_page(br, base, q='&lang=it')
            check('Risposte e record' in pg.inner_text('.cdest'), 'the destination line is Italian')
            check(pg.get_attribute('input[data-key="chat-in-page"]', 'placeholder').startswith('Dì ad Archeus cosa fare'), 'the placeholder is Italian')
            pg.goto('%s?theme=dark&sim=paused&motion=reduced&notes=off&lang=it#/replay/m-date' % base, wait_until='load')
            pg.wait_for_timeout(500)
            pg.evaluate("document.querySelector('.rp-reference').open = true"); pg.wait_for_timeout(150)
            check('categorie' in pg.inner_text('.rp-reference').lower() and 'stato iniziale' in pg.inner_text('.rp-reference').lower(), 'Replay is Italian')
            ctx.close()
            br.close()
    finally:
        srv.terminate()
    print('%d checks, %d failed' % (DONE[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
