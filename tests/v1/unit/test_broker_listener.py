"""PV-20 B10: the broker's MXC transport - one attested loopback listener per grant.

Fakes only: the listening socket, the accepted connections and the process table are in
memory; the two tests that open a socket bind 127.0.0.1 on an ephemeral port inside this
process and talk to it from this process. Nothing native runs, no admission switch is
opened, and nothing reaches the network."""

import io
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from archeus.api import origin
from archeus.api.origin import OriginClass, OriginEvidence, PathClass
from archeus.core.domain import ids
from archeus.node import broker as B
from archeus.node import broker_listener as L
from archeus.node import local, mxc
from archeus.node.origin_native import ESTABLISHED, RawProcess, TcpRow, native_readers
from archeus.node.origin_windows import WindowsOriginBackend

from .test_mxc_boundary import Made, gate, make, request as boundary_request, sdk  # noqa: F401

MODEL = 'claude-x'
KEY = 'sk-ant-api03-UPSTREAM-SECRET'
BODY = b'{"model":"claude-x","messages":[{"role":"user","content":"hi"}]}'
PRINCIPAL = 'archeus.x'
PEER = 54321
JOB = 777
SESSION = 2
T0 = 1000.0


def http(token, method='POST', target='/v1/messages', body=BODY):
    head = '%s %s HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer %s\r\n' % (
        method, target, token)
    if method == 'POST':
        head += 'Content-Length: %d\r\n' % len(body)
    else:
        body = b''
    return head.encode('latin-1') + b'\r\n' + body


class Listening:
    """A listening socket that accepts what a test queues, and never blocks."""
    ports = iter(range(41000, 42000))

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
    def __init__(self, port, data=b'', remote=('127.0.0.1', PEER), local=None, on_open=None):
        self.local = local or ('127.0.0.1', port)
        self.remote, self.data, self.on_open = remote, data, on_open
        self.out, self.closed, self.shut, self.opened = [], False, False, 0

    def settimeout(self, seconds):
        self.timeout = seconds

    def getsockname(self):
        return self.local

    def getpeername(self):
        return self.remote

    def makefile(self, mode):
        self.opened += 1
        if self.on_open:
            self.on_open()
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
    def __init__(self, backend=None, principal=PRINCIPAL, bind=None, live=True, **kw):
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

        self.broker = L.loopback_broker(
            backend_of=lambda port: self.backend, principal_of=principal_of,
            bind=bind or default_bind, core_instance='core1',
            live=live if callable(live) else (lambda bd, d: live),
            credentials=lambda bd: {'x-api-key': KEY},
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

    def get(self, g, data=None, **kw):
        conn = Conn(g.port, http(g.token) if data is None else data, **kw)
        g.ep.handle(conn)
        return conn

    def audit(self):
        return list(self.broker.audit)


def status(conn):
    return int(conn.sent.split(b' ', 2)[1]) if conn.sent else None


def wait(cond):
    end = time.monotonic() + 3
    while not cond():
        assert time.monotonic() < end
        time.sleep(0.005)


# ── a grant is a listener ──

def test_a_grant_binds_a_loopback_listener_and_answers_its_port():
    rig = Rig()
    g = rig.grant()
    assert g.port == rig.socks[0].port == rig.broker.reach(g.bd.execution_id)
    grant = rig.broker._grants[g.digest]
    assert grant['port'] == g.port and grant['endpoint'] is g.ep


def test_the_grant_is_bound_to_its_execution_process_route_account_and_model():
    rig = Rig()
    g = rig.grant(process_seq=3, route_decision_id='rte_9', account_id='acc_9')
    b = rig.broker._grants[g.digest]['binding']
    assert (b.execution_id, b.process_seq, b.route_decision_id, b.account_id, b.model) == (
        g.bd.execution_id, 3, 'rte_9', 'acc_9', MODEL)
    assert g.ep.binding is g.bd


def test_reach_is_none_without_a_grant_and_after_it_ends():
    rig = Rig()
    assert rig.broker.reach('execution_x') is None
    g = rig.grant()
    rig.broker.revoke(g.bd.execution_id)
    assert rig.broker.reach(g.bd.execution_id) is None


def test_two_grants_are_two_listeners_and_a_resume_replaces_the_first():
    rig = Rig()
    a, b = rig.grant(), rig.grant()
    assert a.port != b.port and not rig.socks[0].closed and not rig.socks[1].closed
    again = rig.grant(execution_id=a.bd.execution_id, process_seq=2)
    assert rig.socks[0].closed and not rig.socks[2].closed
    assert rig.broker.reach(a.bd.execution_id) == again.port


@pytest.mark.parametrize('host', ['0.0.0.0', '192.168.1.5', '::', '10.0.0.2'])
def test_a_listener_that_is_not_on_loopback_is_refused_and_closed(host):
    socks = []

    def bind():
        socks.append(Listening(host))
        return socks[-1]

    rig = Rig(bind=bind)
    with pytest.raises(B.BrokerUnavailable):
        rig.grant()
    assert socks[0].closed and rig.broker._grants == {}


def test_a_backend_that_cannot_be_built_leaves_no_listener_and_no_grant():
    rig = Rig()

    def broken(port):
        raise RuntimeError('no readers')

    rig.broker.transport._backend_of = broken
    with pytest.raises(RuntimeError):
        rig.grant()
    assert rig.socks[0].closed and rig.broker._grants == {}


def test_a_transport_with_no_broker_serves_nothing():
    sock = Listening()
    t = L.LoopbackTransport(backend_of=lambda port: Backend(), principal_of=lambda e: 'p',
                            bind=lambda: sock)
    ep = t.create('name', 'p')
    with pytest.raises(B.BrokerUnavailable):
        t.launch_bridge(ep, None)


def test_the_loopback_broker_is_never_the_default_transport():
    assert isinstance(B.Broker(core_instance='c', live=None, credentials=None,
                               upstream_of=None).transport, B.NativeTransport)
    assert B.BROKER_DISPATCH_ENABLED is False and origin.ORIGIN_ENFORCEMENT_ENABLED is False


# ── attestation at accept ──

def test_an_attested_execution_with_its_token_is_served():
    rig = Rig()
    g = rig.grant()
    conn = rig.get(g)
    assert status(conn) == 200 and len(rig.sent) == 1
    assert rig.sent[0][3] == BODY and rig.sent[0][2]['x-api-key'] == KEY
    assert conn.closed and conn.timeout == L.wire.IDLE_S


def test_the_connection_is_attested_before_a_byte_of_it_is_read():
    rig = Rig()
    g = rig.grant()
    conn = Conn(g.port, http(g.token),
                on_open=lambda: rig.backend.calls.append(('open', None)))
    g.ep.handle(conn)
    assert rig.backend.kinds()[:2] == ['attest', 'open']


def test_the_attestor_sees_the_accepted_socket_and_both_of_its_ends():
    rig = Rig()
    g = rig.grant()
    conn = rig.get(g)
    ctx = rig.backend.calls[0][1]
    assert ctx.socket is conn and ctx.remote_endpoint == ('127.0.0.1', PEER)
    assert ctx.local_endpoint == ('127.0.0.1', g.port) and len(ctx.accept_generation) >= 32


def test_every_connection_has_its_own_accept_generation():
    rig = Rig()
    g = rig.grant()
    rig.get(g)
    rig.get(g)
    gens = {c[1].accept_generation for c in rig.backend.calls if c[0] == 'attest'}
    assert len(gens) == 2


def _no_evidence(ctx):
    return OriginEvidence(accept_generation=ctx.accept_generation)


REFUSED = [
    ('undetermined', _no_evidence, 'invalid_evidence'),
    ('undetermined with a binding',
     lambda c: execution_evidence(c, origin=OriginClass.UNDETERMINED), 'origin_undetermined'),
    ('user', lambda c: execution_evidence(c, origin=OriginClass.USER, path=PathClass.DIRECT_LOCAL),
     'origin_user'),
    ('verifier', lambda c: execution_evidence(c, origin=OriginClass.VERIFIER),
     'origin_verifier'),
    ('no binding', lambda c: execution_evidence(c, process_binding=None), 'invalid_evidence'),
    ('another connection', lambda c: execution_evidence(c, accept_generation='g0'),
     'invalid_evidence'),
    ('no identity', lambda c: execution_evidence(c, identity=None), 'invalid_evidence'),
    ('a string for an origin', lambda c: execution_evidence(c, origin='execution'),
     'invalid_evidence'),
    ('not evidence at all', lambda c: 'execution', 'invalid_evidence'),
    ('none', lambda c: None, 'invalid_evidence'),
    ('raises', lambda c: 1 / 0, 'error'),
]


@pytest.mark.parametrize('name,evidence,why', REFUSED, ids=[r[0] for r in REFUSED])
def test_a_peer_that_is_not_an_attested_execution_is_closed_unread(name, evidence, why):
    rig = Rig(Backend(evidence))
    g = rig.grant()
    conn = rig.get(g)
    assert conn.sent == b'' and conn.opened == 0 and conn.closed and conn.shut
    assert rig.sent == []
    assert rig.audit()[-1]['endpoint'] == 'accept:' + why and rig.audit()[-1]['status'] == 403
    assert rig.audit()[-1]['execution_id'] == g.bd.execution_id


def test_an_attestor_that_hangs_is_a_refusal_not_a_stall(monkeypatch):
    monkeypatch.setattr(origin, 'BACKEND_DEADLINE_S', 0.05)
    release = threading.Event()

    def hang(ctx):
        release.wait(3)
        return execution_evidence(ctx)

    rig = Rig(Backend(hang))
    g = rig.grant()
    started = time.monotonic()
    conn = rig.get(g)
    release.set()
    assert time.monotonic() - started < 2 and conn.sent == b'' and rig.sent == []


@pytest.mark.parametrize('remote', [('10.1.2.3', PEER), ('192.168.0.9', PEER), ('::ffff:8.8.8.8', 1)])
def test_a_peer_that_is_not_on_the_loopback_is_refused_whatever_the_attestor_says(remote):
    rig = Rig()
    g = rig.grant()
    conn = rig.get(g, remote=remote)
    assert conn.sent == b'' and rig.audit()[-1]['endpoint'] == 'accept:not_this_listener'


def test_a_connection_to_another_port_is_refused_whatever_the_attestor_says():
    rig = Rig()
    g = rig.grant()
    conn = rig.get(g, local=('127.0.0.1', g.port + 1))
    assert conn.sent == b'' and rig.audit()[-1]['endpoint'] == 'accept:not_this_listener'


@pytest.mark.parametrize('principal', [None, '', 7, b'archeus.x'])
def test_an_execution_process_that_maps_to_no_principal_is_refused(principal):
    rig = Rig(principal=principal)
    g = rig.grant()
    conn = rig.get(g)
    assert conn.sent == b'' and rig.sent == []
    assert rig.audit()[-1]['endpoint'] == 'accept:no_principal'


def test_the_principal_the_backend_observed_is_what_the_broker_checks():
    rig = Rig(principal='archeus.someone-else')
    g = rig.grant()
    conn = rig.get(g)
    assert status(conn) == 403 and rig.sent == []
    assert rig.principals[0].identity == 'process:4124:100'


def test_a_peer_execution_holding_a_stolen_token_is_refused():
    rig = Rig()
    a = rig.grant(principal='archeus.a')
    b = rig.grant(principal='archeus.b')
    assert status(rig.get(a)) == 403 and status(rig.get(b)) == 403    # both observed as PRINCIPAL
    assert rig.sent == []


def test_a_token_answers_only_at_the_listener_it_was_issued_at():
    rig = Rig()
    a, b = rig.grant(), rig.grant()                  # one principal, two executions
    conn = Conn(a.port, http(b.token))
    a.ep.handle(conn)
    assert status(conn) == 403 and rig.sent == []
    assert status(rig.get(b)) == 200


def test_a_token_unknown_or_malformed_is_refused():
    rig = Rig()
    g = rig.grant()
    assert status(rig.get(g, http('brk_nothing'))) == 401
    assert status(rig.get(g, http('hook_abc'))) == 401
    assert rig.sent == []


def test_a_connection_that_sends_nothing_is_ended_without_a_forward():
    rig = Rig()
    g = rig.grant()
    conn = rig.get(g, b'')
    assert rig.sent == [] and conn.closed


# ── each request ──

def test_the_peer_is_checked_again_when_its_request_arrives_and_released_after():
    rig = Rig()
    g = rig.grant()
    rig.get(g)
    assert rig.backend.kinds() == ['attest', 'valid', 'release']


def test_a_connection_that_sends_no_byte_is_not_re_checked():
    rig = Rig()
    g = rig.grant()
    rig.get(g, b'')
    assert rig.backend.kinds() == ['attest', 'release']


@pytest.mark.parametrize('answer', [False, None, 'yes', 1, RuntimeError('boom')])
def test_a_peer_that_is_no_longer_the_attested_process_is_refused(answer):
    rig = Rig(Backend(valid=answer))
    g = rig.grant()
    conn = rig.get(g)
    assert status(conn) == 403 and rig.sent == []
    assert rig.audit()[-1]['status'] == 403


def test_a_re_check_that_hangs_is_a_refusal(monkeypatch):
    monkeypatch.setattr(origin, 'BACKEND_DEADLINE_S', 0.05)
    release = threading.Event()
    backend = Backend()
    backend.valid = lambda ctx, ev: (release.wait(3), True)[1]
    rig = Rig(backend)
    g = rig.grant()
    conn = rig.get(g)
    release.set()
    assert status(conn) == 403 and rig.sent == []


def test_a_release_that_fails_does_not_unserve_the_response():
    backend = Backend()

    def broken(ctx, evidence):
        raise RuntimeError('gone')

    backend.release = broken
    rig = Rig(backend)
    g = rig.grant()
    assert status(rig.get(g)) == 200


def test_the_broker_still_rechecks_the_live_generation_on_every_request():
    live = [True]
    rig = Rig(live=lambda bd, d: live[0])
    g = rig.grant()
    assert status(rig.get(g)) == 200
    live[0] = False
    assert status(rig.get(g)) == 401 and len(rig.sent) == 1
    assert rig.broker.reach(g.bd.execution_id) is None and rig.socks[0].closed


def test_the_model_and_endpoint_stay_pinned_to_the_grant():
    rig = Rig()
    g = rig.grant()
    wrong = BODY.replace(b'claude-x', b'claude-y')
    assert status(rig.get(g, http(g.token, body=wrong))) == 403
    assert status(rig.get(g, http(g.token, target='/v1/other'))) == 404
    assert status(rig.get(g, http(g.token, method='HEAD', target='/api/hello', body=b''))) == 204
    assert rig.sent == []


def test_a_grant_stops_at_its_request_ceiling():
    rig = Rig()
    g = rig.grant(limits=B.BrokerLimits(max_requests=1))
    assert status(rig.get(g)) == 200
    assert status(rig.get(g)) == 429 and len(rig.sent) == 1


# ── the end of a grant ──

def test_revoking_the_execution_closes_its_listener_and_cuts_what_it_holds():
    rig = Rig()
    g = rig.grant()
    open_conn = Conn(g.port)
    g.ep._conns.add(open_conn)
    assert rig.broker.revoke(g.bd.execution_id) == 1
    assert rig.socks[0].closed and open_conn.shut and open_conn.closed


def test_a_revoked_listener_serves_nothing_even_a_connection_already_accepted():
    rig = Rig()
    g = rig.grant()
    rig.broker.revoke(g.bd.execution_id)
    conn = rig.get(g)
    assert conn.sent == b'' and conn.closed and rig.backend.calls == [] and rig.sent == []


def test_a_revoked_token_is_unknown_even_on_a_fresh_listener():
    rig = Rig()
    g = rig.grant()
    rig.broker.revoke(g.bd.execution_id)
    again = rig.grant(execution_id=g.bd.execution_id, process_seq=2)
    conn = Conn(again.port, http(g.token))
    again.ep.handle(conn)
    assert status(conn) == 401


@pytest.mark.parametrize('how', ['sweep', 'revoke_all', 'close'])
def test_every_sweep_closes_the_listeners_of_executions_that_ended(how):
    rig = Rig()
    a, b = rig.grant(), rig.grant()
    {'sweep': lambda: rig.broker.sweep({b.bd.execution_id}),
     'revoke_all': rig.broker.revoke_all, 'close': rig.broker.close}[how]()
    assert rig.socks[0].closed
    assert rig.socks[1].closed == (how != 'sweep')


def test_a_revoke_is_idempotent():
    rig = Rig()
    g = rig.grant()
    assert rig.broker.revoke(g.bd.execution_id) == 1 and rig.broker.revoke(g.bd.execution_id) == 0


def test_a_listener_accepts_and_serves_through_its_accept_loop():
    rig = Rig()
    g = rig.grant()
    conn = Conn(g.port, http(g.token))
    rig.socks[0].queue.append(conn)
    wait(lambda: conn.closed)
    assert status(conn) == 200
    rig.broker.revoke(g.bd.execution_id)


def test_the_connection_cap_closes_the_next_unread():
    rig = Rig()
    g = rig.grant()
    hold, asked = threading.Event(), []

    def attest(ctx):
        asked.append(ctx)
        hold.wait(3)
        return execution_evidence(ctx)

    rig.backend.attest = attest
    rig.socks[0].queue.extend(Conn(g.port) for _ in range(L.MAX_CONNECTIONS))
    wait(lambda: len(asked) == L.MAX_CONNECTIONS)
    extra = Conn(g.port, http(g.token))
    rig.socks[0].queue.append(extra)
    wait(lambda: extra.closed)
    assert len(asked) == L.MAX_CONNECTIONS and extra.opened == 0 and extra.sent == b''
    hold.set()
    rig.broker.revoke(g.bd.execution_id)


def test_a_served_connection_frees_its_slot():
    rig = Rig()
    g = rig.grant(limits=B.BrokerLimits(max_requests=100))
    conns = [Conn(g.port, http(g.token)) for _ in range(L.MAX_CONNECTIONS * 2)]
    for conn in conns:
        rig.socks[0].queue.append(conn)
        wait(lambda c=conn: c.closed)
    assert [status(c) for c in conns] == [200] * len(conns)
    rig.broker.revoke(g.bd.execution_id)


def test_an_accept_error_ends_the_loop_not_the_core():
    rig = Rig()
    g = rig.grant()
    rig.socks[0].closed = True
    time.sleep(0.05)
    rig.broker.revoke(g.bd.execution_id)


# ── the real chain over a fake process table ──

class Api:
    def __init__(self):
        self.rows, self.table = [], {}

    def tcp_rows(self):
        return list(self.rows)

    def core_session(self):
        return SESSION

    def process(self, pid, jobs):
        found = self.table.get(pid)
        if found is None:
            return None
        return found if JOB in jobs else replace(found, in_jobs=False)

    def add(self, pid, parent, ct, name, jobs=False, alive=True):
        self.table[pid] = RawProcess(alive, ct, parent, name, SESSION, jobs)

    def contained(self, pid=4124, ct=100):
        self.add(100, 0, 10, 'services.exe')
        self.add(200, 100, 20, 'wxc-exec.exe')
        self.add(pid, 200, ct, 'claude.exe', jobs=True)

    def user(self, pid=4124, ct=100):
        self.add(300, 0, 10, 'explorer.exe')
        self.add(pid, 300, ct, 'curl.exe')


def real_rig(api, **kw):
    """The shipped backend and readers over *api*; the principal is the process's own."""
    def backend_of(port):
        api.rows = [TcpRow('127.0.0.1', PEER, '127.0.0.1', port, ESTABLISHED, 4124)]
        return WindowsOriginBackend(readers=native_readers(
            api, core_port=port, jobs=lambda: [JOB], clock=lambda: T0))

    rig = Rig(**kw)
    rig.broker.transport._backend_of = backend_of
    rig.broker.transport._principal_of = lambda evidence: (
        PRINCIPAL if evidence.identity == 'process:4124:100' else None)
    return rig


def test_a_contained_process_is_served_through_the_shipped_backend():
    api = Api()
    api.contained()
    rig = real_rig(api)
    g = rig.grant()
    assert status(rig.get(g)) == 200


def test_the_users_own_process_is_refused_through_the_shipped_backend():
    api = Api()
    api.user()
    rig = real_rig(api)
    g = rig.grant()
    conn = rig.get(g)
    assert conn.sent == b'' and rig.audit()[-1]['endpoint'] == 'accept:origin_user'


@pytest.mark.parametrize('fault', ['dead', 'gone', 'no_row', 'no_launcher'])
def test_a_peer_the_table_cannot_prove_is_refused_through_the_shipped_backend(fault):
    api = Api()
    api.contained()
    rig = real_rig(api)
    g = rig.grant()
    if fault == 'dead':
        api.add(4124, 200, 100, 'claude.exe', jobs=True, alive=False)
    elif fault == 'gone':
        del api.table[4124]
    elif fault == 'no_row':
        api.rows = []
    else:
        api.add(200, 100, 20, 'cmd.exe')
    conn = Conn(g.port, http(g.token))
    if fault == 'no_row':
        api.rows = []
    g.ep.handle(conn)
    assert conn.sent == b'' and rig.sent == []


def test_a_pid_recycled_between_accept_and_request_is_refused():
    api = Api()
    api.contained()
    rig = real_rig(api)
    g = rig.grant()
    conn = Conn(g.port, http(g.token), on_open=lambda: api.contained(ct=999))
    g.ep.handle(conn)
    assert status(conn) == 403 and rig.sent == []


def test_a_peer_that_left_the_job_between_accept_and_request_is_refused():
    api = Api()
    api.contained()
    rig = real_rig(api)
    g = rig.grant()
    conn = Conn(g.port, http(g.token), on_open=lambda: api.user())
    g.ep.handle(conn)
    assert status(conn) == 403 and rig.sent == []


def test_the_core_api_path_registry_never_approves_a_broker_execution_origin():
    registry = origin.CorePathRegistry([40000])
    ctx = origin.ConnectionContext(object(), ('127.0.0.1', 40000), ('127.0.0.1', PEER), 'g')
    assert registry.approved(ctx, execution_evidence(ctx)) is False


# ── real sockets, loopback, inside this process ──

def test_a_real_loopback_socket_is_attested_served_and_closed_on_revoke():
    import socket
    rig = Rig(bind=L.bind_loopback)
    g = rig.grant()
    assert g.ep.sock.getsockname()[0] == '127.0.0.1'
    with socket.create_connection(('127.0.0.1', g.port), timeout=3) as client:
        client.sendall(http(g.token))
        data = b''
        while chunk := client.recv(65536):
            data += chunk
    assert data.split(b' ', 2)[1] == b'200' and len(rig.sent) == 1
    ctx = rig.backend.calls[0][1]
    assert ctx.local_endpoint == ('127.0.0.1', g.port) and ctx.remote_endpoint[0] == '127.0.0.1'
    rig.broker.revoke(g.bd.execution_id)
    time.sleep(L.POLL_S * 2)
    with pytest.raises(OSError):
        socket.create_connection(('127.0.0.1', g.port), timeout=1)


def test_a_real_loopback_socket_is_cut_when_its_grant_is_revoked_mid_request():
    import socket
    rig = Rig(bind=L.bind_loopback)
    g = rig.grant()
    client = socket.create_connection(('127.0.0.1', g.port), timeout=3)
    wait(lambda: len(rig.backend.calls) >= 1)
    rig.broker.revoke(g.bd.execution_id)
    client.settimeout(3)
    assert client.recv(10) == b''
    client.close()


# ── the policy proxy ──

def test_the_listener_is_a_proxy_the_mxc_compiler_accepts(tmp_path):
    rig = Rig()
    g = rig.grant()
    work = tmp_path / 'w'
    work.mkdir()
    url = 'http://%s:%d' % (L.HOST, rig.broker.reach(g.bd.execution_id))
    policy = mxc.compile_policy(workspace=str(work), cwd=str(work), command_line='a.exe',
                                env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'C:\\h'},
                                timeout_ms=1000, proxy_url=url)
    assert policy.raw['runtimeConfig'] == {'networkProxy': url}


def test_the_boundary_proxy_is_its_own_executions_listener(tmp_path, sdk, gate, monkeypatch):  # noqa: F811
    rig = Rig()
    Made.made = []
    monkeypatch.setattr(local, 'MxcLaunch', Made)
    h = make(tmp_path, sdk, broker=rig.broker)
    req = boundary_request(tmp_path)
    identity = h.boundary.create_profile(req.execution_id)
    h.boundary.grant_established(req.workspace, identity['sid'], 'rw')
    g = rig.grant(execution_id=req.execution_id)
    h.boundary.launch(['a.exe'], cwd=req.workspace, env={}, profile=identity['profile'],
                      job=None, stdin=None, stdout=None)
    assert Made.made[-1].kw['proxy_url'] == 'http://127.0.0.1:%d' % g.port
    assert Made.made[-1].kw['broker'] is rig.broker


def test_without_a_grant_the_boundary_names_no_proxy(tmp_path, sdk, gate, monkeypatch):  # noqa: F811
    rig = Rig()
    Made.made = []
    monkeypatch.setattr(local, 'MxcLaunch', Made)
    h = make(tmp_path, sdk, broker=rig.broker)
    req = boundary_request(tmp_path)
    identity = h.boundary.create_profile(req.execution_id)
    h.boundary.grant_established(req.workspace, identity['sid'], 'rw')
    rig.grant()                                           # another execution's grant
    h.boundary.launch(['a.exe'], cwd=req.workspace, env={}, profile=identity['profile'],
                      job=None, stdin=None, stdout=None)
    assert Made.made[-1].kw['proxy_url'] is None
