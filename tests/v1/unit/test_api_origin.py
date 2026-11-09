"""R1-A at the HTTP boundary (ADR-0053; T-053 §4 P1, P7; K-O1): the peer's origin
is decided before any credential or code is read, and only the user's origin
reaches a route other than the public page. The attestor here is a fake; the
production one takes every peer as the user, so nothing changes until R1-A is
activated. A paired credential reaches a privileged route only through a
configured remote host (T-053 C2, Q4-A; T-059)."""

import ast
import logging
import os

import pytest

from archeus.api import auth, routes, server
from archeus.cli.tui import sync
from archeus.infra.eventlog import outbox
from v1.judge.http import TempCore, request
from v1.judge.support import wait_for

AUTHORITY = {('POST', '/v1/devices/launch/code'), ('POST', '/v1/devices/launch/redeem'),
             ('POST', '/v1/devices/pair/start'), ('POST', '/v1/devices/pair/redeem')}
NOT_USER = [auth.EXECUTION, auth.VERIFIER, auth.UNDETERMINED]
TUNNEL = 'pc.tailnet.ts.net'
SCOPE = {(r.method, r.path): r.scope for r in routes.ROUTES}


@pytest.fixture
def core(archeus_home):
    c = TempCore(archeus_home, remote_hosts=(TUNNEL,)).start()
    yield c
    c.stop()


def _attest(core, attestor):
    core.core.api.attestor = attestor


def _head(core):
    with core.core.db.read() as conn:
        return outbox.head(conn)


def _devices(core):
    with core.core.db.read() as conn:
        return conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0]


def _path(path):
    return path.replace('{id}', 'x').replace('/*', '/x.js')


def _redeem(core, kind, code):
    return request(core.base_url, 'POST', '/v1/devices/%s/redeem' % kind,
                   body={'code': code, 'platform': 'web'})


# ── the table ──

def test_every_route_is_classified_and_every_class_agrees_with_its_scope():
    scope = {(r.method, r.path): r.scope for r in routes.ROUTES}
    assert set(routes.CLASS) == set(scope)
    for key, cls in routes.CLASS.items():
        assert cls in ('public', 'authority', 'ordinary', 'privileged', 'observe'), key
        if cls == 'public':
            assert scope[key] is None, key
        elif cls == 'observe':
            assert scope[key] == 'observe', key
        elif cls in ('ordinary', 'privileged'):
            assert scope[key] in ('control', 'approve', 'admin'), key
    assert {k for k, c in routes.CLASS.items() if c == 'authority'} == AUTHORITY
    assert AUTHORITY <= routes.PRIVILEGED
    assert not {k for k, c in routes.CLASS.items() if c in ('observe', 'public')} & \
        routes.PRIVILEGED


def test_only_an_authority_route_can_register_a_device():
    """P7: a handler that makes a device is classified, so its origin is checked
    before its code is read."""
    api = os.path.dirname(routes.__file__)
    makers = set()
    for name in os.listdir(api):
        if name.endswith('.py'):
            with open(os.path.join(api, name), encoding='utf-8') as f:
                tree = ast.parse(f.read())
            for fn in ast.walk(tree):
                if isinstance(fn, ast.FunctionDef) and 'register_device' in ast.unparse(fn):
                    makers.add(fn.name)
    assert makers
    by_handler = {r.handler.__name__: (r.method, r.path) for r in routes.ROUTES}
    assert {by_handler.get(m) for m in makers} <= AUTHORITY, makers


def test_by_default_every_peer_is_the_user_so_nothing_changes(core):
    assert core.core.api.attestor is auth.attest_user
    assert server.Api.__init__.__kwdefaults__['attestor'] is auth.attest_user
    assert auth.attest_user(('127.0.0.1', 1)) == auth.USER
    assert core.http('GET', '/v1/health').status == 200


# ── enforcement ──

@pytest.mark.parametrize('origin', NOT_USER)
def test_a_non_user_origin_reaches_no_route_but_the_public_page(core, origin):
    """P1: observe included, before the credential, and nothing is written."""
    before = _head(core), _devices(core)
    _attest(core, lambda peer: origin)
    for r in routes.ROUTES:
        resp = core.http(r.method, _path(r.path), body={} if r.method == 'POST' else None)
        if routes.CLASS[(r.method, r.path)] == 'public':
            assert resp.status in (200, 404), r.path
        else:
            assert resp.status == 403, (r.path, resp.status)
            assert resp.json() == {'error': 'origin_refused', 'detail': {'origin': origin}}
    assert (_head(core), _devices(core)) == before


def test_the_origin_is_decided_before_the_credential_and_the_page_is_never_attested(core):
    seen = []
    _attest(core, lambda peer: seen.append(peer) or auth.EXECUTION)
    r = core.http('GET', '/v1/health', token='dev_' + 'x' * 43)
    assert (r.status, r.json()['error']) == (403, 'origin_refused')     # not 401
    assert seen and seen[0][0] == '127.0.0.1'
    seen.clear()
    assert request(core.base_url, 'GET', '/').status == 200 and seen == []


@pytest.mark.parametrize('answer', ['raise', 'root', None, 'USER'])
def test_an_attestor_that_fails_or_answers_anything_else_is_undetermined(core, answer):
    def attestor(peer):
        if answer == 'raise':
            raise RuntimeError('no observation')
        return answer
    _attest(core, attestor)
    r = core.http('GET', '/v1/health')
    assert (r.status, r.json()['detail']) == (403, {'origin': auth.UNDETERMINED})


@pytest.mark.parametrize('origin', NOT_USER)
def test_a_refused_redemption_spends_no_code_creates_no_device_and_trips_no_breaker(core,
                                                                                     origin):
    """P7: refused before `redeem`, so a flood of wrong codes from an execution
    never reaches the D10 breaker either."""
    launch = core.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    pair = core.http('POST', '/v1/devices/pair/start', body={}).json()['code']
    before = _head(core), _devices(core)
    _attest(core, lambda peer: origin)
    for kind, code in (('launch', launch), ('pair', pair)):
        r = _redeem(core, kind, code)
        assert (r.status, r.json()['error']) == (403, 'origin_refused'), kind
    for _ in range(auth.PairingCodes.FAIL_LIMIT + 2):
        assert _redeem(core, 'pair', 'wrong').status == 403
    assert (_head(core), _devices(core)) == before
    _attest(core, auth.attest_user)
    assert _redeem(core, 'launch', launch).status == 200
    assert _redeem(core, 'pair', pair).status == 200


def test_the_request_log_never_records_a_token_or_a_code(core, caplog):
    caplog.set_level(logging.INFO, logger='archeus.core')
    code = core.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    _attest(core, lambda peer: auth.EXECUTION)
    core.http('GET', '/v1/health')
    _redeem(core, 'launch', code)
    _attest(core, auth.attest_user)
    core.http('GET', '/v1/health')
    # the line is written after the response is sent
    wait_for(lambda: any('/v1/health 200' in r.getMessage() for r in caplog.records))
    lines = [rec.getMessage() for rec in caplog.records]
    assert any('/v1/health 403' in line for line in lines)           # the log was seen
    assert not [line for line in lines if core.token in line or code in line]


# ── a paired credential: privileged only through the remote host (T-059) ──

def _paired(core, scopes=auth.SCOPES):
    code = core.http('POST', '/v1/devices/pair/start', body={'scopes': list(scopes)})
    return _redeem(core, 'pair', code.json()['code']).json()['token']


def _mission(core, token, **kw):
    return core.http('POST', '/v1/missions', token=token, **kw,
                     body={'title': 'M', 'objective': 'o', 'idempotency_key': os.urandom(8).hex()})


def test_a_paired_credential_on_the_loopback_host_reaches_no_privileged_route(core):
    """Q4-A: neither branch's path, so no §3.6 effect, and nothing written."""
    token = _paired(core)                                  # every scope: only the Host refuses
    before = _head(core), _devices(core)
    for key in sorted(routes.PRIVILEGED):
        if SCOPE[key] is None:
            continue                                       # a redemption reads no credential
        r = core.http(key[0], _path(key[1]), body={}, token=token)
        assert (r.status, r.json()['error']) == (403, 'remote_host_required'), key
    assert (_head(core), _devices(core)) == before


def test_the_tui_explains_that_refusal_as_a_remote_connection_not_a_local_one(core):
    r = _mission(core, _paired(core))
    said = sync.explain({'status': r.status, 'code': r.json()['error'],
                         'detail': r.json().get('detail')})
    assert said == 'Only through the configured remote connection to Archeus.'
    assert said != sync.explain({'status': 403, 'code': 'host_not_allowed', 'detail': {}})


def test_on_the_loopback_host_it_keeps_its_observe_and_ordinary_routes(core):
    token = _paired(core)
    assert core.http('GET', '/v1/missions', token=token).status == 200
    ack = core.http('POST', '/v1/digest/ack', body={'up_to_seq': _head(core)}, token=token)
    assert ack.status == 200, ack.body


def test_through_the_remote_host_its_privileged_routes_are_p15s_and_a_local_one_is_not(core):
    token, tunnel = _paired(core, ('observe', 'control')), {'Host': TUNNEL}
    r = _mission(core, token, headers=tunnel)
    assert r.status == 200, r.body
    assert _mission(core, core.token, headers=tunnel).json()['error'] == 'host_not_allowed'
    assert _mission(core, core.token).status == 200        # D21, unchanged


@pytest.mark.parametrize('spoof, error', [
    ({'X-Forwarded-Host': TUNNEL}, 'remote_host_required'),
    ({'Forwarded': 'host=' + TUNNEL}, 'remote_host_required'),
    ({'X-Original-Host': TUNNEL}, 'remote_host_required'),
    ({'Origin': 'https://' + TUNNEL}, 'cross_site'),
])
def test_only_the_host_header_names_the_remote_host(core, spoof, error):
    token = _paired(core)
    before = _head(core)
    r = _mission(core, token, headers=spoof)
    assert (r.status, r.json()['error']) == (403, error)
    assert _head(core) == before
