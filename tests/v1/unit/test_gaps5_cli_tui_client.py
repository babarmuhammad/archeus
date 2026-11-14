"""Deadline transport of archeus/cli/tui/client.py, unit level, with in-memory sockets and a fake clock."""

import io

import pytest

from archeus.cli.tui import client as C

PORT = 7337
TOKEN = 'tok_' + 'q' * 32


class _DripSocket:
    """Socket seam with receipts: every settimeout, sendall payload and close
    (of the socket and of the raw file its makefile hands out) is recorded.
    Each raw read pops the next (delay, bytes) chunk and advances the fake clock."""

    def __init__(self, chunks, clock):
        self.chunks, self.clock = iter(chunks), clock
        self.timeouts, self.sent = [], []
        self.closes = 0
        self.raw_closes = 0

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def setsockopt(self, *args):
        pass

    def sendall(self, data):
        self.sent.append(bytes(data))

    def close(self):
        self.closes += 1

    def makefile(self, mode, buffering=-1):
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

            def close(self):
                sock.raw_closes += 1
                return super().close()

        raw = Raw()
        return raw if buffering == 0 else io.BufferedReader(raw)


class _Headers:
    def __init__(self, **kw):
        self._h = {k.lower(): v for k, v in kw.items()}

    def get(self, name, default=None):
        return self._h.get(name.lower(), default)


class _Answer:
    """Scripted answer. read_clock=(clock_cell, value) moves the fake clock when
    the body is read, which is how a late-arriving body is scripted."""

    def __init__(self, body=b'null', headers=None, read_clock=None):
        self.body, self.headers = body, _Headers(**(headers or {}))
        self.read_clock = read_clock
        self.entered = self.exited = False

    def read(self):
        if self.read_clock is not None:
            self.read_clock[0][0] = self.read_clock[1]
        return self.body

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc):
        self.exited = True
        return False


class _RecordingOpener:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def open(self, req, timeout=None):
        self.calls.append({'method': req.method, 'url': req.full_url,
                           'deadline': getattr(req, 'deadline', 'unset'),
                           'clock': getattr(req, 'clock', 'unset'),
                           'timeout': timeout})
        answer = self.answers.pop(0) if self.answers else _Answer()
        if isinstance(answer, BaseException):
            raise answer
        return answer


class _BoomRaw(io.RawIOBase):
    def __init__(self):
        self.close_runs = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        return 0

    def close(self):
        self.close_runs += 1
        raise OSError('raw close failed')


def _core():
    return C.Core(PORT, TOKEN)


def _fake_open(monkeypatch, *answers):
    calls, pending = [], list(answers)

    def fake_open(self, method, path, **kw):
        calls.append(dict(kw, method=method, path=path))
        return pending.pop(0) if pending else _Answer()

    monkeypatch.setattr(C.Core, '_open', fake_open)
    return calls


def _wire(seq=None):
    lines = [b'HTTP/1.1 200 OK', b'Content-Length: 4']
    if seq is not None:
        lines.append(b'X-Archeus-Seq: ' + seq)
    return b'\r\n'.join(lines) + b'\r\n\r\nnull'


def test_an_expired_deadline_refuses_before_any_request_is_opened(monkeypatch):
    calls = _fake_open(monkeypatch)
    with pytest.raises(C.CoreError) as e:
        _core().get('/v1/x', timeout=10, deadline=0.5, clock=lambda: 1.0)
    assert calls == [], 'the request was opened despite an already-past deadline'
    assert (e.value.status, e.value.code, e.value.detail) == (0, 'network',
                                                              {'why': 'TimeoutError'})
    assert TOKEN not in repr((str(e.value), e.value.detail, e.value.refusal()))


def test_a_redirect_on_the_deadline_path_is_refused_and_no_token_walks_to_the_location(
        monkeypatch):
    # The deadline opener must keep _NoRedirect: urllib would otherwise reconnect
    # to Location and send the bearer token a second time.
    wire = (b'HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:9999/stolen\r\n'
            b'Server: core\r\n\r\n')
    sock = _DripSocket([(0, wire), (0, b'')], [0.0])
    conns = []

    def fake_create(*args, **kwargs):
        conns.append(args)
        return sock

    monkeypatch.setattr(C.socket, 'create_connection', fake_create)
    with pytest.raises(C.CoreError) as e:
        _core().get('/v1/x', timeout=5.0, deadline=5.0, clock=lambda: 0.0)
    assert (e.value.status, e.value.code, e.value.detail) == (302, 'http_302', {})
    assert len(conns) == 1, 'the Location was followed (a second connection was made)'
    assert len(sock.sent) == 1 and sock.sent[0].split(b'\r\n')[0] == b'GET /v1/x HTTP/1.1'
    joined = b''.join(sock.sent)
    assert b'/stolen' not in joined and b':9999' not in joined, 'the token walked to the Location'
    assert ('Bearer ' + TOKEN).encode() in sock.sent[0], 'the one request carried the token'


def test_a_deadlined_request_uses_the_deadline_opener_and_only_that_one(monkeypatch):
    plain, deadline_opener = _RecordingOpener(), _RecordingOpener(_Answer())
    monkeypatch.setattr(C, '_OPENER', plain)
    monkeypatch.setattr(C, '_DEADLINE_OPENER', deadline_opener)
    assert _core().get('/x', timeout=1.25, deadline=5.0, clock=lambda: 0.0) == (None, None)
    assert plain.calls == [], 'a deadlined read went to the plain opener'
    assert [c['deadline'] for c in deadline_opener.calls] == [1.25], 'not the earlier bound'
    assert deadline_opener.calls[0]['clock']() == 0.0
    assert deadline_opener.calls[0]['timeout'] == 1.25
    assert _core().get('/y') == (None, None)
    assert [c['deadline'] for c in plain.calls] == [None]
    assert len(deadline_opener.calls) == 1, 'a deadline-less read touched the deadline opener'


def test_the_earlier_of_the_deadline_and_the_clock_plus_timeout_bounds_the_request(
        monkeypatch):
    calls = _fake_open(monkeypatch, _Answer())
    assert _core().get('/x', timeout=0.5, deadline=5.0, clock=lambda: 0.0) == (None, None)
    assert len(calls) == 1
    assert calls[0]['deadline'] == 0.5, 'the caller deadline was handed down, not the cap'
    assert calls[0]['timeout'] == 0.5, 'the caller timeout no longer reaches the transport'


def test_valid_json_that_arrives_after_the_capped_deadline_is_still_refused(monkeypatch):
    clock = [0.0]
    answer = _Answer(body=b'{"ok": true}', read_clock=(clock, 0.6))   # after the cap, before 5.0
    calls = _fake_open(monkeypatch, answer)
    with pytest.raises(TimeoutError, match='Core request deadline'):
        _core().get('/x', timeout=0.5, deadline=5.0, clock=lambda: clock[0])
    assert calls[0]['deadline'] == 0.5, 'the transport was not bounded by the cap either'
    assert answer.exited is True, 'the refused answer was left open'


def test_a_read_that_finishes_exactly_at_the_deadline_is_refused():
    # 0.25 is exact in binary, so the >= comparison is exact.
    clock = [0.0]
    sock = _DripSocket([(0.25, b'null')], clock)
    reader = C._DeadlineReader(sock.makefile('rb', buffering=0), sock, 0.25,
                               clock=lambda: clock[0])
    with pytest.raises(TimeoutError, match='Core request deadline'):
        reader.readinto(bytearray(4))
    assert clock[0] == 0.25, 'the read did not actually complete at the deadline'
    assert sock.timeouts == [0.25], 'the raw read was not armed with the remaining time'


def test_sendall_arms_the_socket_with_the_remaining_time_and_never_sends_once_it_is_up():
    clock = [0.0]
    sock = _DripSocket([], clock)
    wrapped = C._DeadlineSocket(sock, 1.0, lambda: clock[0])
    wrapped.sendall(b'REQ-1')
    assert (sock.timeouts, sock.sent) == ([1.0], [b'REQ-1'])
    clock[0] = 0.5
    wrapped.sendall(b'REQ-2')
    assert (sock.timeouts, sock.sent) == ([1.0, 0.5], [b'REQ-1', b'REQ-2'])
    clock[0] = 2.0                                    # left is negative, not just zero
    with pytest.raises(TimeoutError, match='Core request deadline'):
        wrapped.sendall(b'REQ-3')
    assert (sock.timeouts, sock.sent) == ([1.0, 0.5], [b'REQ-1', b'REQ-2']), \
        'an expired sendall armed or wrote anyway'


def test_the_deadline_reader_gives_the_raw_reader_back_even_when_closing_it_fails():
    raw = io.BytesIO(b'null')
    reader = C._DeadlineReader(raw, _DripSocket([], [0.0]), 1e9, clock=lambda: 0.0)
    reader.close()
    assert raw.closed is True and reader.closed is True
    boom = _BoomRaw()
    reader2 = C._DeadlineReader(boom, _DripSocket([], [0.0]), 1e9, clock=lambda: 0.0)
    with pytest.raises(OSError, match='raw close failed'):
        reader2.close()
    assert boom.close_runs == 1
    assert reader2.closed is True, 'the finally arm did not close the reader'


def test_closing_the_response_closes_the_real_socket_through_the_wrapper(monkeypatch):
    sock = _DripSocket([(0, _wire(b'9'))], [0.0])
    monkeypatch.setattr(C.socket, 'create_connection', lambda *a, **k: sock)
    assert _core().get('/v1/x', timeout=5.0, deadline=5.0, clock=lambda: 0.0) == (None, 9)
    assert (sock.closes, sock.raw_closes) == (1, 1)


@pytest.mark.parametrize('seq, want', [(None, None), (b'', None), (b'not-a-number', C.CoreError)],
                         ids=['head-absent', 'head-empty', 'head-not-a-number'])
def test_the_event_head_on_the_deadline_transport_is_a_number_or_nothing_or_broken(monkeypatch,
                                                                                    seq, want):
    # An absent head must stay None, not 0: a fabricated 0 would make the
    # connection machine believe a read that never had a head.
    sock = _DripSocket([(0, _wire(seq))], [0.0])
    monkeypatch.setattr(C.socket, 'create_connection', lambda *a, **k: sock)
    if want is C.CoreError:
        with pytest.raises(C.CoreError) as e:
            _core().get('/v1/x', timeout=5.0, deadline=5.0, clock=lambda: 0.0)
        assert (e.value.status, e.value.code, e.value.detail) == (0, 'network',
                                                                  {'why': 'ValueError'})
        assert sock.closes == 1, 'the broken answer was left open'
    else:
        data, head = _core().get('/v1/x', timeout=5.0, deadline=5.0, clock=lambda: 0.0)
        assert data is None and head is None and type(head) is type(want)
        assert len(sock.sent) == 1
