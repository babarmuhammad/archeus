"""P8 units (p8-design-gate §21.2, U01–U06): Core's validator, the cost band,
the serialisation of overlapping parallel tasks, key assignment and handle
checks, the frozen fields, and the phase boundaries (E1–E4) that keep policy,
routing, execution, continuity, verification, review and automation out of the
plan engine."""

import ast
import os
import subprocess
import sys

import pytest

from archeus.core.domain import entities, guards, shapes
from archeus.core.planning import planner, validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
OK = [{'text': 'works', 'check': 'automatic'}]


def t(key, **kw):
    return dict({'key': key, 'title': 'T %s' % key, 'objective': 'do %s' % key,
                 'kind': 'code_change', 'depends_on': (), 'action_classes': ('write_repo',),
                 'acceptance': OK}, **kw)


# ── U01 the structural contract, rule by rule ──

@pytest.mark.parametrize('tasks, kw, problem', [
    ([], {}, 'at least one task'),
    ([t('a'), t('a', title='other')], {}, 'labels repeat: a'),
    ([t('a', depends_on=('a',))], {}, 'depends on itself'),
    ([t('a', depends_on=('z',))], {}, 'depends on z, which is not in the plan'),
    ([t('a', depends_on=('b',)), t('b', depends_on=('c',)), t('c', depends_on=('a',))], {},
     'the dependencies form a cycle: a -> b -> c -> a'),
    ([t('a', kind='dance')], {}, 'unknown kind'),
    ([t('a', action_classes=('teleport',))], {}, 'unknown action classes'),
    ([t('a', capabilities_required=('telepathy',))], {}, 'unknown capabilities'),
    ([t('a', min_model_tier='huge')], {}, 'unknown model tier'),
    ([t('a', estimate=9)], {}, 'estimate outside 1-5'),
    ([t('a', estimate=True)], {}, 'estimate outside 1-5'),
    ([t('a', acceptance=())], {}, 'no acceptance criterion'),
    ([t('a', kind='human', acceptance=OK)], {}, 'human task, so its acceptance is human'),
    ([t('a'), t('b', title='T a', objective='do a')], {}, 'are the same task'),
    ([t('a')], {'explicit': ('r1',)}, 'explicit requirement r1 is served by no task'),
    ([t('a', kind='human', acceptance=[{'text': 'ok', 'check': 'human'}], action_classes=())],
     {'criteria': [{'text': 'x', 'check': 'automatic'}]}, 'needs at least one non-human task'),
])
def test_u01_every_structural_rule_refuses_its_defect(tasks, kw, problem):
    found = validate.problems(tasks, **kw)
    assert any(problem in p for p in found), found


def test_u01_a_valid_plan_has_no_problems_and_coverage_can_be_asked_about():
    tasks = [t('a', serves=('r1',)), t('b', depends_on=('a',)),
             t('h', kind='human', acceptance=[{'text': 'ok', 'check': 'human'}])]
    assert validate.problems(tasks, explicit=('r1',)) == []
    assert validate.problems([t('a')], explicit=('r1',), asked={'r1'}) == []
    assert validate.problems([t(str(i), title=str(i)) for i in range(51)])[0].startswith(
        'a plan has at most 50')


# ── U02 the cost band is Core's (D9, frozen thresholds) ──

@pytest.mark.parametrize('tasks, band', [
    ([t('a')], 'low'),                                                  # mid 2 x 1
    ([t('a', min_model_tier='mid', estimate=3)], 'low'),                # 6: the ceiling
    ([t('a', min_model_tier='large', estimate=2)], 'medium'),           # 8
    ([t('a', min_model_tier='large', estimate=5)], 'medium'),           # 20: the ceiling
    ([t('a', min_model_tier='large', estimate=5), t('b', min_model_tier='small')], 'high'),
])
def test_u02_the_band_is_the_sum_of_tier_times_estimate(tasks, band):
    assert validate.cost_band(tasks) == band
    assert validate.BAND_CEILINGS == (('low', 6), ('medium', 20))
    assert validate.TIER_WEIGHT == {'small': 1, 'mid': 2, 'large': 4}


# ── U03 serialisation (D8) ──

@pytest.mark.parametrize('a, b, hit', [
    ('src/x.py', 'src/x.py', True), ('src/**', 'src/x.py', True), ('src/x*', 'src/*y', True),
    ('src\\x.py', 'src/x.py', True), ('src/a.py', 'src/b.py', False),
    ('src/*', 'docs/*', False), ('docs/**', 'src/x.py', False),
])
def test_u03_touches_overlap_conservatively(a, b, hit):
    assert validate.overlap(a, b) is hit and validate.overlap(b, a) is hit


def test_u03_only_unordered_overlapping_tasks_are_serialised_with_their_reason():
    tasks = [t('a'), t('b', depends_on=('a',), touches=('src/**',)),
             t('c', depends_on=('a',), touches=('src/c.py',)),
             t('d', depends_on=('b',), touches=('src/**',)),         # after b, beside c
             t('e', touches=('docs/**',))]
    out, added = validate.serialise(validate.order(tasks))
    assert added == [{'task': 'c', 'after': 'b', 'because': 'touches overlap: src/** ~ src/c.py'},
                     {'task': 'd', 'after': 'c', 'because': 'touches overlap: src/c.py ~ src/**'}]
    deps = {x['key']: x['depends_on'] for x in out}
    assert deps['c'] == ('a', 'b') and deps['d'] == ('b', 'c') and deps['e'] == ()
    assert validate.find_cycle(out) is None


def test_u03_order_and_waves_follow_the_graph_stably():
    tasks = [t('c', depends_on=('a', 'b')), t('a'), t('b', depends_on=('a',)), t('x')]
    assert [x['key'] for x in validate.order(tasks)] == ['a', 'b', 'c', 'x']
    assert validate.waves(tasks) == [['a', 'x'], ['b'], ['c']]


# ── U04 the planner's answer: handles, labels, keys ──

FACTS = {'r1': {'kind': 'requirement', 'origin': 'explicit', 'text': 'a flag'},
         'r2': {'kind': 'requirement', 'origin': 'inferred', 'text': 'it prints'},
         'c1': {'kind': 'constraint', 'origin': 'explicit', 'text': 'no new deps'},
         'p1': {'kind': 'project', 'id': 'prj_x'},
         'k1': {'kind': 'knowledge_item', 'id': 'kni_x', 'ktype': 'DECISION',
                'state': 'CONFIRMED'},
         'k2': {'kind': 'knowledge_item', 'id': 'kni_y', 'ktype': 'FACT', 'state': 'CONFIRMED'}}


def pt(id_, **kw):
    return dict({'id': id_, 'title': 'T %s' % id_, 'kind': 'code_change',
                 'objective': 'do %s' % id_, 'expected_output': 'out', 'acceptance': OK}, **kw)


def test_u04_handles_are_checked_where_they_are_used():
    bad = planner.check({'summary': 's', 'tasks': [
        pt('a', refs=['r1'], serves=['p1', 'r1'],
           inputs=[{'from_task': 'nope', 'what': 'x'}, {'ref': 'k9', 'what': 'y'},
                   {'what': 'z'}])],
        'conflicts': [{'ref': 'k2', 'why': 'x'}], 'refs': ['q1']}, FACTS)
    text = '\n'.join(bad)
    for needle in ("refs[0]: 'r1' is not a world handle", "serves[0]: 'p1' is not a requirement",
                   "comes from 'nope'", "inputs[1].ref: 'k9'", 'exactly one of from_task',
                   "'k2' is not a CONFIRMED decision", "refs[0]: 'q1'"):
        assert needle in text, needle


def test_u04_core_keys_the_tasks_and_resolves_every_handle():
    parsed = {'summary': 's', 'tasks': [
        pt('ship', depends_on=['build'], serves=['r1'],
           inputs=[{'from_task': 'build', 'what': 'the build'}]),
        pt('build', refs=['p1'], serves=['r1'])],
        'assumptions': [{'text': 'x', 'about': 'p1'}, {'text': 'y', 'about': 'r2'}],
        'questions': [{'question': 'docs too?', 'blocking': False}]}
    assert planner.check(parsed, FACTS) == []
    spec, explicit, asked = planner.resolve(parsed, FACTS)
    assert [(x['key'], x['title'], x['depends_on']) for x in spec['tasks']] == [
        ('t1', 'T build', []), ('t2', 'T ship', ['t1'])]
    assert spec['tasks'][0]['refs'] == [{'kind': 'project', 'id': 'prj_x'}]
    assert spec['tasks'][1]['inputs'] == [{'what': 'the build', 'from_task': 't1'}]
    assert spec['tasks'][0]['workspace_mode'] == 'worktree'
    assert spec['assumptions'] == [
        {'text': 'x', 'origin': 'inferred', 'about': {'kind': 'project', 'id': 'prj_x'}},
        {'text': 'y', 'origin': 'inferred', 'about': 'r2'}]
    assert [(c['requirement'], c['tasks']) for c in spec['coverage']] == [
        ('r1', ['t1', 't2']), ('r2', [])]
    assert explicit == ['r1'] and asked == [] and 'estimated_cost' not in spec


def test_u04_a_blocking_answer_is_judged_on_its_handles_only():
    ask = {'summary': 's', 'tasks': [],
           'questions': [{'question': 'which one?', 'blocking': True, 'about': 'r1'}]}
    assert planner.check(ask, FACTS) == []
    assert planner.blocking(ask)['kind'] == 'clarification'
    against = dict(ask, questions=[], conflicts=[{'ref': 'k1', 'why': 'no'}])
    assert planner.blocking(against)['kind'] == 'challenge'
    assert planner.blocking({'summary': 's', 'tasks': [pt('a')]}) is None


def test_u04_the_schema_has_no_cost_band_and_every_field_is_bounded():
    shapes.validate({'summary': 's', 'tasks': [pt('a', estimate=2)]}, planner.SCHEMA)
    with pytest.raises(shapes.Invalid):
        shapes.validate({'summary': 's', 'tasks': [], 'estimated_cost': 'low'}, planner.SCHEMA)
    assert 'Do not state a cost band' in planner.PREFIX


# ── U05 frozen fields and the ready guard ──

def test_u05_a_plan_is_frozen_but_its_state_and_a_task_keeps_its_lifecycle():
    assert entities.Plan.frozen_fields() == {f for f in entities.Plan.__dataclass_fields__
                                            if f != 'state'}
    frozen = entities.Task.frozen_fields()
    assert 'state' not in frozen and 'failure_class' not in frozen
    assert {'depends_on', 'acceptance', 'objective', 'touches'} <= frozen


def test_u05_ready_needs_no_problem_and_a_matching_digest():
    p = entities.Plan(id='pln_01M3DGX0000000000000000000', mission_id='msn_01M3DGX0000000000000000000',
                      digest='a' * 64)
    assert guards.ready(p, guards.PlanFacts(digest='a' * 64)).passed
    assert not guards.ready(p, guards.PlanFacts(problems=('x',), digest='a' * 64)).passed
    assert not guards.ready(p, guards.PlanFacts(digest='b' * 64)).passed
    assert not guards.ready(entities.Plan(id=p.id, mission_id=p.mission_id),
                            guards.PlanFacts()).passed


# ── U06 phase boundaries (E1–E4) ──

P8_FILES = [os.path.join(ROOT, 'archeus', 'core', 'planning', f)
            for f in ('__init__.py', 'planner.py', 'validate.py', 'worker.py')] + [
    os.path.join(ROOT, 'archeus', 'core', 'application', 'planning.py')]
#: E1: what the plan engine never imports
BANNED_IMPORTS = ('harnesses', 'engine', 'runtime', 'api', 'policy', 'routing', 'router',
                  'execution', 'node', 'verification', 'automation', 'subprocess', 'llmcall',
                  'ports', 'registry')
#: E2/E3: what it never calls or names
BANNED_CALLS = ('evaluate', 'route', 'start', 'stop', 'verify', 'review', 'dispatch_task',
                'ready_tasks', 'record_spawn', 'record_exit', 'record_task_verification',
                'verify_mission', 'record_review', 'advance')
BANNED_TRIGGERS = ('approved', 'rejected', 'plan_auto_approved', 'plan_needs_approval',
                   'dispatch', 'deps_satisfied', 'routed', 'accepted', 'approve')


def _trees():
    for path in P8_FILES:
        yield path, ast.parse(open(path, encoding='utf-8').read())


def test_u06_e1_the_plan_engine_imports_no_later_phase_provider_or_process():
    for path, tree in _trees():
        for n in ast.walk(tree):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for name in [a.name for a in n.names] + [getattr(n, 'module', None) or '']:
                    assert not any(b in name.split('.') for b in BANNED_IMPORTS), (path, name)


def test_u06_e2_e3_it_never_authorises_routes_executes_verifies_or_reviews():
    for path, tree in _trees():
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(
                    n.func, 'id', '')
                assert name not in BANNED_CALLS, (path, name)
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                assert n.value not in BANNED_TRIGGERS, (path, n.value)
            if isinstance(n, ast.Name):
                assert n.id not in ('Policy', 'AllowAllPolicy', 'FixedPolicy'), (path, n.id)


def test_u06_e4_importing_the_plan_engine_loads_no_harness_runner_or_process():
    code = ('import sys; import archeus.core.planning.worker, archeus.core.application.planning; '
            "bad=[m for m in sys.modules if m.split('.')[-1] in ('llmcall','rotate','quota',"
            "'gui_api','engine','runtime','subprocess') or m.startswith('archeus.harnesses.calls')"
            " or m.startswith('archeus.api')]; print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ── plan §31.1 P8: plans for all judge scenarios validate ──

def test_every_recorded_judge_plan_passes_cores_validation():
    import json
    rec = json.load(open(os.path.join(ROOT, 'tests', 'v1', 'fixtures', 'brain',
                                      'recordings.json'), encoding='utf-8'))
    s1 = {'r1': {'kind': 'requirement', 'origin': 'explicit', 'text': 'a --version flag'},
          'r2': {'kind': 'requirement', 'origin': 'inferred', 'text': 'it prints it'}}
    assert rec['planner']
    for entry in rec['planner']:
        facts = s1 if '--version' in entry.get('when', '') else {}
        shapes.validate(entry['parsed'], planner.SCHEMA)
        assert planner.check(entry['parsed'], facts) == [], entry.get('when', 'default')
        assert planner.blocking(entry['parsed']) is None
