"""T-1348 · highest-risk test gaps in claude_sessions/hooks.py 1161-1211.

Slice: `_move` (1161-1173) and `_move_across` (1176-1211) at tip 10d688c0.
Selected branches, ranked (denial first, then boundaries, then error paths):

 1. 1196-1197 — a negative index passes `idx >= len(entries)` and `_move` pops
    the LAST hook. Strict xfail: the guard has no lower bound.
 2. 1196-1197 — an index equal to or past len(entries) returns False, no write.
 3. 1194-1196 — entries under the event that are not a list are refused, no write.
 4. 1198-1201 — explicit cfgdir: `_move` returning None gives False and no `_save`.
    The guard at 1196 already refuses every index `_move` refuses, so this is
    reached only by patching `_move`.
 5. 1202-1210 — fan-out: an account without the hook is never written.
 6. 1206-1209 — the `break` after the first identical entry: a second identical
    copy in the same account stays in place.
 7. 1209 — `moved = _save(s, d) or moved`: a failed save in one account does not
    erase the success in another.
 8. 1163-1167 — `_move` with a missing src_key or event returns None, dst untouched.
 9. 1169-1170 — emptying the last entry drops the event key; a remaining entry keeps it.
10. 1171-1172 — dst_key None removes the entry outright; with dst_key it is
    appended to the end of dst's event list.

Seams: `hooks.settings_path` and `hooks.account_dirs` point into tmp_path. `_save`
is spied only where a test needs it. No real Claude config dir, no subprocess.
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import hooks

A = {'hooks': [{'type': 'command', 'command': 'echo alpha'}]}
B = {'hooks': [{'type': 'command', 'command': 'echo beta'}]}
C = {'hooks': [{'type': 'command', 'command': 'echo gamma'}]}


@pytest.fixture
def accounts(monkeypatch, tmp_path):
    default = tmp_path / 'default'
    other = tmp_path / 'other'
    default.mkdir()
    other.mkdir()
    monkeypatch.setattr(hooks, 'settings_path', str(default / 'settings.json'))
    monkeypatch.setattr(hooks, 'account_dirs',
                        lambda: [('default', str(default)), ('other', str(other))])
    return default, other


def _put(directory, obj):
    (directory / 'settings.json').write_text(json.dumps(obj), encoding='utf-8')


def _raw(directory):
    return (directory / 'settings.json').read_text(encoding='utf-8')


def _get(directory):
    return json.loads(_raw(directory))


def test_a_negative_index_is_refused_not_resolved_to_the_last_hook(accounts):
    default, _ = accounts
    _put(default, {'hooks': {'Stop': [A, B]}})
    assert hooks.set_hook_enabled('Stop', -1, False) is False
    assert _get(default)['hooks']['Stop'] == [A, B]


@pytest.mark.parametrize('index', [1, 5])
def test_an_index_at_or_past_the_end_writes_nothing(accounts, index):
    default, _ = accounts
    _put(default, {'hooks': {'Stop': [A]}})
    before = _raw(default)
    assert hooks.set_hook_enabled('Stop', index, False) is False
    assert _raw(default) == before


def test_an_event_whose_entries_are_not_a_list_is_refused_without_a_write(accounts):
    default, _ = accounts
    _put(default, {'hooks': {'Stop': A}})
    before = _raw(default)
    assert hooks.set_hook_enabled('Stop', 0, False) is False
    assert _raw(default) == before


def test_a_refused_explicit_account_move_skips_the_save(accounts, monkeypatch):
    default, _ = accounts
    _put(default, {'hooks': {'Stop': [A]}})
    saved = []
    monkeypatch.setattr(hooks, '_move', lambda *a, **k: None)
    monkeypatch.setattr(hooks, '_save', lambda s, d=None: saved.append(d) or True)
    assert hooks.set_hook_enabled('Stop', 0, False, cfgdir=str(default)) is False
    assert saved == []


def test_the_fan_out_leaves_an_account_without_the_hook_alone(accounts):
    default, other = accounts
    _put(default, {'hooks': {'Stop': [A]}})
    _put(other, {'hooks': {'Notification': [B]}})
    before = _raw(other)
    assert hooks.set_hook_enabled('Stop', 0, False) is True
    assert _raw(other) == before
    assert _get(default)['hooks_disabled']['Stop'] == [A]


def test_only_the_first_identical_copy_in_an_account_moves(accounts):
    default, _ = accounts
    _put(default, {'hooks': {'Stop': [A, A]}})
    assert hooks.set_hook_enabled('Stop', 0, False) is True
    settings = _get(default)
    assert settings['hooks']['Stop'] == [A]
    assert settings['hooks_disabled']['Stop'] == [A]


def test_a_failed_save_in_one_account_keeps_the_success_of_another(accounts, monkeypatch):
    default, other = accounts
    _put(default, {'hooks': {'Stop': [A]}})
    _put(other, {'hooks': {'Stop': [A]}})
    saves = []
    monkeypatch.setattr(hooks, '_save',
                        lambda s, d=None: saves.append(d) or d == str(other))
    assert hooks.set_hook_enabled('Stop', 0, False) is True
    assert saves == [str(default), str(other)]


def test_move_refuses_a_missing_source_key_or_event_and_touches_nothing():
    s = {'hooks': {'Stop': [A]}}
    before = copy.deepcopy(s)
    assert hooks._move(s, 'Stop', 0, 'nope', 'hooks_disabled') is None
    assert hooks._move(s, 'Missing', 0, 'hooks', 'hooks_disabled') is None
    assert s == before


def test_emptying_the_last_entry_drops_the_event_key():
    s = {'hooks': {'Stop': [A]}}
    assert hooks._move(s, 'Stop', 0, 'hooks', 'hooks_disabled') == A
    assert 'Stop' not in s['hooks']
    assert s['hooks_disabled'] == {'Stop': [A]}


def test_a_remaining_entry_keeps_the_event_key():
    s = {'hooks': {'Stop': [A, B]}}
    hooks._move(s, 'Stop', 0, 'hooks', 'hooks_disabled')
    assert s['hooks'] == {'Stop': [B]}


def test_no_destination_removes_the_entry_outright():
    s = {'hooks': {'Stop': [A, B]}}
    assert hooks._move(s, 'Stop', 0, 'hooks', None) == A
    assert s == {'hooks': {'Stop': [B]}}


def test_a_destination_gets_the_entry_appended_last():
    s = {'hooks': {'Stop': [A, B]}, 'hooks_disabled': {'Stop': [C]}}
    hooks._move(s, 'Stop', 0, 'hooks', 'hooks_disabled')
    assert s['hooks_disabled']['Stop'] == [C, A]
