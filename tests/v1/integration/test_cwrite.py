"""P21 C-write (p21-design-gate D13 (b)): a command issued from an event (an
outbox consumer's) or from an approval records that event in its own events'
`cause_chain`; a direct user command stays its own root; and (owner 2026-10-21)
the task's reply to an execution ending carries that `execution.ended`. The
cause only labels what is written: every decision below is the one it was
without it."""

import time

import pytest

from archeus.core.application import commands, lifecycle, queries
from archeus.core.application import executions as X
from archeus.core.domain import entities, ids
from archeus.core.domain import events as ev
from archeus.core.domain.values import Ref
from archeus.infra.eventlog import consumers
from v1.integration.test_intent import WORK, brain, make  # noqa: F401 (a fixture)
from v1.integration.test_policy import Rig, _dispatchable, task
from v1.integration.test_routing import Rig as RouteRig, _limited


def _events(db):
    with db.read() as c:
        return queries.events(c)


def _of(db, type_, subject_id):
    return [e for e in _events(db) if e['type'] == type_ and e['subject']['id'] == subject_id]


def _after(db, e):
    return [x for x in _events(db) if x['seq'] > e['seq']]


def _mission(db, actor, **kw):
    return db.writer.execute(commands.create_mission,
                             dict({'actor': actor, 'title': 'M', 'objective': 'o'}, **kw))['id']


def _chain(db, mid):
    (e,) = _of(db, 'mission.created', mid)
    return e['cause_chain']


def _decided(db, a, to):
    (e,) = [e for e in _of(db, 'approval.state_changed', a.id) if e['payload']['to'] == to]
    return e


# ── the writer and the consumers ──

def test_what_a_command_writes_under_a_cause_carries_it_and_a_route_command_is_a_root(db, actor):
    a, b = ids.new_ulid(), ids.new_ulid()
    root = _mission(db, actor)
    token = ev.CAUSE.set((a, b))
    try:
        caused = _mission(db, actor)
        own = _mission(db, actor, cause=(b,))              # an explicit cause wins
    finally:
        ev.CAUSE.reset(token)
    assert (_chain(db, root), _chain(db, caused), _chain(db, own)) == ([], [a, b], [b])


def test_the_cause_is_never_part_of_a_keyed_requests_hash(db, actor):
    args = {'actor': actor, 'title': 'K', 'objective': 'o'}
    first = db.writer.execute(commands.create_mission, args, idempotency_key='k-cause')
    token = ev.CAUSE.set((ids.new_ulid(),))
    try:                                  # the same request under a cause: a replay, no conflict
        again = db.writer.execute(commands.create_mission, args, idempotency_key='k-cause')
    finally:
        ev.CAUSE.reset(token)
    assert again == first and _chain(db, first['id']) == []


def test_a_chain_keeps_its_newest_sixteen():
    chain = tuple(ids.new_ulid() for _ in range(ev.MAX_CAUSE_CHAIN))
    e = ev.new_event('mission.created', Ref('mission', ids.new_id('mission')),
                     Ref('user_device', ids.new_id('principal')), cause_chain=chain)
    assert ev.caused_by(e) == chain[1:] + (e.id,)


def test_a_handler_that_raises_leaves_no_cause_behind(db, actor):
    _mission(db, actor)

    def handler(e):
        raise RuntimeError('a bug in the consumer')

    with pytest.raises(RuntimeError):
        consumers.deliver(db, 'c-write-raise', handler)
    assert ev.CAUSE.get() == () and _chain(db, _mission(db, actor)) == []


def test_a_consumer_writes_under_its_event_and_leaves_no_cause_behind(db, actor):
    trigger = _mission(db, actor)
    (t,) = _of(db, 'mission.created', trigger)
    made = []

    def handler(e):
        if e.id == t['id']:
            made.append(_mission(db, actor))
        return 'ok'

    consumers.deliver(db, 'c-write-test', handler)
    after = _mission(db, actor)
    assert (_chain(db, made[0]), _chain(db, after)) == ([t['id']], [])


def test_a_held_event_leaves_no_cause_behind(db, actor):
    _mission(db, actor)

    def handler(e):
        raise consumers.Hold()

    assert consumers.deliver(db, 'c-write-hold', handler) == 0
    assert ev.CAUSE.get() == () and _chain(db, _mission(db, actor)) == []


def test_what_intent_writes_from_a_message_is_caused_by_that_message(make):  # noqa: F811
    r = make([brain(('Add a --version flag to the CLI', WORK))])
    reply, _it = r.say('Add a --version flag to the CLI')
    (m,) = r.all(entities.Mission)
    (said,) = _of(r.db, 'message.created', reply['in_reply_to'])
    (answer,) = _of(r.db, 'message.created', reply['id'])
    assert said['cause_chain'] == []                     # the user said it: a root
    assert _chain(r.db, m.id) == [said['id']] and answer['cause_chain'] == [said['id']]


# ── approvals: what a decision issues carries the decision ──

@pytest.fixture
def r(db):
    return Rig(db)


def _asking(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    return mid, r.pending(mid)


@pytest.mark.parametrize('decision, to, mission, plan', [
    ('approve', 'APPROVED', 'APPROVED', 'APPROVED'),
    ('reject', 'REJECTED', 'CANCELLED', 'REJECTED'),
    ('request_changes', 'REJECTED', 'PLANNING', 'REJECTED')])
def test_a_plan_decision_causes_what_it_moves_and_decides_as_before(r, decision, to, mission,
                                                                     plan):
    mid, a = _asking(r)
    out = r.decide(a, decision)
    assert (out['state'], out['mission']['state'], r.one(entities.Plan).state) == (
        to, mission, plan)                               # the decision itself is unchanged
    e = _decided(r.db, a, to)
    after = _after(r.db, e)
    assert e['cause_chain'] == []                        # a user device decided: a root
    assert after and all(x['cause_chain'] == [e['id']] for x in after)


def test_a_decision_made_under_an_event_passes_that_event_on(r):
    _mid, a = _asking(r)
    x = ids.new_ulid()
    token = ev.CAUSE.set((x,))
    try:
        r.decide(a)
    finally:
        ev.CAUSE.reset(token)
    e = _decided(r.db, a, 'APPROVED')
    assert e['cause_chain'] == [x]
    assert all(y['cause_chain'] == [x, e['id']] for y in _after(r.db, e))


@pytest.mark.parametrize('decision, to, task_state', [
    ('approve', 'APPROVED', 'READY'), ('reject', 'REJECTED', 'BLOCKED')])
def test_a_fallback_routes_decision_causes_what_follows(db, decision, to, task_state):
    rr = RouteRig(db)
    _limited(rr, 'ask')
    mid = rr.ready()
    rr.dispatch(mid)
    a = rr.pending(mid)
    rr.decide(a, decision)
    assert rr.all(entities.Task, mission_id=mid)[0].state == task_state
    e = _decided(db, a, to)
    after = _after(db, e)
    assert e['cause_chain'] == [] and after and all(x['cause_chain'] == [e['id']] for x in after)


def test_a_decision_under_a_consumer_is_caused_by_that_event_and_so_is_its_reply(r):
    """A non-empty `before`: the wrapper must restore to the consumer's chain, not to ()."""
    _mid, a = _asking(r)
    x = _events(r.db)[-1]
    made = []

    def handler(e):
        if e.id == x['id']:
            made.append(r.do(r.authz.decide_by_message, who=r.user, text='approve',
                             conversation_id='primary', approval_id=a.id,
                             action_hash=a.action_hash))
        return 'ok'

    consumers.deliver(r.db, 'c-write-decide', handler)
    assert made and made[0]['decided']['state'] == 'APPROVED'
    ch = list(x['cause_chain']) + [x['id']]
    e = _decided(r.db, a, 'APPROVED')
    assert e['cause_chain'] == ch
    after = _after(r.db, e)
    (reply,) = [y for y in after if y['type'] == 'message.created'
                and y['payload']['author'] == 'archeus']
    assert reply['cause_chain'] == ch
    moved = [y for y in after if y['type'] != 'message.created']
    assert moved and all(y['cause_chain'] == ch + [e['id']] for y in moved)


def test_a_chat_approve_replies_as_a_root_while_what_it_moves_carries_the_decision(r):
    _mid, a = _asking(r)
    out = r.do(r.authz.decide_by_message, who=r.user, text='approve', conversation_id='primary',
               approval_id=a.id, action_hash=a.action_hash)
    assert out['decided']['state'] == 'APPROVED'
    e = _decided(r.db, a, 'APPROVED')
    after = _after(r.db, e)
    (reply,) = [x for x in after if x['type'] == 'message.created'
                and x['payload']['author'] == 'archeus']
    assert reply['cause_chain'] == []                    # the route command's reply: a root
    moved = [x for x in after if x['type'] != 'message.created']
    assert moved and all(x['cause_chain'] == [e['id']] for x in moved)


def test_a_refused_decision_writes_nothing_and_leaves_no_event(r):
    _mid, a = _asking(r)
    head = r.head()
    token = ev.CAUSE.set((ids.new_ulid(),))
    try:                                  # a rollback check: the hash refusal comes first
        with pytest.raises(lifecycle.GuardFailed):
            r.decide(a, h='0' * 64)
    finally:
        ev.CAUSE.reset(token)
    assert r.head() == head and r.pending(_mid).state == 'PENDING'


# ── the task's reply to an execution ending carries `execution.ended` (owner 2026-10-21) ──

FORGED = 'hook_' + 'x' * 43


def _started(r, mid):
    """Each READY task of *mid* dispatched and STARTING, with a hook token set as a spawn sets one."""
    eids = []
    for t in [t for t in r.all(entities.Task, mission_id=mid) if t.state == 'READY']:
        eid = r.do(r.work.dispatch_task, task_id=t.id)['execution_id']
        r.do(r.work.record_spawn, execution_id=eid, pid=1, create_time=1.0)

        def token(tx, actor, eid=eid):
            e = tx.get(entities.Execution, eid).entity
            tx.update(entities.Execution, eid, {'hook_token_hash': X.token_hash(FORGED)},
                      actor=actor)
            X._event(tx, 'execution.hook', e, actor, {'seq': 0, 'decision': 'test', 'reason': ''})
        r.do(token)
        eids.append(eid)
    return eids


@pytest.mark.parametrize('exit_reason, task_state', [('ok', 'VERIFYING'), ('error', 'READY')])
def test_the_tasks_reply_to_an_end_carries_it_and_the_token_is_still_cleared(r, exit_reason,
                                                                            task_state):
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'))
    _dispatchable(r, mid)
    (eid,) = _started(r, mid)
    assert r.one(entities.Execution).hook_token_hash == X.token_hash(FORGED)
    r.do(r.work.record_exit, execution_id=eid, exit_reason=exit_reason, exit_code=None)
    assert r.one(entities.Execution).hook_token_hash is None      # cleared, exactly as before
    assert r.one(entities.Task).state == task_state
    (ended,) = _of(r.db, 'execution.ended', eid)
    after = _after(r.db, ended)
    assert ended['cause_chain'] == []                  # Core recorded what it observed: a root
    assert [x['type'] for x in after] == ['task.state_changed']
    assert after[0]['cause_chain'] == [ended['id']]


def test_one_command_ending_two_executions_keeps_each_reply_to_its_own_end(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'), task('t2', 'write_repo'))
    _dispatchable(r, mid)
    eids = _started(r, mid)
    assert len(eids) == 2

    def both_lost(tx, actor):
        for eid in eids:
            X.lost(tx, actor=actor, execution_id=eid, reason='the process is gone')
    r.do(both_lost)
    task_of = {e.id: e.task_id for e in r.all(entities.Execution)}
    for eid in eids:
        (ended,) = _of(r.db, 'execution.ended', eid)
        reply = next(x for x in _after(r.db, ended) if x['type'] == 'task.state_changed')
        assert reply['subject']['id'] == task_of[eid]
        assert (ended['cause_chain'], reply['cause_chain']) == ([], [ended['id']])


# ── every end site of the task's reply: refuse, record_handoff, approval_answered, and
# ── the restore between the ends one command makes (estop, stop_mission)

def _to(r, eid, *triggers):
    """Move execution *eid* along *triggers*, one transition each (the manager's path)."""
    def step(tx, actor):
        for t in triggers:
            X._fire(tx, eid, t, actor, 'test')
    r.do(step)


def _task_reply(db, ended, task_id):
    return next(x for x in _after(db, ended)
                if x['type'] == 'task.state_changed' and x['subject']['id'] == task_id)


def _task_of(r):
    return {e.id: e.task_id for e in r.all(entities.Execution)}


def test_a_mission_stop_ends_each_paused_execution_and_each_reply_carries_its_own_end(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'), task('t2', 'write_repo'))
    _dispatchable(r, mid)
    eids = _started(r, mid)
    for eid in eids:
        _to(r, eid, 'first_output', 'pause_requested', 'halted_at_boundary')
    out = r.do(X.Executions(missions=r.missions).stop_mission, who=r.user, mission_id=mid)
    assert sorted(out['stopped']) == sorted(eids)
    task_of = _task_of(r)
    ends = {eid: _of(r.db, 'execution.ended', eid)[0] for eid in eids}
    for eid, ended in ends.items():
        assert ended['cause_chain'] == []                # the user's stop: a root
        assert _task_reply(r.db, ended, task_of[eid])['cause_chain'] == [ended['id']]
    (blocked,) = [x for x in _of(r.db, 'mission.state_changed', mid)
                  if x['payload']['to'] == 'BLOCKED']
    last = max(ends.values(), key=lambda x: x['seq'])
    assert blocked['seq'] > last['seq'] and blocked['cause_chain'] == []


def test_an_estop_ends_a_paused_execution_and_the_estop_record_stays_a_root(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'), task('t2', 'write_repo'))
    _dispatchable(r, mid)
    live, paused = _started(r, mid)
    _to(r, live, 'first_output')
    _to(r, paused, 'first_output', 'pause_requested', 'halted_at_boundary')
    out = r.do(X.Executions(missions=r.missions).estop, who=r.user)
    assert sorted(out['stopped']) == sorted([live, paused])
    (ended,) = _of(r.db, 'execution.ended', paused)
    assert ended['cause_chain'] == []
    assert _task_reply(r.db, ended, _task_of(r)[paused])['cause_chain'] == [ended['id']]
    (estopped,) = [e for e in _events(r.db) if e['type'] == 'core.estopped']
    assert estopped['cause_chain'] == []                 # written after that end: no end's cause


def test_a_rejected_action_approval_ends_its_execution_and_the_reply_carries_that_end(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'))
    _dispatchable(r, mid)
    (eid,) = _started(r, mid)
    _to(r, eid, 'first_output')
    push = {'action_class': 'git_push', 'target': 'origin/main',
            'argv': ['git', 'push', 'origin', 'main']}
    asked = r.do(r.authz.evaluate_action, execution_id=eid, action=push)
    assert asked['decision'] == 'ASK'
    _to(r, eid, 'hook_asked')
    r.decide(r.one(entities.Approval, id=asked['approval_id']), 'reject')
    r.do(X.approval_answered, execution_id=eid)
    (ended,) = _of(r.db, 'execution.ended', eid)
    after = _after(r.db, ended)
    assert ended['cause_chain'] == [] and after
    assert all(x['cause_chain'] == [ended['id']] for x in after)


def _handing_off(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'))
    _dispatchable(r, mid)
    (eid,) = _started(r, mid)
    _to(r, eid, 'first_output')
    r.do(X.request_handoff, execution_id=eid, stop_reason='pressure', reason='context is full')
    return eid


def _hand_off(r, eid):
    return r.do(X.record_handoff, policy=r.policy, missions=r.missions, router=r.work.router,
                execution_id=eid, now=time.time())


def test_a_hand_off_s_continuation_is_caused_by_the_hand_off_end(r):
    eid = _handing_off(r)
    out = _hand_off(r, eid)
    assert out['continuation'] is not None
    (ended,) = _of(r.db, 'execution.ended', eid)
    after = _after(r.db, ended)
    assert ended['cause_chain'] == [] and after
    assert all(x['cause_chain'] == [ended['id']] for x in after)


def test_a_refused_hand_off_charges_the_task_under_its_end(r):
    eid = _handing_off(r)

    def seeded(tx, actor):                # a seeded execution: its clean end owes an import
        tx.update(entities.Execution, eid, {'seed_revision': 'a' * 40}, actor=actor)
        X._event(tx, 'execution.hook', tx.get(entities.Execution, eid).entity, actor,
                 {'seq': 0, 'decision': 'test', 'reason': ''})
    r.do(seeded)
    out = _hand_off(r, eid)
    assert out['continuation'] is None and out['refused']      # seeded, no import: refused
    (ended,) = _of(r.db, 'execution.ended', eid)
    after = _after(r.db, ended)
    assert ended['cause_chain'] == [] and after
    assert all(x['cause_chain'] == [ended['id']] for x in after)


def test_a_blocking_refusal_blocks_its_mission_under_its_end(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'))
    _dispatchable(r, mid)
    (eid,) = _started(r, mid)
    _to(r, eid, 'first_output', 'pause_requested', 'halted_at_boundary')
    r.do(X.refuse, execution_id=eid, reason='the path is too long',
         stop_reason='path_too_long', missions=r.missions)
    (ended,) = _of(r.db, 'execution.ended', eid)
    after = _after(r.db, ended)
    (blocked,) = [x for x in after if x['type'] == 'mission.state_changed'
                  and x['payload']['to'] == 'BLOCKED']
    assert ended['cause_chain'] == [] and blocked['cause_chain'] == [ended['id']]
    assert all(x['cause_chain'] == [ended['id']] for x in after)
