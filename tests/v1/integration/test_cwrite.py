"""P21 C-write (p21-design-gate D13 (b)): a command issued from an event (an
outbox consumer's) or from an approval records that event in its own events'
`cause_chain`; a direct user command stays its own root. The cause only labels
what is written: every decision below is the one it was without it."""

import pytest

from archeus.core.application import commands, queries
from archeus.core.domain import entities, ids
from archeus.core.domain import events as ev
from archeus.core.domain.values import Ref
from archeus.infra.eventlog import consumers
from v1.integration.test_intent import WORK, brain, make  # noqa: F401 (a fixture)
from v1.integration.test_policy import Rig, task
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


def test_a_refused_decision_writes_nothing_under_a_cause_either(r):
    _mid, a = _asking(r)
    head = r.head()
    token = ev.CAUSE.set((ids.new_ulid(),))
    try:
        with pytest.raises(Exception):
            r.decide(a, h='0' * 64)
    finally:
        ev.CAUSE.reset(token)
    assert r.head() == head and r.pending(_mid).state == 'PENDING'
