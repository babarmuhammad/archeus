"""T-150 (a) (owner 2026-10-21, p19-design-gate B6): a mission made from a chat
message asks before it starts under `standard`. Start approves it (the card
'Start and plan "<title>"?'), and then the engine plans it. Keep as mission
(the reject) leaves it CREATED and idle: it is not cancelled and not asked
again on a later pass, not even after a Core restart. Only an explicit start
asks again, once. `careful` and `autonomous` keep their behaviour, and a
mission made through the API (origin `api`) starts under `standard` as before."""

import pytest

from archeus.core import engine, ports
from archeus.core.application import authorization, commands, queries
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.core.policy.engine import PolicyEngine
from archeus.infra.db import rows
from v1.integration.test_intent import WORK, brain, make  # noqa: F401 (a fixture)
from v1.integration.test_skeleton import Core

DEPLOY = dict(engine.SKELETON_PLAN, tasks=[dict(engine.SKELETON_PLAN['tasks'][0],
                                                action_classes=['deploy'])])


@pytest.fixture
def core(archeus_home):
    c = Core(policy=PolicyEngine())
    yield c
    c.close()


def _chat(core, title='Chat work'):
    return core.do(commands.create_mission, title=title, objective='o',
                   origin='conversation')['id']


def _starts(core, mid):
    return [a for a in core.all(entities.Approval, mission_id=mid) if a.kind == 'start']


def _start_decisions(core, mid):
    return [(d.decision, d.outcome) for d in core.all(entities.PolicyDecision)
            if d.stage == 'start' and d.mission_id == mid]


def _planned(core, mid):
    return (core.all(entities.Plan, mission_id=mid), core.all(entities.Task),
            core.all(entities.Execution))


def _restart(core):
    core.engine = core.build_engine()


# ── the chat path: a new_work message creates the mission and asks to start it ──

def test_a_chat_new_work_under_standard_asks_to_start_and_plan_it(make):  # noqa: F811
    r = make([brain(('Add a --version flag to the CLI', WORK))])
    r.say('Add a --version flag to the CLI')
    (m,) = r.all(entities.Mission)
    assert (m.state, m.origin) == ('CREATED', 'conversation')
    authz = authorization.Authorization(missions=commands.Missions(policy=PolicyEngine()))
    assert r.run(authz.gate_start, mission_id=m.id) == {
        'started': False, 'waiting': 'approval_required'}
    (a,) = [x for x in r.all(entities.Approval) if x.mission_id == m.id]
    assert (a.kind, a.state) == ('start', 'PENDING')
    texts = [x['text'] for x in r.read(lambda c: queries.messages(c, _primary(c)))]
    assert 'Start and plan "Add a --version flag"?' in texts
    assert r.all(entities.Plan) == [] and r.all(entities.Task) == []
    assert r.all(entities.Execution) == []


def _primary(conn):
    (c,) = [x.entity.id for x in rows.where(conn, entities.Conversation, kind='primary')]
    return c


# ── approve starts it and the engine plans it ──

def test_approve_starts_the_chat_mission_and_the_engine_plans_it(core):
    mid = _chat(core)
    assert core.engine.run(mid)['state'] == 'CREATED'
    assert _planned(core, mid) == ([], [], [])                  # nothing while it waits
    a = core.pending(mid)
    assert core.decide(mid)['mission']['state'] == 'UNDERSTANDING'
    assert core.row(entities.Approval, a.id).entity.state == 'APPROVED'
    assert core.engine.run(mid)['state'] != 'CREATED'
    assert core.all(entities.Plan, mission_id=mid)                # it was planned
    assert _start_decisions(core, mid) == [('ASK', 'asked'), ('ASK', 'approved')]


def test_a_waiting_chat_mission_does_no_work_however_often_the_engine_passes(core):
    mid = _chat(core)
    for _ in range(3):
        core.engine.step(mid)
    assert core.engine.run(mid)['state'] == 'CREATED'
    assert _planned(core, mid) == ([], [], [])
    assert core.all(entities.Plan) == [] and core.all(entities.Execution) == []
    assert len(_starts(core, mid)) == 1


# ── Keep as mission: idle, not cancelled, not asked again (not even after a restart) ──

def test_declining_keeps_the_chat_mission_idle_and_restart_does_not_ask_again(core):
    mid = _chat(core)
    core.engine.run(mid)
    core.decide(mid, decision='reject')
    assert core.row(entities.Mission, mid).entity.state == 'CREATED'
    assert [a.state for a in _starts(core, mid)] == ['REJECTED']
    _restart(core)
    assert core.engine.run(mid)['state'] == 'CREATED'
    for _ in range(3):
        core.engine.step(mid)
    assert [a.state for a in _starts(core, mid)] == ['REJECTED']
    assert _start_decisions(core, mid) == [('ASK', 'asked')]
    assert _planned(core, mid) == ([], [], [])


def test_an_explicit_start_asks_again_once_and_keeps_a_record(core):
    mid = _chat(core)
    core.engine.run(mid)
    core.decide(mid, decision='reject')
    authz = authorization.Authorization(missions=core.missions)
    out = core.do(authz.request_start, mission_id=mid)
    assert out == {'started': False, 'waiting': 'approval_required'}
    (live,) = [a for a in _starts(core, mid) if a.state == 'PENDING']
    assert core.do(authz.request_start, mission_id=mid) == {
        'started': False, 'waiting': 'approval_required'}
    assert [a.state for a in _starts(core, mid)] == ['REJECTED', 'PENDING']
    assert _start_decisions(core, mid) == [('ASK', 'asked'), ('ASK', 'asked')]
    core.decide(mid)                                            # the new card: Start
    assert core.row(entities.Approval, live.id).entity.state == 'APPROVED'
    assert core.row(entities.Mission, mid).entity.state == 'UNDERSTANDING'


# ── the other profiles and origins are unchanged ──

def test_autonomous_chat_mission_starts_without_asking(core):
    mid = _chat(core)
    core.do(authorization.set_profile, actor=_admin(core), scope='mission', mission_id=mid,
            profile='autonomous')
    assert core.engine.run(mid)['state'] != 'CREATED'
    assert _starts(core, mid) == []
    assert _start_decisions(core, mid) == [('ALLOW', 'allow')]


def test_careful_chat_mission_asks_and_rejecting_cancels_it(core):
    mid = _chat(core)
    core.do(authorization.set_profile, actor=_admin(core), scope='mission', mission_id=mid,
            profile='careful')
    core.engine.run(mid)
    core.decide(mid, decision='reject')
    assert core.row(entities.Mission, mid).entity.state == 'CANCELLED'


def test_an_api_mission_under_standard_starts_without_asking(core):
    mid = core.mission()
    assert core.row(entities.Mission, mid).entity.origin == 'api'
    assert core.engine.run(mid)['state'] != 'CREATED'
    assert _starts(core, mid) == []


def _admin(core):
    return Ref('user_device', core.db.writer.execute(
        commands.register_principal, {'kind': 'user_device',
                                      'scopes': ('observe', 'control', 'approve', 'admin')},
        idempotency_key=ids.new_ulid())['id'])


# ── the card says what its buttons do, and the buttons do it ──

def test_the_start_cards_reject_text_is_what_a_reject_does(core):
    mid = _chat(core)
    core.engine.run(mid)
    a = core.pending(mid)
    said = a.presented['consequences']['reject']
    assert 'idle' in said and 'cancel' not in said
    core.decide(mid, decision='reject')
    assert core.row(entities.Mission, mid).entity.state == 'CREATED'

    careful = _chat(core, 'Careful work')
    core.do(authorization.set_profile, actor=_admin(core), scope='mission', mission_id=careful,
            profile='careful')
    core.engine.run(careful)
    assert core.pending(careful).presented['consequences']['reject'] == 'the mission is cancelled'
    core.decide(careful, decision='reject')
    assert core.row(entities.Mission, careful).entity.state == 'CANCELLED'


# ── whose profile decides: the user's, when the mission has none ──

def test_a_user_level_autonomous_profile_starts_a_chat_mission_without_asking(core):
    core.do(authorization.set_profile, actor=_admin(core), scope='user', profile='autonomous')
    mid = _chat(core)
    assert core.engine.run(mid)['state'] != 'CREATED'
    assert _starts(core, mid) == []
    assert _start_decisions(core, mid) == [('ALLOW', 'allow')]


# ── only the Start card reads "Start and plan" ──

def test_a_plan_card_for_a_chat_mission_is_not_worded_as_the_start(core):
    core.brain = ports.FixedPlanBrain(DEPLOY)
    _restart(core)
    mid = _chat(core)
    core.engine.run(mid)
    core.decide(mid)                                            # Start
    assert core.engine.run(mid)['state'] == 'APPROVAL_REQUIRED'
    plan = core.pending(mid)
    assert plan.kind == 'plan'
    with core.db.read() as c:
        (card,) = [m for m in queries.messages(c, _primary(c))
                   if any(x['ref']['id'] == plan.id for x in m['cards'])]
    assert card['text'] == '"Chat work" needs your approval: %s.' % plan.presented['scope']
