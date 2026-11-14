"""The TUI's transport (p17-design-gate A3, §7, §10): Core's answer and its
refusal kept whole, loopback only, the token nowhere but its header, and the
event stream's open / lost / resync signals as the SPA's stream gives them."""

import os
import queue
import time

import pytest

from archeus.cli.tui import client as C, sync as S
from archeus.infra import paths
from v1.judge.http import TempCore, free_port


class _DripSocket:
    def __init__(self, chunks, clock):
        self.chunks, self.clock, self.timeouts = iter(chunks), clock, []

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def setsockopt(self, *args):
        pass

    def sendall(self, data):
        pass

    def close(self):
        pass

    def makefile(self, mode, buffering=-1):
        import io
        sock = self

        class Raw(io.RawIOBase):
            pending = b''

            def readable(self):
                return True

            def readinto(self, buffer):
                if not self.pending:
                    delay, self.pending = next(sock.chunks, (0, b''))
                    sock.clock[0] += delay
                size = min(len(self.pending), len(buffer))
                buffer[:size], self.pending = self.pending[:size], self.pending[size:]
                return size
        raw = Raw()
        return raw if buffering == 0 else io.BufferedReader(raw)


@pytest.mark.parametrize('part', ['headers', 'body', 'error', 'chunked'])
def test_get_deadline_bounds_dripping_headers_body_and_error_body(monkeypatch, part):
    clock = [0.0]
    if part == 'headers':
        chunks = [(0.04, bytes([b])) for b in b'HTTP/1.1 200 OK\r\n']
    else:
        status = b'404 Not Found' if part == 'error' else b'200 OK'
        framing = b'Transfer-Encoding: chunked' if part == 'chunked' else b'Content-Length: 4'
        chunks = [(0, b'HTTP/1.1 ' + status + b'\r\n' + framing + b'\r\n\r\n')]
        body = b'1\r\nn\r\n1\r\nu\r\n0\r\n\r\n' if part == 'chunked' else b'null'
        chunks += [(0.04, bytes([b])) for b in body]
    sock = _DripSocket(chunks, clock)
    monkeypatch.setattr(C.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(C.socket, 'create_connection', lambda *a, **k: sock)
    with pytest.raises((C.CoreError, TimeoutError)):
        C.Core(9001, 'tok').get('/x', timeout=0.1, deadline=0.1, clock=lambda: clock[0])
    assert clock[0] == pytest.approx(0.12)
    assert sock.timeouts == pytest.approx([0.1, 0.1, 0.06, 0.02] if part == 'headers'
                                         else [0.1, 0.1, 0.1, 0.06, 0.02])


def test_a_complete_body_received_at_deadline_is_rejected(monkeypatch):
    import io
    clock = [0.0]

    class Response(io.BytesIO):
        headers = {}

        def read(self):
            clock[0] = 0.1
            return b'null'
    monkeypatch.setattr(C.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(C.Core, '_open', lambda *a, **k: Response())
    with pytest.raises(TimeoutError, match='Core request deadline'):
        C.Core(9001, 'tok').get('/x', timeout=0.1, deadline=0.1, clock=lambda: clock[0])


@pytest.mark.parametrize('timeout', [0, -0.1])
def test_expired_get_never_connects(monkeypatch, timeout):
    monkeypatch.setattr(C.socket, 'create_connection', lambda *a, **k: pytest.fail('connected'))
    with pytest.raises(C.CoreError):
        C.Core(9001, 'tok').get('/x', timeout=timeout, deadline=timeout)


def test_expired_raw_read_never_touches_socket(monkeypatch):
    import io
    monkeypatch.setattr(C.time, 'monotonic', lambda: 1)
    raw = io.BytesIO(b'null')
    sock = _DripSocket([], [1])
    reader = C._DeadlineReader(raw, sock, 1)
    with pytest.raises(TimeoutError):
        reader.readinto(bytearray(4))
    assert raw.tell() == 0 and sock.timeouts == []


def test_a_raw_read_completing_after_deadline_is_rejected():
    clock = [0.0]
    sock = _DripSocket([(0.11, b'null')], clock)
    reader = C._DeadlineReader(sock.makefile('rb', buffering=0), sock, 0.1,
                               clock=lambda: clock[0])
    with pytest.raises(TimeoutError):
        reader.readinto(bytearray(4))
    assert sock.timeouts == [0.1]


def test_expired_connection_never_opens_socket(monkeypatch):
    monkeypatch.setattr(C.time, 'monotonic', lambda: 1)
    monkeypatch.setattr(C.socket, 'create_connection', lambda *a, **k: pytest.fail('connected'))
    with pytest.raises(TimeoutError):
        C._DeadlineConnection('127.0.0.1', deadline=1).connect()


def test_expired_socket_never_sends_request():
    sock = _DripSocket([], [1])
    wrapped = C._DeadlineSocket(sock, 1, lambda: 1)
    sock.sendall = lambda data: pytest.fail('sent expired request')
    with pytest.raises(TimeoutError):
        wrapped.sendall(b'GET /x HTTP/1.1\r\n\r\n')
    assert sock.timeouts == []


def test_a_get_without_a_deadline_keeps_the_per_read_timeout(monkeypatch):
    clock = [0.0]
    chunks = [(0, b'HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\n')]
    sock = _DripSocket(chunks + [(0.04, bytes([b])) for b in b'null'], clock)
    monkeypatch.setattr(C.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(C.socket, 'create_connection', lambda *a, **k: sock)
    assert C.Core(9001, 'tok').get('/x', timeout=0.1)[0] is None
    assert clock[0] == pytest.approx(0.16)


def test_get_preserves_supplied_absolute_deadline(monkeypatch):
    monkeypatch.setattr(C.Core, '_open', lambda *a, **k: pytest.fail('deadline was extended'))
    with pytest.raises(C.CoreError):
        C.Core(9001, 'tok').get('/x', timeout=10, deadline=1, clock=lambda: 1)


def test_a_complete_error_body_received_at_deadline_is_rejected():
    import io
    import urllib.error
    clock = [0.0]

    class Body(io.BytesIO):
        def read(self):
            clock[0] = 0.1
            return b'{"error":"not_found"}'
    error = urllib.error.HTTPError('http://127.0.0.1/x', 404, 'missing', {}, Body())
    with pytest.raises(TimeoutError):
        C._error(error, deadline=0.1, clock=lambda: clock[0])


@pytest.fixture
def core(archeus_home):
    tc = TempCore(archeus_home).start()
    yield tc
    tc.stop(kill=True)


def _drain(q, until, timeout=20):
    got, deadline = [], time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            got.append(q.get(timeout=0.2))
        except queue.Empty:
            continue
        if until(got):
            return got
    raise AssertionError('never happened; got %r' % got)


def test_a_refusal_keeps_cores_status_code_and_detail(core):
    c = C.Core(core.port, core.token)
    with pytest.raises(C.CoreError) as e:
        c.get('/v1/missions/msn_00000000000000000000000000')
    assert (e.value.status, e.value.code) == (404, 'not_found')
    with pytest.raises(C.CoreError) as e:
        c.post('/v1/missions', {'idempotency_key': 'k1'})         # no title, no objective
    assert (e.value.status, e.value.code) == (400, 'invalid_request')
    assert e.value.detail, 'the detail Core gave is kept'
    assert S.explain(e.value.refusal()).startswith('Invalid:')


def test_a_read_returns_cores_answer_and_the_event_head_it_was_read_at(core):
    data, seq = C.Core(core.port, core.token).get('/v1/missions')
    assert data['missions'] == []
    assert isinstance(seq, int)


def test_an_unreachable_core_is_a_network_refusal_with_nothing_of_the_token(archeus_home):
    token = 'tok_' + 'x' * 40
    with pytest.raises(C.CoreError) as e:
        C.Core(free_port(), token).get('/v1/missions')
    assert (e.value.status, e.value.code) == (0, 'network')
    assert token not in repr((str(e.value), e.value.detail, e.value.refusal()))


def test_a_wrong_token_is_refused_and_the_refusal_does_not_carry_it(core):
    token = 'tok_' + 'y' * 40
    with pytest.raises(C.CoreError) as e:
        C.Core(core.port, token).get('/v1/missions')
    assert e.value.status == 401
    assert token not in repr((str(e.value), e.value.detail, e.value.refusal()))


def test_the_client_only_ever_speaks_to_loopback():
    assert C.Core(7337, 't').base == 'http://127.0.0.1:7337'


def test_no_core_is_said_and_the_tui_starts_none(archeus_home):
    got, why = C.Core.local()
    assert (got, why) == (None, 'not_running')
    assert not os.path.exists(os.path.join(paths.run_dir(), 'core.json'))


def test_the_local_core_is_found_with_the_local_token(core):
    got, why = C.Core.local()
    assert why is None and got.base == 'http://127.0.0.1:%d' % core.port
    assert got.get('/v1/health')[0]['core']


def test_the_stream_opens_then_hands_on_frames_by_identity(core):
    q = queue.Queue()
    s = C.Stream(C.Core(core.port, core.token), q)
    s.start()
    try:
        _drain(q, lambda got: ('signal', 'stream_open') in got)
        core.client().create_mission(title='t', objective='o')
        got = _drain(q, lambda got: any(k == 'frame' and (f.get('data') or {}).get('subject', {})
                                        .get('kind') == 'mission' for k, f in got))
        frame = next(f for k, f in got if k == 'frame' and f.get('data'))
        assert set(frame['data']['subject']) >= {'kind', 'id'}
    finally:
        s.stop()


def test_a_restarted_core_is_reconnecting_then_a_resync(core):
    """T07 at the transport: the stream is lost, reopens on the new Core, and
    the connection machine turns that into a resync (everything re-read)."""
    q = queue.Queue()
    s = C.Stream(C.Core(core.port, core.token), q)
    s.start()
    try:
        _drain(q, lambda got: ('signal', 'stream_open') in got)
        core.restart()
        s.core = C.Core(core.port, core.token)          # a restart keeps the local token
        got = _drain(q, lambda got: ('signal', 'stream_lost') in got
                     and got.index(('signal', 'stream_lost')) < len(got) - 1
                     and ('signal', 'stream_open') in got[got.index(('signal', 'stream_lost')):],
                     timeout=40)
    finally:
        s.stop()
    state = S.initial(0)
    for kind, v in got:
        if kind == 'signal':
            state = S.next_state(state, v, 0)
    assert state['conn'] == 'resynced' and state['gen'] == 1


def test_an_expired_cursor_is_a_resync(core):
    c = C.Core(core.port, core.token)
    with pytest.raises(C.CoreError) as e:
        next(c.events(10 ** 9))                           # a cursor Core never issued
    assert e.value.status == 410

    class Once:
        calls = 0

        def events(self, last):
            Once.calls += 1
            if Once.calls == 1:
                raise C.CoreError(410, 'cursor_expired')
            s.stop()
            return iter(())
    q = queue.Queue()
    s = C.Stream(Once(), q)
    s.run()
    assert ('signal', 'resync') in list(q.queue)
