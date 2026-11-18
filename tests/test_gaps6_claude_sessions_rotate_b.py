"""T-1285: claude_sessions/rotate.py lines 301-333 and 364-457 at 6bbd3b44.

Selected candidates, not measured coverage. Probes ranked denial/fail-closed
first, then boundaries, then error paths:

1. 318 missing transcript refuses before the GUI launches
   -> test_missing_transcript_refuses_before_the_gui_launches
2. 322 successor forks the absolute transcript into the explicit target
   -> test_successor_forks_the_absolute_transcript_into_the_explicit_target
3. 320 launch opts copied, target injected, shared defaults untouched
   -> test_launch_opts_are_copied_and_the_target_never_leaks_into_the_defaults
4. 379 next_account excludes the current account even on a cold cache
   -> test_next_account_excludes_the_current_on_a_cold_cache
5. 396 same normalised account logs nothing
   -> test_same_account_under_another_spelling_logs_nothing
6. 399 cross-account note carries names and a bounded reason
   -> test_cross_account_note_names_accounts_and_bounds_the_reason
7. 419 token-reader exception marks one row signed out and keeps the rest
   -> test_token_reader_failure_marks_only_that_row_signed_out
8. 427 live row picked by normalised path, numbers from its own account
   -> test_live_row_is_found_by_path_and_carries_its_own_numbers
9. 441 elect equal to live means rotating is False, hook and headless independent
   -> test_rotating_is_false_when_the_live_account_is_kept
10. 454 recent history filters src=rotate before taking the newest eight
    -> test_recent_filters_rotate_before_slicing
11. 455 recent history returns empty when the event reader raises
    -> test_recent_returns_empty_when_the_reader_raises

Closest existing tests. Partly covered, and this file adds the missing
composition only:
1-3 tests/test_rotate_live.py:490 (fork and cfgdir) and :504 (missing transcript
    by one path only); this file adds the None and empty transcript and the
    no-elect assertion (1), and the shared-opts non-mutation (3).
4 tests/test_rotate_live.py:304 and :324 (exclusion, empty answer, warm 0%);
    this file adds the cold cache (no usage entry) and the elect contrast.
5 tests/test_rotate.py:248 (same account, no event); this file adds the
    spelling variant.
6 tests/test_rotate.py:243 (two names logged); this file adds the detail bound.
7 tests/test_rotate.py:289-304 check signed_in on the API, not a raising reader.
8 tests/test_rotate_live.py:515 and tests/test_rotate.py:302 check live and
    enabled; neither checks the blocked reason or the per-row numbers.
9 tests/test_rotate.py:289 checks the cold-cache shape only.
10 and 11 have no direct test.

Every path that would touch a process, a socket or a credential is faked:
gui.launch_session, subprocess.Popen, hooks.across_accounts, events.read and
events.record. Accounts are synthetic dirs under tmp_path.
"""

import json
import os
import subprocess
import time

import pytest

from claude_sessions import config as _c
from claude_sessions import events, gui, hooks, quota, rotate, usage


def _data(pct):
    return {'limits': [{'kind': 'session', 'percent': pct,
                        'resets_at': '2026-09-01T15:00:00Z'}]}


def _account(tmp_path, name, pct=None, token=True):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    if token:
        (d / '.credentials.json').write_text(json.dumps(
            {'claudeAiOauth': {'accessToken': 'tok-' + name,
                               'expiresAt': 9999999999000}}), encoding='utf-8')
    if pct is not None:
        usage._acct_state[str(d)] = {'name': name, 'status': 'ok', 'data': _data(pct)}
    return str(d)


def _settings(monkeypatch, accounts=(), **over):
    s = {'headless_quota': 'prompt', 'rotate_mode': 'ask'}
    s.update(over)
    monkeypatch.setattr(_c, 'load_settings', lambda: dict(s))
    monkeypatch.setattr(_c, 'all_config_dirs',
                        lambda: [(os.path.basename(d), d) for d in accounts])


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    quota.reset()
    monkeypatch.setattr(events, 'path', lambda: str(tmp_path / 'events.jsonl'))
    events._recent.clear()
    monkeypatch.setattr(usage, '_acct_state', {}, raising=False)
    monkeypatch.setattr(quota, '_interactive', lambda: False)
    monkeypatch.setattr(hooks, 'across_accounts', lambda fn, *a, **k: {})
    monkeypatch.setattr(_c, 'config_dir', str(tmp_path / 'live-home'))


# ── continue_session: refuse before launch, fork into the target ──

def test_missing_transcript_refuses_before_the_gui_launches(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(gui, 'launch_session', lambda *a, **k: calls.append(a) or (True, ''))
    monkeypatch.setattr(rotate, 'elect', lambda *a, **k: pytest.fail('elect consulted'))
    target = str(tmp_path / 'work')
    for transcript in (None, '', str(tmp_path / 'gone.jsonl')):
        assert rotate.continue_session(str(tmp_path), transcript, target) == \
            (False, 'no transcript to continue')
    assert calls == []


def test_successor_forks_the_absolute_transcript_into_the_explicit_target(monkeypatch, tmp_path):
    transcript = tmp_path / 's.jsonl'
    transcript.write_text('{}\n', encoding='utf-8')
    target = str(tmp_path / 'work')
    calls = []
    monkeypatch.setattr(gui, 'launch_session',
                        lambda path, enc, choice, opts, **k: calls.append((path, enc, choice, opts)) or (True, ''))
    monkeypatch.setattr(rotate, 'elect', lambda *a, **k: pytest.fail('elect consulted'))
    proj = str(tmp_path / 'proj')
    assert rotate.continue_session(proj, str(transcript), target, encoded='ENC-1') == (True, '')
    (path, enc, choice, opts), = calls
    assert path == proj and enc == 'ENC-1'
    assert choice == 'fork:' + str(transcript) and os.path.isabs(choice[len('fork:'):])
    assert opts['cfgdir'] == _c.resolve_config_dir(target)


def test_launch_opts_are_copied_and_the_target_never_leaks_into_the_defaults(monkeypatch, tmp_path):
    transcript = tmp_path / 's.jsonl'
    transcript.write_text('{}\n', encoding='utf-8')
    shared = {'effort': 'low', 'cfgdir': 'shared-default'}
    monkeypatch.setattr(rotate, '_launch_opts', lambda: shared)
    seen = []
    monkeypatch.setattr(gui, 'launch_session',
                        lambda path, enc, choice, opts, **k: seen.append((enc, opts)) or (True, ''))
    target = str(tmp_path / 'work')
    rotate.continue_session(str(tmp_path), str(transcript), target, encoded='ENC-KEEP')
    assert shared == {'effort': 'low', 'cfgdir': 'shared-default'}
    (enc, opts), = seen
    assert enc == 'ENC-KEEP'
    assert opts is not shared and opts['cfgdir'] == _c.resolve_config_dir(target)
    assert opts['effort'] == 'low'


# ── next_account vs elect on a cold cache ──

def test_next_account_excludes_the_current_on_a_cold_cache(monkeypatch, tmp_path):
    cur = _account(tmp_path, 'a')                  # no usage entry: cold cache
    other = _account(tmp_path, 'b', pct=10)
    _settings(monkeypatch, [cur, other])
    assert rotate.next_account(exclude=cur) == other
    assert rotate.elect(cur) == cur                # sticky: the same question, the other answer


def test_no_alternative_returns_empty_not_the_current_account(monkeypatch, tmp_path):
    cur = _account(tmp_path, 'a', pct=10)
    _settings(monkeypatch, [cur])
    assert rotate.next_account(exclude=cur) == ''
    assert rotate.elect(cur) == cur


# ── note(): same account is silent, cross-account is names and a bounded reason ──

def test_same_account_under_another_spelling_logs_nothing(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(events, 'record', lambda *a, **k: seen.append((a, k)) or True)
    a = str(tmp_path / 'acct')
    _settings(monkeypatch, [a])
    assert rotate.note(a, a + os.sep, 'why') is False
    assert rotate.note(a, a, 'why') is False
    assert seen == []


def test_cross_account_note_names_accounts_and_bounds_the_reason(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(events, 'record',
                        lambda src, msg, **k: seen.append((src, msg, k)) or True)
    a, b = _account(tmp_path, 'a'), _account(tmp_path, 'b')
    _settings(monkeypatch, [a, b])
    assert rotate.note(a, b, 'x' * 500) is True
    (src, msg, kw), = seen
    assert src == 'rotate' and msg == 'account a -> b'
    assert kw['level'] == 'info' and len(kw['detail']) == 200
    assert str(tmp_path) not in msg


# ── state(): the card reads only the cache and the settings file ──

def test_token_reader_failure_marks_only_that_row_signed_out(monkeypatch, tmp_path):
    a = _account(tmp_path, 'a', pct=10)
    b = _account(tmp_path, 'b', pct=20)
    _settings(monkeypatch, [a, b])

    def token(cfgdir=None):
        if os.path.abspath(cfgdir) == os.path.abspath(a):
            raise RuntimeError('credential reader broke')
        return 'tok-b-secret'
    monkeypatch.setattr(usage, '_read_token', token)
    st = rotate.state()
    rows = {r['name']: r for r in st['accounts']}
    assert set(rows) == {'a', 'b'}
    assert rows['a']['signed_in'] is False and rows['a']['pct'] == 10.0
    assert rows['b']['signed_in'] is True and rows['b']['pct'] == 20.0
    assert 'tok-b-secret' not in json.dumps(st, default=str)


def test_live_row_is_found_by_path_and_carries_its_own_numbers(monkeypatch, tmp_path):
    a = _account(tmp_path, 'a', pct=99)
    b = _account(tmp_path, 'b', pct=10)
    _settings(monkeypatch, [a, b])
    monkeypatch.setattr(_c, 'config_dir', b + os.sep)
    quota._observed[quota._key(a)] = time.time() + 600
    st = rotate.state()
    rows = {r['name']: r for r in st['accounts']}
    assert rows['b']['live'] is True and rows['a']['live'] is False
    assert rows['a']['spent'] is True and rows['a']['blocked'] == 'account rate-limited by Claude'
    assert rows['b']['spent'] is False and rows['b']['blocked'] == ''
    assert st['live_name'] == 'b'


def test_rotating_is_false_when_the_live_account_is_kept(monkeypatch, tmp_path):
    a = _account(tmp_path, 'a', pct=10)
    _settings(monkeypatch, [a], rotate_mode='off', headless_quota='auto')
    monkeypatch.setattr(_c, 'config_dir', a)
    seen = []
    monkeypatch.setattr(hooks, 'across_accounts',
                        lambda fn, *args, **k: seen.append(fn.__name__) or {'a': True})

    def no_process(*a, **k):
        raise AssertionError('state() must not start a process')
    monkeypatch.setattr(subprocess, 'Popen', no_process)
    st = rotate.state()
    assert st['rotating'] is False and st['next'] == a
    assert st['mode'] == 'off' and st['hands_off'] is False
    assert st['hook'] == {'a': True} and seen == ['limit_hook_installed']
    assert st['headless_quota'] == 'auto'


# ── recent(): the rotate filter comes before the slice ──

def test_recent_filters_rotate_before_slicing(monkeypatch, tmp_path):
    rows = [{'src': 'other', 'msg': 'x%d' % i} for i in range(10)]
    rows += [{'src': 'rotate', 'msg': 'account a -> b %d' % i} for i in range(9)]
    limits = []

    def read(limit=200):
        limits.append(limit)
        return rows
    monkeypatch.setattr(events, 'read', read)
    got = rotate.recent()
    assert limits == [200]
    assert [r['msg'] for r in got] == ['account a -> b %d' % i for i in range(8)]


def test_recent_returns_empty_when_the_reader_raises(monkeypatch, tmp_path):
    def read(limit=200):
        raise OSError('log unreadable')
    monkeypatch.setattr(events, 'read', read)
    assert rotate.recent() == []
