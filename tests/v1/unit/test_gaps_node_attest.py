"""Gap tests for the pure attestor (archeus/node/attest.py, T-731).

Companion to tests/v1/unit/test_node_attest.py: same seams (port -> owner,
PID -> observation, clock), same FakeTable style, no OS, no network, no real
process, nothing Windows-specific. This file covers only the branches the
T-231 suite leaves unexercised: truthiness-vs-identity refusals, the
TypeError/ValueError arms of _finite(), the empty-ancestry boundary, the
custom `launcher` parameter, the exact max-age boundary and negative window,
plus the clock failing or reading non-finite at accept and a non-finite
accepted_at at recheck, all of which must fail closed.
"""

import pytest

from archeus.node.attest import (
    ProcessBinding,
    ProcessInfo,
    PeerOwner,
    attest_owner,
    binding_valid,
    CREATION_TIME_UNREADABLE,
    DEAD,
    EXPIRED,
    LAUNCHER_UNPROVEN,
    OUTSIDE_CORE_JOB,
    READER_ERROR,
)

PORT = 54321
PID = 4124
CT = 100.0          # creation time of the legitimate owner instance
T0 = 1000.0         # fake clock base
LAUNCHER = 'wxc-exec'
GOOD = ProcessInfo(alive=True, creation_time=CT,
                   ancestors=(LAUNCHER, 'services.exe'), in_core_job=True)
_UNSET = object()           # distinguishes "no tamper" from "tamper to None"


class FakeTable:
    """Fake process table, same shape as in test_node_attest.py (T-731 copy)."""

    def __init__(self):
        self.owners = {PORT: PID}
        self.processes = {PID: GOOD}
        self.owner_answer = _UNSET
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

    def attest(self, port=PORT, launcher=None):
        kwargs = {'launcher': launcher} if launcher is not None else {}
        return attest_owner(remote_port=port, resolve_owner=self.resolve_owner,
                            read_process=self.read_process, clock=self.clock,
                            **kwargs)

    def recheck(self, binding, **overrides):
        kwargs = {'read_process': self.read_process, 'clock': self.clock}
        kwargs.update(overrides)
        return binding_valid(binding, **kwargs)

    def bind(self, launcher=None):
        result = self.attest(launcher=launcher)
        assert result.ok and result.binding is not None
        return result.binding

    def fresh_binding(self):
        # a binding as attest_owner would have issued it, without calling attest
        return ProcessBinding(remote_port=PORT, pid=PID, creation_time=CT,
                              accepted_at=T0, core_job_at_accept=True)

    def set_process(self, **changes):
        self.processes[PID] = GOOD._replace(**changes)


# ── a clock or an accept time that is not a finite number is no evidence ──

def test_clock_failure_at_accept_fails_closed():
    table = FakeTable()
    table.clock_error = RuntimeError('clock unreadable')
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (READER_ERROR,)


@pytest.mark.parametrize('now', [float('nan'), float('inf')])
def test_non_finite_clock_at_accept_is_no_evidence(now):
    table = FakeTable()
    table.now = now
    result = table.attest()
    assert not result.ok and result.binding is None


def test_binding_with_nan_accepted_at_is_expired():
    table = FakeTable()
    binding = table.fresh_binding()._replace(accepted_at=float('nan'))
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (EXPIRED,)
    assert table.pids_read == []             # refused without consulting any reader


# ── identity, not truthiness: alive / in_core_job must be exactly True ──────

def test_alive_must_be_true_not_truthy_at_accept():
    # `info.alive is not True` (attest.py:98): an int-1 liveness signal is NOT
    # evidence of life; inverting to `if not info.alive` would pass this value.
    table = FakeTable()
    table.set_process(alive=1)
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (DEAD,)


def test_alive_must_be_true_not_truthy_at_use():
    table = FakeTable()
    binding = table.bind()
    table.set_process(alive=1)
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (DEAD,)


def test_core_job_must_be_true_not_truthy_at_accept():
    # `info.in_core_job is not True` (attest.py:105): 1 means nothing here.
    table = FakeTable()
    table.set_process(in_core_job=1)
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (OUTSIDE_CORE_JOB,)


def test_core_job_must_be_true_not_truthy_at_use():
    table = FakeTable()
    binding = table.bind()
    table.set_process(in_core_job=1)
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (OUTSIDE_CORE_JOB,)


# ── _finite(): the uncaught-type arms (TypeError / ValueError) ───────────────

@pytest.mark.parametrize('creation_time', [object(), 'not-a-number', []])
def test_creation_time_non_numeric_fails_closed_at_accept(creation_time):
    # _finite (attest.py:176-180): float() raises TypeError (object, list) or
    # ValueError (unparseable str); deleting either except-arm re-raises and
    # this test errors instead of returning the refusal tuple.
    table = FakeTable()
    table.set_process(creation_time=creation_time)
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (CREATION_TIME_UNREADABLE,)


@pytest.mark.parametrize('creation_time', [object(), 'not-a-number', []])
def test_creation_time_non_numeric_fails_closed_at_use(creation_time):
    # same arms reached from binding_valid's check at attest.py:154; the
    # `elif ... !=` mismatch arm must NOT be taken for unreadable times
    table = FakeTable()
    binding = table.bind()
    table.set_process(creation_time=creation_time)
    result = table.recheck(binding)
    assert not result.ok and result.binding is None
    assert result.failures == (CREATION_TIME_UNREADABLE,)


# ── ancestry boundaries and the custom launcher parameter ────────────────────

def test_empty_ancestry_is_unproven_not_malformed():
    # () is a well-formed tuple (all() is vacuously true) naming no launcher:
    # attest.py:171 must return LAUNCHER_UNPROVEN, not MALFORMED and not ok.
    table = FakeTable()
    table.set_process(ancestors=())
    result = table.attest()
    assert not result.ok and result.binding is None
    assert result.failures == (LAUNCHER_UNPROVEN,)


def test_custom_launcher_proves_ancestry_case_insensitively():
    # launcher parameter honoured (attest.py:171): default wxc-exec absent,
    # pinned launcher present in mixed case -> the ONLY reason it passes.
    table = FakeTable()
    table.set_process(ancestors=('WXC-GUARD', 'services.exe'))
    assert not table.attest().ok                      # default launcher: unproven
    result = table.attest(launcher='wxc-guard')
    assert result.ok and result.failures == ()


def test_custom_launcher_missing_fails_closed():
    table = FakeTable()                                # ancestors name wxc-exec
    result = table.attest(launcher='wxc-guard')
    assert not result.ok and result.binding is None
    assert result.failures == (LAUNCHER_UNPROVEN,)


def test_recheck_honours_its_own_launcher_argument():
    # binding_valid(launcher=...) at attest.py:159->171: ancestry proven at
    # accept for the default launcher must not auto-pass a recheck pinned
    # to a different launcher.
    table = FakeTable()
    binding = table.bind()
    result = table.recheck(binding, launcher='wxc-guard')
    assert not result.ok and result.binding is None
    assert result.failures == (LAUNCHER_UNPROVEN,)


# ── age boundary of the recheck window ───────────────────────────────────────

def test_age_exactly_max_age_is_still_valid():
    # `now - accepted_at > max_age_s` (attest.py:141) is a STRICT greater-than:
    # changing it to >= would expire this binding and fail the test.
    table = FakeTable()
    binding = table.fresh_binding()
    table.now = T0 + 2.0
    result = table.recheck(binding, max_age_s=2.0)
    assert result.ok and result.failures == () and result.binding == binding


def test_negative_max_age_expires_without_consulting_readers():
    # a pinned-negative window must fail closed at zero age, before any read
    # (attest.py:141); deleting the expiry line would let a perfect process pass.
    table = FakeTable()
    binding = table.fresh_binding()
    result = table.recheck(binding, max_age_s=-1.0)
    assert not result.ok and result.binding is None
    assert result.failures == (EXPIRED,)
    assert table.pids_read == []
