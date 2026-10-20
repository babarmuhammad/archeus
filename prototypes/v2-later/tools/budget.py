"""LE-6 budget: what the V1 bundle costs today, what V2-U0 has committed, and what each later-V2
capability would add — priced the way it would ship.

Two prices per part:
  isolated  gzip -9 of the part alone, comments/whitespace crudely stripped (the V2-U0 method)
  marginal  gzip(V1 bundle + part minified by the SPA's own minifiers) - gzip(V1 bundle):
            what the part adds to the file a user downloads. gzip shares a dictionary across
            the whole bundle, so a small part costs less inside it than alone.
Prototype tooling.   py prototypes/v2-later/tools/budget.py
"""
import gzip
import glob
import json
import os
import re
import subprocess

from serve import PROTO, REPO, results

APP = os.path.join(REPO, 'clients', 'app')
STATIC = os.path.join(REPO, 'archeus', 'api', 'static', 'assets')
LAB = os.path.join(PROTO, 'v2-later', 'lab')
U0 = os.path.join(PROTO, 'v2-u0', 'lab')
gz = lambda b: len(gzip.compress(b if isinstance(b, bytes) else b.encode(), 9))  # noqa: E731


def crude(s):
    s = re.sub(r'/\*[\s\S]*?\*/', '', s)
    s = re.sub(r'(?m)^\s*//.*$', '', s)
    return re.sub(r'\s+', ' ', s)


def minify(js='', css=''):
    r = subprocess.run(['node', os.path.join(PROTO, 'v2-later', 'tools', 'minify.mjs')], input=json.dumps({'js': js, 'css': css}),
                       capture_output=True, text=True, encoding='utf-8', cwd=APP, check=True)
    return json.loads(r.stdout)


def fences(path):
    s = open(path, encoding='utf-8').read()
    out = {}
    for m in re.finditer(r'/\*<(\w+)>\*/([\s\S]*?)/\*</\1>\*/', s):
        out[m.group(1)] = out.get(m.group(1), '') + m.group(2)
    return out


V1JS = open(glob.glob(os.path.join(STATIC, 'index-*.js'))[0], 'rb').read()
V1CSS = open(glob.glob(os.path.join(STATIC, 'index-*.css'))[0], 'rb').read()
G_JS, G_CSS = gz(V1JS), gz(V1CSS)


def keep(js):
    # a function nothing calls is deleted by the minifier, which would price a renderer at ~0;
    # publish every declared name so the part survives whole, and subtract that statement's cost
    return sorted(set(re.findall(r'(?:function|const|let)\s+([A-Za-z_$][\w$]*)', js)))


def price(name, js='', css='', iife=True, note=''):
    names = keep(js) if (js and iife) else []
    k = ';window.__k=[%s];' % ','.join(names) if names else ''
    src_js = ('(function(){' + js + k + '})();') if (js and iife) else js
    mn = minify(src_js, css)
    k_cost = 0
    if k:  # the keep statement alone (over dummy bindings), minified, inside the bundle
        dummy = 'let ' + ','.join('%s=Math.random()' % n for n in names) + ';'
        base_min = minify('(function(){' + dummy + 'window.__d=[' + ','.join(names) + '];})();')['js'].encode()
        kmin = minify('(function(){' + dummy + 'window.__d=[' + ','.join(names) + '];' + k + '})();')['js'].encode()
        k_cost = (gz(V1JS + b'\n' + kmin) - gz(V1JS + b'\n' + base_min))
    marg_js = gz(V1JS + b'\n' + mn['js'].encode()) - G_JS - k_cost if js else 0
    marg_css = gz(V1CSS + b'\n' + mn['css'].encode()) - G_CSS if css else 0
    return {'part': name, 'isolated_crude': gz(crude(js + css)) if (js or css) else 0,
            'min_isolated': gz(mn['js'] + mn['css']) if (js or css) else 0,
            'marginal': marg_js + marg_css, 'marginal_js': marg_js, 'marginal_css': marg_css, 'note': note}


def main():
    R = {'baseline': {'v1_js_raw': len(V1JS), 'v1_js_gzip': G_JS, 'v1_css_raw': len(V1CSS), 'v1_css_gzip': G_CSS}}
    # ------------------------------------------------ V2-U0 commitments, re-priced where extractable
    fj, fc = fences(os.path.join(U0, 'figures.js')), fences(os.path.join(U0, 'figures.css')) if '/*<' in open(os.path.join(U0, 'figures.css'), encoding='utf-8').read() else {}
    figcss = open(os.path.join(U0, 'figures.css'), encoding='utf-8').read()
    mo = fences(os.path.join(U0, 'moments.js'))
    gov = open(os.path.join(U0, 'governor.js'), encoding='utf-8').read()
    R['v2u0'] = [
        dict(price('PR-5 C figures + spine (shared+C+CD, figures.css)', fj.get('shared', '') + fj.get('C', '') + fj.get('CD', ''), figcss), recorded=3451),
        dict(price('PR-6 governor (as built, with diagnostic strings)', gov, iife=False), recorded=1470),
        dict(price('PR-6 K-1..K-3 base moments', mo.get('base', ''), open(os.path.join(U0, 'moments.css'), encoding='utf-8').read()), recorded=2130),
        dict(price('PR-4 display type (type.css)', '', open(os.path.join(U0, 'type.css'), encoding='utf-8').read()), recorded=240),
    ]
    R['v2u0_recorded_total'] = {'committed_kb': 9.7, 'items': {'PR-2 spatial': 2.2, 'PR-3 recede': 1.1, 'PR-4 type': 0.24, 'PR-5 figures': 3.5, 'PR-6 base + lean governor': 2.67},
                                'source': 'ARCHEUS_V2_UI_ARCHITECTURE.md §Q; prototypes/v2-u0/results/pr2..pr6.md'}
    # --------------------------------------------------------------------- later-V2 parts
    mj, mc = fences(os.path.join(LAB, 'middle.js')), fences(os.path.join(LAB, 'middle.css'))
    ij, ic = fences(os.path.join(LAB, 'ia.js')), fences(os.path.join(LAB, 'ia.css'))
    lj = fences(os.path.join(LAB, 'light.js'))
    lc = fences(os.path.join(LAB, 'light.html'))
    core = mj['core']
    L = []
    L.append(price('press (CSS)', '', mc['press']))
    L.append(price('hover (CSS)', '', mc['hover']))
    L.append(price('reveal: popover + anchor + @starting-style (CSS only)', '', mc['reveal']))
    L.append(price('summon: palette at 0 ms', '', '', note='no code: a behaviour, not a primitive'))
    L.append(price('motion core (tracked WAAPI, region claim, settle-on-input)', core, '', note='overlaps PR-2 morph engine; counted in full here'))
    L.append(price('flip (shared by disclose and reorder)', mj['flip']))
    L.append(price('disclose / collapse', mj['disclose'], mc['disclose']))
    L.append(price('spring (analytic + linear() settle easing)', mj['spring']))
    L.append(price('reorder (needs flip + spring)', mj['reorder']))
    L.append(price('count (digit roll)', mj['count'], mc['count']))
    L.append(price('release (drag + projected spring, no rAF)', mj['release'], note='needs spring'))
    L.append(price('tooltip group (700 ms → 0 within 300 ms)', mj['tooltip'], mc['tooltip']))
    L.append(price('nav crossfade (peers)', mj['nav']))
    L.append(price('confirm / refuse', mj['confirm'], mc['confirm']))
    L.append(price('push / pop (phone page, history-owned)', mj['push'], mc['push']))
    L.append(price('e-stop two-step (LD-7)', ij['estop'], ic['estop_css']))
    L.append(price('mission context with provenance (LE-2)', ij['context'], ic['context_css'], note='renderer only; Core DR-* are separate'))
    L.append(price('human-language layer (verdict, verbs, consequence, expiry)', ij['language'], note='strings + templates; replaces V1 strings'))
    L.append(price('desktop composition C (panes, CSS)', '', ic['compose_css'], note='gross; replaces V1 .now-grid'))
    L.append(price('phone composition (tabs, strip, decision bar; CSS)', '', ic['phone_css'], note='gross; replaces V1 phone rules'))
    L.append(price("day's light — R1 lanes", lj['shared'] + lj['lanes'] + lj['marks'], lc['lanes_css'] + lc['marks_css']))
    L.append(price("day's light — R2 ledger", lj['shared'] + lj['ledger'], lc['ledger_css'], note='uses PR-5 figures (already committed)'))
    L.append(price("day's light — R3 ledger + traces", lj['shared'] + lj['marks'] + lj['hybrid'], lc['marks_css'] + lc['hybrid_css']))
    L.append(price('disclose via grid-rows (REJECTED, layout animation)', '', mc['disclose_css']))
    pc = fences(os.path.join(LAB, 'polish.css'))
    L.append(price('design pass DP-1..DP-10 (polish.css + typeset)', ij['typeset'], pc['polish_css'], note='presentation only (le8); light.js axis swap not counted'))
    R['later'] = L
    # bundles: what a phase would actually add, priced together (shared dictionary again)
    def bundle(name, parts_js, parts_css):
        return price(name, ''.join(parts_js), ''.join(parts_css))
    R['bundles'] = [
        bundle('LV2-1 free tier: language + context + e-stop + press/hover/reveal', [ij['language'], ij['context'], ij['estop']], [ic['context_css'], ic['estop_css'], mc['press'], mc['hover'], mc['reveal']]),
        bundle('motion middle, full (core+flip+disclose+spring+reorder+count+release+tooltip+nav+confirm+push)',
               [core, mj['flip'], mj['disclose'], mj['spring'], mj['reorder'], mj['count'], mj['release'], mj['tooltip'], mj['nav'], mj['confirm'], mj['push']],
               [mc['press'], mc['hover'], mc['reveal'], mc['tooltip'], mc['disclose'], mc['count'], mc['confirm'], mc['push']]),
        bundle('motion middle, lean (core+flip+disclose+confirm+push; CSS press/hover/reveal)', [core, mj['flip'], mj['disclose'], mj['confirm'], mj['push']],
               [mc['press'], mc['hover'], mc['reveal'], mc['disclose'], mc['confirm'], mc['push']]),
        bundle("day's light R3 (recommended form)", [lj['shared'], lj['marks'], lj['hybrid']], [lc['marks_css'], lc['hybrid_css']]),
        bundle('phone + desktop composition CSS (gross)', [], [ic['compose_css'], ic['phone_css']]),
    ]
    dst = results('le6', 'budget.json')
    json.dump(R, open(dst, 'w', encoding='utf-8'), indent=1)
    for row in R['v2u0'] + R['later'] + R['bundles']:
        print('%-92s iso %5d  min %5d  marginal %5d%s' % (row['part'][:92], row['isolated_crude'], row['min_isolated'], row['marginal'], ('  rec %d' % row['recorded']) if 'recorded' in row else ''))
    print(R['baseline'])


if __name__ == '__main__':
    main()
