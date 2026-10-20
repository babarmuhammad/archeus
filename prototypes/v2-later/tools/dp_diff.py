"""LE-8: what the design pass changed on every LE-1/LE-3 measure. Compares the pre-pass probe
results (probe_pre_dp.json) with the current ones. Prototype tooling.   py dp_diff.py
"""
import json

from serve import results

ld = lambda *p: json.load(open(results(*p), encoding='utf-8'))  # noqa: E731
A1, B1 = ld('le1', 'probe_pre_dp.json'), ld('le1', 'probe.json')
A3, B3 = ld('le3', 'probe_pre_dp.json'), ld('le3', 'probe.json')
out = {'questions': {}, 'screens': {}, 'axe': {}, 'text200': {}, 'phone_flows': {}, 'light': {}}
for k in B1['questions']:
    for q, b in B1['questions'][k].items():
        a = A1['questions'][k][q]
        d = {f: (a[f], b[f]) for f in ('steps', 'scroll', 'words') if a[f] != b[f]}
        if d:
            out['questions']['%s %s' % (k, q)] = d
for k in B1['screens']:
    for r, b in B1['screens'][k].items():
        a = A1['screens'][k][r]
        d = {f: (a[f], b[f]) for f in b if a.get(f) != b[f]}
        if d:
            out['screens']['%s %s' % (k, r)] = d
viol = lambda R: {k: sum(len(x['axe']) + len(x['contrast_below_floor']) for x in v.values()) for k, v in R['axe'].items()}  # noqa: E731
out['axe'] = {'before': sum(viol(A1).values()), 'after': sum(viol(B1).values()), 'after_by_run': {k: n for k, n in viol(B1).items() if n}}
out['text200'] = {k: {r: (A1['text200'][k][r], x) for r, x in v.items() if A1['text200'][k][r] != x} for k, v in B1['text200'].items()}
out['phone_flows'] = {k: (A1['phone_flows'][k], v) for k, v in B1['phone_flows'].items() if A1['phone_flows'][k] != v}
out['light'] = {'keys_changed': [k for k in B3 if json.dumps(A3.get(k), sort_keys=True) != json.dumps(B3[k], sort_keys=True)]}
json.dump(out, open(results('le8', 'dp_diff.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print(json.dumps(out, indent=1, ensure_ascii=False))
