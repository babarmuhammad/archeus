"""Regression tests for hostile-audit findings on archeus/node/broker.py."""

import io
import threading

import pytest

from archeus.node import broker as B

from .test_provider_broker import Resp, Transport, binding, broker, issued, request, serve


def test_a_revoked_grant_stops_relaying_a_stream_even_while_core_still_calls_it_live():
    box = {}

    class Revoking(Resp):
        def read1(self, n):
            if self._c and len(self._c) == 3:
                box['b'].revoke(box['bd'].execution_id)
            return super().read1(n)

    b, _ = broker(send=lambda *a: Revoking(chunks=[b'one', b'two', b'three']))
    box['b'] = b
    bd, token, _ = issued(b)
    box['bd'] = bd
    out, _ = serve(b, request(token=token))
    assert out.endswith(b'one')


def test_two_concurrent_issues_for_one_execution_leave_one_live_grant():
    class Racing(Transport):
        racing = True

        def create(self, name, principal):
            if self.racing:
                self.racing = False
                b.issue(binding(execution_id=bd.execution_id, process_seq=2))
            return super().create(name, principal)

    b, _ = broker(transport=Racing())
    bd = binding()
    b.issue(bd)
    assert sum(1 for g in b._grants.values()
               if g['binding'].execution_id == bd.execution_id) == 1



class _Slow(io.BytesIO):
    """A peer that takes *step* seconds of the fake clock for every read."""

    def __init__(self, data, now, step):
        super().__init__(data)
        self._now, self._step = now, step

    def readline(self, n=-1):
        self._now[0] += self._step
        return super().readline(n)

    def read(self, n=-1):
        self._now[0] += self._step
        return super().read(n)


def _slow_serve(step):
    now = [0.0]
    b, calls = broker(clock=lambda: now[0])
    _bd, token, _d = issued(b)
    out = []
    row = b.serve(_Slow(request(token=token).getvalue(), now, step), out.append, 'archeus.x')
    return b, calls, row, b''.join(out)


@pytest.mark.parametrize('step', [11.0, 31.0])
def test_a_peer_that_takes_too_long_to_send_its_request_is_cut_and_holds_no_slot(step):
    b, calls, row, out = _slow_serve(step)
    assert row['status'] == 408 and out.startswith(b'HTTP/1.1 408') and calls == []
    assert b._in_flight == 0 and all(g['active'] == 0 for g in b._grants.values())


def test_a_peer_inside_the_read_deadline_is_served():
    _b, calls, row, _out = _slow_serve(1.0)
    assert row['status'] == 200 and len(calls) == 1


def test_a_resolver_that_never_answers_is_refused_as_not_resolving(monkeypatch):
    monkeypatch.setattr(B, 'RESOLVE_TIMEOUT_S', 0.05)
    release = threading.Event()
    try:
        with pytest.raises(B.Refused) as r:
            B.check_destination(B.Upstream('https://api.example.com'),
                                lambda host, port: release.wait() or ['93.184.216.34'])
    finally:
        release.set()
    assert r.value.status == 502
