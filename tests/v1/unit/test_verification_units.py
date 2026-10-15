"""P13's pure parts (p13-design-gate §8.4, §13, §14.3): checks to a verdict,
criteria readings, coverage, the `verified` guard over several criteria, and
review independence."""

from types import SimpleNamespace

from archeus.core.application import verification as V
from archeus.core.domain import guards
from archeus.core.verification import reviewer


def _c(result, kind='command'):
    return {'name': kind, 'kind': kind, 'result': result}


def test_a_failing_check_fails_whatever_else_passed_or_errored():
    assert V.verdict_of([_c('pass'), _c('error'), _c('fail')]) == 'FAILED'
    assert V.verdict_of([_c('fail', 'git'), _c('pass')]) == 'FAILED'


def test_an_error_is_never_a_pass():
    assert V.verdict_of([_c('pass'), _c('error')]) == 'ERROR'


def test_no_outcome_check_is_never_a_pass():
    assert V.verdict_of([]) == 'ERROR'
    assert V.verdict_of([_c('pass', 'git')]) == 'ERROR'      # a diff is not an outcome
    assert V.verdict_of([_c('pass'), _c('pass', 'git')]) == 'PASSED'


def test_readings_touch_automatic_criteria_only():
    crit = [{'check': 'automatic'}, {'check': 'human', 'result': 'unknown'}]
    assert [c['result'] for c in V.readings(crit, 'PASSED')] == ['satisfied', 'unknown']
    assert [c['result'] for c in V.readings(crit, 'FAILED')] == ['failed', 'unknown']
    assert [c['result'] for c in V.readings(crit, 'ERROR')] == ['unknown', 'unknown']


def test_a_task_succeeds_only_when_every_criterion_is_satisfied():
    t = SimpleNamespace(acceptance=[{}, {}])
    v = SimpleNamespace(state='PASSED', criteria=({'index': 0, 'result': 'satisfied'},))
    assert V.uncovered(t, [v]) == [1]
    v2 = SimpleNamespace(state='PASSED', criteria=({'index': 1, 'result': 'satisfied'},))
    assert V.uncovered(t, [v, v2]) == []


def test_every_automatic_criterion_must_pass_not_only_the_first():
    f = guards.MissionFacts(criteria=(guards.CriterionFact('automatic', 'PASSED'),
                                      guards.CriterionFact('automatic', None)))
    assert not guards.verified(None, f).passed


def test_a_review_is_independent_only_of_another_resource_or_model():
    ran = [('fake', 'acc_1', 'm-large')]
    assert not reviewer.independent(('fake', 'acc_1', 'm-large'), ran)
    assert not reviewer.independent(('fake', 'acc_1', None), ran)    # unknown model: same
    assert reviewer.independent(('fake', 'acc_1', 'm-small'), ran)   # another model
    assert reviewer.independent(('fake', 'acc_2', 'm-large'), ran)   # another account
    assert reviewer.independent(('claude', 'acc_1', 'm-large'), ran)
    assert reviewer.forbidden(ran + [('fake', None, 'x')]) == {'accounts': ['acc_1']}
