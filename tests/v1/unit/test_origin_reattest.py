"""T-806: re-attestation of a long-lived connection in the origin gate.

A binding older than max_age_s is re-attested once per request and kept only for the
same PID and creation time; anything else, or a failed attempt, refuses and stays
refused. A fake process table and a fake clock: no Windows API, no socket, no process."""

import pytest

from archeus.api import origin
from archeus.node.attest import (
    DEFAULT_LAUNCHER,
    DEFAULT_MAX_AGE_S,
    PeerOwner,
    ProcessInfo,
)
from archeus.node.origin_windows import WindowsOriginBackend

PORT, PID, CT, T0 = 54321, 4124, 100.0, 1000.0
LATE = DEFAULT_MAX_AGE_S + 0.5
GOOD = ProcessInfo(alive=True, creation_time=CT,
                   ancestors=(DEFAULT_LAUNCHER, 'services.exe'), in_core_job=True)


class Table:
    def __init__(self):
        self.now = T0
        self.owner = PID
        self.process = {PID: GOOD}
        self.owner_error = self.process_error = self.clock_error = None
        self.owner_calls = 0

    def resolve_owner(self, port):
        self.owner_calls += 1
        if self.owner_error:
            raise self.owner_error
        return PeerOwner(pid=self.owner)

    def read_process(self, pid):
        if self.process_error:
            raise self.process_error
        return self.process.get(pid)

    def clock(self):
        if self.clock_error:
            raise self.clock_error
        return self.now

    def readers(self, **overrides):
        overrides.setdefault('reattest', True)
        return origin.AttestationReaders(resolve_owner=self.resolve_owner,
                                         read_process=self.read_process,
                                         clock=self.clock, **overrides)


@pytest.fixture
def table():
    return Table()


def connect(table, generation='g1', **overrides):
    backend = WindowsOriginBackend(readers=table.readers(**overrides))
    context = origin.ConnectionContext(object(), ('127.0.0.1', 8731),
                                       ('127.0.0.1', PORT), generation)
    evidence = backend.attest(context)
    assert evidence.process_binding is not None
    return backend, context, evidence


def age(table, seconds=LATE):
    table.now += seconds


def test_fresh_binding_is_kept_without_a_second_attestation(table):
    backend, context, evidence = connect(table)
    assert backend.valid(context, evidence) is True
    assert table.owner_calls == 1


def test_expired_binding_is_reattested_and_kept(table):
    backend, context, evidence = connect(table)
    age(table)
    assert backend.valid(context, evidence) is True
    assert table.owner_calls == 2
    age(table, 1.0)
    assert backend.valid(context, evidence) is True
    assert table.owner_calls == 2


def test_default_readers_still_refuse_an_expired_binding(table):
    backend, context, evidence = connect(table, reattest=False)
    age(table)
    assert backend.valid(context, evidence) is False
    assert table.owner_calls == 1


def test_enforcement_stays_off_and_the_origin_stays_execution(table):
    backend, context, evidence = connect(table)
    age(table)
    assert backend.valid(context, evidence) is True
    assert origin.ORIGIN_ENFORCEMENT_ENABLED is False
    assert evidence.origin == origin.OriginClass.EXECUTION


def test_a_different_pid_is_refused(table):
    backend, context, evidence = connect(table)
    table.owner = PID + 1
    table.process[PID + 1] = GOOD
    age(table)
    assert backend.valid(context, evidence) is False
    assert table.owner_calls == 2


def test_pid_reuse_with_a_new_creation_time_is_refused(table):
    backend, context, evidence = connect(table)
    table.process[PID] = GOOD._replace(creation_time=CT + 1.0)
    age(table)
    assert backend.valid(context, evidence) is False
    assert table.owner_calls == 2


def test_a_dead_pid_is_refused(table):
    backend, context, evidence = connect(table)
    table.process[PID] = GOOD._replace(alive=False)
    age(table)
    assert backend.valid(context, evidence) is False
    assert table.owner_calls == 2


@pytest.mark.parametrize('broken', ['owner_error', 'process_error', 'clock_error'])
def test_a_reader_error_during_reattestation_is_refused(table, broken):
    backend, context, evidence = connect(table)
    setattr(table, broken, OSError('fixture reader failure'))
    age(table)
    assert backend.valid(context, evidence) is False


def test_a_fresh_binding_does_not_reattest_a_recycled_pid(table):
    backend, context, evidence = connect(table)
    table.process[PID] = GOOD._replace(creation_time=CT + 1.0)
    assert backend.valid(context, evidence) is False
    assert table.owner_calls == 1


def test_frames_after_a_failed_reattestation_stay_refused(table):
    backend, context, evidence = connect(table)
    table.owner_error = OSError('fixture reader failure')
    age(table)
    assert backend.valid(context, evidence) is False
    table.owner_error = None
    for _ in range(3):
        age(table, origin.REATTEST_INTERVAL_S + LATE)
        assert backend.valid(context, evidence) is False
    assert table.owner_calls == 2


def test_a_failed_attempt_is_recorded_even_when_the_attestor_raises(table):
    backend, context, evidence = connect(table)
    age(table)
    table.clock_error = None
    calls = []

    def clock():
        calls.append(1)
        if len(calls) > 2:
            raise OSError('fixture clock failure')
        return table.now

    backend.readers = origin.AttestationReaders(
        resolve_owner=table.resolve_owner, read_process=table.read_process,
        clock=clock, reattest=True)
    assert backend.valid(context, evidence) is False
    assert backend.valid(context, evidence) is False
    backend.readers = table.readers()
    age(table, origin.REATTEST_INTERVAL_S + LATE)
    assert backend.valid(context, evidence) is False


def test_one_request_makes_at_most_one_attempt(table):
    backend, context, evidence = connect(table)
    age(table, 100 * LATE)
    assert backend.valid(context, evidence) is True
    assert table.owner_calls == 2


def test_attempts_are_spaced_by_the_interval(table):
    backend, context, evidence = connect(table, max_age_s=0.1)
    age(table, 0.5)
    assert backend.valid(context, evidence) is True
    age(table, 0.5)
    assert backend.valid(context, evidence) is False
    assert table.owner_calls == 2
    age(table, origin.REATTEST_INTERVAL_S)
    assert backend.valid(context, evidence) is True
    assert table.owner_calls == 3


def test_release_forgets_the_connection(table):
    backend, context, evidence = connect(table)
    table.owner_error = OSError('fixture reader failure')
    age(table)
    assert backend.valid(context, evidence) is False
    table.owner_error = None
    backend.release(context, evidence)
    assert backend.valid(context, evidence) is True


def test_another_binding_for_the_same_generation_is_refused(table):
    backend, context, evidence = connect(table)
    age(table)
    assert backend.valid(context, evidence) is True
    other = evidence.process_binding._replace(pid=PID + 1)
    forged = evidence.__class__(origin=evidence.origin, identity=evidence.identity,
                                process_binding=other,
                                accept_generation=context.accept_generation,
                                reason=evidence.reason)
    table.process[PID + 1] = GOOD
    assert backend.valid(context, forged) is False


def test_a_binding_of_another_port_is_refused(table):
    backend, context, evidence = connect(table)
    moved = origin.ConnectionContext(context.socket, context.local_endpoint,
                                     ('127.0.0.1', PORT + 1), context.accept_generation)
    age(table)
    assert backend.valid(moved, evidence) is False
