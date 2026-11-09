"""Hand-mutant pins for the pure attestor (archeus/node/attest.py, T-818).

Every test here names one condition of the attestor the existing suite leaves
free: that condition could be inverted, removed or loosened into a truthiness
test and the whole existing suite would still pass. Only the injected seams are
used — no OS, socket, clock or filesystem call — so the same fake table decides
the same verdict on every platform.
"""

import pytest

from archeus.node.attest import (
    CREATION_TIME_UNREADABLE,
    DEAD,
    EXPIRED,
    LAUNCHER_UNPROVEN,
    OUTSIDE_CORE_JOB,
    READER_ERROR,
    ProcessInfo,
    PeerOwner,
    attest_owner,
    binding_valid,
)

PORT = 47001
PID = 4124
CT = 100.0
T0 = 1000.0
LAUNCHER = 'wxc-exec'
GOOD = ProcessInfo(alive=True, creation_time=CT,
                   ancestors=(LAUNCHER, 'services.exe'), in_core_job=True)


class Table:
    """One peer port, one PID, one clock: the attestor's whole outside world."""

    def __init__(self):
        self.process = GOOD
        self.now = T0
        self.clock_error = None
        self.ports = []
        self.pids = []

    def resolve_owner(self, port):
        self.ports.append(port)
        return PeerOwner(pid=PID)

    def read_process(self, pid):
        self.pids.append(pid)
        return self.process

    def clock(self):
        if self.clock_error is not None:
            raise self.clock_error
        return self.now

    def attest(self, **kwargs):
        return attest_owner(remote_port=PORT, resolve_owner=self.resolve_owner,
                            read_process=self.read_process, clock=self.clock, **kwargs)

    def bind(self):
        result = self.attest()
        assert result.ok and result.binding is not None
        return result.binding

    def recheck(self, binding, **kwargs):
        return binding_valid(binding, read_process=self.read_process,
                             clock=self.clock, **kwargs)

    def tamper(self, **changes):
        self.process = GOOD._replace(**changes)


# ── the liveness flags are identity tests, never truthiness tests ────────────

@pytest.mark.parametrize('alive', [1, 'yes'], ids=['one', 'text'])
def test_accept_refuses_a_truthy_alive_flag(alive):
    # attest.py:98 `info.alive is not True`: a reader answering 1 or 'yes' is as
    # unproven as one answering False, and `not info.alive` would trust both.
    table = Table()
    table.tamper(alive=alive)
    result = table.attest()
    assert result.failures == (DEAD,) and not result.ok and result.binding is None


def test_recheck_refuses_a_truthy_alive_flag():
    # attest.py:152, the same identity test on the per-request path.
    table = Table()
    binding = table.bind()
    table.tamper(alive=1)
    result = table.recheck(binding)
    assert result.failures == (DEAD,) and not result.ok and result.binding is None


@pytest.mark.parametrize('job', [1, 'yes'], ids=['one', 'text'])
def test_accept_refuses_a_truthy_core_job_flag(job):
    # attest.py:105 `info.in_core_job is not True`.
    table = Table()
    table.tamper(in_core_job=job)
    result = table.attest()
    assert result.failures == (OUTSIDE_CORE_JOB,) and result.binding is None


def test_recheck_refuses_a_truthy_core_job_flag():
    # attest.py:161, the same identity test on the per-request path.
    table = Table()
    binding = table.bind()
    table.tamper(in_core_job=1)
    result = table.recheck(binding)
    assert result.failures == (OUTSIDE_CORE_JOB,) and result.binding is None


# ── an unreadable creation time is a refusal, not a crash ───────────────────

def test_accept_refuses_a_creation_time_float_cannot_parse():
    # attest.py:180 `except (TypeError, ValueError)`: keeping only TypeError lets
    # a reader's junk escape attest_owner as a ValueError instead of a refusal.
    table = Table()
    table.tamper(creation_time='yesterday')
    result = table.attest()
    assert result.failures == (CREATION_TIME_UNREADABLE,) and result.binding is None


def test_recheck_refuses_a_creation_time_float_cannot_parse():
    # the same escape on the per-request path, attest.py:154.
    table = Table()
    binding = table.bind()
    table.tamper(creation_time='yesterday')
    result = table.recheck(binding)
    assert result.failures == (CREATION_TIME_UNREADABLE,) and result.binding is None


def test_recheck_compares_the_creation_time_by_value_not_by_identity():
    # attest.py:156 `!=`: under `is not` a creation time that arrives as a fresh,
    # equal float object — which is what a real table read returns — is reported
    # as a recycled PID and the connection loses its binding for no reason.
    table = Table()
    binding = table.bind()
    same_value = CT + 0.0
    assert same_value == binding.creation_time and same_value is not binding.creation_time
    table.process = ProcessInfo(alive=True, creation_time=same_value,
                                ancestors=(LAUNCHER, 'services.exe'), in_core_job=True)
    assert table.recheck(binding).ok


# ── the launcher ancestry is one exact name, matched case-insensitively ─────

def test_accept_matches_the_launcher_in_the_case_it_is_named_in():
    # attest.py:171 lowers the configured launcher as well as the ancestry; drop
    # that half and a differently spelled launcher name refuses every real peer.
    table = Table()
    assert table.attest(launcher=LAUNCHER.upper()).ok


@pytest.mark.parametrize('name', ['not-wxc-exec', 'wxc-exec.exe', 'exec', ''],
                         ids=['prefix', 'suffix', 'shorter', 'empty'])
def test_accept_needs_the_ancestor_to_be_the_launcher_exactly(name):
    # attest.py:171 is element membership in both directions: any substring test
    # would let 'not-wxc-exec', 'exec' or even '' claim the launcher ancestry.
    table = Table()
    table.tamper(ancestors=(name, 'services.exe'))
    result = table.attest()
    assert result.failures == (LAUNCHER_UNPROVEN,) and result.binding is None


# ── the shipped staleness bound is a number, and it is two seconds ──────────

def test_a_binding_past_the_shipped_age_limit_expires_without_reading_the_table():
    # attest.py:58 + 125: no existing test pins DEFAULT_MAX_AGE_S to a value, so
    # widening it to an hour keeps the whole suite green while stale accepts pass.
    table = Table()
    binding = table.bind()
    table.now = T0 + 2.5
    result = table.recheck(binding)                     # max_age_s left at its default
    assert result.failures == (EXPIRED,) and result.binding is None
    assert table.pids == [PID]                          # only the accept-time read


def test_a_binding_inside_the_shipped_age_limit_is_still_usable():
    # the same default, from below: it may not shrink under 1.5 s either.
    table = Table()
    binding = table.bind()
    table.now = T0 + 1.5
    assert table.recheck(binding).ok


def test_a_binding_exactly_at_the_age_limit_is_still_usable():
    # attest.py:141 compares with `>`; turning it into `>=` refuses a binding at
    # the exact age its caller agreed to trust, which no existing test notices.
    table = Table()
    binding = table.bind()
    table.now = T0 + 2.0
    assert table.recheck(binding, max_age_s=2.0).ok


def test_a_binding_whose_accept_time_is_ahead_of_the_clock_expires():
    table = Table()
    binding = table.bind()
    table.now = T0 - 60.0                               # the clock went backwards
    result = table.recheck(binding, max_age_s=2.0)
    assert result.failures == (EXPIRED,) and result.binding is None


def test_a_broken_clock_refuses_before_the_process_table_is_read():
    # attest.py:137-142: the clock is read and judged before any reader is
    # consulted; moving that early return after the read keeps the verdict but
    # lets a table query happen behind a clock nobody can trust.
    table = Table()
    binding = table.bind()
    table.clock_error = RuntimeError('clock unreadable')
    result = table.recheck(binding)
    assert result.failures == (READER_ERROR,) and result.binding is None
    assert table.pids == [PID]
