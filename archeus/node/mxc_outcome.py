"""Binding of a launcher exit code to a workload outcome (audit slice 5, T-451).

Two facts, never merged: the launcher's exit code says the launcher finished, and the
workload's own outcome says the work finished. The launcher is an untrusted reporter, so
a clean exit is only ever a precondition. This module is pure — no archeus import, no OS
call, no clock, no digest function: the caller injects the reader and the identity this
call issued, and every comparison happens here.
"""
from dataclasses import dataclass

SUCCEEDED = 'SUCCEEDED'
WORKLOAD_FAILED = 'WORKLOAD_FAILED'
LAUNCHER_FAILED = 'LAUNCHER_FAILED'
OUTCOME_MISSING = 'OUTCOME_MISSING'
OUTCOME_FORGED = 'OUTCOME_FORGED'
OUTCOME_UNVERIFIED = 'OUTCOME_UNVERIFIED'

STATES = (SUCCEEDED, WORKLOAD_FAILED, LAUNCHER_FAILED, OUTCOME_MISSING,
          OUTCOME_FORGED, OUTCOME_UNVERIFIED)

_HEX = frozenset('0123456789abcdef')
_OUTCOME_FIELDS = frozenset({'execution_id', 'nonce', 'payload_digest', 'timestamp',
                             'status', 'workload_exit'})
_BINDING_FIELDS = frozenset({'execution_id', 'nonce', 'digest', 'now', 'max_age'})
_STATUS = frozenset({'succeeded', 'failed'})


@dataclass(frozen=True)
class BoundOutcome:
    state: str
    launcher_exit: object
    workload_exit: object
    reason: str

    @property
    def succeeded(self):
        return self.state == SUCCEEDED


def _int(value):
    return type(value) is int


def _number(value):
    return type(value) is int or type(value) is float


def _text(value):
    return type(value) is str and value != ''


def _digest(value):
    return type(value) is str and len(value) == 64 and not set(value) - _HEX


def _shape(record):
    if type(record) is not dict or set(record) != _OUTCOME_FIELDS:
        return False
    if not _text(record['execution_id']) or not _text(record['nonce']):
        return False
    if not _digest(record['payload_digest']) or not _number(record['timestamp']):
        return False
    if record['status'] not in _STATUS:
        return False
    exit_code = record['workload_exit']
    if not _int(exit_code) or exit_code < 0:
        return False
    return (record['status'] == 'succeeded') == (exit_code == 0)


def _binding(binding):
    if type(binding) is not dict or set(binding) != _BINDING_FIELDS:
        return False
    if not _text(binding['execution_id']) or not _text(binding['nonce']):
        return False
    if not _digest(binding['digest']):
        return False
    return (_number(binding['now']) and _number(binding['max_age'])
            and binding['max_age'] >= 0)


def bind_outcome(launcher_exit, read_workload_outcome, expected=None):
    """Answer one of STATES for a launcher exit plus the workload's own report.

    `read_workload_outcome` is called only after a clean launcher exit and is never
    believed: it returns None when nothing was reported, or a record carrying the
    identity the workload was handed (execution id, nonce, payload digest, timestamp).
    `expected` is that identity as this call issued it, with the caller's clock reading,
    because this module keeps no clock of its own.
    """
    if not _int(launcher_exit):
        return BoundOutcome(LAUNCHER_FAILED, launcher_exit, None,
                            'launcher exit was never observed as an integer')
    if launcher_exit != 0:
        return BoundOutcome(LAUNCHER_FAILED, launcher_exit, None,
                            'launcher did not report a clean exit')
    try:
        record = read_workload_outcome()
    except Exception:
        return BoundOutcome(OUTCOME_UNVERIFIED, launcher_exit, None,
                            'outcome reader could not be called, raised or timed out')
    # Only an explicit None means "nothing was reported". An empty string, an empty
    # dict or a bare 0 are damaged reports, not absent ones, and must not be readable
    # as the milder OUTCOME_MISSING.
    if record is None:
        return BoundOutcome(OUTCOME_MISSING, launcher_exit, None,
                            'workload reported no outcome')
    if not _shape(record):
        return BoundOutcome(OUTCOME_UNVERIFIED, launcher_exit, None,
                            'outcome record is malformed')
    if not _binding(expected):
        return BoundOutcome(OUTCOME_UNVERIFIED, launcher_exit, None,
                            'the identity this call issued is unavailable or malformed')
    if record['execution_id'] != expected['execution_id']:
        return BoundOutcome(OUTCOME_FORGED, launcher_exit, None,
                            'outcome names another execution')
    if record['nonce'] != expected['nonce']:
        return BoundOutcome(OUTCOME_FORGED, launcher_exit, None,
                            'outcome was not written by this attempt')
    if record['payload_digest'] != expected['digest']:
        return BoundOutcome(OUTCOME_FORGED, launcher_exit, None,
                            'outcome describes different content')
    age = expected['now'] - record['timestamp']
    if age < 0 or age > expected['max_age']:
        return BoundOutcome(OUTCOME_FORGED, launcher_exit, None,
                            'outcome timestamp is outside the accepted window')
    if record['status'] == 'succeeded':
        return BoundOutcome(SUCCEEDED, launcher_exit, record['workload_exit'], 'bound')
    return BoundOutcome(WORKLOAD_FAILED, launcher_exit, record['workload_exit'],
                        'workload reported its own failure')
