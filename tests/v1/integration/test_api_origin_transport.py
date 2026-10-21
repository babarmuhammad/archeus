"""PV20-10 synthetic HTTP transport evidence; no native attestation."""
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from archeus.api import origin, routes
from archeus.infra.eventlog import outbox
from v1.judge.http import TUNNEL, SSEClient, request
from v1.judge.support import wait_for

pytestmark = pytest.mark.core(remote_hosts=(TUNNEL,))


class Backend:
    def __init__(self, kind=origin.OriginClass.USER, path=origin.PathClass.DIRECT_LOCAL):
        self.kind, self.path = kind, path
        self.contexts, self.released = [], []
        self.bad = None

    def attest(self, context):
        self.contexts.append(context)
        if self.bad == 'exception':
            raise TimeoutError()
        if self.bad == 'malformed':
            return {'origin': 'user'}
        evidence = origin.OriginEvidence(
            origin=self.kind, path=self.path, identity='fixture', process_binding=object(),
            accept_generation=context.accept_generation, reason='fixture')
        return replace(evidence, accept_generation='stale') if self.bad == 'stale' else evidence

    def valid(self, context, evidence):
        return self.bad != 'expired'

    def release(self, context, evidence):
        self.released.append(context)


def enable(tc, backend):
    tc.core.api.origin_backend = backend
    tc.core.api.origin_registry = SimpleNamespace(approved=lambda context, evidence: True)
    tc.core.api.origin_enforcement_enabled = True


def snapshot(tc):
    with tc.core.db.read() as conn:
        return (outbox.head(conn), conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0],
                dict(tc.core.api.seen))


@pytest.mark.parametrize('kind', list(origin.OriginClass))
@pytest.mark.parametrize('path', list(origin.PathClass))
def test_valid_local_token_cannot_bypass_origin(tc, kind, path):
    backend = Backend(kind, path)
    enable(tc, backend)
    before = snapshot(tc)
    r = tc.http('GET', '/v1/health', headers={'Forwarded': 'for=127.0.0.1',
                                           'X-Forwarded-Host': TUNNEL})
    allowed = kind == origin.OriginClass.USER and path == origin.PathClass.DIRECT_LOCAL
    assert r.status == (200 if allowed else 403)
    if not allowed:
        assert snapshot(tc) == before
    wait_for(lambda: len(backend.released) == 1)
    context = backend.contexts[0]
    assert context.socket is not None and context.remote_endpoint[0] == '127.0.0.1'
    assert context.accept_generation


@pytest.mark.parametrize('bad', ['exception', 'malformed', 'stale', 'expired'])
def test_bad_evidence_refuses_before_credential_lookup(tc, bad, monkeypatch):
    backend = Backend()
    backend.bad = bad
    enable(tc, backend)
    before = snapshot(tc)

    def forbidden(*args):
        pytest.fail('credential lookup before origin gate')

    monkeypatch.setattr(tc.core.api, 'authenticate', forbidden)
    assert tc.http('GET', '/v1/health').status == 403
    assert snapshot(tc) == before


def test_native_user_and_direct_path_claim_cannot_replace_registry(tc):
    enable(tc, Backend())
    tc.core.api.origin_registry = origin.UnapprovedRegistry()
    before = snapshot(tc)
    assert tc.http('GET', '/v1/health').status == 403
    assert snapshot(tc) == before


def test_connections_never_share_generation_or_evidence(tc):
    backend = Backend()
    enable(tc, backend)
    assert tc.http('GET', '/v1/health').status == 200
    assert tc.http('GET', '/v1/health').status == 200
    wait_for(lambda: len(backend.released) == 2)
    first, second = backend.contexts
    assert first.accept_generation != second.accept_generation
    assert first.socket is not second.socket


def test_Q162_bootstrap_refusal_consumes_no_code(tc):
    launch = tc.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    pair = tc.http('POST', '/v1/devices/pair/start', body={}).json()['code']
    backend = Backend(path=origin.PathClass.DEPUTY)
    enable(tc, backend)
    before = snapshot(tc)
    for kind, code in [('launch', launch), ('pair', pair)]:
        r = request(tc.base_url, 'POST', '/v1/devices/' + kind + '/redeem',
                    body={'code': code, 'platform': 'web'})
        assert r.status == 403
    assert snapshot(tc) == before
    backend.path = origin.PathClass.DIRECT_LOCAL
    for kind, code in [('launch', launch), ('pair', pair)]:
        assert request(tc.base_url, 'POST', '/v1/devices/' + kind + '/redeem',
                       body={'code': code, 'platform': 'web'}).status == 200


def test_Q163_tunnel_requires_paired_credential_and_retains_scope(tc):
    code = tc.http('POST', '/v1/devices/pair/start', body={'scopes': ['observe']}).json()['code']
    paired = request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                     body={'code': code, 'platform': 'web'}).json()['token']
    enable(tc, Backend(path=origin.PathClass.REGISTERED_TUNNEL))
    before = snapshot(tc)
    assert tc.http('GET', '/v1/health', headers={'Host': TUNNEL}).status == 403
    assert snapshot(tc) == before
    assert tc.http('GET', '/v1/health', token=paired, headers={'Host': TUNNEL}).status == 200
    r = tc.http('POST', '/v1/missions', token=paired, headers={'Host': TUNNEL}, body={})
    assert (r.status, r.json()['error']) == (403, 'scope_required')
    assert tc.http('GET', '/v1/health', token=paired).status == 403


def test_enabled_missing_backend_is_closed_disabled_behavior_unchanged(tc):
    assert tc.core.api.origin_enforcement_enabled is False
    assert tc.http('GET', '/v1/health').status == 200
    tc.core.api.origin_enforcement_enabled = True
    assert tc.http('GET', '/v1/health').status == 403
    assert tc.core.api.isolated_dispatch_qualified is False


def test_registered_tunnel_preserves_rearm_step_up(tc):
    code = tc.http('POST', '/v1/devices/pair/start',
                   body={'scopes': ['observe', 'control', 'approve']}).json()['code']
    paired = request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                     body={'code': code, 'platform': 'web', 'pin': '482913'}).json()['token']
    enable(tc, Backend(path=origin.PathClass.REGISTERED_TUNNEL))

    def command(path, **body):
        return tc.http('POST', path, token=paired, headers={'Host': TUNNEL},
                       body=dict(body, idempotency_key=path + str(body)))

    assert command('/v1/estop').status == 200
    response = command('/v1/rearm')
    assert (response.status, response.json()['error']) == (422, 'guard_failed')
    assert 'step-up' in response.json()['detail']['reason']
    assert command('/v1/rearm', step_up='482913').status == 200


NOT_ALLOWED = [
    (origin.OriginClass.EXECUTION, origin.PathClass.DIRECT_LOCAL),
    (origin.OriginClass.VERIFIER, origin.PathClass.DIRECT_LOCAL),
    (origin.OriginClass.UNDETERMINED, origin.PathClass.DIRECT_LOCAL),
    (origin.OriginClass.USER, origin.PathClass.DEPUTY),
    (origin.OriginClass.USER, origin.PathClass.HOP),
    (origin.OriginClass.USER, origin.PathClass.UNAPPROVED),
]


def _path(path):
    return path.replace('{id}', 'x').replace('/*', '/x.js')


def _refused(r):
    return r.status == 403 and r.json()['error'] == 'origin_refused'


def test_every_route_class_is_refused_by_the_switched_on_gate(tc):
    """R1: observe, ordinary, privileged and authority routes, the stream included,
    with the local credential the test client always holds."""
    for kind, path in NOT_ALLOWED:
        enable(tc, Backend(kind, path))
        for r in routes.ROUTES:
            if routes.CLASS[(r.method, r.path)] == 'public':
                continue
            before = snapshot(tc)
            resp = tc.http(r.method, _path(r.path), body={} if r.method == 'POST' else None)
            assert _refused(resp), (kind, path, r.method, r.path, resp.status)
            assert snapshot(tc) == before, (r.method, r.path)


def test_a_paired_device_is_refused_on_the_direct_local_path_and_kept_on_the_tunnel(tc):
    code = tc.http('POST', '/v1/devices/pair/start', body={'scopes': ['observe']}).json()['code']
    paired = request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                     body={'code': code, 'platform': 'web'}).json()['token']
    enable(tc, Backend(path=origin.PathClass.DIRECT_LOCAL))
    before = snapshot(tc)
    assert _refused(tc.http('GET', '/v1/health', token=paired))
    assert snapshot(tc) == before
    enable(tc, Backend(path=origin.PathClass.REGISTERED_TUNNEL))
    assert tc.http('GET', '/v1/health', token=paired, headers={'Host': TUNNEL}).status == 200


def test_a_tunnel_reaches_only_pair_redeem_before_a_credential(tc):
    launch = tc.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    pair = tc.http('POST', '/v1/devices/pair/start', body={'scopes': ['observe']}).json()['code']
    enable(tc, Backend(path=origin.PathClass.REGISTERED_TUNNEL))
    before = snapshot(tc)
    for method, path, body in [('POST', '/v1/devices/launch/code', {}),
                               ('POST', '/v1/devices/pair/start', {'scopes': ['observe']}),
                               ('POST', '/v1/devices/launch/redeem',
                                {'code': launch, 'platform': 'web'})]:
        r = request(tc.base_url, method, path, body=body, headers={'Host': TUNNEL})
        assert _refused(r), path
    assert snapshot(tc) == before
    assert request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                   body={'code': pair, 'platform': 'web'},
                   headers={'Host': TUNNEL}).status == 200
    enable(tc, Backend(path=origin.PathClass.DIRECT_LOCAL))
    assert request(tc.base_url, 'POST', '/v1/devices/launch/redeem',
                   body={'code': launch, 'platform': 'web'}).status == 200


def test_a_stream_over_a_tunnel_closes_when_its_origin_is_lost(tc):
    code = tc.http('POST', '/v1/devices/pair/start', body={'scopes': ['observe']}).json()['code']
    paired = request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                     body={'code': code, 'platform': 'web'}).json()['token']
    backend = Backend(path=origin.PathClass.REGISTERED_TUNNEL)
    enable(tc, backend)
    tc.core.api.sse.heartbeat_s = 0.1
    s = SSEClient(tc.base_url, paired, headers={'Host': TUNNEL})
    try:
        assert s.status == 200
        assert s.next(timeout=5) is not None
        backend.bad = 'expired'
        deadline = time.monotonic() + 5
        while s.next(timeout=1) is not None:
            assert time.monotonic() < deadline, 'the stream outlived its origin'
    finally:
        s.conn.close()


@pytest.mark.xfail(strict=True, reason='PV20-11 activation blocker: backend calls have no time bound')
def test_backend_calls_are_time_bounded(tc):
    """PV20-11 activation blocker (origin.py): a hung attest must answer undetermined
    within a deadline. Until a bound exists this fails, so it stays an xfail."""
    class Slow(Backend):
        def attest(self, context):
            time.sleep(3)
            return super().attest(context)

    enable(tc, Slow())
    started = time.monotonic()
    r = tc.http('GET', '/v1/health')
    assert r.status == 403 and time.monotonic() - started < 1

