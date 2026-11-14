"""T-1004: the highest-risk uncovered branches of archeus/node/broker_listener.py lines
1-210 (the whole module; the card's slice is 1-210 inclusive). Fakes only: no real DLL,
no real socket is bound here, no thread outlives a test, no OS call is made unsealed.

The ten selected branches (ranked fail-closed/denial first, then boundaries, then error
paths; evidence for why each is uncovered in /work/QWEN-DONE-T-1004.md):

1. handle()'s blanket refusal when the *handler* (`transport.broker.serve`) itself fails
   after attestation: refusal audited, evidence released, connection closed, nothing
   written (broker_listener.py:125-138). Probe 9.
2. handle() registers the live connection in `_conns` before serving and discards it
   after, so `close()` can cut it (broker_listener.py:112, 136-137).
3. `_admit`'s principal lookup crashing (`_principal_of` raising, not returning None) is
   a refusal, not a served request (broker_listener.py:147 through 128-129).
4. an accepted connection whose socket ends cannot be read is refused *before* the
   backend is asked to attest anything (broker_listener.py:116-119 before 120).
5. `_one` releases its connection slot even when `handle` crashes (broker_listener.py:
   101-105) - slot leak would DoS the grant's listener.
6. repeat close: `close()` twice over sockets whose shutdown *and* close raise OSError
   is silent and complete; `_close`'s second OSError arm (broker_listener.py:48-53,
   166-171). Probe 10.
7. `bind_loopback` closes the socket it made when listen/settimeout fail
   (broker_listener.py:36-45) - a failed bind must leave no half-bound socket.
8. `create` refuses and closes when the bound address is not even parsable as an IP
   (broker_listener.py:185-194) - the loopback check cannot be fooled by garbage.
9. boundary: an IPv6 loopback ('::1') bind is a valid grant (broker_listener.py:189).
10. `_Gate` fires the liveness re-check on the first byte however it arrives - an empty
    read defers it, a non-empty `read()` (not only `readline()`) fires it exactly once,
    and no byte reaches the broker before the check (broker_listener.py:56-70).

Probes 1-6 of the card (unattested accept, USER accept, wrong execution, wrong grant
endpoint, peer changes, revoked grant) and probes 7-8 (malformed request, body cap) are
already covered or belong outside the slice; see the report for the replacements.
"""

import io
import time
from types import SimpleNamespace

import pytest

from archeus.api.origin import OriginClass, OriginEvidence, PathClass
from archeus.core.domain import ids
from archeus.node import broker as B
from archeus.node import broker_listener as L

MODEL = 'claude-x'
KEY = 'sk-ant-api03-UPSTREAM-SECRET'
BODY = b'{"model":"claude-x","messages":[{"role":"user","content":"hi"}]}'
PRINCIPAL = 'archeus.x'
PEER = 54321


def http(token, body=BODY):
    head = ('POST %s HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer %s\r\n'
            'Content-Length: %d\r\n' % ('/v1/messages', token, len(body)))
    return head.encode('latin-1') + b'\r\n' + body


class Listening:
    """A listening socket that accepts what a test queues, and never blocks."""

    ports = iter(range(43000, 44000))

    def __init__(self, host='127.0.0.1'):
        self.host, self.port = host, next(Listening.ports)
        self.queue, self.closed = [], False

    def getsockname(self):
        return (self.host, self.port)

    def accept(self):
        if self.closed:
            raise OSError('closed')
        if self.queue:
            return self.queue.pop(0), ('127.0.0.1', PEER)
        time.sleep(0.01)
        raise TimeoutError

    def shutdown(self, how):
        raise OSError('not connected')

    def close(self):
        self.closed = True


class Conn:
    def __init__(self, port, data=b'', remote=('127.0.0.1', PEER), local=None):
        self.local = local or ('127.0.0.1', port)
        self.remote, self.data = remote, data
        self.out, self.closed, self.shut, self.opened = [], False, False, 0

    def settimeout(self, seconds):
        self.timeout = seconds

    def getsockname(self):
        return self.local

    def getpeername(self):
        return self.remote

    def makefile(self, mode, buffering=-1):
        self.opened += 1
        return io.BytesIO(self.data)

    def sendall(self, data):
        self.out.append(data)

    def shutdown(self, how):
        self.shut = True

    def close(self):
        self.closed = True

    @property
    def sent(self):
        return b''.join(self.out)


class BadEnd(Conn):
    """A connection whose stated ends cannot be read: one named op raises OSError."""

    def __init__(self, port, op, **kw):
        Conn.__init__(self, port, **kw)
        self.failing = op

    def getsockname(self):
        if self.failing == 'local':
            raise OSError('reset')
        return Conn.getsockname(self)

    def getpeername(self):
        if self.failing == 'remote':
            raise OSError('reset')
        return Conn.getpeername(self)


def execution_evidence(ctx, **kw):
    fields = dict(origin=OriginClass.EXECUTION, path=PathClass.UNAPPROVED,
                  identity='process:4124:100', process_binding=object(),
                  accept_generation=ctx.accept_generation, reason='attested')
    fields.update(kw)
    return OriginEvidence(**fields)


class Backend:
    """What the attestor says, and what it was asked, in order."""

    def __init__(self, evidence=execution_evidence, valid=True):
        self.make, self.answer, self.calls = evidence, valid, []

    def attest(self, ctx):
        self.calls.append(('attest', ctx))
        return self.make(ctx)

    def valid(self, ctx, evidence):
        self.calls.append(('valid', ctx))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def release(self, ctx, evidence):
        self.calls.append(('release', ctx))

    def kinds(self):
        return [c[0] for c in self.calls]


class Resp:
    status, reason = 200, 'OK'

    def __init__(self):
        self._c = [b'ok']

    def getheaders(self):
        return [('content-type', 'application/json')]

    def read1(self, n):
        return self._c.pop(0) if self._c else b''


RIGS = []


@pytest.fixture(autouse=True)
def _no_listener_outlives_its_test():
    yield
    while RIGS:
        RIGS.pop().broker.revoke_all()


class Rig:
    """The shipped listener over faked sockets, backend and upstream (as the existing
    test_broker_listener rig fakes them; written self-contained, not imported)."""

    def __init__(self, backend=None, principal=PRINCIPAL, bind=None, **kw):
        self.backend, self.sent, self.socks = backend or Backend(), [], []
        self.principals = []

        def principal_of(evidence):
            self.principals.append(evidence)
            return principal

        def default_bind():
            sock = Listening()
            self.socks.append(sock)
            return sock

        def send(up, addrs, method, path, headers, body, timeout):
            self.sent.append((method, path, dict(headers), body))
            return Resp()

        kw.setdefault('limits', B.BrokerLimits(max_requests=5))
        self.broker = L.loopback_broker(
            backend_of=lambda port: self.backend, principal_of=principal_of,
            bind=bind or default_bind, core_instance='core1',
            live=lambda bd, d: True, credentials=lambda bd: {'x-api-key': KEY},
            upstream_of=lambda a: B.Upstream('https://api.example.com'),
            resolve=lambda host, port: ['93.184.216.34'], send=send, **kw)
        RIGS.append(self)

    def grant(self, **kw):
        bd = B.BrokerBinding(**dict(dict(
            core_instance='core1', execution_id=ids.new_id('execution'), process_seq=1,
            principal=PRINCIPAL, route_decision_id='rte_1', account_id='acc_1',
            harness_id='claude_code', model=MODEL, upstream=B.Upstream('https://api.example.com'),
            limits=B.BrokerLimits(max_requests=5)), **kw))
        token, digest, endpoint, port = self.broker.issue(bd)
        return SimpleNamespace(bd=bd, token=token, digest=digest, ep=endpoint, port=port)

    def get(self, g, data=None, conn=None):
        conn = conn or Conn(g.port, http(g.token) if data is None else data)
        g.ep.handle(conn)
        return conn

    def audit(self):
        return list(self.broker.audit)


def status(conn):
    return int(conn.sent.split(b' ', 2)[1]) if conn.sent else None


# 1. the handler itself failing is a refusal, not a half-served connection

def test_a_handler_that_crashes_after_attestation_refuses_and_releases_the_peer():
    rig = Rig()
    g = rig.grant()

    reached = []

    def crashing_serve(*args, **kw):
        reached.append(1)
        raise RuntimeError('the handler died')

    rig.broker.serve = crashing_serve
    conn = rig.get(g)
    assert reached == [1]           # the refusal is the handler's crash, not an earlier one
    assert conn.sent == b'' and conn.closed and conn.shut and rig.sent == []
    assert rig.backend.kinds() == ['attest', 'release']
    row = rig.audit()[-1]
    assert row['endpoint'] == 'accept:error' and row['status'] == 403
    assert row['execution_id'] == g.bd.execution_id


# 2. a connection is cut-able while it is served, and gone after

def test_a_served_connection_is_registered_for_the_close_and_dropped_after():
    rig = Rig()
    g = rig.grant()
    real = rig.broker.serve
    during = []

    def spying_serve(rfile, write, principal, endpoint=None):
        during.append((conn in g.ep._conns, g.ep._closed))
        return real(rfile, write, principal, endpoint)

    conn = Conn(g.port, http(g.token))
    rig.broker.serve = spying_serve
    g.ep.handle(conn)
    assert during == [(True, False)] and status(conn) == 200
    assert conn not in g.ep._conns and conn.closed


# 3. a principal lookup that crashes is a refusal, not an unattested pass

def test_a_principal_lookup_that_crashes_is_a_refusal_not_a_served_request():
    rig = Rig()

    def crashing_principal_of(evidence):
        raise RuntimeError('the process table died')

    rig.broker.transport._principal_of = crashing_principal_of
    g = rig.grant()
    conn = rig.get(g)
    assert conn.sent == b'' and conn.closed and conn.shut and rig.sent == []
    assert conn.opened == 0         # refused at admission: the request was never opened
    assert rig.backend.kinds() == ['attest', 'release']
    assert rig.audit()[-1]['endpoint'] == 'accept:error'


# 4. the ends are read before anything is attested; failure there is a closed refusal

@pytest.mark.parametrize('op', ['local', 'remote'])
def test_a_connection_whose_ends_cannot_be_read_is_refused_before_attestation(op):
    rig = Rig()
    g = rig.grant()
    conn = BadEnd(g.port, op, data=http(g.token))
    g.ep.handle(conn)
    assert conn.sent == b'' and conn.closed and rig.sent == []
    assert rig.backend.calls == []                      # nothing was attested or released
    assert rig.audit()[-1]['endpoint'] == 'accept:error' and rig.audit()[-1]['status'] == 403


# 5. a crashed connection gives its slot back

def test_a_crashed_connection_frees_its_slot():
    rig = Rig()
    g = rig.grant()
    ep = g.ep

    def crashing_handle(conn):
        raise RuntimeError('handle died')

    ep.handle = crashing_handle
    for _ in range(L.MAX_CONNECTIONS):
        assert ep._slots.acquire(blocking=False)        # the listener is at its cap
    with pytest.raises(RuntimeError):
        ep._one(object())                               # _one lets the crash travel
    assert ep._slots.acquire(blocking=False) is True    # exactly one slot came back
    assert ep._slots.acquire(blocking=False) is False


# 6. closing the same grant again cuts everything and never raises

class RaiseSock:
    """A socket on which every end operation raises OSError, counting the attempts."""

    def __init__(self, port=44555):
        self.port, self.closes, self.shuts = port, 0, 0

    def getsockname(self):
        return ('127.0.0.1', self.port)

    def shutdown(self, how):
        self.shuts += 1
        raise OSError('not connected')

    def close(self):
        self.closes += 1
        raise OSError('bad descriptor')


def test_closing_the_same_grant_twice_cuts_everything_and_never_raises():
    sock, held = RaiseSock(), [RaiseSock(), RaiseSock()]
    transport = L.LoopbackTransport(backend_of=lambda port: Backend(),
                                    principal_of=lambda e: PRINCIPAL, bind=lambda: sock)
    endpoint = transport.create('name', 'p')
    endpoint._conns.update(held)
    transport.close(endpoint)
    transport.close(endpoint)
    endpoint.close()
    assert endpoint._closed
    assert sock.shuts == sock.closes == 3 and all(s.closes == 3 for s in held)


# 7. a bind that fails leaves no half-made socket behind

def test_a_bind_that_fails_closes_the_socket_it_made_before_failing(monkeypatch):
    class HalfBound:
        def __init__(self):
            self.bound, self.timeout, self.closed = None, None, False

        def bind(self, addr):
            self.bound = addr

        def listen(self, backlog):
            raise OSError('backlog refused')

        def settimeout(self, seconds):
            self.timeout = seconds

        def close(self):
            self.closed = True

    made = HalfBound()
    monkeypatch.setattr(L.socket, 'socket', lambda *a, **kw: made)
    with pytest.raises(OSError):
        L.bind_loopback()
    assert made.bound == (L.HOST, 0) and made.closed is True


# 8. a bind that reports an unparsable address is refused, and its socket closed

def test_a_bind_that_reports_an_unparsable_address_is_refused_and_closed():
    socks = []

    def bind():
        socks.append(Listening('not-an-address'))
        return socks[-1]

    rig = Rig(bind=bind)
    with pytest.raises(ValueError):
        rig.grant()
    assert socks[0].closed and rig.broker._grants == {}


# 9. boundary: an IPv6 loopback bind is a real grant

def test_an_ipv6_loopback_bind_is_a_real_grant():
    asked = []
    socks = []

    def bind():
        socks.append(Listening('::1'))
        return socks[-1]

    rig = Rig(bind=bind)
    rig.broker.transport._backend_of = lambda port: (asked.append(port), rig.backend)[1]
    g = rig.grant()
    assert g.port == socks[0].port and asked == [g.port] and not socks[0].closed
    assert rig.broker.reach(g.bd.execution_id) == g.port and g.ep.binding is g.bd


# 10. the re-check waits for the first byte and fires on it however it arrives

class Reader:
    def __init__(self, lines=(), chunks=()):
        self.lines, self.chunks = list(lines), list(chunks)

    def readline(self, n):
        return self.lines.pop(0)

    def read(self, n):
        return self.chunks.pop(0)


def test_the_first_request_byte_fires_the_recheck_however_it_arrives():
    fired = []
    gate = L._Gate(Reader(lines=[b'', b'x'], chunks=[b'', b'body']),
                   lambda: fired.append(1))
    assert gate.read(64) == b'' and gate.readline(64) == b''
    assert fired == []                                  # no byte yet: no re-check
    assert gate.read(64) == b'body'
    assert len(fired) == 1                              # first byte, via read(), fires it
    assert gate.readline(64) == b'x'
    assert len(fired) == 1                              # and only once, via readline too


def test_no_request_byte_is_handed_over_before_the_recheck_has_run():
    def refusing_check():
        raise RuntimeError('the peer changed')

    gate = L._Gate(Reader(chunks=[b'body']), refusing_check)
    with pytest.raises(RuntimeError):
        gate.read(64)                                   # the byte never reaches the broker
