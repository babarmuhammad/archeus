"""The event stream over real sockets (p3.5b design gate §6; §10 B1–B8, M5)."""

import threading
import time

import pytest

from archeus.api import sse
from archeus.infra.eventlog import retention
from v1.judge.http import SSEClient, TempCore


def _mission(tc, key):
    r = tc.http('POST', '/v1/missions', body={'title': key, 'objective': 'o',
                                              'idempotency_key': key})
    assert r.status == 200, r.body
    return r.json()


def _all(tc):
    return tc.client().events(0)


def _settle(tc):
    """Wait until the engine is idle, so the log stops growing."""
    client = tc.client()
    deadline = time.monotonic() + 30
    while not client._idle():
        assert time.monotonic() < deadline
        time.sleep(0.05)


@pytest.fixture
def quiet(archeus_home, clock):
    """A Core with a 0.1 s heartbeat. Its engine runs, so tests settle it
    before they compare against the log."""
    core = TempCore(archeus_home, heartbeat_s=0.1).start()
    yield core
    core.stop()


# ── B1 replay, B6 identities only ──

def test_last_event_id_replays_exactly_what_came_after(quiet):
    for k in 'abc':
        _mission(quiet, k)
    _settle(quiet)
    seqs = [e['seq'] for e in _all(quiet)]
    n = seqs[len(seqs) // 2]
    s = SSEClient(quiet.base_url, quiet.token, last_event_id=n)
    try:
        assert s.status == 200
        got = s.frames(len([x for x in seqs if x > n]))
        assert [f['id'] for f in got] == [x for x in seqs if x > n]
        by_seq = {e['seq']: e for e in _all(quiet)}
        for f in got:
            assert f['event'] == by_seq[f['id']]['type']
            assert set(f['data']) == {'subject', 'scope'}                     # B6
            assert f['data']['subject'] == by_seq[f['id']]['subject']
            assert f['data']['scope'] == by_seq[f['id']]['scope']
        _mission(quiet, 'd')                                                # then live
        live = s.frames(1)
        assert live[0]['id'] == max(seqs) + 1 and live[0]['event'] == 'mission.created'
    finally:
        s.close()


def test_the_header_wins_over_the_query_and_no_cursor_means_live_only(quiet):
    for k in 'ab':
        _mission(quiet, k)
    _settle(quiet)
    head = _all(quiet)[-1]['seq']
    s = SSEClient(quiet.base_url, quiet.token, last_event_id=head - 1, after=0)
    try:
        assert s.frames(1)[0]['id'] == head
    finally:
        s.close()
    s = SSEClient(quiet.base_url, quiet.token)
    try:
        _mission(quiet, 'c')
        assert s.frames(1)[0]['id'] == head + 1         # nothing replayed, the new one live
    finally:
        s.close()


# ── B2 400 / 410 before the stream ──

@pytest.mark.parametrize('cursor', ['-1', 'x', '1.5', '', '0x1', '1e3'])
def test_a_malformed_cursor_is_400_before_any_stream_bytes(quiet, cursor):
    s = SSEClient(quiet.base_url, quiet.token, last_event_id=cursor)
    assert s.status == 400
    assert s.headers['Content-Type'] == 'application/json'
    assert b'"field":"cursor"' in s.body()


def test_a_pruned_or_ahead_cursor_is_410_with_the_retained_range(quiet):
    _mission(quiet, 'a')
    _settle(quiet)
    head = _all(quiet)[-1]['seq']
    s = SSEClient(quiet.base_url, quiet.token, last_event_id=head + 1)
    assert s.status == 410 and b'"reason":"ahead"' in s.body()
    quiet.core.db.writer.execute(retention.prune, {'now': '2999-01-01T00:00:00.000Z',
                                                   'keep_days': 1})
    s = SSEClient(quiet.base_url, quiet.token, last_event_id=head - 1)
    assert s.status == 410
    assert s.headers['Content-Type'] == 'application/json'
    body = s.body()
    assert b'"reason":"pruned"' in body and (b'"floor":%d' % head) in body
    s = SSEClient(quiet.base_url, quiet.token, last_event_id=head)
    assert s.status == 200                                   # exactly at the floor: fine
    s.close()
    r = quiet.http('GET', '/v1/events?after=%d' % (head - 1))
    assert r.status == 410 and r.json()['detail']['reason'] == 'pruned'


# ── B3 heartbeat, B4 disconnect ──

def test_an_idle_stream_heartbeats(quiet):
    _settle(quiet)
    s = SSEClient(quiet.base_url, quiet.token)
    try:
        assert s.next(2.0) == {'comment': 'hb'}
    finally:
        s.close()


def test_a_client_that_goes_away_frees_its_stream_slot(quiet):
    s = SSEClient(quiet.base_url, quiet.token)
    deadline = time.monotonic() + 5
    while quiet.core.api.sse.count() != 1:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    s.close()
    while quiet.core.api.sse.count() != 0:
        assert time.monotonic() < deadline, 'the slot was never released'
        time.sleep(0.02)


# ── B5 revocation ──

def test_revoking_a_device_closes_its_stream_before_the_revoke_answers(quiet, monkeypatch):
    """With the per-wake token re-check frozen, only the revoke handler itself
    can close the stream — so an EOF by the time it answers proves the order."""
    from v1.integration.test_api_auth import observe_device
    device, token = observe_device(quiet)
    monkeypatch.setattr(sse.Streams, '_still_valid', lambda self, h: True)
    s = SSEClient(quiet.base_url, token)
    other = SSEClient(quiet.base_url, quiet.token)             # another device's stream
    try:
        assert s.status == 200
        r = quiet.http('POST', '/v1/devices/%s/revoke' % device, body={'idempotency_key': 'r'})
        assert r.status == 200
        # already closed when the response arrived: EOF with no waiting
        assert s.wait_eof(0.5)
        assert SSEClient(quiet.base_url, token).status == 401
        assert other.next(2.0) is not None                    # untouched
    finally:
        s.close()
        other.close()


def test_a_revocation_by_any_path_closes_the_stream_within_one_wake(quiet):
    from archeus.core.application import commands
    from v1.integration.test_api_auth import observe_device
    device, token = observe_device(quiet)
    s = SSEClient(quiet.base_url, token)
    try:
        quiet.core.db.writer.execute(commands.revoke_device, {
            'actor': quiet.core.system, 'device_id': device})      # not through the route
        assert s.wait_eof(2.0)
    finally:
        s.close()


# ── B7 order across a restart ──

def test_ids_strictly_increase_across_a_restart(quiet):
    _mission(quiet, 'a')
    _settle(quiet)
    s = SSEClient(quiet.base_url, quiet.token, last_event_id=0)
    first = s.frames(len(_all(quiet)))
    s.close()
    quiet.restart(kill=True)
    _mission(quiet, 'b')
    _settle(quiet)
    s = SSEClient(quiet.base_url, quiet.token, last_event_id=first[-1]['id'])
    try:
        more = s.frames(len(_all(quiet)) - len(first))
        ids = [f['id'] for f in first + more]
        assert ids == sorted(set(ids)) and ids == [e['seq'] for e in _all(quiet)]
    finally:
        s.close()


# ── B8 expiry mid-stream ──

def test_a_stream_that_falls_behind_a_prune_gets_cursor_expired_and_closes(quiet, monkeypatch):
    _settle(quiet)
    hold, released = threading.Event(), threading.Event()
    real = sse.Streams._page

    def slow(self, cursor):
        if hold.is_set():
            released.wait(10)
        return real(self, cursor)
    monkeypatch.setattr(sse.Streams, '_page', slow)
    s = SSEClient(quiet.base_url, quiet.token)
    try:
        hold.set()
        _mission(quiet, 'a')
        _settle(quiet)
        quiet.core.db.writer.execute(retention.prune, {'now': '2999-01-01T00:00:00.000Z',
                                                       'keep_days': 1})
        released.set()
        f = s.frames(1)[0]
        assert f['event'] == 'cursor_expired' and f['data']['reason'] == 'pruned'
        assert s.wait_eof(2.0)
    finally:
        released.set()
        s.close()


# ── M5 shutdown with an open stream ──

def test_shutdown_sends_a_shutdown_frame_then_eof(archeus_home):
    tc = TempCore(archeus_home).start()
    s = SSEClient(tc.base_url, tc.token)
    stopper = threading.Thread(target=tc.stop)
    stopper.start()
    try:
        f = s.frames(1)
        assert f and f[0]['event'] == 'shutdown'
        assert s.wait_eof(5.0)
    finally:
        stopper.join(10)
        s.close()
