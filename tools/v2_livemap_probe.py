"""V2 Live constellation map probe. Serve the worktree root first, e.g. py -m http.server 8861 --bind 127.0.0.1,
then run through testlock: py D:\\Archeus\\.collab\\testlock.py -- py tools\\v2_livemap_probe.py
BASE=http://127.0.0.1:8861 OUT=<dir for screenshots>; localhost only.
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get('BASE', 'http://127.0.0.1:8861').rstrip('/')
OUT = os.environ.get('OUT', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.pv20-out', 'shots', 'probe'))
URL = BASE + '/clients/v2-live-map/demo.html?embed=1'
SIZES = [(320, 640), (390, 844), (768, 1024), (1280, 720), (1440, 900), (2000, 930), (2560, 1440)]
THEMES = ['dark', 'light', 'dark-high-contrast', 'light-high-contrast']
failures = []
os.makedirs(OUT, exist_ok=True)


def check(ok, label):
    print(('ok   ' if ok else 'FAIL ') + label, flush=True)
    if not ok:
        failures.append(label)


GEOM = """() => {
  const r = el => { const b = el.getBoundingClientRect(); return {x: b.x, y: b.y, w: b.width, h: b.height}; };
  const host = document.querySelector('.archeus-map');
  const labels = [...host.querySelectorAll('.am-label')].map(g => ({id: g.dataset.nodeId, ...r(g)}));
  const stars = [...host.querySelectorAll('.am-star')].map(g => { const b = g.querySelector('.am-body').getBoundingClientRect(); return {id: g.dataset.nodeId, cx: b.x + b.width / 2, cy: b.y + b.height / 2, r: Math.max(b.width, b.height) / 2}; });
  const hits = [...host.querySelectorAll('.am-hit circle')].map(c => r(c));
  const buttons = [...host.querySelectorAll('.am-controls button')].map(r);
  const core = ['.am-core-outline', '.am-wordmark'].map(s => r(host.querySelector(s)));
  const needs = [...host.querySelectorAll('.am-star.am-state-needs-you')].map(g => g.dataset.nodeId);
  const col = s => { const m = getComputedStyle(s).fill.match(/[\\d.]+/g).map(Number); return m; };
  const bg = getComputedStyle(host).backgroundColor.match(/[\\d.]+/g).map(Number);
  const text = [...host.querySelectorAll('.am-label-title, .am-label-meta')].map(t => ({fill: col(t), cls: t.getAttribute('class'), id: t.parentNode.dataset.nodeId}));
  return {labels, stars, hits, buttons, core, needs, bg, text, overflow: host.dataset.labelOverflow,
    raster: host.querySelectorAll('img, canvas, image, foreignObject, video').length,
    filters: [...host.querySelectorAll('*')].filter(e => { const s = getComputedStyle(e); return (s.filter !== 'none') || (s.backdropFilter && s.backdropFilter !== 'none'); }).length,
    scrollW: document.documentElement.scrollWidth, scrollH: document.documentElement.scrollHeight, w: innerWidth, h: innerHeight, dpr: devicePixelRatio,
    nodes: stars.length, hullCount: host.querySelectorAll('.am-hull').length};
}"""


def rect_hits_circle(b, c, pad=0):
    x = min(max(c['cx'], b['x']), b['x'] + b['w'])
    y = min(max(c['cy'], b['y']), b['y'] + b['h'])
    return ((x - c['cx']) ** 2 + (y - c['cy']) ** 2) ** .5 < c['r'] + pad


def rects_overlap(a, b):
    return a['x'] < b['x'] + b['w'] and a['x'] + a['w'] > b['x'] and a['y'] < b['y'] + b['h'] and a['y'] + a['h'] > b['y']


def lum(c):
    f = [(v / 255) for v in c[:3]]
    f = [v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4 for v in f]
    return .2126 * f[0] + .7152 * f[1] + .0722 * f[2]


def ratio(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + .05) / (lb + .05)


def open_page(br, w, h, dpr=1, **ctx):
    context = br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=dpr, **ctx)
    pg = context.new_page()
    errors = []
    pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(URL)
    pg.wait_for_function('window.map && document.querySelectorAll(".am-star").length > 0')
    pg.evaluate("() => { window.__sel = []; window.map.on('select', id => window.__sel.push(id)); }")
    return pg, errors


def geometry_checks(pg, tag, phone):
    g = pg.evaluate(GEOM)
    L = g['labels']
    over = [(a['id'], b['id']) for i, a in enumerate(L) for b in L[i + 1:] if rects_overlap(a, b)]
    check(not over, f'{tag}: no label/label overlap ({len(L)} labels{", overlaps " + str(over[:3]) if over else ""})')
    covered = [(l['id'], s['id']) for l in L for s in g['stars'] if rect_hits_circle(l, s)]
    check(not covered, f'{tag}: no label covers a node{" " + str(covered[:3]) if covered else ""}')
    core = [l['id'] for l in L for c in g['core'] if rects_overlap(l, c)]
    check(not core, f'{tag}: no label covers the core mark or its wordmark')
    ctl = [l['id'] for l in L for b in g['buttons'] if rects_overlap(l, b)]
    check(not ctl, f'{tag}: no label under the map controls')
    outside = [l['id'] for l in L if l['x'] < 0 or l['y'] < 0 or l['x'] + l['w'] > g['w'] or l['y'] + l['h'] > g['h']]
    check(not outside, f'{tag}: every label inside the viewport')
    check(g['overflow'] == '0', f'{tag}: no priority label overflow (selected and needs-you all labelled): {g["overflow"]}')
    shown = {l['id'] for l in L}
    check(all(n in shown for n in g['needs']), f'{tag}: every needs-you node has a label')
    check(len(L) >= (5 if phone else 12), f'{tag}: enough labels ({len(L)})')
    small = [round(min(h['w'], h['h']), 1) for h in g['hits'] if min(h['w'], h['h']) < 44 - .01]
    check(not small and len(g['hits']) == g['nodes'], f'{tag}: all {g["nodes"]} hit targets >= 44 px{" " + str(small[:3]) if small else ""}')
    smallb = [b for b in g['buttons'] if min(b['w'], b['h']) < 44 - .01]
    check(not smallb and len(g['buttons']) == 4, f'{tag}: 4 control buttons >= 44 px')
    under = [s['id'] for s in g['stars'] if any(b['x'] <= s['cx'] <= b['x'] + b['w'] and b['y'] <= s['cy'] <= b['y'] + b['h'] for b in g['buttons'])]
    check(not under, f'{tag}: no node under the controls')
    offscreen = [s['id'] for s in g['stars'] if s['cx'] < 0 or s['cy'] < 0 or s['cx'] > g['w'] or s['cy'] > g['h']]
    check(not offscreen, f'{tag}: every node inside the viewport')
    check(g['scrollW'] <= g['w'] and g['scrollH'] <= g['h'], f'{tag}: no page scroll ({g["scrollW"]}x{g["scrollH"]} in {g["w"]}x{g["h"]})')
    low = sorted({round(ratio(t['fill'], g['bg']), 2) for t in g['text']})
    bad = [t['cls'] for t in g['text'] if ratio(t['fill'], g['bg']) < 4.5]
    check(not bad, f'{tag}: label text contrast >= 4.5 (min {low[0] if low else None})')
    check(g['raster'] == 0, f'{tag}: map holds no img, canvas or other raster element')
    check(g['filters'] == 0, f'{tag}: no filter or backdrop-filter in the map')
    return g


def motion_checks(pg, tag, reduced):
    pg.wait_for_timeout(900)
    names = pg.evaluate("document.getAnimations().filter(a => a.playState === 'running').map(a => a.animationName || a.constructor.name)")
    if reduced:
        check(names == [], f'{tag}: 0 running animations under reduced motion ({names})')
    else:
        check(names == ['core-breath'], f'{tag}: exactly 1 running animation at idle, the core breath ({names})')
        scale = pg.evaluate("(() => { const a = document.querySelector('[data-core]').getAnimations()[0]; const t = a.effect.getTiming(); return [t.duration, a.effect.getKeyframes().map(k => k.transform)]; })()")
        check(scale[0] == 6000 and scale[1] == ['scale(1)', 'scale(1.018)', 'scale(1)'], f'{tag}: breath is 6000 ms, scale 1 to 1.018 to 1')


def click_every_node(pg, tag):
    pts = pg.evaluate("[...document.querySelectorAll('.am-star')].map(g => { const b = g.querySelector('.am-body').getBoundingClientRect(); return [g.dataset.nodeId, b.x + b.width / 2, b.y + b.height / 2]; })")
    bad = []
    for nid, x, y in pts:
        pg.evaluate('window.__sel.length = 0')
        pg.mouse.click(x, y)
        if pg.evaluate('window.__sel.at(-1)') != nid:
            bad.append(nid)
    check(not bad, f'{tag}: a click on each of {len(pts)} nodes selects exactly that node{" miss " + str(bad[:5]) if bad else ""}')


def keyboard_checks(pg, tag):
    total = pg.evaluate("document.querySelectorAll('.am-hit').length")
    seen = set()
    for _ in range(total + 2):
        pg.keyboard.press('Tab')
        nid = pg.evaluate("document.activeElement.classList.contains('am-hit') ? document.activeElement.dataset.nodeId : null")
        if nid:
            seen.add(nid)
    check(len(seen) == total, f'{tag}: Tab visits all {total} nodes ({len(seen)})')
    pg.evaluate("document.querySelector('.am-hit[data-node-id=\"n9\"]').focus()")
    moved = 0
    for key in ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp']:
        pg.evaluate("document.querySelector('.am-hit[data-node-id=\"n9\"]').focus()")
        pg.keyboard.press(key)
        if pg.evaluate("document.activeElement.dataset.nodeId") != 'n9':
            moved += 1
    check(moved >= 3, f'{tag}: arrow keys move focus to a neighbour ({moved}/4 directions)')
    pg.keyboard.press('ArrowRight')
    pg.evaluate('window.__sel.length = 0')
    nid = pg.evaluate("document.activeElement.dataset.nodeId")
    pg.keyboard.press('Enter')
    check(pg.evaluate('window.__sel.at(-1)') == nid and pg.evaluate(f"!!document.querySelector('.am-star.am-selected[data-node-id=\"{nid}\"]')"), f'{tag}: Enter selects the focused node ({nid})')
    check(pg.evaluate("document.querySelector('.am-hit').getAttribute('aria-label').split(', ').length >= 4") and pg.evaluate("document.querySelectorAll('.am-equivalent tbody tr').length") == total, f'{tag}: named targets and a node table row for every node')


def view_checks(pg, tag, w, h):
    tf = lambda: pg.evaluate("document.querySelector('.am-world').getAttribute('transform')")
    base = tf()
    check(base == 'translate(0 0) scale(1)', f'{tag}: initial camera is identity ({base})')
    pg.mouse.move(w / 2, h / 2)
    pg.mouse.wheel(0, -400)
    pg.wait_for_timeout(100)
    zoomed = tf()
    check(zoomed != base and 'scale(1)' not in zoomed, f'{tag}: wheel zooms ({zoomed})')
    pg.click('button[aria-label="Reset map view"]')
    check(tf() == base, f'{tag}: Reset restores the view')
    pg.evaluate('window.__sel.length = 0')
    free = pg.evaluate("""(() => { for (let y = innerHeight * .96; y > 20; y -= 17) for (let x = 24; x < innerWidth - 230; x += 23) { const e = document.elementFromPoint(x, y); if (e && !e.closest('.am-hit, button')) return [x, y]; } return null; })()""")
    pg.mouse.move(*free); pg.mouse.down(); pg.mouse.move(free[0] + 30, free[1] - 25, steps=6); pg.mouse.up()
    panned = tf()
    check(panned != base and pg.evaluate('window.__sel.length') == 0, f'{tag}: drag pans and does not select ({panned})')
    pg.click('button[aria-label="Reset map view"]')
    for _ in range(3):
        pg.click('button[aria-label="Zoom out"]')
    small = pg.evaluate("[...document.querySelectorAll('.am-hit circle')].filter(c => { const b = c.getBoundingClientRect(); return Math.min(b.width, b.height) < 43.99; }).length")
    check(small == 0 and 'scale(1)' not in tf(), f'{tag}: targets stay >= 44 px zoomed out ({tf()})')
    pg.click('button[aria-label="Fit all nodes"]')
    fit = tf()
    check(fit != base, f'{tag}: Fit changes the view ({fit})')
    pg.click('button[aria-label="Zoom in"]')
    pg.click('button[aria-label="Reset map view"]')
    check(tf() == base, f'{tag}: Reset after Fit and Zoom in')


PERF = """async () => {
  const {createMap} = await import('/clients/v2-live-map/map.js');
  const el = document.createElement('div');
  el.style.cssText = 'position:fixed;left:0;top:0;width:1280px;height:720px;z-index:-1';
  document.body.append(el);
  const map = createMap(el, {seed: 'perf'});
  const kinds = ['Mission', 'Idea', 'Knowledge', 'Project'], states = ['idle', 'running', 'needs-you', 'blocked', 'done'];
  const nodes = Array.from({length: 200}, (_, i) => ({id: 'n' + i, kind: kinds[i % 4], label: 'Node number ' + i, state: states[i % 5], project: 'p' + (i % 5), weight: 1 + i % 7}));
  const edges = Array.from({length: 300}, (_, i) => ({from: 'n' + (i % 200), to: 'n' + ((i * 7 + 3) % 200), kind: i % 5 ? 'contains' : 'informs'})).filter(e => e.from !== e.to);
  const projects = ['p0', 'p1', 'p2', 'p3', 'p4'].map(id => ({id, label: id}));
  const graph = () => ({nodes: nodes.map(n => ({...n})), edges, projects});
  map.update(graph());
  const time = fn => { const t = performance.now(); fn(); return performance.now() - t; };
  const structural = [], stateOnly = [];
  for (let i = 0; i < 40; i++) { nodes[i].label += '.'; structural.push(time(() => map.update(graph()))); }
  for (let i = 0; i < 60; i++) { nodes[i].state = states[(states.indexOf(nodes[i].state) + 1) % 5]; stateOnly.push(time(() => map.update(graph()))); }
  const frame = await new Promise(resolve => { const t = performance.now(); requestAnimationFrame(() => resolve(performance.now() - t)); });
  const stat = a => { const s = [...a].sort((x, y) => x - y); return {p50: s[Math.floor(s.length / 2)], p95: s[Math.floor(s.length * .95)], max: s.at(-1)}; };
  const out = {structural: stat(structural), stateOnly: stat(stateOnly), frame, labels: el.querySelectorAll('.am-label').length, nodes: el.querySelectorAll('.am-star').length};
  map.destroy(); el.remove();
  return out;
}"""


def main():
    with sync_playwright() as p:
        br = p.chromium.launch()
        for (w, h) in SIZES:
            phone = w < 480
            for theme in THEMES:
                tag = f'{w}x{h} {theme}'
                pg, errors = open_page(br, w, h)
                pg.evaluate("t => window.map.setTheme(t)", theme)
                pg.wait_for_timeout(250)
                geometry_checks(pg, tag, phone)
                motion_checks(pg, tag, False)
                if theme == 'dark':
                    keyboard_checks(pg, tag)
                    click_every_node(pg, tag)
                    view_checks(pg, tag, w, h)
                pg.screenshot(path=os.path.join(OUT, f'{w}x{h}@1-{theme}.png'))
                check(not errors, f'{tag}: no console errors {errors[:2]}')
                pg.context.close()
            pg, errors = open_page(br, w, h, reduced_motion='reduce')
            motion_checks(pg, f'{w}x{h} reduced', True)
            check(pg.evaluate("document.querySelector('.am-running').textContent") != '', f'{w}x{h} reduced: static running count shown at the core')
            check(pg.evaluate("window.map.pulse('n0->n1:contains')") is False, f'{w}x{h} reduced: pulse is suppressed')
            check(not errors, f'{w}x{h} reduced: no console errors')
            pg.context.close()
            for theme in ['dark', 'light', 'light-high-contrast']:
                pg, errors = open_page(br, w, h, dpr=2)
                pg.evaluate("t => window.map.setTheme(t)", theme)
                pg.wait_for_timeout(250)
                g = pg.evaluate(GEOM)
                f = os.path.join(OUT, f'{w}x{h}@2-{theme}.png')
                pg.screenshot(path=f)
                png = open(f, 'rb').read(24)
                pw, ph = int.from_bytes(png[16:20], 'big'), int.from_bytes(png[20:24], 'big')
                check(g['dpr'] == 2 and g['raster'] == 0 and (pw, ph) == (w * 2, h * 2), f'{w}x{h}@2 {theme}: DPR 2 vector only, capture {pw}x{ph}')
                check(not errors, f'{w}x{h}@2 {theme}: no console errors')
                pg.context.close()
        pg, errors = open_page(br, 1440, 900, forced_colors='active')
        g = pg.evaluate(GEOM)
        check(len(g['labels']) > 5 and g['raster'] == 0, 'forced-colors 1440x900: labels drawn, no raster')
        pg.screenshot(path=os.path.join(OUT, '1440x900@1-forced-colors.png'))
        check(not errors, 'forced-colors: no console errors')
        pg.context.close()
        pg, errors = open_page(br, 1440, 900)
        pg.wait_for_timeout(600)
        pg.evaluate("window.map.pulse('n0->n1:contains')")
        pg.wait_for_timeout(150)
        running = pg.evaluate("document.getAnimations().filter(a => a.playState === 'running').length")
        check(running == 2, f'pulse: one finite marker joins the breath while it travels ({running} running)')
        pg.wait_for_timeout(900)
        check(pg.evaluate("document.getAnimations().filter(a => a.playState === 'running').length") == 1 and pg.evaluate("document.querySelectorAll('.am-marker').length") == 0, 'pulse: marker removed, only the breath remains')
        pg.evaluate("document.querySelector('#add').click()")
        pg.wait_for_timeout(500)
        check(pg.evaluate("document.querySelectorAll('.am-star').length") == 26 and pg.evaluate("document.getAnimations().filter(a => a.playState === 'running').length") == 1, 'add node: 26 stars, arrival effects finish, one animation left')
        check(not errors, 'pulse/add: no console errors')
        perf = pg.evaluate(PERF)
        print('perf', perf, flush=True)
        check(perf['nodes'] == 200, 'perf: 200 nodes drawn')
        check(perf['structural']['p95'] < 16, f'perf: structural update of 200 nodes p95 {perf["structural"]["p95"]:.1f} ms (p50 {perf["structural"]["p50"]:.1f}, max {perf["structural"]["max"]:.1f}) < 16 ms')
        check(perf['stateOnly']['p95'] < 16, f'perf: state update of 200 nodes p95 {perf["stateOnly"]["p95"]:.1f} ms (p50 {perf["stateOnly"]["p50"]:.1f}, max {perf["stateOnly"]["max"]:.1f}) < 16 ms')
        pg.context.close()
        br.close()
    print(f'\n{len(failures)} defects')
    for f in failures:
        print('  - ' + f)
    sys.exit(1 if failures else 0)


main()
