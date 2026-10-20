"""LV2-1 W1/W3: what each row-context arm costs, and whether it lets similar missions be told apart.

For ctxrow = p | pb | prb | pbc, on Now and Missions, desktop 1,440, phone 390 and small phone
360, at 100 % and 200 % text, busy and stress corpora:
  - row height (mean / max), rows whose context line wraps, characters per row, page height;
  - field presence: on how many rows each field could be shown (a field V1 does not record, or
    cannot derive for this mission, is left off the row, never filled in);
  - separability: among missions with the SAME title (the stress corpus has three), are their
    visible rows distinct, and does the row carry the branch / the repository that tells them apart.
A structural proxy for the context study, not the human result (H-1's context sub-test is).
Prototype tooling.   py prototypes/v2-later/tools/density_probe.py
"""
import json

from playwright.sync_api import sync_playwright

from serve import results, serve

ARMS = ('p', 'pb', 'prb', 'pbc')
DEV = {'desk': (1440, 900), 'phone': (390, 844), 'small': (360, 740)}
JS = r'''() => {
  const rows = [...document.querySelectorAll('.b-row')].filter(r => r.checkVisibility());
  const lh = (e) => parseFloat(getComputedStyle(e).lineHeight) || 16;
  const R = rows.map(r => { const c = r.querySelector('.ctxl:last-of-type'); const t = r.querySelector('.b-main strong');
    return { id: r.dataset.id, title: t ? t.textContent.trim() : '', h: Math.round(r.getBoundingClientRect().height),
      ctx_lines: c ? Math.round(c.getBoundingClientRect().height / lh(c)) : 0, chars: r.innerText.replace(/\s+/g, ' ').trim().length,
      text: r.innerText.replace(/\s+/g, ' ').trim(), branch: !!r.querySelector('[data-ctx="branch"]'), repo: !!r.querySelector('[data-ctx="repo"]'), head: !!r.querySelector('[data-ctx="head"]'),
      overflow: r.scrollWidth > r.clientWidth + 1 }; });
  return { rows: R, height: document.documentElement.scrollHeight, hscroll: document.documentElement.scrollWidth > innerWidth + 1 };
}'''


def main():
    base, srv = serve()
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for dev, (w, h) in DEV.items():
            ph = w < 600
            c = b.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2 if ph else 1, is_mobile=ph, has_touch=ph)
            pg = c.new_page()
            for corpus in ('', 'stress'):
                for text in ('', '200'):
                    for arm in ARMS:
                        for route in ('now', 'missions'):
                            pg.goto('%sia.html?v=b&ctxrow=%s%s%s#%s' % (base, arm, '&corpus=' + corpus if corpus else '', '&text=' + text if text else '', route))
                            pg.wait_for_timeout(150)
                            m = pg.evaluate(JS)
                            rows = m['rows']
                            same = {}
                            for r in rows:
                                same.setdefault(r['title'], []).append(r)
                            groups = [g for g in same.values() if len({x['id'] for x in g}) > 1]
                            sep = [{'title': g[0]['title'], 'n': len({x['id'] for x in g}), 'rows_distinct': len({x['text'] for x in g}) == len(g),
                                    'branch_on_every_row': all(x['branch'] for x in g), 'repo_on_every_row': all(x['repo'] for x in g)} for g in groups]
                            hs = [r['h'] for r in rows]
                            out['%s/%s/%s/%s/%s' % (dev, corpus or 'busy', text or '100', arm, route)] = {
                                'rows': len(rows), 'row_h_mean': round(sum(hs) / len(hs), 1) if hs else None, 'row_h_max': max(hs) if hs else None,
                                'ctx_wraps': sum(r['ctx_lines'] > 1 for r in rows), 'chars_mean': round(sum(r['chars'] for r in rows) / len(rows), 1) if rows else None,
                                'with_branch': sum(r['branch'] for r in rows), 'with_repo': sum(r['repo'] for r in rows), 'with_commit': sum(r['head'] for r in rows),
                                'overflow': sum(r['overflow'] for r in rows), 'page_h': m['height'], 'hscroll': m['hscroll'], 'look_alikes': sep}
            c.close()
        b.close()
    srv.shutdown()
    json.dump(out, open(results('lv21', 'density.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('%-34s %4s %6s %5s %5s %5s %5s %5s %6s %s' % ('dev/corpus/text/arm/route', 'rows', 'h_avg', 'h_max', 'wrap', 'chars', 'page', 'hsc', 'over', 'look-alikes distinct / branch / repo'))
    for k, v in out.items():
        la = ' '.join('%s:%s/%s/%s' % (s['n'], 'Y' if s['rows_distinct'] else 'N', 'Y' if s['branch_on_every_row'] else 'N', 'Y' if s['repo_on_every_row'] else 'N') for s in v['look_alikes'])
        print('%-34s %4d %6s %5s %5d %5s %5d %5s %6d %s' % (k, v['rows'], v['row_h_mean'], v['row_h_max'], v['ctx_wraps'], v['chars_mean'], v['page_h'], v['hscroll'], v['overflow'], la))


if __name__ == '__main__':
    main()
