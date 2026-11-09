"""Effort per task (resource-router §6): the planner's table, the validator, the
router's clamp to what a model accepts, and the per-model outcome log's shape.
The pure half; test_effort_routing runs the same through the rig."""

import pytest

from archeus.core.application import resources
from archeus.core.domain import entities
from archeus.core.planning import planner, validate
from archeus.core.routing import router as R
from archeus.harnesses import base, calls
from v1.unit.test_planning_units import OK, t
from v1.unit.test_routing_units import call, harness, own, snap


@pytest.mark.parametrize('kind, estimate, effort', [
    ('code_change', 3, 'medium'), ('code_change', 4, 'high'), ('research', 5, 'high'),
    ('document', 2, 'low'), ('presentation', 5, 'medium'), ('inspection', 5, 'low'),
    ('verification', 1, 'low'), ('human', 3, None)])
def test_the_effort_table_reads_kind_and_size(kind, estimate, effort):
    assert validate.effort_for(kind, estimate) == effort


def test_every_kind_the_table_names_is_a_task_kind_and_every_effort_is_on_the_scale():
    assert set(validate.EFFORT_BY_KIND) <= set(entities.TASK_KINDS)
    assert {e for pair in validate.EFFORT_BY_KIND.values() for e in pair} <= set(entities.EFFORTS)
    assert R.EFFORTS == entities.EFFORTS


def test_the_planner_sets_effort_from_the_table_and_never_from_the_models_answer():
    facts = {}
    parsed = {'summary': 's', 'tasks': [
        dict(t('a', estimate=5), id='a', expected_output='o', effort='max'),
        dict(t('b', kind='document'), id='b', expected_output='o')]}
    spec = planner.resolve(parsed, facts)[0]
    assert [x['effort'] for x in spec['tasks']] == ['high', 'low']
    assert 'effort' not in planner.SCHEMA['properties']['tasks']['items']['properties']


def test_the_validator_refuses_an_effort_off_the_scale():
    assert validate.problems([t('a', effort='high')]) == []
    assert validate.problems([t('a', effort=None)]) == []
    assert any('unknown effort' in p for p in validate.problems([t('a', effort='turbo')]))
    with pytest.raises(ValueError, match='effort must be one of'):
        entities.Task(id='tsk_01J0000000000000000000000A', plan_id='pln_01J0000000000000000000000A',
                      mission_id='msn_01J0000000000000000000000A', key='t', title='T',
                      kind='research', effort='turbo', acceptance=tuple(OK))


@pytest.mark.parametrize('effort, allowed, lower, fitted', [
    ('high', {'low', 'medium', 'high'}, False, 'high'),
    ('xhigh', {'low', 'medium', 'high'}, False, 'high'),
    ('high', {'low', 'medium'}, False, 'medium'),
    ('low', {'medium', 'high'}, False, 'medium'),
    ('medium', {'low', 'medium', 'high'}, True, 'low'),
    ('high', {'low', 'high'}, True, 'low'),
    ('low', {'low', 'medium'}, True, 'low')])
def test_fit_clamps_to_the_allowed_set_and_lowers_one_step(effort, allowed, lower, fitted):
    assert R.fit(effort, allowed, lower) == fitted


def _model(efforts, **kw):
    h = harness('h', efforts=('low', 'medium', 'high'), models=('m:mid',))
    h['models'][0]['efforts'] = list(efforts)
    return snap([h], [own('h')]), kw


def test_the_router_clamps_effort_to_the_chosen_model_and_records_it():
    s, _ = _model(('low', 'medium'))
    assert R.route(call(effort='high', min_model_tier='mid'), s)['effort'] == 'medium'
    assert R.route(call(effort='low', min_model_tier='mid'), s)['effort'] == 'low'
    # a model that states no efforts takes what its harness does
    s, _ = _model(())
    assert R.route(call(effort='high', min_model_tier='mid'), s)['effort'] == 'high'


def test_a_required_effort_the_model_cannot_take_eliminates_it():
    s, _ = _model(('low', 'medium'))
    d = R.route(call(effort='high', effort_required=True, min_model_tier='mid'), s)
    assert d['selected'] is None
    assert 'does not accept effort high' in d['candidates'][0]['reason']


def test_a_snapshot_names_a_models_efforts_only_when_it_states_some():
    caps = base.Capabilities(frozenset(), 'hook', (base.ModelInfo('a', 'mid'),
                                                   base.ModelInfo('b', 'mid', efforts=('low',))))
    assert resources._models(caps) == [
        {'id': 'a', 'tier': 'mid', 'context_window': None},
        {'id': 'b', 'tier': 'mid', 'context_window': None, 'efforts': ['low']}]


def test_claude_models_carry_the_efforts_the_catalogue_gives_and_an_alias_its_familys(monkeypatch):
    from claude_sessions import models
    monkeypatch.setattr(models, 'roster', lambda: [
        {'id': 'claude-sonnet-5', 'family': 'sonnet', 'efforts': ['low', 'medium', 'high']},
        {'id': 'claude-haiku-4-5', 'family': 'haiku', 'efforts': []}])
    by = {m.id: m.efforts for m in calls.claude_models()}
    assert by['sonnet'] == by['claude-sonnet-5'] == ('low', 'medium', 'high')
    assert by['haiku'] == by['claude-haiku-4-5'] == () and by['opus'] == ()

