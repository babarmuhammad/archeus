"""LE-1 / LE-2 / LE-4 probe: walk the eight questions, measure the screens, run the gates.

Structural proxy for "how quickly can a person answer" — clicks, scroll distance and words read
before the answer — NOT time-on-task. The human 5-second test and the thumb test are owed and
stated as such in the result. Prototype tooling, not product code.

    py prototypes/v2-later/tools/ia_probe.py            -> results/le1/probe.json + shots
"""
import json
import os
import re
import sys

from serve import results, serve
from playwright.sync_api import sync_playwright

# LV2-1 W1: LV21_Q appends a query (an arm, e.g. '&type=le8') to every page; LV21_TAG writes the run
# to results/lv21/ia_<tag>.json (+ shots_<tag>/, env_<tag>/) so LV2-0's and LE8's records stay as they are
EXTRA = os.environ.get('LV21_Q', '')
TAG = os.environ.get('LV21_TAG')


def out(*p):
    if not TAG:
        return results(*p)
    if p == ('le1', 'probe.json'):
        return results('lv21', 'ia_%s.json' % TAG)
    return results('lv21', '%s_%s' % (p[1], TAG), *p[2:])

HERE = os.path.dirname(os.path.abspath(__file__))
AXE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), 'clients', 'app', 'node_modules', 'axe-core', 'axe.min.js')
DEVICES = {'desk': (1440, 900), 'wide': (1920, 1080), 'narrow': (1024, 768), 'phone': (390, 844), 'small': (360, 740)}
QS = ['q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8']
QTEXT = {'q1': 'What is Archeus doing?', 'q2': 'Which mission / project is it for?', 'q3': 'What needs me?', 'q4': 'What happened (today)?',
         'q5': 'What is currently running?', 'q6': 'What changed?', 'q7': 'Why did it happen (the blocked mission)?', 'q8': 'Where is the evidence?'}
MACHINE = [(r'\d{4}-\d\d-\d\dT\d\d:\d\d', 'ISO timestamp'), (r'profile:\w+@\d', 'policy grammar'), (r'\b(ASK|ALLOW|DENY)\b', 'policy enum'),
           (r'\btask:\w+', 'internal target'), (r'\b[A-Z]{3,}_[A-Z_]{3,}\b', 'enum name')]

MEASURE_JS = r'''([q, bottomChrome]) => {
  const els = [...document.querySelectorAll(`[data-q~="${q}"]`)].filter(e => e.checkVisibility());
  if (!els.length) return null;
  const vh = innerHeight - bottomChrome;
  const top = Math.min(...els.map(e => e.getBoundingClientRect().top + scrollY));
  const bottom = Math.max(...els.map(e => e.getBoundingClientRect().bottom + scrollY));
  const scroll = Math.max(0, Math.round(bottom - vh));
  // words a reader passes before the answer, in document order, visible text only
  const first = els[0];
  const w = document.createTreeWalker(document.querySelector('main') || document.body, NodeFilter.SHOW_TEXT);
  let words = 0, n;
  while ((n = w.nextNode())) {
    if (first.contains(n) || (first.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING)) break;
    const p = n.parentElement;
    if (!p || !p.checkVisibility() || p.closest('.sr')) continue;
    words += (n.textContent.match(/\S+/g) || []).length;
  }
  return { top: Math.round(top), bottom: Math.round(bottom), scroll, words };
}'''
# axe missed a 3.07:1 badge in the light theme, so contrast is also computed directly: every visible
# text run against the first opaque background behind it; < 4.5 below 18.66 px bold / 24 px, else < 3
CONTRAST_JS = r'''() => {
  const rgb = s => { const m = s.match(/[\d.]+/g); return m ? m.map(Number) : null; };
  const lum = c => { const v = c.slice(0, 3).map(x => { x /= 255; return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4; }); return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]; };
  const bgOf = e => { for (let n = e; n; n = n.parentElement) { const c = rgb(getComputedStyle(n).backgroundColor); if (c && (c[3] === undefined || c[3] > .95)) return c; } return rgb(getComputedStyle(document.body).backgroundColor); };
  const out = []; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) { const e = n.parentElement; if (!n.textContent.trim() || !e || !e.checkVisibility() || e.closest('.sr, svg')) continue;
    const cs = getComputedStyle(e); if (+cs.opacity < 1) continue; const fg = rgb(cs.color), bg = bgOf(e); if (!fg || !bg) continue;
    const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x); const r = (a + .05) / (b + .05);
    const big = parseFloat(cs.fontSize) >= 24 || (parseFloat(cs.fontSize) >= 18.66 && +cs.fontWeight >= 600);
    if (r < (big ? 3 : 4.5)) out.push([n.textContent.trim().slice(0, 24), +r.toFixed(2)]); }
  return out; }'''
BOTTOM_JS ='''() => { let h = 0; for (const s of ['.b-tabs', '.b-strip', '.a-nav']) { const e = document.querySelector(s);
  if (e && getComputedStyle(e).position === 'fixed') h = Math.max(h, innerHeight - e.getBoundingClientRect().top); } return Math.round(h); }'''


def ctx(b, dev, extra=None):
    w, h = DEVICES[dev]
    ph = w < 600
    o = dict(viewport={'width': w, 'height': h}, device_scale_factor=2 if ph else 1, is_mobile=ph, has_touch=ph, color_scheme='dark')
    o.update(extra or {})
    return b.new_context(**o)


def goto(pg, base, v, route='now', q=''):
    pg.goto('%sia.html?v=%s%s#%s' % (base, v, q, route))
    pg.wait_for_timeout(250)


def questions(b, base, v, dev):
    c = ctx(b, dev)
    pg = c.new_page()
    out = {}
    for q in QS:
        goto(pg, base, v)
        path = pg.evaluate('([v, q]) => window.PATHS[v][q]', [v, q])
        steps, ok = 0, True
        for sel in path or []:
            loc = pg.locator(sel).first
            if not loc.count():
                ok = False
                break
            loc.scroll_into_view_if_needed()
            loc.click()
            steps += 1
            pg.wait_for_timeout(150)
            pg.evaluate('scrollTo(0, 0)')
        m = pg.evaluate(MEASURE_JS, [q, pg.evaluate(BOTTOM_JS)]) if ok else None
        out[q] = dict(steps=steps, **(m or {'unanswerable': True}))
    c.close()
    return out


def screens(b, base, v, dev, corpus=''):
    c = ctx(b, dev)
    pg = c.new_page()
    routes = {'a': ['now', 'attention', 'work'], 'b': ['now', 'needs', 'missions'], 'c': ['now', 'needs', 'missions']}[v]
    first_m = 'm-c3e9' if not corpus else 'd-0'
    routes = routes + (['m/' + first_m] + (['d/m-91d2'] if v != 'a' and not corpus else []))
    out = {}
    for r in routes:
        goto(pg, base, v, r, corpus)
        vh = DEVICES[dev][1]
        d = pg.evaluate('''() => ({ height: document.documentElement.scrollHeight,
          hscroll: document.documentElement.scrollWidth > innerWidth + 1,
          text: (document.querySelector('main') || document.body).innerText })''')
        d['screens'] = round(d['height'] / vh, 2)
        txt = d.pop('text')
        # first two depths: closed <details> and the raw policy record are depth three
        vis = pg.evaluate('''() => { const m = document.querySelector('main') || document.body; const c = m.cloneNode(true);
          c.querySelectorAll('details:not([open]) > :not(summary), .raw, .sr').forEach(e => e.remove()); return c.innerText; }''')
        d['machine'] = sorted({lbl for rx, lbl in MACHINE if re.search(rx, vis)})
        # the same decision offered twice on one screen (rulebook §8)
        d['dup_decisions'] = pg.evaluate('''() => { const seen = {}; let dup = 0;
          document.querySelectorAll('[data-ap], .a-msg, .b-row.decide').forEach(e => { const k = (e.dataset.ap || e.dataset.id || (e.querySelector('.a-ref')||{}).textContent || '').replace('mission ', '');
            const t = e.matches('.a-msg') ? e.querySelector('.a-ref').textContent.replace('mission ','') : (e.dataset.ap ? (document.querySelector(`[data-ap="${e.dataset.ap}"] a`)||{}).textContent : k);
            seen[t] = (seen[t] || 0) + 1; }); return Object.values(seen).filter(n => n > 1).length; }''')
        # e-stop on the first screen, without scrolling
        d['estop_visible'] = pg.evaluate('''() => { const e = document.querySelector('[data-estop], .a-stop'); if (!e || !e.checkVisibility()) return false;
          const r = e.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight && r.width > 0; }''')
        # touch targets
        d['targets_lt44'] = pg.evaluate('''() => [...document.querySelectorAll('a, button, summary, input, textarea, [tabindex="0"]')].filter(e => e.checkVisibility()).filter(e => {
          const r = e.getBoundingClientRect(); if (!r.width) return false; const inline = getComputedStyle(e).display === 'inline' && e.closest('p');
          return !inline && (r.height < 44 || r.width < 44); }).length''')
        d['targets_lt24'] = pg.evaluate('''() => [...document.querySelectorAll('a, button, summary, input, textarea')].filter(e => e.checkVisibility()).filter(e => {
          const r = e.getBoundingClientRect(); return r.width && (r.height < 24 || r.width < 24); }).length''')
        if v == 'a' or dev in ('desk', 'phone'):
            pg.screenshot(path=results('le1', 'shots', '%s_%s_%s%s.png' % (v, dev, r.replace('/', '-'), corpus.replace('&corpus=', '_'))), full_page=(dev in ('phone', 'small') and r == 'now'))
        out[r] = d
    c.close()
    return out


def above_fold(b, base, v):
    c = ctx(b, 'desk')
    pg = c.new_page()
    goto(pg, base, v)
    r = pg.evaluate('''() => { const vh = innerHeight; const vis = e => { const r = e.getBoundingClientRect(); return r.bottom <= vh && r.top >= 0; };
      return { decide: [...document.querySelectorAll('.a-card, .b-row.decide')].filter(vis).length,
               running: [...document.querySelectorAll('[data-q~="q5"] .a-row, .b-row.run')].filter(vis).length }; }''')
    c.close()
    return r


def axe(b, base, v, dev, env):
    extra = {}
    q = ''
    if env == 'light':
        q = '&theme=light'
        extra['color_scheme'] = 'light'
    if env == 'hc':
        q = '&contrast=high'
        extra['contrast'] = 'more'
    if env == 'forced':
        extra['forced_colors'] = 'active'
    c = ctx(b, dev, extra)
    pg = c.new_page()
    out = {}
    for r in (['now', 'm/m-c3e9'] + (['d/m-91d2'] if v != 'a' else ['attention'])):
        goto(pg, base, v, r, q)
        pg.add_script_tag(path=AXE)
        res = pg.evaluate('''() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] }).then(r => r.violations.map(v => [v.id, v.impact, v.nodes.length]))''')
        out[r] = {'axe': res, 'contrast_below_floor': [] if env == 'forced' else pg.evaluate(CONTRAST_JS)}
        if env in ('light', 'hc', 'forced'):
            pg.screenshot(path=results('le1', 'env', '%s_%s_%s_%s.png' % (v, dev, env, r.replace('/', '-'))))
    c.close()
    return out


def text200(b, base, v, dev):
    c = ctx(b, dev)
    pg = c.new_page()
    out = {}
    for r in ['now', 'm/m-c3e9'] + (['d/m-91d2'] if v != 'a' else []):
        goto(pg, base, v, r, '&text=200')
        out[r] = pg.evaluate('''() => ({ hscroll: document.documentElement.scrollWidth > innerWidth + 1,
          clipped_verbs: [...document.querySelectorAll('.b-row strong, .b-decide-bar button, .a-card strong')].filter(e => e.scrollWidth > e.clientWidth + 1).length,
          height: document.documentElement.scrollHeight })''')
        pg.screenshot(path=results('le1', 'env', '%s_%s_text200_%s.png' % (v, dev, r.replace('/', '-'))))
    c.close()
    return out


def phone_flows(b, base):
    """LD-5/LD-7 and rulebook §25: Back never exits, the e-stop is two presses, no modal."""
    c = ctx(b, 'phone')
    pg = c.new_page()
    dialogs = []
    pg.on('dialog', lambda d: (dialogs.append(d.type), d.dismiss()))
    goto(pg, base, 'b')
    pg.locator('.b-row.decide a').first.click()
    pg.wait_for_timeout(150)
    on_page = pg.evaluate('window.__route')
    bar = pg.evaluate('''() => [...document.querySelectorAll('.b-decide-bar button')].map(e => { const r = e.getBoundingClientRect(); return [e.textContent, Math.round(r.height), Math.round(r.width), Math.round(innerHeight - r.bottom)]; })''')
    pg.go_back()
    pg.wait_for_timeout(150)
    back_route = pg.evaluate('window.__route')
    still_app = pg.url.startswith(base)
    es = pg.locator('[data-estop]')
    es.click()
    armed = pg.evaluate('''() => document.querySelector('[data-estop]').dataset.state''')
    pg.wait_for_timeout(3200)
    lapsed = pg.evaluate('''() => document.querySelector('[data-estop]').dataset.state''')
    es.click()
    pg.wait_for_timeout(100)
    es.click()
    engaged = pg.evaluate('''() => [document.querySelector('[data-estop]').dataset.state, window.__estop || 0]''')
    reach = {}
    for r in ['now', 'needs', 'missions', 'm/m-c3e9', 'm/m-4c1e', 'd/m-91d2']:
        goto(pg, base, 'b', r)
        pg.evaluate('scrollTo(0, 1e6)')
        pg.wait_for_timeout(60)
        reach[r] = pg.evaluate('''() => { const e = document.querySelector('[data-estop]'); const r = e.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; }''')
    c.close()
    return dict(decision_route=on_page, decide_bar=bar, back_route=back_route, back_stays_in_app=still_app, estop_first_press=armed,
                estop_after_3s=lapsed, estop_two_presses=engaged, dialogs=dialogs, estop_visible_after_scroll=reach)


def main():
    base, srv = serve()
    R = {'questions': {}, 'screens': {}, 'above_fold_1440': {}, 'axe': {}, 'text200': {}}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for v in 'abc':
            for dev in ('desk', 'wide', 'narrow', 'phone', 'small'):
                if v == 'c' and dev in ('phone', 'small'):
                    continue  # C differs from B only on the desktop
                R['questions']['%s/%s' % (v, dev)] = questions(b, base, v, dev)
                R['screens']['%s/%s' % (v, dev)] = screens(b, base, v, dev)
                print('done', v, dev, flush=True)
            R['above_fold_1440'][v] = above_fold(b, base, v)
        for v in 'ab':
            R['screens']['%s/phone/diag' % v] = screens(b, base, v, 'phone', '&corpus=diag')
            R['screens']['%s/desk/diag' % v] = screens(b, base, v, 'desk', '&corpus=diag')
        for v in 'abc':
            for dev in (('desk', 'wide') if v == 'c' else ('desk', 'phone')):
                for env in ('dark', 'light', 'hc', 'forced'):
                    R['axe']['%s/%s/%s' % (v, dev, env)] = axe(b, base, v, dev, env)
                R['text200']['%s/%s' % (v, dev)] = text200(b, base, v, dev)
        R['phone_flows'] = phone_flows(b, base)
        b.close()
    dst = results('le1', 'probe.json')
    json.dump(R, open(dst, 'w', encoding='utf-8'), indent=1)
    print(dst)


if __name__ == '__main__':
    sys.exit(main())
