"""V2 chat bar probe (build steps 1 to 3), real Chromium over the served prototype. Measures what the build-order table asks for:
step 1 composer reachable from Now on desktop, phone and terminal, no Start route, SIMULATED on every fixture result;
step 2 reply and history placement, phone sheet over the keyboard, targets of at least 48 CSS px (effective hit area), focus rings,
zero horizontal overflow at 320/360/402 and 1280/1440; step 3 natural scenarios through explicit fixture events, the four beats,
one node per identity, a repeated event adds nothing, reduced motion shows the same facts with no animation; navigation from five
start routes; zero console errors. Run (serve clients/v2-prototype first, then through the testlock):
  BASE=http://127.0.0.1:8817 OUT=<screenshot dir> py -I tools/v2_chatbar_probe.py
Exit 1 on any failed check. Not covered: a real keyboard, real touch, a screen reader, the Windows system fonts."""
import os
import sys

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

BASE = os.environ.get('BASE', 'http://127.0.0.1:8817') + '/index.html'
OUT = os.environ.get('OUT', '.')
fails = []
errors = []


def check(ok, msg):
    print(('ok   ' if ok else 'FAIL ') + msg, flush=True)
    if not ok:
        fails.append(msg)


def page(br, w, h, route='#/now', reduced=False, dpr=1):
    ctx = br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=dpr,
                         reduced_motion='reduce' if reduced else 'no-preference', color_scheme='dark')
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errors.append('pageerror %dx%d %s: %s' % (w, h, route, e)))
    pg.on('console', lambda m: errors.append('console %dx%d %s: %s' % (w, h, route, m.text)) if m.type == 'error' else None)
    pg.goto(BASE + route, wait_until='load')
    pg.evaluate('document.fonts.ready.then(() => true)')
    pg.wait_for_timeout(700)
    return ctx, pg


# Effective hit extent of every visible match: a grid of points around the element, hit-tested with elementFromPoint, so padding,
# ::after areas and covering layers all count. Returns the matches whose extent is under 48 CSS px (2 px grid tolerance).
HIT = """(sels) => {
  const STEP = 2, PAD = 36, out = [];
  document.querySelectorAll(sels).forEach(e => {
    const cs = getComputedStyle(e), b = e.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || e.closest('[hidden]') || b.width < 1 || b.height < 1) return;
    if (b.bottom <= 0 || b.top >= innerHeight || b.right <= 0 || b.left >= innerWidth) return;
    for (let p = e.parentElement; p; p = p.parentElement) {
      const o = getComputedStyle(p).overflowY;
      if ((o === 'auto' || o === 'scroll') && p.scrollHeight > p.clientHeight) { const r = p.getBoundingClientRect(); if (b.top < r.top - 0.5 || b.bottom > r.bottom + 0.5) return; break; }
    }
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    for (let y = Math.max(0, b.top - PAD); y < Math.min(innerHeight, b.bottom + PAD); y += STEP)
      for (let x = Math.max(0, b.left - PAD); x < Math.min(innerWidth, b.right + PAD); x += STEP) {
        const t = document.elementFromPoint(x, y);
        if (t && (t === e || e.contains(t))) { x0 = Math.min(x0, x); x1 = Math.max(x1, x + STEP); y0 = Math.min(y0, y); y1 = Math.max(y1, y + STEP); }
      }
    const w = x1 > x0 ? x1 - x0 : 0, h = y1 > y0 ? y1 - y0 : 0;
    if (!w && !h) return;
    if (w < 48 - STEP || h < 48 - STEP)
      out.push((e.id || e.className || e.tagName) + ' "' + (e.textContent || e.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').slice(0, 22) + '" hit ' + w + 'x' + h);
  });
  return out;
}"""

DESK_TARGETS = '#chat-input, .chatbar .slash-btn, .chatbar .send-btn, .feed-open, .chat-feed .msg-card .btn, .chat-feed .receipt, .chat-feed .promote input, .rec-lbl, .new-reply'
HIST_TARGETS = '[data-act="history-close"], .hist-body .btn, .hist-body .receipt, .hist-body .promote input'
PHONE_TARGETS = '#chat-input, .chatbar .slash-btn, .chatbar .chat-stop, .ph3-back, .ph3-expand, .chat-feed .msg-card .btn, .chat-feed .receipt, .chat-feed .promote input, .new-reply'

REPLIES = "() => [...document.querySelectorAll('#msgs > li.msg-arch, #msgs > li.msg-card, #msgs > li.msg-gen')]"
UNTAGGED = """() => [...document.querySelectorAll('#msgs > li.msg-arch, #msgs > li.msg-card, #msgs > li.msg-gen')]
  .filter(li => { const t = li.querySelector('.sim-tag'); return !t || t.textContent.trim() !== 'SIMULATED'; }).map(li => li.textContent.trim().slice(0, 50))"""
NODES = "() => window.ArchFixture.nodes()"
LAYER = """() => ({ items: document.querySelectorAll('#rec-list [data-rec]').length, groups: document.querySelectorAll('#rec-svg g[data-rec]').length,
  ids: [...document.querySelectorAll('#rec-list [data-rec]')].map(e => e.getAttribute('data-rec')),
  list: [...document.querySelectorAll('#now-list li[data-id]')].map(e => e.getAttribute('data-id')) })"""
RING = """() => { const e = document.activeElement; if (!e || e === document.body) return null; const cs = getComputedStyle(e), bar = e.closest('.chatbar');
  const bs = bar ? getComputedStyle(bar).boxShadow : 'none'; const n = (bs.match(/-?\\d+(?:\\.\\d+)?px/g) || []).map(parseFloat);
  return { key: e.id || e.getAttribute('data-act') || (typeof e.className === 'string' ? e.className : e.tagName), ow: parseFloat(cs.outlineWidth) || 0, os: cs.outlineStyle, spread: n.length > 3 ? n[3] : 0, inbar: !!bar }; }"""


def send(pg, text, wait=1100):
    pg.click('#chat-input')
    pg.fill('#chat-input', text)
    pg.keyboard.press('Enter')
    pg.wait_for_timeout(wait)


def ring_sweep(pg, want, label):
    """Tab through the page; every wanted control must be reached and show a 3 px ring (outline, or the bar's box shadow for the field)."""
    seen = {}
    pg.evaluate('document.activeElement && document.activeElement.blur()')
    for _ in range(90):
        pg.keyboard.press('Tab')
        r = pg.evaluate(RING)
        if r:
            seen[r['key']] = r
    for key in want:
        hit = [v for k, v in seen.items() if key in k]
        if not hit:
            check(False, '%s: Tab never reached %s' % (label, key))
            continue
        r = hit[0]
        ok = (r['os'] != 'none' and r['ow'] >= 3) or (r['inbar'] and r['spread'] >= 3)
        check(ok, '%s: %s shows a 3 px ring (outline %spx %s, bar shadow spread %s)' % (label, key, r['ow'], r['os'], r['spread']))


# ---------------------------------------------------------------- desktop
def desktop(br, w, h):
    tag = 'desktop %dx%d' % (w, h)
    ctx, pg = page(br, w, h)
    # step 1: the composer is on Now, there is no Start route, the disclosure is outside the art
    ph = pg.get_attribute('#chat-input', 'placeholder')
    check(ph == 'Tell Archeus what you need…', '%s: placeholder "%s"' % (tag, ph))
    check(pg.locator('#chat-input').is_visible(), '%s: the composer is visible on Now with no other step' % tag)
    note = pg.inner_text('.demo-note').strip()
    check(note == 'Demo · simulated chat · no Core actions' and pg.locator('.demo-note').is_visible(), '%s: disclosure "%s"' % (tag, note))
    pg.goto(BASE + '#/start')
    pg.wait_for_timeout(300)
    check(pg.locator('#s-now').is_visible() and pg.locator('#s-start').count() == 0, '%s: #/start opens Now, there is no Start screen' % tag)
    pg.goto(BASE + '#/now')
    pg.wait_for_timeout(300)
    check(pg.locator('#s-now').is_visible() and pg.evaluate("location.hash") == '#/now', '%s: back on Now' % tag)
    check(pg.eval_on_selector('#chat-intro', 'e => e.hidden'), '%s: the intro line stays hidden while a conversation shows' % tag)

    # step 3 first (clean state): events, nodes, beats
    pg.evaluate('window.ArchFixture.hold(true)')
    send(pg, 'Start a project called Atlas', 1000)
    check(pg.evaluate(NODES) == [], '%s: before the fixture event there are zero new nodes' % tag)
    lay = pg.evaluate(LAYER)
    check(lay['items'] == 0 and lay['groups'] == 0 and 'atlas' not in lay['list'], '%s: nothing drawn or listed before the event' % tag)
    check('Submitted.' in pg.inner_text('#msgs'), '%s: the receipt is the static text "Submitted."' % tag)
    check(pg.locator('#msgs .msg-typing').count() == 1, '%s: one receipt line while the event is held' % tag)
    pg.evaluate("""() => { window.__t0 = 0; window.__beats = {}; const mo = new MutationObserver(ms => { for (const m of ms) { const el = m.target;
        if (el.matches && el.matches('#rec-svg g[data-rec="atlas"]')) for (const b of ['b2', 'b3', 'b4', 'b5']) if (el.classList.contains(b) && !(b in window.__beats)) window.__beats[b] = performance.now() - window.__t0; } });
      mo.observe(document.getElementById('rec-svg'), { attributes: true, subtree: true, attributeFilter: ['class'] });
      window.__live = []; const lv = [...document.querySelectorAll('p.sr-only[aria-live=polite]')]; const mo2 = new MutationObserver(() => lv.forEach(p => { if (p.textContent) window.__live.push(p.textContent); }));
      lv.forEach(p => mo2.observe(p, { childList: true, characterData: true, subtree: true })); }""")
    pg.evaluate('window.__t0 = performance.now(); window.ArchFixture.hold(false)')
    pg.wait_for_timeout(1100)
    check(pg.evaluate(NODES) == ['atlas'], '%s: after the event exactly one node for Atlas (%s)' % (tag, pg.evaluate(NODES)))
    b = pg.evaluate('window.__beats')
    check(all(k in b for k in ('b2', 'b3', 'b4', 'b5')), '%s: four beats ran (%s)' % (tag, {k: round(v) for k, v in b.items()}))
    if all(k in b for k in ('b2', 'b3', 'b4', 'b5')):
        check(b['b2'] < 100 and 110 < b['b3'] < 280 and 330 < b['b4'] < 540 and 500 < b['b5'] < 720,
              '%s: beats at about 0, 160, 400, 580 ms (%s)' % (tag, {k: round(v) for k, v in b.items()}))
    dur = pg.evaluate("""() => { const g = document.querySelector('#rec-svg g[data-rec="atlas"]'); const d = s => getComputedStyle(g.querySelector(s)).transitionDuration;
      return [d('.rec-hull'), d('.rec-link'), getComputedStyle(document.querySelector('#rec-list [data-rec="atlas"]')).transitionDuration, d('.rec-halo')]; }""")
    check(dur == ['0.16s', '0.24s', '0.18s', '0.22s'], '%s: transition durations appear 160, relation 240, reading 180, accent 220 ms (%s)' % (tag, dur))
    live = pg.evaluate('window.__live')
    check(len([t for t in live if 'Atlas' in t]) == 1, '%s: one polite announcement for the creation (%s)' % (tag, live))
    before = pg.evaluate("document.querySelectorAll('#msgs > li').length")
    pg.evaluate("window.ArchFixture.emit('atlas'); window.ArchFixture.emit('atlas'); window.ArchFixture.reconnect()")
    pg.wait_for_timeout(200)
    check(pg.evaluate(NODES) == ['atlas'] and pg.evaluate("document.querySelectorAll('#msgs > li').length") == before,
          '%s: a duplicate event and a reconnect add no node and no reply' % tag)
    send(pg, 'Start a project called Atlas', 1000)
    lay = pg.evaluate(LAYER)
    check(lay['items'] == 1 and lay['list'].count('atlas') == 1 and 'already exists' in pg.inner_text('#msgs'), '%s: the same request again adds no second node' % tag)
    send(pg, 'Add a mission "Draft the brief" to Atlas', 1000)
    pg.locator('.chat-feed [data-card="start"]').last.click()
    check(pg.evaluate(UNTAGGED) == [] and 'Started' in pg.text_content('#msgs'), '%s: a card that rewrites its own text keeps SIMULATED' % tag)
    send(pg, 'Add an idea "Offline mode" to Atlas', 1000)
    send(pg, 'Add an idea "Voice notes"', 1000)
    lay = pg.evaluate(LAYER)
    check(lay['ids'] == ['atlas', 'm-draft-the-brief', 'i-offline-mode', 'i-voice-notes'] and lay['groups'] == 4, '%s: one node per identity (%s)' % (tag, lay['ids']))
    check(all(lay['list'].count(i) == 1 for i in lay['ids']), '%s: each identity once in the text list' % tag)
    txt = pg.inner_text('#rec-list')
    check('Not started' in txt and 'Idea · not a commitment' in txt and 'Project · 2 items' in txt, '%s: labels say Not started, Idea · not a commitment, Project · 2 items' % tag)
    check('Mission ‘Draft the brief’ created in Atlas. Not started.' in pg.text_content('#msgs'), '%s: the mission reply says Not started, and the record is not started' % tag)
    check(not pg.evaluate("document.querySelector('#now-overview') && !document.querySelector('#now-overview').hidden"), '%s: no camera move (the whole-space control never appeared)' % tag)
    pg.click('[data-show="i-voice-notes"]')
    check(pg.evaluate("document.querySelectorAll('#rec-layer .is-shown').length") >= 2 and pg.eval_on_selector('#now-overview', 'e => e.hidden'),
          '%s: Show marks the same identity, the camera stays' % tag)
    pg.screenshot(path=os.path.join(OUT, 'chatbar_%s_created.png' % tag.replace(' ', '_')))

    # step 1: every fixture result says SIMULATED
    for t in ['What is a replay?', 'Change the daily spend limit to 20 EUR', 'Run the notes index', '/status', '/stop', '/remember I prefer tabs', '/general why', '/feedback x', '?']:
        send(pg, t, 1000)
    pg.click('#chat-input')
    pg.fill('#chat-input', '')
    bad = pg.evaluate(UNTAGGED)
    check(bad == [], '%s: every reply, card and answer carries SIMULATED (%d replies, untagged %s)' % (tag, len(pg.evaluate(REPLIES)), bad))

    # step 2: placement of replies and history
    r = pg.evaluate("""() => { const f = document.querySelector('#feed').getBoundingClientRect(), b = document.querySelector('#chat-form').getBoundingClientRect();
      return { fl: f.left, fw: f.width, fb: f.bottom, bl: b.left, bw: b.width, bt: b.top, vis: [...document.querySelectorAll('#msgs > li')].filter(li => li.offsetParent !== null).length,
        total: document.querySelectorAll('#msgs > li').length }; }""")
    check(abs(r['fl'] - r['bl']) <= 2 and abs(r['fw'] - r['bw']) <= 2 and r['fb'] <= r['bt'] + 0.5, '%s: replies sit right above the bar in the same column' % tag)
    check(560 <= r['bw'] <= 760, '%s: the bar is %d CSS px wide (560 to 760)' % (tag, round(r['bw'])))
    check(r['vis'] < r['total'] and 'Open a mission in Notes' not in pg.evaluate("[...document.querySelectorAll('#msgs > li')].filter(li => li.offsetParent !== null).map(li => li.textContent).join(' ')"),
          '%s: only the last exchange is visible (%d of %d lines)' % (tag, r['vis'], r['total']))
    check(pg.evaluate('document.documentElement.scrollWidth <= innerWidth'), '%s: no horizontal overflow' % tag)
    bad = pg.evaluate(HIT, DESK_TARGETS)
    check(bad == [], '%s: chat targets are 48 CSS px or more (%s)' % (tag, bad))
    pg.click('#feed-open')
    pg.wait_for_timeout(300)
    hp = pg.evaluate("""() => { const p = document.querySelector('#history').getBoundingClientRect(), s = document.querySelector('.shell').getBoundingClientRect();
      return { w: p.width, l: p.left, sr: s.right, n: document.querySelectorAll('.hist-body #msgs > li').length, seed: document.querySelector('.hist-body').textContent.includes('Open a mission in Notes'),
        feedHidden: getComputedStyle(document.querySelector('#feed')).display === 'none', over: document.documentElement.scrollWidth <= innerWidth,
        exp: document.querySelector('#feed-open').getAttribute('aria-expanded') }; }""")
    check(360 <= hp['w'] <= 420, '%s: the conversation panel is %d px wide (360 to 420)' % (tag, round(hp['w'])))
    check(hp['sr'] <= hp['l'] + 1, '%s: the scene is rescaled beside the panel, no overlap (scene right %d, panel left %d)' % (tag, round(hp['sr']), round(hp['l'])))
    check(hp['seed'] and hp['n'] >= 10 and hp['feedHidden'] and hp['over'], '%s: the panel holds the whole conversation, no overflow' % tag)
    bad = pg.evaluate(HIT, HIST_TARGETS)
    check(bad == [], '%s: panel targets are 48 CSS px or more (%s)' % (tag, bad))
    pg.screenshot(path=os.path.join(OUT, 'chatbar_%s_history.png' % tag.replace(' ', '_')))
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    check(pg.eval_on_selector('#history', 'e => e.hidden') and pg.evaluate('document.activeElement.id') == 'feed-open', '%s: Escape closes the panel and returns focus to Open conversation' % tag)
    check(pg.evaluate("document.querySelectorAll('#feed #msgs > li').length") == r['total'], '%s: the conversation is back in the reply surface' % tag)
    ring_sweep(pg, ['chat-input', 'slash-open', 'feed-open'], tag)
    pg.focus('#chat-input')
    pg.keyboard.type('/')
    pg.wait_for_timeout(100)
    check(not pg.evaluate("document.getElementById('slash-menu').hidden"), '%s: "/" opens the command menu above the bar' % tag)
    pg.keyboard.press('Escape')
    pg.fill('#chat-input', '')
    pg.click('.slash-btn')
    check(not pg.evaluate("document.getElementById('slash-menu').hidden"), '%s: the "/" button opens the menu' % tag)
    pg.keyboard.press('Escape')
    ctx.close()


def terminal(br):
    ctx, pg = page(br, 1296, 755, '#/terminal')
    check(pg.locator('#term-tell').is_visible(), 'terminal: the Tell Archeus line is visible')
    check(pg.inner_text('.term-tell label').strip().startswith('Tell Archeus'), 'terminal: the line is labelled "Tell Archeus >"')
    pg.click('#term-tell')
    pg.fill('#term-tell', 'Start a project called Atlas')
    pg.keyboard.press('Enter')
    pg.wait_for_timeout(1700)
    rep = pg.inner_text('#term-reply')
    check('SIMULATED' in rep and 'Atlas' in rep, 'terminal: the reply is text in its own area, marked SIMULATED (%s)' % rep.strip()[:70])
    check(pg.evaluate(NODES) == ['atlas'], 'terminal: the same chat made one node')
    pg.fill('#term-tell', '/xyz')
    pg.keyboard.press('Enter')
    n = pg.evaluate("document.querySelectorAll('#msgs > li').length")
    pg.wait_for_timeout(200)
    check('Unknown command' in pg.inner_text('#slash-note') and pg.evaluate("document.querySelectorAll('#msgs > li').length") == n,
          'terminal: an unknown command shows the help line and sends nothing')
    ctx.close()


# ---------------------------------------------------------------- phone
def phone(br, w, h):
    tag = 'phone %dx%d' % (w, h)
    ctx, pg = page(br, w, h, dpr=2)
    check(pg.evaluate('document.documentElement.scrollWidth <= innerWidth'), '%s: no horizontal overflow on the Overview' % tag)
    check(pg.get_attribute('#chat-input', 'placeholder').startswith('Tell Archeus'), '%s: the composer is on Now' % tag)
    d = pg.inner_text('.demo-note').strip()
    r = pg.evaluate("(() => { const n = document.querySelector('.demo-note').getBoundingClientRect(), b = document.querySelector('#chat-form').getBoundingClientRect(); return [n.top, n.bottom, b.bottom, innerHeight]; })()")
    check(d == 'Demo · simulated chat · no Core actions' and r[0] >= r[2] - 1 and r[1] <= r[3], '%s: the disclosure sits under the bar, inside the screen' % tag)
    bad = pg.evaluate(HIT, '#chat-input, .chatbar .slash-btn, .chatbar .chat-stop')
    check(bad == [], '%s: Overview bar targets are 48 CSS px or more (%s)' % (tag, bad))
    # Tab to the composer on the open Overview: ring
    pg.evaluate('document.activeElement && document.activeElement.blur()')
    for _ in range(40):
        pg.keyboard.press('Tab')
        if pg.evaluate('document.activeElement.id') == 'chat-input':
            break
    rg = pg.evaluate(RING)
    check(rg and rg['inbar'] and rg['spread'] >= 3, '%s: the composer shows a 3 px ring on the Overview (spread %s)' % (tag, rg and rg['spread']))
    pg.click('#chat-input')
    pg.wait_for_timeout(400)
    st = pg.evaluate("""() => { const s = document.querySelector('.ph-sheet-bg').getBoundingClientRect(), b = document.querySelector('#chat-form').getBoundingClientRect(), f = document.querySelector('#feed').getBoundingClientRect();
      return { top: s.top, bt: b.top, bb: b.bottom, fb: f.bottom, ft: f.top, ih: innerHeight, frame: document.querySelector('#s-now').dataset.frame, full: document.body.classList.contains('kb-open') }; }""")
    check(st['frame'] == '3' and st['full'] and st['top'] <= 30, '%s: the field opens the chat sheet, taller while the keyboard is up (sheet top %d)' % (tag, round(st['top'])))
    check(st['fb'] <= st['bt'] + 1 and st['bb'] <= st['ih'], '%s: replies end above the composer, the composer is inside the screen' % tag)
    pg.evaluate("document.documentElement.style.setProperty('--kb', '%dpx')" % int(h * 0.34))
    pg.wait_for_timeout(200)
    st2 = pg.evaluate("(() => { const b = document.querySelector('#chat-form').getBoundingClientRect(), f = document.querySelector('#feed').getBoundingClientRect(); return [b.bottom, f.bottom, f.height, innerHeight]; })()")
    check(st2[0] <= st2[3] - int(h * 0.34) + 1 and st2[1] <= st2[0] and st2[2] >= 120, '%s: with a keyboard of %d px the composer is above it and the replies keep room (%s)' % (tag, int(h * 0.34), [round(v) for v in st2]))
    pg.screenshot(path=os.path.join(OUT, 'chatbar_%s_keyboard.png' % tag.replace(' ', '_')))
    pg.evaluate("document.documentElement.style.setProperty('--kb', '0px')")
    pg.fill('#chat-input', 'a draft I have not sent')
    pg.evaluate('document.activeElement.blur()')
    pg.wait_for_timeout(300)
    s3 = pg.evaluate("(() => { const s = document.querySelector('.ph-sheet-bg').getBoundingClientRect(); return [(innerHeight - s.top) / innerHeight, document.body.classList.contains('kb-open')]; })()")
    check(not s3[1] and 0.38 <= s3[0] <= 0.5, '%s: with the keyboard closed the sheet is about 45 percent of the screen (%.2f)' % (tag, s3[0]))
    pg.screenshot(path=os.path.join(OUT, 'chatbar_%s_sheet.png' % tag.replace(' ', '_')))
    bad = pg.evaluate(HIT, PHONE_TARGETS)
    check(bad == [], '%s: sheet targets are 48 CSS px or more (%s)' % (tag, bad))
    pg.click('.ph3-expand')
    check(pg.get_attribute('.ph3-expand', 'aria-expanded') == 'true' and pg.evaluate("document.querySelector('#s-now').classList.contains('sheet-full')"), '%s: Expand opens the sheet fully' % tag)
    pg.click('.ph3-expand')
    ring_sweep(pg, ['chat-input', 'slash-open'], tag + ' sheet')
    check(pg.evaluate('document.documentElement.scrollWidth <= innerWidth'), '%s: no horizontal overflow with the sheet open' % tag)
    # creation while the scene is behind the sheet: a text receipt, the count chip, no camera, Show leads to the list
    pg.evaluate("document.getElementById('chat-input').value = ''")
    send(pg, 'Start a project called Atlas', 1100)
    check('SIMULATED' in pg.inner_text('#msgs > li:last-child') and pg.locator('#msgs [data-show="atlas"]').count() == 1, '%s: the receipt is text with a Show link' % tag)
    check(pg.evaluate("document.querySelector('#now-overview') ? document.querySelector('#now-overview').hidden : true"), '%s: no camera move for a creation behind the sheet' % tag)
    pg.fill('#chat-input', 'a draft I have not sent')
    pg.evaluate('document.activeElement.blur()')
    pg.wait_for_timeout(300)
    pg.click('.ph3-back')
    pg.wait_for_timeout(400)
    after = pg.evaluate("""() => ({ frame: document.querySelector('#s-now').dataset.frame, open: document.querySelector('#feed').classList.contains('is-open'),
      active: document.activeElement.id, draft: document.getElementById('chat-input').value, chip: document.querySelector('.ov-chip .ov-chip-text') && document.querySelector('.ov-chip .ov-chip-text').textContent,
      fresh: !!document.querySelector('.ov-chip.is-fresh') })""")
    check(after['frame'] == '1' and not after['open'] and after['active'] == 'chat-form', '%s: Back closes the sheet and returns focus to the Tell bar' % tag)
    check(after['draft'] == 'a draft I have not sent', '%s: the draft is kept' % tag)
    check(after['fresh'] and after['chip'] == '3 more projects', '%s: back on the Overview the count shows the new project, marked statically (%s)' % (tag, after['chip']))
    pg.screenshot(path=os.path.join(OUT, 'chatbar_%s_back.png' % tag.replace(' ', '_')))
    pg.click('.ov-chip')
    pg.wait_for_timeout(300)
    lst = pg.evaluate("[...document.querySelectorAll('#now-sheet [data-proj-row]')].map(e => e.getAttribute('data-proj-row'))")
    check(lst.count('atlas') == 1, '%s: the All work list holds Atlas once' % tag)
    ctx.close()


def reduced(br):
    for reduce in (False, True):
        tag = 'reduced motion' if reduce else 'motion on'
        ctx, pg = page(br, 1296, 755, reduced=reduce)
        send(pg, 'Start a project called Atlas', 1100)
        send(pg, 'Add a mission "Draft the brief" to Atlas', 1100)
        send(pg, 'Add an idea "Voice notes"', 900)
        facts = pg.evaluate("""() => ({ ids: window.ArchFixture.nodes(), labels: [...document.querySelectorAll('#rec-list .rec-lbl')].map(e => e.textContent.trim().replace(/\\s+/g, ' ')),
          replies: [...document.querySelectorAll('#msgs > li.msg-arch')].slice(-3).map(e => e.textContent.replace(/\\s+/g, ' ').trim()),
          beats: [...document.querySelectorAll('#rec-svg g[data-rec]')].map(g => ['b2', 'b3', 'b4', 'b5'].every(c => g.classList.contains(c))), motion: document.getElementById('rec-layer').dataset.motion,
          anims: document.getAnimations().length, accent: [...document.querySelectorAll('#rec-svg .rec-halo')].map(h => getComputedStyle(h).display) })""")
        if reduce:
            ref = globals().get('_REF')
            check(facts['motion'] == 'none' and all(facts['beats']) and facts['anims'] == 0, 'reduced motion: every beat is already done, zero animations (%s, anims %d)' % (facts['motion'], facts['anims']))
            check(all(a == 'none' for a in facts['accent']), 'reduced motion: no transient accent')
            check(ref is not None and ref['ids'] == facts['ids'] and ref['labels'] == facts['labels'] and ref['replies'] == facts['replies'], 'reduced motion: the same ids, labels and replies as with motion')
            quick = pg.evaluate("""() => { window.ArchFixture.hold(true); return true; }""")
            send(pg, 'Add a mission "Second one" to Atlas', 700)
            pg.evaluate('window.ArchFixture.hold(false)')
            check(pg.evaluate('document.getAnimations().length') == 0 and 'm-second-one' in pg.evaluate(NODES), 'reduced motion: a creation right now shows at once and starts no animation')
        else:
            globals()['_REF'] = facts
        ctx.close()
    ctx, pg = page(br, 1296, 755)
    pg.evaluate("localStorage.setItem('archeus.v2.motion', 'quiet')")
    send(pg, 'Start a project called Atlas', 1000)
    check(pg.get_attribute('#rec-layer', 'data-motion') == 'none' and pg.evaluate('document.getAnimations().length') == 0, 'Quiet: the same facts with no motion and no accent')
    ctx.close()


NAV_ROUTES = ['#/now', '#/shared', '#/replay/m-date', '#/mission/m-date', '#/terminal']


def nav(br, w, h):
    tag = 'nav %dx%d' % (w, h)
    miss, total = [], 0
    for route in NAV_ROUTES:
        ctx, pg = page(br, w, h, route)
        hrefs = pg.evaluate("""() => [...new Set([...document.querySelectorAll('a[href^="#/"]')].filter(a => { const b = a.getBoundingClientRect(), cs = getComputedStyle(a);
          return b.width > 0 && b.height > 0 && cs.visibility !== 'hidden' && !a.closest('[hidden]') && b.bottom > 0 && b.right > 0 && b.top < innerHeight && b.left < innerWidth; }).map(a => a.getAttribute('href')))]""")
        for href in hrefs:
            pg.evaluate("location.hash = '%s'" % route)
            pg.wait_for_timeout(250)
            sel = 'a[href="%s"]' % href
            loc = pg.locator(sel + ':visible').first
            total += 1
            try:
                loc.click(timeout=1500)
                pg.wait_for_timeout(120)
                if pg.evaluate('location.hash') != href and not (href.count('/') >= 2 and pg.evaluate('location.hash').startswith(href.split('/')[0] + '/' + href.split('/')[1])):
                    miss.append('%s -> %s landed on %s' % (route, href, pg.evaluate('location.hash')))
            except PWTimeout:
                miss.append('%s -> %s blocked' % (route, href))
        ctx.close()
    check(len(miss) <= 2, '%s: %d of %d in-app links land where they say (misses: %s)' % (tag, total - len(miss), total, miss))


def main():
    only = os.environ.get('ONLY')
    with sync_playwright() as p:
        br = p.chromium.launch()
        if only == 'nav':
            nav(br, 1296, 755)
            nav(br, 402, 874)
            br.close()
            check(not errors, 'zero console and page errors (%s)' % errors[:3])
            sys.exit(1 if fails else 0)
        for w, h in ((1280, 720), (1440, 900)):
            desktop(br, w, h)
        terminal(br)
        for w, h in ((320, 568), (360, 740), (402, 874)):
            phone(br, w, h)
        reduced(br)
        nav(br, 1296, 755)
        nav(br, 402, 874)
        br.close()
    check(not errors, 'zero console and page errors (%s)' % errors[:3])
    if fails:
        print('FAILED %d' % len(fails))
        sys.exit(1)
    print('OK chat bar probe')


if __name__ == '__main__':
    main()
