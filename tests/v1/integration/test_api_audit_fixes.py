"""Regressions for the loopback API audit of 2026-11-01 (audit-api): each test
is one finding's request, asserting the refusal it should have drawn."""

import json
import os
import threading

import pytest

from archeus.api import auth
from archeus.core.domain import entities, ids
from archeus.core.execution import output
from archeus.harnesses.fake import FakeHarness
from archeus.infra.paths import ExecPaths
from v1.judge.http import TUNNEL, request

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


# ── F8: the step-up attempt limit holds against concurrent requests ──

@pytest.mark.core(remote_hosts=(TUNNEL,))
def test_f8_a_burst_of_wrong_pins_runs_no_more_than_the_limit(tc):
    pin = '482913'
    code = tc.http('POST', '/v1/devices/pair/start', body={'scopes': ['observe', 'control']})
    r = request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                body={'code': code.json()['code'], 'platform': 'android', 'pin': pin})
    token = r.json()['token']
    answers = [None] * 40

    def guess(i):
        r = request(tc.base_url, 'POST', '/v1/rearm', token=token, headers={'Host': TUNNEL},
                    body=dict(_key(), step_up='%06d' % (100000 + i)))
        answers[i] = r.json().get('error')

    threads = [threading.Thread(target=guess, args=(i,)) for i in range(len(answers))]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert answers.count('guard_failed') <= auth.StepUpFailures.LIMIT
    assert request(tc.base_url, 'GET', '/v1/health', token=token,
                   headers={'Host': TUNNEL}).status == 401          # and the fifth revoked it


# ── F5: a string that is not UTF-8 text is refused at the schema ──

def test_f5_a_lone_surrogate_is_a_400_and_stores_nothing(tc):
    r = tc.http('POST', '/v1/missions', body=dict(_key(), title='t', objective='\ud83dbroken'))
    assert (r.status, r.json()['error']) == (400, 'invalid_request')
    assert r.json()['detail'] == {'field': 'objective', 'why': 'is not valid text'}
    assert tc.http('GET', '/v1/missions').json()['missions'] == []
    r = request(tc.base_url, 'POST', '/v1/devices/launch/redeem',
                body={'code': '\ud800', 'platform': 'web'})
    assert r.status == 400 and b'codec' not in r.body


# ── F7: a long stream is read as a bounded tail, not whole ──

def test_f7_a_long_stream_is_read_from_a_window_of_whole_lines(monkeypatch):
    exe = entities.Execution(id=ids.new_id('execution'), task_id=ids.new_id('task'),
                             mission_id=ids.new_id('mission'), harness_id='fake',
                             pid=os.getpid(), create_time=1.0)
    paths = ExecPaths(exe.id)
    os.makedirs(paths.dir)
    with open(paths.stream, 'w', encoding='utf-8') as f:
        for i in range(200):
            f.write(json.dumps({'type': 'text', 'text': 'line %03d' % i + ' ' * 50}) + '\n')
    monkeypatch.setattr(output, 'MAX_BYTES', 2000)
    got = output.read(exe, FakeHarness())
    texts = [e['text'].strip() for e in got['events']]
    assert got['truncated'] and 5 <= len(texts) < 40
    assert texts[-1] == 'line 199' and texts == sorted(texts)           # the newest, whole
    assert got['next_offset'] == os.path.getsize(paths.stream)
    short = output.read(exe, FakeHarness(), got['next_offset'] - 300)
    assert not short['truncated'] and len(short['events']) >= 2         # a short read is not cut


# ── F11: a cursor is ASCII digits ──

def test_f11_a_cursor_in_non_ascii_digits_is_a_400(tc):
    for digits in ('%D9%A3', '%EF%BC%91'):                    # Arabic-Indic three, fullwidth one
        r = tc.http('GET', '/v1/events?after=%s&limit=1' % digits)
        assert (r.status, r.json()['detail']['field']) == (400, 'cursor')
    assert tc.http('GET', '/v1/events?after=0&limit=1').status == 200
