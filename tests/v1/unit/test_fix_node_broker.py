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


def test_a_closed_broker_revokes_its_grants_and_issues_no_more_listeners():
    b, _ = broker()
    issued(b)
    assert b.close() == 1 and b.transport.closed == ['ep1']
    with pytest.raises(B.BrokerUnavailable, match='closed'):
        b.issue(binding())
    assert len(b.transport.created) == 1 and b._grants == {}


def test_an_issue_in_flight_when_the_broker_closes_leaves_no_listener():
    class Closing(Transport):
        def create(self, name, principal):
            got = super().create(name, principal)
            b.close()
            return got

    b, _ = broker(transport=Closing())
    with pytest.raises(B.BrokerUnavailable, match='closed'):
        b.issue(binding())
    assert b.transport.closed == ['ep1'] and b._grants == {}


def test_revoke_all_alone_leaves_the_broker_open():
    b, _ = broker()
    issued(b)
    assert b.revoke_all() == 1
    issued(b)
    assert len(b._grants) == 1


def test_close_waits_for_an_issue_in_flight_and_leaves_no_listener():
    resolving, release = threading.Event(), threading.Event()

    def resolve(host, port):
        resolving.set()
        release.wait(5)
        return ['93.184.216.34']

    b, _ = broker()
    b._resolve = resolve
    errors = []
    issuer = threading.Thread(target=lambda: errors.append(_issue_error(b)))
    issuer.start()
    assert resolving.wait(5)
    closer = threading.Thread(target=b.close)
    closer.start()
    closer.join(0.3)
    returned_early = not closer.is_alive()
    release.set()
    issuer.join(5)
    closer.join(5)
    assert not returned_early, 'close returned while an issue was still resolving'
    assert isinstance(errors[0], B.BrokerClosed) and b._grants == {}
    assert b.transport.closed == []


def _issue_error(b):
    try:
        b.issue(binding())
    except Exception as error:
        return error
    return None


@pytest.mark.parametrize('phase', ['resolve', 'create', 'launch', 'launch_error'])
def test_close_deadline_revokes_even_a_stalled_issue(phase, caplog):
    entered, release = threading.Event(), threading.Event()
    b, _ = broker()
    issued(b)
    launched = set()
    launch_calls = []
    close = b.transport.close
    def closing(endpoint):
        launched.discard(endpoint)
        close(endpoint)
    b.transport.close = closing
    if phase == 'resolve':
        def resolve(host, port):
            entered.set()
            assert release.wait(5)
            return ['93.184.216.34']
        b._resolve = resolve
    elif phase == 'create':
        create = b.transport.create
        def stalled_create(name, principal):
            entered.set()
            assert release.wait(5)
            return create(name, principal)
        b.transport.create = stalled_create
        launch = b.transport.launch_bridge
        def recording_launch(*args):
            launch_calls.append(args)
            return launch(*args)
        b.transport.launch_bridge = recording_launch
    else:
        launch = b.transport.launch_bridge
        def stalled(endpoint, binding):
            entered.set()
            assert release.wait(5)
            if phase == 'launch_error':
                raise OSError('listener closed during launch')
            launched.add(endpoint)
            return launch(endpoint, binding)
        b.transport.launch_bridge = stalled
    errors = []
    issuer = threading.Thread(target=lambda: errors.append(_issue_error(b)), daemon=True)
    issuer.start()
    try:
        assert entered.wait(5)
        closer = threading.Thread(target=b.close, kwargs={'deadline': 0.0}, daemon=True)
        closer.start()
        closer.join(5)
        assert not closer.is_alive(), 'close waited past its deadline'
        assert b._closed and not b._grants and not b._pending
        created_before = list(b.transport.created)
        assert 'ep1' in b.transport.closed
        if phase in ('launch', 'launch_error'):
            assert 'ep2' in b.transport.closed
        assert 'broker drain timed out' in caplog.text
        with pytest.raises(B.BrokerClosed):
            b.issue(binding())
    finally:
        release.set()
        issuer.join(5)
    assert not issuer.is_alive() and isinstance(errors[0], B.BrokerClosed)
    assert not launched
    assert b._grants == {} and b._pending == {}
    if phase == 'create':
        assert launch_calls == []
    if phase == 'resolve':
        assert b.transport.created == created_before
    assert set(b.transport.closed) == set('ep%d' % (n + 1)
                                         for n in range(len(b.transport.created)))
