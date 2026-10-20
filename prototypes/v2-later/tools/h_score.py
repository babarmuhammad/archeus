"""LV2-1 W2: score the human sessions against the criteria fixed in the LV2-1 gate (§5) BEFORE the
first participant. Every criterion is evaluated per participant and reported per participant; a
miss is a miss (nothing is averaged away). Group rules (naming, header spacing, decision bar,
context fields, "B's median beats A") are computed only from the sessions present and say how many
participants they rest on. With fewer participants than the gate requires, the result is
INCOMPLETE and no criterion is reported as passed.

    py prototypes/v2-later/tools/h_score.py      (reads results/lv21/sessions/lv21-*.json)
Prototype tooling.
"""
import glob
import json
import statistics as st

from serve import results

FIELDS = {'p': 1, 'pb': 2, 'prb': 3, 'pbc': 3}


def load():
    return [json.load(open(f, encoding='utf-8')) for f in sorted(glob.glob(results('lv21', 'sessions', 'x')[:-1] + 'lv21-*.json'))]


def tr(p, part, device, v=None, arm=None):
    return [t for t in p['trials'].values() if t['part'] == part and t['device'] == device and (v is None or t['v'] == v) and (arm is None or t.get('arm') == arm)]


def qs(t, n):
    return [t['q'].get(str(j), {}) for j in range(n)]


def ok(q):
    return q.get('mark') == 'ok'


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def one(lst):
    return lst[0] if lst else None


def participant(p):
    R = {}
    # ---------------- H-1 recall
    for dev in ('desktop', 'phone'):
        b, a = one(tr(p, 'recall', dev, 'b')), one(tr(p, 'recall', dev, 'a'))
        nb = sum(ok(q) for q in qs(b, 6)) if b else None
        na = sum(ok(q) for q in qs(a, 6)) if a else None
        R['H1 recall B >= 5/6 (%s)' % dev] = None if nb is None else nb >= 5
        R['H1 recall B >= A (%s)' % dev] = None if nb is None or na is None else nb >= na
        R['_recall_%s' % dev] = {'B': nb, 'A': na}
    # ---------------- H-1 findability (B)
    for dev, lim in (('desktop', 10), ('phone', 15)):
        b = one(tr(p, 'find', dev, 'b'))
        if not b:
            for k in ('9/9', 'each < 60 s', 'median', '<= 2 wrong-path taps', 'project and branch correct'):
                R['H1 find %s (%s)' % (k, dev)] = None
            continue
        Q = qs(b, 9)
        secs = [q.get('secs') for q in Q]
        R['H1 find 9/9 (%s)' % dev] = all(ok(q) for q in Q)
        R['H1 find each < 60 s (%s)' % dev] = all(s is not None and s < 60 for s in secs)
        m = med(secs)
        R['H1 find median <= %d s (%s)' % (lim, dev)] = None if m is None else m <= lim
        R['H1 find <= 2 wrong-path taps (%s)' % dev] = sum(q.get('wrong', 0) for q in Q) <= 2
        R['H1 find project and branch correct (%s)' % dev] = ok(Q[3]) and ok(Q[4])
        R['_find_%s' % dev] = {'secs': secs, 'median': m, 'wrong': sum(q.get('wrong', 0) for q in Q)}
    inv = [q for t in p['trials'].values() if t['part'] in ('find', 'context') for j, q in t['q'].items() if q.get('mark') == 'inv']
    R['H1 zero invented remotes'] = not inv
    # ---------------- H-2
    for dev in ('desktop', 'phone'):
        new, old = one(tr(p, 'decide', dev, 'c' if dev == 'desktop' else 'b')), one(tr(p, 'decide', dev, 'a'))
        nn = sum(ok(q) for q in qs(new, 7)) if new else None
        no = sum(ok(q) for q in qs(old, 7)) if old else None
        R['H2 lab page >= 6/7 (%s)' % dev] = None if nn is None else nn >= 6
        R['H2 lab page >= V1 card (%s)' % dev] = None if nn is None or no is None else nn >= no
        R['H2 zero invented facts (%s)' % dev] = None if not new else not any(q.get('mark') == 'inv' for q in qs(new, 7))
        R['_h2_%s' % dev] = {'lab': nn, 'v1': no, 'q1_secs': (qs(new, 7)[0].get('secs') if new and ok(qs(new, 7)[0]) else None)}
    # ---------------- H-3
    for dev in ('iphone', 'android'):
        t = one(tr(p, 'phone', dev))
        if not t:
            R['H3 run (%s)' % dev] = None
            continue
        q = t['q']
        g = lambda k, f: q.get(k, {}).get(f)  # noqa: E731
        R['H3 zero Approve/Reject mis-taps (%s)' % dev] = not (g('ap1', 'mistap') or g('ap2', 'mistap'))
        R['H3 armed never described as stopped (%s)' % dev] = not g('t4', 'armed_as_stopped')
        R['H3 zero one-press stops (%s)' % dev] = not g('t4', 'one_press_stop')
        pr, secs = g('t4', 'presses'), g('t4', 'secs')
        R['H3 full stop <= 2 presses and <= 5 s (%s)' % dev] = None if pr in (None, '') or secs is None else int(pr) <= 2 and secs <= 5
        R['H3 Back never exits (%s)' % dev] = bool(g('t5', 'stayed') and g('t6', 'stayed') and not g('t5', 'left') and not g('t6', 'left'))
        ws = g('why', 'secs')
        R['H3 because correct within 20 s (%s)' % dev] = bool(g('why', 'ok')) and ws is not None and ws <= 20
        taps = g('t3', 'taps')
        R['H3 project from the strip within one tap (%s)' % dev] = bool(g('t3', 'project_ok')) and taps not in (None, '') and int(taps) <= 1
        R['H3 no sideways scrolling at 360 px / 200 % (%s)' % dev] = not g('t7', 'sideways')
    return R


def main():
    S = load()
    out = {'participants': {}, 'group': {}, 'status': None}
    prof = [s.get('profile', {}) for s in S]
    mix = {'n': len(S), 'owner': any(p.get('owner') for p in prof), 'new_to_archeus': sum(bool(p.get('new_to_archeus')) for p in prof),
           'daily_agent': sum(bool(p.get('daily_agent')) for p in prof)}
    out['mix'] = mix
    complete = mix['n'] >= 5 and mix['owner'] and mix['new_to_archeus'] >= 2 and mix['daily_agent'] >= 1
    for s in S:
        out['participants'][s['pid']] = participant(s)
    # ---------------- group rules (each says how many sessions it rests on)
    G = out['group']
    for dev in ('desktop', 'phone'):
        wins, n_ = 0, 0
        for j in range(9):
            b = [qs(t, 9)[j].get('secs') for s in S for t in tr(s, 'find', dev, 'b')]
            a = [qs(t, 9)[j].get('secs') for s in S for t in tr(s, 'find', dev, 'a')]
            if med(b) is not None and med(a) is not None:
                n_ += 1
                wins += med(b) < med(a)
        G['H1 B median beats A on >= 7/9 tasks (%s)' % dev] = {'wins': wins, 'tasks_measured': n_, 'pass': (wins >= 7) if n_ == 9 else None}
    q1 = [p['_h2_%s' % d]['q1_secs'] for p in out['participants'].values() for d in ('desktop', 'phone')]
    G['H2 median correct-answer time for #1 <= 15 s'] = {'median': med(q1), 'n': len([x for x in q1 if x is not None]), 'pass': None if med(q1) is None else med(q1) <= 15}

    def errs_time(group, tasks):
        e, ts = 0, []
        for s in group:
            for t in tr(s, 'find', 'desktop', 'b'):
                Q = qs(t, 9)
                e += sum((not ok(Q[j])) + Q[j].get('wrong', 0) for j in tasks)
                ts += [Q[j].get('secs') for j in tasks]
        return e, med(ts)
    for rule, key, a, b, tasks, default in (('names', 'names', 'new', 'v1', (1, 2), 'v1'), ('list-header spacing', 'hdr', '28', '20', (2,), '20')):
        ga, gb = [s for s in S if s.get(key) == a], [s for s in S if s.get(key) == b]
        (ea, ta), (eb, tb) = errs_time(ga, tasks), errs_time(gb, tasks)
        better = bool(ga and gb) and ((eb and ea <= 0.9 * eb) or (ta is not None and tb is not None and ta <= 0.9 * tb))
        G['rule: %s' % rule] = {a: {'n': len(ga), 'errors': ea, 'median_s': ta}, b: {'n': len(gb), 'errors': eb, 'median_s': tb},
                                'keep': (a if better else default) if ga and gb else None}
    two = {'mis': 0, 'hes': 0, 't': []}
    one_ = {'mis': 0, 'hes': 0, 't': []}
    for s in S:
        for t in tr(s, 'phone', 'iphone') + tr(s, 'phone', 'android'):
            for i, k in enumerate(('ap1', 'ap2')):
                arm = (s.get('bar') or ['two', 'one'])[i]
                q = t['q'].get(k, {})
                d = two if arm == 'two' else one_
                d['mis'] += bool(q.get('mistap'))
                d['hes'] += bool(q.get('hesitate'))
                d['t'].append(q.get('secs'))
    keep2 = None
    if two['t'] and one_['t'] and med(two['t']) is not None and med(one_['t']) is not None:
        keep2 = 'two' if (two['mis'] + two['hes'] <= one_['mis'] + one_['hes'] and med(two['t']) <= med(one_['t'])) else 'one'
    G['rule: decision bar'] = {'two': {'mistaps': two['mis'], 'hesitations': two['hes'], 'median_s': med(two['t'])},
                               'one': {'mistaps': one_['mis'], 'hesitations': one_['hes'], 'median_s': med(one_['t'])}, 'keep': keep2}
    ctx = {}
    for arm in FIELDS:
        ts = [t for s in S for t in tr(s, 'context', 'desktop', 'b', arm)]
        n_ = len(ts)
        ctx[arm] = {'n': n_, 'all_correct': (n_ > 0 and all(ok(qs(t, 3)[0]) and ok(qs(t, 3)[1]) for t in ts)) if n_ else None}
    winners = [a for a in FIELDS if ctx[a]['all_correct']]
    # the four arms share the stress corpus, so a participant may learn the look-alikes: each arm is
    # also reported on FIRST exposure only (the arm a participant met first, plan(n) rotation)
    first = {a: [] for a in FIELDS}
    for s in S:
        lead = list(FIELDS)[(s.get('n') or 1) % 4]
        for t in tr(s, 'context', 'desktop', 'b', lead):
            first[lead].append(ok(qs(t, 3)[0]) and ok(qs(t, 3)[1]))
    G['rule: row context'] = {'arms': ctx, 'keep': (min(winners, key=lambda a: FIELDS[a]) if winners else None),
                              'first_exposure': {a: {'n': len(v), 'all_correct': (all(v) if v else None)} for a, v in first.items()}}
    out['status'] = 'COMPLETE' if complete else 'INCOMPLETE — the gate requires >= 5 participants including the owner, >= 2 new to Archeus, >= 1 daily coding-agent user; nothing below is a pass'
    json.dump(out, open(results('lv21', 'human.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(out['status'], json.dumps(mix))
    for pid, R in out['participants'].items():
        miss = [k for k, v in R.items() if not k.startswith('_') and v is False]
        print(pid, 'MISSES:', miss or 'none', '| not run:', [k for k, v in R.items() if not k.startswith('_') and v is None])
    print(json.dumps(G, indent=1))


if __name__ == '__main__':
    main()
