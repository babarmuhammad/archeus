"""Commands are idempotent by key over HTTP, through the ONE P2 mechanism —
the writer's `idempotency_keys` (p3.5b design gate §4, §10 E1–E4)."""

import sqlite3
import threading

from archeus.infra.db import connection

BODY = {'title': 'Once', 'objective': 'exactly once', 'idempotency_key': 'k-1'}


def _missions(tc):
    return tc.http('GET', '/v1/missions').json()['missions']


def test_the_same_key_and_body_replays_the_first_response(tc):
    first = tc.http('POST', '/v1/missions', body=BODY)
    again = tc.http('POST', '/v1/missions', body=BODY)
    assert first.status == again.status == 200
    assert first.body == again.body
    assert [m['id'] for m in _missions(tc)] == [first.json()['id']]


def test_ten_concurrent_duplicates_make_one_mission_and_ten_identical_answers(tc):
    out, gate = [], threading.Barrier(10)

    def post():
        gate.wait()
        out.append(tc.http('POST', '/v1/missions', body=dict(BODY, idempotency_key='race')))
    threads = [threading.Thread(target=post) for _ in range(10)]
    [t.start() for t in threads]
    [t.join(30) for t in threads]
    assert [r.status for r in out] == [200] * 10
    assert len({r.body for r in out}) == 1
    assert len(_missions(tc)) == 1


def test_the_same_key_with_another_body_is_refused_every_time(tc):
    assert tc.http('POST', '/v1/missions', body=BODY).status == 200
    for _ in range(2):
        r = tc.http('POST', '/v1/missions', body=dict(BODY, title='Twice'))
        assert r.status == 400
        assert r.json()['error'] == 'invalid_request'
        assert r.json()['detail']['field'] == 'idempotency_key'
    other = tc.http('POST', '/v1/missions/%s/pause' % _missions(tc)[0]['id'],
                    body={'idempotency_key': 'k-1'})                     # another command
    assert (other.status, other.json()['detail']['field']) == (400, 'idempotency_key')
    assert len(_missions(tc)) == 1


def test_every_command_needs_a_key_and_launch_needs_none(tc):
    mid = tc.http('POST', '/v1/missions', body=BODY).json()['id']
    for path, body in (('/v1/missions', {'title': 't', 'objective': 'o'}),
                       ('/v1/missions/%s/pause' % mid, {}),
                       ('/v1/missions/%s/resume' % mid, {'idempotency_key': ''}),
                       ('/v1/devices/dvc_x/revoke', {'idempotency_key': 7})):
        r = tc.http('POST', path, body=body)
        assert (r.status, r.json()['detail'].get('field')) == (400, 'idempotency_key'), path
    code = tc.http('POST', '/v1/devices/launch/code', body={})
    assert code.status == 200
    with sqlite3.connect(connection.db_path()) as conn:
        keys = [r[0] for r in conn.execute('SELECT command FROM idempotency_keys')]
    assert keys == ['archeus.core.application.commands.create_mission']


def test_a_replay_is_answered_after_a_restart(tc):
    first = tc.http('POST', '/v1/missions', body=BODY)
    tc.restart(kill=False)
    again = tc.http('POST', '/v1/missions', body=BODY)
    assert again.body == first.body and len(_missions(tc)) == 1
