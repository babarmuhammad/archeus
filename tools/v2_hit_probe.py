"""V2 prototype 44 pt hit-area probe. Measures the EFFECTIVE hit area, not the element box: a grid of points around each
visible control is hit-tested with elementFromPoint, so ::after hit areas, padding and occlusion all count (pseudo-elements
hit-tested to their owner). A control passes when the hit extent is at least 44 x 44 CSS px on the phone and 48 x 48 CSS px on desktop
(desktop frames are measured at their master size, so one frame px is one CSS px). Run:
  BASE=http://127.0.0.1:8791 py -I tools/v2_hit_probe.py        (serve clients/v2-prototype first)
PHONE=WxHxDPR overrides the phone viewport (default 402x687x2).
Exit 1 when any control is under its minimum. With the composer sheet open, controls fully covered by the sheet are skipped."""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get('BASE', 'http://127.0.0.1:8791') + '/index.html'
PHONE = tuple(int(n) for n in os.environ.get('PHONE', '402x687x2').split('x'))  # PHONE=320x640x2 measures the 320 width
ROUTES = ['#/now', '#/plan/m-search', '#/mission/m-date', '#/shared', '#/replay/m-date']
DESKTOP = [('#/now', 1296, 755), ('#/mission/m-date', 1244, 855), ('#/shared', 1382, 948), ('#/replay/m-date', 1440, 836), ('#/terminal', 1600, 900)]
DESK_MIN = 48

JS = """([covered_ok, MIN]) => {
  const sel = 'a[href], button, input, textarea, select, [role=button], summary';
  const STEP = 2, PAD = 40, out = [];
  document.querySelectorAll(sel).forEach(e => {
    const cs = getComputedStyle(e), b = e.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || e.closest('[hidden], [inert]') || e.closest('#slash-menu,.slash-menu')) return;
    if (b.width < 1 || b.height < 1 || b.bottom <= 0 || b.top >= innerHeight || b.right <= 0 || b.left >= innerWidth) return;
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    for (let y = Math.max(0, b.top - PAD); y < Math.min(innerHeight, b.bottom + PAD); y += STEP)
      for (let x = Math.max(0, b.left - PAD); x < Math.min(innerWidth, b.right + PAD); x += STEP) {
        const t = document.elementFromPoint(x, y);
        if (t && (t === e || e.contains(t))) { x0 = Math.min(x0, x); x1 = Math.max(x1, x + STEP); y0 = Math.min(y0, y); y1 = Math.max(y1, y + STEP); }
      }
    const w = x1 > x0 ? x1 - x0 : 0, h = y1 > y0 ? y1 - y0 : 0;
    if (covered_ok && !w) return;
    if (w < MIN - STEP || h < MIN - STEP)
      out.push({ tag: e.tagName, text: (e.textContent || e.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').slice(0, 26),
        cls: String(e.className && e.className.baseVal === undefined ? e.className : '').slice(0, 30),
        box: Math.round(b.width * 10) / 10 + 'x' + Math.round(b.height * 10) / 10, hit: w + 'x' + h });
  });
  return out;
}"""

sys.stdout.reconfigure(encoding='utf-8')
ONLY = os.environ.get('ONLY', 'both')
fails = 0
with sync_playwright() as p:
    br = p.chromium.launch()
    for focus_composer in ((False, True) if ONLY != 'desktop' else ()):
        for route in ([ROUTES[0]] if focus_composer else ROUTES):
            w, h, dpr = PHONE
            pg = br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=dpr, reduced_motion='reduce').new_page()
            pg.goto(BASE + route, wait_until='load')
            pg.evaluate('document.fonts.ready.then(() => true)')
            pg.wait_for_timeout(500)
            if focus_composer:
                pg.click('#chat-input')
                pg.wait_for_timeout(400)
            bad = pg.evaluate(JS, [focus_composer, 44])
            fails += len(bad)
            print('%s %s%s: %d under 44' % ('FAIL' if bad else 'PASS', route, ' +composer' if focus_composer else '', len(bad)))
            for b in bad:
                print('   %(tag)s "%(text)s" .%(cls)s box %(box)s hit %(hit)s' % b)
            pg.context.close()
    for route, w, h in (DESKTOP if ONLY != 'phone' else []):
        pg = br.new_context(viewport={'width': w, 'height': h}, reduced_motion='reduce').new_page()
        pg.goto(BASE + route, wait_until='load')
        pg.evaluate('document.fonts.ready.then(() => true)')
        pg.wait_for_timeout(500)
        bad = pg.evaluate(JS, [False, DESK_MIN])
        fails += len(bad)
        print('%s desktop %s %dx%d: %d under %d' % ('FAIL' if bad else 'PASS', route, w, h, len(bad), DESK_MIN))
        for b in bad:
            print('   %(tag)s "%(text)s" .%(cls)s box %(box)s hit %(hit)s' % b)
        pg.context.close()
    br.close()
sys.exit(1 if fails else 0)
