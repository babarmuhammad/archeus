"""Red-team probes of the broker's request reader (node/broker_listener.py `_Raw`, `_Gate`, the
deadline; node/broker_bridge.py `read_request`; node/broker.py `serve`). Built on the fakes of
tests/v1/unit/test_broker_listener.py: in-memory connections and a fake clock, no socket, no
network.

A FAILING test is a confirmed defect."""

import io
import os
import sys
import tracemalloc

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'v1', 'unit'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'v1'))

from unit.test_broker_listener import (BODY, RIGS, Conn, Drip, Rig, dripped, http,  # noqa: E402
                                       status)
from archeus.node import broker as B  # noqa: E402
from archeus.node import broker_bridge as wire  # noqa: E402
from archeus.node import broker_listener as L  # noqa: E402


@pytest.fixture(autouse=True)
def _no_listener_outlives_its_test():
    yield
    while RIGS:
        RIGS.pop().broker.revoke_all()


def raw_request(g, request_line='POST /v1/messages HTTP/1.1', headers=None, body=BODY, auth=True,
                cl=True, eol='\r\n'):
    hs = ['Host: 127.0.0.1']
    if auth:
        hs.append('Authorization: Bearer %s' % g.token)
    if cl:
        hs.append('Content-Length: %d' % len(body))
    hs += headers or []
    return (eol.join([request_line] + hs) + eol + eol).encode('utf-8') + body


def refused(rig, g, data, expect):
    conn = rig.get(g, data)
    assert rig.sent == [], 'something was forwarded: %r' % (rig.sent,)
    assert status(conn) == expect, (status(conn), conn.sent[:60])


# ── framing the reader must refuse, and the wire must never see ──

def test_baseline_valid_request_is_forwarded():
    rig = Rig()
    g = rig.grant()
    conn = rig.get(g, raw_request(g))
    assert status(conn) == 200 and len(rig.sent) == 1


@pytest.mark.parametrize('what,headers', [
    ('chunked', ['Transfer-Encoding: chunked']),
    ('chunked-upper', ['TRANSFER-ENCODING: Chunked']),
    ('te-and-cl', ['Transfer-Encoding: identity']),
    ('upgrade', ['Upgrade: websocket']),
    ('dup-cl', ['Content-Length: 5']),
    ('dup-cl-lower', ['content-length: %d' % len(BODY)]),
    ('dup-auth', ['Authorization: Bearer brk_other']),
    ('dup-host', ['Host: evil']),
    ('dup-x-api-key', ['x-api-key: a', 'X-API-KEY: b']),
    ('space-before-colon', ['Transfer-Encoding : chunked']),
    ('obs-fold', [' folded: x']),
    ('tab-fold', ['\tfolded: x']),
    ('nul-in-value', ['X-A: a\x00b']),
    ('bare-cr-in-value', ['X-A: a\rb']),
    ('empty-name', [': x']),
    ('no-colon', ['garbage']),
    ('non-ascii-name', ['X-é: x']),
])
def test_headers_refused(what, headers):
    rig = Rig()
    g = rig.grant()
    refused(rig, g, raw_request(g, headers=headers), 400)


@pytest.mark.parametrize('cl', ['+5', ' 5', '-1', '0x10', '1_0', '5.0', '', '99999999999999', '５', '5\t5'])
def test_content_length_forms_refused(cl):
    rig = Rig()
    g = rig.grant()
    data = raw_request(g, cl=False, headers=['Content-Length: %s' % cl])
    conn = rig.get(g, data)
    assert rig.sent == []
    assert status(conn) in (400, 413)


def test_content_length_larger_than_the_cap_is_refused_before_any_body():
    rig = Rig()
    g = rig.grant()
    data = raw_request(g, cl=False, headers=['Content-Length: 99999999999'], body=b'')
    conn = rig.get(g, data)
    assert status(conn) == 413 and rig.sent == []


def test_content_length_over_the_grants_own_max_body():
    rig = Rig()
    g = rig.grant(limits=B.BrokerLimits(max_requests=5, max_body=100))
    data = raw_request(g, cl=False, headers=['Content-Length: 101'], body=b'x' * 101)
    conn = rig.get(g, data)
    assert status(conn) == 413 and rig.sent == []


def test_content_length_longer_than_the_body_sent():
    rig = Rig()
    g = rig.grant()
    data = raw_request(g, cl=False, headers=['Content-Length: %d' % (len(BODY) + 10)])
    refused(rig, g, data, 400)


def test_pipelined_second_request_is_never_read():
    rig = Rig()
    g = rig.grant()
    second = raw_request(g)
    conn = rig.get(g, raw_request(g) + second)
    assert status(conn) == 200 and len(rig.sent) == 1


def test_smuggled_second_request_in_the_body_is_forwarded_as_body_only():
    rig = Rig()
    g = rig.grant()
    inner = raw_request(g)
    body = BODY + b'\r\n\r\n' + inner
    conn = rig.get(g, raw_request(g, body=body))
    # the body is not JSON (trailing data): refused, never forwarded
    assert rig.sent == [] and status(conn) == 400


@pytest.mark.parametrize('line,expect', [
    ('POST /v1/messages HTTP/1.0', 400), ('post /v1/messages HTTP/1.1', 400),
    ('POST http://evil/v1/messages HTTP/1.1', 400), ('POST //v1/messages HTTP/1.1', 400),
    ('POST /v1/messages%2e HTTP/1.1', 400), ('POST /v1/../v1/messages HTTP/1.1', 400),
    ('POST /v1/./messages HTTP/1.1', 400), ('POST /v1\\messages HTTP/1.1', 400),
    ('POST /v1/messages HTTP/1.1 ', 400), ('POST  /v1/messages HTTP/1.1', 400),
    ('CONNECT 127.0.0.1:80 HTTP/1.1', 400), ('POST /v1/messages?beta=true&x=1 HTTP/1.1', 404),
    ('POST /v1/messages;x HTTP/1.1', 404), ('POST /v1/messages/ HTTP/1.1', 404),
    ('POST /V1/messages HTTP/1.1', 404), ('POST /v1/messages#f HTTP/1.1', 404),
    ('POST /v1/messages?beta=true HTTP/1.1', 200), ('POST /v1/messages? HTTP/1.1', 200),
])
def test_request_line_shapes(line, expect):
    rig = Rig()
    g = rig.grant()
    conn = rig.get(g, raw_request(g, request_line=line))
    assert status(conn) == expect, (line, status(conn))
    assert len(rig.sent) == (1 if expect == 200 else 0)


@pytest.mark.parametrize('eol', ['\n', '\r'])
def test_bare_lf_or_cr_line_endings_refused(eol):
    rig = Rig()
    g = rig.grant()
    refused(rig, g, raw_request(g, eol=eol), 400)


def test_header_flood_and_oversized_header_block():
    rig = Rig()
    g = rig.grant()
    refused(rig, g, raw_request(g, headers=['X-%d: a' % i for i in range(80)]), 400)
    refused(rig, g, raw_request(g, headers=['X-Big: ' + 'a' * 40000]), 400)
    refused(rig, g, raw_request(g, headers=['X-%d: %s' % (i, 'a' * 2000) for i in range(20)]), 400)


def test_one_byte_under_the_header_budget_then_body():
    """The budget arithmetic at its edge: a header block of exactly max_header_bytes."""
    rig = Rig()
    g = rig.grant()
    base_len = len(raw_request(g).split(b'\r\n\r\n')[0])
    pad = wire.MAX_HEADER_BYTES - base_len - len('\r\nX-Pad: ') - 4
    for extra in (-3, -2, -1, 0, 1, 2):
        conn = rig.get(g, raw_request(g, headers=['X-Pad: ' + 'a' * (pad + extra)]))
        assert status(conn) in (200, 400), extra


@pytest.mark.parametrize('auth', ['Bearer', 'bearer  %s', 'BEARER %s', 'Bearer %s, Bearer brk_x',
                                  'Bearer %s\t', 'Basic %s', 'Bearer\t%s'])
def test_authorization_scheme_shapes_never_forward_without_the_token(auth):
    rig = Rig()
    g = rig.grant()
    value = auth % g.token if '%s' in auth else auth
    conn = rig.get(g, raw_request(g, auth=False, headers=['Authorization: ' + value]))
    if auth in ('bearer  %s', 'BEARER %s', 'Bearer %s\t'):
        assert status(conn) == 200
    else:
        assert rig.sent == []


# ── the deadline ──

def drip_status(rig, g, head, step=9.0):
    drip = Drip(rig.now, head, step)
    conn = Conn(g.port)
    conn.makefile = lambda mode, buffering=-1: drip if buffering == 0 else io.BufferedReader(drip)
    g.ep.handle(conn)
    return conn, drip


@pytest.mark.parametrize('step', [0.5, 3.0, 9.9, 29.0, 31.0, 100.0])
@pytest.mark.parametrize('where', ['start', 'headers', 'body'])
def test_slow_drip_ends_at_the_deadline(where, step):
    rig = Rig(clock=lambda: rig.now[0])
    g = rig.grant()
    full = raw_request(g)
    head = {'start': b'', 'headers': full[:25], 'body': full[:-len(BODY)] + BODY[:3]}[where]
    conn, drip = drip_status(rig, g, head, step)
    assert status(conn) == 408 and rig.sent == []
    assert drip.reads <= B.READ_DEADLINE_S / step + 4
    assert conn.closed


def test_drip_inside_the_idle_timeout_cannot_outlast_the_deadline_on_the_wire_clock():
    """A real clock: each recv's timeout is min(IDLE_S, time left), so the last recv before the
    deadline is bounded by what is left, never by IDLE_S."""
    rig = Rig(clock=lambda: rig.now[0])
    g = rig.grant()
    conn, drip = drip_status(rig, g, raw_request(g)[:30], step=0.001)
    # a 1 ms drip: 30 s of clock takes 30000 reads: the loop is long but bounded by the clock
    assert status(conn) == 408
    assert drip.reads < 40000


class Scripted(io.RawIOBase):
    """Chunks, each costing the clock some seconds when it is read."""

    def __init__(self, now, script):
        self.now, self.script, self.reads = now, list(script), 0

    def readable(self):
        return True

    def readinto(self, b):
        self.reads += 1
        if not self.script:
            return 0
        data, cost = self.script.pop(0)
        self.now[0] += cost
        n = min(len(b), len(data))
        b[:n] = data[:n]
        if len(data) > n:
            self.script.insert(0, (data[n:], 0))
        return n


def scripted_status(rig, g, script):
    raw = Scripted(rig.now, script)
    conn = Conn(g.port)
    conn.makefile = lambda mode, buffering=-1: raw if buffering == 0 else io.BufferedReader(raw)
    g.ep.handle(conn)
    return conn, raw


def test_body_that_ends_after_the_deadline_is_refused():
    rig = Rig(clock=lambda: rig.now[0])
    g = rig.grant()
    full = raw_request(g)
    cut = len(full) - 5
    conn, _ = scripted_status(rig, g, [(full[:cut], 1.0), (full[cut:], 40.0)])
    assert status(conn) == 408 and rig.sent == []


def test_body_whose_last_byte_comes_exactly_at_the_deadline():
    rig = Rig(clock=lambda: rig.now[0])
    g = rig.grant()
    full = raw_request(g)
    cut = len(full) - 5
    conn, _ = scripted_status(rig, g, [(full[:cut], 1.0), (full[cut:], B.READ_DEADLINE_S - 1.0)])
    assert status(conn) in (200, 408)


def test_headers_end_after_the_deadline_with_the_body_already_buffered():
    """The whole request is in one chunk that arrives after the deadline."""
    rig = Rig(clock=lambda: rig.now[0])
    g = rig.grant()
    conn, _ = scripted_status(rig, g, [(raw_request(g), B.READ_DEADLINE_S + 1)])
    assert status(conn) == 408 and rig.sent == []


def test_socket_timeout_left_for_the_response_is_not_the_leftover_of_the_read_deadline():
    """LOW: _Raw.readinto sets conn.settimeout(min(IDLE_S, left)) and never restores it, so the
    timeout the response is written under (conn.sendall) is whatever was left of the 30 s request
    deadline at the last recv: a request that took 29.95 s sends its upstream response under a
    50 ms timeout (broker_listener.py:70-73)."""
    rig = Rig(clock=lambda: rig.now[0])
    g = rig.grant()
    full = raw_request(g)
    cut = len(full) - 5
    seen = []
    raw = Scripted(rig.now, [(full[:cut], 29.9), (full[cut:], 0.05)])
    conn = Conn(g.port)
    conn.makefile = lambda mode, buffering=-1: raw if buffering == 0 else io.BufferedReader(raw)
    orig = conn.sendall
    conn.sendall = lambda d: (seen.append(getattr(conn, 'timeout', None)), orig(d))
    g.ep.handle(conn)
    assert status(conn) == 200 and seen
    assert min(seen) >= 1.0, 'responses are written under a %.2f s socket timeout' % min(seen)


def test_declared_body_length_allocates_up_front():
    """LOW: io.BufferedReader.read(n) allocates n bytes at once; the reader asks for the declared
    Content-Length (up to max_body, 16 MiB) before a single body byte has arrived, so each of the
    8 connections a grant holds pins up to 16 MiB for up to 30 s while sending nothing."""
    class Empty(io.RawIOBase):
        def readable(self):
            return True

        def readinto(self, b):
            return 0

    f = io.BufferedReader(L._Raw(Conn(1), Empty(), lambda: 0.0, 1e9))
    tracemalloc.start()
    try:
        f.read(wire.MAX_BODY)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < (1 << 20), 'read(%d) with no data held %.1f MiB' % (wire.MAX_BODY, peak / (1 << 20))


def test_attest_time_is_not_part_of_the_request_deadline_but_the_read_clock_starts_after_it():
    """_Raw's end is taken after origin attestation, serve's own deadline (t0) before it: the two
    clocks differ by the attest time; the stricter one still ends the read."""
    rig = Rig(clock=lambda: rig.now[0])
    g = rig.grant()
    conn, drip = drip_status(rig, g, b'', 9.0)
    assert status(conn) == 408


def test_real_socket_drip_is_cut_at_the_deadline():
    """_Raw over a real socketpair and a real clock: one byte every 0.3 s against a 1 s deadline."""
    import socket
    import threading
    import time
    a, b = socket.socketpair()
    stop = threading.Event()

    def drip():
        try:
            while not stop.is_set():
                a.send(b'x')
                time.sleep(0.3)
        except OSError:
            pass

    threading.Thread(target=drip, daemon=True).start()
    try:
        rd = io.BufferedReader(L._Raw(b, b.makefile('rb', buffering=0), time.monotonic, time.monotonic() + 1.0))
        t = time.monotonic()
        with pytest.raises(B.Refused) as ei:
            rd.read(1000)
        assert ei.value.status == 408 and time.monotonic() - t < 3
    finally:
        stop.set()
        a.close()
        b.close()


def test_real_socket_silent_peer_is_cut_by_the_deadline_not_the_idle_time():
    import socket
    import time
    a, b = socket.socketpair()
    try:
        rd = io.BufferedReader(L._Raw(b, b.makefile('rb', buffering=0), time.monotonic, time.monotonic() + 0.5))
        t = time.monotonic()
        with pytest.raises((B.Refused, OSError)):
            rd.read(10)
        assert time.monotonic() - t < 3
    finally:
        a.close()
        b.close()
