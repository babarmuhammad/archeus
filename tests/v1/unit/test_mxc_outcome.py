import ast
from pathlib import Path

import pytest

from archeus.node import mxc_outcome as outcome

NOW = 1000
MAX_AGE = 60
EXEC = 'exec-7'
NONCE = 'nonce-a'
DIGEST = 'a' * 64


def issued(**change):
    binding = {'execution_id': EXEC, 'nonce': NONCE, 'digest': DIGEST,
               'now': NOW, 'max_age': MAX_AGE}
    binding.update(change)
    return binding


def reported(**change):
    record = {'execution_id': EXEC, 'nonce': NONCE, 'payload_digest': DIGEST,
              'timestamp': NOW - 5, 'status': 'succeeded', 'workload_exit': 0}
    record.update(change)
    return record


def once(value):
    calls = []

    def read():
        calls.append(1)
        return value
    read.calls = calls
    return read


def raiser(error):
    def read():
        raise error
    return read


def test_bound_outcome_succeeds():
    read = once(reported())
    result = outcome.bind_outcome(0, read, issued())
    assert result.state == outcome.SUCCEEDED
    assert result.succeeded is True
    assert (result.launcher_exit, result.workload_exit) == (0, 0)
    assert read.calls == [1]


def test_result_is_a_frozen_typed_record():
    result = outcome.bind_outcome(0, once(reported()), issued())
    assert isinstance(result, outcome.BoundOutcome)
    assert set(vars(result)) == {'state', 'launcher_exit', 'workload_exit', 'reason'}
    with pytest.raises(Exception):
        result.state = outcome.WORKLOAD_FAILED


def test_states_are_distinct_named_values():
    assert set(outcome.STATES) == {
        outcome.SUCCEEDED, outcome.WORKLOAD_FAILED, outcome.LAUNCHER_FAILED,
        outcome.OUTCOME_MISSING, outcome.OUTCOME_FORGED, outcome.OUTCOME_UNVERIFIED}
    assert len(outcome.STATES) == 6


@pytest.mark.parametrize('exit_code', [1, 7, 127, 255])
def test_unclean_launcher_fails_before_any_read(exit_code):
    read = once(reported())
    result = outcome.bind_outcome(exit_code, read, issued())
    assert result.state == outcome.LAUNCHER_FAILED
    assert result.launcher_exit == exit_code
    assert result.workload_exit is None
    assert read.calls == []


def test_killed_launcher_fails():
    assert outcome.bind_outcome(-9, once(reported()), issued()).state == outcome.LAUNCHER_FAILED


def test_launcher_fact_and_outcome_fact_never_cancel_each_other():
    # The workload's own report is perfect; a launcher that never reported a clean
    # exit still cannot carry it, and a broken report still cannot be rescued by 0.
    assert outcome.bind_outcome(1, once(reported()), issued()).state == outcome.LAUNCHER_FAILED
    assert outcome.bind_outcome(0, once(None), issued()).state == outcome.OUTCOME_MISSING


@pytest.mark.parametrize('value', [None, True, 0.0, '0', 'ok', [], {}, object()])
def test_launcher_exit_that_is_not_an_integer_fails(value):
    read = once(reported())
    result = outcome.bind_outcome(value, read, issued())
    assert result.state == outcome.LAUNCHER_FAILED
    assert read.calls == []


def test_clean_launcher_without_a_report_is_missing():
    result = outcome.bind_outcome(0, once(None), issued())
    assert result.state == outcome.OUTCOME_MISSING
    assert result.succeeded is False
    assert result.workload_exit is None


def test_verified_workload_failure_is_not_missing_or_unverified():
    result = outcome.bind_outcome(0, once(reported(status='failed', workload_exit=3)),
                                  issued())
    assert result.state == outcome.WORKLOAD_FAILED
    assert (result.launcher_exit, result.workload_exit) == (0, 3)


@pytest.mark.parametrize('which', ['execution_id', 'nonce', 'payload_digest',
                                   'stale', 'future'])
def test_every_forgery_is_refused(which):
    forgeries = {'execution_id': reported(execution_id='exec-other'),
                 'nonce': reported(nonce='nonce-replay'),
                 'payload_digest': reported(payload_digest='b' * 64),
                 'stale': reported(timestamp=NOW - MAX_AGE - 1),
                 'future': reported(timestamp=NOW + 1)}
    result = outcome.bind_outcome(0, once(forgeries[which]), issued())
    assert result.state == outcome.OUTCOME_FORGED
    assert result.workload_exit is None


@pytest.mark.parametrize('which', ['execution_id', 'nonce', 'payload_digest', 'stale'])
def test_forgery_survives_a_clean_launcher_and_a_claim_of_success(which):
    forgeries = {'execution_id': reported(execution_id='exec-other'),
                 'nonce': reported(nonce='nonce-replay'),
                 'payload_digest': reported(payload_digest='b' * 64),
                 'stale': reported(timestamp=NOW - MAX_AGE - 1)}
    assert outcome.bind_outcome(0, once(forgeries[which]), issued()).state != outcome.SUCCEEDED


@pytest.mark.parametrize('damage', [
    'string', 'bytes', 'int', 'list', 'empty-dict', 'zero',
    'missing-field', 'marker-field', 'identity-not-text', 'digest-not-hex', 'digest-length',
    'timestamp-text', 'timestamp-bool', 'status-unknown', 'status-empty',
    'exit-bool', 'exit-negative',
    'success-with-exit', 'failure-with-zero',
])
def test_a_malformed_report_is_unverified(damage):
    damaged = {'string': 'succeeded', 'bytes': b'{"status": "succeeded"}', 'int': 0,
               'list': [reported()], 'empty-dict': {}, 'zero': 0.0,
               'missing-field': {k: v for k, v in reported().items() if k != 'nonce'},
               # a stdout marker or a result-file path is a claim, never an outcome,
               # and it is not part of the record's shape.
               'marker-field': reported(stdout_marker='ARCHEUS_OUTCOME=0',
                                        result_file='C:\\outcomes\\e1.json'),
               'identity-not-text': reported(execution_id=7),
               'digest-not-hex': reported(payload_digest='z' * 64),
               'digest-length': reported(payload_digest='a' * 63),
               'timestamp-text': reported(timestamp='1000'),
               'timestamp-bool': reported(timestamp=True),
               # neither of these is a verdict the workload is allowed to give, and
               # neither may fall through to the failed branch just because its exit
               # code is not zero.
               'status-unknown': reported(status='ok', workload_exit=1),
               'status-empty': reported(status='', workload_exit=1),
               'exit-bool': reported(status='failed', workload_exit=True),
               'exit-negative': reported(status='failed', workload_exit=-1),
               'success-with-exit': reported(workload_exit=4),
               'failure-with-zero': reported(status='failed', workload_exit=0)}[damage]
    assert outcome.bind_outcome(0, once(damaged), issued()).state == outcome.OUTCOME_UNVERIFIED


@pytest.mark.parametrize('error', [OSError('outcome channel closed'),
                                   ValueError('bad json'),
                                   KeyError('status'),
                                   TypeError('reader is not callable'),
                                   TimeoutError('reader timed out')])
def test_a_reader_that_cannot_answer_is_unverified(error):
    assert outcome.bind_outcome(0, raiser(error), issued()).state == outcome.OUTCOME_UNVERIFIED


def test_a_reader_that_hangs_like_a_dead_channel_is_unverified():
    # The reader is the only way out; a channel that never resolves is reported by
    # the injected reader as a timeout, and that is uncertainty, not absence.
    assert outcome.bind_outcome(0, raiser(TimeoutError()), issued()).state \
        == outcome.OUTCOME_UNVERIFIED


@pytest.mark.parametrize('reader', [None, 'reader', 0, object()])
def test_a_reader_that_is_not_callable_is_unverified(reader):
    assert outcome.bind_outcome(0, reader, issued()).state == outcome.OUTCOME_UNVERIFIED


@pytest.mark.parametrize('broken', [
    None, {}, 'binding', [],
    {'execution_id': '', 'nonce': NONCE, 'digest': DIGEST, 'now': NOW, 'max_age': MAX_AGE},
    {'execution_id': EXEC, 'nonce': NONCE, 'digest': 'not-a-digest', 'now': NOW,
     'max_age': MAX_AGE},
    {'execution_id': EXEC, 'nonce': NONCE, 'now': NOW, 'max_age': MAX_AGE},
    {'execution_id': EXEC, 'nonce': NONCE, 'digest': DIGEST, 'max_age': MAX_AGE},
    {'execution_id': EXEC, 'nonce': NONCE, 'digest': DIGEST, 'now': NOW},
    {'execution_id': EXEC, 'nonce': NONCE, 'digest': DIGEST, 'now': NOW, 'max_age': -1},
    {'execution_id': EXEC, 'nonce': NONCE, 'digest': DIGEST, 'now': 'now', 'max_age': MAX_AGE},
])
def test_an_unavailable_identity_is_unverified_not_forged(broken):
    assert outcome.bind_outcome(0, once(reported()), broken).state == outcome.OUTCOME_UNVERIFIED


def test_identity_of_another_attempt_is_never_reused():
    # A genuine, in-window report from the previous attempt on the same execution id.
    replayed = reported(nonce='nonce-of-previous-attempt')
    assert outcome.bind_outcome(0, once(replayed), issued()).state == outcome.OUTCOME_FORGED


@pytest.mark.parametrize('window', [
    {'now': NOW, 'max_age': MAX_AGE},
    {'now': NOW - 5, 'max_age': 0},
    {'now': NOW + 400, 'max_age': 405},
])
def test_accepted_window_is_the_callers_clock(window):
    assert outcome.bind_outcome(0, once(reported()), issued(**window)).state \
        == outcome.SUCCEEDED


@pytest.mark.parametrize('which', ['missing', 'forged', 'unverified'])
def test_a_clean_exit_code_is_never_an_outcome_by_itself(which):
    reports = {'missing': (None, issued()),
               'forged': (reported(execution_id='exec-other'), issued()),
               'unverified': ('the launcher printed ARCHEUS_OUTCOME=0', issued())}
    report, binding = reports[which]
    result = outcome.bind_outcome(0, once(report), binding)
    assert result.state != outcome.SUCCEEDED
    assert result.succeeded is False
    assert result.workload_exit is None


def test_module_stays_pure_logic():
    source = Path(outcome.__file__).read_text(encoding='utf-8')
    tree = ast.parse(source)
    imported = [node for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert [alias.name for node in imported for alias in node.names] == ['dataclass']
    assert [getattr(node, 'module', None) for node in imported] == ['dataclasses']
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.value.id for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)}
    attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    forbidden = {'os', 'sys', 'subprocess', 'time', 'socket', 'pathlib', 'hashlib',
                 'open', 'print', 'archeus', 'system', 'popen', 'spawn', 'urlopen',
                 'remove', 'unlink', 'environ', 'sleep'}
    assert sorted(names & forbidden) == []
    assert sorted(attrs & forbidden) == []
