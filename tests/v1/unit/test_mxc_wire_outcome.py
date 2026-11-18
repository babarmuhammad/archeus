# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""T-800: the outcome MxcLaunch reports for a finished execution is the one
bind_outcome binds, never the launcher's exit code. Same fakes as the wire tests."""

import copy

import pytest

from archeus.node import local, mxc_ledger as ledger_mod, mxc_outcome as outcome_mod, staging

from .test_mxc_wire import args, journal_ops, native_parts, wire  # noqa: F401

DIGEST = 'a' * 64
EXPECTED = {'execution_id': 'e1', 'nonce': 'n1', 'digest': DIGEST, 'now': 100.0, 'max_age': 10.0}
GOOD = {'execution_id': 'e1', 'nonce': 'n1', 'payload_digest': DIGEST, 'timestamp': 95.0,
        'status': 'succeeded', 'workload_exit': 0}


def record(**changes):
    return dict(copy.deepcopy(GOOD), **changes)


def bound(wire, reader, expected=lambda: dict(EXPECTED), **options):
    h = wire(reader=lambda execution_id, owner: True, **options)
    h.launch.workload_reader, h.launch.workload_expected = reader, expected
    h.launch.start(job=h.job)
    return h


def raising(exc):
    def reader(process):
        raise exc
    return reader


def no_identity():
    raise OSError('no identity')


def test_a_bound_success_is_the_reported_outcome(wire):
    seen = []
    h = bound(wire, lambda process: (seen.append(process), record())[1])
    assert h.launch.wait() == 0
    assert seen == [h.launch.process]
    assert h.launch.bound.state == outcome_mod.SUCCEEDED
    assert h.launch.completed == 0 and h.launch.end_state['state'] == ledger_mod.DEAD_CLEAN
    assert journal_ops(h.journal) == ['intent', 'ownership', 'disposal', 'completion']


@pytest.mark.parametrize('answer,state', [
    (None, outcome_mod.OUTCOME_MISSING),
    (record(status='failed', workload_exit=3), outcome_mod.WORKLOAD_FAILED),
    (record(nonce='other'), outcome_mod.OUTCOME_FORGED),
    (record(execution_id='e2'), outcome_mod.OUTCOME_FORGED),
    (record(payload_digest='b' * 64), outcome_mod.OUTCOME_FORGED),
    (record(timestamp=50.0), outcome_mod.OUTCOME_FORGED),
    (record(timestamp=101.0), outcome_mod.OUTCOME_FORGED),
    (record(timestamp=float('nan')), outcome_mod.OUTCOME_UNVERIFIED),
    (record(timestamp=float('inf')), outcome_mod.OUTCOME_UNVERIFIED),
    ({}, outcome_mod.OUTCOME_UNVERIFIED),
    (0, outcome_mod.OUTCOME_UNVERIFIED),
    (record(workload_exit=5), outcome_mod.OUTCOME_UNVERIFIED),
])
def test_a_launcher_zero_with_any_other_binding_is_never_success(wire, answer, state):
    h = bound(wire, lambda process: answer)
    with pytest.raises(staging.StageError, match=state):
        h.launch.wait()
    assert h.launch.launcher_exit == 0 and h.launch.bound.state == state
    assert h.launch.completed is None
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops


@pytest.mark.parametrize('expected', [lambda: None, lambda: {'nonce': 'n1'},
                                      no_identity])
def test_an_identity_that_cannot_be_issued_never_binds(wire, expected):
    h = bound(wire, lambda process: record(), expected=expected)
    with pytest.raises(staging.StageError, match=outcome_mod.OUTCOME_UNVERIFIED):
        h.launch.wait()
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED


def test_a_reader_that_raises_is_unverified(wire):
    h = bound(wire, raising(OSError('read failed')))
    with pytest.raises(staging.StageError, match=outcome_mod.OUTCOME_UNVERIFIED):
        h.launch.wait()
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert journal_ops(h.journal)[-1] == 'quarantine'


def test_a_reader_that_is_interrupted_still_ends_the_launch(wire):
    h = bound(wire, raising(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        h.launch.wait()
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert journal_ops(h.journal)[-1] == 'quarantine'
    assert h.api.handles == {}


def test_a_failed_launcher_is_never_asked_for_an_outcome(wire):
    calls = []
    h = bound(wire, lambda process: (calls.append(1), record())[1], exit_code=3)
    with pytest.raises(staging.StageError, match=outcome_mod.LAUNCHER_FAILED):
        h.launch.wait()
    assert calls == [] and h.launch.launcher_exit == 3
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED


def test_a_reader_without_its_identity_is_refused(args, wire):
    h = wire()
    with pytest.raises(staging.StageError, match='identity'):
        local.MxcLaunch(api=h.api, boundary=h.boundary, ledger=h.journal,
                        schema_validator=lambda raw: True, execution_id='e9',
                        outcome=lambda process: 0, workload_reader=lambda process: None,
                        **args)


def test_the_default_keeps_the_core_owned_outcome_callable_and_binds_nothing(wire):
    h = wire(outcome=lambda process: 7, reader=lambda execution_id, owner: True)
    h.launch.start(job=h.job)
    assert h.launch.wait() == 7 and h.launch.bound is None
    assert h.launch.end_state['state'] == ledger_mod.DEAD_CLEAN
