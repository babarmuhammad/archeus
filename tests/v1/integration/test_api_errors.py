"""The §5.5 error table over real HTTP, where each row is reachable, and the
endpoint floor: bad input to every route never produces a 500
(p3.5b design gate §5.5, §10 D1, M1, M9)."""

import concurrent.futures
import json
import random

import pytest

from archeus.api import routes
from archeus.core.application import errors
from v1.judge.http import SSEClient, request


def _err(r):
    return r.status, r.json()['error'], r.json()['detail']


def _mission(tc):
    return tc.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
                                                 'idempotency_key': 'm'}).json()['id']


def test_client_mistakes_are_typed_4xx(tc):
    mid = _mission(tc)
    cases = [
        (('GET', '/v1/missions/msn_nope'), (404, 'not_found', {'id': 'msn_nope'})),
        (('GET', '/nope'), (404, 'not_found', {})),
        (('GET', '/v1/missions/%s/pause' % mid), (405, 'method_not_allowed', {})),
        (('DELETE', '/v1/missions'), (405, 'method_not_allowed', {})),
        (('GET', '/v1/events?after=x'), (400, 'invalid_request',
                                         {'field': 'cursor', 'why': 'is an integer >= 0'})),
        (('GET', '/v1/events?limit=0'), (400, 'invalid_request',
                                         {'field': 'limit', 'why': 'is 1..1000'})),
        (('GET', '/v1/events?limit=1001'), (400, 'invalid_request',
                                            {'field': 'limit', 'why': 'is 1..1000'})),
    ]
    for (method, path), want in cases:
        assert _err(tc.http(method, path)) == want, path
    r = tc.http('GET', '/v1/missions?state=NOPE')
    assert _err(r)[:2] == (400, 'invalid_request')
    r = tc.http('POST', '/v1/missions/%s/resume' % mid, body={'idempotency_key': 'r'})
    assert _err(r) == (422, 'invalid_transition', {
        'machine': 'mission', 'from': _state(tc, mid), 'to': 'RESUMED', 'trigger': 'resume'})
    r = tc.http('POST', '/v1/devices/dvc_nope/revoke', body={'idempotency_key': 'v'})
    assert _err(r)[:2] == (404, 'not_found')


def _state(tc, mid):
    return tc.http('GET', '/v1/missions/' + mid).json()['state']


@pytest.mark.parametrize('raw,field', [
    (b'not json', None), (b'[1, 2]', None), (b'"s"', None), (b'\xff\xfe', None),
    (json.dumps({'objective': 'o', 'idempotency_key': 'k'}).encode(), 'title'),
    (json.dumps({'title': 1, 'objective': 'o', 'idempotency_key': 'k'}).encode(), 'title'),
    (json.dumps({'title': 't', 'objective': 'o', 'idempotency_key': 'k',
                 'extra': 1}).encode(), 'extra'),
    (json.dumps({'title': 't', 'objective': 'o', 'idempotency_key': 'k',
                 'success_criteria': [{'text': 'x'}]}).encode(), 'success_criteria[0].check'),
    (json.dumps({'title': '', 'objective': 'o', 'idempotency_key': 'k'}).encode(), None),
])
def test_a_malformed_body_is_400_and_writes_nothing(tc, raw, field):
    before = len(tc.client().events(0))
    r = tc.http('POST', '/v1/missions', raw=raw)
    status, code, detail = _err(r)
    assert (status, code) == (400, 'invalid_request'), r.body
    assert detail.get('field') == field
    assert len(tc.client().events(0)) == before


def test_a_body_over_one_mebibyte_is_413_unread(tc):
    r = tc.http('POST', '/v1/missions', raw=b'{' + b' ' * (1 << 20) + b'}')
    assert _err(r) == (413, 'payload_too_large', {})


def test_a_refused_oversized_body_is_drained_so_the_413_arrives(tc, unread_at_finish):
    """The body is never parsed, but the socket is read to the end before it
    closes (a lingering close): closing it with the body unread sends RST, and
    under load the client got WinError 10053 instead of the 413."""
    done, unread = unread_at_finish
    r = tc.http('POST', '/v1/missions', raw=b'{' + b' ' * (2 << 20) + b'}')
    assert done.wait(15)
    assert unread == [0], 'the server closed with the body unread'
    assert _err(r) == (413, 'payload_too_large', {})


def test_a_full_request_pool_is_503_busy_with_retry_after(tc, monkeypatch):
    import threading
    monkeypatch.setattr(tc.core.api, 'requests', threading.BoundedSemaphore(1))
    tc.core.api.requests.acquire()
    r = tc.http('GET', '/v1/version')
    assert _err(r) == (503, 'busy', {}) and r.headers['Retry-After'] == '1'


def test_a_full_writer_queue_and_a_slow_command_are_503_busy(tc, monkeypatch):
    def busy(*a, **k):
        raise errors.WriterBusy('full')
    monkeypatch.setattr(tc.core.db.writer, 'submit', busy)
    r = tc.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
                                              'idempotency_key': 'b'})
    assert _err(r) == (503, 'busy', {}) and r.headers['Retry-After'] == '1'
    monkeypatch.setattr(tc.core.db.writer, 'submit', lambda *a, **k: concurrent.futures.Future())
    monkeypatch.setattr(tc.core.api, 'command_timeout', 0.05)
    r = tc.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
                                              'idempotency_key': 'c'})
    assert _err(r) == (503, 'busy', {})


def test_a_command_during_shutdown_is_answered_never_twice(tc, monkeypatch):
    """M6: a closed writer is 503 core_stopping, not a 500."""
    def closed(*a, **k):
        raise errors.WriterClosed('closed')
    monkeypatch.setattr(tc.core.db.writer, 'submit', closed)
    r = tc.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
                                              'idempotency_key': 's'})
    assert _err(r) == (503, 'core_stopping', {})


# ── the endpoint floor ──

JUNK = [None, b'', b'{}', b'[]', b'null', b'{"idempotency_key": null}', b'\x00\x01',
        json.dumps({'idempotency_key': 'k', 'title': ['x'], 'objective': {'o': 1}}).encode(),
        json.dumps({'idempotency_key': 'k', 'code': 5, 'platform': 'web'}).encode(),
        json.dumps({'idempotency_key': 'k' * 5000}).encode()]
PATH_JUNK = ['x', 'msn_', '..', '%00', 'msn_' + 'A' * 300, '%E2%98%83']


@pytest.mark.parametrize('route', routes.ROUTES, ids=lambda r: '%s %s' % (r.method, r.path))
def test_no_input_to_any_route_is_a_500(tc, route):
    rnd = random.Random(route.path)
    paths = [route.path]
    if '{id}' in route.path:
        paths = [route.path.replace('{id}', p) for p in PATH_JUNK]
    if route.path.endswith('/*'):
        paths = [route.path[:-1] + p for p in PATH_JUNK]
    queries = ['', '?after=-5', '?after=99999999999999999999', '?limit=x', '?state=%00',
               '?after=1&after=x', '?' + ''.join(rnd.choice('&=%x') for _ in range(20))]
    for path in paths:
        for q in queries:
            for raw in (JUNK if route.method == 'POST' else [None]):
                for token in (tc.token, None):
                    if route.path == routes.STREAM:          # a 200 here streams forever
                        s = SSEClient(tc.base_url, token, after=q[len('?after='):] if
                                      q.startswith('?after=') else None)
                        status = s.status
                        s.close()
                    else:
                        status = request(tc.base_url, route.method, path + q, raw=raw,
                                         token=token).status
                    assert status < 500, (route.method, path + q, raw, status)
