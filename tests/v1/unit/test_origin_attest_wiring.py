"""T-456 (audit slice 10): the PID-plus-creation-time attestor wired into the origin
gate. `WindowsOriginBackend` asks `attest.attest_owner(...)` once at accept with
injected readers, keeps the returned `ProcessBinding` on the evidence the connection
holds, and asks `attest.binding_valid(...)` again before every privileged effect.

The outside world is a fake process table (port -> owner, PID -> observation, clock)
and the connections are built by hand on the real `server.Handler` methods, in the
order `_serve` uses them: transport re-check, gate, effect. No Windows API, no
socket, no real process, no network: the same assertions hold on every platform.
Every refusal test states its control first (a healthy table effects), so a removed
check shows up as an effect that should have been refused, and names its branch by
the exact failure the attestor reports for the same table.
"""

import inspect
import socketserver
from types import SimpleNamespace

import pytest

from archeus.api import auth, origin, server
from archeus.node.attest import (
    CREATION_TIME_MISMATCH,
    CREATION_TIME_UNREADABLE,
    DEAD,
    DEFAULT_LAUNCHER,
    DEFAULT_MAX_AGE_S,
    EXPIRED,
    LAUNCHER_UNPROVEN,
    NO_BINDING,
    OUTSIDE_CORE_JOB,
    READER_ERROR,
    ProcessBinding,
    ProcessInfo,
    PeerOwner,
    binding_valid,
)
from archeus.node.origin_windows import WindowsOriginBackend

PORT = 54321
PID = 4124
CT = 100.0
T0 = 1000.0
CORE_PORT = 8731
GOOD = ProcessInfo(alive=True, creation_time=CT,
                   ancestors=(DEFAULT_LAUNCHER, 'services.exe'), in_core_job=True)


class FakeTable:
    """The whole outside world of the attestor: one peer port, one PID, one clock."""

    def __init__(self):
        self.process = GOOD
        self.owner_error = None
        self.process_error = None
        self.now = T0
        self.events = []
        self.ports_queried = []
        self.pids_read = []

    def resolve_owner(self, port):
        self.events.append('attest')
        self.ports_queried.append(port)
        if self.owner_error is not None:
            raise self.owner_error
        return PeerOwner(pid=PID if port == PORT else None)

    def read_process(self, pid):
        self.events.append('recheck')
        self.pids_read.append(pid)
        if self.process_error is not None:
            raise self.process_error
        return self.process if pid == PID else None

    def clock(self):
        return self.now

    def readers(self, **overrides):
        return origin.AttestationReaders(resolve_owner=self.resolve_owner,
                                         read_process=self.read_process,
                                         clock=self.clock, **overrides)

    def context(self, generation='gen-1'):
        return origin.ConnectionContext(object(), ('127.0.0.1', CORE_PORT),
                                        ('127.0.0.1', PORT), generation)

    def tamper(self, **changes):
        self.process = GOOD._replace(**changes)

    def verdict(self, binding):
        """The attestor's own verdict on *binding*, through the real readers, with
        the counters of that extra probe taken back out again."""
        ports, pids, events = len(self.ports_queried), len(self.pids_read), len(self.events)
        result = binding_valid(binding, read_process=self.read_process, clock=self.clock)
        del self.ports_queried[ports:], self.pids_read[pids:], self.events[events:]
        return result


def _connect(table, *, readers='default'):
    """A connection as `Handler.setup` leaves it; *readers* 'default' is the shipped
    bundle, None is the production default of no readers at all."""
    bundle = table.readers() if readers == 'default' else readers
    handler = object.__new__(server.Handler)
    handler.context = table.context()
    handler.evidence, handler.evidence_acquired = None, False
    handler.origin_backend = WindowsOriginBackend(readers=bundle)
    handler.origin_registry = SimpleNamespace(approved=lambda context, evidence: True)
    handler.api = SimpleNamespace(origin=auth.Origin(CORE_PORT),
                                  origin_enforcement_enabled=True)
    handler.server = SimpleNamespace(api=handler.api)
    handler.attested = None
    handler.headers = {'Host': '127.0.0.1:%d' % CORE_PORT}
    handler.principal = {'origin': 'local'}
    handler.effects = []
    return handler


def _request(handler):
    """One request in `_serve`'s order: the transport re-check, then the effect when it
    holds. The effect is what a route that accepts an attested execution would do; the
    user gate itself is `origin_allows`, pinned apart below."""
    handler.attested = handler.transport_evidence()
    if handler.attested.process_binding is None:
        return 'refused'
    handler.effects.append('effect')
    return 'effected'


@pytest.fixture
def table():
    return FakeTable()


# ── accept: attest once, keep the binding on the connection ──

def test_the_binding_is_attested_once_at_accept_and_rechecked_on_every_request(table):
    handler = _connect(table)
    for _ in range(3):
        assert _request(handler) == 'effected'
    assert table.ports_queried == [PORT]                        # attest_owner once, at accept
    assert table.pids_read == [PID, PID, PID, PID]              # accept plus one re-check each
    binding = handler.evidence.process_binding
    assert isinstance(binding, ProcessBinding)
    assert (binding.remote_port, binding.pid, binding.creation_time) == (PORT, PID, CT)
    assert binding.accepted_at == T0 and binding.core_job_at_accept is True


def test_the_binding_travels_on_the_evidence_the_connection_holds(table):
    handler = _connect(table)
    assert _request(handler) == 'effected'
    assert handler.evidence.origin == origin.OriginClass.EXECUTION
    assert handler.evidence.path == origin.PathClass.UNAPPROVED
    assert origin.validate_evidence(handler.context, handler.evidence)
    assert handler.origin_backend.valid(handler.context, handler.evidence) is True
    handler.origin_registry = origin.UnapprovedRegistry()       # Core approval is still its own
    assert _request(handler) == 'refused'


def test_the_owner_is_resolved_from_the_accepted_peer_port(table):
    handler = _connect(table)
    assert _request(handler) == 'effected'
    assert table.ports_queried == [PORT]


def test_every_new_accept_generation_attests_again(table):
    first, second = _connect(table), _connect(table)
    second.context = table.context('gen-2')
    assert _request(first) == 'effected' and _request(second) == 'effected'
    assert first.context.accept_generation != second.context.accept_generation
    assert table.ports_queried == [PORT, PORT]


def test_a_process_proven_inside_the_job_is_an_execution_and_never_the_user(table):
    handler = _connect(table)
    assert _request(handler) == 'effected'
    assert handler.attested.origin == origin.OriginClass.EXECUTION
    for credential in (None, 'local', 'paired'):
        assert handler.origin_allows(credential) is False


def test_a_binding_of_another_peer_port_is_refused(table):
    handler = _connect(table)
    assert _request(handler) == 'effected'
    other = table.context()
    other = origin.ConnectionContext(other.socket, other.local_endpoint,
                                     ('127.0.0.1', PORT + 1), other.accept_generation)
    assert handler.origin_backend.valid(handler.context, handler.evidence) is True
    assert handler.origin_backend.valid(other, handler.evidence) is False


def test_the_binding_is_taken_at_accept_not_at_the_first_request(table, monkeypatch):
    monkeypatch.setattr(socketserver.StreamRequestHandler, 'setup', lambda self: None)
    api = SimpleNamespace(instance='i', origin_enforcement_enabled=True,
                          origin_backend=WindowsOriginBackend(readers=table.readers()),
                          origin_registry=SimpleNamespace(approved=lambda c, e: True))
    handler = object.__new__(server.Handler)
    handler.request = SimpleNamespace(getsockname=lambda: ('127.0.0.1', CORE_PORT))
    handler.client_address = ('127.0.0.1', PORT)
    handler.server = SimpleNamespace(api=api, accept_generations=iter(range(5)))
    handler.setup()
    assert table.ports_queried == [PORT] and handler.evidence_acquired is True
    assert handler.evidence.process_binding is not None
    api.origin_enforcement_enabled = False
    other = object.__new__(server.Handler)
    other.request, other.client_address, other.server = (
        handler.request, handler.client_address, handler.server)
    other.setup()
    assert table.ports_queried == [PORT] and other.evidence_acquired is False


# ── every privileged effect re-checks first ──

def test_the_binding_is_rechecked_before_the_effect_and_not_after(table):
    handler = _connect(table)
    assert _request(handler) == 'effected'
    assert table.events == ['attest', 'recheck', 'recheck']     # attested, then re-checked
    assert handler.effects == ['effect']                        # the effect came last
    before = len(table.pids_read)
    assert handler.origin_holds() is False                      # an execution is not the user
    assert len(table.pids_read) == before + 1                   # but the stream still re-checks


def test_the_request_gate_precedes_the_route_handler():
    serve = inspect.getsource(server.Handler._serve)
    effect = serve.index('route.handler(self)')
    assert serve.index('self.transport_evidence()') < effect
    assert 'self.api.origin_enforcement_enabled' in serve[:effect]
    holds = inspect.getsource(server.Handler.origin_holds)
    assert holds.index('self.transport_evidence()') < holds.index('self.origin_allows(')


@pytest.mark.parametrize('tamper,reason', [
    ({'creation_time': CT + 0.5}, CREATION_TIME_MISMATCH),      # the recycled PID
    ({'alive': False}, DEAD),
    ({'creation_time': None}, CREATION_TIME_UNREADABLE),
    ({'in_core_job': False}, OUTSIDE_CORE_JOB),
    ({'ancestors': ('svchost.exe',)}, LAUNCHER_UNPROVEN),
])
def test_a_binding_the_table_no_longer_supports_is_refused_before_the_effect(table,
                                                                             tamper, reason):
    handler = _connect(table)
    assert _request(handler) == 'effected'                      # the control
    table.tamper(**tamper)
    assert _request(handler) == 'refused'
    assert len(handler.effects) == 1                            # only the control effected
    assert table.verdict(handler.evidence.process_binding).failures == (reason,)


def test_a_recycled_pid_never_effects_again_within_the_binding_age(table):
    handler = _connect(table)
    assert _request(handler) == 'effected'
    table.tamper(creation_time=CT + 1.0)                        # the PID now names another run
    assert _request(handler) == 'refused'
    assert table.ports_queried == [PORT]                        # never re-attested


def test_a_missing_binding_is_refused(table):
    handler = _connect(table)
    assert _request(handler) == 'effected'
    handler.evidence = origin.OriginEvidence(accept_generation=handler.context.accept_generation)
    handler.evidence_acquired = True                            # as an accept that bound nothing
    assert _request(handler) == 'refused'
    assert table.verdict(handler.evidence.process_binding).failures == (NO_BINDING,)


def test_a_binding_of_another_connection_is_refused(table):
    handler = _connect(table)
    assert _request(handler) == 'effected'
    handler.evidence = origin.OriginEvidence(
        origin=origin.OriginClass.EXECUTION, identity='x',
        process_binding=handler.evidence.process_binding, accept_generation='gen-2',
        reason='attested')
    handler.evidence_acquired = True
    assert _request(handler) == 'refused'


def test_an_expired_binding_is_refused_and_a_longer_max_age_is_not(table):
    handler = _connect(table)
    assert _request(handler) == 'effected'
    table.now = T0 + DEFAULT_MAX_AGE_S + 0.5                    # the accept is too old to trust
    assert _request(handler) == 'refused'
    assert table.verdict(handler.evidence.process_binding).failures == (EXPIRED,)
    roomier = _connect(table, readers=table.readers(max_age_s=DEFAULT_MAX_AGE_S * 10))
    assert _request(roomier) == 'effected'
    table.now += DEFAULT_MAX_AGE_S * 4                          # older than the shipped limit
    assert _request(roomier) == 'effected'                      # inside the one it was given
    table.now += DEFAULT_MAX_AGE_S * 10
    assert _request(roomier) == 'refused'                       # and past its own


def test_an_owner_reader_that_raises_at_accept_refuses_the_connection(table):
    table.owner_error = OSError('the table query failed')
    handler = _connect(table)
    assert _request(handler) == 'refused'
    assert handler.evidence.process_binding is None
    assert handler.evidence.origin == origin.OriginClass.UNDETERMINED
    assert handler.evidence.reason == READER_ERROR              # the refusal names why


def test_a_process_reader_that_raises_refuses_the_effect(table):
    handler = _connect(table)
    assert _request(handler) == 'effected'
    table.process_error = OSError('the process died under the query')
    assert _request(handler) == 'refused'
    assert handler.attested.origin == origin.OriginClass.UNDETERMINED
    assert table.verdict(handler.evidence.process_binding).failures == (READER_ERROR,)


def test_an_owner_that_is_gone_from_the_table_refuses_the_connection(table):
    handler = _connect(table)
    assert _request(handler) == 'effected'
    table.process = None                                        # the PID names nothing at all
    assert _request(handler) == 'refused'


def test_the_launcher_the_core_runs_under_is_the_one_named(table):
    table.tamper(ancestors=('Other-Exec', 'services.exe'))
    assert _request(_connect(table)) == 'refused'               # the shipped launcher's name
    assert _request(_connect(table, readers=table.readers(launcher='other-exec'))) == 'effected'


def test_an_unproven_launcher_is_refused_at_accept(table):
    table.tamper(ancestors=('svchost.exe',))
    handler = _connect(table)
    assert _request(handler) == 'refused'
    assert handler.evidence.process_binding is None
    assert handler.evidence.reason == LAUNCHER_UNPROVEN         # the refusal names why
    assert table.ports_queried == [PORT]


# ── the default wiring (no reader supplied) is exactly today's ──

def test_a_backend_with_no_readers_still_authorizes_nothing(table):
    backend, context = WindowsOriginBackend(), table.context()
    assert backend.attest(context) == origin.OriginEvidence(accept_generation='gen-1')
    assert backend.valid(context, origin.OriginEvidence(
        origin=origin.OriginClass.EXECUTION, identity='x',
        process_binding=object(), accept_generation='gen-1', reason='attested')) is False
    assert backend.release(context, None) is None
    assert table.ports_queried == [] and table.pids_read == []


def test_a_connection_on_the_shipped_backend_is_refused_on_every_route(table):
    handler = _connect(table, readers=None)
    assert _request(handler) == 'refused'
    assert not any(handler.origin_allows(credential) for credential in (None, 'local', 'paired'))
    assert handler.origin_holds() is False
    assert handler.attested.origin == origin.OriginClass.UNDETERMINED
    assert table.ports_queried == [] and table.pids_read == []


def test_the_shipped_api_still_carries_a_backend_with_no_readers():
    api = server.Api(db=None, missions=SimpleNamespace(policy=None), port=CORE_PORT,
                     health=None, version='x')
    assert isinstance(api.origin_backend, WindowsOriginBackend)
    assert api.origin_backend.readers is None
    assert api.origin_enforcement_enabled is False
