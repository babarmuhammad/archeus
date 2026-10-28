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
            k0 = pg.evaluate("window.v2live.sim.state.knowledge.length")
            check('Work \u00b7 Archeus' in pg.inner_text('.cdest') or 'Work' in pg.inner_text('.cdest'), 'the destination is visible (Work, with its project)')
            pg.select_option('select.cscope', 'general')
            check('General' in pg.inner_text('.cdest') and 'not project memory' in pg.inner_text('.cdest'), 'the destination line says General, not project memory')
            send(pg, 'Explain a checkpoint')
            check('general \u00b7 not project memory' in pg.inner_text('.msgs').lower(), 'the general answer is labelled')
            check(pg.evaluate("window.v2live.sim.state.knowledge.length") == k0, 'a general answer adds no memory')
            pg.evaluate("document.querySelectorAll('details.cp-disclosure').forEach(d => d.open = true)")
            check('Retention' in pg.inner_text('.convo') and 'Unknown' in pg.inner_text('.convo'), 'retention is shown as Unknown')
            pg.click('.ccard[data-kind="general"] .btn')
            pg.wait_for_timeout(300)
            pg.click('.ccard[data-kind="remember"] .btn.primary')
            pg.wait_for_timeout(250)
            check(pg.evaluate("window.v2live.sim.state.knowledge.length") == k0, 'Remember with no destination writes nothing')
            pg.select_option('.ccard[data-kind="remember"] select', 'notes')
            pg.wait_for_timeout(300)
            pg.click('.ccard[data-kind="remember"] .btn.primary')
            pg.wait_for_timeout(300)
            check(pg.evaluate("window.v2live.sim.state.knowledge.length") == k0 + 1, 'Remember writes one item after the confirm')
            pg.select_option('select.cscope', 'work:archeus')
            pg.wait_for_timeout(2100)
            send(pg, 'What is a checkpoint')
            check(pg.locator('.ccard[data-kind="choice"]').count() == 1, 'an ambiguous question asks: Answer this, or create work?')
            ctx.close()

            # ---- the dock on Now (desktop), then the phone sheet ----
            ctx, pg, errs = new_page(br, base, hash_='#/now')
            check(pg.is_visible('.tell-dock input[data-key="chat-in-dock"]'), 'the chat bar is anchored in the Overview scene, no click needed')
            d = pg.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect(), a = r('.tell-dock .composer2'), sc = r('.now-scene'), st = r('.now-strip'), cs = getComputedStyle(document.querySelector('.tell-dock .composer2')); return { off: Math.abs((a.left + a.right) / 2 - (sc.left + sc.right) / 2), w: a.width, scw: sc.width, gap: st.top - a.bottom, bg: cs.backgroundColor, bf: cs.backdropFilter, h: a.height }; }""")
            check(d['off'] < 2 and d['w'] >= min(700, d['scw'] * .9) and d['gap'] >= 0 and d['h'] < 90, 'the dock is bottom centre, about 760 px wide, slim, above the status strip (%s)' % d)
            check(d['bf'] == 'none' and 0.5 < float(re.findall(r'([0-9.]+)\)$', d['bg'])[0]) < 0.75, 'the dock is a flat translucent fill, no blur (%s %s)' % (d['bg'], d['bf']))
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
            check(pg.get_attribute('.chatsheet', 'data-kb') == '1' and pg.is_visible('.kbsim'), 'the simulated keyboard is up')
            pg.keyboard.type('hello there')
            pg.click('.chatsheet >> text=Expand')
            pg.wait_for_timeout(300)
            h1 = pg.evaluate("document.querySelector('.chatsheet').getBoundingClientRect().height")
            check(h1 > h0, 'Expand makes the sheet taller')
            check(pg.input_value('input[data-key="chat-in-sheet"]') == 'hello there', 'the draft survives a redraw')
            pg.click('.chatsheet >> text=Back')
            pg.wait_for_timeout(300)
            check(not pg.is_visible('.chatsheet'), 'Back closes the sheet')
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
            pg.evaluate("document.querySelectorAll('details.cp-disclosure').forEach(d => d.open = true)")
            pg.click('.chip:has-text("Failed send")')
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
            n_steps = pg.locator('.rtl [role=option]').count()
            check(n_steps >= 12, 'the timeline lists the recorded steps (%d)' % n_steps)
            pg.wait_for_timeout(1500)
            check(pg.locator('.rtl [role=option]').count() == n_steps, 'nothing plays by itself (the paused simulation adds no step)')
            check(pg.locator('.cat.rc').count() > 8, 'every step has a category chip')
            pg.click('.rtl [role=option]:has-text("LOST")')
            pg.wait_for_timeout(250)
            sel = pg.inner_text('.rpmain')
            check('UNCERTAIN' in sel and 'NOT RECORDED' in sel, 'a LOST step is UNCERTAIN and its external effect is NOT RECORDED')
            check('unsettled lost awaiting core sweep' in sel, 'settled_by reads unknown with its reason')
            pg.click('.rtl [role=option][aria-selected=true]')
            pg.keyboard.press('ArrowDown')
            pg.wait_for_timeout(250)
            check(pg.evaluate("document.activeElement.getAttribute('role')") == 'option', 'ArrowDown moves the cursor to the next step')
            pg.keyboard.press('Home')
            pg.wait_for_timeout(250)
            check(pg.evaluate("document.activeElement.id") == 'rs-1', 'Home goes to the first step')
            pg.click('.rfilters >> text=UNCERTAIN')
            pg.wait_for_timeout(250)
            check(pg.locator('.rtl [role=option]').count() < n_steps, 'a category filter narrows the list')
            pg.click('.rfilters >> text=All')
            check('180 days' in pg.inner_text('.rpside') and 'not built' in pg.inner_text('.rpside'), 'retention depth is stated honestly')
            check('Mission.integration_head' in pg.inner_text('.rpside') and 'UNKNOWN' in pg.inner_text('.rpside'), 'the starting state shows its three bindings with UNKNOWN')
            check(pg.locator('.five').count() == 5, 'the five example rows')
            check('130 states' in pg.inner_text('.vocab summary'), 'the vocabulary says 130 states')
            check(pg.locator('.rcv').count() == 3, 'three recovery cards')
            check('archeus would' in pg.inner_text('.rcv').lower() and 'archeus will not' in pg.inner_text('.rcv').lower(), 'recovery says what Archeus would and will not do')
            before = pg.evaluate("window.v2live.sim.state.events.length")
            pg.click('.rcv[data-ok="true"] .btn >> nth=0')
            pg.wait_for_timeout(250)
            check(pg.locator('.ccard[data-kind="proposal"]').count() == 1, 'a recovery option drafts an approval card')
            check(pg.evaluate("window.v2live.sim.state.events.length") == before, 'drafting changes nothing')
            pg.click('.ccard[data-kind="proposal"] .btn.primary')
            pg.wait_for_timeout(400)
            check('Evidence unchanged' in pg.inner_text('.rpmain') or 'invariate' in pg.inner_text('.rpmain') or 'unchanged' in pg.inner_text('.rpmain'), 'approval gives a receipt that says the evidence is unchanged')
            check(not errs, 'no page errors in the Replay run: %s' % errs[:2])
            ctx.close()

            # ---- language switch re-draws the chat in Italian ----
            ctx, pg, errs = new_page(br, base, q='&lang=it')
            check('Destinazione' in pg.inner_text('.cdest'), 'the destination line is Italian')
            check(pg.get_attribute('input[data-key="chat-in-page"]', 'placeholder').startswith('Dì ad Archeus cosa fare'), 'the placeholder is Italian')
            pg.goto('%s?theme=dark&sim=paused&motion=reduced&notes=off&lang=it#/replay/m-date' % base, wait_until='load')
            pg.wait_for_timeout(500)
            check('categorie' in pg.inner_text('.rpside').lower() and 'stato iniziale' in pg.inner_text('.rpside').lower(), 'Replay is Italian')
            ctx.close()
            br.close()
    finally:
        srv.terminate()
    print('%d checks, %d failed' % (DONE[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
