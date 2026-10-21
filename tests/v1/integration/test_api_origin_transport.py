"""PV20-10 synthetic HTTP transport evidence; no native attestation."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from archeus.api import origin
from archeus.infra.eventlog import outbox
from v1.judge.http import TUNNEL, request
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
