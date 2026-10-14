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
