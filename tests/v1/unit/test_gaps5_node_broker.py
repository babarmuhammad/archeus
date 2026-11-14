import logging
import threading
import time

import pytest

from archeus.core.domain import ids
from archeus.node import broker as B


class Transport:
    def __init__(self):
        self.created, self.closed, self.ops, self.launches = [], [], [], []

    def create(self, name, principal):
        self.created.append((name, principal))
        return 'ep%d' % len(self.created)

    def cancel(self):
        self.ops.append('cancel')

    def launch_bridge(self, endpoint, binding):
        self.launches.append(endpoint)
        return 4321

    def close(self, endpoint):
        self.closed.append(endpoint)
        self.ops.append(endpoint)


def binding(**kw):
    kw = dict(dict(core_instance='core1', execution_id=ids.new_id('execution'), process_seq=1,
                   principal='archeus.x', route_decision_id='rte_1', account_id='acc_1',
                   harness_id='claude_code', model='claude-x',
                   upstream=B.Upstream('https://api.example.com'),
                   limits=B.BrokerLimits(max_requests=3)), **kw)
    return B.BrokerBinding(**kw)


def broker(transport=None):
    return B.Broker(core_instance='core1', live=lambda bd, d: True,
                    credentials=lambda bd: {}, limits=B.BrokerLimits(max_requests=3),
                    upstream_of=lambda a: B.Upstream('https://api.example.com'),
                    transport=transport or Transport(),
                    resolve=lambda host, port: ['93.184.216.34'])


def issued(b, **kw):
    bd = binding(**kw)
    token, d, endpoint, port = b.issue(bd)
    return bd, token, d


def _capture(b, bd, errors):
    try:
        b.issue(bd)
    except BaseException as err:
        errors.append(err)


def _start_issue(b, bd):
    errors = []
    thread = threading.Thread(target=lambda: _capture(b, bd, errors), daemon=True)
    thread.start()
    return errors, thread


def _wait_until(cond, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not cond():
        time.sleep(0.01)
    return bool(cond())


def test_a_closed_broker_refuses_with_exactly_broker_closed_without_registering_anything():
    b = broker()
    issued(b)
    b.close()
    t = b.transport
    before = (list(t.created), list(t.closed), list(t.ops))
    with pytest.raises(B.BrokerClosed) as raised:
        b.issue(binding())
    assert type(raised.value) is B.BrokerClosed
    assert raised.value.__cause__ is None
    assert (t.created, t.closed, t.ops) == before
    assert b._grants == {} and b._pending == {} and b._issuing == []


def test_a_close_between_the_pre_create_recheck_and_create_leaves_no_endpoint(monkeypatch):
    b = broker()
    t = b.transport
    entered, release = threading.Event(), threading.Event()
    real = B.pipe_name

    def pausing(bd, nonce):
        entered.set()
        assert release.wait(5)
        return real(bd, nonce)

    monkeypatch.setattr(B, 'pipe_name', pausing)
    errors, issuer = _start_issue(b, binding())
    try:
        assert entered.wait(5)
        b.close(deadline=0.0)
        assert t.created == []
    finally:
        release.set()
        issuer.join(5)
    assert not issuer.is_alive()
    assert set(t.closed) == {'ep%d' % (i + 1) for i in range(len(t.created))}
    assert t.launches == []
    assert type(errors[0]) is B.BrokerClosed
    assert b._grants == {} and b._pending == {} and b._issuing == []


def test_a_cancelled_transport_refusal_of_create_stays_the_very_same_broker_closed():
    boom = B.BrokerClosed('the transport is cancelled')

    class Cancelled(Transport):
        def create(self, name, principal):
            super().create(name, principal)
            raise boom

    b = broker(transport=Cancelled())
    with pytest.raises(B.BrokerClosed) as raised:
        b.issue(binding())
    assert raised.value is boom
    assert raised.value.__cause__ is None
    assert b._closed is False
    assert b.transport.closed == []
    assert b._grants == {} and b._pending == {} and b._issuing == []


def test_a_close_that_runs_after_launch_returns_installs_no_grant_and_closes_endpoints():
    b = broker()
    t = b.transport
    issued(b)
    real_launch = t.launch_bridge
    done, revoked = [], []

    def launch_then_close(endpoint, bd):
        port = real_launch(endpoint, bd)
        done.append((endpoint, port))
        revoked.append(b.close())
        return port

    t.launch_bridge = launch_then_close
    other = binding(execution_id=ids.new_id('execution'))
    with pytest.raises(B.BrokerClosed) as raised:
        b.issue(other)
    assert type(raised.value) is B.BrokerClosed
    assert done == [('ep2', 4321)]
    assert revoked == [1]
    assert b._grants == {}
    assert b._pending == {} and b._issuing == []
    assert set(t.closed) == {'ep1', 'ep2'}


def test_a_superseded_generation_has_its_endpoint_closed_when_the_new_grant_lands():
    class Racing(Transport):
        def __init__(self):
            super().__init__()
            self.inner = None

        def create(self, name, principal):
            endpoint = super().create(name, principal)
            if self.inner is not None:
                inner, self.inner = self.inner, None
                inner()
            return endpoint

    b = broker(transport=Racing())
    t = b.transport
    bd = binding()

    def second():
        issued(b, execution_id=bd.execution_id, process_seq=2)

    t.inner = second
    token, d, endpoint, port = b.issue(bd)
    assert endpoint == 'ep1'
    assert [g['endpoint'] for g in b._grants.values()] == ['ep1']
    assert t.closed == ['ep2']
    assert b._pending == {} and b._issuing == []


def test_a_second_close_reopens_nothing(caplog):
    b = broker()
    t = b.transport
    issued(b)
    assert b.close() == 1
    settled = (list(t.closed), list(t.ops), len(t.created))
    caplog.set_level(logging.WARNING, logger='archeus.node.broker')
    caplog.clear()
    assert b.close() == 0
    assert (t.closed, t.ops[:len(settled[1])], len(t.created)) == settled
    assert b._grants == {} and b._pending == {} and b._issuing == []
    assert 'drain timed out' not in caplog.text
    with pytest.raises(B.BrokerClosed):
        b.issue(binding())


def test_close_cancels_first_and_drains_every_pending_endpoint_not_just_the_first(caplog):
    b = broker()
    t = b.transport
    issued(b)
    release = threading.Event()
    real_launch = t.launch_bridge

    def stalled(endpoint, bd):
        t.launches.append(endpoint)
        assert release.wait(5)
        return real_launch(endpoint, bd)

    t.launch_bridge = stalled
    first, first_thread = _start_issue(b, binding())
    second, second_thread = _start_issue(b, binding(execution_id=ids.new_id('execution')))
    try:
        assert _wait_until(lambda: len(b._pending) == 2)
        b.close(deadline=0.0)
    finally:
        release.set()
        first_thread.join(5)
        second_thread.join(5)
    assert t.ops[0] == 'cancel'
    assert set(t.closed) == {'ep1', 'ep2', 'ep3'}
    assert not first_thread.is_alive() and not second_thread.is_alive()
    assert 'broker drain timed out' in caplog.text
    assert [type(e) for e in (first[0], second[0])] == [B.BrokerClosed, B.BrokerClosed]
    assert first[0].__cause__ is None and second[0].__cause__ is None
    assert b._grants == {} and b._pending == {} and b._issuing == []


def test_close_without_deadline_waits_for_a_launch_blocked_issue_and_logs_no_warning(caplog, monkeypatch):
    b = broker()
    t = b.transport
    entered, release = threading.Event(), threading.Event()
    real_launch = t.launch_bridge

    def stalled(endpoint, bd):
        t.launches.append(endpoint)
        entered.set()
        assert release.wait(5)
        return real_launch(endpoint, bd)

    t.launch_bridge = stalled
    waiting = threading.Event()
    real_wait = b._drained.wait_for

    def wait_for(predicate, timeout=None):
        assert timeout is None and not predicate()
        waiting.set()
        return real_wait(predicate, timeout)

    monkeypatch.setattr(b._drained, 'wait_for', wait_for)
    errors, issuer = _start_issue(b, binding())
    closer = None
    try:
        assert entered.wait(5)
        closer = threading.Thread(target=b.close, daemon=True)
        closer.start()
        assert waiting.wait(5)
        assert closer.is_alive()
        release.set()
        closer.join(5)
        issuer.join(5)
    finally:
        release.set()
        if closer is not None:
            closer.join(5)
        issuer.join(5)
    assert not closer.is_alive() and not issuer.is_alive()
    assert type(errors[0]) is B.BrokerClosed
    assert errors[0].__cause__ is None
    assert b._grants == {} and b._pending == {} and b._issuing == []
    assert t.closed == ['ep1']
    assert 'drain timed out' not in caplog.text
    with pytest.raises(B.BrokerClosed):
        b.issue(binding())


def test_a_launch_failure_while_open_propagates_the_original_os_error_unchanged():
    boom = OSError('the listener died during launch')

    class Failing(Transport):
        def launch_bridge(self, endpoint, bd):
            self.launches.append(endpoint)
            raise boom

    b = broker(transport=Failing())
    with pytest.raises(OSError) as raised:
        b.issue(binding())
    assert raised.value is boom
    assert raised.value.__cause__ is None
    assert b.transport.closed == ['ep1']
    assert b.transport.launches == ['ep1']
    assert b._grants == {} and b._pending == {} and b._issuing == []
    assert b._closed is False


def test_a_keyboard_interrupt_during_launch_after_close_is_reraised_and_drain_still_completes(caplog):
    boom = KeyboardInterrupt()
    b = broker()
    t = b.transport
    entered, release = threading.Event(), threading.Event()

    def stalled(endpoint, bd):
        t.launches.append(endpoint)
        entered.set()
        assert release.wait(5)
        raise boom

    t.launch_bridge = stalled
    errors, issuer = _start_issue(b, binding())
    try:
        assert entered.wait(5)
        b.close(deadline=0.0)
    finally:
        release.set()
        issuer.join(5)
    assert not issuer.is_alive()
    assert errors == [boom]
    assert b._pending == {} and b._grants == {}
    assert set(t.closed) == {'ep1'}
    assert b._issuing == []
    caplog.set_level(logging.WARNING, logger='archeus.node.broker')
    caplog.clear()
    closer = threading.Thread(target=b.close, daemon=True)
    closer.start()
    closer.join(5)
    assert not closer.is_alive(), 'the drain notification never reached a later close'
    assert 'drain timed out' not in caplog.text
