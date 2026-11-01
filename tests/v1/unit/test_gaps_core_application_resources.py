"""T-306: the ten highest-risk uncovered branches of
archeus/core/application/resources.py, as tests.

Fail-closed and denial paths first (who may grant and revoke an account; what
counts as live work against an account's ceilings), then the boundary values
(a day, an own call's maximum run, the staleness window), then the error paths
(a crashing adapter probe). Same style and seams as the module's closest unit
tests (test_own_call_no_tools.py, test_routing_units.py): the real database on
the test's own ARCHEUS_HOME, scripted adapters, every instant fixed by the test
so nothing depends on the clock, no process, no network, no sleep.
"""

from types import SimpleNamespace

import pytest

from archeus.core.application import commands, resources
from archeus.core.application.authorization import NotPermitted
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.routing import router as R
from archeus.infra.db import Database, rows

HARNESS = 'fake'
#: every test decides at this instant, and writes the rows' own created_at, so
#: no assertion here moves when the suite runs or on which machine it runs
NOW = resources._epoch('2026-09-16T10:00:00.000Z')
TODAY = resources._iso(NOW)[:10]


@pytest.fixture
def db():
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def actors(db):
    def principal(kind, scopes):
        return Ref(kind, db.writer.execute(commands.register_principal, {
            'kind': kind, 'scopes': list(scopes)})['id'])
    return SimpleNamespace(
        user=principal('user_device', ('observe', 'control', 'approve', 'admin')),
        system=principal('system', ('system',)),
        brain=principal('brain', ('propose',)),
        execution=principal('execution', ('report', 'checkpoint', 'request_approval')))


def do(db, command, **kw):
    return db.writer.execute(command, dict(kw))


def read(db, fn, *a, **kw):
    with db.read() as conn:
        return fn(conn, *a, **kw)


def account(db, actors, label='A', auth=True):
    """A registered account, AVAILABLE when probed ok, UNVERIFIED when not probed.
    `auth` is the adapter's answer as `Resources.probe` gives it, or True/False
    for the scripted version of it, or None for an adapter that cannot tell."""
    probe = ({'ok': bool(auth), 'detail': 'the probe said so'}
             if not isinstance(auth, (dict, type(None))) else auth)
    return do(db, resources.register_account, actor=actors.user, harness_id=HARNESS,
              label=label, auth_kind='api_key', auth=probe)['id']


def health(db, acc):
    with db.read() as c:
        return rows.get(c, entities.Account, acc).entity.health


def call_route(db, actors, *, account_id, result='selected', outcome=None, max_run_s=None,
               created_at=None):
    """One recorded own-call decision (what `own_calls` scans), as `record_route`
    writes it, with the `created_at` its decision was committed at."""
    at = resources._iso(NOW) if created_at is None else created_at
    rd = entities.RouteDecision(
        id=ids.new_id('route_decision'), subject=Ref('archeus_call', 'brain'), purpose='brain',
        decided_by='router', result=result, outcome=outcome, account_id=account_id,
        account_ref=None if account_id else '%s:default' % HARNESS, harness_id=HARNESS,
        requirements={'subject': 'archeus_call', 'purpose': 'brain', 'max_run_s': max_run_s},
        input_snapshot={'now': at, 'accounts': [], 'harnesses': []})

    def run(tx, actor):
        tx.insert(rd, actor=actor)
        tx.conn.execute('UPDATE route_decisions SET created_at = ?, updated_at = ? WHERE id = ?',
                        (at, at, rd.id))
        tx.append(new_event('route.decided', Ref('route_decision', rd.id), actor,
                            payload={'result': result}))
    do(db, run, actor=actors.system)
    return rd.id


def snapshot_row(db, actors, account_id, *, window='5h', pct=10.0, observed_at=None,
                 source='scripted', resets_at=None):
    at = resources._iso(NOW if observed_at is None else observed_at)

    def run(tx, actor):
        tx.insert(entities.UsageSnapshot(id=ids.new_id('usage_snapshot'),
                                         account_id=account_id, window=window,
                                         utilisation_pct=pct, source=source, observed_at=at,
                                         resets_at=resets_at), actor=actor)
        tx.append(new_event('usage.observed', Ref('account', account_id), actor,
                            payload={'window': window, 'pct': pct, 'source': source},
                            visibility='system'))
    do(db, run, actor=actors.system)


def ledger_row(db, actors, account_id, *, created_at=None, tokens_in=1, tokens_out=1,
               cost_usd=0.0, basis='reported_total'):
    at = resources._iso(NOW) if created_at is None else created_at

    def run(tx, actor):
        rd = entities.RouteDecision(
            id=ids.new_id('route_decision'), subject=Ref('archeus_call', 'brain'),
            decided_by='router', result='selected', outcome={'state': 'ok'},
            account_id=account_id)
        tx.insert(rd, actor=actor)
        led = entities.UsageLedger(id=ids.new_id('usage_ledger'), account_id=account_id,
                                   route_decision_id=rd.id, tokens_in=tokens_in,
                                   tokens_out=tokens_out, cost_usd=cost_usd, basis=basis)
        tx.insert(led, actor=actor)
        tx.conn.execute('UPDATE usage_ledger SET created_at = ?, updated_at = ? WHERE id = ?',
                        (at, at, led.id))
        tx.append(new_event('route.decided', Ref('route_decision', rd.id), actor,
                            payload={'result': 'selected'}))
    do(db, run, actor=actors.system)
    return at


# ── 1. resources.py:106 — only a user device grants or revokes an account ───

def test_only_a_user_device_enables_or_disables_an_account(db, actors):
    """`_user(actor, 'enables or disables an account')`: with it removed or with
    `kind` read wrongly, any principal — the system, a brain, an execution —
    could take an account out of rotation or put it back, and the assertions on
    `health` below are exactly what such a change would move."""
    acc = account(db, actors)
    assert health(db, acc) == 'AVAILABLE'
    for who in (actors.system, actors.brain, actors.execution):
        with pytest.raises(NotPermitted, match='enables or disables an account'):
            do(db, resources.set_account_enabled, actor=who, account_id=acc, enabled=False)
        assert health(db, acc) == 'AVAILABLE'              # nothing revoked
    do(db, resources.set_account_enabled, actor=actors.user, account_id=acc, enabled=False)
    assert health(db, acc) == 'DISABLED'
    for who in (actors.system, actors.brain, actors.execution):
        with pytest.raises(NotPermitted, match='enables or disables an account'):
            do(db, resources.set_account_enabled, actor=who, account_id=acc, enabled=True)
        assert health(db, acc) == 'DISABLED'               # nothing granted back


# ── 2. resources.py:110 — enabling without the adapter's answer never restores ─

def test_enabling_an_account_never_restores_it_without_the_probe(db, actors):
    """`if enabled and auth is not None:` — the user's `enable` is not a health
    claim. If it fired `auth_ok` on its own (or defaulted `auth` to ok) the
    account would come back AVAILABLE, which is what the router routes to,
    without the adapter ever having been asked."""
    quiet, broken = account(db, actors, label='A'), account(db, actors, label='B')
    for acc in (quiet, broken):
        do(db, resources.set_account_enabled, actor=actors.user, account_id=acc, enabled=False)
        assert health(db, acc) == 'DISABLED'
    out = do(db, resources.set_account_enabled, actor=actors.user, account_id=quiet,
             enabled=True)
    assert out['health'] == 'UNVERIFIED' and health(db, quiet) == 'UNVERIFIED'
    out = do(db, resources.set_account_enabled, actor=actors.user, account_id=broken,
             enabled=True, auth={'ok': False, 'detail': 'no login'})
    assert out['health'] == 'UNAUTHENTICATED' and health(db, broken) == 'UNAUTHENTICATED'
    # and the probe's own answer still decides, both ways
    ok = account(db, actors, label='C')
    do(db, resources.set_account_enabled, actor=actors.user, account_id=ok, enabled=False)
    out = do(db, resources.set_account_enabled, actor=actors.user, account_id=ok, enabled=True,
             auth={'ok': True, 'detail': 'the adapter probed the login'})
    assert out['health'] == 'AVAILABLE' and health(db, ok) == 'AVAILABLE'


# ── 3. resources.py:203 — only a call that ran is live work ─────────────────

@pytest.mark.parametrize('result,outcome,live', [
    ('selected', None, True), ('fallback', None, True),
    ('ask', None, False), ('blocked', None, False),            # nothing was chosen: nothing ran
    ('selected', {'state': 'ok'}, False),                      # the outcome releases the slot
    ('fallback', {'state': 'error'}, False),
])
def test_an_own_call_is_live_work_only_between_its_decision_and_its_outcome(
        db, actors, result, outcome, live):
    """`if rd.outcome is not None or rd.result not in ('selected', 'fallback'): return
    False`: with either test inverted or dropped, a decision that selected
    nothing, or a call that already answered, holds a concurrency slot for ever
    and the account's `running` (its budget path) is wrong either way."""
    acc = account(db, actors)
    rd = call_route(db, actors, account_id=acc, result=result, outcome=outcome)
    with db.read() as c:
        row = rows.get(c, entities.RouteDecision, rd)
        assert resources.own_call_live(row, NOW) is live
        counts = resources.live_counts(c, TODAY, NOW, acc)
        # nothing that is live work and nothing that lapsed leaves no entry at all
        assert counts.get(acc, {'running': 0, 'lapsed': False}) == {
            'running': 1 if live else 0, 'lapsed': False}
        assert (acc in counts) is live


# ── 4. resources.py:206 — the maximum run of an own call is a boundary ───────

@pytest.mark.parametrize('max_run_s,at,live', [
    (600, NOW + 599, True),
    (600, NOW + 600, True),        # `<= bound`: exactly at it the call is still in flight
    (600, NOW + 601, False),       # one second past: a Core that died cannot hold the slot
    (None, NOW + 86400, True),     # no bound recorded: live until its outcome
])
def test_an_own_call_holds_a_slot_only_up_to_its_maximum_run(db, actors, max_run_s, at, live):
    """`return bound is None or now - _epoch(row.created_at) <= bound`: an
    off-by-one (`<` instead of `<=`, or the comparison inverted) releases a call
    that is still running or keeps one that is dead counting against the
    account's concurrency budget for ever."""
    acc = account(db, actors)
    rd = call_route(db, actors, account_id=acc, max_run_s=max_run_s)
    with db.read() as c:
        assert resources.own_call_live(rows.get(c, entities.RouteDecision, rd), at) is live


# ── 5. resources.py:244, 275 — only an own call of TODAY that lost its outcome ─

def test_only_an_own_call_of_today_that_ended_with_no_outcome_lapses_the_day(db, actors):
    """`elif rd.outcome is None and rd.result in ('selected', 'fallback') and
    r.created_at >= today:` — the three conditions are the whole `lapsed`
    derivation: it marks a call that may have run and will never write its row,
    so its account's day becomes unknown (never 0). A call of yesterday is not
    today's unknown; a call still in flight is running, not lapsed; a decision
    that selected nothing is neither."""
    ran = account(db, actors, label='A')
    old = account(db, actors, label='B')
    flying = account(db, actors, label='C')
    never = account(db, actors, label='D')
    answered = account(db, actors, label='E')
    call_route(db, actors, account_id=ran, max_run_s=60, created_at=resources._iso(NOW - 120))
    call_route(db, actors, account_id=old, max_run_s=60, created_at='2026-09-15T23:00:00.000Z')
    call_route(db, actors, account_id=flying, max_run_s=3600)
    call_route(db, actors, account_id=never, result='ask', max_run_s=3600)
    # the same call of today, past its run, but its Core did answer: not a lapse
    call_route(db, actors, account_id=answered, outcome={'state': 'ok'}, max_run_s=60,
               created_at=resources._iso(NOW - 120))
    with db.read() as c:
        counts = resources.live_counts(c, TODAY, NOW)
        for acc, want in ((ran, {'running': 0, 'lapsed': True}),
                          (old, {'running': 0, 'lapsed': False}),
                          (flying, {'running': 1, 'lapsed': False})):
            assert counts.get(acc, {'running': 0, 'lapsed': False}) == want
        assert never not in counts                     # a decision that chose nothing is neither
        assert answered not in counts                  # a call that answered is not a lapse
        # and the lapse is what makes that account's day unknown, never 0
        assert resources.ledger_totals(c, ran, TODAY, NOW)['complete'] == {
            'tokens': False, 'cost': False}
        assert resources.ledger_totals(c, old, TODAY, NOW)['complete'] == {
            'tokens': True, 'cost': True}
        # the account filter reads the same two scans
        assert resources.live_counts(c, TODAY, NOW, flying) == {flying: {'running': 1,
                                                                         'lapsed': False}}


# ── 6. resources.py:167 — a usage feed nobody wrote is None, never 0 ─────────

def test_latest_usage_is_none_with_nothing_stored_and_keeps_the_newest_of_each_window(
        db, actors):
    """`if not newest: return None` and the last-stored-wins loop: an account
    with no reading has no usage at all (the router eliminates it, it is not a
    free 0%), and each window keeps the snapshot stored last, the resets of the
    windows that have one and the one source the reading names."""
    acc = account(db, actors)
    assert read(db, resources.latest_usage, acc) is None
    snapshot_row(db, actors, acc, window='5h', pct=10.0, observed_at=NOW - 3600)
    got = read(db, resources.latest_usage, acc)
    assert got['windows'] == {'5h': 10.0} and got['resets_at'] == {}
    assert got['observed_at'] == NOW - 3600 and got['source'] == 'scripted'
    snapshot_row(db, actors, acc, window='5h', pct=40.0, observed_at=NOW - 60,
                 source='usage_api')
    snapshot_row(db, actors, acc, window='7d', pct=5.0, observed_at=NOW - 60,
                 source='rollout_file', resets_at='2026-09-20T00:00:00.000Z')
    got = read(db, resources.latest_usage, acc)
    assert got['windows'] == {'5h': 40.0, '7d': 5.0}          # the 5h stored last wins
    assert got['resets_at'] == {'7d': '2026-09-20T00:00:00.000Z'}   # no reset is not a reset
    assert got['observed_at'] == NOW - 60 and got['source'] == 'rollout_file'
    assert read(db, resources.latest_usage, account(db, actors, label='other')) is None


# ── 7. resources.py:266 — what was consumed before today is not today ────────

def test_usage_recorded_before_today_never_counts_towards_today(db, actors):
    """`if r.created_at < today: continue`: a ceiling of the day that also
    counts yesterday is a budget that is already spent before the day starts,
    and an account blocked from its own first call."""
    acc = account(db, actors)
    ledger_row(db, actors, acc, created_at=resources._iso(NOW), tokens_in=10, tokens_out=5,
               cost_usd=0.5, basis='reported_total')
    ledger_row(db, actors, acc, created_at='2026-09-15T23:59:59.000Z', tokens_in=1000,
               tokens_out=1000, cost_usd=99.0, basis='reported_total')
    led = read(db, resources.ledger_totals, acc, TODAY, NOW)
    assert led['tokens_today'] == 15 and led['cost_today'] == 0.5
    assert led['complete'] == {'tokens': True, 'cost': True}    # not even spoiled by yesterday
    assert led['running'] == 0
    # an account with nothing in the ledger at all: a day it cannot disprove,
    # which is what the budget gate in the router reads as known
    assert read(db, resources.ledger_totals, account(db, actors, label='empty'), TODAY,
                NOW) == {'tokens_today': 0, 'cost_today': 0.0, 'running': 0,
                         'complete': {'tokens': True, 'cost': True}}
    # the same rows, the day after: none of them is that day's either
    assert read(db, resources.ledger_totals, acc, '2026-09-17', NOW)[
        'tokens_today'] == 0


# ── 8. resources.py:269, 272, 274 — completeness per measure, on what was told ─

def test_the_day_is_complete_per_measure_only_on_what_the_harness_reported(db, actors):
    """`complete['tokens'] &= whole and None not in (e.tokens_in, e.tokens_out)` and
    `complete['cost'] &= whole and e.cost_usd is not None`: the two measures are
    judged apart, and only a `reported_total` row is the harness's own total.
    If any of the three fell over, a day whose figures were never reported
    would read as known, and the budget path would spend against a 0 it made up."""
    no_cost = account(db, actors, label='A')
    half = account(db, actors, label='B')
    lower = account(db, actors, label='C')
    ledger_row(db, actors, no_cost, tokens_in=3, tokens_out=4, cost_usd=None)
    ledger_row(db, actors, half, tokens_in=3, tokens_out=None, cost_usd=0.25)
    ledger_row(db, actors, lower, tokens_in=3, tokens_out=4, cost_usd=0.25, basis='partial')
    got = {acc: read(db, resources.ledger_totals, acc, TODAY, NOW)
           for acc in (no_cost, half, lower)}
    assert got[no_cost] == {'tokens_today': 7, 'cost_today': 0.0, 'running': 0,
                            'complete': {'tokens': True, 'cost': False}}
    assert got[half] == {'tokens_today': 3, 'cost_today': 0.25, 'running': 0,
                         'complete': {'tokens': False, 'cost': True}}
    assert got[lower] == {'tokens_today': 7, 'cost_today': 0.25, 'running': 0,
                          'complete': {'tokens': False, 'cost': False}}


# ── 9. resources.py:185 — the same reading inside the window is not news ─────

def reading(pct, at):
    return {'windows': {'5h': pct}, 'observed_at': at, 'source': 'scripted',
            'resets_at': {'5h': None}}


def observed(db, acc):
    with db.read() as c:
        return [(r.entity.window, r.entity.utilisation_pct)
                for r in rows.where(c, entities.UsageSnapshot, account_id=acc)]


def test_the_same_reading_inside_the_staleness_window_is_not_news(db, actors):
    """`fresh = have.get('observed_at') is not None and (rd['observed_at'] -
    have['observed_at'] <= R.STALE_S)` with the `continue` under it: without it
    every poll of the feed adds a snapshot and the age of the account's usage
    never grows, so the stale penalty and the reset ordering both read a
    permanent now. The boundary is inclusive; a different value is always news,
    and a reading of nothing records nothing."""
    acc = account(db, actors)
    quiet = account(db, actors, label='B')
    do(db, resources.observe, actor=actors.system, readings={acc: reading(10.0, NOW),
                                                              quiet: {}})
    assert observed(db, acc) == [('5h', 10.0)] and observed(db, quiet) == []
    for at, rows_ in ((NOW + R.STALE_S - 1, 1), (NOW + R.STALE_S, 1), (NOW - 99999.0, 1),
                      (NOW + R.STALE_S + 1, 2), (NOW + R.STALE_S + 2, 2)):
        do(db, resources.observe, actor=actors.system, readings={acc: reading(10.0, at)})
        assert len(observed(db, acc)) == rows_           # the same pct, at the edge and past it
    do(db, resources.observe, actor=actors.system, readings={acc: reading(11.0, NOW)})
    assert observed(db, acc) == [('5h', 10.0), ('5h', 10.0), ('5h', 11.0)]


# ── 10. resources.py:724, 726 — an adapter that cannot answer the probe ──────

class Adapter:
    """A scripted harness adapter for the transport-facing service: it answers
    `authenticate` and `capabilities`, nothing else, and never runs anything."""

    def __init__(self, id=HARNESS, ok=True, detail=None, raises=None, measures=('tokens',),
                 caps=True):
        self.id, self.ok, self.detail, self.raises = id, ok, detail, raises
        self.measures, self.asked = list(measures), []
        self.caps = caps

    def authenticate(self, ref):
        self.asked.append(ref)
        if self.raises:
            raise self.raises
        return SimpleNamespace(ok=self.ok, detail=self.detail)

    def capabilities(self, ref):
        if not self.caps:
            raise self.raises or RuntimeError('no capabilities')
        return SimpleNamespace(usage_measures=tuple(self.measures))


class Silent:
    """An adapter with no `authenticate` at all: nothing can tell whether a login
    works, so the account is registered UNVERIFIED rather than guessed at."""

    id = 'silent'


def service(*adapters):
    by = {a.id: a for a in adapters}
    return resources.Resources(
        registry=SimpleNamespace(ids=lambda: sorted(by), get=lambda i: by[i]), callers=[])


def test_a_probe_that_crashes_fails_closed_and_one_nobody_answers_is_none(db, actors):
    """`except Exception as e: return {'ok': False, ...}` and the `return None`
    out of the loop: an adapter bug is a failed login, never a registered
    account, and an adapter that cannot tell leaves the account UNVERIFIED. The
    same holds for what the adapter declares it reports: a crash declares
    nothing, which is what makes a budget on a reported measure be refused."""
    crash = Adapter(raises=RuntimeError('boom'))
    assert service(crash).probe(HARNESS, 'home-x') == {'ok': False, 'detail': 'RuntimeError: boom'}
    assert [(a.account_id, a.home_ref) for a in crash.asked] == [(HARNESS, 'home-x')]
    acc = account(db, actors, label='crashed', auth=service(crash).probe(HARNESS, None))
    assert health(db, acc) == 'UNAUTHENTICATED'
    assert service(Silent()).probe('silent') is None
    assert health(db, account(db, actors, label='unprobed', auth=None)) == 'UNVERIFIED'
    assert service(Adapter(ok=False)).probe(HARNESS) == {'ok': False, 'detail': ''}
    assert service(Adapter(detail='logged in')).probe(HARNESS) == {'ok': True,
                                                                    'detail': 'logged in'}
    assert service(Adapter(raises=RuntimeError('no capabilities'), caps=False)).usage_measures(
        HARNESS) == ()
    assert service(Adapter(measures=('tokens', 'cost'))).usage_measures(HARNESS) == (
        'cost', 'tokens')
