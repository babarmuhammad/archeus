"""Regressions for the loopback API audit of 2026-11-01 (audit-api): each test
is one finding's request, asserting the refusal it should have drawn."""

import json
import os
import threading
import types

import pytest

from archeus.api import auth
from archeus.core.domain import entities, ids
from archeus.core.execution import output
from archeus.core.redact import redact_json
from archeus.harnesses import base
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


@pytest.mark.parametrize('kind', ['launch', 'pair'])
def test_r7_a_revoke_landing_just_before_the_commit_still_refuses_the_redeem(tc, monkeypatch, kind):
    """The minter is revoked after the code was spent and before register_device
    commits (the token is made in between): the command checks the minter."""
    from archeus.api import routes
    device, token = _launch_device(tc, ['observe', 'admin'])
    path, err = (('/v1/devices/launch', 'invalid_launch_code') if kind == 'launch'
                 else ('/v1/devices/pair', 'invalid_pairing_code'))
    code = tc.http('POST', path + ('/code' if kind == 'launch' else '/start'), token=token,
                   body={'scopes': ['observe']}).json()['code']
    before = len(tc.http('GET', '/v1/devices').json()['devices'])
    real = routes.auth.new_token

    def revoking():
        monkeypatch.setattr(routes.auth, 'new_token', real)
        assert tc.http('POST', '/v1/devices/%s/revoke' % device, body=_key()).status == 200
        return real()

    monkeypatch.setattr(routes.auth, 'new_token', revoking)
    r = request(tc.base_url, 'POST', path + '/redeem', body={'code': code, 'platform': 'web'})
    assert (r.status, r.json()['error']) == (401, err)
    assert len(tc.http('GET', '/v1/devices').json()['devices']) == before


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


@pytest.mark.core(remote_hosts=(TUNNEL,))
def test_r5_a_revoke_that_fails_locks_the_device_and_the_next_request_retries_it(tc, monkeypatch):
    from archeus.api import routes
    pin = '482913'
    code = tc.http('POST', '/v1/devices/pair/start', body={'scopes': ['observe', 'control']})
    r = request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                body={'code': code.json()['code'], 'platform': 'android', 'pin': pin})
    token, device = r.json()['token'], r.json()['device_id']
    real, calls = routes.commands.revoke_device, []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('writer busy')
        return real(*a, **k)

    monkeypatch.setattr(routes.commands, 'revoke_device', flaky)

    def wrong(i):
        return request(tc.base_url, 'POST', '/v1/rearm', token=token, headers={'Host': TUNNEL},
                       body=dict(_key(), step_up='%06d' % (100000 + i))).status

    assert [wrong(i) for i in range(5)] == [422] * 4 + [500]
    # the sixth guess is not tried (review of fix batches 9 and 10, F4): it is refused, and retries
    assert wrong(5) == 429 and len(calls) == 2
    states = {d['id']: d['state'] for d in tc.http('GET', '/v1/devices').json()['devices']}
    assert states[device] == 'REVOKED'
    assert request(tc.base_url, 'GET', '/v1/health', token=token,
                   headers={'Host': TUNNEL}).status == 401


# ── F5: a string that is not UTF-8 text is refused at the schema ──

def test_f5_a_lone_surrogate_is_a_400_and_stores_nothing(tc):
    r = tc.http('POST', '/v1/missions', body=dict(_key(), title='t', objective='\ud83dbroken'))
    assert (r.status, r.json()['error']) == (400, 'invalid_request')
    assert r.json()['detail'] == {'field': 'objective', 'why': 'is not valid text'}
    assert tc.http('GET', '/v1/missions').json()['missions'] == []
    r = request(tc.base_url, 'POST', '/v1/devices/launch/redeem',
                body={'code': '\ud800', 'platform': 'web'})
    assert r.status == 400 and b'codec' not in r.body


def test_r11_a_lone_surrogate_in_a_free_form_object_is_a_400_and_stores_nothing(tc):
    rule = dict(scope_level='USER', action_class='write_repo', decision='ASK')
    for extra in ({'match': {'path_glob': '\ud800'}}, {'match': {'a': ['x', {'k': 'y\udfff'}]}},
                  {'boundary': {'\ud800': 1}}):
        r = tc.http('POST', '/v1/policies/rules', body=dict(_key(), **rule, **extra))
        assert (r.status, r.json()['error']) == (400, 'invalid_request'), extra
        assert r.json()['detail']['why'] == 'is not valid text'
    ok = tc.http('POST', '/v1/policies/rules', body=dict(_key(), **rule, match={'path_glob': '*.py'}))
    assert ok.status == 200


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


class _Adapter:
    def __init__(self, events):
        self.events = events

    def inspect(self, handle, offset):
        return types.SimpleNamespace(events=self.events, offset=offset + 1)


def _exe():
    return entities.Execution(id=ids.new_id('execution'), task_id=ids.new_id('task'),
                              mission_id=ids.new_id('mission'), harness_id='fake',
                              pid=os.getpid(), create_time=1.0)


def test_r6_only_the_tail_is_redacted_not_every_event_before_it(monkeypatch):
    seen = []
    monkeypatch.setattr(output, 'redact_json', lambda event: seen.append(event) or event)
    events = [{'type': 'text', 'n': i} for i in range(output.MAX_EVENTS + 50)]
    got = output.read(_exe(), _Adapter(events))
    assert len(seen) == output.MAX_EVENTS and got['truncated']
    assert [e['n'] for e in got['events']] == list(range(50, output.MAX_EVENTS + 50))
    short = output.read(_exe(), _Adapter(events[:3]))
    assert not short['truncated'] and len(short['events']) == 3


def test_r1_a_secret_ending_an_event_string_does_not_break_the_tail():
    events = [{'type': 'assistant', 'text': 'run curl -u admin:SYNTHhunter2'},
              {'type': 'assistant', 'text': 'aws_secret_access_key=SYNTH0123'},
              {'type': 'assistant', 'text': 'key -----BEGIN PRIVATE KEY----- SYNTHbody'}]
    got = output.read(_exe(), _Adapter(events))
    assert [e['type'] for e in got['events']] == ['assistant'] * 3
    assert 'SYNTH' not in json.dumps(got)


JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcDEFghi123'


def test_a_jwt_after_a_newline_or_tab_is_redacted_in_the_tail():
    # review of fix batches 9 and 10, F2: the dump spelt the newline as a backslash
    # and an `n`, and the JWT's left edge saw that `n`
    events = [{'type': 'stderr', 'text': 'token:\n' + JWT},
              {'type': 'stderr', 'text': 'a\tb\r\n' + JWT}]
    got = output.read(_exe(), _Adapter(events))
    assert 'abcDEFghi123' not in json.dumps(got)
    assert got['events'][0]['text'] == 'token:\n[redacted]'


def test_a_newline_before_a_token_prefix_cannot_break_the_tail():
    # F3: the match used to start at the `n` of the dumped newline and leave a lone
    # backslash, which is not valid JSON, so one stderr line made every read of the
    # execution fail. Nothing here is a secret: the strings come back as they went in.
    events = [{'type': 'stderr', 'text': 'x\npm_AAAAAAAAAAAAAAAA'},
              {'type': 'stderr', 'text': 'x\rk_live_AAAAAAAAAAAAAAAA\bearer abcdefgh'}]
    got = output.read(_exe(), _Adapter(events))
    assert [e['text'] for e in got['events']] == [e['text'] for e in events]


def test_a_key_in_a_prefixed_or_escaped_dump_is_redacted_in_the_tail():
    # F1: a Read tool's arrows, a docker prefix or a doubly escaped string ended the match early
    body = ['-----BEGIN OPENSSH PRIVATE KEY-----', 'QyNTUxOQAAACDsecretsecretsecretsecret',
            '-----END OPENSSH PRIVATE KEY-----']
    forms = ['\n'.join('%6d→%s' % (i, line) for i, line in enumerate(body)),
             '\n'.join('web-1  | ' + line for line in body),
             '\n'.join('> ' + line for line in body),
             json.dumps('\n'.join(body)), json.dumps(json.dumps('\n'.join(body)))]
    got = output.read(_exe(), _Adapter([{'type': 'stderr', 'text': f + ' tail'} for f in forms]))
    assert 'secretsecret' not in json.dumps(got)
    assert all(e['text'].endswith(' tail') for e in got['events'])


# ── F10, F11: an idempotency key is bounded; a cursor is ASCII digits ──

def test_f10_an_idempotency_key_longer_than_128_characters_is_a_400(tc):
    body = {'title': 't', 'objective': 'o'}
    r = tc.http('POST', '/v1/missions', body=dict(body, idempotency_key='k' * 129))
    assert (r.status, r.json()['detail']['field']) == (400, 'idempotency_key')
    assert tc.http('POST', '/v1/missions', body=dict(body, idempotency_key='k' * 128)).status == 200


def test_f11_a_cursor_in_non_ascii_digits_is_a_400(tc):
    for digits in ('%D9%A3', '%EF%BC%91'):                    # Arabic-Indic three, fullwidth one
        r = tc.http('GET', '/v1/events?after=%s&limit=1' % digits)
        assert (r.status, r.json()['detail']['field']) == (400, 'cursor')
    assert tc.http('GET', '/v1/events?after=0&limit=1').status == 200


# ── a private key split over the lines of a stream is still one key ──

_KEY_LINES = ['-----BEGIN PRIVATE KEY-----', 'U1lOVEhfUFJJVkFURV9CT0RZ', 'U1lOVEhfU0VDT05E',
              '-----END PRIVATE KEY-----', 'after the key']


def _stream(lines):
    exe = _exe()
    paths = ExecPaths(exe.id)
    os.makedirs(paths.dir)
    with open(paths.stream, 'w', encoding='utf-8', newline='\n') as f:
        f.write(''.join(line + '\n' for line in lines))
    return exe, paths


def _texts(got):
    return [e['text'] for e in got['events']]


def test_a_key_on_separate_stderr_lines_is_redacted_in_every_line():
    exe, _ = _stream(['before'] + _KEY_LINES)
    got = output.read(exe, FakeHarness())
    assert 'U1lOVEhf' not in json.dumps(got) and _texts(got)[0] == 'before'
    assert _texts(got)[-1] == 'after the key'


@pytest.mark.parametrize('cut', [2, 3, 4])
def test_a_read_that_starts_inside_a_key_redacts_the_rest_of_it(cut):
    exe, paths = _stream(['before'] + _KEY_LINES)
    start = sum(len(line) + 1 for line in (['before'] + _KEY_LINES)[:cut])
    got = output.read(exe, FakeHarness(), start)
    assert 'U1lOVEhf' not in json.dumps(got) and _texts(got)[-1] == 'after the key'


def test_a_window_cut_inside_a_key_redacts_the_rest_of_it(monkeypatch):
    exe, _ = _stream(['x'] * 40 + _KEY_LINES[:3] + ['SYNTHMORE'] * 40 + _KEY_LINES[3:])
    monkeypatch.setattr(output, 'MAX_BYTES', 200)
    got = output.read(exe, FakeHarness())
    assert got['truncated'] and 'SYNTHMORE' not in json.dumps(got) and _texts(got)[-1] == 'after the key'


def test_a_key_over_the_batches_of_a_long_read_is_redacted():
    exe, paths = _stream(_KEY_LINES)
    seen, offset = [], 0
    while True:
        events, end = base.read_stream(paths.stream, offset, 1)
        if end == offset:
            break
        seen += [redact_json(e)['text'] for e in events]
        offset = end
    assert 'U1lOVEhf' not in ''.join(seen) and seen[-1] == 'after the key'


def test_a_key_too_long_to_see_its_start_is_still_redacted(monkeypatch):
    body = ['U1lOVEhfQk9EWV9MSU5F%04d' % i for i in range(30)]
    exe, _ = _stream(['-----BEGIN PRIVATE KEY-----'] + body + ['-----END PRIVATE KEY-----', 'after'])
    monkeypatch.setattr(base, 'KEY_PROBE', 100)
    start = sum(len(line) + 1 for line in body[:20]) + 28
    got = output.read(exe, FakeHarness(), start)
    assert 'U1lOVEhf' not in json.dumps(got) and _texts(got)[-1] == 'after'


@pytest.mark.parametrize('pad', [95, 150])
def test_a_key_that_begins_inside_an_oversized_line_is_redacted_after_it(monkeypatch, pad):
    monkeypatch.setattr(base, 'MAX_LINE', 100)
    exe, _ = _stream(['y' * pad + '-----BEGIN PRIVATE KEY-----' + 'z' * 400, 'SYNTHBODYLINE',
                      '-----END PRIVATE KEY-----', 'after'])
    got = output.read(exe, FakeHarness())
    assert 'SYNTHBODYLINE' not in json.dumps(got) and _texts(got)[-1] == 'after'
