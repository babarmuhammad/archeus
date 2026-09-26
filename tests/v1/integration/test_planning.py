"""P8 over a real database (p8-design-gate §21.2, I01–I26): the plan engine — the
planning worker, the planner call through `archeus_call`, Core's validator, the
PlanVersion lifecycle and every boundary it keeps. Fake adapters only: no real
CLI is ever spawned, and the only processes are the fake harness's, where a
scenario runs a task at all.

Every test also passes E6 (the autouse `no_plan_is_ever_approved`): across the
suite no plan version reaches APPROVED or REJECTED — that is P9's.
"""

import pytest

from archeus.core import engine, ports
from archeus.core.application import calls as C
from archeus.core.application import commands, lifecycle, queries, work
from archeus.core.application.planning import Planning
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.planning import planner as P, validate
from archeus.core.planning.worker import Planner
from archeus.harnesses.fake import FakeCaller, FakeHarness
from archeus.harnesses.registry import AdapterRegistry
from archeus.infra.db import rows
from archeus.infra.eventlog import outbox
from v1.integration.test_intent import WORK, Rig as IRig, _decision
from v1.integration.test_knowledge import Real

AUTO = {'text': 'the result passes its automatic check', 'check': 'automatic'}


def task(id_, **kw):
    return dict({'id': id_, 'title': 'Task %s' % id_, 'kind': 'code_change',
                 'objective': 'Do %s.' % id_, 'expected_output': 'the %s change' % id_,
                 'action_classes': ['write_repo'],
                 'acceptance': [{'text': '%s works' % id_, 'check': 'automatic'}]}, **kw)


def answer(*tasks, **kw):
    return dict({'summary': 'a plan', 'tasks': list(tasks), 'success_criteria': [AUTO]}, **kw)


ONE = answer(task('do'))


def fake(*planner, id_='fake', structured='native', brain=()):
    """A headless fake answering plan.v1 in order (the last repeating), and
    intent.v1 from (utterance, parsed) pairs."""
    replies = {'planner': [p if 'error' in p or 'text' in p else {'parsed': p}
                           for p in planner]}
    if brain:
        replies['brain'] = [{'when': 'The message:\n' + u, 'parsed': p} for u, p in brain]
    return FakeCaller(id_, structured=structured, replies=replies)


class Rig(IRig):
    def __init__(self, db, parent, callers, preference=None, policy='ASK'):
        super().__init__(db, parent, callers, preference)
        self.missions = commands.Missions(policy=ports.FixedPolicy(policy))
        self.work = work.Work(missions=self.missions, router=ports.FixedCandidateRouter('fake'))
        registry = AdapterRegistry(self.missions.policy)
        registry.register(FakeHarness())
        self.scenarios = {}
        self.engine = engine.Engine(db, actor=self.system, work=self.work, brain=None,
                                    registry=registry, verifier=ports.ScriptedVerifier(),
                                    reviewer=ports.ScriptedReview(), scenarios=self.scenarios)
        self.planning = Planning(work=self.work)
        self.planner = Planner(db, actor=self.system, calls=self.calls, planning=self.planning)

    def settle(self, limit=300, plan=True):
        for _ in range(limit):
            moved = (self.world.pass_once()['changed'] | self.knowledge.pass_once()['changed']
                     | self.intents.pass_once()['changed'])
            if plan:
                moved |= self.planner.pass_once()['changed']
            live = [m.id for m in self.all(entities.Mission) if m.state not in engine.SETTLED]
            stepped = any([self.engine.step(mid)['changed'] for mid in live])
            if not (moved or stepped):
                return
        raise AssertionError('did not settle')

    def mission(self, title='Ship it', objective='Ship the thing.', **kw):
        return self.run(commands.create_mission, title=title, objective=objective, **kw)['id']

    def sys(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.system))

    def plans(self, mid):
        return sorted(self.all(entities.Plan, mission_id=mid), key=lambda p: p.plan_version)

    def tasks(self, plan_id):
        return sorted(self.all(entities.Task, plan_id=plan_id), key=lambda t: t.key)

    def m(self, mid):
        return self.read(lambda c: rows.get(c, entities.Mission, mid).entity)

    def rds(self, purpose='planner'):
        return [rd for rd in self.all(entities.RouteDecision) if rd.purpose == purpose]

    def to_reasoning(self, mid):
        """Step the engine alone (no planning worker) until the mission reasons."""
        for _ in range(10):
            if self.m(mid).state == 'REASONING':
                return
            self.engine.step(mid)
        raise AssertionError('never reached REASONING')


@pytest.fixture
def make(db, tmp_path):
    parent = tmp_path / 'repos'
    parent.mkdir()
    return lambda callers, preference=None, policy='ASK': Rig(db, str(parent), callers,
                                                               preference, policy)


@pytest.fixture(autouse=True)
def no_plan_is_ever_approved(db):
    """E6: whatever a test does, P8 never takes a plan to APPROVED or REJECTED."""
    yield
    with db.read() as conn:
        moved = [e for e in queries.events(conn, 0) if e['type'] == 'plan.state_changed']
        states = {r.entity.state for r in rows.where(conn, entities.Plan)}
    assert {e['payload']['to'] for e in moved} <= {'PROPOSED', 'SUPERSEDED'}
    assert states <= {'PROPOSED', 'SUPERSEDED'}


def _with_requirements(r):
    """A mission from a message, with an explicit (r1) and an inferred (r2) requirement."""
    r.say('Add a --version flag to the CLI')
    (m,) = r.all(entities.Mission)
    return m.id


# ── I01–I03 plans and their graph ──

def test_i01_a_simple_mission_becomes_one_proposed_plan_version(make):
    r = make([fake(ONE)])
    mid = r.mission()
    r.settle()
    (p,) = r.plans(mid)
    (t,) = r.tasks(p.id)
    assert (p.state, p.plan_version, p.estimated_cost, p.supersedes_plan_id) == (
        'PROPOSED', 1, 'low', None)
    assert (t.key, t.state, t.objective, t.acceptance[0]['check']) == (
        't1', 'PENDING', 'Do do.', 'automatic')
    m = r.m(mid)
    assert (m.state, m.decided_plan_version) == ('APPROVAL_REQUIRED', 1)
    (moved,) = r.events('plan.state_changed')
    assert (moved['payload']['from'], moved['payload']['to'], moved['payload']['guard']['name']) \
        == ('DRAFT', 'PROPOSED', 'ready')
    (rd,) = r.rds()
    assert (rd.outcome['state'], rd.source, rd.context_package_id) == (
        'ok', Ref('mission', mid), p.context_package_id)
    assert p.route_decision_id == rd.id
    entered = [e['seq'] for e in r.events('mission.state_changed')
               if e['payload']['to'] == 'REASONING']
    assert p.round_seq == entered[0]


def test_i02_a_multi_step_mission_is_a_dependency_graph_keyed_by_core(make):
    r = make([fake(answer(task('ship', depends_on=['build', 'docs']), task('build'),
                          task('docs', depends_on=['build'])))])
    mid = r.mission()
    r.settle()
    (p,) = r.plans(mid)
    got = {t.title: (t.key, t.depends_on) for t in r.tasks(p.id)}
    assert got == {'Task build': ('t1', ()), 'Task docs': ('t2', ('t1',)),
                   'Task ship': ('t3', ('t1', 't2'))}
    assert r.read(queries.get_plan, p.id)['waves'] == [['t1'], ['t2'], ['t3']]


def test_i03_parallel_tasks_share_a_wave_and_overlapping_touches_are_serialised(make):
    r = make([fake(answer(task('a'), task('b', depends_on=['a'], touches=['src/x/**']),
                          task('c', depends_on=['a'], touches=['src/x/y.py']),
                          task('d', depends_on=['a'], touches=['docs/**'])))])
    mid = r.mission()
    r.settle()
    (p,) = r.plans(mid)
    deps = {t.key: t.depends_on for t in r.tasks(p.id)}
    assert deps == {'t1': (), 't2': ('t1',), 't3': ('t1', 't2'), 't4': ('t1',)}
    (edge,) = p.serialised
    assert (edge['task'], edge['after']) == ('t3', 't2')
    assert 'src/x/**' in edge['because'] and 'src/x/y.py' in edge['because']
    # the planner's own edges are exactly the persisted ones minus Core's
    planner_made = {k: tuple(d for d in v if not any(
        s['task'] == k and s['after'] == d for s in p.serialised)) for k, v in deps.items()}
    assert planner_made['t3'] == ('t1',)
    assert r.read(queries.get_plan, p.id)['waves'] == [['t1'], ['t2', 't4'], ['t3']]
    assert p.estimated_cost == 'medium'      # Core's band: 4 mid tasks x 1 = 8 (D9)


# ── I04–I08 what never becomes a plan ──

def test_i04_a_cycle_is_rejected_retried_and_never_recorded(make):
    cyclic = answer(task('a', depends_on=['b']), task('b', depends_on=['a']))
    r = make([fake(cyclic)])
    mid = r.mission()
    r.settle()
    assert r.plans(mid) == [] and r.all(entities.Task) == []
    m = r.m(mid)
    assert (m.state, m.planning_blocked['kind'], m.planning_blocked['outcome']) == (
        'REASONING', 'call', 'invalid')
    (rd,) = r.rds()
    assert rd.outcome['attempts'] == 2 and 'cycle: ' in rd.outcome['reason']


def test_i05_an_explicit_requirement_no_task_serves_is_invalid(make):
    r = make([fake(ONE, brain=[('Add a --version flag to the CLI', WORK)])])
    mid = _with_requirements(r)
    r.settle()
    assert r.plans(mid) == []
    (rd,) = r.rds()
    assert rd.outcome['state'] == 'invalid' and 'explicit requirement r1' in rd.outcome['reason']


def test_i06_an_ambiguous_requirement_is_asked_and_the_first_plan_waits_blocked(make):
    ask = answer(questions=[{'question': 'Which CLI, the core or the client?',
                             'blocking': True, 'about': 'r1'}])
    served = answer(task('do', serves=['r1']))
    r = make([fake(ask, served, brain=[('Add a --version flag to the CLI', WORK)])])
    mid = _with_requirements(r)
    r.settle()
    m = r.m(mid)
    assert r.plans(mid) == []
    assert (m.state, m.held_from, m.planning_blocked['kind']) == (
        'BLOCKED', 'REASONING', 'clarification')
    assert m.planning_blocked['questions'] == ['Which CLI, the core or the client?']
    (last,) = [x for x in r.all(entities.Message) if x.author == 'archeus'
               and x.cards and x.cards[0]['type'] == 'clarification'
               and x.cards[0]['ref'] == {'kind': 'mission', 'id': mid}]
    assert 'Which CLI' in last.text and 'resume' in last.text
    # explicit resume: re-understood, fresh context, a new round plans
    r.run(r.missions.resume, mission_id=mid)
    r.settle()
    (p,) = r.plans(mid)
    assert p.state == 'PROPOSED' and r.m(mid).planning_blocked is None


def test_i06b_a_blocked_replan_waits_in_place_and_never_takes_a_new_blocked_edge(make):
    ask = answer(questions=[{'question': 'Keep the old flag?', 'blocking': True}])
    r = make([fake(ONE, ask, answer(task('do', serves=['r1'])))], policy='ALLOW')
    r.scenarios['t1'] = [{'exit': 1}]
    mid = r.mission()
    r.settle()
    m = r.m(mid)
    assert (m.state, m.planning_blocked['kind']) == ('REPLANNING', 'clarification')
    assert [p.plan_version for p in r.plans(mid)] == [1]
    assert 'BLOCKED' not in [e['payload']['to'] for e in r.events('mission.state_changed')]
    # the user's answer changes the mission: the round it starts records v2
    r.scenarios['t1'] = [{'emit': {'type': 'result', 'summary': 'done'}}]
    r.sys(_add_requirement, mission_id=mid, text='keep the old flag too')
    r.settle()
    assert [p.plan_version for p in r.plans(mid)] == [1, 2]


def test_i07_a_missing_world_object_is_asked_and_never_created(make):
    r = make([fake(answer(missing=[{'name': 'the billing service', 'kind': 'service',
                                    'required': True}]))])
    mid = r.mission()
    r.settle()
    m = r.m(mid)
    assert r.plans(mid) == [] and m.state == 'BLOCKED'
    assert m.planning_blocked['missing'] == [{'name': 'the billing service', 'kind': 'service'}]
    assert r.all(entities.Project) == [] and r.all(entities.Repository) == []


def test_i08_an_unknown_handle_is_invalid_and_nothing_is_created_from_it(make):
    r = make([fake(answer(task('do', refs=['p9'])))])
    mid = r.mission()
    r.settle()
    assert r.plans(mid) == [] and r.all(entities.Project) == []
    (rd,) = r.rds()
    assert rd.outcome['state'] == 'invalid' and "'p9' is not a world handle" in rd.outcome['reason']


# ── I09–I10 stale context ──

def _add_requirement(tx, *, actor, mission_id, text):
    m = tx.get(entities.Mission, mission_id).entity
    req = ({'text': text, 'origin': 'explicit'},)
    tx.update(entities.Mission, mission_id, {'requirements': m.requirements + req}, actor=actor)
    e = tx.append(new_event('mission.updated', Ref('mission', mission_id), actor, payload={
        'fields': ['requirements'], 'added': {'requirements': list(req)}}))
    return {'seq': e.seq}


def test_i09_a_package_older_than_the_mission_is_replaced_before_the_call(make):
    r = make([fake(answer(task('do', serves=['r1'])))])
    mid = r.mission()
    r.to_reasoning(mid)
    first = r.m(mid).context_package_id
    seq = r.sys(_add_requirement, mission_id=mid, text='also print the hash')['seq']
    r.settle()
    (p,) = r.plans(mid)
    assert p.context_package_id != first
    pkg = r.read(queries.get_context_package, p.context_package_id)
    assert pkg['as_of_seq'] >= seq
    assert p.round_seq == seq       # the REASONING round was superseded by the newer one
    assert len(r.rds()) == 1        # and never called the planner


def test_i10_a_result_made_stale_during_the_call_is_discarded(make):
    f = fake(ONE, answer(task('do', serves=['r1'])))
    r = make([f])
    mid = r.mission()
    r.to_reasoning(mid)
    inner = f.call

    def call(spec):         # the mission changes while the model is thinking
        if len(f.sent) == 0:
            r.sys(_add_requirement, mission_id=mid, text='changed mid-call')
        return inner(spec)
    f.call = call
    r.settle()
    first, second = r.rds()
    assert first.outcome['state'] == 'failed' and first.outcome['reason'].startswith('stale: ')
    (p,) = r.plans(mid)
    assert p.route_decision_id == second.id


# ── I11–I13 requirements, assumptions, conflicts ──

def test_i11_explicit_and_inferred_stay_apart_and_the_mission_is_never_written(make):
    plan = answer(task('do', serves=['r1']),
                  assumptions=[{'text': 'the version is in pyproject.toml', 'about': 'r2'}])
    r = make([fake(plan, brain=[('Add a --version flag to the CLI', WORK)])])
    mid = _with_requirements(r)          # settles: the plan is recorded by now
    (p,) = r.plans(mid)
    assert [(c['text'], c['origin']) for c in r.m(mid).requirements] == [
        (c['text'], c['origin']) for c in WORK['requirements']]      # exactly what P7 wrote
    assert [(i['handle'], i['origin']) for i in p.inputs] == [('r1', 'explicit'),
                                                             ('r2', 'inferred')]
    assert [(c['requirement'], c['tasks']) for c in p.coverage] == [('r1', ['t1']), ('r2', [])]
    (a,) = p.assumptions
    assert (a['origin'], a['about']) == ('inferred', 'r2')


def test_i12_non_blocking_gaps_make_a_plan_with_explicit_assumptions(make):
    r = make([fake(answer(task('do'), assumptions=[{'text': 'pytest is the test runner'}],
                          questions=[{'question': 'Also update the docs?', 'blocking': False}]))])
    mid = r.mission()
    r.settle()
    (p,) = r.plans(mid)
    assert p.state == 'PROPOSED'
    assert p.assumptions == ({'text': 'pytest is the test runner', 'origin': 'inferred'},)
    assert p.questions == ({'question': 'Also update the docs?', 'about': None},)


def test_i13_a_plan_against_confirmed_knowledge_is_challenged(make):
    r = make([fake(answer(task('do'), conflicts=[{'ref': 'k1', 'why': 'it bypasses the rule'}]))])
    dec = _decision(r, 'The core never talks to the database directly')
    mid = r.mission()
    r.settle()
    m = r.m(mid)
    assert r.plans(mid) == [] and m.state == 'BLOCKED'
    assert m.planning_blocked['kind'] == 'challenge'
    assert m.planning_blocked['conflicts'] == [
        {'ref': {'kind': 'knowledge_item', 'id': dec}, 'why': 'it bypasses the rule'}]
    assert [x for x in r.all(entities.Message) if x.cards
            and x.cards[0]['type'] == 'challenge']


# ── I14–I17 versions, revision, replanning, the budget ──

def test_i14_a_version_records_its_identity_lineage_and_provenance(make):
    r = make([fake(ONE)])
    mid = r.mission()
    r.settle()
    (p,) = r.plans(mid)
    (e,) = r.events('plan.created')
    assert e['payload'] == {
        'mission_id': mid, 'plan_version': 1, 'supersedes_plan_id': None,
        'round_seq': p.round_seq, 'digest': p.digest, 'route_decision_id': p.route_decision_id,
        'context_package_id': p.context_package_id, 'tasks': 1, 'serialised': 0}
    assert p.digest == validate.digest(p, r.tasks(p.id))


def test_i15_request_changes_revises_the_plan_into_a_new_version(make):
    f = fake(ONE, answer(task('a'), task('b', depends_on=['a'])))
    r = make([f])
    mid = r.mission()
    r.settle()
    r.run(r.missions.request_changes, mission_id=mid, reason='split it into two steps')
    r.settle()
    v1, v2 = r.plans(mid)
    assert (v1.state, v2.state, v2.supersedes_plan_id) == ('SUPERSEDED', 'PROPOSED', v1.id)
    assert [e['payload']['to'] for e in r.events('plan.state_changed')] == [
        'PROPOSED', 'PROPOSED', 'SUPERSEDED']
    prompt = f.sent[-1][1]
    assert 'split it into two steps' in prompt and 'Previous plan v1' in prompt


def test_i16_i17_a_failing_task_replans_until_the_budget_blocks_before_any_call(make):
    f = fake(ONE)
    r = make([f], policy='ALLOW')
    r.scenarios['t1'] = [{'exit': 1}]
    mid = r.mission()
    r.settle()
    m = r.m(mid)
    assert [p.plan_version for p in r.plans(mid)] == [1, 2, 3]
    assert [p.state for p in r.plans(mid)] == ['SUPERSEDED', 'SUPERSEDED', 'PROPOSED']
    assert (m.state, m.held_from) == ('BLOCKED', 'REPLANNING')
    assert len(r.rds()) == 3                  # the refused fourth plan was never asked for
    assert 'failed: execution' in f.sent[1][1]
    (blocked,) = [e for e in r.events('mission.state_changed')
                  if e['payload']['trigger'] == 'replan_budget_exhausted']
    assert blocked['payload']['guard']['name'] == 'replan_budget_exhausted'


# ── I18–I22 idempotency and the model call ──

def test_i18_a_round_is_planned_once_whatever_is_replayed(make, db):
    f = fake(ONE)
    r = make([f])
    mid = r.mission()
    r.settle()
    (p,) = r.plans(mid)
    assert r.planner.plan(mid, p.round_seq, 'again').startswith('skip')
    with db.read() as conn:                                     # redeliver every event
        every = [outbox.decode(x) for x in conn.execute('SELECT * FROM events ORDER BY seq')]
    for e in every:
        r.planner._handle(e)
    r.settle()
    assert len(r.plans(mid)) == 1 and len(f.sent) == 1
    with pytest.raises(Exception, match='UNIQUE'):             # and the database refuses a race
        r.sys(_same_round, mission_id=mid, round_seq=p.round_seq)


def _same_round(tx, *, actor, mission_id, round_seq):
    tx.insert(entities.Plan(id=ids.new_id('plan'), mission_id=mission_id, plan_version=99,
                            round_seq=round_seq), actor=actor)
    return {}


def test_i19_invalid_model_output_is_retried_once_then_refused(make):
    r = make([fake({'text': 'not json at all'}, {'summary': 'no tasks key'})])
    mid = r.mission()
    r.settle()
    assert r.plans(mid) == []
    (rd,) = r.rds()
    assert (rd.outcome['state'], rd.outcome['attempts']) == ('invalid', 2)
    assert r.m(mid).planning_blocked['outcome'] == 'invalid'


def test_i20_a_second_attempt_that_holds_is_recorded(make):
    cyclic = answer(task('a', depends_on=['a']))
    r = make([fake(cyclic, ONE)])
    mid = r.mission()
    r.settle()
    (p,) = r.plans(mid)
    (rd,) = r.rds()
    assert (rd.outcome['state'], rd.outcome['attempts'], p.route_decision_id) == (
        'ok', 2, rd.id)


@pytest.mark.parametrize('structured', ['native', 'prompted'])
def test_i21_i22_native_and_prompted_structured_output_plan_alike(make, structured):
    f = fake(ONE, structured=structured)
    r = make([f])
    mid = r.mission()
    r.settle()
    (p,) = r.plans(mid)
    assert [t.key for t in r.tasks(p.id)] == ['t1']
    (rd,) = r.rds()
    assert rd.candidates[0]['structured_output'] == structured
    assert ('"tasks"' in f.sent[0][1]) is (structured == 'prompted')     # the schema, prompted


def test_i23_any_headless_harness_plans_and_the_choice_is_recorded(make):
    a, b = fake(ONE, id_='alpha'), fake(ONE, id_='beta')
    talker = FakeCaller('gamma', headless=False)
    r = make([a, b, talker], preference=ports.FixedOwnCallPreference(harness='beta'))
    mid = r.mission()
    r.settle()
    (rd,) = r.rds()
    assert rd.selected == 'beta' and a.sent == [] and len(b.sent) == 1
    steps = {c['resource']: c['eliminated_at_step'] for c in rd.candidates}
    assert steps == {'alpha': 'election', 'beta': None, 'gamma': 'headless'}
    assert r.plans(mid)[0].route_decision_id == rd.id


def test_i24_the_provider_terms_gate_holds_planning_until_the_user_answers(make):
    gated = Real('pi', replies={'planner': [{'parsed': ONE}]})
    r = make([gated])
    mid = r.mission()
    r.settle()
    m = r.m(mid)
    assert gated.sent == [] and r.plans(mid) == []
    assert (m.state, m.planning_blocked['outcome']) == ('REASONING', 'gated')
    r.run(C.decide_provider_terms, harness_id='pi', headless='permitted')
    r.settle()
    (p,) = r.plans(mid)
    assert len(gated.sent) == 1 and p.state == 'PROPOSED'


# ── I25–I26 no execution, and a version never changes ──

def test_i25_a_planning_round_starts_nothing(make):
    r = make([fake(ONE)], policy='ALLOW')
    mid = r.mission()
    r.to_reasoning(mid)
    seq = [e['seq'] for e in r.events('mission.state_changed')
           if e['payload']['to'] == 'REASONING'][-1]
    assert r.planner.plan(mid, seq, 'first plan').startswith('plan:')
    (p,) = r.plans(mid)
    assert [t.state for t in r.tasks(p.id)] == ['PENDING']
    for cls in (entities.Execution, entities.Verification, entities.Review):
        assert r.all(cls) == []
    assert {rd.purpose for rd in r.all(entities.RouteDecision)} == {'planner'}
    assert r.m(mid).state == 'APPROVED'       # the P3 stub gate decided the MISSION
    assert p.state == 'PROPOSED'              # the plan itself is only ready for policy


def test_i26_a_recorded_version_is_preserved_exactly(make, db):
    r = make([fake(ONE, answer(task('again')))])
    mid = r.mission()
    r.settle()
    r.run(r.missions.request_changes, mission_id=mid, reason='again')
    r.settle()
    v1, v2 = r.plans(mid)
    t1 = r.tasks(v1.id)
    assert v1.digest == validate.digest(v1, t1) and v2.digest != v1.digest

    def edit_plan(tx, *, actor):
        tx.update(entities.Plan, v1.id, {'summary': 'rewritten'}, actor=actor)

    def edit_task(tx, *, actor):
        tx.update(entities.Task, t1[0].id, {'objective': 'something else'}, actor=actor)

    def move_with_fields(tx, *, actor):
        lifecycle.fire(tx, entities.Plan, v2.id, 'superseded', actor=actor, reason='x',
                       fields={'summary': 'rewritten'})

    for command in (edit_plan, edit_task, move_with_fields):
        with pytest.raises(ValueError, match='frozen'):
            r.sys(command)
    assert r.plans(mid)[0] == v1 and r.tasks(v1.id) == t1
    with pytest.raises(Exception):
        r.sys(r.work.dispatch_task, task_id=t1[0].id)       # a superseded version never runs
