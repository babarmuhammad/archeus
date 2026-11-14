"""T-819 hand-mutant pins on `archeus/node/origin_windows.py`. Each test names a
condition that the existing origin tests leave green when it is inverted, removed
or loosened (the run is `/work/scratch/mutcheck.py`), and fails on that mutation
alone. No Windows API, no socket, no real process, no network: the attestor is the
real pure one over a fake process table, or a stub that hands back the results the
real one cannot produce, and every context is built by hand with an explicit port.

Not duplicated here: the branches the existing suites already turn red on are listed
as COVERED in the card report (attest/valid reader guards, the port key, the EXECUTION
class, the carried binding and generation, the port guard, `.ok`, the re-check kwargs).
"""

from types import SimpleNamespace

from archeus.api import origin
from archeus.node import attest, origin_windows
from archeus.node.attest import (
    DEAD,
    DEFAULT_LAUNCHER,
    OUTSIDE_CORE_JOB,
    AttestResult,
    PeerOwner,
    ProcessBinding,
    ProcessInfo,
)

HOST = '127.0.0.1'
CORE_PORT = 8731
PORT = 54321
PID = 4124
CT = 1601234567
T0 = 1000.0
GENERATION = 'gen-1'
GOOD = ProcessInfo(alive=True, creation_time=CT, ancestors=(DEFAULT_LAUNCHER, 'services.exe'),
                   in_core_job=True)


def _context(port=PORT, generation=GENERATION):
    return origin.ConnectionContext(object(), (HOST, CORE_PORT), (HOST, port), generation)


def _binding(port=PORT, pid=PID, creation_time=CT):
    return ProcessBinding(remote_port=port, pid=pid, creation_time=creation_time,
                          accepted_at=T0, core_job_at_accept=True)


def _evidence(**over):
    fields = dict(origin=origin.OriginClass.EXECUTION, identity='process:%d:%s' % (PID, CT),
                  process_binding=_binding(), accept_generation=GENERATION, reason='attested')
    fields.update(over)
    return origin.OriginEvidence(**fields)


class _Table:
    """Port -> one PID, PID -> one observation, one clock: the attestor's whole world."""

    def __init__(self, **over):
        self.process = GOOD._replace(**over)
        self.now = T0

    def resolve_owner(self, port):
        return PeerOwner(pid=PID if port == PORT else None)

    def read_process(self, pid):
        return self.process if pid == PID else None

    def clock(self):
        return self.now

    def readers(self, **overrides):
        return origin.AttestationReaders(resolve_owner=self.resolve_owner,
                                         read_process=self.read_process,
                                         clock=self.clock, **overrides)


class _StubAttest:
    """The attestor seam: hands back whatever verdict the real one never returns."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def attest_peer(self, **kwargs):
        self.calls.append(('attest', kwargs))
        return self.result

    def binding_valid(self, binding, **kwargs):
        self.calls.append(('recheck', binding, kwargs))
        return self.result


def _backend(table=None, readers='default'):
    bundle = table.readers() if readers == 'default' else readers
    return origin_windows.WindowsOriginBackend(readers=bundle)


def _refusal_reason(**defects):
    return _backend(_Table(**defects)).attest(_context()).reason


# ── attest: the verdict it is handed decides the answer, never the binding alone ──

def test_an_attestation_that_failed_binds_nothing_even_if_a_binding_arrives(monkeypatch):
    stub = _StubAttest(AttestResult(False, _binding(), (DEAD,)))
    monkeypatch.setattr(origin_windows, '_attest', stub)
    evidence = _backend(_Table()).attest(_context())
    assert evidence.origin is origin.OriginClass.UNDETERMINED
    assert evidence.path is origin.PathClass.UNAPPROVED
    assert evidence.process_binding is None
    assert evidence.identity is None
    assert evidence.reason == DEAD
    assert evidence.accept_generation == GENERATION
    stub.result = AttestResult(True, _binding(), ())
    bound = _backend(_Table()).attest(_context())
    assert bound.origin is origin.OriginClass.EXECUTION
    assert bound.process_binding == _binding()


def test_an_attestation_with_no_binding_binds_nothing_however_it_passed(monkeypatch):
    stub = _StubAttest(AttestResult(True, None, ()))
    monkeypatch.setattr(origin_windows, '_attest', stub)
    evidence = _backend(_Table()).attest(_context())
    assert evidence.origin is origin.OriginClass.UNDETERMINED
    assert evidence.path is origin.PathClass.UNAPPROVED
    assert evidence.process_binding is None
    assert evidence.identity is None
    stub.result = AttestResult(True, _binding(), ())
    assert _backend(_Table()).attest(_context()).process_binding == _binding()


def test_a_refusal_that_has_no_failure_to_name_says_no_evidence(monkeypatch):
    stub = _StubAttest(AttestResult(True, None, ()))
    monkeypatch.setattr(origin_windows, '_attest', stub)
    backend = _backend(_Table())
    assert backend.attest(_context()).reason == 'no_evidence'
    assert origin_windows.NO_EVIDENCE == 'no_evidence'
    stub.result = AttestResult(False, None, (DEAD,))
    assert backend.attest(_context()).reason == 'dead'


def test_a_refusal_names_the_first_failure_and_not_the_last_one():
    table = _Table(alive=False, in_core_job=False)
    assert attest.attest_owner(**table.readers().attest_kwargs(PORT)).failures == (
        DEAD, OUTSIDE_CORE_JOB)
    assert _refusal_reason(alive=False, in_core_job=False) == 'dead'
    assert _refusal_reason(alive=False) == 'dead'
    assert _refusal_reason(in_core_job=False) == 'outside_core_job'


def test_an_attested_peer_is_named_by_pid_and_creation_time_together():
    table = _Table()
    backend = _backend(table)
    assert backend.attest(_context()).identity == 'process:%d:%d' % (PID, CT)
    table.process = GOOD._replace(creation_time=CT + 1)
    recycled = backend.attest(_context())
    assert recycled.identity == 'process:%d:%d' % (PID, CT + 1)
    assert recycled.identity != 'process:%d' % PID


def test_an_attested_connection_carries_the_attested_reason_code():
    assert _backend(_Table()).attest(_context()).reason == 'attested'
    assert origin_windows.ATTESTED == 'attested'


# ── valid: a refusal, never a crash, on the shapes the guard reads by getattr ──

def test_valid_refuses_a_matching_binding_when_the_backend_has_no_readers():
    evidence = _evidence()
    assert origin_windows.WindowsOriginBackend().valid(_context(), evidence) is False
    assert _backend(_Table()).valid(_context(), evidence) is True


def test_valid_refuses_evidence_that_carries_no_binding_field_at_all():
    backend = _backend(_Table())
    assert backend.valid(_context(), SimpleNamespace()) is False
    assert backend.valid(_context(), _evidence()) is True


def test_valid_refuses_a_binding_that_carries_no_remote_port():
    backend = _backend(_Table())
    assert backend.valid(_context(), _evidence(process_binding=object())) is False
    assert backend.valid(_context(), _evidence(process_binding=None)) is False
    assert backend.valid(_context(), _evidence(process_binding=_binding())) is True
