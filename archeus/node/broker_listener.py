"""PV-20 B10: the provider broker's MXC transport. One loopback listener per grant, named as
the execution's MXC network proxy (ADR-0053; the only reach N3 evidenced), in place of the
named pipe and the execution-local bridge.

Core binds the listener when the grant is issued and closes it when the grant ends, so
revocation (every end path, the cancel order's first step) takes the endpoint away. Each
accepted connection is attested at accept by the injected origin backend, before a byte is
read: only an EXECUTION origin on the direct loopback path whose process maps to a principal
is served, and what the backend observed is that principal. An undetermined, user, verifier
or unmapped peer is closed unread. The request's own liveness is checked again when its
first bytes arrive. The broker then decides as it always does (token, principal, live
generation, route, account, model, limits); a grant answers only at its own listener.

Native facts - the socket owner, the process read, the Job table - are the backend's and
`principal_of`'s, injected: importing this binds nothing. No composition root builds one,
and the broker stays behind `BROKER_DISPATCH_ENABLED` and the origin switch: never alone.
"""

import ipaddress
import secrets
import socket
import threading

from ..api import origin
from ..api.origin import ConnectionContext, OriginClass
from . import broker as B
from . import broker_bridge as wire

HOST = '127.0.0.1'
#: connections one grant's listener holds at once; the next is closed unread
MAX_CONNECTIONS = 8
#: how often the accept loop looks at whether its listener was closed
POLL_S = 0.2


def bind_loopback():
    sock = socket.socket()
    try:
        sock.bind((HOST, 0))
        sock.listen(MAX_CONNECTIONS)
        sock.settimeout(POLL_S)
    except BaseException:
        sock.close()
        raise
    return sock


def _close(sock):
    for op in (lambda: sock.shutdown(socket.SHUT_RDWR), sock.close):
        try:
            op()
        except OSError:
            pass


class _Gate:
    """*f*, running *check* once the first bytes of the request have arrived."""

    def __init__(self, f, check):
        self._f, self._check = f, check

    def _read(self, data):
        if data and self._check is not None:
            check, self._check = self._check, None
            check()
        return data

    def readline(self, n):
        return self._read(self._f.readline(n))

    def read(self, n):
        return self._read(self._f.read(n))


class _Listener:
    def __init__(self, sock, port, backend, principal_of, transport):
        self.sock, self.port, self.backend = sock, port, backend
        self._principal_of, self._transport = principal_of, transport
        self.binding = None
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self._lock = threading.Lock()
        self._conns, self._closed = set(), False

    def start(self, binding):
        self.binding = binding
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self._closed:
            try:
                conn, _ = self.sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            if not self._slots.acquire(blocking=False):
                _close(conn)
                continue
            threading.Thread(target=self._one, args=(conn,), daemon=True).start()

    def _one(self, conn):
        try:
            self.handle(conn)
        finally:
            self._slots.release()

    def handle(self, conn):
        with self._lock:
            if self._closed:
                _close(conn)
                return
            self._conns.add(conn)
        ctx = evidence = None
        try:
            conn.settimeout(wire.IDLE_S)
            ctx = ConnectionContext(
                socket=conn, local_endpoint=tuple(conn.getsockname()[:2]),
                remote_endpoint=tuple(conn.getpeername()[:2]),
                accept_generation=secrets.token_hex(16))
            evidence = origin.bounded(self.backend.attest, ctx)
            principal, why = self._admit(ctx, evidence)
            if why is not None:
                self._refused(why)
                return
            self._transport.broker.serve(
                _Gate(conn.makefile('rb'), lambda: self._still(ctx, evidence)),
                conn.sendall, principal, self)
        except Exception:
            self._refused('error')
        finally:
            if evidence is not None:
                try:
                    origin.bounded(self.backend.release, ctx, evidence)
                except Exception:
                    pass
            with self._lock:
                self._conns.discard(conn)
            _close(conn)

    def _admit(self, ctx, evidence):
        if not origin.validate_evidence(ctx, evidence):
            return None, 'invalid_evidence'
        if evidence.origin is not OriginClass.EXECUTION:
            return None, 'origin_' + evidence.origin.value
        if not origin.direct_loopback(ctx) or ctx.local_endpoint[1] != self.port:
            return None, 'not_this_listener'
        principal = origin.bounded(self._principal_of, evidence)
        if not (isinstance(principal, str) and principal):
            return None, 'no_principal'
        return principal, None

    def _still(self, ctx, evidence):
        try:
            ok = origin.bounded(self.backend.valid, ctx, evidence) is True
        except Exception:
            ok = False
        if not ok:
            raise B.Refused(403, 'the peer is no longer the process attested at accept')

    def _refused(self, why):
        self._transport.broker.audit.append({
            'execution_id': self.binding.execution_id, 'model': self.binding.model,
            'endpoint': 'accept:' + why, 'status': 403, 'bytes_in': 0, 'bytes_out': 0,
            'duration_ms': 0})

    def close(self):
        with self._lock:
            self._closed = True
            conns = list(self._conns)
        for sock in [self.sock] + conns:
            _close(sock)


class LoopbackTransport:
    """The `Broker` transport for MXC: `create` binds a loopback listener (refusing any
    other address), `launch_bridge` starts serving it and answers its port, `close` ends
    it and cuts what it holds. *backend_of(port)* is the origin backend for connections to
    that port (its readers name the listener's port as Core's); *principal_of(evidence)*
    is the principal an attested execution process runs as, or None."""

    def __init__(self, *, backend_of, principal_of, bind=bind_loopback):
        self._backend_of, self._principal_of, self._bind = backend_of, principal_of, bind
        self.broker = None

    def create(self, name, principal):
        sock = self._bind()
        try:
            host, port = sock.getsockname()[:2]
            if not ipaddress.ip_address(host).is_loopback:
                raise B.BrokerUnavailable('the broker listener is not on a loopback address')
            return _Listener(sock, port, self._backend_of(port), self._principal_of, self)
        except BaseException:
            sock.close()
            raise

    def launch_bridge(self, endpoint, binding):
        if self.broker is None:
            raise B.BrokerUnavailable('the listener has no broker to serve')
        endpoint.start(binding)
        return endpoint.port

    def close(self, endpoint):
        endpoint.close()


def loopback_broker(*, backend_of, principal_of, bind=bind_loopback, **kw):
    """A `Broker` whose grants are served at attested loopback listeners."""
    transport = LoopbackTransport(backend_of=backend_of, principal_of=principal_of, bind=bind)
    transport.broker = B.Broker(transport=transport, **kw)
    return transport.broker
