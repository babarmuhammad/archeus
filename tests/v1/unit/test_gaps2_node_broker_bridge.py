"""T-1007: the ten highest-risk uncovered branches of archeus/node/broker_bridge.py,
lines 1-319 inclusive (the whole execution-side bridge module as scheduled).

The ten branches, ranked by risk, fail-closed and denial first, then boundaries, then
error paths. Evidence, closest existing test and the scheduled probe each one replaced
are in the T-1007 report:

 1. broker_bridge.py:135-136   the TAB half of the obsolete line-fold refusal
 2. broker_bridge.py:123-124   the method allowlist is case-sensitive, past the single
                               uppercase CONNECT the suite already sends
 3. broker_bridge.py:158-161   PUT/PATCH must declare a body; GET/HEAD/DELETE/OPTIONS
                               must not be forced to
 4. broker_bridge.py:277-282   the bridge's own CONCURRENT slots are all busy before a
                               503, and every one of them comes back
 5. broker_bridge.py:167-170,308  bytes that follow the declared body are never read and
                               never reach the pipe (no pipelined second request)
 6. broker_bridge.py:216-217   the drain ends at the refused client's EOF, and each read
                               is bounded by min(left, 8192)
 7. broker_bridge.py:208-213   the drain clock is one TOTAL budget, stopped at equality
 8. broker_bridge.py:195-199 (and 270-274)  a cut/shutdown on a socket that is already
                               gone is silent
 9. broker_bridge.py:283-319   every refusal kind (400, 401, 413, 502) returns the slot
                               it took
10. broker_bridge.py:260-263   closing a started bridge twice is silent and frees the
                               listening socket

Style and fakes follow test_broker_bridge.py and test_gaps_node_broker_bridge.py, but
this file is self-contained: it imports no other test file and depends on no queue
order. The pipe to Core is always a fake object; the drain, cut, busy and slot tests run
against a fake socket with a fake clock, so no real timer, process, DLL or network
beyond the same loopback listener those files already use is involved. Nothing is
written to disk, no OS error text, live thread set or environment value is asserted on,
and no test waits on a wall-clock bound.
"""

import io
import socket
import threading
import time

import pytest

from archeus.node import broker_bridge as W

BODY = b'{"model":"claude-x","messages":[]}'
OK_REPLY = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok'

# What a refusal looks like on the wire, written out rather than asked for with the
# source's own local_reply: a check that calls the code under test to build its expected
# value cannot notice that code changing what it answers. A BadRequest is answered with
# the parser's status and the reason 'Refused' (289-291), a busy bridge with 503 'Busy'
# (280) and a dead pipe with 502 'Bad Gateway' (305).
REFUSED_400 = (b'HTTP/1.1 400 Refused\r\nContent-Length: 0\r\n'
               b'Connection: close\r\n\r\n')
BUSY_503 = (b'HTTP/1.1 503 Busy\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
BAD_GATEWAY_502 = (b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n'
                   b'Connection: close\r\n\r\n')


def raw(*lines, body=b''):
    return ('\r\n'.join(lines) + '\r\n\r\n').encode('latin-1') + body


def ok_request(body=BODY, extra=(), method='POST', target='/v1/messages?beta=true'):
    return raw('%s %s HTTP/1.1' % (method, target), 'Host: 127.0.0.1:9',
               'Authorization: Bearer brk_x', 'Content-Length: %d' % len(body), *extra,
               body=body)


def head_only(*lines):
    """A head with its blank terminator and nothing after it: what the bridge holds
    before a single body byte has arrived."""
    return ('\r\n'.join(lines) + '\r\n\r\n').encode('latin-1')


class Pipe:
    """A fake connection to Core's pipe: records what was sent, answers *reply*."""

    def __init__(self, reply=OK_REPLY):
        self.sent, self.reply, self.closed = b'', [reply], False

    def sendall(self, data):
        self.sent += data

    def recv(self, n):
        return self.reply.pop(0) if self.reply else b''

    def close(self):
        self.closed = True


def _nope():
    raise OSError('no pipe')


class FakeSock:
    """A client connection that never reaches the OS: the bytes the bridge may read are
    handed over, and every operation the bridge performs on the client is recorded in
    one ordered list, so a test can assert the order and not only the fact."""

    def __init__(self, data=b'', chunks=(), rest=b'', shutdown_raises=None,
                 send_raises=None):
        self.source = io.BytesIO(data)
        self.chunks, self.rest = list(chunks), rest
        self.shutdown_raises, self.send_raises = shutdown_raises, send_raises
        self.events = []                       # ('send'|'timeout'|'shutdown'|'recv', arg)
        self.delivered = 0

    @property
    def sent(self):
        return [d for kind, d in self.events if kind == 'send']

    @property
    def recvs(self):
        return [n for kind, n in self.events if kind == 'recv']

    @property
    def shutdowns(self):
        return [h for kind, h in self.events if kind == 'shutdown']

    @property
    def timeouts(self):
        return [t for kind, t in self.events if kind == 'timeout']

    def makefile(self, mode):
        assert mode == 'rb'
        return self.source

    def settimeout(self, value):
        self.events.append(('timeout', value))

    def sendall(self, data):
        if self.send_raises is not None:
            raise self.send_raises
        self.events.append(('send', data))

    def shutdown(self, how):
        self.events.append(('shutdown', how))
        if self.shutdown_raises is not None:
            raise self.shutdown_raises

    def recv(self, maxbytes):
        self.events.append(('recv', maxbytes))
        chunk = self.chunks.pop(0) if self.chunks else self.rest
        self.delivered += len(chunk)
        return chunk


class Clock:
    """Stands in for the module's time.monotonic: every read hands out the next value,
    so how far a drain loop gets is decided by the test, not by the wall clock."""

    def __init__(self, start=0.0, step=0.0):
        self.now, self.step, self.reads = start, step, 0

    def monotonic(self):
        self.reads += 1
        value = self.now
        self.now += self.step
        return value


class Timers:
    """Stands in for threading.Timer: the test fires a request's deadline when it says
    so, so nothing here waits on or races a real timer."""

    def __init__(self):
        self.made = []

    def __call__(self, delay, fn, args):
        self.made.append(_Timer(delay, fn, args))
        return self.made[-1]

    def fire_all(self):
        for t in self.made:
            t.fire()


class _Timer:
    def __init__(self, delay, fn, args):
        self.delay, self.fn, self.args, self.cancelled = delay, fn, args, False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.fn(*self.args)


def _read_to_eof(c):
    out = b''
    while True:
        try:
            chunk = c.recv(65536)
        except ConnectionError:           # bytes the bridge left unread are a reset or an
            return out                    # abort on Windows and a FIN elsewhere: all end it
        if not chunk:
            return out
        out += chunk


def _answer(bridge, data, half_close=True):
    """Send *data* to the bridge and read the answer. The client stops writing first: a
    refused client that has nothing more to say is the case the drain must handle, and
    it keeps every test here off the wall clock."""
    with socket.create_connection(('127.0.0.1', bridge.port), timeout=5) as c:
        c.sendall(data)
        if half_close:
            c.shutdown(socket.SHUT_WR)
        return _read_to_eof(c)


def _wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.01)
    return cond()


def _slot_back(bridge, width):
    """Wait until the request that just finished has handed its slot back, and say so if
    it never does. The drain stops SENDING before it stops reading, so a client can see a
    refusal while the handler that owed it is still running; a test that fired the next
    request at that moment would be racing the semaphore the test exists to check, and
    would be answered 503 for the wrong reason. On correct code this waits nothing at all.
    """
    assert _wait_for(lambda: bridge._slots._value == width), \
        'a request never gave its slot back'


# ── 1. broker_bridge.py:135-136: the TAB half of the obsolete line-fold refusal ──
#
# Branch: `if raw[:1] in (b' ', b'\t'): raise BadRequest('folded header lines are
# refused')`. Closest existing test: test_broker_bridge.py:50 sends ('X-A: 1',
# ' folded') and nothing else ever folds, so the TAB member is never read. It matters
# that this line is refused AS A FOLD and not merely refused: the name check at 142
# would also reject a tab-led line, but as 'a malformed header line', which is the wrong
# answer for a gateway - an obsolete fold is a request smuggling attempt, and the reason
# the bridge and Core give is what an operator reads. Read as a continuation instead,
# the line welds itself onto the previous header value and rides the pipe to Core, where
# Core's parser has to guess again. The accepted side of the same strip is pinned next
# to it: a tab that is not at the line start belongs to the value, only the edges go.

def test_a_tab_folded_header_line_is_refused_where_a_space_fold_already_is():
    smuggled = ok_request(extra=('X-Note: 1', '\tX-Admin: yes'))
    with pytest.raises(W.BadRequest, match='folded'):       # refused as a fold, by name
        W.read_request(io.BytesIO(smuggled))
    with pytest.raises(W.BadRequest, match='folded'):        # the half the suite has
        W.read_request(io.BytesIO(ok_request(extra=('X-Note: 1', ' X-Admin: yes'))))
    calls = []
    b = W.Bridge(lambda: calls.append(1) or Pipe())
    try:
        b.start(lambda port: None)
        width = b._slots._value
        assert _answer(b, smuggled) == REFUSED_400 and calls == []
        _slot_back(b, width)
        # the tab in the middle of a value is not a fold, and the bridge relays it as
        # the one stripped value it read: a wrong strip would change what Core is told
        assert _answer(b, ok_request(extra=('accept: \tapplication/json\t ',))) \
            .endswith(b'\r\n\r\nok')
        _slot_back(b, width)
    finally:
        b.close()
    assert W.read_request(io.BytesIO(ok_request(extra=('accept: \ttext/x \t',)))) \
        .header('accept') == 'text/x'


# ── 2. broker_bridge.py:123-124: the method allowlist is case-sensitive ──
#
# Branch: `if method not in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE',
# 'OPTIONS'): raise BadRequest('method %r is not relayed')`. Closest existing test:
# test_broker_bridge.py:38 ('CONNECT api.anthropic.com:443 HTTP/1.1'), one uppercase
# member outside the list; no test in tests/v1 sends a lowercase, mixed-case or
# near-miss method. The shape a future edit takes is `method.upper() not in ...` (or a
# startswith, or a .strip()), which admits 'post' and 'POSTT': the bridge then relays a
# request line it never vetted, while Core, comparing the same way the bridge does now,
# refuses it, and the CLI's connection dies for a reason nobody logged.

@pytest.mark.parametrize('line', [
    'post /v1/messages HTTP/1.1',                       # upper() would admit this
    'PoST /v1/messages HTTP/1.1',
    'trace /v1/messages HTTP/1.1',
    'connect x:443 HTTP/1.1',
    'options /v1/messages HTTP/1.1',
    'POSTT /v1/messages HTTP/1.1',                      # a prefix match would admit it
], ids=['lower-post', 'mixed-post', 'lower-trace', 'lower-connect', 'lower-options',
        'near-miss'])
def test_only_the_exact_uppercase_methods_are_relayed_and_the_rest_never_reach_a_pipe(
        line):
    data = raw(line, 'Host: x', 'Authorization: Bearer brk_x',
               'Content-Length: %d' % len(BODY), body=BODY)
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(data))
    calls = []
    b = W.Bridge(lambda: calls.append(1) or Pipe())
    try:
        b.start(lambda port: None)
        assert _answer(b, data) == REFUSED_400 and calls == []
    finally:
        b.close()
    for m in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'):
        got = W.read_request(io.BytesIO(ok_request(method=m)))
        assert got.method == m and got.body == BODY      # the list is exactly these seven


# ── 3. broker_bridge.py:158-161: who has to declare a body ──
#
# Branch: `if length is None: if method in ('POST', 'PUT', 'PATCH'): raise BadRequest`
# and the `return req` next to it. Closest existing test: test_broker_bridge.py:52
# ('POST /v1/messages HTTP/1.1', 'Host: x', body=b'{}') pins POST alone, and nothing in
# tests/v1 sends a PUT or PATCH anywhere. Drop 'PUT' from that tuple and the bridge
# accepts a PUT that declared nothing, reads no body, and frames it to Core as
# 'Content-Length: 0': a write whose payload vanished, answered as if it had been
# relayed. The other side is the failure in the opposite direction: forcing HEAD,
# DELETE or OPTIONS to declare a body the CLI never sends.

def test_a_put_or_patch_that_declares_no_body_is_refused_before_anything_is_relayed():
    for m in ('POST', 'PUT', 'PATCH'):                       # a writer must say how much
        with pytest.raises(W.BadRequest):
            W.read_request(io.BytesIO(raw('%s /v1/messages HTTP/1.1' % m, 'Host: x')))
    for m in ('GET', 'HEAD', 'DELETE', 'OPTIONS'):           # a reader must not have to
        got = W.read_request(io.BytesIO(raw('%s /v1/messages HTTP/1.1' % m, 'Host: x')))
        assert got.method == m and got.body == b''
    lies = raw('PUT /v1/messages HTTP/1.1', 'Host: x', 'Authorization: Bearer brk_x',
               'Content-Length: 100', body=b'{"half":1}')
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(lies))
    pipes = []
    b = W.Bridge(lambda: pipes.append(Pipe()) or pipes[-1])
    try:
        b.start(lambda port: None)
        width = b._slots._value
        assert _answer(b, lies).startswith(b'HTTP/1.1 400') and pipes == []
        _slot_back(b, width)
        assert _answer(b, raw('PUT /v1/messages HTTP/1.1', 'Host: x',
                              'Authorization: Bearer brk_x')).startswith(b'HTTP/1.1 400')
        _slot_back(b, width)
        assert pipes == []                                   # nothing was opened for either
        assert _answer(b, ok_request(method='PUT', body=BODY)).endswith(b'\r\n\r\nok')
        _slot_back(b, width)
        (p,) = pipes
        up = W.read_request(io.BytesIO(p.sent))               # an honest PUT: body and all
        assert (up.method, up.path, up.body, p.closed) == ('PUT', '/v1/messages', BODY, True)
    finally:
        b.close()


# ── 4. broker_bridge.py:277-282: the slots that really exist are all busy first ──
#
# Branch: `if not self._slots.acquire(blocking=False):` with the counting and the drain
# that follow. Closest existing tests: test_broker_bridge.py:133 and
# test_gaps_node_broker_bridge.py:356 both REPLACE b._slots with a BoundedSemaphore(1)
# they hold by hand, so the bridge's own BoundedSemaphore(CONCURRENT) is never filled
# by real work and the `finally: release` that keeps it honest is never watched. The
# width is read off the bridge rather than repeated here, so widening the default the
# bridge gives itself is caught too. Hand the acquire back to the class, release one too
# many, or widen the default, and the bridge answers 503 with free slots or grows slots
# without bound; both pass the suite today.

def test_the_real_slots_are_all_busy_before_a_request_is_refused_busy_and_then_come_back():
    gate, started, pipes = threading.Event(), [], []

    class Held(Pipe):
        def recv(self, n):
            started.append(1)
            gate.wait(5)                                     # Core takes its time
            return b''

    def connect():
        pipes.append(Held())
        return pipes[-1]
    b = W.Bridge(connect, timer=Timers())        # the slot count the bridge gives itself
    width = b._slots._value                      # read off the bridge, not repeated here
    assert width == W.CONCURRENT                 # the width it advertises, not one wider
    stuck = [FakeSock(ok_request()) for _ in range(width)]   # every slot, by real work
    third, fourth = FakeSock(ok_request()), FakeSock(ok_request())
    try:
        b.start(lambda port: None)
        workers = [threading.Thread(target=b._serve, args=(s,), daemon=True)
                   for s in stuck]
        for t in workers:
            t.start()
        assert _wait_for(lambda: len(started) == width), 'the slots never filled'
        b._serve(third)                                      # no slot left: refused here
        assert b.busy_refused == 1 and len(pipes) == width    # nothing was opened for it
        assert third.sent == [BUSY_503]                      # one reply, the right one
        kinds = [kind for kind, _ in third.events]           # answer, then stop sending,
        assert kinds == ['send', 'shutdown', 'timeout', 'recv']   # then read what is left
        assert third.shutdowns == [socket.SHUT_WR]
        assert third.recvs == [min(W.DRAIN_BYTES, 8192)]     # a bounded read, not a free one
        gate.set()
        for t in workers:
            t.join(5)
            assert not t.is_alive()
        assert all(p.closed for p in pipes)                  # every pipe was closed
        assert b.busy_refused == 1                           # the refusal was counted once
        b._serve(fourth)                       # and the slot really came back for the next
        assert len(pipes) == width + 1 and b.busy_refused == 1   # a pipe was opened for it
        assert b._slots.acquire(blocking=False)              # none of them leaked
        for _ in range(width - 1):
            assert b._slots.acquire(blocking=False)
        assert not b._slots.acquire(blocking=False)          # exactly width, no more
    finally:
        gate.set()
        b.close()


# ── 5. broker_bridge.py:167-170 and 308: no second request hides behind the body ──
#
# Branch: `body = f.read(n); if len(body) != n: raise BadRequest('the body ended
# early')` together with the single `pipe.sendall(frame(...))` of _serve. Closest
# existing test: test_broker_bridge.py:54 only ever sends FEWER bytes than declared;
# nothing sends MORE. A client that pipelines a second request after the first body has
# to have it left unread on the connection: read past n, or loop over the connection,
# and the bridge has become a smuggling proxy that relays a request it never parsed,
# bounded, authenticated or logged. The second request is pushed only once the answer to
# the first has been read, so this never depends on whether a close with unread bytes is
# a FIN or a reset on the platform running it.

def test_bytes_that_follow_the_declared_body_are_never_read_and_never_reach_the_pipe():
    first = ok_request(body=b'ab')
    second = raw('POST /second HTTP/1.1', 'Host: x', 'Authorization: Bearer brk_x',
                 'Content-Length: %d' % len(BODY), body=BODY)
    stream = io.BytesIO(first + second)
    req = W.read_request(stream)
    assert (req.method, req.body) == ('POST', b'ab')
    assert stream.tell() == len(first)                       # it stopped at the body's end
    assert b'/second' not in stream.getvalue()[:stream.tell()]
    pipes = []

    def connect():
        pipes.append(Pipe())
        return pipes[-1]
    b = W.Bridge(connect)
    try:
        b.start(lambda port: None)
        with socket.create_connection(('127.0.0.1', b.port), timeout=5) as c:
            c.sendall(first)                                 # one request, answered
            assert _read_to_eof_before(c, b'\r\n\r\nok').endswith(b'\r\n\r\nok')
            c.sendall(second)                                # then the smuggled second
            assert _read_to_eof(c) == b''                    # nothing more is ever answered
        (p,) = pipes
        assert p.sent.count(b'HTTP/1.1') == 1 and b'/second' not in p.sent
        assert W.read_request(io.BytesIO(p.sent)).body == b'ab'
        assert p.closed                                      # and that one connection is over
    finally:
        b.close()


def _read_to_eof_before(c, want):
    """Read up to *want* and stop there: the tail the client pushes afterwards is left
    for the bridge to leave unread, which is the case under test."""
    out = b''
    while want not in out:
        try:
            chunk = c.recv(65536)
        except ConnectionError:
            break
        if not chunk:
            break
        out += chunk
    return out


# ── 6. broker_bridge.py:216-217: a refused client that shuts up is closed out at once ──
#
# Branch: `chunk = sock.recv(min(left, 8192)); if not chunk: break` inside _drain.
# Closest existing tests: test_broker_bridge.py:149 and test_broker_gaps.py:448 both
# feed the drain a client that KEEPS sending (a trickle and a flood), so the EOF half -
# by far the common case, a client that sent its head and is waiting for the refusal -
# is never taken. Drop the break and every 400, 401, 413 or 503 costs the bridge a full
# DRAIN_S of a held thread: free amplification for anyone who connects, and the drain
# here is given a clock that ticks so that the wrong code still finishes, in 30 reads. The read bound
# min(left, 8192) is asserted nowhere either, and without it one refused client can ask
# for the whole declared body in a single read.

def test_a_refused_client_that_sends_nothing_more_ends_the_drain_at_the_first_read(
        monkeypatch):
    clock = Clock(0.0, 1.0)                                  # a second per read, 30 to spend
    s = FakeSock(rest=b'')                                   # every read answers EOF
    monkeypatch.setattr(W, 'DRAIN_S', 30.0)                  # so time cannot be the reason
    monkeypatch.setattr(W, 'time', clock)
    W._drain(s)
    assert s.shutdowns == [socket.SHUT_WR]                   # stop answering, then read
    assert s.recvs == [min(W.DRAIN_BYTES, 8192)]             # exactly one bounded read
    assert s.sent == []                                      # and nothing is ever written
    assert clock.reads == 2                                  # budget read twice, 29 s left


# ── 7. broker_bridge.py:208-213: the drain clock is one total, stopped at equality ──
#
# Branch: `end = time.monotonic() + DRAIN_S; while left > 0: wait = end -
# time.monotonic(); if wait <= 0: break`. Closest existing test:
# test_broker_bridge.py:149 lets a real client trickle for 0.3 s, which only shows the
# loop ends SOMEWHERE. `wait < 0` instead of `wait <= 0`, or recomputing `end` inside
# the loop (a per-read timeout, which the comment above the function says is not what
# this is) both pass it. Here the clock is handed to the module, the last pass lands on
# wait == 0 exactly, and the extra read either change would take is caught.

def test_the_drain_reads_under_one_total_deadline_and_stops_the_moment_it_is_reached(
        monkeypatch):
    monkeypatch.setattr(W, 'DRAIN_BYTES', 8)
    monkeypatch.setattr(W, 'DRAIN_S', 1.0)
    monkeypatch.setattr(W, 'time', Clock(0.0, 0.5))          # 0.0, 0.5, 1.0: ends at zero
    s = FakeSock(rest=b'x' * 4)                              # a client that dribbles on
    W._drain(s)
    assert s.recvs == [8]                                    # one read, never a second
    assert s.timeouts == [0.5]                               # armed with the time that is left
    assert s.delivered == 4 and s.sent == []


# ── 8. broker_bridge.py:195-199 (with 270-274): cutting a socket that is already gone ──
#
# Branch: `try: sock.shutdown(socket.SHUT_RDWR) except OSError: pass` in _cut, and the
# same swallow in serve()'s finally. Closest existing tests:
# test_broker_bridge.py:286 fires the deadline against a live loopback connection, so
# shutdown succeeds and the swallow is never entered, and test_broker_gaps.py:526
# swallows only for _send. _cut runs on a timer thread, where a raise is a thread that
# dies with a traceback instead of a cut, and serve()'s swallow is the difference
# between a closed connection and a second reply bolted onto a refused one.

def test_a_deadline_cut_on_a_socket_that_is_already_gone_never_raises():
    live = FakeSock()
    W._cut(live)
    assert live.events == [('shutdown', socket.SHUT_RDWR)]
    gone = FakeSock(shutdown_raises=OSError('not connected'))
    W._cut(gone)                                             # must not raise on the timer
    assert gone.events == [('shutdown', socket.SHUT_RDWR)]   # attempted once, then forgotten
    timers = Timers()
    b = W.Bridge(_nope, timer=timers)
    s = FakeSock(ok_request(), shutdown_raises=OSError('not connected'))
    try:
        b.start(lambda port: None)
        b.serve(s)                                           # the handler's own entry point
        assert s.sent == [BAD_GATEWAY_502]                   # one reply, the right one
        assert s.events[-1] == ('shutdown', socket.SHUT_RDWR)   # the finally still ran
        assert s.timeouts[0] == b._idle
        assert len(timers.made) == 1 and timers.made[0].cancelled
        assert timers.made[0].delay == b._deadline
        timers.fire_all()                                    # a late cut is a no-op
        assert s.sent == [BAD_GATEWAY_502]
    finally:
        b.close()


# ── 9. broker_bridge.py:283-319: every refusal kind gives its slot back ──
#
# Branch: `finally: self._slots.release()` seen from each early `return` inside the try
# of _serve - the 400 framing path, the 401 admission path, the 413 size path and the
# 502 pipe path. Closest existing tests: test_broker_bridge.py:133
# and 223 run on a bridge whose CONCURRENT=2 they then overwrite with their own
# semaphore, and test_gaps_node_broker_bridge.py:316 only checks the slot after a
# mid-relay death, so a single burned slot is invisible to all of them. On a one-slot
# bridge a leak is the end of the service, so it is asserted here: after one of every
# refusal, an honest request must still be served.

def test_every_kind_of_refusal_gives_its_slot_back_so_the_bridge_stays_usable():
    pipes, down = [], [True]

    def connect():
        if down[0]:
            down[0] = False
            raise OSError('the pipe is down')                # the 502 kind
        pipes.append(Pipe())
        return pipes[-1]
    b = W.Bridge(connect, concurrent=1, timer=Timers())   # one slot: a leak is seen at once
    width = b._slots._value
    try:
        b.start(lambda port: None)
        refusals = [
            (raw('GET /v1/messages HTTP/1.1', 'Bad Name: 1'), b'HTTP/1.1 400'),
            (raw('POST /v1/messages HTTP/1.1', 'Host: x', 'Authorization: Bearer brk_x',
                 'Content-Length: 10', body=b'{}'), b'HTTP/1.1 400'),      # ended early
            (head_only('POST /v1/messages HTTP/1.1', 'Host: x',
                       'Authorization: Bearer nope'), b'HTTP/1.1 401'),
            (head_only('POST /v1/messages HTTP/1.1', 'Host: x',
                       'Authorization: Bearer brk_x',
                       'Content-Length: %d' % (W.MAX_BODY + 1)), b'HTTP/1.1 413'),
            (ok_request(), b'HTTP/1.1 502'),                 # the pipe could not be opened
        ]
        for data, status in refusals:
            assert _answer(b, data).startswith(status), status
            _slot_back(b, width)                           # refused, and the slot returned
        assert b.busy_refused == 0                        # none of them was a busy case
        assert _answer(b, ok_request()).endswith(b'\r\n\r\nok')
        _slot_back(b, width)                              # the served one returned too
        (p,) = pipes
        assert p.closed and W.read_request(io.BytesIO(p.sent)).body == BODY
    finally:
        b.close()


# ── 10. broker_bridge.py:260-263: closing a bridge twice is silent and final ──
#
# Branch: `if self._thread is not None: self._server.shutdown()` plus
# `self._server.server_close()`, taken a second time round. Closest existing test:
# test_broker_bridge.py:377 closes a bridge that NEVER started, which is the
# `_thread is None` half; nothing closes a started bridge twice, and that is exactly
# what an execution teardown does when its own finally runs after the owner has closed
# it. A second close that raises leaves the caller's cleanup half done, and a listener
# still bound after close() is a port the next execution is told about and does not own.

def test_closing_a_started_bridge_twice_is_silent_and_leaves_the_listener_closed():
    pipes = []
    b = W.Bridge(lambda: pipes.append(Pipe()) or pipes[-1])
    b.start(lambda port: None)
    try:
        assert _answer(b, ok_request()).endswith(b'\r\n\r\nok')
    finally:
        b.close()
    listener = b._server.socket
    assert listener.fileno() == -1                           # the port is given up at once
    b.close()                                                # teardown after teardown
    assert listener.fileno() == -1                           # still given up, and no raise
    again = W.Bridge(lambda: pipes.append(Pipe()) or pipes[-1])
    try:
        again.start(lambda port: None)
        assert _answer(again, ok_request()).endswith(b'\r\n\r\nok')
    finally:
        again.close()
