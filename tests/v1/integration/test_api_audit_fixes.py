"""Regressions for the loopback API audit of 2026-11-01 (audit-api): each test
is one finding's request, asserting the refusal it should have drawn."""

from archeus.core.domain import ids
from v1.judge.http import request

SYNTHETIC = 'synthetic-audit-secret'


def _launch_device(tc, scopes):
    code = tc.http('POST', '/v1/devices/launch/code', body={'scopes': scopes}).json()['code']
    r = request(tc.base_url, 'POST', '/v1/devices/launch/redeem',
                body={'code': code, 'platform': 'web'})
    assert r.status == 200, r.body
    return r.json()['device_id'], r.json()['token']


def _key():
    return {'idempotency_key': ids.new_ulid()}


# ── F2: a pairing never grants more scope than the minting device holds ──

def test_f2_a_device_cannot_pair_a_client_with_scopes_it_lacks(tc):
    _device, token = _launch_device(tc, ['observe', 'admin'])
    r = tc.http('POST', '/v1/devices/pair/start', token=token,
                body={'scopes': ['observe', 'control', 'approve', 'admin']})
    assert (r.status, r.json()['error']) == (403, 'scope_required')
    assert r.json()['detail'] == {'scope': 'control'}
    ok = tc.http('POST', '/v1/devices/pair/start', token=token, body={'scopes': ['observe', 'admin']})
    assert ok.status == 200 and ok.json()['scopes'] == ['observe', 'admin']


# ── F3: revoking a device cancels the codes it minted ──

def test_f3_a_revoked_minters_launch_and_pair_codes_no_longer_redeem(tc):
    device, token = _launch_device(tc, ['observe', 'admin'])
    launch = tc.http('POST', '/v1/devices/launch/code', token=token,
                     body={'scopes': ['observe', 'admin']}).json()['code']
    pair = tc.http('POST', '/v1/devices/pair/start', token=token,
                   body={'scopes': ['observe']}).json()['code']
    assert tc.http('POST', '/v1/devices/%s/revoke' % device, body=_key()).status == 200
    r = request(tc.base_url, 'POST', '/v1/devices/launch/redeem',
                body={'code': launch, 'platform': 'web'})
    assert (r.status, r.json()['error']) == (401, 'invalid_launch_code')
    r = request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                body={'code': pair, 'platform': 'web'})
    assert (r.status, r.json()['error']) == (401, 'invalid_pairing_code')
