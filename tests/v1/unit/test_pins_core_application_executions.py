"""T-400 hand-mutant pins on archeus/core/application/executions.py.

Every test here was written after reading the module and the existing tests
and asking: would any existing test still pass if this condition were
inverted, removed or loosened? The tests below pin the conditions the audit
found UNCOVERED; each fails on the named mutation. Platform-neutral: no OS
calls, no sleeps, no network, explicit `Z` instants, fakes only through the
seams the existing tests already use (monkeypatched `X.rows` / `X.active_plan`
/ `X.authorization`, and the real writer over the ARCHEUS_HOME the v1 conftest
pins into the test's temp directory).
"""

import json
from types import SimpleNamespace

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref

SYSTEM = Ref('system', ids.new_id('principal'))
USER = Ref('user_device', ids.new_id('principal'))
T0 = 1_800_000_000.0                       # a fixed epoch; every instant is derived


# ── the real-writer seam (the same one test_execution_units._seeded uses) ───

def _world(*, execs):
    """Mission, plan, task and the given executions on a real database.

    *execs* is a list of entity kwargs; each gets a fresh id and the shared
    task/mission/plan. Returns (db, mid, pid, tid, eids)."""
    from archeus.infra.db import Database
    db = Database.open()
    mid, pid, tid = (ids.new_id(k) for k in ('mission', 'plan', 'task'))
    made = []

    def run(tx, **_):
        tx.insert(entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE,
                                   title='M', objective='o', state='EXECUTING'),
                  actor=USER)
        tx.insert(entities.Plan(id=pid, mission_id=mid, state='APPROVED'), actor=USER)
        tx.insert(entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t', title='T',
                                kind='code_change', state='RUNNING', max_attempts=3),
                  actor=USER)
        for kw in execs:
            e = entities.Execution(id=ids.new_id('execution'), task_id=tid, mission_id=mid,
                                   plan_id=pid, **kw)
            tx.insert(e, actor=USER)
            made.append(e.id)
        tx.append(new_event('mission.updated', Ref('mission', mid), USER, payload={},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return db, mid, pid, tid, made


def _row(db, kind, id_):
    from archeus.infra.db import rows
    with db.read() as r:
        return rows.get(r, kind, id_)


def _exec_db(state='INTENT', **kw):
    db, _mid, _pid, tid, eids = _world(execs=[dict(state=state, **kw)])
    return db, tid, eids[0]


# ── charged_attempts (executions.py:98): `charged is not False` ─────────────
# Mutation caught: a truthiness test (`if r.entity.charged`) stops counting
# the never-stamped rows (charged None); `is not None` starts counting the
# uncharged ones. No existing test names charged_attempts or feeds it a row
# whose charge is False or None.

def test_charged_attempts_counts_never_stamped_rows_and_not_uncharged_ones():
    db, _mid, _pid, tid, _ = _world(execs=[
        dict(state='ENDED_OK', charged=True, attempt=1),
        dict(state='ENDED_KILLED', charged=False, attempt=2),
        dict(state='ENDED_ERROR', charged=None, attempt=3),
        dict(state='ENDED_ERROR', charged=None, attempt=4)])
    try:
        counted = db.writer.execute(lambda tx, **_: X.charged_attempts(tx, tid), {})
        assert counted == 3            # the True and both Nones count; the False does not
        # a truthiness test would say 1; `is not None` would say 2
    finally:
        db.close()


# ── spawn_wait (executions.py:207): the streak runs backwards from the end ─
# Mutation caught: dropping `reversed` counts the leading failures instead of
# the trailing ones: with [fail, ok-start, fail, fail] the wait is one step
# too short (spawn_wait_s(1)=15 instead of spawn_wait_s(2)=30). The existing
# T106r5 row set reads the same either way.

def test_spawn_wait_counts_the_trailing_failures_not_the_leading_ones(monkeypatch):
    now = T0 + 31
    iso = lambda s: X._iso(T0 + s)                      # noqa: E731
    a = SimpleNamespace(stop_reason='spawn', started_at=None, ended_at=iso(0))
    b = SimpleNamespace(stop_reason=None, started_at=iso(10), ended_at=None)
    c = SimpleNamespace(stop_reason='spawn', started_at=None, ended_at=iso(20))
    d = SimpleNamespace(stop_reason='spawn', started_at=None, ended_at=iso(30))
    monkeypatch.setattr(X.rows, 'where', lambda conn, cls, **eq: [
        SimpleNamespace(entity=x, created_at=iso(0)) for x in (a, b, c, d)])
    got = X.spawn_wait(None, 't1', now)
    assert got == X._epoch(iso(30)) + X.spawn_wait_s(2)   # two failures in a row


# ── binding (executions.py:232, 235, 243): the three untested arms ─────────
# Fakes on the seams the module already exposes; the happy baseline in each
# test proves the refusal below is the named clause's doing.

def _bound_execution():
    return SimpleNamespace(id='e1', mission_id='m1', plan_id='p1', plan_digest='d1',
                           task_id='t1', policy_decision_id='pd2')


def _bind_fakes(monkeypatch, *, plan='ok', digest='d1', intact=True, task='ok',
                decisions=None):
    e = _bound_execution()
    if plan == 'ok':
        prow = SimpleNamespace(entity=SimpleNamespace(id='p1', state='APPROVED',
                                                      digest=digest, plan_version=3))
    elif plan == 'superseded':
        prow = SimpleNamespace(entity=SimpleNamespace(id='p1', state='SUPERSEDED',
                                                      digest=digest, plan_version=3))
    elif plan == 'other':
        prow = SimpleNamespace(entity=SimpleNamespace(id='pX', state='APPROVED',
                                                      digest=digest, plan_version=3))
    else:                                       # plan='none'
        prow = None
    monkeypatch.setattr(X, 'active_plan', lambda conn, mid: prow)
    trow = SimpleNamespace(entity=SimpleNamespace(id='t1', plan_id='p1', state='RUNNING'))
    monkeypatch.setattr(X.rows, 'get', lambda conn, cls, id_: trow)
    if decisions is None:
        decisions = [dict(id='pd1', stage='action', outcome='covered'),
                     dict(id='pd2', stage='dispatch', outcome='covered')]
    monkeypatch.setattr(X.rows, 'where', lambda conn, cls, **eq: [
        SimpleNamespace(entity=SimpleNamespace(**d)) for d in decisions])
    monkeypatch.setattr(X.authorization, 'intact', lambda conn, plan_: intact)
    return e


def test_binding_refuses_when_no_plan_is_in_force(monkeypatch):
    for plan in ('none', 'other', 'superseded'):
        e = _bind_fakes(monkeypatch, plan=plan)
        assert X.binding(None, e) == 'the plan it was dispatched under is no longer in force'
    assert X.binding(None, _bind_fakes(monkeypatch)) is None    # the baseline holds


def test_binding_refuses_a_digest_change_or_a_tampered_plan(monkeypatch):
    e = _bind_fakes(monkeypatch, digest='other-digest')
    assert 'does not match its recorded digest' in X.binding(None, e)
    e = _bind_fakes(monkeypatch, intact=False)
    assert 'does not match its recorded digest' in X.binding(None, e)
    assert X.binding(None, _bind_fakes(monkeypatch)) is None    # the baseline holds


def test_binding_refuses_a_superseded_or_missing_dispatch_decision(monkeypatch):
    e = _bind_fakes(monkeypatch, decisions=[])
    assert X.binding(None, e) == 'its dispatch authorisation was superseded'
    # the newest dispatch decision is not the one the execution carries
    e = _bind_fakes(monkeypatch, decisions=[dict(id='pd9', stage='dispatch',
                                                 outcome='covered')])
    assert X.binding(None, e) == 'its dispatch authorisation was superseded'
    # the newest dispatch decision is no longer covered
    e = _bind_fakes(monkeypatch, decisions=[dict(id='pd2', stage='dispatch',
                                                 outcome='denied')])
    assert X.binding(None, e) == 'its dispatch authorisation was superseded'
    # a later NON-dispatch decision never replaces the dispatch one (the stage
    # filter): removing it makes this row the newest and the answer wrong
    e = _bind_fakes(monkeypatch, decisions=[dict(id='pd2', stage='dispatch',
                                                 outcome='covered'),
                                            dict(id='pd3', stage='action',
                                                 outcome='denied')])
    assert X.binding(None, e) is None
    assert X.binding(None, _bind_fakes(monkeypatch)) is None    # the baseline holds


# ── prepare_process (executions.py:270, 273): state and sequence gates ─────
# No existing test starts a preparation from a state outside the trio or with
# a process number that is not the next one: removing either check would
# let a second, unprepared process onto a live execution.

@pytest.mark.parametrize('state', ['STARTING', 'RUNNING', 'STOPPING', 'ENDED_OK'])
def test_prepare_refuses_a_state_from_which_no_process_may_start(state):
    db, _tid, eid = _exec_db(state, process_seq=1, isolated=True)
    try:
        before = _row(db, entities.Execution, eid)
        with pytest.raises(X.lifecycle.IllegalTrigger, match='no process may be started'):
            db.writer.execute(X.prepare_process, {
                'actor': SYSTEM, 'execution_id': eid, 'token_digest': '0' * 64,
                'workdir': 'w', 'branch': None, 'process_seq': 2, 'isolated': True})
        assert _row(db, entities.Execution, eid).version == before.version
    finally:
        db.close()


def test_prepare_refuses_a_process_number_that_is_not_the_next_one():
    for seq in (2, 5):                      # the current one, and one skipped ahead
        db, _tid, eid = _exec_db('INTENT', process_seq=2, isolated=True)
        try:
            before = _row(db, entities.Execution, eid)
            with pytest.raises(ValueError, match='cannot follow'):
                db.writer.execute(X.prepare_process, {
                    'actor': SYSTEM, 'execution_id': eid, 'token_digest': '0' * 64,
                    'workdir': 'w', 'branch': None, 'process_seq': seq, 'isolated': True})
            assert _row(db, entities.Execution, eid).version == before.version
        finally:
            db.close()


# ── record_process (executions.py:382, 385): the prepared sequence and the
#    trigger map ─────────────────────────────────────────────────────────────
# No existing test reports an unprepared sequence or a state outside the
# trigger map; and the map's values are pinned so a PAUSED row reported as
# `spawn` (instead of `resume`) fails the state table.

def test_record_process_refuses_a_sequence_it_never_prepared(monkeypatch):
    """executions.py:382 — the pid/create_time pair must carry the sequence
    the supervisor prepared.  The execution is deliberately made bindable
    (plan, digest, dispatch decision): with the gate deleted the command
    runs past it, takes its edge and stores a pid nobody prepared."""
    db, _tid, eid = _exec_db('INTENT', process_seq=1, hook_token_hash=None,
                             plan_digest='d1',
                             policy_decision_id=ids.new_id('policy_decision'))
    try:
        e = _row(db, entities.Execution, eid).entity
        def seed_decision(tx, **_):
            tx.insert(entities.PolicyDecision(
                id=e.policy_decision_id, task_id=e.task_id, mission_id=e.mission_id,
                stage='dispatch', decision='ALLOW', outcome='covered', reason='pin'),
                actor=SYSTEM)
            tx.append(new_event('policy_decision.created',
                                Ref('policy_decision', e.policy_decision_id), SYSTEM,
                                payload={}, workspace=ids.GLOBAL_WORKSPACE))
        db.writer.execute(seed_decision, {})
        prow = SimpleNamespace(entity=SimpleNamespace(
            id=e.plan_id, state='APPROVED', digest=e.plan_digest, plan_version=3))
        trow = SimpleNamespace(entity=SimpleNamespace(
            id=e.task_id, plan_id=e.plan_id, state='RUNNING'))
        decision = SimpleNamespace(entity=SimpleNamespace(
            id=e.policy_decision_id, stage='dispatch', outcome='covered'))
        monkeypatch.setattr(X, 'active_plan', lambda conn, mid: prow)
        monkeypatch.setattr(X.authorization, 'intact', lambda conn, p: True)
        import archeus.infra.db.rows as _rows
        real_get = _rows.get
        monkeypatch.setattr(
            X.rows, 'get',
            lambda conn, cls, id_: (trow if cls is entities.Task
                                    else real_get(conn, cls, id_)))
        monkeypatch.setattr(X.rows, 'where', lambda conn, cls, **eq: [decision])
        before = _row(db, entities.Execution, eid)
        with pytest.raises(ValueError, match='was not prepared'):
            db.writer.execute(X.record_process, {
                'actor': SYSTEM, 'execution_id': eid, 'pid': 4242,
                'create_time': 'ct', 'process_seq': 2})       # prepared was 1
        assert _row(db, entities.Execution, eid).version == before.version
    finally:
        db.close()


def test_record_process_refuses_a_state_that_cannot_start_a_process():
    db, _tid, eid = _exec_db('RUNNING', process_seq=1)
    try:
        before = _row(db, entities.Execution, eid)
        with pytest.raises(X.lifecycle.IllegalTrigger,
                           match='a process can only start from INTENT or a halt'):
            db.writer.execute(X.record_process, {
                'actor': SYSTEM, 'execution_id': eid, 'pid': 4242,
                'create_time': 'ct', 'process_seq': 1})
        assert _row(db, entities.Execution, eid).version == before.version
    finally:
        db.close()


@pytest.mark.parametrize('state', ['INTENT', 'PAUSED', 'AWAITING_APPROVAL'])
def test_record_process_takes_its_own_edge_from_each_startable_state(state):
    db, _tid, eid = _exec_db(state, process_seq=1)
    try:
        out = db.writer.execute(X.record_process, {
            'actor': SYSTEM, 'execution_id': eid, 'pid': 4242,
            'create_time': 'ct', 'process_seq': 1})
        assert out['state'] == 'STARTING'
        assert _row(db, entities.Execution, eid).entity.state == 'STARTING'
    finally:
        db.close()


# ── record_progress (executions.py:423): the nothing-new early return ──────
# The integration pin (test_E71) only proves a backwards offset raises. The
# early return itself is unpinned: removing it records a progress event and
# a write on every poll, and loosening any one of the compared fields makes
# a real change (a new usage, pressure or context at the same offset) vanish.

def _progress_db():
    return _exec_db('RUNNING', process_seq=1, stream_offset=50)


def test_record_progress_writes_and_records_nothing_when_nothing_is_new():
    db, _tid, eid = _progress_db()
    try:
        before = _row(db, entities.Execution, eid)
        db.writer.execute(X.record_progress, {
            'actor': SYSTEM, 'execution_id': eid, 'offset': 50, 'events': 0})
        after = _row(db, entities.Execution, eid)
        assert after.version == before.version             # no write, no bump
        with db.read() as r:                                 # and no event either
            types = [row[0] for row in r.execute(
                "SELECT type FROM events WHERE subject_kind = 'execution'"
                ' AND subject_id = ?', (eid,))]
        assert 'execution.progress' not in types
    finally:
        db.close()


@pytest.mark.parametrize('field,read_back', [
    ('usage', lambda e: e.usage), ('pressure', lambda e: e.pressure),
    ('context', lambda e: e.context)])
def test_record_progress_at_the_same_offset_still_records_a_real_change(field, read_back):
    value = {'tokens_in': 10} if field == 'usage' else (0.35 if field == 'pressure'
                                                        else {'used': 100})
    kw = {field: dict(value) if isinstance(value, dict) else value}
    db, _tid, eid = _progress_db()
    try:
        before = _row(db, entities.Execution, eid)
        db.writer.execute(X.record_progress,
                          dict({'actor': SYSTEM, 'execution_id': eid, 'offset': 50}, **kw))
        after = _row(db, entities.Execution, eid)
        assert after.version != before.version           # the early return did NOT take it
        assert read_back(after.entity) == value
    finally:
        db.close()


# ── _usage (executions.py:467): aliases, the ledger keys, numbers only ────
# Nothing existing calls X._usage directly; a bool sneaking into the ledger
# (`True` as a "count") or a foreign key surviving would pass every suite.

def test_usage_keeps_only_numeric_ledger_figures_and_maps_the_aliases():
    assert X._usage({'input_tokens': 5, 'output_tokens': 7,
                     'cache_read_input_tokens': 1, 'cache_creation_input_tokens': 2,
                     'total_cost_usd': 0.5}) == {
        'tokens_in': 5, 'tokens_out': 7, 'cache_read': 1, 'cache_write': 2,
        'cost_usd': 0.5}
    got = X._usage({'tokens_in': True, 'cost_usd': '3', 'model': 'sonnet',
                    'num': 3, 'is_error': False})
    assert got == {}                                     # bools, text and strangers die
    assert X._usage(None) == {}
    assert json.dumps(X._usage({'tokens_in': 5})) == '{"tokens_in": 5}'


# ── account_limited (executions.py:1119): only an in-service account moves ──
# No existing call puts the command on an account that is already LIMITED (or
# DEGRADED/OPEN); removing the health guard fires `window_exhausted` from a
# state whose table has no such edge, which this test turns into a failure.

@pytest.mark.parametrize('health', ['LIMITED', 'DEGRADED', 'OPEN'])
def test_account_limited_never_moves_an_account_that_cannot_take_the_edge(health):
    from archeus.infra.db import Database
    db = Database.open()
    acc = ids.new_id('account')
    stored = X._iso(T0 + 86400)

    def run(tx, **_):
        tx.insert(entities.Account(id=acc, harness_id='pi', label='W',
                                   auth_kind='api_key', health=health,
                                   limited_until=stored), actor=SYSTEM)
        tx.append(new_event('account.registered', Ref('account', acc), SYSTEM,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    try:
        out = db.writer.execute(X.account_limited, {
            'actor': SYSTEM, 'account_id': acc,
            'resets_at': X._iso(T0 + 48 * 3600), 'now': T0})
        assert out['account_id'] == acc
        a = _row(db, entities.Account, acc).entity
        assert (a.health, a.limited_until) == (health, stored)   # nothing moved
    finally:
        db.close()


def test_account_limited_still_limits_an_available_account():
    """The control the guard cannot pass by being inverted: an AVAILABLE
    account does take `window_exhausted` and stores the provider's reset."""
    from archeus.infra.db import Database
    db = Database.open()
    acc = ids.new_id('account')

    def run(tx, **_):
        tx.insert(entities.Account(id=acc, harness_id='pi', label='W',
                                   auth_kind='api_key', health='AVAILABLE'),
                  actor=SYSTEM)
        tx.append(new_event('account.registered', Ref('account', acc), SYSTEM,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    try:
        db.writer.execute(X.account_limited, {
            'actor': SYSTEM, 'account_id': acc,
            'resets_at': X._iso(T0 + 48 * 3600), 'now': T0})
        a = _row(db, entities.Account, acc).entity
        from datetime import datetime
        assert a.health == 'LIMITED'
        assert datetime.fromisoformat(a.limited_until.replace('Z', '+00:00')).timestamp() == T0 + 48 * 3600
    finally:
        db.close()
