"""P3: the mission lifecycle on a real database — guards, actions, orchestration,
concurrency and atomicity, all through the P2 writer (state-machines §0, §2)."""

import dataclasses
import threading
from collections import deque

import pytest

from archeus.core import ports
from archeus.core.application import commands, lifecycle
from archeus.core.domain import entities, guards, ids, states
from archeus.core.domain.guards import CriterionFact, MissionFacts, TaskFact
from archeus.core.domain.states import TransitionProof
from archeus.core.domain.values import Ref
from archeus.infra.db import rows, writer
from archeus.infra.eventlog import outbox, retention

A, H = 'automatic', 'human'
PLAN = dict(plan_version=1, cost_within_ceiling=True,
            tasks=(TaskFact('t1', 'code_change', 'PENDING', action_classes=('write_repo',)),))
#: facts under which each mission guard passes (and nothing else is implied)
PASSING = {
    'plan_auto_approved': MissionFacts(**PLAN),
    # something to ask: the cost band is over the ceiling (the port says ALLOW)
    'plan_needs_approval': MissionFacts(**dict(PLAN, cost_within_ceiling=False)),
    'verification_failed': MissionFacts(criteria=(CriterionFact(A, 'FAILED'),)),
    'accepted': MissionFacts(review='ACCEPTED'),
    # `redispatch` reads the mission's own held_from, not the facts
    'all_tasks_done': MissionFacts(plan_version=1,
                                   tasks=(TaskFact('t1', 'code_change', 'SUCCEEDED'),)),
    'verified': MissionFacts(criteria=(CriterionFact(A, 'PASSED'),)),
    'awaiting_human_acceptance': MissionFacts(criteria=(CriterionFact(H, None),)),
    'replan_budget_exhausted': MissionFacts(plan_version=3),
    'task_failed_retryable': MissionFacts(tasks=(TaskFact('t1', 'code_change', 'FAILED',
                                                          attempts=2, max_attempts=2),)),
    'unrecoverable': MissionFacts(missing_capability=True),
}


class Facts:
    """A scripted snapshot source: tests set `.now` to what the world says."""

    def __init__(self, now=None):
        self.now = now or MissionFacts()
        self.calls = 0

    def __call__(self, tx, row):
        self.calls += 1
        return self.now


class SpyPolicy(ports.AllowAllPolicy):
    def __init__(self, decision='ALLOW'):
        self.decision, self.asked, self.contexts = decision, [], []

    def evaluate(self, action, ctx):
        self.asked.append((action.action_class, action.target, ctx['mission_id']))
        self.contexts.append(ctx)
        return entities.PolicyDecision(id=ids.new_id('policy_decision'), action=action,
                                       decision=self.decision, reason='spy')


@pytest.fixture
def facts():
    return Facts()


@pytest.fixture
def missions(facts):
    return commands.Missions(policy=ports.AllowAllPolicy(), facts=facts)


@pytest.fixture
def run(db, actor, missions):
    """run('pause', mission_id, **kw) -> the command's response."""
    def go(verb, mission_id, *, key=None, who=None, **kw):
        return db.writer.execute(getattr(missions, verb),
                                 dict(kw, actor=who or actor, mission_id=mission_id),
                                 idempotency_key=key)
    return go


def _state(db, mid):
    with db.read() as r:
        row = rows.get(r, entities.Mission, mid)
    return row.entity.state, row.version


def _snapshot(db, mid):
    with db.read() as r:
        return (rows.get(r, entities.Mission, mid).version, outbox.head(r),
                r.execute('SELECT COUNT(*) FROM idempotency_keys').fetchone()[0])


def _changes(db, mid):
    with db.read() as r:
        return [e.payload for e in outbox.events_after(r, 0, limit=1000)
                if e.subject.id == mid and e.type == 'mission.state_changed']


def _fire(run, facts, mid, trigger, **kw):
    if trigger in PASSING:
        facts.now = PASSING[trigger]
    return run('fire', mid, trigger=trigger, reason='test: %s' % trigger, **kw)


#: RESUMED held from EXECUTING, so both of its exits are legal from there.
PRE_PLAN_RESUMED = ('start', 'needs_clarification', 'unblock')


def _paths():
    """Shortest trigger path from CREATED to every mission state. `redispatch`
    is left out of the search: it is legal only when the mission was held
    with a plan in force, and the shortest route to RESUMED holds it before one."""
    edges = [(f, to, t) for f, to, t, _g in states.edges('mission')
             if t and t != 'redispatch' and f != states.START and to != states.END]
    paths, todo = {'CREATED': ()}, deque(['CREATED'])
    while todo:
        s = todo.popleft()
        for f, to, t in edges:
            if f == s and to not in paths:
                paths[to] = paths[s] + (t,)
                todo.append(to)
    paths['RESUMED'] = paths['PAUSED'] + ('resume',)
    return paths


PATHS = _paths()
EDGES = [(f, to, t) for f, to, t, _g in states.edges('mission')
         if t and f != states.START and to != states.END]
TRIGGERS = sorted({t for _f, _to, t in EDGES})


def test_advance_holds_no_legality_of_its_own():
    """Every exit `advance` may take is a guarded edge, and none of them lands
    in EXECUTING or COMPLETED: advancing chooses an order, it never licenses."""
    for state, triggers in commands.DECISIONS.items():
        for t in triggers:
            to, g = lifecycle.resolve('mission', state, t)
            assert g == t and ('mission', t) in guards.GUARDS, (state, t)
            assert to not in ('EXECUTING', 'COMPLETED'), (state, t)


def test_every_mission_state_is_reachable():
    assert set(PATHS) == set(states.states('mission'))


def _at(run, facts, new_mission, state):
    m = new_mission()
    for trig in PATHS[state]:
        _fire(run, facts, m['id'], trig)
    return m['id']


# ── generated: every edge taken, every non-edge refused, on the database ──

@pytest.mark.parametrize('frm, to, trigger', EDGES, ids=['%s-%s' % (e[0], e[2]) for e in EDGES])
def test_every_mission_edge_is_taken_through_the_writer(db, run, facts, new_mission,
                                                        frm, to, trigger):
    mid = _at(run, facts, new_mission, frm)
    assert _state(db, mid)[0] == frm
    before = _state(db, mid)[1]
    if frm == 'REPLANNING' and trigger in commands.PLAN_DECISIONS:
        # the plan in force was decided on the way here: decide a replacement
        facts.now = dataclasses.replace(PASSING[trigger], plan_version=2)
        got = run('fire', mid, trigger=trigger, reason='test: %s' % trigger)
    else:
        got = _fire(run, facts, mid, trigger)
    assert (got['state'], got['version']) == (to, before + 1)
    last = _changes(db, mid)[-1]
    assert (last['from'], last['to'], last['trigger']) == (frm, to, trigger)
    if (('mission', trigger)) in guards.GUARDS:
        assert last['guard']['name'] == trigger
    else:
        assert 'guard' not in last


@pytest.mark.parametrize('state', sorted(PATHS))
def test_every_non_edge_is_refused_and_changes_nothing(db, run, facts, new_mission, state):
    mid = _at(run, facts, new_mission, state)
    legal = {t for f, _to, t in EDGES if f == state}
    before = _snapshot(db, mid)
    for trig in TRIGGERS:
        if trig in legal:
            continue
        with pytest.raises(lifecycle.IllegalTrigger) as err:
            _fire(run, facts, mid, trig)
        assert (err.value.machine, err.value.frm, err.value.trigger) == ('mission', state, trig)
    assert _snapshot(db, mid) == before


# ── guards ──

@pytest.mark.parametrize('trigger', sorted(t for m, t in guards.GUARDS if m == 'mission'))
def test_a_failed_guard_is_not_an_invalid_transition_and_writes_nothing(
        db, run, facts, new_mission, trigger):
    frm = next(f for f, _to, t in EDGES if t == trigger)
    if trigger == 'redispatch':                       # it reads held_from: hold before a plan
        mid = new_mission()['id']
        for t in PRE_PLAN_RESUMED:
            _fire(run, facts, mid, t)
    else:
        mid = _at(run, facts, new_mission, frm)
    before = _snapshot(db, mid)
    facts.now = MissionFacts()                        # the world allows nothing
    engine = Ref('system', ids.new_id('principal'))   # not a user: declares nothing
    with pytest.raises(lifecycle.GuardFailed) as err:
        run('fire', mid, trigger=trigger, reason='try', who=engine)
    assert not isinstance(err.value, writer.InvalidTransition)
    assert (err.value.machine, err.value.frm, err.value.trigger) == ('mission', frm, trigger)
    assert err.value.result.guard == trigger and not err.value.result.passed
    assert err.value.result.reason
    assert _snapshot(db, mid) == before               # no row, no event, no version, no key


def test_the_snapshot_is_gathered_only_for_a_guarded_edge(run, facts, new_mission):
    mid = new_mission()['id']
    _fire(run, facts, mid, 'start')
    assert facts.calls == 0
    for t in ('understood', 'context_ready', 'reasoned', 'plan_auto_approved'):
        _fire(run, facts, mid, t)
    assert facts.calls == 1


def _guarded_at(db, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'PLANNING')
    return mid, _state(db, mid)[1]


def _primitive(tx, *, actor, mission_id, proof):
    row, _e = tx.transition(entities.Mission, mission_id, 'APPROVED', actor=actor,
                            reason='bypass', proof=proof)
    return row.version


def _proof(mid, v, **kw):
    base = dict(entity_id=mid, version=v, frm='PLANNING', to='APPROVED',
                trigger='plan_auto_approved', guard='plan_auto_approved', guard_reason='r')
    return TransitionProof(**dict(base, **kw))


@pytest.mark.parametrize('forge, why', [
    (lambda mid, v: None, 'needs a transition proof'),
    (lambda mid, v: _proof(mid, v, guard=None), 'another edge'),        # "unguarded"
    (lambda mid, v: _proof(mid, v, guard='all_tasks_done'), 'another edge'),
    (lambda mid, v: _proof(mid, v, trigger='approve'), 'another edge'),
    (lambda mid, v: _proof(ids.new_id('mission'), v), 'another edge'),  # another row
    (lambda mid, v: _proof(mid, v - 1), 'another edge'),                # stale
    (lambda mid, v: _proof(mid, v, frm='REPLANNING'), 'another edge'),
    (lambda mid, v: _proof(mid, v, to='APPROVAL_REQUIRED'), 'another edge'),
    (lambda mid, v: {'guard': 'plan_auto_approved', 'passed': True}, 'not a TransitionProof'),
])
def test_the_primitive_cannot_be_talked_past_a_guard(db, actor, run, facts, new_mission,
                                                     forge, why):
    mid, v = _guarded_at(db, run, facts, new_mission)
    before = _snapshot(db, mid)
    with pytest.raises(writer.InvalidTransition, match=why):
        db.writer.execute(_primitive, {'actor': actor, 'mission_id': mid,
                                       'proof': forge(mid, v)})
    assert _snapshot(db, mid) == before


def test_a_matching_proof_is_what_the_primitive_takes(db, actor, run, facts, new_mission):
    mid, v = _guarded_at(db, run, facts, new_mission)
    assert db.writer.execute(_primitive, {'actor': actor, 'mission_id': mid,
                                          'proof': _proof(mid, v)}) == v + 1


def test_a_guard_is_judged_on_the_version_it_lets_through(db, actor, run, facts, new_mission):
    """No time-of-check/time-of-use gap: a proof from before a change is refused."""
    mid, v = _guarded_at(db, run, facts, new_mission)

    def stale_then_move(tx, *, actor, mission_id):
        proof = _proof(mission_id, tx.get(entities.Mission, mission_id).version)
        v = tx.get(entities.Mission, mission_id).version
        tx.transition(entities.Mission, mission_id, 'APPROVAL_REQUIRED', actor=actor,
                      reason='someone else moved first',
                      proof=_proof(mission_id, v, to='APPROVAL_REQUIRED',
                                   trigger='plan_needs_approval', guard='plan_needs_approval'))
        tx.transition(entities.Mission, mission_id, 'PLANNING', actor=actor, reason='back')
        tx.transition(entities.Mission, mission_id, 'APPROVED', actor=actor, reason='stale',
                      proof=proof)
    before = _snapshot(db, mid)
    with pytest.raises(writer.InvalidTransition, match='version %d' % (v + 2)):
        db.writer.execute(stale_then_move, {'actor': actor, 'mission_id': mid})
    assert _snapshot(db, mid) == before                # the two earlier moves rolled back too


def test_fields_ride_the_move_but_never_set_the_state(db, actor, run, facts, new_mission):
    mid = new_mission()['id']

    def sneak(tx, *, actor, mission_id):
        tx.transition(entities.Mission, mission_id, 'UNDERSTANDING', actor=actor, reason='r',
                      fields={'state': 'COMPLETED'})
    before = _snapshot(db, mid)
    with pytest.raises(ValueError, match='state'):
        db.writer.execute(sneak, {'actor': actor, 'mission_id': mid})

    def bad_value(tx, *, actor, mission_id):
        tx.transition(entities.Mission, mission_id, 'UNDERSTANDING', actor=actor, reason='r',
                      fields={'held_from': 'NOWHERE'})
    with pytest.raises(ValueError, match='held_from'):
        db.writer.execute(bad_value, {'actor': actor, 'mission_id': mid})
    assert _snapshot(db, mid) == before


# ── the P2/P3 boundary ──

def test_persistence_knows_the_table_never_a_guard_or_a_mission():
    """infra/ checks a generic TransitionProof against the P1 table; guard
    semantics and mission behaviour live in core/, and infra/ imports neither."""
    import ast
    import os
    infra = os.path.dirname(os.path.dirname(writer.__file__))
    names = {t for _m, t in guards.GUARDS}
    mission_words = set(states.states('mission')) - {'FAILED', 'PAUSED', 'BLOCKED',
                                                     'CANCELLED', 'RUNNING', 'PENDING'}
    for root, _dirs, files in os.walk(infra):
        for name in files:
            if not name.endswith('.py'):
                continue
            path = os.path.join(root, name)
            src = open(path, encoding='utf-8').read()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert 'guards' not in node.module and 'application' not in node.module, \
                        (path, node.module)
                    assert not any(a.name in ('guards', 'lifecycle', 'commands')
                                   for a in node.names), path
            code = '\n'.join(ln for ln in src.splitlines()
                             if not ln.lstrip().startswith(('#', '"', "'")))
            for word in names | mission_words:
                assert "'%s'" % word not in code, (path, word)


# ── versions and races ──

def test_a_stale_expected_version_is_refused_before_the_guard_runs(db, run, facts, new_mission):
    mid, v = _guarded_at(db, run, facts, new_mission)
    facts.now = PASSING['plan_auto_approved']
    with pytest.raises(writer.VersionConflict) as err:
        run('fire', mid, trigger='plan_auto_approved', reason='r', expected_version=v - 1)
    assert (err.value.expected, err.value.current) == (v - 1, v)
    assert facts.calls == 0 and _state(db, mid) == ('PLANNING', v)


@pytest.mark.parametrize('verb', ['pause', 'advance'])
def test_racing_actions_produce_one_winner_and_lose_no_update(db, run, facts, new_mission,
                                                              verb):
    mid = _at(run, facts, new_mission, 'EXECUTING')
    facts.now = PASSING['all_tasks_done']
    v = _state(db, mid)[1]
    gate, results = threading.Barrier(8), []

    def racer():
        gate.wait()
        try:
            results.append(run(verb, mid, expected_version=v))
        except writer.VersionConflict as e:
            results.append(e)
    ts = [threading.Thread(target=racer) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    wins = [r for r in results if isinstance(r, dict)]
    assert len(wins) == 1 and wins[0]['version'] == v + 1
    assert all(isinstance(r, writer.VersionConflict) for r in results if r not in wins)
    assert len(_changes(db, mid)) == len(PATHS['EXECUTING']) + 1


# ── actors and reasons ──

def test_the_actor_is_a_principal(db, run, facts, new_mission):
    mid = new_mission()['id']
    before = _snapshot(db, mid)
    with pytest.raises(ValueError, match='principal id'):
        run('fire', mid, trigger='start', reason='r',
            who=Ref('execution', ids.new_id('execution')))
    assert _snapshot(db, mid) == before
    run('fire', mid, trigger='start', reason='r')
    with db.read() as r:
        e = outbox.events_after(r, 0)[-1]
    assert e.type == 'mission.state_changed' and e.actor.id.startswith('prn_')


@pytest.mark.parametrize('reason', ['', '   ', None])
def test_a_transition_needs_a_reason_and_keeps_it(db, run, facts, new_mission, reason):
    mid = new_mission()['id']
    with pytest.raises(ValueError, match='reason'):
        run('fire', mid, trigger='start', reason=reason)
    run('fire', mid, trigger='start', reason='the user said go')
    assert _changes(db, mid)[-1]['reason'] == 'the user said go'


def test_an_unexplained_action_is_refused_before_anything_is_asked(db, run, facts, new_mission):
    """No snapshot is gathered and no policy consulted for a request without a reason."""
    mid = _at(run, facts, new_mission, 'PLANNING')
    facts.calls = 0
    with pytest.raises(ValueError, match='reason'):
        run('fire', mid, trigger='plan_auto_approved', reason=' ')
    assert facts.calls == 0


# ── the lifecycle ──

def test_the_normal_lifecycle_runs_to_completed_only_through_verification_and_review(
        db, run, facts, new_mission):
    mid = new_mission()['id']
    for t in ('start', 'understood', 'context_ready', 'reasoned'):
        _fire(run, facts, mid, t)
    facts.now = PASSING['plan_auto_approved']
    assert run('advance', mid)['state'] == 'APPROVED'
    _fire(run, facts, mid, 'dispatch')
    facts.now = MissionFacts(plan_version=1, tasks=(TaskFact('t1', 'code_change', 'RUNNING'),))
    stay = run('advance', mid)
    assert stay['state'] == 'EXECUTING' and stay['transitions'] == []
    facts.now = PASSING['all_tasks_done']
    assert run('advance', mid)['state'] == 'VERIFYING'
    facts.now = MissionFacts(criteria=(CriterionFact(A, 'PASSED'),))
    assert run('advance', mid)['state'] == 'REVIEWING'
    with pytest.raises(lifecycle.GuardFailed, match='no accepting review'):
        run('accept', mid)                            # verified is not reviewed
    facts.now = MissionFacts(review='REJECTED')
    with pytest.raises(lifecycle.GuardFailed, match='the latest is REJECTED'):
        run('accept', mid)
    facts.now = PASSING['accepted']
    done = run('accept', mid)
    assert done['state'] == 'COMPLETED'
    trail = [(c['from'], c['trigger']) for c in _changes(db, mid)]
    assert trail[-4:] == [('APPROVED', 'dispatch'), ('EXECUTING', 'all_tasks_done'),
                          ('VERIFYING', 'verified'), ('REVIEWING', 'accepted')]


@pytest.mark.parametrize('trigger', ['accepted', 'verified', 'all_tasks_done'])
def test_execution_success_alone_never_completes_a_mission(db, run, facts, new_mission,
                                                          trigger):
    mid = _at(run, facts, new_mission, 'EXECUTING')
    before = _snapshot(db, mid)
    facts.now = MissionFacts()                  # nothing reported yet but "it ran"
    with pytest.raises((lifecycle.IllegalTrigger, lifecycle.GuardFailed)):
        run('fire', mid, trigger=trigger, reason='the agent says it is done')
    assert _snapshot(db, mid) == before


def test_verification_is_not_review(db, run, facts, new_mission):
    """VERIFYING -> REVIEWING needs every automatic criterion PASSED; REVIEWING
    -> COMPLETED needs an accept. Neither stands in for the other."""
    mid = _at(run, facts, new_mission, 'VERIFYING')
    with pytest.raises(lifecycle.IllegalTrigger):
        run('accept', mid)
    facts.now = PASSING['verified']
    assert run('advance', mid)['state'] == 'REVIEWING'
    assert run('request_changes', mid, reason='not what I asked')['state'] == 'REPLANNING'


def test_on_the_persisted_snapshot_nothing_passes_a_plan_guard(db, actor, new_mission):
    """With no plan persisted, both plan decisions refuse (fail closed): the
    mission stays in PLANNING — it is not sent for approval of nothing."""
    live = commands.Missions(policy=ports.AllowAllPolicy())
    mid = new_mission()['id']
    for t in ('start', 'understood', 'context_ready', 'reasoned'):
        db.writer.execute(live.fire, {'actor': actor, 'mission_id': mid, 'trigger': t,
                                      'reason': 'r'})
    got = db.writer.execute(live.advance, {'actor': actor, 'mission_id': mid})
    assert (got['state'], got['changed']) == ('PLANNING', False)
    assert got['considered'] == [
        {'trigger': t, 'taken': False, 'reason': 'no active plan with tasks'}
        for t in ('plan_auto_approved', 'plan_needs_approval')]


def test_pause_and_resume_return_to_execution(db, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'EXECUTING')
    assert run('pause', mid)['state'] == 'PAUSED'
    got = run('resume', mid)
    assert got['state'] == 'EXECUTING'
    assert [t['trigger'] for t in got['transitions']] == ['resume', 'redispatch']


@pytest.mark.parametrize('held, block, back', [
    ('UNDERSTANDING', 'needs_clarification', 'UNDERSTANDING'),
    ('REASONING', 'challenge_raised', 'UNDERSTANDING'),
    ('EXECUTING', 'block', 'EXECUTING'),
    ('VERIFYING', 'awaiting_human_acceptance', 'EXECUTING'),
    ('REPLANNING', 'replan_budget_exhausted', 'UNDERSTANDING'),
])
def test_unblocking_returns_to_where_a_plan_was_in_force(db, run, facts, new_mission,
                                                         held, block, back):
    mid = _at(run, facts, new_mission, held)
    _fire(run, facts, mid, block)
    assert _state(db, mid)[0] == 'BLOCKED'
    got = run('resume', mid)
    assert got['state'] == back
    assert got['transitions'][0]['trigger'] == 'unblock'


def test_resume_is_refused_where_nothing_is_held(db, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'EXECUTING')
    before = _snapshot(db, mid)
    with pytest.raises(lifecycle.IllegalTrigger) as err:
        run('resume', mid)
    assert (err.value.frm, err.value.to) == ('EXECUTING', 'RESUMED')
    assert _snapshot(db, mid) == before


def test_a_failure_replans_and_the_budget_blocks(db, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'EXECUTING')
    facts.now = PASSING['task_failed_retryable']
    assert run('advance', mid)['state'] == 'REPLANNING'
    facts.now = MissionFacts(**dict(PLAN, plan_version=2))        # one replan used
    assert run('advance', mid)['state'] == 'APPROVED'
    _fire(run, facts, mid, 'dispatch')
    facts.now = PASSING['unrecoverable']
    assert run('advance', mid)['state'] == 'FAILED'
    _fire(run, facts, mid, 'replan')
    facts.now = MissionFacts(**dict(PLAN, plan_version=3))        # budget spent
    got = run('advance', mid)
    assert got['state'] == 'BLOCKED'
    assert got['considered'][0]['trigger'] == 'replan_budget_exhausted'


def test_verification_outcomes_are_decided_in_order(db, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'VERIFYING')
    facts.now = MissionFacts(criteria=(CriterionFact(A, 'FAILED'), CriterionFact(H, None)))
    assert run('advance', mid)['state'] == 'REPLANNING'           # a failure first
    mid = _at(run, facts, new_mission, 'VERIFYING')
    facts.now = MissionFacts(criteria=(CriterionFact(A, 'PASSED'), CriterionFact(H, None)))
    got = run('advance', mid)
    assert got['state'] == 'BLOCKED'
    assert _changes(db, mid)[-1]['reason'] == 'waiting for your acceptance'
    mid = _at(run, facts, new_mission, 'VERIFYING')
    facts.now = MissionFacts(criteria=(CriterionFact(A, None),))
    assert run('advance', mid)['transitions'] == []               # still verifying


def test_a_user_may_declare_a_mission_failed_the_engine_may_not(db, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'EXECUTING')
    facts.now = MissionFacts()
    assert run('advance', mid)['transitions'] == []              # the engine sees no cause
    with pytest.raises(lifecycle.GuardFailed):
        run('fire', mid, trigger='unrecoverable', reason='r',
            who=Ref('brain', ids.new_id('principal')))
    got = run('fire', mid, trigger='unrecoverable', reason='I give up on this')
    assert got['state'] == 'FAILED'


@pytest.mark.parametrize('state, trigger', [
    ('CREATED', 'cancel'), ('PLANNING', 'cancel'), ('APPROVAL_REQUIRED', 'reject'),
    ('BLOCKED', 'cancel'), ('PAUSED', 'cancel'), ('FAILED', 'cancel')])
def test_cancel_takes_the_edge_into_cancelled(db, run, facts, new_mission, state, trigger):
    mid = _at(run, facts, new_mission, state)
    got = run('cancel', mid)
    assert got['state'] == 'CANCELLED' and got['transitions'][0]['trigger'] == trigger


@pytest.mark.parametrize('state', ['EXECUTING', 'VERIFYING', 'COMPLETED', 'CANCELLED'])
def test_cancel_is_refused_where_the_machine_has_no_way_to_cancelled(
        db, run, facts, new_mission, state):
    mid = _at(run, facts, new_mission, state)
    before = _snapshot(db, mid)
    with pytest.raises(lifecycle.IllegalTrigger) as err:
        run('cancel', mid)
    assert (err.value.frm, err.value.to) == (state, 'CANCELLED')
    assert _snapshot(db, mid) == before


def test_request_changes_is_the_edge_back_from_approval_or_review(db, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'APPROVAL_REQUIRED')
    assert run('request_changes', mid, reason='smaller steps')['state'] == 'PLANNING'
    with pytest.raises(lifecycle.IllegalTrigger):
        run('request_changes', mid, reason='again')


# ── the policy seam ──

def test_plan_approval_asks_the_policy_port_for_every_action_class(db, actor, facts,
                                                                    new_mission):
    spy = SpyPolicy('ALLOW')
    ms = commands.Missions(policy=spy, facts=facts)
    mid = new_mission()['id']
    for t in ('start', 'understood', 'context_ready', 'reasoned'):
        db.writer.execute(ms.fire, {'actor': actor, 'mission_id': mid, 'trigger': t,
                                    'reason': 'r'})
    facts.now = MissionFacts(plan_version=1, cost_within_ceiling=True, tasks=(
        TaskFact('a', 'code_change', 'PENDING', action_classes=('write_repo', 'exec')),
        TaskFact('b', 'research', 'PENDING', action_classes=('web',))))
    assert db.writer.execute(ms.advance, {'actor': actor, 'mission_id': mid})['state'] == \
        'APPROVED'
    assert sorted(spy.asked) == sorted([('write_repo', 'task:a', mid), ('exec', 'task:a', mid),
                                        ('web', 'task:b', mid)])


@pytest.mark.parametrize('decision, state', [('ASK', 'APPROVAL_REQUIRED'),
                                             ('DENY', 'PLANNING')])
def test_ask_sends_the_plan_for_approval_and_deny_does_not(db, actor, facts,
                                                           new_mission, decision, state):
    """ASK is a question for a human; DENY is not (P3.5 checkpoint decision):
    a denied plan never becomes an approval request and the mission stays put."""
    ms = commands.Missions(policy=SpyPolicy(decision), facts=facts)
    mid = new_mission()['id']
    for t in ('start', 'understood', 'context_ready', 'reasoned'):
        db.writer.execute(ms.fire, {'actor': actor, 'mission_id': mid, 'trigger': t,
                                    'reason': 'r'})
    facts.now = PASSING['plan_auto_approved']
    before = _snapshot(db, mid)
    with pytest.raises(lifecycle.GuardFailed, match=decision):
        db.writer.execute(ms.fire, {'actor': actor, 'mission_id': mid,
                                    'trigger': 'plan_auto_approved', 'reason': 'r'})
    assert _snapshot(db, mid) == before
    got = db.writer.execute(ms.advance, {'actor': actor, 'mission_id': mid})
    assert got['state'] == state
    if decision == 'DENY':
        assert not got['changed'] and _snapshot(db, mid) == before
        assert got['considered'][-1] == {
            'trigger': 'plan_needs_approval', 'taken': False,
            'reason': 'policy denies write_repo on task t1: not a question for approval'}
        # fired by name the edge refuses too: the guard, not the orchestration, says no
        with pytest.raises(lifecycle.GuardFailed, match='not a question for approval'):
            db.writer.execute(ms.fire, {'actor': actor, 'mission_id': mid,
                                        'trigger': 'plan_needs_approval', 'reason': 'r'})
        assert _snapshot(db, mid) == before
    else:                   # sent back: the same plan (v1) is never decided again
        db.writer.execute(ms.fire, {'actor': actor, 'mission_id': mid,
                                    'trigger': 'request_changes', 'reason': 'r'})
        back = db.writer.execute(ms.advance, {'actor': actor, 'mission_id': mid})
        assert (back['state'], back['changed']) == ('PLANNING', False)
        assert all('already decided' in c['reason'] for c in back['considered'])
        facts.now = MissionFacts(**dict(PLAN, plan_version=2))       # a new proposal
        assert db.writer.execute(ms.advance, {'actor': actor, 'mission_id': mid})['state'] \
            == 'APPROVAL_REQUIRED'


def test_a_denied_action_during_execution_is_unrecoverable(db, actor, facts, new_mission):
    spy = SpyPolicy('ALLOW')
    ms = commands.Missions(policy=spy, facts=facts)
    mid = new_mission()['id']
    for t in PATHS['EXECUTING']:
        facts.now = PASSING.get(t, facts.now)
        db.writer.execute(ms.fire, {'actor': actor, 'mission_id': mid, 'trigger': t,
                                    'reason': 'r'})
    spy.decision = 'DENY'                             # the policy changed mid-mission
    facts.now = MissionFacts(**PLAN)
    got = db.writer.execute(ms.advance, {'actor': actor, 'mission_id': mid})
    assert got['state'] == 'FAILED'
    assert 'policy denies write_repo' in got['considered'][0]['reason']


# ── resume reads current state, never history ──

def _prune_everything(db):
    from datetime import datetime, timedelta, timezone
    later = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    return db.writer.execute(retention.prune, {'now': later.replace('+00:00', 'Z')})


@pytest.mark.parametrize('held, hold, back', [('EXECUTING', 'pause', 'EXECUTING'),
                                              ('UNDERSTANDING', 'needs_clarification',
                                               'UNDERSTANDING')])
def test_event_retention_cannot_change_where_resume_goes(db, run, facts, new_mission,
                                                         held, hold, back):
    mid = _at(run, facts, new_mission, held)
    _fire(run, facts, mid, hold)
    with db.read() as r:
        assert rows.get(r, entities.Mission, mid).entity.held_from == held
    assert _prune_everything(db)['events'] > 0
    with db.read() as r:                             # the history of the hold is gone
        assert [e for e in outbox.events_after(r, outbox.floor(r), limit=1000)
                if e.subject.id == mid] == []
    got = run('resume', mid)
    assert got['state'] == back
    with db.read() as r:
        assert rows.get(r, entities.Mission, mid).entity.held_from is None   # spent


def test_held_from_agrees_with_the_history_that_recorded_it(db, run, facts, new_mission):
    """Replaying the log gives the same answer the row holds."""
    for held, hold in (('EXECUTING', 'block'), ('REASONING', 'challenge_raised'),
                       ('VERIFYING', 'awaiting_human_acceptance')):
        mid = _at(run, facts, new_mission, held)
        _fire(run, facts, mid, hold)
        with db.read() as r:
            row = rows.get(r, entities.Mission, mid)
        assert row.entity.held_from == _changes(db, mid)[-1]['from'] == held


def test_a_hold_with_no_record_is_refused_not_guessed(db, actor, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'EXECUTING')

    def raw_block(tx, *, actor, mission_id):          # the P2 primitive, no provenance
        tx.transition(entities.Mission, mission_id, 'BLOCKED', actor=actor, reason='raw')
    db.writer.execute(raw_block, {'actor': actor, 'mission_id': mid})
    before = _snapshot(db, mid)
    with pytest.raises(lifecycle.IllegalTrigger, match='would guess'):
        run('resume', mid)
    assert _snapshot(db, mid) == before


# ── trigger authority: legality here, authorisation at the policy seam ──

KINDS = ('user_device', 'brain', 'execution', 'automation', 'node', 'system')


@pytest.mark.parametrize('kind', KINDS)
def test_a_legal_trigger_reaches_the_policy_seam_whoever_asks(db, facts, new_mission, kind):
    """P3 decides only whether the trigger is legal; it hardcodes no role. The
    acting principal reaches the Policy port as context, for P9 to decide."""
    spy = SpyPolicy('ALLOW')
    ms = commands.Missions(policy=spy, facts=facts)
    who = Ref(kind, ids.new_id('principal'))
    mid = new_mission()['id']
    for t in PATHS['PLANNING']:
        db.writer.execute(ms.fire, {'actor': who, 'mission_id': mid, 'trigger': t,
                                    'reason': 'r'})
    facts.now = PASSING['plan_auto_approved']
    got = db.writer.execute(ms.fire, {'actor': who, 'mission_id': mid,
                                      'trigger': 'plan_auto_approved', 'reason': 'r'})
    assert got['state'] == 'APPROVED'
    assert spy.contexts[-1]['actor'] == {'kind': kind, 'id': who.id}


@pytest.mark.parametrize('kind', KINDS)
def test_no_actor_kind_is_refused_or_privileged_by_the_state_machine(db, facts, new_mission,
                                                                      kind):
    """An execution principal asking `accepted` is legal here: whether it may
    is P9's question, not a rule hidden in P3 (state-machines §2)."""
    ms = commands.Missions(policy=ports.AllowAllPolicy(), facts=facts)
    who = Ref(kind, ids.new_id('principal'))
    mid = new_mission()['id']
    for t in PATHS['REVIEWING']:
        facts.now = PASSING.get(t, facts.now)
        db.writer.execute(ms.fire, {'actor': who, 'mission_id': mid, 'trigger': t,
                                    'reason': 'r'})
    facts.now = PASSING['accepted']
    assert db.writer.execute(ms.accept, {'actor': who, 'mission_id': mid})['state'] == \
        'COMPLETED'


def test_the_policy_port_is_the_only_policy_call(db):
    import ast
    src = open(commands.__file__, encoding='utf-8').read()
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Attribute) and n.attr == 'evaluate'
             and isinstance(n.value, ast.Attribute) and n.value.attr == 'policy']
    assert len(calls) == 1
    lsrc = open(lifecycle.__file__, encoding='utf-8').read()
    assert 'policy' not in lsrc.replace('policy (P9)', '')


# ── advance: one declared order, explicit no-ops ──

def test_advance_tries_only_legal_exits_and_every_guarded_one():
    for state, order in commands.DECISIONS.items():
        legal = {t for f, _to, t in EDGES if f == state}
        guarded = {t for t in legal if ('mission', t) in guards.GUARDS}
        assert set(order) <= legal and guarded <= set(order), state
        assert len(set(order)) == len(order)


def test_the_documented_order_is_the_declared_order():
    import os
    import re
    doc = open(os.path.join(os.path.dirname(commands.__file__), '..', '..', '..', 'docs',
                            'architecture', 'state-machines.md'), encoding='utf-8').read()
    row = next(ln for ln in doc.splitlines() if ln.startswith('| `advance` |'))
    found = {s: tuple(re.findall(r'`([a-z_]+)`', seq))
             for s, seq in re.findall(r'([A-Z_]+): ((?:`[a-z_]+`(?: \([^)]*\))?,? ?)+)', row)}
    assert found == commands.DECISIONS


def test_nothing_changed_is_explicit_and_repeatable(db, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'EXECUTING')
    facts.now = MissionFacts(plan_version=1, tasks=(TaskFact('t1', 'code_change', 'RUNNING'),))
    before = _snapshot(db, mid)
    first, second = run('advance', mid), run('advance', mid)
    assert first == second
    assert first['changed'] is False and first['transitions'] == [] and first['seq'] is None
    assert [c['taken'] for c in first['considered']] == [False, False, False]
    assert _snapshot(db, mid) == before
    for state in ('CREATED', 'APPROVED', 'COMPLETED'):             # not a decision point
        m = _at(run, facts, new_mission, state)
        got = run('advance', m)
        assert got['changed'] is False and got['considered'] == []


# ── cancel, generated over every state ──

@pytest.mark.parametrize('state', sorted(PATHS))
def test_cancel_exists_exactly_where_the_table_has_an_edge_into_cancelled(
        db, run, facts, new_mission, state):
    into = [t for f, to, t in EDGES if f == state and to == 'CANCELLED']
    mid = _at(run, facts, new_mission, state)
    before = _snapshot(db, mid)
    if into:
        got = run('cancel', mid)
        assert (got['state'], got['transitions'][0]['trigger']) == ('CANCELLED', into[0])
    else:
        with pytest.raises(lifecycle.IllegalTrigger):
            run('cancel', mid)
        assert _snapshot(db, mid) == before


# ── completion cannot be reached any other way ──

@pytest.mark.parametrize('frm', ['EXECUTING', 'VERIFYING', 'APPROVED'])
def test_no_direct_move_into_completed(db, actor, run, facts, new_mission, frm):
    mid = _at(run, facts, new_mission, frm)

    def jump(tx, *, actor, mission_id):
        tx.transition(entities.Mission, mission_id, 'COMPLETED', actor=actor, reason='jump')
    before = _snapshot(db, mid)
    with pytest.raises(writer.InvalidTransition, match='no such edge'):
        db.writer.execute(jump, {'actor': actor, 'mission_id': mid})
    with pytest.raises(lifecycle.IllegalTrigger):
        run('accept', mid)
    assert _snapshot(db, mid) == before


def test_a_stale_completion_is_a_conflict(db, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'REVIEWING')
    v = _state(db, mid)[1]
    run('request_changes', mid, reason='one more thing')      # someone else moved it
    with pytest.raises(writer.VersionConflict):
        run('accept', mid, expected_version=v)
    assert _state(db, mid)[0] == 'REPLANNING'


def test_the_only_road_to_completed_is_verified_then_accepted():
    """In the table itself: COMPLETED has one way in (REVIEWING/accepted) and
    REVIEWING has one (VERIFYING/verified, a guarded edge)."""
    into = lambda s: [(f, t) for f, to, t in EDGES if to == s]           # noqa: E731
    assert into('COMPLETED') == [('REVIEWING', 'accepted')]
    assert into('REVIEWING') == [('VERIFYING', 'verified')]
    assert ('mission', 'verified') in guards.GUARDS


# ── idempotency (P2 contract) ──

def test_a_repeated_action_returns_its_first_answer(db, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'EXECUTING')
    first = run('pause', mid, key='p1')
    before = _snapshot(db, mid)
    assert run('pause', mid, key='p1') == first
    assert _snapshot(db, mid) == before
    with pytest.raises(writer.IdempotencyConflict):
        run('resume', mid, key='p1')                      # same key, other action
    with pytest.raises(writer.IdempotencyConflict):
        run('pause', mid, key='p1', reason='different')   # same key, other arguments


def test_a_guarded_action_is_idempotent_too(db, run, facts, new_mission):
    mid = _at(run, facts, new_mission, 'PLANNING')
    facts.now = PASSING['plan_auto_approved']
    first = run('advance', mid, key='a1')
    facts.now = MissionFacts()                            # the world changed since
    assert run('advance', mid, key='a1') == first          # the stored answer, no re-judging
    assert _state(db, mid)[0] == 'APPROVED'
