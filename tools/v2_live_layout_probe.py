"""V2 Live layout probe: every route and overlay of clients/v2-live at 14 viewport sizes in dark and light, counting defects.

Defects counted (each with its own column in the table):
  overlap   two visible interactive or text boxes cover each other (nesting, such as text inside its own button, is not overlap)
  clipped   a box is cut off or sticks out of the viewport horizontally (not inside an intentional horizontal scroller)
  hscroll   the page itself scrolls sideways
  target    an interactive element under 44 px (48 px for primary controls when the window is 1024 px or wider); the button system's ::after hit area counts
  wraps     a button, chip or tab whose label breaks onto a second line
  covered   the element at the centre of a control is not the control (something sits on top of it)
  contrast  text under 4.5:1 against its effective background (computed colours)
  error     a page error or a console error

It serves clients/v2-live from its own http.server on a free port and stops only that server.
Run it through the shared lock, from the worktree root:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_layout_probe.py
  options: --themes dark,light  --lang en|it  --notes on|off  --viewports 390x844,1440x900  --routes now,work  --shots <dir>  --verbose  --no-overlays
Exit code 1 when any defect is found.
"""
import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections import OrderedDict

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, 'clients', 'v2-live')

VIEWPORTS = ['320x640', '390x844', '430x932', '600x800', '768x1024', '1024x768', '1280x720', '1366x768', '1440x900', '1536x864',
             '1920x1080', '2000x930', '2560x1080', '2560x1440']
ROUTES = ['now', 'work', 'replay/m-date', 'chat', 'settings', 'security', 'health', 'usage', 'accounts', 'extensions', 'terminal', 'work/m-date', 'work/m-export', 'work/a-1', 'chat-slash', 'chat-confirm', 'chat-cards', 'chat-general', 'chat-picker', 'chat-mission', 'chat-more', 'chat-receipts', 'chat-context', 'dock-slash', 'dock-reply', 'sheet', 'sheet-slash', 'replay-ev', 'replay-rec', 'replay-pick',
          'terminal/work', 'terminal/attention', 'terminal/m-date', 'terminal/a-1', 'terminal/replay', 'terminal/accounts', 'terminal/security',
          'tui:help', 'tui:cmd', 'tui:confirm', 'tui:ansi', 'tui:hc', 'tui:mono', 'tui:ascii', 'tui:read',
          # S3: inspectors, tabs, offline and confirm states ("~state" runs STATES[state] first); the ~adv states advance the simulation and so come last
          'work/m-date~why', 'work/m-date~relations', 'work/m-date~timeline', 'work/m-date~plan', 'work/a-1~policy', 'work/a-1~confirm', 'work/x-date-1', 'work/t-date-1', 'work/p-search-v1', 'work/v-1',
          'work/i-1', 'work/k-4', 'work/prj-archeus', 'projects', 'projects/prj-archeus', 'projects/prj-notes', 'projects~offline', 'work/rd-t-date-1', 'security/sec-b5', 'extensions/h-1', 'extensions/h-1~confirm', 'extensions/mcp-1', 'extensions/mcp-live-4', 'extensions/ag-1', 'extensions/au-3', 'accounts/acc-personal', 'accounts/acc-personal~usage',
          'accounts/mdl-claude-sonnet', 'health/chk-accounts', 'security~confirm', 'now~offline', 'work~offline', 'work/m-date~offline', 'work~pinned', 'now~ask', 'now~help', 'now~details', 'now~toast', 'chat~toast',
          'security~adv', 'health~adv', 'usage~adv', 'security/bk-codex~adv', 'now~adv', 'extensions~adv', 'settings~estop', 'now~estop', 'security~estop', 'terminal/security~estop',
          # S1: the safety popover, its two-step Stop, the Tell overlay
          'now~safety', 'settings~safety', 'now~stopask', 'work~tell', 'now~estopsafety']
# terminal states that need keys or a look: (keys sent to the terminal's controller, preferences)
TUI = {'tui:help': ('?', {}), 'tui:cmd': (':', {}), 'tui:confirm': ('a enter A', {}), 'tui:ansi': ('', {'look': 'ansi'}), 'tui:hc': ('', {'look': 'hc'}), 'tui:mono': ('', {'look': 'mono'}),
       'tui:ascii': ('', {'ascii': True}), 'tui:read': ('', {'linear': True})}
TUI_RESET = "() => { const c = window.v2live.ui.tui.ctl; c.setPrefs({ look: 'app', ascii: false, linear: false }); c.state.mode = null; c.go('now'); window.v2live.ui.tui.redraw(); }"
TUI_SET = "([keys, prefs]) => { const c = window.v2live.ui.tui.ctl; c.setPrefs(prefs); if (keys) c.keys(keys); window.v2live.ui.tui.redraw(); }"
OVERLAYS = ['menu:device', 'menu:theme', 'menu:sim', 'device:all']
KINDS = ['overlap', 'clipped', 'hscroll', 'target', 'wraps', 'covered', 'contrast', 'narrow', 'error']

STATES = {
    'why': "window.v2live.ui.tab = 'why'",
    'relations': "window.v2live.ui.tab = 'relations'",
    'timeline': "window.v2live.ui.tab = 'timeline'",
    'plan': "window.v2live.ui.tab = 'plan'",
    'policy': "window.v2live.ui.tab = 'policy'",
    'usage': "window.v2live.ui.tab = 'usage'",
    'offline': "window.v2live.areas.goOffline()",
    'pinned': "window.v2live.areas.togglePin('m-date'); window.v2live.areas.togglePin('i-1')",
    'adv': "window.v2live.sim.advance(700000)",
    'safety': "document.querySelector('[data-key=safety]').click()",
    'stopask': "document.querySelector('[data-key=stop], [data-key=bb-stop]').click()",
    'tell': "document.querySelector('[data-key=tell], [data-key=bb-tell]').click()",
    'details': "document.querySelector('.now-toggle').click()",
    'estopsafety': "window.v2live.sim.advance(60000); window.v2live.sim.act('estop'); document.querySelector('[data-key=stop], [data-key=bb-stop]').click()",
    'ask': "window.v2live.ui.estopAsk = true",
    'help': "window.v2live.help()",
    'toast': "window.v2live.toast('Not done: Nothing is paused', { action: { label: 'Open Settings', href: '#/settings' } })",
    'estop': "window.v2live.sim.advance(60000); window.v2live.sim.act('estop')",
    'confirm': "(() => { const b = document.querySelector('[data-key^=\"trip-\"], .decide.danger, .ax-sw[aria-checked=true]'); if (b) b.click(); })()",
}
RESET = "(() => { window.v2live.areas.reconnect(); window.v2live.ui.tab = 'outcome'; window.v2live.ui.confirm = null; window.v2live.ui.nowDrawer = false; window.v2live.ui.estopAsk = window.v2live.ui.rearmAsk = false; document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); const tt = document.querySelector('.toast'); if (tt) tt.hidden = true; const A = window.v2live.areas; A.X.pins.slice().forEach((p) => A.togglePin(p)); })()"

MEASURE = r"""
(opts) => {
  const vw = innerWidth, vh = innerHeight, out = [];
  const add = (kind, msg) => out.push({ kind, msg });
  const layer = opts.layer ? document.querySelector(opts.layer) : null;
  const inLayer = (el) => !layer || layer.contains(el);
  const primary = '.btn.primary, .btn.decide, .nav-item, .send';
  const vis = (el) => el.checkVisibility({ checkVisibilityCSS: true });
  const name = (el) => { let s = el.tagName.toLowerCase(); if (el.id) s += '#' + el.id; else if (el.className && typeof el.className === 'string') s += '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.'); return s; };
  const inter = (a, b) => { const l = Math.max(a.left, b.left), t = Math.max(a.top, b.top), r = Math.min(a.right, b.right), bt = Math.min(a.bottom, b.bottom); return r > l && bt > t ? { left: l, top: t, right: r, bottom: bt, width: r - l, height: bt - t } : null; };
  const scrollerX = (el) => { for (let a = el.parentElement; a && a !== document.documentElement; a = a.parentElement) { const o = getComputedStyle(a).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };
  const clipOf = (el) => { // starts at the element itself: a line clamped text (overflow hidden on its own box) is not visible below the clamp
    let c = { left: 0, top: 0, right: vw, bottom: vh, width: vw, height: vh };
    for (let a = el; a && a !== document.documentElement; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if (cs.overflowX === 'visible' && cs.overflowY === 'visible') continue;
      const r = a.getBoundingClientRect();
      const box = { left: cs.overflowX !== 'visible' ? r.left : -1e9, right: cs.overflowX !== 'visible' ? r.right : 1e9, top: cs.overflowY !== 'visible' ? r.top : -1e9, bottom: cs.overflowY !== 'visible' ? r.bottom : 1e9 };
      c = inter(c, box); if (!c) return null;
    }
    return c;
  };
  if (document.documentElement.scrollWidth > vw + 1) add('hscroll', 'document scrollWidth ' + document.documentElement.scrollWidth + ' > ' + vw);

  const boxes = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) {
    const t = n.nodeValue.trim(); if (!t) continue;
    const p = n.parentElement;
    if (!p || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'OPTION', 'TITLE'].includes(p.tagName) || !inLayer(p) || !vis(p) || p.closest('.am-sr')) continue;
    const pb = p.getBoundingClientRect(); if (pb.width <= 1 || pb.height <= 1) continue; // visually hidden text
    if ((() => { for (let a = p.parentElement; a; a = a.parentElement) { const ar = a.getBoundingClientRect(); if (ar.width <= 1 && getComputedStyle(a).overflowX === 'hidden') return true; } return false; })()) continue; // inside a visually hidden box
    const r = document.createRange(); r.selectNodeContents(n);
    for (const rc of r.getClientRects()) if (rc.width >= 2 && rc.height >= 2) boxes.push({ kind: 'text', el: p, r: rc, label: t.slice(0, 32) });
  }
  const ctl = [...document.querySelectorAll('a[href], button, input, select, textarea, summary, [role=button], [role=tab], [tabindex]:not([tabindex="-1"])')].filter((e) => inLayer(e) && vis(e) && !e.closest('.am-sr') && e.getBoundingClientRect().width > 1);
  // the map's invisible 44 px hit circles overlap their neighbours by design (a click picks the nearest star), so they count for size only
  ctl.forEach((e) => { if (!e.matches('.am-hit, .am-chit')) boxes.push({ kind: 'ctl', el: e, r: e.getBoundingClientRect(), label: name(e) }); });

  // clipped: sticks out of the viewport or is cut by an overflow:hidden parent, horizontally
  const seenClip = new Set();
  boxes.forEach((b) => {
    if (scrollerX(b.el)) return;
    let c = { left: 0, right: vw };
    for (let a = b.el; a && a !== document.documentElement; a = a.parentElement) {
      if (a === b.el && b.kind === 'ctl') continue;
      const cs = getComputedStyle(a); if (cs.overflowX === 'hidden' || cs.overflowX === 'clip') { const r = a.getBoundingClientRect(); c = { left: Math.max(c.left, r.left), right: Math.min(c.right, r.right) }; }
    }
    if (b.r.left < c.left - 1 || b.r.right > c.right + 1) { const k = name(b.el) + '|' + b.label; if (!seenClip.has(k)) { seenClip.add(k); add('clipped', name(b.el) + ' "' + b.label + '" x ' + Math.round(b.r.left) + '..' + Math.round(b.r.right) + ' of ' + Math.round(c.left) + '..' + Math.round(c.right)); } }
  });

  // Content that has scrolled under an opaque sticky bar is hidden, not overlapping.
  const stickyOf = (el) => { for (let a = el; a && a !== document.body; a = a.parentElement) if (getComputedStyle(a).position === 'sticky') return a; return null; };
  // overlap, on what is actually visible (clipped by scrollers and by the layer)
  const items = [];
  boxes.forEach((b) => { const c = clipOf(b.el); if (!c) return; const v = inter(b.r, c); if (v && v.width > 1.5 && v.height > 1.5) items.push({ b, v }); });
  const seenOv = new Set();
  for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) {
    const A = items[i], B = items[j];
    if (A.b.el === B.b.el || A.b.el.contains(B.b.el) || B.b.el.contains(A.b.el)) continue;
    const x = inter(A.v, B.v); if (!x || x.width <= 1.5 || x.height <= 1.5) continue;
    const sa = stickyOf(A.b.el), sb = stickyOf(B.b.el);
    if (sa !== sb) { const top = document.elementFromPoint(x.left + x.width / 2, x.top + x.height / 2); if (top && ((sa && !sb && sa.contains(top)) || (sb && !sa && sb.contains(top)))) continue; }
    const k = name(A.b.el) + '|' + name(B.b.el) + '|' + A.b.label + '|' + B.b.label;
    if (seenOv.has(k)) continue; seenOv.add(k);
    add('overlap', name(A.b.el) + ' "' + A.b.label + '" x ' + name(B.b.el) + ' "' + B.b.label + '" ' + Math.round(x.width) + 'x' + Math.round(x.height));
  }

  // target size and covered
  ctl.forEach((e) => {
    const r = e.getBoundingClientRect(), need = opts.desktop && e.matches(primary) ? 48 : 44;
    const hit = getComputedStyle(e, '::after'), ext = (a, b) => (parseFloat(hit[a]) < 0 ? -parseFloat(hit[a]) : 0) + (parseFloat(hit[b]) < 0 ? -parseFloat(hit[b]) : 0), grow = hit.content !== 'none' && hit.position === 'absolute' ? [ext('left', 'right'), ext('top', 'bottom')] : [0, 0];
    if (Math.min(r.width + grow[0], r.height + grow[1]) < need - 0.5) add('target', name(e) + ' "' + (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 24) + '" ' + Math.round(r.width) + 'x' + Math.round(r.height) + ' < ' + need);
    const c = clipOf(e), v = c && inter(r, c);
    if (v && v.width > 4 && v.height > 4 && !e.matches('.am-hit')) {
      const top = document.elementFromPoint(v.left + v.width / 2, v.top + v.height / 2);
      const st = top && stickyOf(top);
      if (top && !e.contains(top) && !(st && !st.contains(e))) add('covered', name(e) + ' covered by ' + name(top));
    }
  });

  // wraps: a button label on two lines
  ctl.filter((e) => e.matches('.btn, .chip, .tb-btn, .tui-btn, .tb-search, .tab, .set-nav-item')).forEach((e) => {
    const w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
    for (let n; (n = w.nextNode());) {
      if (!n.nodeValue.trim() || !vis(n.parentElement)) continue;
      const r = document.createRange(); r.selectNodeContents(n);
      const tops = new Set([...r.getClientRects()].filter((q) => q.width > 1).map((q) => Math.round(q.top / 4)));
      if (tops.size > 1) { add('wraps', name(e) + ' "' + (e.textContent || '').trim().slice(0, 24) + '" breaks onto ' + tops.size + ' lines'); break; }
    }
  });

  // contrast from computed colours
  const num = (s) => s.match(/-?[\d.]+/g).map(Number);
  const parse = (s) => {
    if (s.startsWith('color(')) { const [r, g, b, a] = num(s.replace('srgb', '')); return [r * 255, g * 255, b * 255, a == null ? 1 : a]; }
    const v = num(s); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1];
  };
  const over = (f, b) => { const a = f[3]; return [f[0] * a + b[0] * (1 - a), f[1] * a + b[1] * (1 - a), f[2] * a + b[2] * (1 - a), 1]; };
  const bgOf = (el) => { const stack = []; for (let a = el; a; a = a.parentElement) { const c = parse(getComputedStyle(a).backgroundColor); if (c[3] > 0) { stack.push(c); if (c[3] >= 1) break; } } let base = [255, 255, 255, 1]; for (let i = stack.length - 1; i >= 0; i--) base = over(stack[i], base); return base; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const seenC = new Set();
  const textEls = new Map(); boxes.filter((b) => b.kind === 'text').forEach((b) => { if (!textEls.has(b.el)) textEls.set(b.el, b.label); });
  ctl.filter((e) => ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.tagName)).forEach((e) => textEls.set(e, 'control'));
  textEls.forEach((label, el) => {
    const cs = getComputedStyle(el); if (parseFloat(cs.opacity) < 1) return;
    const bg = bgOf(el), fg = over(parse(cs.color), bg), l1 = lum(fg), l2 = lum(bg);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const k = name(el) + cs.color + bg.join(',');
    if (ratio < 4.5 && !seenC.has(k)) { seenC.add(k); add('contrast', name(el) + ' "' + label + '" ' + ratio.toFixed(2) + ' (' + cs.color + ' on rgb(' + bg.slice(0, 3).map(Math.round).join(',') + '))'); }
  });
  // narrow: a column or a row title squeezed below 120 px (text breaking one letter per line), and a Details sheet that squeezes the scene
  document.querySelectorAll('.now-panels > .panel, .now-panels .mrow .t, .now-panels .mrow .m').forEach((e) => { const w = e.getBoundingClientRect().width; if (inLayer(e) && vis(e) && w < 120) add('narrow', name(e) + ' ' + Math.round(w) + ' px wide'); });
  const sc = document.querySelector('.now-scene'), nv = document.querySelector('.now-view');
  if (sc && nv && vis(sc) && sc.getBoundingClientRect().height < Math.min(240, nv.getBoundingClientRect().height * 0.5)) add('narrow', 'scene squeezed to ' + Math.round(sc.getBoundingClientRect().height) + ' px');
  out.push({ kind: 'stat', msg: boxes.length + ' boxes, ' + ctl.length + ' controls' });
  return out;
}
"""


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(port):
    proc = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', APP_DIR],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/index.html' % port, timeout=1).read(10)
            return proc
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    raise SystemExit('server did not start')


def motion_invariants(br, base):
    """ADR-0055 as amended by the owner on 2026-10-27 (V2 Live only): with a playing simulation and full motion the map may run exactly the allowed loops (core-breath with fresh live work,
    am-drift, am-ring, am-travel), each infinite, 3.6 s or longer per cycle (under 0.3 Hz) and made of transform or opacity only; paused, offline, under reduced motion or with a hidden tab none; off the map none."""
    bad = []
    ctx = br.new_context(viewport={'width': 1440, 'height': 900})
    pg = ctx.new_page()
    css = "document.getAnimations().map(a => a.animationName).filter(Boolean)"
    allowed = ['core-breath', 'am-drift', 'am-ring', 'am-travel']
    detail = """() => document.getAnimations().filter(a => a.animationName).map(a => { const t = a.effect.getTiming(); return { name: a.animationName, duration: t.duration, iterations: t.iterations, props: [...new Set(a.effect.getKeyframes().flatMap((k) => Object.keys(k)))].filter((p) => !['offset', 'easing', 'composite', 'computedOffset'].includes(p)) }; })"""
    pg.goto(base + '?theme=dark&motion=full&sim=paused#/now', wait_until='load')
    pg.wait_for_timeout(700)
    names = pg.evaluate(css)
    if names:
        bad.append('a paused simulation still runs %r' % names)
    pg.evaluate("window.v2live.sim.play()")
    pg.wait_for_timeout(900)
    names = set(pg.evaluate(css))
    if not {'core-breath', 'am-drift'} <= names or names - set(allowed):
        bad.append('full motion with live work runs %r, expected core-breath and am-drift, nothing outside %r' % (sorted(names), allowed))
    for a in pg.evaluate(detail):
        if a['duration'] < 3600 or a['iterations'] is not None and a['iterations'] != float('inf') and a['iterations'] != 'Infinity':
            bad.append('%s cycles in %s ms (%s times): a loop must be infinite and 3.6 s or longer' % (a['name'], a['duration'], a['iterations']))
        if set(a['props']) - {'transform', 'opacity', 'translate', 'scale'}:
            bad.append('%s animates %r: transform and opacity only' % (a['name'], a['props']))
    pg.evaluate("Object.defineProperty(document, 'hidden', { value: true, configurable: true }); document.dispatchEvent(new Event('visibilitychange'))")
    pg.wait_for_timeout(200)
    names = pg.evaluate(css)
    if names:
        bad.append('a hidden tab still runs %r' % names)
    pg.evaluate("delete document.hidden; document.dispatchEvent(new Event('visibilitychange'))")
    pg.wait_for_timeout(200)
    pg.evaluate("window.v2live.store.set('motion', 'reduced')")
    pg.wait_for_timeout(300)
    names = pg.evaluate(css)
    if names:
        bad.append('reduced motion still runs %r' % names)
    if 'running' not in pg.evaluate("(document.querySelector('.am-running') || {}).textContent || ''"):
        bad.append('reduced motion does not show the static running text')
    pg.evaluate("window.v2live.store.set('motion', 'full'); window.v2live.sim.pause()")
    pg.wait_for_timeout(300)
    names = pg.evaluate(css)
    if names:
        bad.append('pausing the simulation still runs %r' % names)
    pg.evaluate("window.v2live.sim.play()")
    pg.goto(base + '?theme=dark&motion=full#/work', wait_until='load')
    pg.wait_for_timeout(300)
    names = pg.evaluate(css)
    # 2026-10-27 owner: more liveliness. The Work graph may run its soft pulse on needs-you marks; nothing else, and nothing under reduced motion.
    if set(names) - {'wg-soft'}:
        bad.append('a page without the core mark runs %r' % names)
    pg.evaluate("window.v2live.store.set('motion', 'reduced')")
    pg.wait_for_timeout(300)
    names = pg.evaluate(css)
    if names:
        bad.append('the Work graph runs %r under reduced motion' % names)
    ctx.close()
    return bad


SETTLE = """() => Promise.race([new Promise((r) => setTimeout(r, 800)), Promise.allSettled(document.getAnimations().filter((x) => x.effect && x.effect.getTiming().iterations !== Infinity).map((x) => x.finished))])"""

S4_ROUTES = ('chat-slash', 'chat-confirm', 'chat-cards', 'chat-general', 'chat-picker', 'chat-mission', 'chat-more', 'chat-receipts', 'chat-context', 'dock-slash', 'dock-reply', 'sheet', 'sheet-slash', 'replay-ev', 'replay-rec', 'replay-pick')


def s4_send(pg, where, text):
    pg.fill('input[data-key="chat-in-%s"]' % where, text)
    pg.keyboard.press('Enter')
    pg.wait_for_timeout(1000)


def s4_reset(pg):
    pg.keyboard.press('Escape')
    pg.evaluate("window.v2live.sim.reset(); window.v2live.ui.draft = ''; window.v2live.ui.tellOpen = false; window.v2live.ui.s4 = undefined; window.v2live.ui.rp = undefined; window.v2live.ui.replaySel = null")
    pg.wait_for_timeout(250)


def s4_state(pg, route, w):
    """S4 states: slash menu open, confirm card, card gallery, general answer, the dock bar, the phone chat sheet with the keyboard simulated, Replay with evidence and a recovery proposal.
    Returns the layer to measure (an overlay is measured on its own)."""
    s4_reset(pg)
    if route.startswith('chat'):
        pg.evaluate("location.hash = '#/chat'")
        pg.wait_for_timeout(250)
        if route == 'chat-slash':
            pg.fill('input[data-key="chat-in-page"]', '/')
        elif route == 'chat-confirm':
            s4_send(pg, 'page', '/stop fix date')
        elif route == 'chat-cards':
            s4_send(pg, 'page', '/approve search')
            s4_send(pg, 'page', '/mission Probe mission')
        elif route == 'chat-general':
            pg.click('.composer2[data-where="page"] .cscope'); pg.click('.pkpop [role="option"][data-value="general"]')
            s4_send(pg, 'page', 'Explain a checkpoint')
            pg.click('.ccard[data-kind="general"] .btn')
            pg.wait_for_timeout(400)
        elif route == 'chat-picker':
            pg.click('.composer2[data-where="page"] .cscope')
        elif route == 'chat-mission':
            pg.click('[data-key="chat-mission"]')
        elif route == 'chat-more':
            pg.click('[data-key="chat-more"]')
        elif route in ('chat-receipts', 'chat-context'):
            if pg.evaluate("document.documentElement.dataset.phone === 'true'"):
                pg.click('[data-key="chat-more"]')   # on a phone the three views live in More
            pg.click('[data-key="chat-tab-%s"]' % route.split('-')[1])
        pg.wait_for_timeout(200)
        if route in ('chat-picker', 'chat-mission') and pg.evaluate("!!document.querySelector('.sheet')"):
            return '.sheet'   # the picker is a bottom sheet on a phone
        return '.pkpop' if route in ('chat-picker', 'chat-mission', 'chat-more') else '.slash' if route == 'chat-slash' else None
    if route.startswith('dock') or route.startswith('sheet'):
        if route.startswith('sheet') and w >= 600:
            (pg.click('[data-tb="tools"]') if not pg.is_visible('[data-tb="device"]') else None, pg.click('[data-tb="device"]'))
            pg.click('[data-device="phone"]')
            pg.wait_for_timeout(400)
            pg.click('[data-tb="tools"]')
            pg.wait_for_timeout(300)
        pg.evaluate("location.hash = '#/now'")
        pg.wait_for_timeout(250)
        phone = pg.evaluate("document.getElementById('app').clientWidth < 600")
        if phone:
            pg.click('[data-key="bb-tell"]')
            pg.wait_for_timeout(300)
            if route in ('sheet-slash', 'dock-slash'):
                pg.keyboard.type('/')
            elif route == 'dock-reply':
                pg.keyboard.type('/status')
                pg.keyboard.press('Enter')
                pg.wait_for_timeout(600)
            pg.wait_for_timeout(300)
            return '.chatsheet'
        pg.click('input[data-key="chat-in-dock"]')
        pg.wait_for_timeout(200)
        if route == 'dock-slash':
            pg.fill('input[data-key="chat-in-dock"]', '/')
        elif route == 'dock-reply':
            s4_send(pg, 'dock', '/mission Probe mission')
        pg.wait_for_timeout(250)
        return '.tell-dock'
    pg.evaluate("window.v2live.sim.advance(520000)")
    pg.evaluate("location.hash = '#/replay/m-date'")
    pg.wait_for_timeout(400)
    if route == 'replay-pick':  # the mission chooser: a popover on a desktop, a full sheet on a phone
        pg.click('[data-key="rp-mission"]')
        pg.wait_for_timeout(300)
        return '.mc-sheet' if pg.evaluate("!!document.querySelector('.mc-sheet')") else '.mc-pop'
    if route == 'replay-ev':
        pg.click('#rs-9')
    else:
        pg.click('#rs-12')
        pg.keyboard.press('Escape'); pg.wait_for_timeout(150)
        if pg.evaluate("!document.querySelector('.rcv')"):  # a phone shows one section at a time
            pg.click('[data-key="rp-nav-recovery"]'); pg.wait_for_timeout(300)
        pg.click('.rcv[data-ok="true"] .btn')
    pg.wait_for_timeout(250)
    return '.sheet' if pg.evaluate("!!document.querySelector('.sheet')") else None


def s4_after(pg, route, w):
    if route.startswith('sheet') and w >= 600:
        for _ in range(3):   # a mouse window opens the Tell sheet at full, which makes the page behind (the prototype toolbar too) inert; the first Escape may only close the slash menu
            if pg.evaluate("!!document.querySelector('.sheet-wrap:not([data-leaving])')"):
                pg.keyboard.press('Escape')
                pg.wait_for_timeout(300)
        (pg.click('[data-tb="tools"]') if not pg.is_visible('[data-tb="device"]') else None, pg.click('[data-tb="device"]'))
        pg.click('[data-device="auto"]')
        pg.wait_for_timeout(250)


def open_tool(pg, which):
    """A prototype tool (device, theme, sim): from the toolbar, or from the sheet the phone top bar's SIMULATED tag opens when the toolbar row is folded away."""
    if pg.is_visible('[data-key="tools"]'):
        pg.click('[data-key="tools"]')
        pg.click('[data-key="tools-%s"]' % which)
    else:
        (pg.click('[data-tb="tools"]') if not pg.is_visible('[data-tb="%s"]' % which) else None, pg.click('[data-tb="%s"]' % which))


def open_overlay(pg, name):
    kind, which = name.split(':')
    open_tool(pg, which)
    pg.wait_for_selector('.menu, .sheet', state='visible')
    return '.menu' if pg.is_visible('.menu') else '.sheet'


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser()
    ap.add_argument('--viewports', default=','.join(VIEWPORTS))
    ap.add_argument('--routes', default=','.join(ROUTES))
    ap.add_argument('--themes', default='dark,light')
    ap.add_argument('--shots', default='')
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--no-overlays', action='store_true')
    ap.add_argument('--port', type=int, default=0)
    ap.add_argument('--lang', default='en')
    ap.add_argument('--notes', default='on')
    ap.add_argument('--query', default='', help='extra URL query for the first load, for example overview=network&story=many')
    a = ap.parse_args()
    viewports = a.viewports.split(',')
    routes = a.routes.split(',') + ([] if a.no_overlays else OVERLAYS)
    themes = a.themes.split(',')
    port = a.port or free_port()
    srv = start_server(port)
    base = 'http://127.0.0.1:%d/index.html' % port
    cells = OrderedDict()          # (viewport, route) -> {kind: count}
    details = OrderedDict()
    total = dict.fromkeys(KINDS, 0)
    stats = [0, 0]
    inv = []
    t0 = time.time()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            inv = motion_invariants(br, base)
            for vp in viewports:
                w, h = [int(x) for x in vp.split('x')]
                for theme in themes:
                    ctx = br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=1,
                                         color_scheme='light' if theme == 'light' else 'dark', reduced_motion='no-preference')
                    pg = ctx.new_page()
                    errs = []
                    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
                    pg.on('console', lambda m: errs.append('console: ' + m.text) if m.type == 'error' else None)
                    pg.goto('%s?theme=%s&sim=paused&motion=reduced&lang=%s&notes=%s%s#/now' % (base, theme, a.lang, a.notes, '&' + a.query if a.query else ''), wait_until='load')
                    pg.evaluate('document.fonts.ready.then(() => true)')
                    pg.wait_for_timeout(300)
                    for route in routes:
                        errs.clear()
                        layer = None
                        frames = []
                        if route == 'device:all':
                            pg.evaluate("location.hash = '#/now'")
                            pg.wait_for_timeout(100)
                            open_tool(pg, 'device')
                            pg.click('[data-device="all"]')
                            pg.wait_for_timeout(2500)
                            frames = [f for f in pg.frames if f != pg.main_frame]
                        elif route in S4_ROUTES:
                            layer = s4_state(pg, route, w)
                        elif route.startswith('tui:'):
                            pg.evaluate("location.hash = '#/terminal'")
                            pg.wait_for_timeout(200)
                            pg.evaluate(TUI_RESET)
                            keys, prefs = TUI[route]
                            pg.evaluate(TUI_SET, [keys, prefs])
                            pg.wait_for_timeout(250)
                        elif route.startswith('menu:'):
                            pg.evaluate("location.hash = '#/now'")
                            pg.wait_for_timeout(120)
                            layer = open_overlay(pg, route)
                        else:
                            rt, _, st = route.partition('~')
                            pg.evaluate("location.hash = '#/%s'" % rt)
                            pg.wait_for_timeout(180)
                            if st:
                                pg.evaluate(STATES[st])
                                pg.evaluate("window.dispatchEvent(new Event('hashchange'))")
                                pg.wait_for_timeout(250)
                                layer = {'help': '.helpbox', 'toast': '.toast', 'safety': '.safety-pop, .sheet', 'stopask': '.safety-pop, .sheet', 'estopsafety': '.safety-pop, .sheet', 'tell': '.tell-dock' if rt == 'now' else '.chatdock.tell'}.get(st)
                                if st == 'tell' and pg.evaluate("!!document.querySelector('.chatsheet')"):
                                    layer = '.chatsheet'
                            if '/' in rt and rt.split('/')[0] in ('work', 'projects', 'now', 'security', 'health', 'usage', 'accounts', 'extensions'):
                                pos = pg.evaluate("getComputedStyle(document.querySelector('#inspector')).position")
                                if pos == 'absolute':
                                    layer = '.sheet[data-insp]' if pg.evaluate("!!document.querySelector('.sheet[data-insp]')") else '#inspector'
                            pg.evaluate("document.querySelector('.main-col') && (document.querySelector('.main-col').scrollTop = 0)")
                        desktop = w >= 1024 and not route.startswith('sheet')
                        # layout is judged at rest: the motion layer's finite transitions (route cross-fade, row glide, sheets) are given up to 800 ms to end; loops stay (they are checked in motion_invariants)
                        pg.mouse.move(2, 2)   # the pointer left where the last click was: cells that glide under it would open a preview card, which is a popover, not a defect
                        pg.evaluate(SETTLE)
                        res = pg.evaluate(MEASURE, {'layer': layer, 'desktop': desktop})
                        for f in frames:   # each pane is a real document laid out at its own width
                            fw = f.evaluate('innerWidth')
                            res += [r for r in f.evaluate(MEASURE, {'layer': None, 'desktop': fw >= 1024}) if r['kind'] != 'stat']
                        if route == 'device:all':
                            (pg.click('[data-tb="tools"]') if not pg.is_visible('[data-tb="device"]') else None, pg.click('[data-tb="device"]'))
                            pg.click('[data-device="auto"]')
                            pg.wait_for_timeout(200)
                        if route in S4_ROUTES:
                            if a.shots:
                                os.makedirs(a.shots, exist_ok=True)
                                pg.screenshot(path=os.path.join(a.shots, '%s_%s_%s.png' % (vp, route, theme)))
                            s4_after(pg, route, w)
                            s4_reset(pg)
                        for e in errs:
                            res.append({'kind': 'error', 'msg': e})
                        cell = cells.setdefault((vp, route), dict.fromkeys(KINDS, 0))
                        for r in res:
                            if r['kind'] == 'stat':
                                nb, nc = r['msg'].replace(',', '').split()[0], r['msg'].replace(',', '').split()[2]
                                stats[0] += int(nb)
                                stats[1] += int(nc)
                                continue
                            cell[r['kind']] += 1
                            total[r['kind']] += 1
                            details.setdefault((vp, route, theme), []).append(r)
                        if a.shots and route not in S4_ROUTES:
                            os.makedirs(a.shots, exist_ok=True)
                            pg.screenshot(path=os.path.join(a.shots, '%s_%s_%s.png' % (vp, route.replace('/', '-').replace(':', '-'), theme)))
                        if layer in ('.menu', '.sheet'):
                            pg.keyboard.press('Escape')
                        if '~' in route:
                            pg.evaluate(RESET)
                        if route.startswith('tui:'):
                            pg.evaluate(TUI_RESET)
                    ctx.close()
            br.close()
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            srv.kill()

    print('\nDefects per route x viewport (dark + light)')
    print('%-30s' % 'route' + ''.join('%6s' % v.split('x')[0] for v in viewports) + '%7s' % 'total')
    for r in routes:
        row = [sum(cells[(vp, r)].values()) for vp in viewports]
        print('%-30s' % r[:29] + ''.join('%6d' % n for n in row) + '%7d' % sum(row))
    print('\nDefects per kind: ' + ', '.join('%s %d' % (k, total[k]) for k in KINDS))
    for m in inv:
        print('MOTION INVARIANT FAILED: ' + m)
    n = sum(total.values()) + len(inv)
    print('Motion invariants (ADR-0055): %s' % ('FAILED' if inv else 'ok, only core-breath, am-drift, am-ring and am-travel (transform or opacity, 3.6 s or longer) with a playing simulation, none when paused, hidden, under reduced motion or off the map'))
    print('Measured %d text boxes and %d controls in %d pages.' % (stats[0], stats[1], len(viewports) * len(routes) * len(themes)))
    print('TOTAL DEFECTS: %d   (%d viewports x %d routes x %d themes, %.0f s)' % (n, len(viewports), len(routes), len(themes), time.time() - t0))
    if n and (a.verbose or n < 60):
        print('\nDetails')
        for (vp, route, theme), rs in details.items():
            for r in rs[:6]:
                print('  %s %s %s  %s: %s' % (vp, route, theme, r['kind'], r['msg']))
            if len(rs) > 6:
                print('  ... %d more in %s %s %s' % (len(rs) - 6, vp, route, theme))
    return 1 if n else 0


if __name__ == '__main__':
    sys.exit(main())
