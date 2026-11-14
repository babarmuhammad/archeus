"""The P19.5 Core slice (ADR-0030; ADR-0042 §1; the user's P19.5 decisions of
2026-10-01): Pause all pauses exactly the EXECUTING missions as one recorded
batch, Resume all inverts exactly that batch, a mission's priority orders only
dispatch across missions, and the e-stop's state is readable on Health and on
/v1/status, as is what Resume all would resume (`resumable`, R10a). On the real
database, through the writer; fake adapters only."""

import ast
import os

import pytest

from archeus.core import runtime
from archeus.core.application import commands, executions as X, grammar, resources
from archeus.core.domain import entities
from archeus.core.routing import router as R
from archeus.node.local import LocalNode

from v1.integration.test_execution import Rig as ExecRig
from v1.integration.test_intent import brain, make  # noqa: F401 (fixture)
from v1.integration.test_policy import task
from v1.integration.test_routing import Rig

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


@pytest.fixture
def r(db):
    rig = Rig(db)
    rig.account('A')
    yield rig
    LocalNode.clear_estop()


def executing(r, title):
    return r.ready(task('t1', 'write_repo'), title=title)


def state(r, mid):
    return r.m(mid).state


def batches(r):
    return r.all(entities.PauseBatch)


# ── Pause all (decision 1) ──────────────────────────────────────────────────

def test_pause_all_pauses_every_executing_mission_as_one_recorded_batch(r):
    a, b = executing(r, 'A'), executing(r, 'B')
    out = r.do(r.missions.pause_all, who=r.user)
    assert (state(r, a), state(r, b)) == ('PAUSED', 'PAUSED')
    (pb,) = batches(r)
    assert out['pause_batch_id'] == pb.id and pb.mission_ids == (a, b) and out['changed']
    assert [m['id'] for m in out['missions']] == [a, b]
    assert (r.m(a).pause_batch_id, r.m(a).held_from) == (pb.id, 'EXECUTING')
    (ev,) = r.events('pause_batch.created')
    assert ev['payload']['mission_ids'] == [a, b]
    moves = [e['payload'] for e in r.events('mission.state_changed')
             if e['subject']['id'] in (a, b) and e['payload']['to'] == 'PAUSED']
    assert [m['trigger'] for m in moves] == ['pause', 'pause']   # each by its own edge


def test_pause_all_leaves_approved_replanning_and_blocked_missions_alone(r):
    """Decision 1: no new edge. An approved mission still starts afterwards;
    the e-stop is what guarantees nothing does."""
    approved = r.mission('approved')
    r.propose(approved, task('t1', 'write_repo'))
    replanning = executing(r, 'replanning')
    r.run_task(replanning, ok=False, attempts=2)
    r.do(r.missions.advance, mission_id=replanning)
    blocked = executing(r, 'blocked')
    r.do(r.work.dispatch_task, task_id=r.one(entities.Task, mission_id=blocked).id)
    LocalNode.engage_estop()
    r.do(X.estop, who=r.user, missions=r.missions)
    LocalNode.clear_estop()
    r.do(X.rearm, who=r.user)
    assert [state(r, m) for m in (approved, replanning, blocked)] == [
        'APPROVED', 'REPLANNING', 'BLOCKED']
    out = r.do(r.missions.pause_all, who=r.user)
    assert out == {'pause_batch_id': None, 'changed': False, 'missions': []}
    assert batches(r) == [] and [state(r, m) for m in (approved, replanning, blocked)] == [
        'APPROVED', 'REPLANNING', 'BLOCKED']
    r.do(r.missions.fire, mission_id=approved, trigger='dispatch', reason='go')
    assert state(r, approved) == 'EXECUTING'


# ── Resume all (decision 2) ─────────────────────────────────────────────────

def test_resume_all_resumes_exactly_the_last_batch_never_one_paused_on_its_own(r):
    a, b, alone = executing(r, 'A'), executing(r, 'B'), executing(r, 'alone')
    r.do(r.missions.pause, who=r.user, mission_id=alone)
    r.do(r.missions.pause_all, who=r.user)
    (pb,) = batches(r)
    assert pb.mission_ids == (a, b) and r.m(alone).pause_batch_id is None
    out = r.do(r.missions.resume_all, who=r.user)
    assert [m['id'] for m in out['missions']] == [a, b] and out['changed']
    assert (state(r, a), state(r, b), state(r, alone)) == ('EXECUTING', 'EXECUTING', 'PAUSED')
    assert r.m(a).pause_batch_id is None and r.m(a).held_from is None
    assert r.events('pause_batch.resumed')[-1]['payload']['mission_ids'] == [a, b]


def test_a_batch_mission_resumed_and_paused_on_its_own_is_no_longer_the_batchs(r):
    a, b = executing(r, 'A'), executing(r, 'B')
    r.do(r.missions.pause_all, who=r.user)
    r.do(r.missions.resume, who=r.user, mission_id=a)        # by hand
    r.do(r.missions.pause, who=r.user, mission_id=a)         # and on its own again
    assert r.m(a).pause_batch_id is None
    r.do(r.missions.resume_all, who=r.user)
    assert (state(r, a), state(r, b)) == ('PAUSED', 'EXECUTING')


def test_resume_all_reads_the_newest_batch_and_repeats_safely(r):
    a = executing(r, 'A')
    r.do(r.missions.pause_all, who=r.user)                   # batch 1: A
    c = executing(r, 'C')
    r.do(r.missions.pause_all, who=r.user)                   # batch 2: C (A is paused)
    assert [b.mission_ids for b in batches(r)] == [(a,), (c,)]
    first = r.do(r.missions.resume_all, who=r.user)
    assert [m['id'] for m in first['missions']] == [c]
    assert (state(r, a), state(r, c)) == ('PAUSED', 'EXECUTING')
    again = r.do(r.missions.resume_all, who=r.user)
    assert (again['changed'], again['missions']) == (False, [])
    # a Pause all that pauses nothing records nothing: the newest batch stays batch 2
    r.do(r.missions.pause, who=r.user, mission_id=c)
    assert r.do(r.missions.pause_all, who=r.user)['changed'] is False
    assert len(batches(r)) == 2
    assert state(r, a) == 'PAUSED'                           # batch 1 is never resumed by it


def test_resume_all_never_unblocks_a_blocked_mission(r):
    a, b = executing(r, 'A'), executing(r, 'B')
    r.do(r.missions.pause_all, who=r.user)
    r.do(r.missions.resume, who=r.user, mission_id=b)
    r.do(r.work.dispatch_task, task_id=r.one(entities.Task, mission_id=b).id)
    LocalNode.engage_estop()
    r.do(X.estop, who=r.user, missions=r.missions)
    assert state(r, b) == 'BLOCKED'
    r.do(r.missions.resume_all, who=r.user)
    assert (state(r, a), state(r, b)) == ('EXECUTING', 'BLOCKED')


def test_pause_all_and_resume_all_with_nothing_to_do_write_nothing(r):
    head = r.head()
    assert r.do(r.missions.resume_all, who=r.user)['changed'] is False
    assert r.do(r.missions.pause_all, who=r.user)['changed'] is False
    assert r.head() == head and batches(r) == []


# ── what Resume all would resume, readable (R10a) ───────────────────────────
# The minimal contract the client's Resume all needs: /v1/status `resumable`,
# from the one rule Resume all itself runs (`commands.resumable`).

def resumable(r):
    with r.db.read() as conn:
        return commands.resumable(conn)


def resume_all_resumes_what_status_said(r):
    """Resume all, checked against what the read said just before it."""
    said = resumable(r)
    out = r.do(r.missions.resume_all, who=r.user)
    assert (out['pause_batch_id'], [m['id'] for m in out['missions']]) == said
    assert out['changed'] is bool(said[1])
    return out


def test_resumable_is_the_newest_batchs_missions_it_still_holds(r):
    assert resumable(r) == (None, [])
    a, b = executing(r, 'A'), executing(r, 'B')
    r.do(r.missions.pause_all, who=r.user)
    (pb,) = batches(r)
    assert resumable(r) == (pb.id, [a, b])
    resume_all_resumes_what_status_said(r)
    assert resumable(r) == (pb.id, [])
    assert resume_all_resumes_what_status_said(r)['changed'] is False   # a second one: nothing


def test_an_older_batch_still_holding_a_mission_is_not_resumable(r):
    """The case that needed the read: batch A holds m1, the newest batch B held
    only m2, which was resumed by hand. Resume all would resume nothing, so
    nothing is resumable, though m1 still carries A's id."""
    m1 = executing(r, 'm1')
    r.do(r.missions.pause_all, who=r.user)                   # batch A: m1
    m2 = executing(r, 'm2')
    r.do(r.missions.pause_all, who=r.user)                   # batch B: m2
    a, b = batches(r)
    assert (a.mission_ids, b.mission_ids) == ((m1,), (m2,))
    r.do(r.missions.resume, who=r.user, mission_id=m2)       # by hand
    assert resumable(r) == (b.id, [])
    assert r.m(m1).pause_batch_id == a.id and state(r, m1) == 'PAUSED'
    resume_all_resumes_what_status_said(r)
    assert state(r, m1) == 'PAUSED'


def test_a_mission_paused_on_its_own_is_never_resumable(r):
    alone, a = executing(r, 'alone'), executing(r, 'A')
    r.do(r.missions.pause, who=r.user, mission_id=alone)
    assert resumable(r) == (None, [])
    r.do(r.missions.pause_all, who=r.user)
    assert resumable(r)[1] == [a]
    # a batch mission resumed and paused again by hand leaves the batch
    r.do(r.missions.resume, who=r.user, mission_id=a)
    r.do(r.missions.pause, who=r.user, mission_id=a)
    assert resumable(r)[1] == []
    resume_all_resumes_what_status_said(r)
    assert (state(r, alone), state(r, a)) == ('PAUSED', 'PAUSED')


def test_a_pause_all_that_pauses_nothing_leaves_the_newest_batch_resumable(r):
    a = executing(r, 'A')
    r.do(r.missions.pause_all, who=r.user)
    (pb,) = batches(r)
    assert r.do(r.missions.pause_all, who=r.user)['changed'] is False   # nothing executing
    assert batches(r) == [pb] and resumable(r) == (pb.id, [a])
    resume_all_resumes_what_status_said(r)
    assert state(r, a) == 'EXECUTING'


def test_resume_all_and_the_read_share_one_rule():
    """One helper, so the read and the command cannot drift apart."""
    import inspect
    from archeus.api import routes
    assert 'resumable(tx.conn)' in inspect.getsource(commands.Missions.resume_all)
    assert 'commands.resumable(conn)' in inspect.getsource(routes.status)
    assert 'PauseBatch' not in inspect.getsource(commands.Missions.resume_all)


def test_the_contract_declares_what_the_client_reads():
    from archeus.api import schemas
    m, s = schemas.TYPES['Mission'], schemas.TYPES['Status']
    assert m['properties']['priority'] == {'type': 'integer'}
    assert m['properties']['pause_batch_id'] == {'type': 'string', 'nullable': True}
    assert s['properties']['resumable'] == {'type': 'array', 'items': {'type': 'string'}}
    assert 'resumable' in s['required']


# ── authorisation (decision 3): exactly as one mission's pause ──────────────

def test_the_all_scope_routes_take_the_same_scope_as_one_missions_pause():
    from archeus.api import routes
    by = {(x.method, x.path): (x.scope, x.idempotent) for x in routes.ROUTES}
    one = by[('POST', '/v1/missions/{id}/pause')]
    assert by[('POST', '/v1/missions/pause-all')] == one
    assert by[('POST', '/v1/missions/resume-all')] == one
    assert by[('POST', '/v1/missions/{id}/reprioritize')] == one
    assert not hasattr(commands.Missions, 'pause_all_policy')          # no policy stage


# ── priority (decision 4) ───────────────────────────────────────────────────

def test_priority_defaults_to_zero_and_reprioritise_changes_only_it(r):
    mid = executing(r, 'M')
    before = r.m(mid)
    assert before.priority == 0
    pol = r.all(entities.ResourcePolicy)
    out = r.do(r.missions.reprioritise, who=r.user, mission_id=mid, priority=7)
    after = r.m(mid)
    assert out['changed'] and after.priority == 7
    assert {k: v for k, v in after.to_dict().items() if k != 'priority'} == {
        k: v for k, v in before.to_dict().items() if k != 'priority'}
    assert r.all(entities.ResourcePolicy) == pol                       # no policy touched
    assert r.events('mission.updated')[-1]['payload'] == {'priority': 7, 'was': 0}
    assert r.do(r.missions.reprioritise, who=r.user, mission_id=mid, priority=7)[
        'changed'] is False
    with pytest.raises(ValueError):
        r.do(r.missions.reprioritise, who=r.user, mission_id=mid, priority='high')


def test_priority_never_reaches_the_router():
    """Decision 4: a scheduling concern only. The router and the snapshot
    builders never read a mission's priority."""
    for rel in ('archeus/core/routing/router.py', 'archeus/core/application/resources.py',
                'archeus/core/routing/usage.py'):
        src = open(os.path.join(ROOT, rel), encoding='utf-8').read()
        tree = ast.parse(src)
        reads = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                 and n.attr == 'priority' and isinstance(n.value, ast.Name)
                 and n.value.id in ('mission', 'm', 'mission_row')]
        assert reads == [], rel


def test_a_reprioritised_mission_routes_exactly_as_before(r):
    mid = executing(r, 'M')
    m = r.m(mid)
    (t,) = r.all(entities.Task, mission_id=mid)
    plan = r.one(entities.Plan, mission_id=mid)
    now = __import__('time').time()

    def snap(mission):
        with r.db.read() as conn:
            return resources.task_snapshot(
                conn, adapters=r.router.adapters(), feed=r.feed, mission=mission, plan=plan,
                task=t, decision=_decision(), now=now)
    req0, s0, _ = snap(m)
    r.do(r.missions.reprioritise, who=r.user, mission_id=mid, priority=99)
    req1, s1, _ = snap(r.m(mid))
    # the usage feed's own reading is taken at each call: the only field that moves
    for sn in (s0, s1):
        for a in sn['accounts']:
            a.pop('usage', None)
    assert (req0, s0) == (req1, s1)
    d0, d1 = R.route(req0, s0), R.route(req1, s1)
    assert d0 == d1 and d0['account_id'] is not None


def test_higher_priority_steps_first_and_equals_keep_the_oldest_first(db):
    """The engine pass is the dispatch order across missions: it steps higher
    priority first, oldest first among equals (the order it had before)."""
    rig = Rig(db)
    old, mid_, new = (executing(rig, t) for t in ('old', 'mid', 'new'))
    rig.do(rig.missions.reprioritise, who=rig.user, mission_id=new, priority=5)
    seen = []

    class Spy:
        def step(self, mission_id):
            seen.append(mission_id)
            return {'changed': False}

        def reconcile_orphans(self):
            return []
    loop = runtime.EngineLoop(Spy(), db, idle_s=0.01)
    loop._pass()
    assert seen == [new, old, mid_]


def test_under_contended_capacity_the_higher_priority_mission_dispatches_first(db):
    """Decision 4 end to end: one account, one concurrency slot (AP-1), two
    missions ready at once; the higher priority one takes the slot."""
    x = ExecRig(db)
    try:
        acc = x.account('Only')
        x.do(resources.set_resource_policy, who=x.user, account_id=acc,
             usage_measures=(), budgets={'concurrency': 1})
        low = x.ready(task('t1', 'write_repo'), title='low')
        high = x.ready(task('t1', 'write_repo'), title='high')
        x.do(x.missions.reprioritise, who=x.user, mission_id=high, priority=3)
        runtime.EngineLoop(x.engine, db, idle_s=0.01)._pass()
        (won,) = x.all(entities.Execution)
        assert won.mission_id == high and won.account_id == acc
        rd = [d for d in x.all(entities.RouteDecision) if d.mission_id == low][-1]
        assert rd.result != 'selected'
        assert next(c for c in rd.candidates if c['resource'] == acc)['reason'] == \
            'budget reached: concurrency'
    finally:
        x.cleanup()
        LocalNode.clear_estop()


# ── grammar (decision 1, 2, 4): deterministic, no model ─────────────────────

def test_pause_all_resume_all_and_reprioritise_never_call_the_model(make):  # noqa: F811
    fake = brain()
    rg = make([fake])
    rg.run(commands.create_mission, title='Ship it', objective='o')
    reply, it = rg.say('pause all')
    assert (it.via, it.kind, it.reason) == ('grammar', 'control_verb', 'pause_all')
    assert it.resolution == 'answered' and 'nothing was paused' in reply['text']
    _reply, it = rg.say('Resume all')
    assert (it.via, it.reason, it.resolution) == ('grammar', 'resume_all', 'answered')
    _reply, it = rg.say('reprioritise Ship it to 3')
    assert (it.via, it.reason, it.resolution) == ('grammar', 'reprioritise', 'mission_updated')
    assert rg.all(entities.Mission)[0].priority == 3
    reply, it = rg.say('reprioritise Ship it')
    assert (it.via, it.resolution) == ('grammar', 'declined') and 'as a number' in reply['text']
    assert rg.all(entities.Mission)[0].priority == 3
    assert fake.sent == []


def test_the_grammar_reads_the_three_verbs(db):
    rig = Rig(db)
    mid = rig.mission('Ship it')
    with db.read() as conn:
        assert grammar.resolve(conn, 'pause all') == grammar.Control('pause_all', None, '')
        assert grammar.resolve(conn, 'resume ALL.') == grammar.Control('resume_all', None, '')
        assert grammar.resolve(conn, 'reprioritize Ship it 2') == grammar.Control(
            'reprioritise', {'kind': 'mission', 'id': mid}, '2')
        assert grammar.resolve(conn, 'reprioritise %s to -1' % mid).arg == '-1'
        assert grammar.resolve(conn, 'reprioritise Nobody to 2') is None      # the brain's
        assert grammar.resolve(conn, 'pause Ship it').verb == 'pause'           # unchanged


# ── the e-stop, readable (decision 5) ──────────────────────────────────────

@pytest.fixture
def core(archeus_home):
    from archeus.core import engine, ports
    from archeus.core.routing.usage import FakeUsageFeed
    from v1.judge.http import TempCore
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), usage=FakeUsageFeed())).start()
    yield tc
    tc.stop()


def _post(tc, path, body=None):
    from archeus.core.domain import ids
    return tc.http('POST', path, body=dict(body or {}, idempotency_key=ids.new_ulid()))


def test_health_and_status_both_read_the_e_stop(core):
    def armed():
        return (core.http('GET', '/v1/health').json()['armed'],
                core.http('GET', '/v1/status').json()['armed'])
    assert armed() == (True, True)
    assert _post(core, '/v1/estop').json()['armed'] is False
    assert armed() == (False, False)
    assert _post(core, '/v1/rearm').json() == {'armed': True}
    assert armed() == (True, True)


def test_the_all_scope_routes_answer_over_http(core):
    assert core.http('GET', '/v1/status').json()['resumable'] == []
    assert _post(core, '/v1/missions/pause-all').json() == {
        'pause_batch_id': None, 'changed': False, 'missions': []}
    assert _post(core, '/v1/missions/resume-all').json()['changed'] is False
    mid = _post(core, '/v1/missions', {'title': 'M', 'objective': 'o'}).json()['id']
    one = core.http('GET', '/v1/missions/%s' % mid).json()
    assert (one['priority'], one['pause_batch_id']) == (0, None)    # declared, as Core returns them
    got = _post(core, '/v1/missions/%s/reprioritize' % mid, {'priority': 4})
    assert got.status == 200 and got.json()['changed'] is True
    assert core.http('GET', '/v1/missions/%s' % mid).json()['priority'] == 4
    bad = _post(core, '/v1/missions/%s/reprioritize' % mid, {'priority': 'high'})
    assert bad.status == 400


# ── helpers ─────────────────────────────────────────────────────────────────

def _decision():
    import types
    return types.SimpleNamespace(id='pdc_x', outcome='covered', items=())
