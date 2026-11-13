"""T-1247: the highest-risk stop-path gaps in the broker's MXC transport.

Source slice under test: `archeus/node/broker_listener.py` lines **196-262 inclusive** at tip
`6bbd3b44` — `_Listener.close` (196-201) and `LoopbackTransport.__init__ / create / _drop /
cancel / launch_bridge / close` (211-262). Everything outside that slice (the imports, the
module constants, `_close`, `_Raw`, `_Gate`, the accept loop and `handle`'s arrival path) is
read-only context: it is called, never asserted as owned, and never edited.

Selected branches (ranked in /work/QWEN-DONE-T-1247.md, denial/fail-closed first, then
boundaries, then error paths):

  1. :224  `if cancelled:` — a `create` whose bind returns only after the stop has run.
  2. :233  the second cancellation guard, after the socket is already registered.
  3. :249  cancel's snapshot-and-clear, which runs before any socket is closed.
  4. :200  `_Listener.close` cuts the listening socket and every held conn.
  5. :236  `except BaseException:` — a non-Exception failure after registration.
  6. :229  the non-loopback refusal, taken after the socket was registered.
  7. :250  cancel's close loop walking past a socket that raises on both end operations.
  8. :259  `close(endpoint)` discarding that endpoint's own socket before closing it.
  9. :254  `launch_bridge` refusing a listener with no broker, before it is started.
 10. :198  the closed flag set under the lock and kept across repeated closes.

Fakes only: the listening sockets, the accepted connections, `bind`, `backend_of`, the origin
backend and every broker hook are in memory. Nothing binds, accepts, reads a process table,
loads a DLL, opens a native handle, spawns a thread it does not join, touches the network, a
real home directory or the environment. No sleeps; the two racing tests hand over with explicit
`threading.Event`s and join their worker with a bound.
"""

import threading

import pytest

from archeus.node import broker as B
from archeus.node import broker_listener as L

PRINCIPAL = 'archeus.x'
PEER = ('127.0.0.1', 54321)
PORTS = iter(range(46100, 46500))


class Log(list):
    """Every `shutdown`/`close` the transport provoked, in the order it provoked them."""

    def ops(self, sock):
        return [op for (who, op) in self if who is sock]

    @property
    def order(self):
        return [who for (who, op) in self]


class Sock:
    """A bound listening socket whose end operations are only counted, logged and (when the
    test asks) made to raise OSError, so a test can watch `_close` walk past a failure."""

    def __init__(self, log, name, host='127.0.0.1', port=None,
                 fail_shutdown=False, fail_close=False, on_shutdown=None):
        self.log, self.name = log, name
        self.host = host
        self.port = next(PORTS) if port is None else port
        self.fail_shutdown, self.fail_close = fail_shutdown, fail_close
        self.on_shutdown = on_shutdown
        self.shuts = self.closes = 0
        self.closed = False

    def getsockname(self):
        return (self.host, self.port)

    def shutdown(self, how):
        self.shuts += 1
        self.log.append((self, 'shutdown'))
        if self.on_shutdown is not None:
            self.on_shutdown(how)
        if self.fail_shutdown:
            raise OSError('not connected')

    def close(self):
        self.closes += 1
        self.log.append((self, 'close'))
        if self.fail_close:
            raise OSError('bad descriptor')
        self.closed = True


class Conn(Sock):
    """An accepted connection: the same counted end operations, plus a record of every
    read-side call, so a test can prove a stopped listener never asks it for a byte."""

    def __init__(self, log, port, name, peer=PEER, **end_ops):
        Sock.__init__(self, log, name, host='127.0.0.1', port=port, **end_ops)
        self.local, self.remote, self.calls = ('127.0.0.1', port), peer, []

    def getsockname(self):
        self.calls.append('getsockname')
        return self.local

    def getpeername(self):
        self.calls.append('getpeername')
        return self.remote

    def settimeout(self, seconds):
        self.calls.append('settimeout')

    def makefile(self, mode, buffering=-1):
        self.calls.append('makefile')
        raise AssertionError('a stopped listener must not read its peer')

    def sendall(self, data):
        self.calls.append('sendall')


class Backend:
    """The injected origin backend: it is only ever asked, never believed."""

    def __init__(self, port):
        self.port, self.calls = port, []

    def attest(self, ctx):
        self.calls.append('attest')
        return object()

    def valid(self, ctx, evidence):
        self.calls.append('valid')
        return True

    def release(self, ctx, evidence):
        self.calls.append('release')


class Seam:
    """A `LoopbackTransport` with every outside call supplied: `bind`, `backend_of`, the
    principal lookup and the broker's own hooks. No listener is ever started."""

    def __init__(self, broker=True):
        self.log, self.socks, self.pending = Log(), [], []
        self.asked, self.backends = [], []
        self.on_bind, self.on_backend = None, None
        self.backend_error = None
        self.transport = L.LoopbackTransport(
            backend_of=self._backend_of, principal_of=lambda evidence: PRINCIPAL,
            bind=self._bind,
            broker_options=dict(core_instance='core1', live=lambda bd, d: True,
                                credentials=lambda bd: {},
                                upstream_of=lambda a: B.Upstream('https://api.example.com'),
                                resolve=lambda host, port: ['93.184.216.34']) if broker else None)

    def queue(self, *socks):
        self.pending.extend(socks)
        return self

    def _bind(self):
        sock = self.pending.pop(0) if self.pending else Sock(self.log, 'listen')
        self.socks.append(sock)
        if self.on_bind is not None:
            self.on_bind(sock)
        return sock

    def _backend_of(self, port):
        self.asked.append(port)
        if self.on_backend is not None:
            self.on_backend(port)
        if self.backend_error is not None:
            raise self.backend_error
        self.backends.append(Backend(port))
        return self.backends[-1]

    def create(self, name='grant'):
        return self.transport.create(name, PRINCIPAL)


class Worker:
    """One call, in a thread the test always releases, bounds and joins."""

    def __init__(self, fn):
        self.entered, self.release = threading.Event(), threading.Event()
        self.errors, self.result = [], None
        self._fn = fn
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            self.result = self._fn()
        except BaseException as err:                    # the test reads what the call raised
            self.errors.append(err)

    def start(self):
        self.thread.start()
        return self

    def finish(self):
        self.release.set()
        self.thread.join(5)
        assert not self.thread.is_alive(), 'the worker never came back'


# ── denial first: a stop that runs while a grant is being made ──

def test_a_cancel_during_a_paused_bind_closes_the_socket_that_lands_after_it():
    # :224 `if cancelled:` — bind had not returned when the stop ran, so the socket arrives
    # late, unregistered. Caught if it goes: the late socket is kept open and handed back.
    seam = Seam()
    w = Worker(lambda: seam.transport.create('grant', PRINCIPAL))

    def pause(sock):
        w.entered.set()
        assert w.release.wait(5), 'the stop never released the paused bind'

    seam.on_bind = pause
    w.start()
    try:
        assert w.entered.wait(5), 'create never reached bind'
        seam.transport.cancel()                      # the stop runs while bind is still open
        assert seam.transport._socks == set()
    finally:
        w.finish()

    assert [type(e).__name__ for e in w.errors] == ['BrokerClosed'] and w.result is None
    sock = seam.socks[0]
    assert (sock.shuts, sock.closes, sock.closed) == (1, 1, True)   # closed once by `create`
    assert seam.transport._socks == set() and seam.transport._cancelled is True
    assert seam.asked == []                                          # no backend was ever built
    assert seam.transport.broker._grants == {} and seam.transport.broker._pending == {}


def test_a_cancel_while_the_backend_factory_runs_refuses_the_finished_create_and_drops_it():
    # :233 the second cancellation guard, reached after the socket was registered at :223.
    # Caught if it goes: a transport already cancelled hands back a live listener.
    seam = Seam()
    w = Worker(lambda: seam.transport.create('grant', PRINCIPAL))

    def pause(port):
        w.entered.set()
        assert w.release.wait(5), 'the stop never released the paused backend factory'

    seam.on_backend = pause
    w.start()
    try:
        assert w.entered.wait(5), 'create never reached backend_of'
        sock = seam.socks[0]
        assert sock in seam.transport._socks                    # registered before being asked
        seam.transport.cancel()
        assert seam.transport._socks == set() and (sock.shuts, sock.closes) == (1, 1)
    finally:
        w.finish()

    assert [type(e).__name__ for e in w.errors] == ['BrokerClosed'] and w.result is None
    sock = seam.socks[0]
    assert (sock.shuts, sock.closes) == (2, 2)        # `_drop` cut it again on the way out
    assert seam.transport._socks == set() and seam.asked == [sock.port]


def test_a_keyboard_interrupt_from_the_backend_factory_still_drops_the_socket():
    # :236 `except BaseException:` — a failure that is not an Exception, after registration.
    # Caught if it narrows to `except Exception`: the bound socket stays open and stays listed.
    seam = Seam()
    seam.backend_error = KeyboardInterrupt('stopped')
    with pytest.raises(KeyboardInterrupt):
        seam.create()
    sock = seam.socks[0]
    assert (sock.shuts, sock.closes, sock.closed) == (1, 1, True)
    assert seam.transport._socks == set() and seam.transport._cancelled is False


def test_a_nonloopback_bind_is_refused_before_the_backend_is_asked_and_its_socket_dropped():
    # :229 the loopback refusal, taken after the socket was already registered at :223 and on
    # a socket whose shutdown raises. Caught if it goes: an off-loopback listener is built,
    # given an attestation backend and returned.
    seam = Seam()
    seam.queue(Sock(seam.log, 'public', host='192.168.1.5', fail_shutdown=True))
    with pytest.raises(B.BrokerUnavailable):
        seam.create()
    sock = seam.socks[0]
    assert seam.asked == []                                   # no backend, nothing to attest
    assert (sock.shuts, sock.closes, sock.closed) == (1, 1, True)
    assert seam.transport._socks == set() and seam.transport._cancelled is False


# ── boundaries: what a stop owns, and in what order ──

def test_cancel_empties_the_socket_set_before_it_closes_anything():
    # :249 `socks, self._socks = list(self._socks), set()` runs before the close loop, so a
    # cancel re-entered from inside a socket's own shutdown is a no-op. Caught if the close
    # loop moves under `_lock` (self-deadlock on a plain Lock) or the set is cleared only
    # afterwards (the re-entered cancel closes everything a second time).
    seam = Seam()
    a, b = seam.create('a'), seam.create('b')
    seen = []

    def reentrant(how):
        seen.append(len(seam.transport._socks))
        seam.transport.cancel()

    a.sock.on_shutdown = reentrant
    Worker(seam.transport.cancel).start().finish()            # bounded: a deadlock fails here
    assert seen == [0]                                        # already cleared when it was asked
    assert (a.sock.shuts, a.sock.closes) == (1, 1)            # once, by the first cancel only
    assert (b.sock.shuts, b.sock.closes) == (1, 1)
    assert seam.transport._socks == set() and seam.transport._cancelled is True


def test_cancel_keeps_cutting_the_other_sockets_when_one_raises_on_shutdown_and_close():
    # :250 the close loop, with a socket that fails both end operations. Caught if the OSError
    # guard is dropped: the loop aborts on the failing socket and the rest stay open.
    seam = Seam()
    good = [seam.create('g%d' % n) for n in range(2)]
    bad = seam.create('bad')
    for ep in good + [bad]:
        ep.sock.fail_shutdown = True                          # raises whatever its place in line
    bad.sock.fail_close = True
    seam.transport.cancel()
    assert [(ep.sock.shuts, ep.sock.closes) for ep in good] == [(1, 1), (1, 1)]
    assert all(ep.sock.closed for ep in good)
    assert (bad.sock.shuts, bad.sock.closes, bad.sock.closed) == (1, 1, False)
    assert seam.transport._socks == set() and seam.transport._cancelled is True


def test_transport_close_discards_the_endpoints_own_socket_before_it_closes_it():
    # :259-262 `close(endpoint)`: the discard happens under the lock, before `endpoint.close`.
    # Caught if the discard moves after the callback, or takes the whole set: the observed
    # state inside the callback, and the other grant's socket, both say which.
    seam = Seam()
    a, b = seam.create('a'), seam.create('b')
    seen = []
    real = a.close

    def observed():
        seen.append((set(seam.transport._socks), a._closed))
        real()

    a.close = observed
    seam.transport.close(a)
    assert seen[0][0] == {b.sock}                    # its own socket already gone, other kept
    assert seen[0][1] is False                       # the endpoint is still open at that moment
    assert seam.transport._socks == {b.sock}
    assert a._closed is True and (a.sock.shuts, a.sock.closes) == (1, 1)
    assert (b.sock.shuts, b.sock.closes, b.sock.closed) == (0, 0, False)


def test_launch_bridge_without_a_broker_refuses_before_the_listener_is_started():
    # :254 the no-broker guard. Caught if `endpoint.start(binding)` is hoisted above it: the
    # listener would be started and take a binding it has no broker to serve.
    seam = Seam(broker=False)
    endpoint = seam.create('grant')
    started = []
    endpoint.start = lambda binding: started.append(binding)
    with pytest.raises(B.BrokerUnavailable):
        seam.transport.launch_bridge(endpoint, object())
    assert started == [] and endpoint.binding is None


# ── error paths: an end that fails must still end everything ──

def test_closing_a_listener_cuts_the_listening_socket_and_every_conn_even_one_that_raises():
    # :200 `for sock in [self.sock] + conns:` — the listening socket goes first, and every
    # socket gets both end operations tried, whatever one of them raises. Caught if `close`
    # stops at the listening socket, at the first failure, or serves a conn that arrives after.
    seam = Seam()
    endpoint = seam.create('grant')
    listening = seam.socks[0]
    noisy = Conn(seam.log, endpoint.port, 'noisy', fail_shutdown=True)
    quiet = Conn(seam.log, endpoint.port, 'quiet')
    endpoint._conns.update((noisy, quiet))
    endpoint.close()
    order = seam.log.order
    assert order[:2] == [listening, listening]       # shutdown, then close, before any conn
    assert set(order[2:]) == {noisy, quiet}
    for sock in (listening, noisy, quiet):
        assert seam.log.ops(sock) == ['shutdown', 'close']
    assert (noisy.shuts, noisy.closes) == (1, 1)     # the one that raised was still closed
    assert (quiet.shuts, quiet.closes, quiet.closed) == (1, 1, True)
    late = Conn(seam.log, endpoint.port, 'late')
    endpoint.handle(late)
    assert (late.shuts, late.closes, late.closed) == (1, 1, True)
    assert late.calls == [] and seam.backends[0].calls == []      # never named, never read


def test_a_listener_closed_twice_stays_closed_and_cuts_what_was_registered_in_between():
    # :198 `self._closed = True` under the lock, re-read at every close. Caught if the flag is
    # cleared or not set: a second close would reopen the listener, and a conn registered
    # between the two closes would survive. A repeated close may repeat its end operations;
    # the contract is that everything ends closed and no peer is read.
    seam = Seam()
    endpoint = seam.create('grant')
    listening = seam.socks[0]
    first = Conn(seam.log, endpoint.port, 'first')
    endpoint._conns.add(first)
    endpoint.close()
    assert endpoint._closed is True and first.closed
    late = Conn(seam.log, endpoint.port, 'late')      # registered before the second close
    endpoint._conns.add(late)
    endpoint.close()
    assert endpoint._closed is True                   # never re-opened by a second close
    assert listening.closed and first.closed and late.closed
    assert late.calls == [] and first.calls == []     # the late peer was cut, never read
    after = Conn(seam.log, endpoint.port, 'after')
    endpoint.handle(after)
    assert after.closed and after.calls == [] and seam.backends[0].calls == []
