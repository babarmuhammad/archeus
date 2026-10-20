"""LV2-1 W1: every IA-probe measure for LV2-0, LE8 and each LV2-1 arm, side by side, with nothing
re-scored. LV2-0 = results/le1/probe_pre_dp.json; LE8 = results/le1/probe_le8.json; LV2-1 arms =
results/lv21/ia_<tag>.json. Writes results/lv21/compare.md.   py lv21_compare.py
Prototype tooling.
"""
import json
import os

from serve import results

RUNS = [('LV2-0', results('le1', 'probe_pre_dp.json')), ('LE8', results('le1', 'probe_le8.json'))] + [
    ('LV2-1 ' + t, results('lv21', 'ia_%s.json' % t)) for t in ('af', 'le8type', 'bar1', 'hdr20', 'namesv1')]
R = [(n, json.load(open(p, encoding='utf-8'))) for n, p in RUNS if os.path.exists(p)]


def g(d, *k):
    for x in k:
        if d is None:
            return None
        d = d.get(x) if isinstance(d, dict) else None
    return d


lines = ['# LV2-1 W1 — IA probe: LV2-0 vs LE8 vs the LV2-1 arms', '',
         'LV2-1 `af` = the corrected lab at its defaults (A §F typography, LE8 presentation, V1-true context). '
         'Other arms change one switch from `af`. Nothing is re-scored; the LV2-0 and LE8 files are as recorded.', '',
         '| Measure | ' + ' | '.join(n for n, _ in R) + ' |', '|---|' + '---|' * len(R)]


def row(label, f):
    lines.append('| %s | %s |' % (label, ' | '.join(str(f(d)) if f(d) is not None else '—' for _, d in R)))


for v, dev in (('b', 'phone'), ('b', 'small'), ('b', 'desk'), ('c', 'desk'), ('a', 'phone')):
    for r in ('now', 'needs', 'missions', 'm/m-c3e9', 'd/m-91d2'):
        row('%s %s height %s (px)' % (v.upper(), dev, r), lambda d, v=v, dev=dev, r=r: g(d, 'screens', '%s/%s' % (v, dev), r, 'height'))
row('B phone Now, the D-1 diagnosis state (px)', lambda d: g(d, 'screens', 'b/phone/diag', 'now', 'height'))
for v, dev in (('b', 'phone'), ('b', 'small'), ('b', 'desk'), ('c', 'desk')):
    for q in ('q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8'):
        row('%s %s %s clicks / scroll / words' % (v.upper(), dev, q), lambda d, v=v, dev=dev, q=q: (lambda x: None if x is None else '%s / %s / %s' % (x.get('steps'), x.get('scroll'), x.get('words')))(g(d, 'questions', '%s/%s' % (v, dev), q)))
row('axe violations + contrast failures, B and C (all runs)', lambda d: sum(len(x['axe']) + len(x['contrast_below_floor']) for k, v in d['axe'].items() if not k.startswith('a/') for x in v.values()))
row('axe violations, A replica (its unlabelled field)', lambda d: sum(len(x['axe']) for k, v in d['axe'].items() if k.startswith('a/') for x in v.values()))
row('machine strings at depth 1–2, B/C screens', lambda d: sum(len(x['machine']) for k, v in d['screens'].items() if not k.startswith('a/') for x in v.values()))
row('duplicate decisions, B/C screens', lambda d: sum(x['dup_decisions'] for k, v in d['screens'].items() if not k.startswith('a/') for x in v.values()))
row('e-stop visible, B/C screens (of all)', lambda d: '%d / %d' % (sum(x['estop_visible'] for k, v in d['screens'].items() if not k.startswith('a/') for x in v.values()), sum(1 for k, v in d['screens'].items() if not k.startswith('a/') for x in v.values())))
row('targets < 44 px, B phone (all screens)', lambda d: sum(x['targets_lt44'] for x in d['screens']['b/phone'].values()))
row('200 % text: horizontal scroll / clipped verbs (B/C)', lambda d: '%d / %d' % (sum(x['hscroll'] for k, v in d['text200'].items() if not k.startswith('a/') for x in v.values()), sum(x['clipped_verbs'] for k, v in d['text200'].items() if not k.startswith('a/') for x in v.values())))
row('phone decision bar (label h×w, gap to edge)', lambda d: '; '.join('%s %s×%s @%s' % tuple(b) for b in d['phone_flows']['decide_bar']))
row('Back stays in app · e-stop arms → lapses → engages · dialogs', lambda d: '%s · %s → %s → %s · %d' % (d['phone_flows']['back_stays_in_app'], d['phone_flows']['estop_first_press'], d['phone_flows']['estop_after_3s'] or "''", d['phone_flows']['estop_two_presses'][0], len(d['phone_flows']['dialogs'])))
row('e-stop visible after scrolling, 6 phone screens', lambda d: sum(d['phone_flows']['estop_visible_after_scroll'].values()))
open(results('lv21', 'compare.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
