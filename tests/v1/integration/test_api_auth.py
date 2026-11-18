"""Authentication at the HTTP boundary (p3.5b design gate §4, D5, D7; §10 F1–F7, P3).

Every refusal here must happen before any command is submitted or any query
runs, so each one also checks that nothing was written."""

import json
import os
import secrets
import sqlite3
import threading

import pytest

from archeus.api import auth
from archeus.core.application import commands
from archeus.infra import discovery, paths
from archeus.infra.db import connection
from v1.judge.http import SSEClient, request

SECRETS = []            # every token and code minted here: F7 greps for them


def _head(tc):
    return tc.http('GET', '/v1/events?after=0&limit=1000').json()['events'][-1]['seq']


def launch(tc, token=None):
    r = tc.http('POST', '/v1/devices/launch/code', body={}, token=token or tc.token)
    if r.status == 200:
        SECRETS.append(r.json()['code'])
    return r


def redeem(tc, code, platform='web', **kw):
    r = request(tc.base_url, 'POST', '/v1/devices/launch/redeem',
                body={'code': code, 'platform': platform}, **kw)
    if r.status == 200:
        SECRETS.append(r.json()['token'])
    return r


def observe_device(tc):
    """(device_id, token) of a browser device made the real way."""
    r = redeem(tc, launch(tc).json()['code'])
    assert r.status == 200, r.body
    return r.json()['device_id'], r.json()['token']


def _no_writes(tc, fn):
    before = _head(tc)
    out = fn()
    assert _head(tc) == before, 'a refused request wrote an event'
    return out


# ── F1 Host, F4 cross-site ──

@pytest.mark.parametrize('path', ['/', '/assets/x.js', '/v1/health', '/v1/missions',
                                  '/v1/events/stream', '/nope'])
@pytest.mark.parametrize('host', ['evil.example:{port}', 'localhost:{port}', '127.0.0.1',
                                  '127.0.0.1:1'])
def test_a_foreign_host_is_refused_on_every_path(tc, path, host):
    r = tc.http('GET', path, headers={'Host': host.format(port=tc.port)})
    assert r.status == 403 and r.json()['error'] == 'host_not_allowed'
    assert 'http://127.0.0.1:%d' % tc.port in r.json()['detail']['why']


def test_a_foreign_host_cannot_create_anything(tc):
    _no_writes(tc, lambda: tc.http('POST', '/v1/missions', headers={'Host': 'evil.example'},
                                   body={'title': 't', 'objective': 'o',
                                         'idempotency_key': 'k'}))


@pytest.mark.parametrize('path,headers,refusal', [
    ('/v1/missions', {'Host': 'evil.example'}, (403, 'host_not_allowed')),
    ('/v1/missions', {'Sec-Fetch-Site': 'cross-site'}, (403, 'cross_site')),
    ('/v1/missions?token=x', {}, (401, 'token_in_url'))])
def test_an_early_refusal_of_a_post_is_answered_not_reset(tc, unread_at_finish, path, headers,
                                                          refusal):
    """Refused before routing, the body must still be read: a socket closed with
    its body unread sends RST, and the client gets a reset (WinError 10053)
    instead of the response. Whether the client sees that reset is a race, so
    the invariant is checked where it holds — nothing unread when the server
    closes the socket — as well as by the response arriving."""
    done, unread = unread_at_finish
    body = json.dumps({'title': 't', 'objective': 'o' * (512 << 10),
                       'idempotency_key': 'k'}).encode()

    def post():
        r = tc.http('POST', path, raw=body, headers=headers)
        assert done.wait(15), 'the request never finished'
        return r
    r = _no_writes(tc, post)
    assert unread == [0], 'the server finished with the body unread'
    assert (r.status, r.json()['error']) == refusal


@pytest.mark.parametrize('headers,status', [
    ({'Sec-Fetch-Site': 'cross-site'}, 403), ({'Sec-Fetch-Site': 'same-site'}, 403),
    ({'Sec-Fetch-Site': 'same-origin'}, 200), ({'Sec-Fetch-Site': 'none'}, 200),
    ({'Origin': 'http://evil.example'}, 403), ({'Origin': 'http://localhost:{port}'}, 403),
    ({'Origin': 'http://127.0.0.1:{port}'}, 200),
    ({'Origin': 'http://127.0.0.1:{port}', 'Sec-Fetch-Site': 'cross-site'}, 403)])
def test_fetch_metadata_allows_only_same_origin(tc, headers, status):
    h = {k: v.format(port=tc.port) for k, v in headers.items()}
    r = tc.http('GET', '/v1/version', headers=h)
    assert r.status == status
    if status == 403:
        assert r.json()['error'] == 'cross_site'


def test_a_cross_site_post_writes_nothing(tc):
    """CSRF: a page elsewhere cannot make a request that changes anything."""
    r = _no_writes(tc, lambda: tc.http(
        'POST', '/v1/missions', headers={'Sec-Fetch-Site': 'cross-site',
                                         'Origin': 'http://evil.example'},
        body={'title': 't', 'objective': 'o', 'idempotency_key': 'csrf'}))
    assert r.status == 403


# ── F2 tokens ──

def test_every_bad_token_is_the_same_401(tc):
    device, observe = observe_device(tc)
    expired = auth.new_token()
    tc.core.db.writer.execute(commands.register_device, {
        'actor': tc.core.system, 'name': 'old', 'platform': 'web',
        'token_hash': auth.token_hash(expired), 'scopes': ['observe'],
        'expires_at': '2001-01-01T00:00:00.000Z'})
    assert tc.http('POST', '/v1/devices/%s/revoke' % device,
                   body={'idempotency_key': 'rv'}).status == 200
    bad = [None, 'Bearer', 'Bearer x', 'Basic ' + tc.token, 'Bearer dev_' + 'A' * 43,
           'Bearer node_' + secrets.token_urlsafe(32), 'bearer ' + tc.token + 'x',
           'Bearer ' + observe, 'Bearer ' + expired]
    for header in bad:
        h = {} if header is None else {'Authorization': header}
        r = request(tc.base_url, 'GET', '/v1/missions', headers=h)
        assert (r.status, r.json()) == (401, {'error': 'unauthenticated', 'detail': {}}), header
    assert tc.http('GET', '/v1/missions').status == 200          # the live one still works


def test_a_token_in_the_url_is_refused_even_beside_a_valid_header(tc):
    for q in ('token=' + tc.token, 'access_token=x', 'state=CREATED&token='):
        r = tc.http('GET', '/v1/missions?' + q)
        assert (r.status, r.json()['error']) == (401, 'token_in_url'), q


# ── F3 scope ──

def test_an_observe_device_cannot_command_and_nothing_is_written(tc):
    _device, observe = observe_device(tc)
    before = tc.http('GET', '/v1/missions').json()['missions']
    for method, path, scope in (('POST', '/v1/missions', 'control'),
                                ('POST', '/v1/missions/msn_x/pause', 'control'),
                                ('POST', '/v1/devices/launch/code', 'admin'),
                                ('POST', '/v1/devices/dvc_x/revoke', 'admin')):
        r = _no_writes(tc, lambda m=method, p=path: tc.http(m, p, token=observe, body={
            'title': 't', 'objective': 'o', 'idempotency_key': 'k'}))
        assert (r.status, r.json()) == (403, {'error': 'scope_required',
                                              'detail': {'scope': scope}}), path
    assert tc.http('GET', '/v1/missions').json()['missions'] == before
    assert tc.http('GET', '/v1/missions', token=observe).status == 200   # it can read
    with sqlite3.connect(connection.db_path()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM idempotency_keys').fetchone()[0] == 0


# ── F5 headers, P3 SPA not built ──

HEADERS = {'Content-Security-Policy': auth.CSP, 'X-Content-Type-Options': 'nosniff',
           'Referrer-Policy': 'no-referrer'}


def _has_headers(r, cache='no-store'):
    for k, v in HEADERS.items():
        assert r.headers.get(k) == v, (k, r.status)
    assert r.headers.get('Cache-Control') == cache, r.status


@pytest.fixture
def built(tmp_path):
    d = tmp_path / 'static'
    (d / 'assets').mkdir(parents=True)
    (d / 'index.html').write_text('<!doctype html><script type="module" '
                                  'src="/assets/app-1.js"></script>', encoding='utf-8')
    (d / 'assets' / 'app-1.js').write_text('console.log(1)', encoding='utf-8')
    (d / 'secret.txt').write_text('not an asset', encoding='utf-8')
    return d


def test_every_response_class_carries_the_security_headers(archeus_home, built, monkeypatch):
    from v1.judge.http import TempCore
    tc = TempCore(archeus_home, static_dir=str(built), heartbeat_s=0.05).start()
    try:
        _has_headers(tc.http('GET', '/v1/health'))                              # 200 JSON
        _has_headers(tc.http('GET', '/v1/missions/msn_nope'))                   # 404
        _has_headers(tc.http('GET', '/v1/missions', headers={'Host': 'x'}))      # 403
        _has_headers(request(tc.base_url, 'GET', '/v1/missions'))               # 401
        _has_headers(tc.http('DELETE', '/v1/missions'))                         # 405
        r = tc.http('GET', '/')                                                 # static index
        assert r.status == 200 and b'app-1.js' in r.body
        _has_headers(r)
        a = tc.http('GET', '/assets/app-1.js')                                  # hashed asset
        assert a.status == 200 and a.headers['Content-Type'].startswith('text/javascript')
        _has_headers(a, cache='public, max-age=31536000, immutable')
        s = SSEClient(tc.base_url, tc.token)                                    # the stream
        assert s.status == 200
        _has_headers(s)
        s.close()
        from archeus.core.application import queries

        def boom(*a, **k):
            raise RuntimeError('an internal bug')
        monkeypatch.setattr(queries, 'list_missions', boom)
        r = tc.http('GET', '/v1/missions')                                      # 500
        assert r.status == 500 and set(r.json()['detail']) == {'ref'}
        assert b'Traceback' not in r.body and b'internal bug' not in r.body
        _has_headers(r)
        tc.core.api.stopping = True
        r = tc.http('GET', '/v1/health')                                        # 503
        assert (r.status, r.json()['error']) == (503, 'core_stopping')
        _has_headers(r)
        tc.core.api.stopping = False
    finally:
        tc.stop()


def test_without_a_build_the_root_serves_a_plain_not_built_page(archeus_home, tmp_path):
    from v1.judge.http import TempCore
    tc = TempCore(archeus_home, static_dir=str(tmp_path / 'nothing')).start()
    try:
        r = request(tc.base_url, 'GET', '/')                  # public: no token needed
        assert r.status == 200 and b'not built' in r.body and b'<script' not in r.body
        _has_headers(r)
        assert request(tc.base_url, 'GET', '/assets/x.js').status == 404
    finally:
        tc.stop()


@pytest.mark.parametrize('path', ['/assets/../secret.txt', '/assets/%2e%2e/secret.txt',
                                  '/assets/..%5csecret.txt', '/assets/', '/secret.txt',
                                  '/assets/app-1.js/x', '/index.html'])
def test_nothing_outside_the_built_assets_is_served(archeus_home, built, path):
    from v1.judge.http import TempCore
    tc = TempCore(archeus_home, static_dir=str(built)).start()
    try:
        r = tc.http('GET', path)
        assert r.status == 404 and b'not an asset' not in r.body, path
    finally:
        tc.stop()


# ── F6 launch codes ──

def test_a_launch_code_redeems_once_into_an_observe_only_device(tc):
    code = launch(tc).json()['code']
    r = redeem(tc, code)
    assert r.status == 200
    device, token = r.json()['device_id'], r.json()['token']
    assert token.startswith('dev_') and device.startswith('dvc_')
    assert redeem(tc, code).json() == {'error': 'invalid_launch_code', 'detail': {}}
    assert redeem(tc, code).status == 401
    ok = tc.http('GET', '/v1/missions', token=token)
    assert ok.status == 200
    for scope, path in (('control', '/v1/missions'), ('admin', '/v1/devices/launch/code')):
        r = tc.http('POST', path, token=token, body={'idempotency_key': 'x', 'title': 't',
                                                     'objective': 'o'})
        assert r.json() == {'error': 'scope_required', 'detail': {'scope': scope}}
    changed = [e for e in tc.client().events(0) if e['type'] == 'device.state_changed'
               and e['subject']['id'] == device]
    assert [e['payload']['to'] for e in changed] == ['ACTIVE']


def test_a_launch_code_expires_after_60_seconds(tc, clock):
    code = launch(tc).json()['code']
    clock.advance(60.5)
    assert redeem(tc, code).status == 401
    fresh = launch(tc).json()['code']
    clock.advance(59)
    assert redeem(tc, fresh).status == 200


def test_bad_codes_all_get_the_same_answer(tc):
    for code in ('', 'x', 'A' * 43, secrets.token_urlsafe(32)):
        assert redeem(tc, code).json() == {'error': 'invalid_launch_code', 'detail': {}}
    assert redeem(tc, 'x', platform='tui').status == 400        # schema before the pop
    code = launch(tc).json()['code']
    assert redeem(tc, code, platform='phone').status == 400
    assert redeem(tc, code).status == 200                      # not spent by the bad call


def test_only_loopback_may_mint_or_redeem(tc, monkeypatch):
    code = launch(tc).json()['code']
    monkeypatch.setattr(auth, 'loopback_peer', lambda addr: False)
    for r in (launch(tc), redeem(tc, code)):
        assert (r.status, r.json()['error']) == (403, 'host_not_allowed')
    monkeypatch.undo()
    assert redeem(tc, code, headers={'Host': 'evil.example'}).status == 403
    assert redeem(tc, code).status == 200


def test_two_concurrent_redemptions_one_wins(tc):
    code = launch(tc).json()['code']
    out, start = [], threading.Barrier(2)

    def go():
        start.wait()
        out.append(redeem(tc, code).status)
    threads = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(out) == [200, 401]


def test_redemption_writes_no_idempotency_record(tc):
    observe_device(tc)
    with sqlite3.connect(connection.db_path()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM idempotency_keys').fetchone()[0] == 0


def test_the_local_token_is_kept_while_live_and_reminted_when_revoked(archeus_home):
    from v1.judge.http import TempCore
    tc = TempCore(archeus_home).start()
    first, device = tc.token, tc.core.local['device_id']
    SECRETS.append(first)
    assert tc.http('POST', '/v1/devices/%s/revoke' % device,
                   body={'idempotency_key': 'self'}).status == 200
    assert tc.http('GET', '/v1/version').status == 401
    tc.restart(kill=False)
    try:
        assert tc.token != first and discovery.read_local_token() == tc.token
        SECRETS.append(tc.token)
        assert tc.http('GET', '/v1/version').status == 200
    finally:
        tc.stop()


# ── F7 no secrets at rest or in logs ──

def test_no_token_or_code_is_at_rest_anywhere(tc):
    """The F flow once more on one home, then every file and table Core
    writes is searched for what it minted."""
    del SECRETS[:]
    SECRETS.append(tc.token)
    device, observe = observe_device(tc)
    redeem(tc, SECRETS[1])                                  # a replayed code
    tc.http('GET', '/v1/missions?token=' + observe)
    tc.http('POST', '/v1/missions', token=observe, body={'title': 't', 'objective': 'o',
                                                         'idempotency_key': 'a'})
    tc.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
                                          'idempotency_key': 'b'})
    tc.http('POST', '/v1/devices/%s/revoke' % device, body={'idempotency_key': 'c'})
    s = SSEClient(tc.base_url, tc.token)
    s.close()
    tc.stop()
    blobs = []
    for d, _s, files in os.walk(os.path.join(paths.archeus_home(), 'logs')):
        blobs += [open(os.path.join(d, f), encoding='utf-8').read() for f in files]
    with sqlite3.connect(connection.db_path()) as conn:
        for table in ('idempotency_keys', 'events', 'tokens', 'principals', 'devices'):
            blobs.append(json.dumps(conn.execute('SELECT * FROM %s' % table).fetchall()))
    everything = '\n'.join(blobs)
    assert 'POST /v1/devices/launch/redeem 200' in everything     # the log did record
    assert len(SECRETS) == 3
    leaked = [i for i, x in enumerate(SECRETS) if x in everything]
    assert not leaked, 'secrets at rest (by index): %s' % leaked
    assert open(discovery.local_token_path()).read() == SECRETS[0]   # its one plaintext home
    assert not os.path.exists(discovery.core_json_path())
