"""P14 units (p14-design-gate §7, §10, §17): the matcher, templates, the
suspension rule, and the phase boundary B1–B3."""

import ast
import os

import pytest

from archeus.core.automation import matcher as M
from archeus.core.domain import events

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
P14 = ('archeus/core/automation/matcher.py', 'archeus/core/automation/worker.py',
       'archeus/core/application/automations.py')
TYPES = set(events.REGISTRY)


def _imports(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        tree = ast.parse(f.read())
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            out |= {'.' * n.level + (n.module or '') + '.' + a.name for a in n.names}
        elif isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
    return out


# ── matching (E04) ──

def _trigger(**where):
    return M.validate_trigger({'type': 'repository.model_added', 'where': where}, TYPES)


def test_E04_matching_is_deterministic_and_explains_itself():
    t = _trigger(path={'not_glob': 'tests/*'}, revision='abc')
    payload = {'revision': 'abc', 'path': 'billing/models/invoice.py', 'extra': 1}
    first = M.matches(t, 'repository.model_added', payload)
    for _ in range(5):
        assert M.matches(t, 'repository.model_added', dict(reversed(list(payload.items())))) \
            == first
    assert first == (True, {'type': 'repository.model_added', 'where': {
        'path': {'test': {'not_glob': 'tests/*'}, 'value': 'billing/models/invoice.py'},
        'revision': {'test': 'abc', 'value': 'abc'}}})


def test_a_predicate_tests_type_value_and_glob_exactly():
    t = _trigger(path={'glob': 'app/*'}, n=1)
    assert M.matches(t, 'repository.model_added', {'path': 'app/x.py', 'n': 1})[0]
    assert not M.matches(t, 'repository.file_added', {'path': 'app/x.py', 'n': 1})[0]
    assert not M.matches(t, 'repository.model_added', {'path': 'lib/x.py', 'n': 1})[0]
    assert not M.matches(t, 'repository.model_added', {'path': 'app/x.py', 'n': True})[0]
    assert not M.matches(t, 'repository.model_added', {'path': 'app/x.py', 'n': '1'})[0]
    assert not M.matches(t, 'repository.model_added', {'n': 1})[0]      # absent: no glob hit


@pytest.mark.parametrize('trigger, why', [
    ({'type': 'no.such_type'}, 'not a registered'),
    ({'type': 'automation_run.state_changed'}, 'loop by construction'),     # D10
    ({'type': 'automation.created'}, 'loop by construction'),
    ({'type': 'automation.schedule_due'}, 'loop by construction'),         # P21 D9
    ({'kind': 'condition', 'type': 'mission.created'}, 'not built'),       # D14
    ({'type': 'mission.created', 'where': {'a.b': 1}}, 'top-level'),
    ({'type': 'mission.created', 'where': {'a': [1]}}, 'string, number'),
    ({'type': 'mission.created', 'where': {'a': {'regex': '.*'}}}, 'glob'),
    ({'type': 'mission.created', 'cron': '* * * * *'}, 'has no'),
    ({'kind': 'schedule', 'type': 'mission.created', 'every': '1h'}, 'has no'),
    ({'kind': 'schedule', 'every': '* * * * *'}, 'count and a unit'),
    ({'kind': 'schedule', 'every': 15}, 'count and a unit'),
    ({'kind': 'schedule', 'every': '30s'}, 'once a minute'),
    ({'kind': 'schedule', 'every': '0m'}, 'once a minute'),
])
def test_a_trigger_that_cannot_be_written_is_refused(trigger, why):
    with pytest.raises(M.Invalid, match=why):
        M.validate_trigger(trigger, TYPES)


# ── schedule triggers (P21 slice H, p21-design-gate D9) ──

@pytest.mark.parametrize('every, stored, seconds', [
    ('15m', '15m', 900), (' 2 h ', '2h', 7200), ('1d', '1d', 86400), ('90', '90m', 5400),
    ('60s', '60s', 60), ('007m', '7m', 420),
])
def test_a_schedule_takes_the_legacy_loops_interval_grammar(every, stored, seconds):
    t = M.validate_trigger({'kind': 'schedule', 'every': every}, TYPES)
    assert t == {'kind': 'schedule', 'every': stored} and M.every_s(t) == seconds


def test_the_next_time_is_the_first_on_the_grid_after_now():
    assert M.next_due(1000, 60, 999) == 1000                # not due yet: unchanged
    assert M.next_due(1000, 60, 1000) == 1060               # due now: one period on
    assert M.next_due(1000, 60, 1059.9) == 1060
    assert M.next_due(1000, 60, 1000 + 4.5 * 60) == 1300    # four missed times: one claim


def test_an_event_never_matches_a_schedule_trigger():
    t = M.validate_trigger({'kind': 'schedule', 'every': '1m'}, TYPES)
    assert M.matches(t, 'mission.created', {}) == (False, None)


# ── templates (E11, E14, §13) ──

def test_a_template_is_a_mission_request_and_nothing_else():
    ok = M.validate_template({'title': 'Doc {payload.path}', 'objective': 'o {event.seq}'})
    assert ok == {'title': 'Doc {payload.path}', 'objective': 'o {event.seq}',
                  'success_criteria': []}
    for key in ('model', 'harness', 'account', 'verdict', 'approval', 'plan'):
        with pytest.raises(M.Invalid, match='cannot carry'):
            M.validate_template({'title': 't', 'objective': 'o', key: 'x'})
    with pytest.raises(M.Invalid, match='not a placeholder'):
        M.validate_template({'title': '{payload.__class__.mro}', 'objective': 'o'})
    with pytest.raises(M.Invalid, match='needs a title'):
        M.validate_template({'title': ' ', 'objective': 'o'})


def test_a_rendered_value_is_one_short_line_of_data():
    t = M.validate_template({'title': 'Doc {payload.path}', 'objective': '{payload.note}'})
    out = M.render(t, 'repository.model_added', 7, ('repository', 'rep_1'),
                   {'path': 'a\nb\x00c', 'note': 'x' * 500})
    assert out['title'] == 'Doc a b c'
    assert out['objective'] == 'x' * M.MAX_VALUE
    assert M.render(t, 'e', 1, ('k', 'i'), {})['title'] == 'Doc '


# ── the loop guard (§10) ──

def test_three_escalations_or_three_rate_limits_suspend_and_fewer_do_not():
    assert not M.should_suspend([('ESCALATED', 'depth_exceeded')] * 2
                                + [('SKIPPED', 'rate_limited')] * 2)
    assert M.should_suspend([('ESCALATED', 'depth_exceeded')] * 3)
    assert M.should_suspend([('SKIPPED', 'rate_limited')] * 3)
    assert not M.should_suspend([('MISSION_CREATED', 'allowed')] * 50)


# ── boundaries B1–B2 (§17) ──

def test_B1_the_matcher_is_pure():
    assert {i.split('.')[0] for i in _imports(P14[0])} <= {'fnmatch', 're'}


def test_B2_no_p14_module_reaches_routing_execution_sessions_verification_or_a_process():
    bad = ('routing', 'execution', 'sessions', 'verification', 'policy', 'planning',
           'harnesses', 'node', 'subprocess', 'socket', 'urllib', 'http', 'engine', 'calls',
           'brain', 'context')
    for rel in P14:
        for name in _imports(rel):
            parts = set(name.lstrip('.').split('.'))
            assert not parts & set(bad), (rel, name)
