"""Fake-process-table tests for the pure attestor (archeus/node/attest.py, T-231).

Every decision branch of attest_owner() and binding_valid() has a test, driven
only through the injected seams: port -> owner, PID -> observation, clock.
Each test pins one branch by its exact failure tuple, so removing that branch
changes the verdict or the reason codes and the test fails.
"""

import pytest

from archeus.node.attest import (
    AttestResult,
    ProcessBinding,
    ProcessInfo,
    PeerOwner,
    attest_owner,
    binding_valid,
    CREATION_TIME_MISMATCH,
    CREATION_TIME_UNREADABLE,
    DEAD,
    EXPIRED,
    LAUNCHER_UNPROVEN,
    MALFORMED,
    MALFORMED_OWNER,
    NO_BINDING,
    NO_OWNER,
    OUTSIDE_CORE_JOB,
    READER_ERROR,
)

PORT = 54321
OTHER_PORT = 54322
PID = 4124
CT = 100.0          # creation time of the legitimate owner instance
T0 = 1000.0         # fake clock base
LAUNCHER = 'wxc-exec'
GOOD = ProcessInfo(alive=True, creation_time=CT,
                   ancestors=(LAUNCHER, 'services.exe'), in_core_job=True)
_UNSET = object()           # distinguishes "no tamper" from "tamper to None"


class FakeTable:
    """Fake process table: port owners plus per-PID observations, fully injectable."""

    def __init__(self):
        self.owners = {PORT: PID}
        self.processes = {PID: GOOD}
        self.owner_answer = _UNSET        # when set, returned verbatim (tamper knob)
        self.owner_error = None
        self.process_error = None
        self.clock_error = None
        self.now = T0
        self.ports_queried = []
        self.pids_read = []

    def resolve_owner(self, port):
        self.ports_queried.append(port)
        if self.owner_error is not None:
            raise self.owner_error
        if self.owner_answer is not _UNSET:
            return self.owner_answer
        return PeerOwner(pid=self.owners.get(port))

    def read_process(self, pid):
        self.pids_read.append(pid)
        if self.process_error is not None:
            raise self.process_error
        return self.processes.get(pid)

    def clock(self):
        if self.clock_error is not None:
            raise self.clock_error
        return self.now

    def attest(self, port=PORT):
        return attest_owner(remote_port=port, resolve_owner=self.resolve_owner,
                            read_process=self.read_process, clock=self.clock)

    def recheck(self, binding, **overrides):
        kwargs = {'read_process': self.read_process, 'clock': self.clock}
        kwargs.update(overrides)
        return binding_valid(binding, **kwargs)

    def bind(self):
        result = self.attest()
        assert result.ok and result.binding is not None
        return result.binding

    def set_process(self, **changes):
        self.processes[PID] = GOOD._replace(**changes)


# ── attest at accept: the passing baseline ──────────────────────────────────

def test_live_matching_process_attests_ok():
    table = FakeTable()
    result = table.attest()
    assert isinstance(result, AttestResult) and result.ok and result.failures == ()
    assert isinstance(result.binding, ProcessBinding)
    assert result.binding.remote_port == PORT
    assert result.binding.pid == PID
    assert result.binding.creation_time == CT
    assert result.binding.accepted_at == T0
    assert result.binding.core_job_at_accept is True
    # the lookup is keyed by the accepted peer port, never by any other port
    assert table.ports_queried == [PORT]
    assert table.pids_read == [PID]


def test_ancestry_match_is_case_insensitive():
    table = FakeTable()
    table.set_process(ancestors=(LAUNCHER.upper(), 'services.exe'))
    assert table.attest().ok


# ── attest: port -> owner branch ────────────────────────────────────────────

def test_owner_reader_error_fails_closed():
    table = FakeTable()
    table.owner_error = OSError('table query failed')
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (READER_ERROR,)


@pytest.mark.parametrize('answer', [None, 'x', 4124, (PID,)])
def test_malformed_owner_answer_fails_closed(answer):
    table = FakeTable()
    table.owner_answer = answer
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (MALFORMED_OWNER,)


def test_no_owner_fails_closed():
    table = FakeTable()
    table.owners = {}                     # table names no owner for this port
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (NO_OWNER,)
    assert table.pids_read == []


def test_owner_found_for_wrong_port_fails_closed():
    # Another port has an owner, the queried port has none: the attestor must
    # not fall back to some other port's owner.
    table = FakeTable()
    table.owners = {OTHER_PORT: PID}
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (NO_OWNER,)
    assert table.ports_queried == [PORT]
    assert table.pids_read == []


@pytest.mark.parametrize('pid', [0, -1, '4124', True, 4.2])
def test_malformed_owner_pid_fails_closed(pid):
    table = FakeTable()
    table.owners = {PORT: pid}
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (MALFORMED_OWNER,)


# ── attest: PID -> observation branch ───────────────────────────────────────

def test_process_reader_error_fails_closed():
    table = FakeTable()
    table.process_error = RuntimeError('snapshot failed')
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (READER_ERROR,)


def test_malformed_process_info_fails_closed():
    table = FakeTable()
    del table.processes[PID]              # reader answers with a non-ProcessInfo
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (MALFORMED,)


def test_dead_pid_fails_closed():
    # F9C: the table still lists the dead owner; liveness is its own check.
    table = FakeTable()
    table.set_process(alive=False)
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (DEAD,)


@pytest.mark.parametrize('creation_time', [None, float('nan'), float('inf')])
def test_creation_time_unreadable_fails_closed(creation_time):
    table = FakeTable()
    table.set_process(creation_time=creation_time)
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (CREATION_TIME_UNREADABLE,)


def test_launcher_not_in_ancestry_fails_closed():
    # Job membership is fine here, so this test pins the ancestry branch alone.
    table = FakeTable()
    table.set_process(ancestors=('explorer.exe', 'services.exe'))
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (LAUNCHER_UNPROVEN,)


@pytest.mark.parametrize('ancestors', [['wxc-exec'], ('wxc-exec', 7), 'wxc-exec'])
def test_malformed_ancestors_fails_closed(ancestors):
    table = FakeTable()
    table.set_process(ancestors=ancestors)
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (MALFORMED,)


def test_outside_core_job_fails_closed():
    # Ancestry is fine here, so this test pins the job branch alone.
    table = FakeTable()
    table.set_process(in_core_job=False)
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (OUTSIDE_CORE_JOB,)


def test_host_forwarder_rejected():
    # F9B: alive and readable, but launched by the host: no launcher ancestry
    # and no Core Job, both refused at once.
    table = FakeTable()
    table.processes[PID] = ProcessInfo(alive=True, creation_time=CT,
                                       ancestors=('explorer.exe', 'cmd.exe'),
                                       in_core_job=False)
    result = table.attest()
    assert not result.ok and result.binding is None
    assert set(result.failures) == {LAUNCHER_UNPROVEN, OUTSIDE_CORE_JOB}


# ── recheck at use ──────────────────────────────────────────────────────────

def test_valid_recheck_still_valid():
    table = FakeTable()
    binding = table.bind()
    table.now = T0 + 1.0                  # within the window F9's lag suggests
    result = table.recheck(binding, max_age_s=2.0)
    assert result.ok and result.failures == () and result.binding == binding


@pytest.mark.parametrize('binding', [None, ('port', PID, CT, T0, True), 'binding'])
def test_missing_or_foreign_binding_fails_closed(binding):
    table = FakeTable()
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (NO_BINDING,)
    assert table.pids_read == []          # refused without consulting any reader


def test_clock_error_fails_closed():
    table = FakeTable()
    binding = table.bind()
    table.clock_error = RuntimeError('clock unreadable')
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (READER_ERROR,)


@pytest.mark.parametrize('now', [float('nan'), float('inf')])
def test_non_finite_clock_fails_closed(now):
    table = FakeTable()
    binding = table.bind()
    table.now = now
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (EXPIRED,)


def test_clock_error_at_accept_fails_closed():
    table = FakeTable()
    table.clock_error = RuntimeError('clock unreadable')
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (READER_ERROR,)


@pytest.mark.parametrize('now', [float('nan'), float('inf')])
def test_non_finite_clock_at_accept_issues_no_binding(now):
    table = FakeTable()
    table.now = now
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (READER_ERROR,)


def test_nan_max_age_does_not_switch_expiry_off():
    table = FakeTable()
    binding = table.bind()
    table.now = T0 + 10.0
    result = table.recheck(binding, max_age_s=float('nan'))
    assert not result.ok and result.failures == (EXPIRED,)


def test_expired_binding_fails_closed():
    table = FakeTable()
    binding = table.bind()
    table.now = T0 + 10.0                 # past any small pinned window
    result = table.recheck(binding, max_age_s=2.0)
    assert not result.ok and result.binding is None
    assert result.failures == (EXPIRED,)
    # the process still looks perfect, yet the expired answer stands: the
    # recheck must fail closed before reading anything
    assert table.pids_read == [PID]       # only the attest-time read above


def test_use_reader_error_fails_closed():
    table = FakeTable()
    binding = table.bind()
    table.process_error = RuntimeError('snapshot failed')
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (READER_ERROR,)


def test_malformed_process_info_at_use_fails_closed():
    table = FakeTable()
    binding = table.bind()
    del table.processes[PID]
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (MALFORMED,)


def test_dead_pid_at_use_fails_closed():
    table = FakeTable()
    binding = table.bind()
    table.set_process(alive=False)        # owner died in the accept->use window
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (DEAD,)


def test_recycled_pid_fails_closed_at_use():
    # PID reuse: same number, a NEW process instance with a different creation
    # time (and, here, its own fresh ancestry) must never inherit the binding.
    table = FakeTable()
    binding = table.bind()
    table.processes[PID] = ProcessInfo(alive=True, creation_time=999.0,
                                       ancestors=(LAUNCHER, 'services.exe'),
                                       in_core_job=True)
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (CREATION_TIME_MISMATCH,)


@pytest.mark.parametrize('creation_time', [None, float('nan'), float('inf')])
def test_creation_time_unreadable_at_use_fails_closed(creation_time):
    table = FakeTable()
    binding = table.bind()
    table.set_process(creation_time=creation_time)
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (CREATION_TIME_UNREADABLE,)


def test_launcher_lost_at_use_fails_closed():
    table = FakeTable()
    binding = table.bind()
    table.set_process(ancestors=('explorer.exe',))   # job membership kept
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (LAUNCHER_UNPROVEN,)


def test_malformed_ancestors_at_use_fails_closed():
    table = FakeTable()
    binding = table.bind()
    table.set_process(ancestors=(7,))
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (MALFORMED,)


def test_job_membership_lost_at_use_fails_closed():
    table = FakeTable()
    binding = table.bind()
    table.set_process(in_core_job=False)
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (OUTSIDE_CORE_JOB,)


def test_multiple_failures_are_reported_together_without_partial_pass():
    table = FakeTable()
    binding = table.bind()
    table.processes[PID] = ProcessInfo(alive=False, creation_time=999.0,
                                       ancestors=('explorer.exe',),
                                       in_core_job=False)
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert set(result.failures) == {DEAD, CREATION_TIME_MISMATCH,
                                    LAUNCHER_UNPROVEN, OUTSIDE_CORE_JOB}


def test_a_filetime_creation_time_is_compared_exactly():
    # a Windows FILETIME is above 2**53: float() would make neighbours equal
    bound = 130_000_000_000_000_001
    binding = ProcessBinding(remote_port=1, pid=PID, creation_time=bound, accepted_at=0.0,
                             core_job_at_accept=True)
    info = ProcessInfo(alive=True, creation_time=bound + 1, ancestors=(LAUNCHER,), in_core_job=True)
    result = binding_valid(binding, read_process=lambda pid: info, clock=lambda: 0.0)
    assert result.failures == (CREATION_TIME_MISMATCH,)
