"""Leftover defects of `archeus/api/server.py`: an OSError from the e-stop or
re-arm path was swallowed with no answer, and a connection that stalled while
sending its request held a worker for ever."""

import logging

import pytest

from archeus.node.local import LocalNode
from v1.judge.http import TempCore


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
