"""The judge's two clocks say which one fired (T-076): a flake that times out
must identify itself in the failure message, not only in its timing."""

import inspect
import re
import socket
import threading
import urllib.error

import pytest

from v1.judge import http, support


class _Clock:
    def __init__(self, step):
        self.now, self.step = 1000.0, step

    def __call__(self):
        self.now += self.step
        return self.now


def test_a_wait_for_timeout_names_the_state_the_elapsed_time_and_the_last_read(monkeypatch):
    monkeypatch.setattr(support.time, 'monotonic', _Clock(4.0))
    monkeypatch.setattr(support.time, 'sleep', lambda s: None)
    monkeypatch.setattr(support, 'idle', None)

    def mission_planned():
        return []
    with pytest.raises(AssertionError) as err:
        support.wait_for(mission_planned, timeout=10.0)
    msg = str(err.value)
    assert 'mission_planned' in msg
    assert 'wait_for deadline' in msg
    assert 'timed out after 10s' in msg
    assert re.search(r'\(wait_for deadline, \d+\.\ds elapsed;', msg)
    assert 'last read []' in msg


def test_an_idle_core_names_the_elapsed_time_and_the_last_read(monkeypatch):
    monkeypatch.setattr(support.time, 'monotonic', _Clock(0.5))
    monkeypatch.setattr(support, 'idle', lambda: True)

    def knowledge_built():
        return None
    with pytest.raises(NotImplementedError) as err:
        support.wait_for(knowledge_built)
    msg = str(err.value)
    assert 'knowledge_built' in msg
    assert re.search(r'Core idle after \d+\.\ds;', msg)
    assert 'last read None' in msg


def test_a_stalled_request_names_the_route_the_socket_timeout_and_the_elapsed_time():
    srv = socket.socket()
    srv.bind(('127.0.0.1', 0))
    srv.listen(4)
    accepted = []

    def hold():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            accepted.append(c)          # held open, never answered
    t = threading.Thread(target=hold, daemon=True)
    t.start()
    try:
        base = 'http://127.0.0.1:%d' % srv.getsockname()[1]
        with pytest.raises(TimeoutError) as err:
            http.request(base, 'POST', '/v1/missions', body={}, timeout=0.3)
    finally:
        srv.close()
        for c in accepted:
            c.close()
    msg = str(err.value)
    assert msg.startswith('POST /v1/missions:')
    assert 'within the 0.3s socket timeout' in msg
    assert re.search(r'\(\d+\.\ds elapsed\)$', msg)
    assert len(accepted) == 1           # one attempt: no retry


def test_a_refused_connection_is_not_reported_as_a_timeout():
    port = http.free_port()
    with pytest.raises(urllib.error.URLError) as err:
        # Windows retries a refused loopback SYN for about 2 s before giving up
        http.request('http://127.0.0.1:%d' % port, 'GET', '/v1/health', timeout=10)
    assert not isinstance(err.value, TimeoutError)


def test_the_two_clocks_keep_their_values():
    assert inspect.signature(http.request).parameters['timeout'].default == 15
    assert inspect.signature(support.wait_for).parameters['timeout'].default == 30.0


class _Ok:
    status, headers = 200, {}

    def read(self):
        return b'{}'

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_a_connect_this_machine_has_no_port_for_is_tried_again(monkeypatch):
    """T-115e: suites side by side run the machine out of local ports; that
    connect sent nothing, so it is tried again. Any other failure is not."""
    import errno
    calls = []

    def busy_twice(req, timeout):
        calls.append(req)
        if len(calls) < 3:
            raise urllib.error.URLError(OSError(errno.EADDRINUSE, 'in use'))
        return _Ok()
    monkeypatch.setattr(http, '_RETRY_S', (0, 0, 0))
    monkeypatch.setattr(http.urllib.request, 'urlopen', busy_twice)
    assert http.request('http://127.0.0.1:1', 'GET', '/v1/health').status == 200
    assert len(calls) == 3

    def refused(req, timeout):
        calls.append(req)
        raise urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED, 'refused'))
    calls.clear()
    monkeypatch.setattr(http.urllib.request, 'urlopen', refused)
    with pytest.raises(urllib.error.URLError):
        http.request('http://127.0.0.1:1', 'GET', '/v1/health')
    assert len(calls) == 1


def test_a_core_whose_chosen_port_is_taken_binds_another(archeus_home, monkeypatch):
    """T-115e: the port the harness chose was taken before Core bound it; the
    harness chooses again, but never moves a port the test named."""
    squat = socket.socket()
    squat.bind(('127.0.0.1', 0))
    squat.listen()
    taken = squat.getsockname()[1]
    picks = iter([taken, http.free_port()])
    monkeypatch.setattr(http, 'free_port', lambda: next(picks))
    tc = http.TempCore(archeus_home)
    try:
        tc.start()
        assert tc.port != taken and tc.http('GET', '/v1/health').status == 200
    finally:
        tc.stop()
        with pytest.raises(OSError):
            http.TempCore(archeus_home, port=taken).start()
        squat.close()
