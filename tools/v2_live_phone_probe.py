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
ROUTES = ['now', 'work', 'chat', 'settings', 'projects', 'security', 'health', 'usage', 'accounts', 'extensions', 'replay/m-date']
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
        ('a swipe that starts on the Work graph scrolls', 'B', 'the Work graph is not rebuilt yet'),
        ('palette input stays above the keyboard (faked 440 and 300 px)', 'A', 'the palette is not pinned to --vv-bottom yet'),
        ('toast sits above the bar and not over a sheet header', 'A', 'the toast is still anchored at the top'),
        ('first screen: sentence, ledger, counts and Review above the bar, centre in the lower 60 %', 'B', 'the Overview is still the map page'),
        ('Work first row under 60 % of the height; Security, Health, Usage, Accounts, Extensions first row under 260 px', 'B, D', 'page heads not rebuilt'),
        ('scale at ?story=huge: under 1200 elements in the main column and under 8 screens on Work, Projects and Overview, 100 projects searchable in the palette', 'B', 'lists are not capped yet'),
        ('safety sheet and bar never overlap with injected insets', 'A', 'the safety popover still uses a literal offset of its own'),
        ('Stop two-step from the bar with the confirm on the far side', 'A', 'the bar is still Tell, Places, Stop with the old safety popover'),
        ('Places and Replay evidence are openSheet() sheets with detents', 'A, D', 'not migrated yet'),
        ('Places and safety sheet primaries are 48 px', 'A', 'not migrated yet')]:
        xfail(name, slice_, reason)


# ---------- slice C: the Tell sheet, the inspector sheets, the picker sheet, the Chat page ----------
VV = "(h) => { Object.defineProperty(visualViewport, 'height', { get: () => h, configurable: true }); visualViewport.dispatchEvent(new Event('resize')); }"
VV_OFF = "() => { delete visualViewport.height; visualViewport.dispatchEvent(new Event('resize')); }"
# the field's centre must be inside the visual viewport and hit-test to the field itself (no bar, toast or sheet over it)
FIELD = """() => { const e = document.activeElement; if (!e) return null; const r = e.getBoundingClientRect(), vv = visualViewport.height, hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return { tag: e.tagName, cls: e.className, top: Math.round(r.top), bottom: Math.round(r.bottom), vv, inside: r.top >= 0 && r.bottom <= vv + 0.5, hits: hit === e }; }"""
# vertical scrollers inside the open sheet: only one may really scroll, and none may draw a scrollbar
SCROLLERS = """() => { const sh = document.querySelector('.sheet'); if (!sh) return null; const out = [];
  for (const e of [sh, ...sh.querySelectorAll('*')]) { const cs = getComputedStyle(e); if (!/(auto|scroll)/.test(cs.overflowY) || e.scrollHeight <= e.clientHeight + 1 || !e.checkVisibility()) continue;
    out.push({ cls: String(e.className).slice(0, 28), bar: cs.scrollbarWidth }); }
  return out; }"""
HIT = "(sel) => { const e = document.querySelector(sel); if (!e) return null; const cs = getComputedStyle(e, '::after'), r = e.getBoundingClientRect(); return { h: Math.round(Math.max(r.height, parseFloat(cs.height) || 0)), w: Math.round(Math.max(r.width, parseFloat(cs.width) || 0)) }; }"
INSP_ROUTES = ['work/t-date-1', 'work/x-date-1', 'work/p-search-v1', 'work/v-1', 'work/i-1', 'work/k-4', 'work/prj-archeus', 'security/sec-b5', 'extensions/h-1', 'accounts/mdl-claude-sonnet', 'health/chk-accounts']


def tell_open(pg, text=None):
    pg.click('[data-key="bb-tell"]')
    pg.wait_for_timeout(300)
    if text:
        pg.keyboard.type(text)
        pg.wait_for_timeout(250)


def tell_sheet(br, base):
    errs = []
    ctx, pg = new_page(br, 390, 844, base, errs=errs)
    tell_open(pg)
    s = pg.evaluate(SHEET_STATE)
    check('tell sheet: an openSheet dialog named Tell Archeus, modeless at peek, focus in the field', s['role'] == 'dialog' and s['label'] == 'Tell Archeus' and s['modal'] is None and pg.evaluate("document.activeElement.classList.contains('cinput')"), str(s))
    check('tell sheet: peek is the composer and the last reply (280 px)', s['detent'] == 'peek' and s['h'] == 280, str(s))
    check('tell sheet: handle and Close are 44 px, the Send button is 48 px', s['gripH'] >= 44 and s['closeH'] >= 44 and pg.evaluate(HIT, '.chatsheet .csend')['h'] >= 48, str(pg.evaluate(HIT, '.chatsheet .csend')))
    pg.click('.sheet-grip')
    pg.wait_for_timeout(150)
    a = pg.evaluate(SHEET_STATE)
    pg.click('.sheet-grip')
    pg.wait_for_timeout(150)
    b = pg.evaluate(SHEET_STATE)
    check('tell sheet: the handle button steps peek, half, full', a['detent'] == 'half' and b['detent'] == 'full' and b['modal'] == 'true', '%s %s' % (a, b))
    s = drag(pg, 150)
    check('tell sheet: a drag down on the handle goes to the detent below', s and s['detent'] == 'half', str(s))
    check('tell sheet: the thread is its one scroller and draws no scrollbar', all(x['bar'] == 'none' for x in pg.evaluate(SCROLLERS)) and len(pg.evaluate(SCROLLERS)) <= 1, str(pg.evaluate(SCROLLERS)))
    pg.go_back()
    pg.wait_for_timeout(300)
    check('tell sheet: the system Back closes it', pg.evaluate("!document.querySelector('.sheet') && !document.querySelector('.sheet-wrap')") or pg.evaluate("!!document.querySelector('.sheet-wrap[data-leaving]')"), '')
    check('tell sheet: closing returns focus to the Tell button', pg.evaluate("document.activeElement.dataset.key") == 'bb-tell', pg.evaluate('document.activeElement.outerHTML.slice(0, 80)'))
    # the keyboard: a faked visual viewport (no IME in headless): the field stays above it, the bar steps aside, the sheet never exceeds what is left
    for vv in (440, 300):
        tell_open(pg)
        pg.focus('.chatsheet input.cinput')
        pg.evaluate(VV, vv)
        pg.wait_for_timeout(300)
        f = pg.evaluate(FIELD)
        s = pg.evaluate(SHEET_STATE)
        bar = pg.evaluate("getComputedStyle(document.querySelector('.bottombar')).display")
        check('keyboard %d: the Tell field is inside the visual viewport and nothing sits over it' % vv, f and f['inside'] and f['hits'], str(f))
        check('keyboard %d: the sheet is no taller than min(detent, viewport - 8) and the bar is hidden' % vv, s['h'] <= vv - 8 and bar == 'none', '%s bar %s' % (s, bar))
        pg.evaluate(VV_OFF)
        pg.evaluate('document.activeElement.blur()')
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(400)
    check('tell sheet: no console or page errors', not errs, '; '.join(errs[:3]))
    ctx.close()
    # the slash menu replaces the thread and never pushes the composer out (360x740, with and without the keyboard)
    ctx, pg = new_page(br, 360, 740, base, errs=errs)
    for vv in (None, 440, 300):
        tell_open(pg)
        if vv:
            pg.evaluate(VV, vv)
            pg.wait_for_timeout(250)
        pg.keyboard.type('/')
        pg.wait_for_timeout(350)
        m = pg.evaluate("""() => { const sl = document.querySelector('.chatsheet .slash'), c = document.querySelector('.chatsheet .cinput'), row = document.querySelector('.chatsheet .crow2').getBoundingClientRect(), vv = visualViewport.height, cr = c.getBoundingClientRect();
          return { menu: sl && !sl.hidden ? Math.round(sl.getBoundingClientRect().height) : -1, vv, row: Math.round(row.height), inside: cr.top >= 0 && cr.bottom <= vv + .5, hits: document.elementFromPoint(cr.left + cr.width / 2, cr.top + cr.height / 2) === c, log: document.querySelector('.chatsheet .sheet-body').getBoundingClientRect().height }; }""")
        check('slash menu at 360x740%s: the composer stays visible (row >= 96 px), the menu is at most 40 %% of the viewport and takes the thread\'s place' % (' with a %d px viewport' % vv if vv else ''),
              m['menu'] > 0 and m['inside'] and m['hits'] and m['row'] >= 96 and m['menu'] <= m['vv'] * .4 + 1 and m['log'] == 0, str(m))
        sc = pg.evaluate(SCROLLERS)
        check('slash menu%s: it is the one scroller and has no scrollbar' % (' (%d px)' % vv if vv else ''), len(sc) <= 1 and all(x['bar'] == 'none' for x in sc), str(sc))
        if vv:
            pg.evaluate(VV_OFF)
        pg.keyboard.press('Escape')
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(300)
        pg.evaluate('document.activeElement.blur()')
        pg.evaluate("window.v2live.ui.draft = ''")
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(400)
    check('slash menu: no console or page errors', not errs, '; '.join(errs[:3]))
    ctx.close()


def inspector_sheets(br, base):
    errs = []
    ctx, pg = new_page(br, 390, 844, base, hash_='#/work', errs=errs)
    bad_scroll, bad_prim, nodet = [], [], []
    for r in INSP_ROUTES:
        pg.evaluate("location.hash = '#/%s'" % r.split('/')[0])
        pg.wait_for_timeout(120)
        pg.evaluate("location.hash = '#/%s'" % r)
        pg.wait_for_timeout(400)
        s = pg.evaluate(SHEET_STATE)
        if not s:
            nodet.append(r + ': no sheet')
            continue
        if s['detent'] != 'peek' or abs(s['h'] - .4 * s['wrapH']) > 3:
            nodet.append('%s: %s %s of %s' % (r, s['detent'], s['h'], s['wrapH']))
        for peek in (True, False):
            if not peek:
                pg.click('.sheet-grip')
                pg.wait_for_timeout(250)
            sc = pg.evaluate(SCROLLERS)
            if len(sc) > 1 or any(x['bar'] != 'none' for x in sc):
                bad_scroll.append('%s %s: %s' % (r, 'peek' if peek else 'full', sc))
        for sel in ('.sheet .btn.primary', '.sheet .btn.decide'):
            hit = pg.evaluate(HIT, sel)
            if hit and hit['h'] < 48:
                bad_prim.append('%s %s: %s' % (r, sel, hit))
    check('inspector sheets: every kind opens as a sheet at peek (40 %)', not nodet, '; '.join(nodet[:4]))
    check('inspector sheets: the body is the one vertical scroller and none draws a scrollbar (peek and full)', not bad_scroll, '; '.join(bad_scroll[:4]))
    check('inspector sheets: primary actions are 48 px', not bad_prim, '; '.join(bad_prim[:4]))
    # one sheet in detail: the idea inspector has a primary action
    pg.evaluate("location.hash = '#/work'")
    pg.wait_for_timeout(400)
    pg.evaluate("location.hash = '#/work/i-1'")
    pg.wait_for_timeout(400)
    st = pg.evaluate(SHEET_STATE)
    foot = pg.evaluate("() => { const f = document.querySelector('.sheet .sheet-foot').getBoundingClientRect(), s = document.querySelector('.sheet').getBoundingClientRect(); return { fromBottom: Math.round(s.bottom - f.bottom), btn: !!document.querySelector('.sheet .isf .btn.primary'), peekState: !!document.querySelector('.sheet .isl .badge, .sheet .isl [class*=badge], .sheet .isl .smark') }; }")
    check('inspector sheet: title, state word and the primary action in the thumb zone (sticky foot at the bottom)', foot['btn'] and foot['fromBottom'] <= 1 + 34 and foot['peekState'], str(foot))
    check('inspector sheet: handle and Close are 44 px, the handle says Expand', st['gripH'] >= 44 and st['closeH'] >= 44 and st['gripLabel'] == 'Expand', str(st))
    pg.click('.sheet-grip')
    pg.wait_for_timeout(250)
    s = pg.evaluate(SHEET_STATE)
    check('inspector sheet: the handle button goes to full (92 %) and says Collapse', s['detent'] == 'full' and abs(s['h'] - .92 * s['wrapH']) <= 3 and s['gripLabel'] == 'Collapse', str(s))
    s = drag(pg, 420, steps=10, wait=100)
    check('inspector sheet: a slow drag down on the handle settles on peek', s and s['detent'] == 'peek', str(s))
    pg.evaluate("document.documentElement.dataset.notes = 'on'")
    n = pg.evaluate("() => { const d = document.querySelector('.sheet .dnote-d'); return d && { open: d.open, h: Math.round(d.getBoundingClientRect().height), s: Math.round(d.firstElementChild.getBoundingClientRect().height) }; }")
    pg.evaluate("document.documentElement.dataset.notes = 'off'")
    check('inspector sheet: a decision note is one collapsed 44 px line', n and not n['open'] and n['h'] == 44 and n['s'] == 44, str(n))
    cdp = ctx.new_cdp_session(pg)
    g = pg.evaluate(GRIP_BOX)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': g['x'], 'y': g['y']}]})
    for i in range(1, 9):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': g['x'], 'y': g['y'] - 40 * i}]})
        pg.wait_for_timeout(16)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    pg.wait_for_timeout(300)
    s = pg.evaluate(SHEET_STATE)
    check('inspector sheet: a touch swipe that starts on the handle drags the sheet (no scroll trap)', s and s['detent'] == 'full', str(s))
    pg.evaluate("location.hash = '#/work'")
    pg.wait_for_timeout(400)
    check('inspector sheet: leaving the route closes the sheet', pg.evaluate("!document.querySelector('.sheet:not([data-leaving])') || !document.querySelector('.sheet-wrap:not([data-leaving])')"), '')
    # Back, Close, Esc: the route is the sheet's address
    pg.evaluate("location.hash = '#/work/i-1'")
    pg.wait_for_timeout(400)
    pg.go_back()
    pg.wait_for_timeout(400)
    check('inspector sheet: the system Back closes it and returns to #/work', pg.evaluate("location.hash") == '#/work' and pg.evaluate("!document.querySelector('.sheet-wrap:not([data-leaving])')"), pg.evaluate('location.hash'))
    pg.evaluate("location.hash = '#/work/i-1'")
    pg.wait_for_timeout(400)
    pg.click('.sheet .sheet-close')
    pg.wait_for_timeout(400)
    check('inspector sheet: Close leaves the route', pg.evaluate("location.hash") == '#/work' and pg.evaluate("!document.querySelector('.sheet-wrap:not([data-leaving])')"), pg.evaluate('location.hash'))
    pg.evaluate("location.hash = '#/work/i-1'")
    pg.wait_for_timeout(400)
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(400)
    check('inspector sheet: Esc leaves the route', pg.evaluate("location.hash") == '#/work' and pg.evaluate("!document.querySelector('.sheet-wrap:not([data-leaving])')"), pg.evaluate('location.hash'))
    check('inspector sheets: no console or page errors', not errs, '; '.join(errs[:3]))
    ctx.close()


def pages_and_insets(br, base):
    errs = []
    ctx, pg = new_page(br, 390, 844, base, hash_='#/work/m-date', errs=errs)
    pg.evaluate("() => { const s = document.documentElement.style; s.setProperty('--sa-t', '47px'); s.setProperty('--sa-b', '34px'); window.dispatchEvent(new Event('resize')); }")
    pg.wait_for_timeout(300)
    for route in ('work/m-date', 'work/a-1'):
        pg.evaluate("location.hash = '#/%s'" % route)
        pg.wait_for_timeout(450)
        r = pg.evaluate("""() => { const i = document.querySelector('.inspector').getBoundingClientRect(), t = document.querySelector('.topbar').getBoundingClientRect(), b = document.querySelector('.bottombar'), br = b.getBoundingClientRect();
          return { top: Math.round(i.top - t.bottom), bottom: Math.round(br.top - i.bottom), shown: getComputedStyle(b).display !== 'none', h: Math.round(i.height) }; }""")
        check('%s page: sits between the top bar and the bar with --sa-t 47 and --sa-b 34 (no overlap, no gap over 1 px)' % route, abs(r['top']) <= 1 and abs(r['bottom']) <= 1 and r['shown'] and r['h'] > 300, str(r))
    ctx.close()
    # a mission page offers no sheet: Stop (the bar) stays reachable under it
    ctx, pg = new_page(br, 390, 844, base, hash_='#/work/m-date', errs=errs)
    check('mission page: a full page, not a sheet, and the bar is not covered', pg.evaluate("!document.querySelector('.sheet') && document.elementFromPoint(195, 844 - 20).closest('.bottombar') !== null"), '')
    ctx.close()


def picker_sheet(br, base):
    errs = []
    for story, search in (('', False), ('many', True), ('huge', True)):
        ctx, pg = new_page(br, 390, 844, base, hash_='#/chat', query='story=' + story if story else '', errs=errs)
        pg.click('[data-key="chat-scope-head"]')
        pg.wait_for_timeout(350)
        r = pg.evaluate("""() => { const sh = document.querySelector('.sheet'); if (!sh) return null; const opts = [...sh.querySelectorAll('[role=option]')], vis = opts.filter((o) => o.checkVisibility());
          return { n: opts.length, minH: Math.min(...vis.map((o) => Math.round(o.getBoundingClientRect().height))), sel: sh.querySelectorAll('[role=option][aria-selected=true]').length, tick: !!sh.querySelector('[aria-selected=true] svg'), search: !!sh.querySelector('input[type=search]'), role: sh.getAttribute('role'), pop: !!document.querySelector('.pkpop') }; }""")
        check('picker sheet (%s): a bottom sheet, not a popover; 48 px options; the current one has aria-selected and a tick' % (story or 'default'), r and not r['pop'] and r['role'] == 'dialog' and r['minH'] >= 48 and r['sel'] == 1 and r['tick'], str(r))
        check('picker sheet (%s): a search field exactly when there are more than 12 options (%s)' % (story or 'default', r and r['n']), r and r['search'] == (r['n'] > 12), str(r))
        sc = pg.evaluate(SCROLLERS)
        check('picker sheet (%s): one scroller, no scrollbar' % (story or 'default'), len(sc) <= 1 and all(x['bar'] == 'none' for x in sc), str(sc))
        if r and r['search']:
            for vv in (440, 300):
                pg.focus('.sheet input[type=search]')
                pg.evaluate(VV, vv)
                pg.wait_for_timeout(300)
                f = pg.evaluate(FIELD)
                check('picker sheet (%s) keyboard %d: the search field is inside the visual viewport and nothing sits over it' % (story, vv), f and f['inside'] and f['hits'], str(f))
                pg.evaluate(VV_OFF)
            pg.fill('.sheet input[type=search]', 'zzzz')
            check('picker sheet (%s): a search with no match says so' % story, pg.evaluate("!!document.querySelector('.sheet .pk-none')"), '')
            pg.fill('.sheet input[type=search]', '')
        pg.keyboard.press('ArrowDown')
        pg.keyboard.press('Enter')
        pg.wait_for_timeout(400)
        check('picker sheet (%s): choosing closes it and keeps the destination chip' % (story or 'default'), pg.evaluate("!document.querySelector('.sheet-wrap:not([data-leaving])')") and pg.evaluate("!!document.querySelector('[data-key=\"chat-scope-head\"]')"), '')
        ctx.close()
    ctx, pg = new_page(br, 1280, 720, base, hash_='#/chat', touch=False)
    pg.click('[data-key="chat-scope-head"]')
    pg.wait_for_timeout(250)
    check('picker: on a desktop window it is still the popover', pg.evaluate("!!document.querySelector('.pkpop') && !document.querySelector('.sheet')"), '')
    ctx.close()
    check('picker sheets: no console or page errors', not errs, '; '.join(errs[:3]))


def chat_page(br, base):
    errs = []
    ctx, pg = new_page(br, 390, 844, base, hash_='#/chat', errs=errs)
    r = pg.evaluate("""() => { const cb = document.querySelector('.cb'), kids = [...cb.children].filter((e) => e.checkVisibility() && !e.classList.contains('vh') && e.getBoundingClientRect().height > 0), rows = new Set(kids.map((e) => Math.round(e.getBoundingClientRect().top / 8)));
      return { h: Math.round(cb.getBoundingClientRect().height), rows: rows.size, tabs: !!document.querySelector('.cb-tabs'), more: !!document.querySelector('[data-key=chat-more]') }; }""")
    check('chat page: the header is one row (scope, mission, needs you, More) and the tab strip is gone', r['rows'] == 1 and r['h'] <= 60 and not r['tabs'] and r['more'], str(r))
    c = pg.evaluate("() => { const c = document.querySelector('.chatpage .composer2').getBoundingClientRect(), b = document.querySelector('.bottombar').getBoundingClientRect(); return { gap: Math.round(b.top - c.bottom), tell: !!document.querySelector('.sheet') }; }")
    check('chat page: the composer is pinned just above the bar and Tell opens no sheet here', 0 <= c['gap'] <= 12 and not c['tell'], str(c))
    pg.click('[data-key="bb-tell"]')
    pg.wait_for_timeout(300)
    check('chat page: the Tell button focuses the page composer instead of a sheet', pg.evaluate("!document.querySelector('.sheet') && document.activeElement.classList.contains('cinput')"), '')
    for vv in (440, 300):
        pg.focus('.chatpage input.cinput')
        pg.evaluate(VV, vv)
        pg.wait_for_timeout(300)
        f = pg.evaluate(FIELD)
        bar = pg.evaluate("getComputedStyle(document.querySelector('.bottombar')).display")
        check('chat page keyboard %d: the composer field is inside the visual viewport, nothing sits over it, the bar is hidden' % vv, f and f['inside'] and f['hits'] and bar == 'none', '%s bar %s' % (f, bar))
        pg.evaluate(VV_OFF)
        pg.evaluate('document.activeElement.blur()')
        pg.wait_for_timeout(300)
    pg.click('[data-key="chat-more"]')
    pg.wait_for_timeout(250)
    check('chat page: More holds the three views, and Receipts switches the thread', pg.evaluate("document.querySelectorAll('.pkpop [data-key^=chat-tab-]').length") == 3, '')
    pg.click('.pkpop [data-key="chat-tab-receipts"]')
    pg.wait_for_timeout(300)
    check('chat page: the Receipts view shows', pg.evaluate("!!document.querySelector('.cp-scroll')"), '')
    check('chat page: no scrollbar on the thread and lists', all(x == 'none' for x in pg.evaluate("[...document.querySelectorAll('.msgs, .cp-scroll')].map((e) => getComputedStyle(e).scrollbarWidth)")), '')
    check('chat page: no console or page errors', not errs, '; '.join(errs[:3]))
    ctx.close()


def sheets_slice_c(br, base):
    for fn in (tell_sheet, inspector_sheets, pages_and_insets, picker_sheet, chat_page):
        try:
            fn(br, base)
        except Exception as e:
            check(fn.__name__ + ' ran to the end', False, '%s: %s' % (type(e).__name__, str(e)[:300]))


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
            for fn in (shell_flip, safe_areas, sheet_checks, sizes, sheets_slice_c, expected_failures):
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
