"""Leftover defects of `archeus/api/server.py`: an OSError from the e-stop or
re-arm path was swallowed with no answer, and a connection that stalled while
sending its request held a worker for ever."""

import logging
import socket
import time

import pytest

from archeus.api import server
from archeus.node.local import LocalNode
from v1.judge.http import SSEClient, TempCore


@pytest.fixture
def core(archeus_home):
    c = TempCore(archeus_home).start()
    yield c
    c.stop()


@pytest.mark.parametrize('path, hook', [('/v1/estop', 'engage_estop'),
                                        ('/v1/rearm', 'clear_estop')])
def test_an_oserror_in_the_estop_or_rearm_path_is_an_error_answer_and_a_log_line(
        core, monkeypatch, caplog, path, hook):
    def broken(*a, **k):
        raise PermissionError('the sentinel cannot be written')
    monkeypatch.setattr(LocalNode, hook, staticmethod(broken))
    with caplog.at_level(logging.ERROR, logger='archeus.core'):
        r = core.http('POST', path, body={'idempotency_key': 'k-fix-p'})
    assert (r.status, r.json()['error']) == (500, 'internal')
    assert any('internal error' in m for m in caplog.messages)


def _dropped(core, sent, wait=3.0):
    """True once the server has closed a connection that stalled after *sent*."""
    s = socket.create_connection(('127.0.0.1', core.port), timeout=wait)
    try:
        s.sendall(sent)
        try:
            return s.recv(1024) == b''
        except socket.timeout:
            return False
    finally:
        s.close()


def test_a_client_that_stalls_in_the_request_head_is_dropped(core, monkeypatch):
    monkeypatch.setattr(server.Handler, 'timeout', 0.3)
    assert _dropped(core, b'GET /v1/health HTT')


def test_a_client_that_stalls_in_the_body_is_dropped_unanswered(core, monkeypatch):
    monkeypatch.setattr(server.Handler, 'timeout', 0.3)
    head = ('POST /v1/missions HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nContent-Length: 100\r\n'
            '\r\n{"a":' % core.port).encode()
    assert _dropped(core, head)


def test_an_event_stream_outlives_the_head_timeout(core, monkeypatch):
    monkeypatch.setattr(server.Handler, 'timeout', 0.3)
    core.core.api.sse.heartbeat_s = 0.1
    s = SSEClient(core.base_url, core.token)
    try:
        time.sleep(1.0)
        assert s.next(timeout=2.0) == {'comment': 'hb'} and not s.eof
    finally:
        s.close()


def test_the_handler_reads_a_request_under_one_named_timeout():
    assert server.Handler.timeout == server.REQUEST_TIMEOUT_S == 30.0
