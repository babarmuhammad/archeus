"""T-742: the highest-risk uncovered branches of
`archeus/core/application/planning.py` — the four planning commands driven
directly over a real database, fail-closed first.

The module's existing tests reach it only through the planning worker
(tests/v1/integration/test_planning.py); the closest unit tests
(tests/v1/unit/test_planning_units.py) judge the plan engine, not these
commands. What no test drove until now is the commands' own refusal behaviour:
what `apply`, `hold`, `deny` and `note` must do when the round went stale,
when the same round is replayed, when the policy stopped denying, when the
mission moved on — and that each refusal still ends the call and writes
nothing else. The style and fixtures follow the sibling database-driven unit
tests (tests/v1/unit/test_gaps_core_application_verification.py,
test_gaps_core_application_resources.py): Database.open() under the test's own
ARCHEUS_HOME, one writer command per call, the real `Missions` and `Work` over
the Policy-port stub, nothing spawned, no network, no sleep, no OS call beyond
the database file in the test's temp directory. Nothing here is Windows-
specific or POSIX-specific; ids are Core's own, no path is written by hand.

The ten branches, with the test that now covers each, are listed in
/work/QWEN-DONE-T-742.md.
"""

import json

import pytest

from archeus.core import ports
from archeus.core.application import commands, lifecycle
from archeus.core.application import planning as PL
from archeus.core.application import work as W
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows

OK = ({'text': 'it works', 'check': 'automatic'},)


def who(kind='system'):
    """A principal of *kind*: what a caller claims to be (the commands do not
    judge their actor — the routes above them do)."""
    return Ref(kind, ids.new_id('principal'))


def task(key='t1', **kw):
    """One valid task spec, in the shape `planner.resolve` hands the commands
    (test_planning_units.py's t())."""
    return dict({'key': key, 'title': 'T %s' % key, 'objective': 'do %s' % key,
                 'kind': 'code_change', 'depends_on': (), 'action_classes': ('write_repo',),
                 'acceptance': OK}, **kw)


def proposal(*tasks, **kw):
    return dict({'spec': {'summary': 'a plan', 'tasks': list(tasks) or [task()]},
                 'explicit': (), 'asked': ()}, **kw)


def planning(policy='ALLOW'):
    """The real P3.5 `Work` over the real `Missions` and the Policy-port stub:
    an approval or a denial proven here is a real edge of P3's machine."""
    ms = commands.Missions(policy=ports.FixedPolicy(policy))
    return PL.Planning(work=W.Work(missions=ms, router=ports.FixedCandidateRouter('fake')))


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    try:
        yield d
    finally:
        d.close()


# ── seeding: one transaction each; no command, no call, no process ──────────

def _seed(db, actor, state='PLANNING', **over):
    """One mission in *state* (an insert sets it; no move is taken here), with
    one automatic success criterion so the plan gate has something to decide."""
    m = dict(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
             title='Ship it', objective='Ship the thing.', state=state,
             origin='api', success_criteria=OK)
    m.update(over or {})

    def run(tx, **_):
        tx.insert(entities.Mission(**m), actor=actor)
        tx.append(new_event('mission.created', Ref('mission', m['id']), actor,
                            payload={'fields': []}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return m['id']


def _package(db, actor, mid):
    """The context package the round read, current as of every event that
    exists when it is seeded (planner.currency judges events after its
    `as_of_seq`)."""
    pkg = ids.new_id('context_package')
    with db.read() as c:
        head = c.execute('SELECT COALESCE(MAX(seq), 0) FROM events').fetchone()[0]

    def run(tx, **_):
        tx.insert(entities.ContextPackage(id=pkg, workspace_id=ids.GLOBAL_WORKSPACE,
                                          subject_kind='mission', subject_id=mid,
                                          as_of_seq=head), actor=actor)
        tx.append(new_event('context_package.created', Ref('context_package', pkg), actor,
                            payload={'subject': {'kind': 'mission', 'id': mid}, 'items': 0},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return pkg


def _stale_package(db, actor, mid, pkg):
    """What the runtime records between the call and its end while the round
    is still open: the mission's requirements moved after the package was
    assembled — exactly what `planner.currency` reads the package stale from."""
    def run(tx, **_):
        m = tx.get(entities.Mission, mid).entity
        req = ({'text': 'also print the hash', 'origin': 'explicit'},)
        tx.update(entities.Mission, mid, {'requirements': m.requirements + req}, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', mid), actor, payload={
            'fields': ['requirements'], 'added': {'requirements': list(req)}},
            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})


def _plan_of_round(db, actor, mid, round_seq):
    """A version this round already recorded (what the UNIQUE (mission_id,
    round_seq) stands for): the replay a command must refuse."""
    pid = ids.new_id('plan')

    def run(tx, **_):
        tx.insert(entities.Plan(id=pid, mission_id=mid, plan_version=1,
                                round_seq=round_seq, state='PROPOSED'), actor=actor)
        tx.append(new_event('plan.created', Ref('plan', pid), actor,
                            payload={'round_seq': round_seq}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return pid


def _call(db, actor, mid, pkg, usage=None):
    """The round's open call (its RouteDecision committed before the adapter
    ran, ADR-0022) and the `called` the worker hands the command."""
    rd = entities.RouteDecision(
        id=ids.new_id('route_decision'), subject=Ref('archeus_call', ids.new_id('route_decision')),
        purpose='planner', decided_by='router', result='selected', harness_id='fake',
        mission_id=mid, context_package_id=pkg)

    def run(tx, **_):
        tx.insert(rd, actor=actor)
        tx.append(new_event('route.decided', Ref('route_decision', rd.id), actor,
                            payload={'result': 'selected'}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return {'route_decision_id': rd.id, 'attempts': 2, 'account_ref': 'fake:default',
            'usage': usage, 'context_package_id': pkg}


def _do(db, command, **kw):
    return db.writer.execute(command, dict(kw))


def _row(db, cls, entity_id):
    with db.read() as c:
        r = rows.get(c, cls, entity_id)
    return None if r is None else r.entity


def _all(db, cls, **eq):
    with db.read() as c:
        return [r.entity for r in rows.where(c, cls, **eq)]


def _events(db, type_):
    """The payloads of the events of *type_*, oldest first."""
    with db.read() as c:
        return [json.loads(p) for (p,) in c.execute(
            'SELECT payload FROM events WHERE type = ? ORDER BY seq', (type_,))]


def _n_events(db):
    with db.read() as c:
        return c.execute('SELECT COUNT(*) FROM events').fetchone()[0]


# ── 1–4. every command re-judges its round: fail closed, end the call ───────

def test_a_plan_for_a_mission_that_moved_during_the_call_is_discarded(db):
    """planning.py:38-39 + 83-85 (`if mission.state != during` inside
    `_stale`, then apply's `failed` end): without the re-judge, a result the
    model made for a mission that has since left the planning state would
    still record a version and decide the mission's plan gate. The call still
    ends — a discarded result that leaves the call open is a leak — and
    nothing but the call's end is written."""
    actor = who()
    mid = _seed(db, actor, 'EXECUTING')
    pkg = _package(db, actor, mid)
    c = _call(db, actor, mid, pkg)
    out = _do(db, planning().apply, actor=actor, mission_id=mid, during='REASONING',
              round_seq=5, called=c, proposal=proposal())
    assert out == {'recorded': False,
                   'why': 'the mission moved from REASONING to EXECUTING during the call'}
    assert _all(db, entities.Plan, mission_id=mid) == []
    assert _all(db, entities.Task) == []
    rd = _row(db, entities.RouteDecision, c['route_decision_id'])
    assert rd.outcome['state'] == 'failed'
    assert rd.outcome['reason'].startswith('stale: the mission moved')
    assert (rd.outcome['attempts'], rd.outcome['account_ref']) == (2, 'fake:default')
    assert _row(db, entities.Mission, mid).state == 'EXECUTING'


def test_a_round_that_already_recorded_a_plan_records_no_second_one(db):
    """planning.py:40-41 (`if tx.where(entities.Plan, mission_id, round_seq)`):
    at-least-once delivery replays a round; dropped, the replay would insert
    a second version for the same round (or die on the UNIQUE index with the
    call left open). The mission is not moved again and the replay's own call
    ends `failed`."""
    actor = who()
    mid = _seed(db, actor, 'PLANNING')
    pkg = _package(db, actor, mid)
    first = _plan_of_round(db, actor, mid, 5)
    c = _call(db, actor, mid, pkg)
    out = _do(db, planning().apply, actor=actor, mission_id=mid, during='PLANNING',
              round_seq=5, called=c, proposal=proposal())
    assert out == {'recorded': False, 'why': 'round 5 already recorded a plan'}
    assert [p.id for p in _all(db, entities.Plan, mission_id=mid)] == [first]
    assert _row(db, entities.Mission, mid).state == 'PLANNING'
    assert _row(db, entities.RouteDecision, c['route_decision_id']).outcome['state'] == 'failed'


def test_a_result_whose_context_moved_after_the_call_is_thrown_away(db):
    """planning.py:42-3 (`planner.currency` through `_stale`): the mission's
    requirements changed after the package was assembled, so the answer was
    read from a world that no longer exists — the I10 worker case, seen from
    the command: nothing is recorded, the call ends `failed` with the why,
    and the round that the change started plans instead."""
    actor = who()
    mid = _seed(db, actor, 'PLANNING')
    pkg = _package(db, actor, mid)
    _stale_package(db, actor, mid, pkg)
    c = _call(db, actor, mid, pkg)
    out = _do(db, planning().apply, actor=actor, mission_id=mid, during='PLANNING',
              round_seq=9, called=c, proposal=proposal())
    assert out['recorded'] is False and 'changed after its context was assembled' in out['why']
    assert _all(db, entities.Plan, mission_id=mid) == []
    rd = _row(db, entities.RouteDecision, c['route_decision_id'])
    assert rd.outcome['state'] == 'failed' and out['why'] in rd.outcome['reason']


def test_a_call_that_names_a_package_that_does_not_exist_fails_closed(db):
    """planner.currency's `if pkg is None` (planner.py:336-337), reached
    through apply's stale branch (planning.py:83-85): a hostile or buggy
    `called` pointing at no package must not be treated as current — an
    answer judged on nothing records nothing."""
    actor = who()
    mid = _seed(db, actor, 'REASONING')
    pkg = _package(db, actor, mid)
    c = _call(db, actor, mid, pkg)
    c['context_package_id'] = ids.new_id('context_package')
    out = _do(db, planning().apply, actor=actor, mission_id=mid, during='REASONING',
              round_seq=5, called=c, proposal=proposal())
    assert out['recorded'] is False and 'does not exist' in out['why']
    assert _all(db, entities.Plan, mission_id=mid) == []
    assert _row(db, entities.RouteDecision, c['route_decision_id']).outcome['state'] == 'failed'
    assert _row(db, entities.Mission, mid).state == 'REASONING'


# ── 5–6. apply's recorded side, its ledger, and a hostile proposal ──────────

def test_a_current_result_records_the_version_once_and_replay_records_it_again_nothing(
        db):
    """planning.py:86-92 (propose_plan, `_end` 'ok' with `plan_id`,
    `recorded=out['plan_id'] is not None`) and planning.py:46-50 (`_end`'s
    `usage=called.get('usage') or None`): the recorded side in one
    transaction — version in force, mission decided by the plan gate,
    call ended ok, and the call's usage ledgered as the adapter reported it.
    Replaying the same round (a fresh call, same round_seq) is then refused by
    the round guard: still exactly one version, nothing re-decided."""
    actor = who()
    mid = _seed(db, actor, 'REASONING')
    pkg = _package(db, actor, mid)
    usage = {'tokens_in': 120, 'tokens_out': 30, 'cache_read': None,
             'cache_write': None, 'cost_usd': None}
    c = _call(db, actor, mid, pkg, usage=usage)
    out = _do(db, planning().apply, actor=actor, mission_id=mid, during='REASONING',
              round_seq=5, called=c, proposal=proposal())
    assert out['recorded'] is True and out['plan_id'] is not None and out['digest']
    (p,) = _all(db, entities.Plan, mission_id=mid)
    assert (p.state, p.plan_version, p.round_seq) == ('APPROVED', 1, 5)   # the ALLOW gate
    (gate,) = [d for d in _all(db, entities.PolicyDecision) if d.plan_id == p.id]
    assert (gate.stage, gate.outcome, gate.plan_digest) == ('plan', 'auto_approved', p.digest)
    assert (p.route_decision_id, p.context_package_id) == (c['route_decision_id'], pkg)
    assert _row(db, entities.Mission, mid).state == 'APPROVED'      # the ALLOW gate decided
    rd = _row(db, entities.RouteDecision, c['route_decision_id'])
    assert (rd.outcome['state'], rd.outcome['plan_id'], rd.outcome['attempts']) == (
        'ok', p.id, 2)
    (led,) = _all(db, entities.UsageLedger, route_decision_id=c['route_decision_id'])
    assert (led.basis, led.tokens_in, led.tokens_out) == ('reported_total', 120, 30)
    # the same round replayed at-least-once: refused, and nothing is written twice
    again = _call(db, actor, mid, pkg)
    out2 = _do(db, planning().apply, actor=actor, mission_id=mid, during='REASONING',
               round_seq=5, called=again, proposal=proposal())
    assert out2['recorded'] is False
    assert out2['why'] == 'the mission moved from REASONING to APPROVED during the call'
    assert [x.id for x in _all(db, entities.Plan, mission_id=mid)] == [p.id]
    assert _row(db, entities.Mission, mid).state == 'APPROVED'


def test_a_plan_the_validator_refuses_writes_neither_rows_nor_a_call_end(db):
    """Fail-closed over hostile input through apply (planning.py:86 ->
    work.propose_plan's `validate.problems` refusal): the whole transaction
    rolls back — no version, no task, and the call stays open (the boot sweep
    ends it), so a half-recorded plan can never be decided."""
    actor = who()
    mid = _seed(db, actor, 'PLANNING')
    pkg = _package(db, actor, mid)
    c = _call(db, actor, mid, pkg)
    bad = proposal(task('a', depends_on=('b',)), task('b', depends_on=('a',)))
    before = _n_events(db)
    with pytest.raises(ValueError, match='not valid'):
        _do(db, planning().apply, actor=actor, mission_id=mid, during='PLANNING',
            round_seq=5, called=c, proposal=bad)
    assert _all(db, entities.Plan, mission_id=mid) == []
    assert _all(db, entities.Task) == []
    assert _row(db, entities.RouteDecision, c['route_decision_id']).outcome is None
    assert _all(db, entities.UsageLedger) == []
    assert _n_events(db) == before


# ── 7–9. hold: the question is posted, the state decides who moves ──────────

CLARIFICATION = {'kind': 'clarification', 'questions': ['Which CLI, the core or the client?'],
                 'missing': [{'kind': 'service', 'name': 'the billing service'}],
                 'conflicts': []}


def test_a_blocking_answer_while_reasoning_blocks_the_mission_and_asks_in_the_primary(
        db):
    """planning.py:106-108 (`if m.state == 'REASONING': self.missions.challenge`)
    with 104-105 (the one archeus message with the card) and 68-69 (`_text`'s
    REASONING branch, 'Then resume the mission.'): a mission that has not
    planned anything yet goes to BLOCKED by the real `challenge_raised` edge,
    carries `planning_blocked` with the round's identity, and the user is told
    in the primary conversation. The call ends ok with `planned=False`, and
    the usage ledger exists even though nothing was reported (ADR-0048)."""
    actor = who()
    mid = _seed(db, actor, 'REASONING')
    pkg = _package(db, actor, mid)
    c = _call(db, actor, mid, pkg)
    out = _do(db, planning().hold, actor=actor, mission_id=mid, during='REASONING',
              round_seq=5, called=c, block=CLARIFICATION)
    assert out == {'recorded': False, 'blocked': 'clarification'}
    m = _row(db, entities.Mission, mid)
    assert (m.state, m.held_from) == ('BLOCKED', 'REASONING')
    assert m.planning_blocked == dict(CLARIFICATION, round_seq=5,
                                       route_decision_id=c['route_decision_id'],
                                       context_package_id=pkg)
    (msg,) = _all(db, entities.Message)
    assert (msg.author, msg.principal_id) == ('archeus', actor.id)
    assert msg.cards[0] == {'type': 'clarification', 'ref': {'kind': 'mission', 'id': mid}}
    assert msg.text.splitlines() == [
        'Planning "Ship it" needs your answer first:',
        '- Which CLI, the core or the client?',
        '- missing service: the billing service',
        'Reply to this message; nothing is planned until you do. Then resume the mission.']
    assert msg.links == ({'ref': {'kind': 'mission', 'id': mid}},)
    rd = _row(db, entities.RouteDecision, c['route_decision_id'])
    assert (rd.outcome['state'], rd.outcome['planned'], rd.outcome['blocked']) == (
        'ok', False, 'clarification')
    (led,) = _all(db, entities.UsageLedger, route_decision_id=c['route_decision_id'])
    assert led.basis == 'none'                       # nothing reported, nothing hides


def test_a_challenge_while_replanning_waits_in_place_and_takes_no_blocked_edge(db):
    """planning.py:109-110 (`else: _block(...)` — the branch a REPLANNING
    round must take) and planning.py:61 + 64-67 (`_text`'s challenge head and
    the questions/missing/conflicts lines): a replan that hits confirmed
    knowledge waits exactly where it is — a BLOCKED edge from here would
    bypass the replan budget — and the user is told what it conflicts with.
    The block is a plain field update with its `mission.updated` event."""
    actor = who()
    mid = _seed(db, actor, 'REPLANNING')
    pkg = _package(db, actor, mid)
    c = _call(db, actor, mid, pkg)
    block = {'kind': 'challenge', 'questions': [], 'missing': [],
             'conflicts': [{'ref': {'kind': 'knowledge_item', 'id': 'kni_x'},
                            'why': 'it bypasses the rule'}]}
    out = _do(db, planning().hold, actor=actor, mission_id=mid, during='REPLANNING',
              round_seq=7, called=c, block=block)
    assert out == {'recorded': False, 'blocked': 'challenge'}
    m = _row(db, entities.Mission, mid)
    assert m.state == 'REPLANNING' and m.held_from is None
    assert _events(db, 'mission.state_changed') == []              # no edge, no BLOCKED
    assert m.planning_blocked['kind'] == 'challenge'
    assert m.planning_blocked['round_seq'] == 7
    (msg,) = _all(db, entities.Message)
    assert msg.text.splitlines() == [
        'Planning "Ship it" goes against what is recorded:',
        '- against knowledge_item kni_x: it bypasses the rule',
        'Reply to this message; nothing is planned until you do.']
    assert 'Then resume' not in msg.text
    assert [e['fields'] for e in _events(db, 'mission.updated')] == \
        [['planning_blocked']]


def test_a_hold_for_a_mission_that_moved_posts_nothing_and_fails_the_call(db):
    """planning.py:96-99 (hold's stale branch before the `_message` at 104):
    a question from a dead round must never reach the user — it would ask for
    an answer to a call that no longer decides anything, and would set
    `planning_blocked` on a mission that has moved past it. Nothing is
    written but the call's `failed` end."""
    actor = who()
    mid = _seed(db, actor, 'EXECUTING')
    pkg = _package(db, actor, mid)
    c = _call(db, actor, mid, pkg)
    before = _n_events(db)
    out = _do(db, planning().hold, actor=actor, mission_id=mid, during='REASONING',
              round_seq=5, called=c, block=CLARIFICATION)
    assert out['recorded'] is False and out['why'].startswith('the mission moved')
    assert _all(db, entities.Message) == []
    assert _all(db, entities.Conversation) == []                   # not even a primary made
    assert _row(db, entities.Mission, mid).planning_blocked is None
    rd = _row(db, entities.RouteDecision, c['route_decision_id'])
    assert rd.outcome['state'] == 'failed' and rd.outcome['reason'].startswith('stale:')
    assert _n_events(db) == before + 1                             # only archeus_call.ended


# ── 10–12. deny: recorded when it still denies, never when it does not ───────

def test_a_denied_plan_records_the_denial_and_blocks_the_mission_for_it(db):
    """planning.py:123-127 (deny's recorded side: `authorization.
    record_plan_denial` with `policy=self.work.policy`, then the 'ok' end with
    `denied=out.get('policy_decision_id')`): a plan the policy DENIES leaves
    no version, task or approval — the auditable denial is recorded, the
    REASONING mission goes BLOCKED by the guarded `plan_denied` edge, and
    `planning_blocked.kind` is `policy` with the denied items."""
    actor = who()
    mid = _seed(db, actor, 'REASONING')
    pkg = _package(db, actor, mid)
    c = _call(db, actor, mid, pkg)
    out = _do(db, planning('DENY').deny, actor=actor, mission_id=mid, during='REASONING',
              round_seq=5, called=c, specs=[task()])
    assert out['recorded'] is True and out['planned'] is False and out['policy_decision_id']
    (d,) = _all(db, entities.PolicyDecision)
    assert (d.stage, d.outcome, d.mission_id) == ('plan', 'denied', mid)
    assert out['policy_decision_id'] == d.id
    m = _row(db, entities.Mission, mid)
    assert (m.state, m.held_from) == ('BLOCKED', 'REASONING')
    assert m.planning_blocked['kind'] == 'policy'
    assert m.planning_blocked['policy_decision_id'] == d.id
    assert [x['task'] for x in m.planning_blocked['denied']] == ['t1']
    assert _all(db, entities.Plan, mission_id=mid) == []
    rd = _row(db, entities.RouteDecision, c['route_decision_id'])
    assert (rd.outcome['state'], rd.outcome['planned'], rd.outcome['denied']) == (
        'ok', False, d.id)


def test_a_denial_delivered_for_a_mission_that_moved_records_nothing(db):
    """planning.py:119-122 (deny's stale branch, before `record_plan_denial`):
    a DENY judged for a round whose mission has moved must not produce a
    PolicyDecision, a block, or a BLOCKED edge for a mission that is no
    longer planning — the call ends `failed` and the rows say nothing else."""
    actor = who()
    mid = _seed(db, actor, 'EXECUTING')
    pkg = _package(db, actor, mid)
    c = _call(db, actor, mid, pkg)
    out = _do(db, planning('DENY').deny, actor=actor, mission_id=mid, during='REASONING',
              round_seq=5, called=c, specs=[task()])
    assert out == {'recorded': False,
                   'why': 'the mission moved from REASONING to EXECUTING during the call'}
    assert _all(db, entities.PolicyDecision) == []
    assert _row(db, entities.Mission, mid).planning_blocked is None
    assert _row(db, entities.Mission, mid).state == 'EXECUTING'
    rd = _row(db, entities.RouteDecision, c['route_decision_id'])
    assert rd.outcome['state'] == 'failed' and rd.outcome['reason'].startswith('stale:')


def test_a_policy_that_stopped_denying_records_nothing_and_just_ends_the_call(db):
    """authorization.record_plan_denial's `if not denied` (reached through
    planning.py:123-127): the policy changed between the refusal and the end
    of the call. Nothing is recorded and the mission waits in place for the
    next round — but the call still ends ok, with `denied=None`, because there
    is nothing left to report."""
    actor = who()
    mid = _seed(db, actor, 'REASONING')
    pkg = _package(db, actor, mid)
    c = _call(db, actor, mid, pkg)
    out = _do(db, planning('ALLOW').deny, actor=actor, mission_id=mid, during='REASONING',
              round_seq=5, called=c, specs=[task()])
    assert out == {'recorded': False, 'why': 'the policy no longer denies this plan',
                   'planned': False}
    assert _all(db, entities.PolicyDecision) == []
    m = _row(db, entities.Mission, mid)
    assert (m.state, m.planning_blocked) == ('REASONING', None)
    rd = _row(db, entities.RouteDecision, c['route_decision_id'])
    assert (rd.outcome['state'], rd.outcome['denied'], rd.outcome['planned']) == (
        'ok', None, False)


# ── 13–14. note: a call that never answered, and one whose mission moved on ─

def test_a_call_that_never_answered_blocks_the_round_in_place(db):
    """planning.py:135-137 (`_block` with `kind='call'`): a gated, unavailable
    or invalid call records why planning is blocked — nothing is invented —
    while the mission waits exactly where it was, with the round and the
    call's identity carried in the block."""
    actor = who()
    mid = _seed(db, actor, 'PLANNING')
    out = _do(db, planning().note, actor=actor, mission_id=mid, during='PLANNING',
              round_seq=5, outcome='invalid', detail='no tasks key',
              route_decision_id='rds-external')
    assert out == {'recorded': False, 'blocked': 'call', 'outcome': 'invalid'}
    m = _row(db, entities.Mission, mid)
    assert m.state == 'PLANNING' and m.held_from is None
    assert m.planning_blocked == {'kind': 'call', 'outcome': 'invalid',
                                  'detail': 'no tasks key', 'round_seq': 5,
                                  'route_decision_id': 'rds-external'}
    assert [e['fields'] for e in _events(db, 'mission.updated')] == \
        [['planning_blocked']]


def test_a_note_for_a_mission_that_moved_on_writes_nothing_at_all(db):
    """planning.py:133-4 (`if m.state != during: return ... 'the mission
    moved on'`): the call already ended itself, so `note` must not end
    anything and must not block a mission that has moved — dropped, a late
    note would stamp `planning_blocked` on a mission that is long past the
    round, and the user would later be told the wrong reason. Not one event
    is written."""
    actor = who()
    mid = _seed(db, actor, 'EXECUTING')
    before = _n_events(db)
    out = _do(db, planning().note, actor=actor, mission_id=mid, during='REASONING',
              round_seq=5, outcome='timeout', detail='the adapter did not answer')
    assert out == {'recorded': False, 'why': 'the mission moved on'}
    assert _row(db, entities.Mission, mid).planning_blocked is None
    assert _n_events(db) == before
