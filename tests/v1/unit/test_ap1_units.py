"""AP-1, the pure half (ADR-0041 §1, §3; ADR-0048; testing-strategy §8: AP-1,
G9, G10, AP-UK, AP-CC): consumption classes partitioned before any ordering
key, the user-device lift, budgets on every account, unknown usage failing
closed, and concurrency over live work — all as a function of the snapshot a
decision records."""

import random

from archeus.core.routing import router as R

from v1.unit.test_routing_units import acct, call, harness, snap, steps, task


def led(tokens=0, cost=0, running=0, tokens_ok=True, cost_ok=True):
    return {'tokens_today': tokens, 'cost_today': cost, 'running': running,
            'complete': {'tokens': tokens_ok, 'cost': cost_ok}}


def ap1(id_, h='h', *, consumption='normal', ledger=None, measures=('tokens',), **kw):
    a = acct(id_, h, consumption=consumption, **kw)
    a['usage_measures'] = list(measures)
    if ledger is not None:
        a['ledger'] = ledger
    return a


def reason(d, resource):
    return next(c['reason'] for c in d['candidates'] if c['resource'] == resource)


# ── the partition (ADR-0041 §1) ─────────────────────────────────────────────

def test_a_last_resort_account_is_never_elected_while_a_normal_one_survives():
    """The AP-1 invariant over generated snapshots: whatever the affinity, the
    preference for the harness or the priorities, a normal survivor wins."""
    rnd = random.Random(48)
    for _ in range(300):
        n = rnd.randint(2, 5)
        accts = [ap1('a%d' % i, priority=rnd.randint(1, 9),
                     consumption=rnd.choice(('normal', 'last_resort')),
                     usage=rnd.choice((None, 10.0, 50.0)),
                     budgets={'tokens_per_day': 1000} if rnd.random() < .3 else {})
                 for i in range(n)]
        aff = rnd.choice([None] + [{'harness': 'h', 'account': a['id']} for a in accts])
        req = rnd.choice((task(), call()))
        req['preferred'] = {'harnesses': ['h'] if rnd.random() < .5 else []}
        d = R.route(req, snap([harness('h')], accts, affinity=aff))
        normals = [c for c in d['candidates'] if c['eliminated_at_step'] in (None, 'election')
                   and dict((a['id'], a['policy']['consumption']) for a in accts)[
                       c['resource']] == 'normal']
        if d['result'] == 'selected' and normals:
            won = next(a for a in accts if a['id'] == d['selected'])
            assert won['policy']['consumption'] == 'normal', (d['selected'], accts, aff)


def test_affinity_to_a_now_protected_account_does_not_keep_the_work_there():
    """Case 9: the mission's previous account became last_resort; affinity is an
    ordering key and the partition comes before ordering."""
    s = snap([harness('h')], [ap1('a', consumption='last_resort'), ap1('b', priority=5)],
             affinity={'harness': 'h', 'account': 'a'})
    d = R.route(task(), s)
    assert (d['result'], d['selected']) == ('selected', 'b')
    assert steps(d)['a'] == 'partition'
    assert reason(d, 'a') == 'a last-resort account, not used while a normal one can run'


def test_with_only_last_resort_left_it_is_a_fallback_under_its_own_mode():
    for mode, result in (('ask', 'ask'), ('allow', 'fallback'), ('deny', 'blocked')):
        s = snap([harness('h')], [ap1('a', consumption='last_resort', fallback=mode)])
        d = R.route(task(), s)
        assert d['result'] == result, mode
        assert reason(d, 'a') == 'a last-resort account, used only as a fallback'
    d = R.route(task(), snap([harness('h')], [ap1('a', consumption='last_resort')],
                             approved_fallbacks=['a']))
    assert (d['result'], d['selected']) == ('fallback', 'a')
    assert 'last-resort' in R.explain(d, task())


def test_a_normal_account_in_fallback_comes_before_a_last_resort_one():
    """The partition holds among fallbacks: a normal account stopped by its
    ceiling is the fallback before a protected one is."""
    s = snap([harness('h')], [ap1('a', consumption='last_resort', fallback='allow'),
                              ap1('b', usage=95.0, fallback='allow', priority=9)])
    d = R.route(task(), s)
    assert (d['result'], d['selected']) == ('fallback', 'b')


def test_explicit_only_is_never_automatic_and_a_user_named_account_lifts_it():
    s = snap([harness('h')], [ap1('c', consumption='explicit_only')])
    d = R.route(task(), s)
    assert d['result'] == 'blocked' and steps(d)['c'] == 'restriction'
    assert reason(d, 'c') == 'used only when you name it (explicit_only)'
    # a mission preference naming it (set only by a user device) lifts it, for that work
    named = R.route(task(preferred={'accounts': ['c']}), s)
    assert (named['result'], named['selected']) == ('selected', 'c')
    # a preference for the harness names no account: no lift
    assert R.route(task(preferred={'harnesses': ['h']}), s)['result'] == 'blocked'
    # an own call names no account, so it never lifts a class
    assert R.route(call(), s)['result'] == 'blocked'


def test_a_named_last_resort_account_is_an_ordinary_candidate_for_that_work():
    s = snap([harness('h')], [ap1('a', consumption='last_resort'), ap1('b', priority=5)])
    d = R.route(task(preferred={'accounts': ['a']}), s)
    assert (d['result'], d['selected']) == ('selected', 'a')


def test_all_protected_is_never_a_silent_fallback():
    """Case 4: nothing normal survives; nothing is elected without its mode."""
    s = snap([harness('h')], [ap1('a', consumption='explicit_only', fallback='allow'),
                              ap1('b', consumption='last_resort')])
    d = R.route(task(), s)
    assert (d['result'], d['selected']) == ('ask', None)
    assert steps(d) == {'a': 'restriction', 'b': 'partition'}


# ── budgets on every account (ADR-0041 §3, G10) ─────────────────────────────

def test_a_budget_on_a_windowed_account_is_enforced():
    s = snap([harness('h')], [ap1('a', usage=10.0, budgets={'tokens_per_day': 100},
                                  ledger=led(tokens=100)),
                              ap1('b', priority=2)])
    d = R.route(task(), s)
    assert d['selected'] == 'b' and steps(d)['a'] == 'allocation'
    assert reason(d, 'a') == 'budget reached: tokens_per_day'
    # none set: behaviour unchanged
    s['accounts'][0]['policy']['budgets'] = {}
    assert R.route(task(), s)['selected'] == 'a'


def test_partly_unreported_usage_makes_a_budget_unevaluable_never_zero():
    """Case 6/7: an incomplete ledger is not "under budget"; a lower bound that
    already reaches the budget is simply reached."""
    unknown = ap1('a', usage=None, budgets={'tokens_per_day': 100},
                  ledger=led(tokens=10, tokens_ok=False))
    d = R.route(task(), snap([harness('h')], [unknown]))
    assert d['result'] == 'ask' and steps(d)['a'] == 'allocation'
    assert reason(d, 'a') == ('budget tokens_per_day cannot be evaluated: usage partly '
                              'unreported')
    reached = ap1('a', usage=None, budgets={'tokens_per_day': 100},
                  ledger=led(tokens=150, tokens_ok=False))
    d = R.route(task(), snap([harness('h')], [reached]))
    assert reason(d, 'a') == 'budget reached: tokens_per_day'


def test_a_budget_on_a_measure_the_account_does_not_report_is_unevaluable():
    a = ap1('a', usage=10.0, budgets={'cost_per_day': 5}, measures=('tokens',),
            ledger=led(cost=0))
    d = R.route(task(), snap([harness('h')], [a]))
    assert reason(d, 'a') == 'budget cost_per_day cannot be evaluated: usage partly unreported'


def test_no_readable_window_and_no_budget_is_fallback_only():
    """Case 8, as built and unchanged."""
    d = R.route(task(), snap([harness('h')], [ap1('a', usage=None)]))
    assert d['result'] == 'ask'
    assert reason(d, 'a') == 'no readable usage window and no budget: used only as a fallback'


# ── concurrency over live work (ADR-0048 D-25.4) ────────────────────────────

def test_a_full_concurrency_budget_refuses_tasks_and_own_calls_alike():
    """Cases 5, 11, 12: `running` counts live executions and own calls in
    flight; at the cap every subject is refused, and another account runs."""
    full = ap1('a', usage=10.0, budgets={'concurrency': 1}, ledger=led(running=1))
    other = ap1('b', priority=2)
    for req in (task(), call()):
        d = R.route(req, snap([harness('h')], [full, other]))
        assert (d['selected'], reason(d, 'a')) == ('b', 'budget reached: concurrency'), req
    d = R.route(call(), snap([harness('h')], [full]))
    assert d['result'] in ('ask', 'blocked') and d['selected'] is None


def test_every_budget_key_has_a_measure_in_the_router():
    from archeus.core.domain import entities
    assert set(R.BUDGET_MEASURES) == set(entities.BUDGET_KEYS)


def test_concurrency_needs_no_reported_measure():
    a = ap1('a', usage=10.0, budgets={'concurrency': 2}, measures=(), ledger=led(running=1,
            tokens_ok=False, cost_ok=False))
    assert R.route(task(), snap([harness('h')], [a]))['selected'] == 'a'


# ── every exclusion has a machine-readable reason ───────────────────────────

def test_every_candidate_that_is_not_elected_has_a_step_and_a_reason():
    rnd = random.Random(7)
    for _ in range(200):
        accts = [ap1('a%d' % i, priority=rnd.randint(1, 5),
                     consumption=rnd.choice(R.STEPS and ('normal', 'last_resort',
                                                         'explicit_only')),
                     usage=rnd.choice((None, 10.0, 99.0)),
                     budgets=rnd.choice(({}, {'concurrency': 1}, {'tokens_per_day': 50})),
                     ledger=led(tokens=rnd.choice((0, 60)), running=rnd.randint(0, 1),
                                tokens_ok=rnd.random() < .7))
                 for i in range(rnd.randint(1, 4))]
        d = R.route(task(), snap([harness('h')], accts))
        for c in d['candidates']:
            if c['resource'] != d['selected']:
                assert c['eliminated_at_step'] in R.STEPS and c['reason'], c
        assert R.replay({'requirements': task(), 'input_snapshot': snap([harness('h')],
                                                                       accts)}) == d
