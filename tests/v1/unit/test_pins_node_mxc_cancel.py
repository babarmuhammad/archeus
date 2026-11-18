"""Hand-mutant pins for archeus/node/mxc_cancel.py (T-812).

Each test names one condition in that module and goes red when the condition is
inverted, removed or loosened. Injected callables only: no MXC, no Win32, no
subprocess, no ledger, no network.
"""

import time

import pytest

from archeus.node import mxc_cancel as cancel_mod

EXECUTION = object()

STEPS = ('revoke_admission', 'end_job', 'wait_quiescent', 'read_back_resources')

FACT_KEYS = ['faults', 'order', 'owned', 'prior', 'quiescent', 'read_back', 'wait_s']

DEFAULT = object()


class Ratio(float):
    pass


NON_TEXT_IDS = [pytest.param((b'res-1',), id='bytes'),
                pytest.param((1,), id='int'),
                pytest.param(('res-1', 2), id='mixed'),
                pytest.param(('res-1', ''), id='blank-id'),
                pytest.param((object(),), id='object')]

NON_VERDICT_PRIORS = [pytest.param('MAYBE', id='word'),
                      pytest.param('DISPOSED', id='prefix'),
                      pytest.param('DISPOSED_VERIFIED ', id='padded'),
                      pytest.param(1, id='one'),
                      pytest.param(True, id='true')]

NOT_A_BOUND = [pytest.param('5', id='str'),
               pytest.param(None, id='none'),
               pytest.param(True, id='true'),
               pytest.param(False, id='false'),
               pytest.param(Ratio(1.0), id='float-subclass')]


def fresh(text):
    # built at run time, never interned: a ledger that reads a verdict back from disk
    # hands back an equal object, and comparing verdicts by identity would miss it
    parts = text.split('_')
    joined = '_'.join(parts)
    assert joined is not text
    return joined


class Ledger:
    def __init__(self, seen, prior=None):
        self.seen = seen
        self.prior = prior
        self.writes = []
        self.factsets = []

    def __call__(self, execution, verdict, facts):
        assert execution is EXECUTION
        self.seen['calls'].append('lookup' if verdict is None else 'record')
        if verdict is None:
            assert facts is None
            return self.prior
        self.writes.append(verdict)
        self.factsets.append(facts)
        return verdict


class Clock:
    def __init__(self, *values):
        self.values = list(values)

    def __call__(self):
        return self.values.pop(0) if self.values else 0.0


@pytest.fixture
def seen():
    return {'calls': [], 'deadline': None}


def effect(seen, name, answer=None, boom=None):
    def run(*args):
        assert args[0] is EXECUTION
        seen['calls'].append(name)
        if name == 'wait_quiescent':
            seen['deadline'] = args[1]
        if boom is not None:
            raise boom
        return answer
    return run


def healthy(seen):
    return [effect(seen, 'revoke_admission'),
            effect(seen, 'end_job'),
            effect(seen, 'wait_quiescent', True),
            effect(seen, 'read_back_resources', True)]


def cancel(effects, seen, ledger=None, wait_s=5.0, clock_values=(0.0, 1.0, 2.0)):
    kwargs = {} if wait_s is DEFAULT else {'wait_s': wait_s}
    used = Ledger(seen) if ledger is None else ledger
    return cancel_mod.cancel(EXECUTION, *effects, used, clock=Clock(*clock_values),
                             **kwargs), used


@pytest.mark.parametrize('answer', NON_TEXT_IDS)
def test_a_non_text_ownership_id_never_proves_ownership(seen, answer):
    effects = healthy(seen)
    effects[3] = effect(seen, 'read_back_resources', answer)
    verdict, ledger = cancel(effects, seen)
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert ledger.factsets[0]['faults'] == {'read_back': 'unknown_ownership'}
    assert ledger.factsets[0]['owned'] is None
    assert cancel_mod.DISPOSED_VERIFIED not in ledger.writes


@pytest.mark.parametrize('prior', NON_VERDICT_PRIORS)
def test_a_prior_answer_outside_the_verdicts_is_no_prior_at_all(seen, prior):
    verdict, ledger = cancel(healthy(seen), seen, ledger=Ledger(seen, prior=prior))
    assert verdict == cancel_mod.DISPOSED_VERIFIED
    assert seen['calls'] == ['lookup', *STEPS, 'record']
    assert ledger.factsets[0]['prior'] is None


@pytest.mark.parametrize('position', range(5), ids=['revoke', 'end', 'wait', 'read', 'record'])
def test_every_injected_effect_has_to_be_callable(seen, position):
    effects = healthy(seen) + [Ledger(seen)]
    effects[position] = None
    with pytest.raises(ValueError, match='callable'):
        cancel_mod.cancel(EXECUTION, *effects, clock=Clock(0.0, 1.0, 2.0), wait_s=5.0)


@pytest.mark.parametrize('position', range(4), ids=['revoke', 'end', 'wait', 'read'])
def test_a_non_callable_effect_is_rejected_before_anything_is_called(seen, position):
    effects = healthy(seen) + [Ledger(seen)]
    effects[position] = None
    with pytest.raises(ValueError, match='callable'):
        cancel_mod.cancel(EXECUTION, *effects, clock=Clock(0.0, 1.0, 2.0), wait_s=5.0)
    assert seen['calls'] == []


def test_an_unbounded_wait_is_rejected_before_anything_is_called(seen):
    effects = healthy(seen) + [Ledger(seen)]
    with pytest.raises(ValueError, match='bound'):
        cancel_mod.cancel(EXECUTION, *effects, clock=Clock(0.0, 1.0, 2.0), wait_s=0)
    assert seen['calls'] == []


@pytest.mark.parametrize('wait_s', NOT_A_BOUND)
def test_a_bound_that_is_not_plain_numeric_is_a_programming_error(seen, wait_s):
    effects = healthy(seen) + [Ledger(seen)]
    with pytest.raises(ValueError, match='bound'):
        cancel_mod.cancel(EXECUTION, *effects, clock=Clock(0.0, 1.0, 2.0), wait_s=wait_s)
    assert seen['calls'] == []


@pytest.mark.parametrize('wait_s', [0, -1, -0.5], ids=['zero', 'neg-int', 'neg-float'])
def test_a_bound_that_is_not_positive_is_a_programming_error(seen, wait_s):
    effects = healthy(seen) + [Ledger(seen)]
    with pytest.raises(ValueError, match='bound'):
        cancel_mod.cancel(EXECUTION, *effects, clock=Clock(0.0, 1.0, 2.0), wait_s=wait_s)
    assert seen['calls'] == []


def test_a_wait_that_raises_says_nothing_at_all_about_quiescence(seen):
    effects = healthy(seen)
    effects[2] = effect(seen, 'wait_quiescent', boom=RuntimeError('query refused'))
    verdict, ledger = cancel(effects, seen)
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert ledger.factsets[0]['faults'] == {'wait_quiescent': 'RuntimeError'}
    assert ledger.factsets[0]['quiescent'] is None
    assert seen['calls'] == ['lookup', *STEPS, 'record']


def test_a_recorded_quarantine_does_not_overrule_a_fresh_still_running_finding(seen):
    effects = healthy(seen)
    effects[2] = effect(seen, 'wait_quiescent', False)
    verdict, ledger = cancel(effects, seen,
                             ledger=Ledger(seen, prior=cancel_mod.QUARANTINE_UNVERIFIED))
    assert verdict == cancel_mod.STILL_RUNNING
    assert ledger.writes == [cancel_mod.STILL_RUNNING]
    assert ledger.factsets[0]['prior'] == cancel_mod.QUARANTINE_UNVERIFIED
    assert ledger.factsets[0]['quiescent'] is False


def test_a_quarantine_holds_when_the_ledger_hands_it_back_as_a_fresh_string(seen):
    prior = fresh(cancel_mod.QUARANTINE_UNVERIFIED)
    verdict, ledger = cancel(healthy(seen), seen, ledger=Ledger(seen, prior=prior))
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert ledger.writes == [cancel_mod.QUARANTINE_UNVERIFIED]


def test_a_verified_disposal_short_circuits_when_read_back_as_a_fresh_string(seen):
    prior = fresh(cancel_mod.DISPOSED_VERIFIED)
    verdict, ledger = cancel(healthy(seen), seen, ledger=Ledger(seen, prior=prior))
    assert verdict == cancel_mod.DISPOSED_VERIFIED
    assert seen['calls'] == ['lookup']
    assert ledger.writes == []


def test_the_facts_on_the_record_are_exactly_the_seven_locked_ones(seen):
    verdict, ledger = cancel(healthy(seen), seen)
    facts = ledger.factsets[0]
    assert verdict == cancel_mod.DISPOSED_VERIFIED
    assert sorted(facts) == FACT_KEYS
    assert facts['order'] == [*STEPS, 'record']
    assert facts['faults'] == {}
    assert facts['quiescent'] is True
    assert facts['read_back'] == 'absent'
    assert facts['owned'] is None
    assert facts['prior'] is None
    assert facts['wait_s'] == 5.0


def test_the_default_quiescence_bound_is_five_seconds(seen):
    verdict, ledger = cancel(healthy(seen), seen, wait_s=DEFAULT)
    assert verdict == cancel_mod.DISPOSED_VERIFIED
    assert seen['deadline'] == 5.0
    assert ledger.factsets[0]['wait_s'] == 5.0


def test_the_default_clock_is_the_monotonic_one_never_the_wall_clock(seen):
    # the default is bound at import, so patching time would not reach it: judge the numbers
    effects = healthy(seen)
    before = time.monotonic()
    cancel_mod.cancel(EXECUTION, *effects, Ledger(seen), wait_s=300.0)
    assert seen['deadline'] < time.time()
    assert abs(seen['deadline'] - before - 300.0) < 5.0


def test_owned_ids_are_recorded_as_text_in_a_stable_order(seen):
    effects = healthy(seen)
    effects[3] = effect(seen, 'read_back_resources', ('res-2', 'res-1', 'res-10'))
    verdict, ledger = cancel(effects, seen)
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert ledger.factsets[0]['faults'] == {'read_back': 'still_owned'}
    assert ledger.factsets[0]['owned'] == ['res-1', 'res-10', 'res-2']
