"""T-1166: the ten highest-risk uncovered branches of
archeus/core/application/resources.py lines 435-620 inclusive, as tests.
Fail-closed and denial first, then boundaries, then fault paths. The starting
ten probes were checked against tests/v1/integration/test_routing.py,
tests/v1/integration/test_spawn_breaker.py, tests/v1/integration/test_execution.py
(E30) and tests/v1/unit/{test_gaps_core_application_resources,test_routing_units}.py;
two probes already had a passing assertion that fails when the branch breaks and
were replaced (documented on the tests below). Final selected branches:

 1. current_authorization  resources.py:446   foreign plan_id with a matching digest
 2. current_authorization  resources.py:451   forged `covered` head decision == 'DENY'
 3. _affinity              resources.py:460-475  dropped by ('breaker','limit') stops,
                                                non-task subjects, account_ref fallback
 4. _approved_fallbacks    resources.py:476-482  APPROVED `route` approval of ANOTHER
                                                plan version (and REJECTED / wrong kind)
 5. route_wait             resources.py:492-496  only the task's LATEST decision (rowid
                                                DESC) decides the wait
 6. route_wait             resources.py:503   `until > now` boundary; an unreadable
                                                unblock_at is no wait and no error
 7. route_wait             resources.py:492-493  WHERE task_id: another task's blocked
                                                breaker decision is not this task's wait
 8. task_snapshot          resources.py:520-523  adapter whose default_account crashes:
                                                the entry is recorded why_not'd, never thrown
 9. record_route          resources.py:560-588  a failing reading rolls the whole
                                                decision and its event back
10. _written_resets       resources.py:604-617  replay: unknown reset text is omitted
                                                (None), a written {at, key} is kept, the
                                                caller's snapshot is never mutated

Same seams as the neighbouring files: the real database on the test's own
ARCHEUS_HOME (tmp_path), the P10 rig of test_routing.py (fake registry adapters,
scripted feed), every command through the writer, one transaction each. No
`tc` fixture, no engine or manager, no process, no network, no sleep: routing
touches no adapter beyond discover/capabilities/default_account (test_B7's
guarantee), and all fakes are in-process.
"""

import hashlib
import json
import time
from types import SimpleNamespace

import pytest

from archeus.core.application import commands, resources
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.harnesses.fake import FakeHarness

from v1.integration.test_policy import task
from v1.integration.test_routing import Rig

FUTURE = '2099-01-01T00:00:00.000Z'
FUTURE_EPOCH = resources._epoch(FUTURE)
ALLOW = {'class': 'write_repo', 'decision': 'ALLOW', 'boundary': None}


@pytest.fixture
def r(db):
    return Rig(db)


def active_plan(rig, mid):
    with rig.db.read() as c:
        return commands.active_plan(c, mid).entity


def put_decision(rig, *, subject, result, mission_id=None, task_id=None, unblock_at=None,
                 candidates=(), harness_id=None, account_id=None, account_ref=None):
    """One recorded RouteDecision (what record_route writes), straight through
    the writer; its rowid order is the insertion order below."""
    rd = entities.RouteDecision(
        id=ids.new_id('route_decision'), subject=subject, result=result,
        mission_id=mission_id, task_id=task_id, unblock_at=unblock_at,
        candidates=candidates, harness_id=harness_id, account_id=account_id,
        account_ref=account_ref, decided_by='router', requirements={}, input_snapshot={})

    def run(tx, actor):
        tx.insert(rd, actor=actor)
        tx.append(new_event('route.decided', Ref('route_decision', rd.id), actor,
                            payload={'result': result}))
    rig.do(run, who=rig.system)
    return rd


def put_policy_decision(rig, **fields):
    pd = entities.PolicyDecision(id=ids.new_id('policy_decision'),
                                 decision=fields.pop('decision', 'ALLOW'),
                                 stage='dispatch', outcome='covered', **fields)

    def run(tx, actor):
        tx.insert(pd, actor=actor)
        tx.append(new_event('policy_decision.created', Ref('policy_decision', pd.id), actor))
    rig.do(run, who=rig.system)
    return pd


def put_approval(rig, *, kind, state, plan_id, mission_id, task_id, account, requested_by):
    digest = hashlib.sha256(('%s|%s|%s' % (kind, state, plan_id)).encode()).hexdigest()
    a = entities.Approval(
        id=ids.new_id('approval'), kind=kind, subject=Ref('task', task_id),
        action_hash=digest, requested_by=requested_by, mission_id=mission_id,
        plan_id=plan_id, task_id=task_id, state=state, expires_at=FUTURE,
        items=({'task': 't1', 'resource': {'harness': 'fake', 'account': account}},))

    def run(tx, actor):
        tx.insert(a, actor=actor)
        tx.append(new_event('approval.state_changed', Ref('approval', a.id), actor,
                           payload={'state': state}))
    rig.do(run, who=rig.system)
    return a


def second_plan(rig):
    """A real, different plan (its own approved mission): the foreign plan_id
    an attacker or a stale record could name."""
    mid2 = rig.mission('M2')
    rig.propose(mid2, task('t9', 'write_repo'))
    return active_plan(rig, mid2)


# ── 1. resources.py:446 — the decision's plan_id is part of the authorisation ──

def test_gaps3_01_foreign_plan_authorization_cannot_route(r):
    """`if (d.plan_id, d.plan_digest) != (plan.id, plan.digest): raise NotAuthorised`:
    test_I_A4 varies only the digest (replace(plan, digest='0'*64)), so deleting
    `d.plan_id` from the tuple breaks nothing. Here the digest matches exactly and
    only the plan_id is foreign: a covered dispatch decision of this task, no DENY,
    the latest one, recorded against another real plan. It must not route."""
    r.account('Work')
    mid = r.ready()
    (t,) = r.all(entities.Task, mission_id=mid)
    plan = active_plan(r, mid)
    other = second_plan(r)
    forged = put_policy_decision(r, mission_id=mid, plan_id=other.id,
                                 plan_digest=plan.digest, task_id=t.id, items=(ALLOW,))
    with r.db.read() as c:
        with pytest.raises(resources.NotAuthorised, match='another plan version'):
            resources.current_authorization(c, t, plan, forged.id)
    # the same row with the plan's own id authorises: the raise came from plan_id,
    # not from the record being a forgery in shape
    good = put_policy_decision(r, mission_id=mid, plan_id=plan.id, plan_digest=plan.digest,
                               task_id=t.id, items=(ALLOW,))
    with r.db.read() as c:
        assert resources.current_authorization(c, t, plan, good.id).id == good.id


# ── 2. resources.py:451 — the head DENY of a forged `covered` decision ────────

def test_gaps3_02_forged_deny_head_cannot_route(r):
    """`if d.decision == 'DENY' or any(...)`: test_I_A6 forges items carrying a
    DENY over an ALLOW head, so deleting the head disjunct breaks nothing. A real
    P9 never pairs a DENY head with outcome `covered` (a denied task is refused
    before any dispatch decision is recorded), so only a forged record can reach
    it here — and it must be refused, fail-closed, before the latest-decision
    check is even consulted."""
    r.account('Work')
    mid = r.ready()
    (t,) = r.all(entities.Task, mission_id=mid)
    plan = active_plan(r, mid)
    forged = put_policy_decision(r, mission_id=mid, plan_id=plan.id,
                                 plan_digest=plan.digest, task_id=t.id,
                                 decision='DENY', items=(ALLOW,))
    with r.db.read() as c:
        with pytest.raises(resources.NotAuthorised, match='denies'):
            resources.current_authorization(c, t, plan, forged.id)
    assert r.rds(mission_id=mid) == [] and r.all(entities.Execution) == []


# ── 3. resources.py:460-475 — what affinity may follow ───────────────────────

def test_gaps3_03_affinity_excludes_stopped_and_non_task_routes(r):
    """`dropped = {... for r in rows.where(conn, entities.Execution, mission_id=...)
    if r.entity.stop_reason in ('ceiling', 'limit', 'breaker')}` plus the filters
    `subject.kind == 'task'` and `result in ('selected', 'fallback')` plus
    `rd.account_id or rd.account_ref`: test_I_R3 only exercises the `since`
    clearing, and E30 pins only the `ceiling` value through the whole handoff
    rig. An 'ask' decision, an archeus_call decision, and a route stopped by the
    breaker are all followed by the wrong account — or by none — when their
    filter falls out; a 'pressure' stop is not in the dropped set and must keep
    its affinity."""
    acc = r.account('A')
    mid = r.ready()
    (t,) = r.all(entities.Task, mission_id=mid)
    task_ref = Ref('task', t.id)
    rd1 = put_decision(r, subject=task_ref, result='selected', mission_id=mid,
                       task_id=t.id, harness_id='fake', account_id=acc)
    put_decision(r, subject=task_ref, result='ask', mission_id=mid, task_id=t.id,
                 harness_id='fake', account_ref='fake:asked')
    mission = r.m(mid)
    with r.db.read() as c:
        assert resources._affinity(c, mission) == {'harness': 'fake', 'account': acc}
    # an own call of the same mission ran later: it is not where the task ran
    put_decision(r, subject=Ref('archeus_call', 'brain'), result='selected', mission_id=mid,
                 harness_id='fake', account_ref='fake:default')
    with r.db.read() as c:
        assert resources._affinity(c, mission) == {'harness': 'fake', 'account': acc}

    def stop(rd_id, stop_reason, attempt):
        ex = entities.Execution(id=ids.new_id('execution'), task_id=t.id, mission_id=mid,
                                attempt=attempt, state='INTENT', harness_id='fake',
                                route_decision_id=rd_id, account_id=acc,
                                stop_reason=stop_reason)

        def run(tx, actor):
            tx.insert(ex, actor=actor)
            tx.append(new_event('execution.ended', Ref('execution', ex.id), actor,
                                payload={'stop_reason': stop_reason}))
        r.do(run, who=r.system)

    stop(rd1.id, 'breaker', 1)                     # §7 D10: it must not route straight back
    with r.db.read() as c:
        assert resources._affinity(c, mission) is None
    rd4 = put_decision(r, subject=task_ref, result='selected', mission_id=mid,
                       task_id=t.id, harness_id='fake', account_ref='fake:default')
    with r.db.read() as c:                          # the unregistered default: its ref is it
        assert resources._affinity(c, mission) == {'harness': 'fake',
                                                   'account': 'fake:default'}
    stop(rd4.id, 'pressure', 2)                    # not a resource stop: the affinity holds
    with r.db.read() as c:
        assert resources._affinity(c, mission) == {'harness': 'fake',
                                                   'account': 'fake:default'}


# ── 4. resources.py:476-482 — approved fallbacks bind the current plan ────────

def test_gaps3_04_foreign_approval_cannot_grant_fallback(r):
    """`if a.entity.kind == 'route' and a.entity.state == 'APPROVED' and
    a.entity.plan_id == plan.id`: I_F2/I_F3 only ever produce the approval the
    router itself asked for, on the current plan, and decide it through P9. An
    APPROVED `route` approval recorded against another plan version, a decided
    approval of another kind, and a REJECTED one must all leave the fallback
    ungranted — the task asks again and nothing runs."""
    a = r.account('A', priority=1)
    b = r.account('B', priority=2, fallback='ask')
    r.feed.set(a, '5h', 100)
    r.feed.set(b, '5h', 79)
    mid = r.ready()
    (t,) = r.all(entities.Task, mission_id=mid)
    plan = active_plan(r, mid)
    other = second_plan(r)
    for kind, state, plan_id in (('route', 'APPROVED', other.id),        # foreign plan
                                 ('task', 'APPROVED', plan.id),          # not a route ask
                                 ('route', 'REJECTED', plan.id)):        # never approved
        put_approval(r, kind=kind, state=state, plan_id=plan_id, mission_id=mid,
                     task_id=t.id, account=b, requested_by=r.user.id)
    with r.db.read() as c:
        assert resources._approved_fallbacks(c, t, plan) == []
    out = r.dispatch(mid)
    assert (out['execution_id'], out['state']) == (None, 'AWAITING_APPROVAL')
    assert r.all(entities.Execution) == []
    ap = r.pending(mid)
    assert (ap.kind, ap.state, ap.plan_id) == ('route', 'PENDING', plan.id)
    # the real approval of this plan version is what unlocks it (control)
    r.decide(ap)
    assert r.dispatch(mid)['account_id'] == b
    assert r.rds(mission_id=mid)[-1].result == 'fallback'


# ── 5. resources.py:492-496 — the latest decision is the only one that waits ──

def test_gaps3_05_only_the_latest_route_decides_the_wait(r):
    """`ORDER BY rowid DESC LIMIT 1`: every existing assertion inspects a task
    with exactly one RouteDecision, so reading the OLDEST (or every) decision
    passes them all. A task that was blocked by the breaker and re-routed onto
    an account must not keep waiting on its stale blocked row, and one whose
    newest decision is blocked must wait even though it was selected before."""
    r.ready(task('t1', 'write_repo'), task('t2', 'write_repo'))
    t1, t2 = sorted(r.all(entities.Task), key=lambda t: t.key)
    breaker_c = ({'resource': 'fake', 'eliminated_at_step': 'breaker'},)
    put_decision(r, subject=Ref('task', t1.id), result='blocked', mission_id=t1.mission_id,
                 task_id=t1.id, unblock_at=FUTURE, candidates=breaker_c)
    put_decision(r, subject=Ref('task', t1.id), result='selected', mission_id=t1.mission_id,
                 task_id=t1.id, harness_id='fake', account_id=None)
    put_decision(r, subject=Ref('task', t2.id), result='selected', mission_id=t2.mission_id,
                 task_id=t2.id, harness_id='fake', account_id=None)
    put_decision(r, subject=Ref('task', t2.id), result='blocked', mission_id=t2.mission_id,
                 task_id=t2.id, unblock_at=FUTURE, candidates=breaker_c)
    with r.db.read() as c:
        now = time.time()
        assert resources.route_wait(c, t1.id, now) is None        # recovered: no wait
        assert resources.route_wait(c, t2.id, now) == FUTURE_EPOCH   # blocked again: waits


# ── 6. resources.py:503 — the wait ends AT its instant, and garbage is no wait ─

def test_gaps3_06_wait_boundary_and_unreadable_unblock(r):
    """`return until if until and until > now else None` and
    `at = instants.instant(d.unblock_at)`: test_T106_the_third_failure... checks
    `now + 301` only, so `>` turning into `>=` (or into no check at all at the
    exact instant) passes the suite. At the recorded instant the task must be
    routable again; a hair before, it waits. And an unblock_at that is not a
    time must be no wait and must not raise — Core's engine pass reads this on
    every try (T-106 r2's rule for provider text)."""
    r.ready(task('t1', 'write_repo'), task('t2', 'write_repo'))
    t1, t2 = sorted(r.all(entities.Task), key=lambda t: t.key)
    breaker_c = ({'resource': 'fake', 'eliminated_at_step': 'breaker'},)
    put_decision(r, subject=Ref('task', t1.id), result='blocked', mission_id=t1.mission_id,
                 task_id=t1.id, unblock_at=FUTURE, candidates=breaker_c)
    put_decision(r, subject=Ref('task', t2.id), result='blocked', mission_id=t2.mission_id,
                 task_id=t2.id, unblock_at='not a time', candidates=breaker_c)
    with r.db.read() as c:
        assert resources.route_wait(c, t1.id, FUTURE_EPOCH - 0.5) == FUTURE_EPOCH
        assert resources.route_wait(c, t1.id, FUTURE_EPOCH) is None      # it is due now
        assert resources.route_wait(c, t1.id, FUTURE_EPOCH + 1) is None  # and past it
        assert resources.route_wait(c, t2.id, time.time()) is None       # garbage: no wait


# ── 7. resources.py:492-493 — another task's block is not this task's wait ────

def test_gaps3_07_other_task_wait_is_ignored(r):
    """`WHERE task_id = ?` in route_wait's scan: every existing call asks the
    task that owns the blocked decision, so dropping the filter — letting the
    newest decision of ANY task hold a task that was never blocked — breaks no
    test. Here the blocked breaker decision is the newest row in the table, of
    a DIFFERENT task: the task that ran fine, and a task never routed at all,
    must both be free."""
    r.ready(task('t1', 'write_repo'), task('t2', 'write_repo'), task('t3', 'write_repo'))
    t1, t2, t3 = sorted(r.all(entities.Task), key=lambda t: t.key)
    put_decision(r, subject=Ref('task', t1.id), result='selected', mission_id=t1.mission_id,
                 task_id=t1.id, harness_id='fake', account_id=None)
    put_decision(r, subject=Ref('task', t2.id), result='blocked', mission_id=t2.mission_id,
                 task_id=t2.id, unblock_at=FUTURE,
                 candidates=({'resource': 'fake', 'eliminated_at_step': 'breaker'},))
    with r.db.read() as c:
        now = time.time()
        assert resources.route_wait(c, t1.id, now) is None
        assert resources.route_wait(c, t3.id, now) is None         # never routed: no wait
        assert resources.route_wait(c, t2.id, now) == FUTURE_EPOCH  # (the owner still does)


# ── 8. resources.py:520-523 — an adapter that cannot name its default account ─

def _raise_default():
    raise RuntimeError('no default')


def test_gaps3_08_adapter_without_a_default_is_excluded(db):
    """`except Exception as e: ref, why = None, '%s: %s' % (type(e).__name__, e)`:
    the same shape in `Resources.probe` has test_a_probe_that_crashes_fails_closed,
    but nothing puts a crashing `default_account` in front of `task_snapshot`. An
    adapter bug must not raise out of dispatch (one bad adapter would stop every
    mission), must not invent an account, and must not route there: the entry is
    recorded `why_not` and the router's health step eliminates it, while the task
    runs on the other harness."""
    broken = FakeHarness('broken')
    broken.default_account = _raise_default          # an instance seam: still "the fake"
    r = Rig(db, adapters=[broken, FakeHarness('other')])
    acc = r.account('Work', harness_id='other')
    out = r.dispatch(r.ready())
    assert out['account_id'] == acc                  # it ran on the sound harness
    (e,) = r.all(entities.Execution)
    assert e.harness_id == 'other'
    (rd,) = r.rds()
    assert {c['harness']: c['eliminated_at_step'] for c in rd.candidates} == {
        'broken': 'health', 'other': None}
    assert any('RuntimeError: no default' in (c.get('reason') or '')
               for c in rd.candidates)
    entry = [a for a in rd.input_snapshot['accounts'] if a['harness'] == 'broken'][0]
    assert (entry['registered'], entry['ref'], entry['id']) == (False, None, None)
    assert entry['why_not'] == 'RuntimeError: no default'


# ── 9. resources.py:560-588 — a decision that cannot record its readings ──────

_BLOCKED = {'result': 'blocked', 'selected': None, 'harness_id': None, 'account_id': None,
            'account_ref': None, 'model': None, 'effort': None, 'label': None,
            'why': None, 'candidates': [], 'fallback_from': [], 'unblock_at': None}


def test_gaps3_09_record_route_reading_failure_writes_nothing(r):
    """`observe(tx, actor=actor, readings=readings)` inside the transaction that
    also inserts the RouteDecision and appends `route.decided`: the writer rolls
    the whole command back, so a reading the feed should never have produced
    leaves no half-decision behind — an orphan `selected` row would hold a
    concurrency slot (own_call_live) and lie about what ran. The same command
    with no readings is then shown to record normally, so the refusal below can
    only come from the reading."""
    acc = r.account('Live')
    mid = r.ready()
    (t,) = r.all(entities.Task, mission_id=mid)
    kw = dict(actor=r.system, subject=Ref('task', t.id),
              requirements={'subject': 'task', 'mission_id': mid, 'task_id': t.id},
              snapshot={'now': resources._iso(time.time()), 'harnesses': [], 'accounts': [],
                        'terms': {}, 'affinity': None, 'approved_fallbacks': []},
              decision=dict(_BLOCKED))
    broken_reading = {acc: {'windows': {'5h': 50.0}, 'source': 'scripted'}}  # no observed_at
    with pytest.raises(KeyError, match='observed_at'):
        r.db.writer.execute(resources.record_route, dict(kw, readings=broken_reading))
    assert r.rds(mission_id=mid) == []                    # no decision survived
    assert r.events('route.decided') == []                # and no event said it did
    assert r.all(entities.UsageSnapshot, account_id=acc) == []   # nor a partial reading
    r.db.writer.execute(resources.record_route, dict(kw, readings=None))
    (rd,) = r.rds(mission_id=mid)                          # the control: it records fine
    assert rd.result == 'blocked' and len(r.events('route.decided')) == 1


# ── 10. resources.py:604-617 — replay writes unknown resets away ──────────────

_H = {'id': 'h', 'installed': True,
      'capabilities': ['code_edit', 'headless', 'shell'], 'enforcement': 'hook',
      'structured_output': 'native', 'efforts': [], 'exempt': True,
      'models': [{'id': 'm-large', 'tier': 'large', 'context_window': None}]}
_POL = {'priority': 1, 'allocation_pct': 80, 'reserve_pct': 10, 'brain_reserve_pct': 10,
        'fallback': 'ask', 'budgets': {}, 'project_allow': [], 'project_deny': []}
_REQ = {'subject': 'task', 'capabilities': ['code_edit'], 'structured_output': False,
        'min_model_tier': None, 'models': {}, 'preferred': {}, 'forbidden': {},
        'required': {}, 'size': 'M', 'mission_id': 'msn_x', 'task_id': 'tsk_x',
        'project_id': None,
        'policy': {'decision_id': 'pdc_x', 'outcome': 'covered',
                   'items': [{'class': 'write_repo', 'decision': 'ALLOW',
                              'boundary': None}]}}
_NOW = '2026-09-26T10:00:00.000Z'
_GOOD = {'at': '2026-09-26T12:00:00.000Z', 'key': '2026-09-26T12:00:00.000Z'}


def _snap(resets_at):
    account = {'id': 'acc_x', 'ref': 'acc_x', 'harness': 'h', 'label': 'ACC_X',
               'auth_kind': 'api_key', 'registered': True, 'health': 'AVAILABLE',
               'why_not': None, 'policy': dict(_POL),
               'usage': {'windows': {'5h': 100.0}, 'age_s': 0, 'resets_at': resets_at},
               'ledger': {'tokens_today': 0, 'cost_today': 0, 'running': 0}}
    return {'now': _NOW, 'harnesses': [dict(_H)], 'accounts': [account], 'terms': {},
            'affinity': None, 'approved_fallbacks': []}


def test_gaps3_10_replay_omits_unknown_resets():
    """`v if isinstance(v, dict) else instants.ahead(v, now)` (and the copy
    discipline around it): test_T106r8 replays only values that ARE times (the
    {at, key} pair kept as written, free text that is one), so neither dropping
    the isinstance check (ahead() of a {at, key} dict reads as no time and would
    silently drop the real wait) nor passing garbage through (the router would
    sort a raw string as if it were a wait) fails the existing suite. An unknown
    provider reset must replay as no wait — never as a time — and the caller's
    stored snapshot must come back unmutated."""
    snap_raw = _snap({'5h': 'not a time', '7d': dict(_GOOD)})
    before = json.dumps(snap_raw, sort_keys=True)
    written = resources._written_resets(snap_raw)
    assert json.dumps(snap_raw, sort_keys=True) == before        # the record is never touched
    assert written is not snap_raw and written['accounts'][0] is not snap_raw['accounts'][0]
    assert written['accounts'][0]['usage']['resets_at'] == {'5h': None, '7d': _GOOD}
    d = resources.replay(SimpleNamespace(requirements=dict(_REQ), input_snapshot=snap_raw))
    assert (d['result'], d['unblock_at']) == ('blocked', _GOOD['at'])   # only the real wait
    assert json.dumps(snap_raw, sort_keys=True) == before       # replay wrote nothing either
    junk = resources.replay(SimpleNamespace(
        requirements=dict(_REQ),
        input_snapshot=_snap({'5h': 'not a time', '7d': '2020-01-01T00:00:00.000Z'})))
    assert (junk['result'], junk['unblock_at']) == ('blocked', None)  # no readable future: no wait
