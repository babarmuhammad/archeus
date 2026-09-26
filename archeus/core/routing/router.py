"""The resource router (resource-router §5, ADR-0005; p10-design-gate §6).

Pure and deterministic: `route(req, snap)` reads nothing but its two
arguments, both plain JSON, so the same inputs give the same decision and a
recorded decision replays from its own `requirements` and `input_snapshot`.
It answers WHERE an authorised subject runs — never whether it may (P9) and
never runs it (P11). It creates no approval: `ask` is an answer, and the
command that recorded it asks P9's approval machinery.

    candidates  every (harness, account) in the snapshot, sorted by id; a
                harness with no registered account offers its own (`account`
                None, `account_ref` the adapter's), one with none offers nothing
    eliminate   STEPS in order; a candidate stops at the first it fails
    order       affinity, preference, priority, tier fit, not near its
                ceiling, id (§5 ordering; cost and latency: no V1 adapter
                reports them, so they are not keys)
    fallback    nothing survived: a candidate stopped only by its ceiling (or
                a DEGRADED account) may run if its account says `fallback:
                allow` or the user approved it; `ask` asks; else blocked (§7)

`req` (the requirements, recorded as the decision's `requirements`):
    subject      archeus_call | task
    purpose      own-call purpose (archeus_call)
    capabilities harness capabilities needed (a task's `capabilities_required`)
    structured_output  True: a schema is asked; native OR prompted satisfies it
    min_model_tier / min_context_window   None: no minimum
    models       {harness_id: model}: the preferred model, in THAT harness's
                 vocabulary; `model_required` makes it a constraint
    effort / effort_required
    preferred / forbidden / required     {harnesses: [], accounts: []}
    project_id, size (S | M | L: the projected bump), policy (task: the P9
    decision's id, outcome and per-item decision and boundary)

`snap` (the decision's `input_snapshot`): harnesses [{id, installed,
capabilities, enforcement, structured_output, efforts, models [{id, tier,
context_window}], exempt}], accounts [{id, ref, harness, label, auth_kind,
registered, health, why_not, policy, usage {windows {5h: pct}, resets_at,
age_s}, ledger {tokens_today, cost_today, running}}], terms {harness:
{headless, rotation}}, affinity {harness, account}, approved_fallbacks [key].
"""

TIERS = ('small', 'mid', 'large')
STEPS = ('installed', 'headless', 'capability', 'model', 'enforcement', 'provider_terms',
         'restriction', 'health', 'allocation', 'election')
#: health states the router may use (state-machines §9); DEGRADED only by fallback
ROUTABLE = ('AVAILABLE', 'CONSTRAINED')
#: the conservative bump a task adds before it starts, by size (resource-router §4)
PROJECTED = {'S': 1, 'M': 3, 'L': 8}
STALE_S, STALE_PENALTY = 120, 5
#: `near_ceiling` is `ceiling - 5` (state-machines §9)
NEAR = 5
#: sandbox-expressible boundary keys (resource-router §3; p9-design-gate §14.1)
SANDBOX_KEYS = ('paths',)
_LAST = 10 ** 9                     # the priority of a harness's own account: after every
                                    # registered one, which has a policy that says where


def size_of(estimate):
    """A task's size band from its 1-5 estimate: 1 S, 2-3 M, 4-5 L."""
    return 'S' if estimate <= 1 else 'M' if estimate <= 3 else 'L'


def ceiling(policy, subject):
    """How high the observed window may be when work starts (resource-router §4):
    `allocation - reserve`, less the brain reserve for everything but own calls."""
    eff = policy['allocation_pct'] - policy['reserve_pct']
    return eff if subject == 'archeus_call' else eff - policy['brain_reserve_pct']


def worst(usage, penalty=True):
    """The fullest window, plus the stale penalty when the reading is old;
    None when no window is known (unknown is never 0)."""
    windows = (usage or {}).get('windows') or {}
    if not windows:
        return None
    w = max(windows.values())
    if penalty and (usage.get('age_s') or 0) > STALE_S:
        w += STALE_PENALTY
    return w


def _rank(tier):
    """An unknown tier counts as the smallest (ADR-0022)."""
    return TIERS.index(tier) if tier in TIERS else 0


def _ids(d, k):
    return set((d or {}).get(k) or ())


def _key(c):
    return c['account'] or c['account_ref'] or c['harness']


def candidates(snap):
    by_harness = {}
    for a in snap.get('accounts') or ():
        by_harness.setdefault(a['harness'], []).append(a)
    out = []
    for h in sorted(snap.get('harnesses') or (), key=lambda h: h['id']):
        accts = sorted(by_harness.get(h['id']) or [None],
                       key=lambda a: '' if a is None else (a['id'] or a['ref'] or ''))
        for a in accts:
            a = a or {}
            out.append({'harness': h['id'], 'account': a.get('id'), 'account_ref': a.get('ref'),
                        'label': a.get('label') or h['id'],
                        'resource': a.get('id') or h['id'], '_h': h, '_a': a,
                        'model': None, 'effort': None,
                        'structured_output': h.get('structured_output'),
                        'fallback': (a.get('policy') or {}).get('fallback'),
                        'priority': (a.get('policy') or {}).get('priority', _LAST),
                        'usage': None, 'ceiling': None, 'constrained': False,
                        'fallbackable': False, 'eliminated_at_step': None, 'reason': None})
    return out


# ── the elimination steps: each returns a reason, or None to keep ──────────

def _installed(c, req, snap):
    if not c['_h'].get('installed'):
        return 'not installed'
    return None


def _headless(c, req, snap):
    if req['subject'] == 'archeus_call' and 'headless' not in c['_h']['capabilities']:
        return 'does not declare headless (it cannot make a tool-less call)'
    return None


def _capability(c, req, snap):
    h = c['_h']
    missing = sorted(set(req.get('capabilities') or ()) - set(h['capabilities']))
    if missing:
        return 'lacks %s' % ', '.join(missing)
    if req.get('structured_output') and h.get('structured_output') not in ('native', 'prompted'):
        return 'has no structured-output mechanism (neither native nor prompted)'
    return None


def _model(c, req, snap):
    h = c['_h']
    offers = {m['id']: m for m in h.get('models') or ()}
    need, ctx = req.get('min_model_tier'), req.get('min_context_window')

    def fits(m):
        return (_rank(m.get('tier')) >= _rank(need)
                and (not ctx or (m.get('context_window') or 0) >= ctx))
    want = (req.get('models') or {}).get(h['id'])
    if want and want in offers and fits(offers[want]):
        c['model'] = want
    elif want and req.get('model_required'):
        return 'model %s is not an offer of this account that meets the requirement' % want
    elif need or ctx:
        # smallest tier first; within a tier the adapter's own order (it lists
        # its offers cheapest first), which a stable sort keeps
        ok = sorted((m for m in offers.values() if fits(m)), key=lambda m: _rank(m.get('tier')))
        if not ok:
            return 'offers no model of tier %s%s' % (
                need or 'any', ' with a %d-token context' % ctx if ctx else '')
        c['model'] = ok[0]['id']
    effort = req.get('effort')
    if effort and effort in (h.get('efforts') or ()):
        c['effort'] = effort
    elif effort and req.get('effort_required'):
        return 'does not accept effort %s' % effort
    return None


def _enforcement(c, req, snap):
    if req['subject'] != 'task':
        return None             # an own call is read-only by construction (ADR-0022)
    items = (req.get('policy') or {}).get('items') or ()
    mode = c['_h'].get('enforcement')
    if mode == 'hook':
        return None
    for i in items:
        d = i['decision']
        if d == 'ALLOW':
            continue
        if mode == 'sandbox' and d == 'ALLOW_WITHIN_BOUNDARY' and all(
                set(b) <= set(SANDBOX_KEYS)
                for b in (i['boundary'] if isinstance(i['boundary'], list) else [i['boundary']])
                if b):
            continue
        return 'cannot enforce %s %s (enforcement: %s)' % (d, i['class'], mode)
    return None


def _terms(c, req, snap):
    h, a = c['_h'], c['_a']
    if h.get('exempt'):
        return None
    t = (snap.get('terms') or {}).get(h['id']) or {}
    if t.get('headless', 'unknown') != 'permitted':
        return ('provider terms %s (ADR-0021): no real call until you permit automated '
                'headless use' % t.get('headless', 'unknown'))
    if a.get('registered') and a.get('auth_kind') == 'subscription_oauth' \
            and t.get('rotation', 'unknown') != 'permitted':
        subs = [x for x in snap.get('accounts') or ()
                if x['harness'] == h['id'] and x.get('registered')
                and x.get('auth_kind') == 'subscription_oauth']
        first = min(subs, key=lambda x: ((x.get('policy') or {}).get('priority', _LAST), x['id']))
        if first['id'] != a['id']:
            return ('rotation across %s subscriptions is not permitted (ADR-0021): only %s '
                    'is used' % (h['id'], first['id']))
    return None


def _restriction(c, req, snap):
    for kind, what in (('required', 'is not the one you required'),
                       ('forbidden', 'is forbidden for this work')):
        hs, accs = _ids(req.get(kind), 'harnesses'), _ids(req.get(kind), 'accounts')
        hit_h, hit_a = c['harness'] in hs, c['account'] in accs
        if kind == 'required' and ((hs and not hit_h) or (accs and not hit_a)):
            return what
        if kind == 'forbidden' and (hit_h or hit_a):
            return what
    p = c['_a'].get('policy') or {}
    project = req.get('project_id')
    if project in (p.get('project_deny') or ()):
        return 'excluded for project %s by your resource rules' % project
    if p.get('project_allow') and project not in p['project_allow']:
        return 'reserved for other projects by your resource rules'
    return None


def _health(c, req, snap):
    a = c['_a']
    if not a:
        return 'no account to run on'
    if not a.get('registered'):
        return a.get('why_not') or None
    if a['health'] not in ROUTABLE:
        c['fallbackable'] = a['health'] == 'DEGRADED'
        return 'account is %s' % a['health']
    raw = worst(a.get('usage'), penalty=False)
    if raw is not None and raw >= 100:
        return 'a usage window is exhausted (%g%%)' % raw
    return None


def _allocation(c, req, snap):
    a = c['_a']
    if not a.get('registered'):
        return None             # no ResourcePolicy: its harness governs its own account
    p, usage = a['policy'], a.get('usage')
    c['ceiling'] = cap = ceiling(p, req['subject'])
    w = worst(usage)
    if w is not None:
        c['usage'] = w
        bump = PROJECTED.get(req.get('size'), 0)
        c['constrained'] = w >= cap - NEAR
        if w + bump < cap:
            return None
        c['fallbackable'] = True
        return '%s at %g%%%s is not under its %g%% ceiling for %s' % (
            'usage' if not usage.get('age_s') or usage['age_s'] <= STALE_S
            else 'stale usage (+%d)' % STALE_PENALTY, w,
            ' (+%d projected)' % bump if bump else '', cap,
            'own calls' if req['subject'] == 'archeus_call' else 'tasks')
    budgets, led = p.get('budgets') or {}, a.get('ledger') or {}
    c['fallbackable'] = True
    if not budgets:
        return 'no readable usage window and no budget: used only as a fallback'
    over = [k for k, have in (('tokens_per_day', led.get('tokens_today', 0)),
                              ('cost_per_day', led.get('cost_today', 0)),
                              ('concurrency', led.get('running', 0)))
            if k in budgets and have >= budgets[k]]
    if over:
        return 'budget reached: %s' % ', '.join(over)
    c['fallbackable'] = False
    return None


_STEP = {'installed': _installed, 'headless': _headless, 'capability': _capability,
         'model': _model, 'enforcement': _enforcement, 'provider_terms': _terms,
         'restriction': _restriction, 'health': _health, 'allocation': _allocation}


def order_key(c, req, snap):
    """The ordering (resource-router §5), smallest first."""
    aff = snap.get('affinity') or {}
    affine = bool(aff) and (c['harness'], _key(c)) == (aff.get('harness'), aff.get('account'))
    pref = (c['account'] in _ids(req.get('preferred'), 'accounts')
            or c['harness'] in _ids(req.get('preferred'), 'harnesses'))
    tier = next((m.get('tier') for m in c['_h'].get('models') or ()
                 if m['id'] == c['model']), None)
    return (0 if affine else 1, 0 if pref else 1, c['priority'],
            _rank(tier) if c['model'] else 0, 1 if c['constrained'] else 0, c['resource'])


_WHY = ('this mission was already running there', 'it is your preferred choice',
        None, 'it has the smallest model that meets the tier', 'it is not near its ceiling',
        'it comes first by id among equals')


def _why(win, rest, req, snap):
    if win['account'] is not None:
        head = 'it is your priority-%d account' % win['priority']
    else:
        head = "it is %s's own account" % win['harness']
    if rest:
        k, o = order_key(win, req, snap), order_key(rest[0], req, snap)
        i = next(i for i in range(len(k)) if k[i] != o[i])
        if _WHY[i]:
            return '%s, and %s' % (head, _WHY[i])
    return head


def route(req, snap):
    """The decision for *req* on *snap* (both JSON): a dict with `result`
    (selected | fallback | ask | blocked), the chosen resource and every
    candidate with the step that stopped it."""
    cands = candidates(snap)
    live = list(cands)
    for step in STEPS[:-1]:
        keep = []
        for c in live:
            why = _STEP[step](c, req, snap)
            if why is None:
                keep.append(c)
            else:
                c['eliminated_at_step'], c['reason'] = step, why
        live = keep
    ordered = sorted(live, key=lambda c: order_key(c, req, snap))
    result, win, why = 'selected', None, None
    if ordered:
        win = ordered[0]
        why = _why(win, ordered[1:], req, snap)
        for c in ordered[1:]:
            c['eliminated_at_step'], c['reason'] = 'election', 'ranked below %s' % win['resource']
    else:
        fb = sorted((c for c in cands if c['fallbackable']), key=lambda c: order_key(c, req, snap))
        approved = set(snap.get('approved_fallbacks') or ())
        pick = (next((c for c in fb if _key(c) in approved), None)
                or next((c for c in fb if c['fallback'] == 'allow'), None))
        if pick is not None:
            result, win = 'fallback', pick
            why = ('you approved running it there' if _key(pick) in approved
                   else 'its policy allows fallback') + ' (%s)' % pick['reason']
        else:
            ask = next((c for c in fb if c['fallback'] == 'ask'), None)
            result, win = ('ask', ask) if ask is not None else ('blocked', None)
    resets = sorted(r for c in cands if c['eliminated_at_step'] in ('health', 'allocation')
                    for r in ((c['_a'].get('usage') or {}).get('resets_at') or {}).values() if r)
    public = [{k: v for k, v in c.items() if not k.startswith('_')} for c in cands]
    return {
        'result': result,
        'selected': win['resource'] if win is not None and result != 'ask' else None,
        'harness_id': win and win['harness'], 'account_id': win and win['account'],
        'account_ref': win and win['account_ref'], 'model': win and win['model'],
        'effort': win and win['effort'], 'label': win and win['label'],
        'why': why, 'candidates': public,
        # what it fell back FROM: every candidate stopped only by availability
        'fallback_from': [c['resource'] for c in cands if c is not win
                          and c['eliminated_at_step'] in ('health', 'allocation')]
        if result in ('fallback', 'ask') else [],
        'unblock_at': resets[0] if resets and result == 'blocked' else None}


def explain(d, req):
    """The explanation, generated from the record (resource-router §8)."""
    others = ['%s — %s' % (c['label'], c['reason']) for c in d['candidates']
              if c['reason'] and c['resource'] != (d['account_id'] or d['harness_id'])]
    win = next((c for c in d['candidates'] if c['harness'] == d['harness_id']
                and c['resource'] == (d['account_id'] or d['harness_id'])), None)
    use = ''
    if win is not None and win['usage'] is not None:
        use = ', at %g%% of its window against a %g%% ceiling' % (win['usage'], win['ceiling'])
    what = '%s (%s, %s)' % (d['label'], d['harness_id'], d['model'] or 'its default model') \
        if d['harness_id'] else None
    if d['result'] == 'selected':
        head = 'I used %s because %s%s.' % (what, d['why'], use)
    elif d['result'] == 'fallback':
        head = 'I fell back to %s because nothing preferred could run and %s.' % (what, d['why'])
    elif d['result'] == 'ask':
        head = ('Nothing could run within its limits; %s may be used only if you approve '
                'it.' % what)
    else:
        head = 'Nothing could run this%s.' % (
            ' until %s' % d['unblock_at'] if d['unblock_at'] else '')
    return head + ('' if not others else ' Not used: ' + '; '.join(others) + '.')


def replay(decision):
    """Route a recorded decision again from its own record: equal when nothing
    but the record decided it."""
    return route(decision['requirements'], decision['input_snapshot'])
