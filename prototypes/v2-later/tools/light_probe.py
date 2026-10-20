"""LE-3 probe: the day's light. Provenance (nothing drawn without a record), idleness, cost,
what each representation answers without interaction, density, accessibility, and captures.
Prototype tooling.   py prototypes/v2-later/tools/light_probe.py
"""
import json
import os

from serve import results, serve
from playwright.sync_api import sync_playwright
from ia_probe import AXE

PROV_JS = r'''() => {
  const ev = new Map(window.FX.events.map(e => [e.seq, e]));
  const ids = new Set(window.__rec.map(r => r.id));
  const drawn = [...document.querySelectorAll('.daylight line, .daylight path, .daylight circle, .daylight rect, .daylight text, .daylight li, .daylight section')];
  const bad = [];
  for (const e of drawn) {
    const s = e.dataset.src || (e.closest('[data-src]') || {}).dataset?.src;
    if (!s) { bad.push(e.outerHTML.slice(0, 80)); continue; }
    for (const part of s.split(' ')) {
      const [k, v] = part.split(':');
      if (k === 'mission' && !ids.has(v)) bad.push('unknown mission ' + v);
      if (k === 'seq' && v.split(',').some(n => !ev.has(+n) && +n < 900)) bad.push('unknown seq ' + v);
    }
  }
  return { drawn: drawn.length, without_record: bad.length, examples: bad.slice(0, 3) };
}'''
FACTS_JS = r'''() => {
  const text = document.querySelector('main').innerText;
  const P = Object.values(window.FX.projects).map(p => p.name);
  const rec = window.__rec;
  const titles = rec.map(r => (window.FX.missions.find(m => m.id === r.id) || {}).title).filter(Boolean);
  const vis = (s) => text.includes(s);
  const hasSvg = !!document.querySelector('.daylight svg, svg.daylight');
  return {
    projects_named: P.filter(vis).length, missions_named: titles.filter(vis).length, missions: rec.length,
    outcome_by_shape: !!document.querySelector('.daylight .e, .daylight .figslot'),
    outcome_in_words: /verified|failed|blocked|running|waiting/.test(text.split('\n').slice(2).join(' ')),
    when: hasSvg || /\d\d:\d\d–\d\d:\d\d/.test(text), files_changed: /files/.test(text),
    words: (text.match(/\S+/g) || []).length, height: document.documentElement.scrollHeight,
  };
}'''
OVERLAP_JS = r'''() => { const e = [...document.querySelectorAll('svg.lanes .e')].map(x => [x.closest('a').getAttribute('href'), x.getBoundingClientRect()]);
  let n = 0; for (let i = 0; i < e.length; i++) for (let j = i + 1; j < e.length; j++) { const a = e[i][1], b = e[j][1];
    if (e[i][0] !== e[j][0] && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom) n++; } return n; }'''
IDLE_JS = r'''() => new Promise(res => { const raf = window.requestAnimationFrame; let n = 0;
  window.requestAnimationFrame = cb => { n++; return raf(cb); }; setTimeout(() => { window.requestAnimationFrame = raf;
  res({ raf: n, animations: document.getAnimations().length, timers_hint: 'static render' }); }, 1500); })'''


def main():
    base, srv = serve()
    R = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for dev, (w, h) in {'desk': (1440, 900), 'phone': (390, 844)}.items():
            ph = w < 600
            for env in ('dark', 'light', 'hc', 'forced', 'text200'):
                extra = {'color_scheme': 'light' if env == 'light' else 'dark'}
                if env == 'forced':
                    extra['forced_colors'] = 'active'
                if env == 'hc':
                    extra['contrast'] = 'more'
                c = b.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2 if ph else 1, is_mobile=ph, has_touch=ph, **extra)
                pg = c.new_page()
                q = {'light': '&theme=light', 'hc': '&contrast=high', 'text200': '&text=200'}.get(env, '')
                for r in ('quiet', 'lanes', 'ledger', 'hybrid'):
                    for day in ('', '&day=yesterday', '&corpus=heavy'):
                        if env != 'dark' and day:
                            continue
                        key = '%s/%s/%s%s' % (dev, env, r, day.replace('&day=', '/').replace('&corpus=', '/'))
                        pg.goto('%slight.html?r=%s%s%s' % (base, r, day, q))
                        pg.wait_for_timeout(200)
                        d = {'render_ms': pg.evaluate('window.__render_ms'), 'provenance': pg.evaluate(PROV_JS), 'facts': pg.evaluate(FACTS_JS)}
                        d['hscroll'] = pg.evaluate('document.documentElement.scrollWidth > innerWidth + 1')
                        if r == 'lanes':
                            d['end_mark_overlaps'] = pg.evaluate(OVERLAP_JS)
                        if env == 'dark' and not day:
                            d['idle'] = pg.evaluate(IDLE_JS)
                            pg.add_script_tag(path=AXE)
                            d['axe'] = pg.evaluate("() => axe.run(document, {runOnly: ['wcag2a','wcag2aa','wcag21aa','wcag22aa']}).then(r => r.violations.map(v => [v.id, v.nodes.length]))")
                        if env == 'forced' or env == 'hc':
                            pg.add_script_tag(path=AXE)
                            d['axe'] = pg.evaluate("() => axe.run(document, {runOnly: ['wcag2a','wcag2aa']}).then(r => r.violations.map(v => [v.id, v.nodes.length]))")
                        pg.screenshot(path=results('le3', 'shots', key.replace('/', '_') + '.png'), full_page=True)
                        R[key] = d
                        print(key, d['provenance']['without_record'], d['facts']['words'], flush=True)
                c.close()
        b.close()
    dst = results('le3', 'probe.json')
    json.dump(R, open(dst, 'w', encoding='utf-8'), indent=1)
    print(dst)


if __name__ == '__main__':
    main()
