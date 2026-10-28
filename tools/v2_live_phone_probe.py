"""V2 Live phone probe, foundation F0: what the phone overhaul's shared primitives (js/viewport.js, js/sheet.js, the phone tokens, the PWA files) promise, checked in Chromium.

Checks that run and must pass (any FAIL gives exit code 1):
  single threshold    no phone-width literal (clientWidth or innerWidth against 599 or 600, a width matchMedia, a 599 or 600 px media query) outside js/viewport.js and js/phone-model.js
  pwa static          manifest fields and icon files, viewport and theme-color meta, apple and mobile-web-app meta, apple-touch-icon size
  safe areas          injecting --sa-t, --sa-r, --sa-b and --sa-l puts the bar's items above the bottom inset, the page inside the others, and the sheet's footer above its inset
  visual viewport     a faked visualViewport height with a field focused sets --vv-bottom and html[data-kb=open]; blur clears it
  targets             no control under 44 px (the ::after hit area counts) on the phone routes at 390x844 and 360x740
  no sideways scroll  320, 360, 390, 430 wide, 200 % zoom (320 CSS px) and landscape 844x390 and 667x375
  landscape           a coarse-pointer window under 500 high and 950 wide is the phone shell; a mouse window of the same size, and a wide one, are not
  frame               a 390 px frame on a desktop window is the phone shell, so the Projects / Network switch is hidden there
  pages (slice D)     Replay, Security, Health, Usage, Accounts, Extensions, Settings: one vertical scroller per route, no scrollbar of their own, the first row early (Replay under 75 % of the height,
                      the five area pages under 260 px of the page), tab strips and chip rows not cut mid-label, no text under 12 px, the Replay evidence as a sheet
  sheet               role, aria-modal, inert, focus in and back, detents by button, key and drag (flick and slow), Back and Esc, modeless until full, pinned above the keyboard, flat scrim, instant under Reduced motion

Expected failures (XFAIL, never block): the checks that need the slices after F0. Those marked "measured" run and print what they find; an unexpected pass prints XPASS.

It serves clients/v2-live from its own http.server and stops only that server. Run it from the worktree root through the shared lock:
  py D:\\Archeus\\.collab\\testlock.py -- py -I tools\\v2_live_phone_probe.py        options: --port N
"""
import argparse
import json
import os
import re
import struct
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v2_live_layout_probe as lp  # noqa: E402  (its measuring script, server helpers and settle wait)

APP = lp.APP_DIR
ROUTES = ['now', 'work', 'chat', 'settings', 'projects', 'security', 'health', 'usage', 'accounts', 'extensions', 'replay/m-date', 'settings/appearance', 'settings/prototype', 'replay/m-date?section=evidence', 'replay/m-date?section=recovery', 'replay/m-date?section=reference']
PAGES = ['replay/m-date', 'replay/m-date?section=evidence', 'replay/m-date?section=recovery', 'replay/m-date?section=reference', 'security', 'health', 'usage', 'accounts', 'extensions', 'settings', 'settings/appearance']
AREAS = ['security', 'health', 'usage', 'accounts', 'extensions']
results = []


def record(status, name, detail=''):
    results.append((status, name, detail))


def check(name, ok, detail=''):
    record('ok' if ok else 'FAIL', name, '' if ok else detail)


def xfail(name, slice_, reason, ok=None, detail=''):
    """A check a later slice makes pass. ok=None: not run. A measured pass is reported as XPASS."""
    record('XPASS' if ok else 'xfail', '%s [%s]' % (name, slice_), (reason + (' - ' + detail if detail else '')) if not ok else 'now passes, move it to a real check')


def read(rel):
    with open(os.path.join(APP, rel), encoding='utf-8', errors='replace') as f:
        return f.read()


def png_size(rel):
    with open(os.path.join(APP, rel), 'rb') as f:
        head = f.read(24)
    return struct.unpack('>II', head[16:24]) if head[:8] == b'\x89PNG\r\n\x1a\n' else None


# ---------- static ----------
def source_files(exts):
    for base, dirs, files in os.walk(APP):
        dirs[:] = [d for d in dirs if d not in ('test', 'fonts')]
        for n in files:
            if n.endswith(exts) and not n.endswith('.test.mjs'):
                yield os.path.relpath(os.path.join(base, n), APP).replace('\\', '/')


def single_threshold():
    js = re.compile(r'\b(clientWidth|innerWidth|offsetWidth|outerWidth)\s*[<>]=?\s*(599|600)\b|matchMedia\([^)]*(max|min)-width')
    css = re.compile(r'@media[^{]*\((max|min)-width:\s*(599|600)px\)')
    # the map and territory geometry measure their own host box, not the device: they are a different quantity
    skip = ('js/viewport.js', 'js/phone-model.js')
    hits, replay = [], []
    for rel in source_files(('.js', '.css', '.html')):
        if rel in skip or rel.startswith('js/constellation/'):
            continue
        for i, line in enumerate(read(rel).splitlines(), 1):
            if (css if rel.endswith('.css') else js).search(line):
                (replay if rel == 'js/replay.js' else hits).append('%s:%d' % (rel, i))
    check('single threshold: no phone-width literal outside viewport.js', not hits, ', '.join(hits[:8]))
    if replay:
        xfail('single threshold: js/replay.js reading column', 'D', 'Replay still compares its own column to 600', False, ', '.join(replay))
    else:
        record('ok', 'single threshold: js/replay.js reading column')


def pwa_static():
    m = json.loads(read('manifest.webmanifest'))
    for k in ('id', 'name', 'short_name', 'description', 'lang', 'start_url', 'scope', 'display', 'orientation', 'background_color', 'theme_color'):
        check('pwa manifest: ' + k, bool(m.get(k)), 'missing')
    icons = m.get('icons', [])
    check('pwa manifest: no combined "any maskable" purpose', all(i.get('purpose') in ('any', 'maskable') for i in icons), 'purposes %r' % [i.get('purpose') for i in icons])
    for purpose in ('any', 'maskable'):
        for size in (192, 512):
            hit = [i for i in icons if i.get('purpose') == purpose and i.get('sizes') == '%dx%d' % (size, size)]
            ok = bool(hit) and png_size(hit[0]['src']) == (size, size)
            check('pwa manifest: %s icon %d with that real size' % (purpose, size), ok, 'missing or wrong size: %r' % hit)
    html = read('index.html')
    meta = lambda name: re.findall(r'<meta name="%s" content="([^"]*)"([^>]*)>' % name, html)
    vp = meta('viewport')
    check('pwa meta: viewport has width=device-width and viewport-fit=cover, no zoom lock', bool(vp) and 'width=device-width' in vp[0][0] and 'viewport-fit=cover' in vp[0][0] and 'user-scalable' not in vp[0][0] and 'maximum-scale' not in vp[0][0], str(vp))
    tc = meta('theme-color')
    check('pwa meta: theme-color for dark and light by media', {t[1].strip() for t in tc} == {'media="(prefers-color-scheme: dark)"', 'media="(prefers-color-scheme: light)"'}, str(tc))
    for name, want in (('apple-mobile-web-app-capable', 'yes'), ('mobile-web-app-capable', 'yes'), ('apple-mobile-web-app-title', 'Archeus'), ('apple-mobile-web-app-status-bar-style', None)):
        got = meta(name)
        check('pwa meta: ' + name, bool(got) and (want is None or got[0][0] == want), str(got))
    check('pwa: link manifest', 'rel="manifest" href="manifest.webmanifest"' in html or 'href="manifest.webmanifest"' in html, '')
    touch = re.search(r'rel="apple-touch-icon" href="([^"]+)"', html)
    check('pwa: apple-touch-icon is a 180 px png', bool(touch) and png_size(touch.group(1)) == (180, 180), str(touch and touch.group(1)))


# ---------- browser ----------
SHEET_OPEN = """async (o) => {
  const { openSheet } = await import('./js/sheet.js');
  const opener = document.querySelector('[data-key="bb-places"]'); opener.focus();
  const body = document.createElement('div'); body.innerHTML = '<p>body</p><input id="probe-in" aria-label="probe">';
  const foot = document.createElement('button'); foot.className = 'btn'; foot.textContent = 'Go';
  window.__s = openSheet(Object.assign({ id: 'probe', title: 'Probe', detents: ['peek', 'half', 'full'], initial: 'half', content: body, footer: foot }, o || {}));
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
}"""
SHEET_STATE = """() => { const el = document.querySelector('.sheet'); if (!el) return null; const wrap = el.parentElement, r = el.getBoundingClientRect(), w = wrap.getBoundingClientRect(), grip = el.querySelector('.sheet-grip').getBoundingClientRect();
  return { detent: el.dataset.detent, h: Math.round(r.height), wrapH: Math.round(w.height), bottom: Math.round(r.bottom), wrapBottom: Math.round(w.bottom), modal: el.getAttribute('aria-modal'), role: el.getAttribute('role'),
    label: document.getElementById(el.getAttribute('aria-labelledby')).textContent, focusIn: el.contains(document.activeElement), barInert: document.querySelector('.bottombar').inert, wrapModal: wrap.hasAttribute('data-modal'),
    gripH: Math.round(grip.height), closeH: Math.round(el.querySelector('.sheet-close').getBoundingClientRect().height), gripLabel: el.querySelector('.sheet-grip').getAttribute('aria-label') } }"""
GRIP_BOX = "() => { const r = document.querySelector('.sheet-grip').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }"


def new_page(br, w, h, base, hash_='#/now', touch=True, query='', errs=None):
    ctx = br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2, has_touch=touch, is_mobile=touch, color_scheme='dark')
    pg = ctx.new_page()
    if errs is not None:
        pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
        pg.on('console', lambda m: errs.append('console: ' + m.text) if m.type == 'error' else None)
    pg.goto('%s?theme=dark&sim=paused&motion=reduced&notes=off%s%s' % (base, '&' + query if query else '', hash_), wait_until='load')
    pg.evaluate('document.fonts.ready.then(() => true)')
    pg.wait_for_timeout(300)
    return ctx, pg


def drag(pg, dy, steps=5, wait=0):
    b = pg.evaluate(GRIP_BOX)
    pg.mouse.move(b['x'], b['y'])
    pg.mouse.down()
    for i in range(1, steps + 1):
        pg.mouse.move(b['x'], b['y'] + dy * i / steps)
        if wait:
            pg.wait_for_timeout(wait)
    pg.mouse.up()
    pg.wait_for_timeout(120)
    return pg.evaluate(SHEET_STATE)


def sheet_checks(br, base):
    errs = []
    ctx, pg = new_page(br, 390, 844, base, errs=errs)
    pg.evaluate(SHEET_OPEN)
    s = pg.evaluate(SHEET_STATE)
    check('sheet: dialog named by its title, modal, focus inside, page inert', s['role'] == 'dialog' and s['label'] == 'Probe' and s['modal'] == 'true' and s['focusIn'] and s['barInert'], str(s))
    check('sheet: handle and Close are 44 px', s['gripH'] >= 44 and s['closeH'] >= 44, 'grip %s close %s' % (s['gripH'], s['closeH']))
    near = lambda v, share, tol=3: abs(v['h'] - share * v['wrapH']) <= tol
    check('sheet: half is 56 % of the space', s['detent'] == 'half' and near(s, .56), str(s))
    pg.click('.sheet-grip')
    pg.wait_for_timeout(120)
    s = pg.evaluate(SHEET_STATE)
    check('sheet: the handle button steps to full (92 %) and says Collapse', s['detent'] == 'full' and near(s, .92) and s['gripLabel'] == 'Collapse', str(s))
    pg.focus('.sheet-grip')
    pg.keyboard.press('ArrowDown')
    s = pg.evaluate(SHEET_STATE)
    check('sheet: arrow down on the handle goes to half', s['detent'] == 'half', str(s))
    s = drag(pg, -250)
    check('sheet: a fast drag up flicks to full', s['detent'] == 'full' and near(s, .92), str(s))
    s = drag(pg, 200)
    check('sheet: a fast drag down flicks to the detent below', s['detent'] == 'half', str(s))
    s = drag(pg, -50, steps=10, wait=40)
    check('sheet: a slow short drag settles on the nearest detent', s['detent'] == 'half' and near(s, .56), str(s))
    s = drag(pg, 300)
    s2 = drag(pg, 300) if s and s['detent'] == 'peek' else s
    check('sheet: flicking down past the lowest detent closes it', s2 is None, str(s2))
    check('sheet: closing returns focus to the opener and frees the page', pg.evaluate("document.activeElement.dataset.key === 'bb-places' && !document.querySelector('.bottombar').inert"), pg.evaluate('document.activeElement.outerHTML.slice(0, 80)'))
    pg.evaluate(SHEET_OPEN)
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(250)
    check('sheet: Esc closes it', pg.evaluate("!document.querySelector('.sheet') && document.activeElement.dataset.key === 'bb-places'"), '')
    pg.evaluate(SHEET_OPEN)
    pg.go_back()
    pg.wait_for_timeout(300)
    check('sheet: the system Back closes it', pg.evaluate("!document.querySelector('.sheet')"), '')
    pg.evaluate(SHEET_OPEN, {'modal': False, 'initial': 'peek'})
    s = pg.evaluate(SHEET_STATE)
    check('sheet: modal false is modeless at peek (no aria-modal, page live, no scrim)', s['modal'] is None and not s['barInert'] and not s['wrapModal'], str(s))
    pg.evaluate('window.__s.setDetent("full")')
    s = pg.evaluate(SHEET_STATE)
    check('sheet: modal false becomes modal at full', s['modal'] == 'true' and s['barInert'] and s['wrapModal'], str(s))
    flat = pg.evaluate("() => { const sc = document.querySelector('.sheet-scrim'), cs = getComputedStyle(sc); return { f: cs.backdropFilter, bg: cs.backgroundColor, bgi: cs.backgroundImage, d: getComputedStyle(document.querySelector('.sheet')).transitionDuration }; }")
    check('sheet: flat scrim (no blur, no gradient) and no transition under Reduced motion', flat['f'] == 'none' and flat['bgi'] == 'none' and 'rgba' in flat['bg'] and flat['d'] == '0s', str(flat))
    pg.evaluate('window.__s.close()')
    pg.wait_for_timeout(100)

    # the keyboard: a faked visual viewport, a field focused
    pg.evaluate(SHEET_OPEN, {'initial': 'full'})
    pg.focus('#probe-in')
    pg.evaluate("() => { Object.defineProperty(visualViewport, 'height', { get: () => 440, configurable: true }); visualViewport.dispatchEvent(new Event('resize')); }")
    pg.wait_for_timeout(250)
    s = pg.evaluate(SHEET_STATE)
    v = pg.evaluate("() => ({ kb: document.documentElement.dataset.kb, bottom: document.documentElement.style.getPropertyValue('--vv-bottom'), vvh: document.documentElement.style.getPropertyValue('--vv-h') })")
    check('visual viewport: a focused field and a 440 px viewport set --vv-bottom and data-kb', v['kb'] == 'open' and v['bottom'] == '404px' and v['vvh'] == '440px', str(v))
    check('sheet: pinned above the keyboard, never taller than what is left', s['wrapBottom'] == 440 and s['bottom'] <= 440 and s['h'] <= 432, str(s))
    pg.evaluate("() => { delete visualViewport.height; visualViewport.dispatchEvent(new Event('resize')); document.activeElement.blur(); }")
    pg.wait_for_timeout(300)
    v = pg.evaluate("() => ({ kb: document.documentElement.dataset.kb || null, bottom: document.documentElement.style.getPropertyValue('--vv-bottom') })")
    check('visual viewport: back to full height and blur clears data-kb', v['kb'] is None and v['bottom'] == '0px', str(v))
    pg.evaluate('window.__s.close()')
    pg.evaluate("() => { const i = document.createElement('input'); document.body.append(i); i.focus(); Object.defineProperty(visualViewport, 'height', { get: () => 790, configurable: true }); visualViewport.dispatchEvent(new Event('resize')); }")
    pg.wait_for_timeout(200)
    check('visual viewport: a collapsing browser bar (54 px) is not a keyboard', pg.evaluate("document.documentElement.dataset.kb === undefined"), '')
    check('sheet and viewport: no console or page errors', not errs, '; '.join(errs[:3]))
    ctx.close()


def safe_areas(br, base):
    ctx, pg = new_page(br, 390, 844, base)
    pg.evaluate("() => { const s = document.documentElement.style; s.setProperty('--sa-t', '47px'); s.setProperty('--sa-r', '44px'); s.setProperty('--sa-b', '34px'); s.setProperty('--sa-l', '44px'); }")
    r = pg.evaluate("""() => { const b = document.querySelector('.bottombar'), br = b.getBoundingClientRect(), items = [...b.querySelectorAll('.bb-item')].map((e) => e.getBoundingClientRect().bottom), cs = getComputedStyle(document.body);
      return { pad: getComputedStyle(b).paddingBottom, gap: br.bottom - Math.max(...items), top: cs.paddingTop, left: cs.paddingLeft, right: cs.paddingRight, toolbar: document.getElementById('toolbar').getBoundingClientRect().top }; }""")
    check('safe areas: the bar items sit above the bottom inset', r['pad'] == '34px' and r['gap'] >= 33.5, str(r))
    check('safe areas: the page keeps inside the top, left and right insets', r['top'] == '47px' and r['left'] == '44px' and r['right'] == '44px' and r['toolbar'] >= 46.5, str(r))
    pg.evaluate(SHEET_OPEN)
    r = pg.evaluate("() => { const e = document.querySelector('.sheet'), f = e.querySelector('.sheet-foot').getBoundingClientRect(); return { pad: getComputedStyle(e).paddingBottom, gap: e.getBoundingClientRect().bottom - f.bottom }; }")
    check('safe areas: the sheet footer sits above the bottom inset', r['pad'] == '34px' and r['gap'] >= 33.5, str(r))
    ctx.close()


def sizes(br, base):
    errs = []
    bad = []
    for vp, w, h, touch in [('390x844', 390, 844, True), ('360x740', 360, 740, True)]:
        ctx, pg = new_page(br, w, h, base, errs=errs, touch=touch)
        for route in ROUTES:
            pg.evaluate("location.hash = '#/%s'" % route)
            pg.wait_for_timeout(150)
            pg.evaluate(lp.SETTLE)
            for r in pg.evaluate(lp.MEASURE, {'layer': None, 'desktop': False}):
                if r['kind'] == 'target':
                    bad.append('%s %s: %s' % (vp, route, r['msg']))
        ctx.close()
    check('targets: every control 44 px or more on the phone routes (390x844, 360x740)', not bad, '; '.join(bad[:4]))
    check('routes: no console or page errors on the phone routes', not errs, '; '.join(errs[:3]))
    over = []
    for label, w, h in [('320', 320, 640), ('360', 360, 740), ('390', 390, 844), ('430', 430, 932), ('200% zoom', 320, 480), ('landscape 844x390', 844, 390), ('landscape 667x375', 667, 375)]:
        ctx, pg = new_page(br, w, h, base)
        for route in ROUTES:
            pg.evaluate("location.hash = '#/%s'" % route)
            pg.wait_for_timeout(120)
            x = pg.evaluate("() => ({ d: document.documentElement.scrollWidth - innerWidth, m: (document.querySelector('.main-col') || {}).scrollWidth - (document.querySelector('.main-col') || {}).clientWidth })")
            if x['d'] > 1 or x['m'] > 1:
                over.append('%s %s +%s/+%s' % (label, route, x['d'], x['m']))
        ctx.close()
    check('no sideways scroll at 320, 360, 390, 430, 200 % zoom and in landscape (page and main column)', not over, '; '.join(over[:5]))


# ---------- slice D: the pages ----------
SCROLLERS = """() => { const mc = document.querySelector('.main-col'), out = [];
  for (const e of [mc, ...mc.querySelectorAll('*')]) { const cs = getComputedStyle(e); if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && e.scrollHeight > e.clientHeight + 1) out.push(e.tagName.toLowerCase() + '.' + String(e.className).slice(0, 24)); }
  return out; }"""
BARS = """() => { const mc = document.querySelector('.main-col'), out = [];
  for (const e of [...mc.querySelectorAll('*'), ...document.querySelectorAll('.sheet *')]) { const cs = getComputedStyle(e); if (!['auto', 'scroll'].includes(cs.overflowX) && !['auto', 'scroll'].includes(cs.overflowY)) continue;
    if (cs.scrollbarWidth !== 'none' && (e.offsetWidth - e.clientWidth - e.clientLeft * 2 > 0 || e.offsetHeight - e.clientHeight - e.clientTop * 2 > 0)) out.push(e.tagName.toLowerCase() + '.' + String(e.className).slice(0, 24)); }
  const m = getComputedStyle(mc); return { rows: out, main: m.scrollbarWidth === 'none' || mc.offsetWidth - mc.clientWidth === 0 }; }"""
FIRST = """() => { const mc = document.querySelector('.main-col'), top = mc.getBoundingClientRect().top, panel = document.querySelector('.ax-panel'), ext = document.querySelector('.ext-needs, .ext-list');
  const first = panel ? [...panel.children].find((c) => c.getBoundingClientRect().height > 0) : ext; return first ? Math.round(first.getBoundingClientRect().top - top) : null; }"""
STRIPS = """() => [...document.querySelectorAll('.ax-subnav, .ext-tabs, .rp-nav, .ax-facet, .rp-filters')].filter((e) => e.getClientRects().length).map((row) => {
  const r = row.getBoundingClientRect(), items = [...row.children].filter((c) => c.getClientRects().length), cur = items.find((c) => c.matches('[aria-current], [aria-selected=true], [aria-pressed=true]')) || null;
  const inside = (c) => { const b = c.getBoundingClientRect(); return b.left >= r.left - 1 && b.right <= r.right + 1; };
  const scrolls = row.scrollWidth > row.clientWidth + 1;
  return { cls: String(row.className).slice(0, 20), scrolls, edge: row.dataset.edge || '', curIn: cur ? inside(cur) : true, allIn: items.every(inside), bar: getComputedStyle(row).scrollbarWidth }; })"""
SMALL = """() => [...document.querySelectorAll('.main-col *, .sheet *')].filter((e) => !e.closest('svg') && e.checkVisibility({ checkVisibilityCSS: true }) && [...e.childNodes].some((c) => c.nodeType === 3 && c.nodeValue.trim()) && parseFloat(getComputedStyle(e).fontSize) < 12 && parseFloat(getComputedStyle(e).fontSize) > 0).map((e) => e.tagName.toLowerCase() + '.' + String(e.className).slice(0, 20) + ' ' + getComputedStyle(e).fontSize).slice(0, 6)"""


def page_checks(br, base):
    errs = []
    for w, h_ in [(390, 844), (360, 740), (430, 932)]:
        ctx, pg = new_page(br, w, h_, base, errs=errs)
        vp = '%dx%d' % (w, h_)
        bad_scroll, bad_strip, bad_small, bad_first = [], [], [], []
        for route in PAGES:
            pg.evaluate("location.hash = '#/%s'" % route)
            pg.wait_for_timeout(300)
            sc = pg.evaluate(SCROLLERS)
            if len(sc) > 1 or (sc and not sc[0].startswith('main')):
                bad_scroll.append('%s: %s' % (route, sc))
            for st in pg.evaluate(STRIPS):
                if (st['scrolls'] and (not st['edge'] or not st['curIn'] or st['bar'] != 'none')) or (not st['scrolls'] and not st['allIn']):
                    bad_strip.append('%s %s' % (route, st))
            bad_small += ['%s %s' % (route, t) for t in pg.evaluate(SMALL)]
            if route in AREAS:
                top = pg.evaluate(FIRST)
                if top is None or top >= 260:
                    bad_first.append('%s %s' % (route, top))
        check('pages %s: no vertical scroller but the main column' % vp, not bad_scroll, '; '.join(bad_scroll[:3]))
        check('pages %s: tab strips and chip rows scroll with a faded edge, no scrollbar, the current item whole; a strip that fits is not cut' % vp, not bad_strip, '; '.join(bad_strip[:3]))
        check('pages %s: no visible text under 12 px' % vp, not bad_small, '; '.join(bad_small[:4]))
        check('pages %s: Security, Health, Usage, Accounts, Extensions show their first row under 260 px' % vp, not bad_first, '; '.join(bad_first))
        pg.evaluate("location.hash = '#/replay/m-date'")
        pg.wait_for_timeout(300)
        r = pg.evaluate("() => { const e = document.querySelector('.rp-event'), b = e.getBoundingClientRect(), s = document.querySelector('.rp-scrub').getBoundingClientRect(); return { bottom: Math.round(b.bottom), h: innerHeight, scrub: Math.round(s.height), sticky: getComputedStyle(document.querySelector('.rp-scrub')).position }; }")
        check('pages %s: the first Replay event row is above 75 %% of the height, under a sticky 56 px scrubber' % vp, r['bottom'] < .75 * r['h'] and r['scrub'] == 56 and r['sticky'] == 'sticky', str(r))
        ctx.close()
    check('pages: no console or page errors', not errs, '; '.join(errs[:3]))
    ctx, pg = new_page(br, 390, 844, base, hash_='#/replay/m-date', query='story=many')
    pg.evaluate("document.querySelector('.main-col').scrollTop = 300")
    pg.wait_for_timeout(100)
    top = pg.evaluate("Math.round(document.querySelector('.rp-scrub').getBoundingClientRect().top - document.querySelector('.main-col').getBoundingClientRect().top)")
    check('replay: the scrubber stays at the top of the column while the list scrolls', top == 0, 'top %s' % top)
    ctx.close()
    # a mouse window shows classic scrollbars, so any scroller that did not hide its own bar shows up here
    ctx, pg = new_page(br, 1440, 900, base, touch=False, query='device=phone')
    bars, mains = [], []
    for route in PAGES:
        pg.evaluate("location.hash = '#/%s'" % route)
        pg.wait_for_timeout(250)
        b = pg.evaluate(BARS)
        if b['rows']:
            bars.append('%s: %s' % (route, b['rows']))
        if not b['main']:
            mains.append(route)
    check('scrollbars: no scroller inside the pages shows a bar (rows, chips, tabs, sheets)', not bars, '; '.join(bars[:3]))
    check('scrollbars: the main column hides its bar on the phone', not mains, ', '.join(mains))
    ctx.close()


def shell_flip(br, base):
    probe = "() => { const v = (s) => { const e = document.querySelector(s); return !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0; }; return { phone: document.documentElement.dataset.phone, dev: document.getElementById('device').dataset.phone, bar: v('.bottombar'), rail: v('.rail'), sw: v('.view-switch') }; }"
    for label, w, h, touch, query, want in [('844x390 touch', 844, 390, True, '', True), ('667x375 touch', 667, 375, True, '', True), ('844x390 mouse', 844, 390, False, '', False),
                                            ('1024x400 touch', 1024, 400, True, '', False), ('390x844 touch', 390, 844, True, '', True), ('1440x900 mouse, phone frame', 1440, 900, False, 'device=phone', True), ('1440x900 mouse', 1440, 900, False, '', False)]:
        ctx, pg = new_page(br, w, h, base, touch=touch, query=query)
        s = pg.evaluate(probe)
        ok = s['phone'] == str(want).lower() and s['dev'] == str(want).lower() and s['bar'] == want and s['rail'] == (not want) and s['sw'] == (not want)
        check(('landscape' if 'touch' in label and w > 600 else 'frame' if 'frame' in label else 'phone shell') + ': %s is %s' % (label, 'the phone shell' if want else 'the desktop shell'), ok, str(s))
        ctx.close()
    ctx, pg = new_page(br, 390, 844, base)
    pg.set_viewport_size({'width': 844, 'height': 390})
    pg.wait_for_timeout(400)
    s = pg.evaluate(probe)
    check('landscape: turning the phone sideways flips the shell live (no reload)', s['phone'] == 'true' and s['bar'] and not s['rail'], str(s))
    pg.set_viewport_size({'width': 1440, 'height': 900})
    ctx.close()


def expected_failures(br, base):
    lits = []
    for rel in source_files(('.js', '.css')):
        for i, line in enumerate(read(rel).splitlines(), 1):
            if re.search(r'bottom:\s*(77|88)px', line):
                lits.append('%s:%d' % (rel, i))
    xfail('no 77px or 88px bar offset literals (measured)', 'A', 'the safety popover and the mission page still sit on hard-coded offsets', not lits, ', '.join(lits))
    ctx, pg = new_page(br, 390, 844, base)
    n = pg.evaluate("""() => [...document.querySelectorAll('.main-col *, .topbar *, .bottombar *')].filter((e) => !e.closest('svg') && e.checkVisibility({ checkVisibilityCSS: true }) && [...e.childNodes].some((c) => c.nodeType === 3 && c.nodeValue.trim()) && parseFloat(getComputedStyle(e).fontSize) < 12).length""")
    xfail('no visible text under 12 px on the Overview (measured)', 'A, B', '%d elements are under 12 px (eyebrows, wordmark)' % n, n == 0)
    cdp = ctx.new_cdp_session(pg)
    top = pg.evaluate("() => { const e = document.querySelector('.archeus-map > svg'); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height * .7 }; }")
    if top:
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': top['x'], 'y': top['y']}]})
        for i in range(1, 9):
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': top['x'], 'y': top['y'] - 25 * i}]})
            pg.wait_for_timeout(16)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        pg.wait_for_timeout(300)
        moved = pg.evaluate("document.querySelector('.main-col').scrollTop")
        xfail('a swipe that starts on the Overview map scrolls the page (measured)', 'B', 'the map svg is touch-action: none, scrollTop stays 0', moved > 0, 'scrollTop %s' % moved)
    ctx.close()
    for name, slice_, reason in [
        ('a swipe that starts on the Work graph and on every sheet handle scrolls or drags', 'B, C', 'Work graph and the existing sheets are not on the new primitive yet'),
        ('Tell input, palette input and every focused field stay above the keyboard (faked 440 and 300 px)', 'A, C', 'Tell sheet and palette are not pinned to --vv-bottom yet'),
        ('toast sits above the bar and not over a sheet header', 'A', 'the toast is still anchored at the top'),
        ('first screen: sentence, ledger, counts and Review above the bar, centre in the lower 60 %', 'B', 'the Overview is still the map page'),
        ('Work first row under 60 % of the height', 'B', 'Work is still the graph page'),
        ('scale at ?story=huge: under 1200 elements in the main column and under 8 screens on Work, Projects and Overview, 100 projects searchable in the palette', 'B', 'lists are not capped yet'),
        ('safety sheet, inspector and bar never overlap with injected insets', 'A, C', 'they still use env() and literals of their own'),
        ('Stop two-step from the bar with the confirm on the far side', 'A', 'the bar is still Tell, Places, Stop with the old safety popover'),
        ('every existing sheet (Places, Tell, inspectors) is an openSheet() with detents; the Replay evidence and the "..." sheets already are', 'A, C', 'not migrated yet'),
        ('sheet primaries are 48 px', 'A, C', 'no sheet has a primary action yet')]:
        xfail(name, slice_, reason)


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=0)
    a = ap.parse_args()
    single_threshold()
    pwa_static()
    port = a.port or lp.free_port()
    srv = lp.start_server(port)
    base = 'http://127.0.0.1:%d/index.html' % port
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for fn in (shell_flip, safe_areas, sheet_checks, sizes, page_checks, expected_failures):
                try:
                    fn(br, base)
                except Exception as e:  # a crashed check is a failure, not a silent skip
                    check(fn.__name__ + ' ran to the end', False, '%s: %s' % (type(e).__name__, str(e)[:300]))
            br.close()
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            srv.kill()
    fails = 0
    for status, name, detail in results:
        print('%-6s %s%s' % (status, name, ('\n         ' + detail) if detail and status != 'ok' else ''))
        fails += status == 'FAIL'
    count = lambda s: sum(1 for r in results if r[0] == s)
    print('\nPHONE PROBE: %d ok, %d FAIL, %d xfail, %d XPASS' % (count('ok'), fails, count('xfail'), count('XPASS')))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
