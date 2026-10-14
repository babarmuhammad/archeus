"""F4 (p20-design-gate D2): at a device's stream cap the newest stream wins and
the oldest is closed. Over the real HTTP stack: item 112's two reloads, the
order a concurrent burst is resolved in, a third device left alone, the pool's
cap still a refusal, and authentication still before any of it.
Mutation-verified by tools/mutate_p20.py (Q18 onward)."""

import threading
import time

from archeus.api import sse
from archeus.infra.eventlog import outbox
from v1.integration.test_api_auth import observe_device
from v1.judge.http import SSEClient


def _until(fn, what, timeout=10):
    deadline = time.monotonic() + timeout
    while not fn():
        assert time.monotonic() < deadline, 'timed out: %s' % what
        time.sleep(0.02)


def _open(tc, token, n):
    """*n* streams of one token, each registered before the next opens."""
    out = []
    for _ in range(n):
        before = tc.core.api.sse.count()
        s = SSEClient(tc.base_url, token)
        assert s.status == 200
        _until(lambda before=before, s=s: tc.core.api.sse.count() > before or s.eof, 'registered')
        out.append(s)
    return out


def _port(stream):
    """The server-side stream object's peer port: which client it serves."""
    return stream.conn.getpeername()[1]


def _ports(tc, device_id):
    with tc.core.api.sse._lock:
        return [_port(s) for s in tc.core.api.sse._open if s.device_id == device_id]


def _mine(client):
    return client.sock.getsockname()[1]


def _gets_frames(tc, *clients):
    """Each client is still live: it receives the next committed event."""
    tc.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
                                          'idempotency_key': 'k%f' % time.monotonic()})
    for c in clients:
        assert c.frames(1), 'a live stream received nothing'


def test_two_reloads_leave_the_live_page_its_stream_at_once(tc):
    """Item 112: two streams whose page reloaded away (closed client-side, with
    nothing written since, so Core has not noticed) used to refuse the live page
    for a heartbeat (19.9 s measured). Now it connects at once."""
    dev, token = observe_device(tc)
    for s in _open(tc, token, 2):
        s.close()                                   # the page went; Core does not know
    assert len(tc.core.api.sse.connections(dev)) == 2
    t0 = time.monotonic()
    live = SSEClient(tc.base_url, token)
    try:
        assert live.status == 200
        assert time.monotonic() - t0 < 2.0
        _until(lambda: _ports(tc, dev) and _mine(live) in _ports(tc, dev), 'live registered')
        _gets_frames(tc, live)
    finally:
        live.close()


def test_the_newest_wins_the_oldest_closes_and_no_other_stream_is_touched(tc):
    a_dev, a = observe_device(tc)
    b_dev, b = observe_device(tc)
    bs = _open(tc, b, 2)                            # another device, at its own cap
    a1, a2 = _open(tc, a, 2)
    b_before = tc.core.api.sse.connections(b_dev)
    a_before = tc.core.api.sse.connections(a_dev)
    a3 = SSEClient(tc.base_url, a)
    try:
        assert a3.status == 200
        assert a1.closed(), 'the oldest stream was not closed'
        _until(lambda: _ports(tc, a_dev) == [_mine(a2), _mine(a3)], 'a2 and a3 held')
        after = tc.core.api.sse.connections(a_dev)
        # presence sees one close and one open: the oldest id gone, one new id
        assert after[0] == a_before[1] and after[1] not in a_before
        assert tc.core.api.sse.connections(b_dev) == b_before
        assert tc.core.api.sse.count() == 4
        _gets_frames(tc, a2, a3, *bs)               # nothing else was closed
        assert not a2.eof and not any(s.eof for s in bs)
    finally:
        for s in (a1, a2, a3, *bs):
            s.close()


def test_a_takeover_is_no_presence_transition(tc):
    """The device never went from no stream to one, or back: no trace is
    written for a takeover (p15 §5 D4 records only those transitions)."""
    dev, token = observe_device(tc)
    first = _open(tc, token, 2)
    head = _head(tc)
    third = SSEClient(tc.base_url, token)
    try:
        assert third.status == 200 and first[0].closed()
        _until(lambda: len(_ports(tc, dev)) == 2 and first[0].eof, 'taken over')
        time.sleep(0.2)
        types = [e['type'] for e in _events_after(tc, head)]
        assert not [t for t in types if t.startswith(sse.PRESENCE)], types
    finally:
        for s in (*first, third):
            s.close()


def test_a_concurrent_burst_keeps_exactly_the_last_two_registered(tc, monkeypatch):
    """Eight opens from one device at the same instant, on top of two old
    streams: every one is answered 200 (none refused), the device ends with
    exactly two, and those two are the last two Core registered — the order
    is the pool's own, decided under its lock, never the network's."""
    dev, token = observe_device(tc)
    old = _open(tc, token, 2)
    order, real = [], sse._Stream

    # recorded where `_register` builds the stream, inside the pool's lock: a
    # record taken after `_register` returns can swap two neighbours
    def stream(device_id, conn=None):
        order.append(conn.getpeername()[1])
        return real(device_id, conn)
    monkeypatch.setattr(sse, '_Stream', stream)
    gate, got = threading.Barrier(8), []

    def go():
        gate.wait()
        got.append(SSEClient(tc.base_url, token))
    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    try:
        assert [c.status for c in got] == [200] * 8
        _until(lambda: len(order) == 8, 'all registered')
        assert _ports(tc, dev) == order[-2:]
        for c in old:
            assert c.closed()
        by_port = {_mine(c): c for c in got}
        for p in order[:-2]:
            assert by_port[p].closed(), 'a superseded stream stayed open'
        survivors = [by_port[p] for p in order[-2:]]
        _gets_frames(tc, *survivors)
        assert not any(s.eof for s in survivors)
        assert tc.core.api.sse.count() == 2
    finally:
        for c in (*old, *got):
            c.close()


def test_the_pools_cap_is_still_a_refusal_and_a_capped_device_still_takes_over(tc):
    tokens = [tc.token] + [observe_device(tc)[1] for _ in range(4)]
    streams = []
    try:
        for token in tokens[:4]:
            streams += _open(tc, token, 2)
        assert tc.core.api.sse.count() == sse.MAX_STREAMS
        fifth = SSEClient(tc.base_url, tokens[4])          # a new device: the pool is full
        assert fifth.status == 429 and b'too_many_streams' in fifth.body()
        again = SSEClient(tc.base_url, tokens[0])           # a capped device: replaces its own
        streams.append(again)
        assert again.status == 200 and streams[0].closed()
        assert tc.core.api.sse.count() == sse.MAX_STREAMS
        assert not any(s.eof for s in streams[1:8])
    finally:
        for s in streams:
            s.close()


def test_no_takeover_without_a_live_credential(tc):
    """Authentication is before the pool: a revoked or absent token takes over
    nothing, so the policy is no way around a revocation."""
    dev, token = observe_device(tc)
    held = _open(tc, token, 2)
    other_dev, other = observe_device(tc)
    try:
        assert SSEClient(tc.base_url, None).status == 401
        assert SSEClient(tc.base_url, 'x' * 43).status == 401
        r = tc.http('POST', '/v1/devices/%s/revoke' % other_dev,
                    body={'idempotency_key': 'rv-%s' % other_dev})
        assert r.status == 200, r.body
        assert SSEClient(tc.base_url, other).status == 401
        assert len(tc.core.api.sse.connections(dev)) == 2
        _gets_frames(tc, *held)
    finally:
        for s in held:
            s.close()


def _head(tc):
    with tc.core.db.read() as conn:
        return outbox.head(conn)


def _events_after(tc, seq):
    with tc.core.db.read() as conn:
        return [{'type': e.type} for e in outbox.events_after(conn, seq, limit=1000)]
