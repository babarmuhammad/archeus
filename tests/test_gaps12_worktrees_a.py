"""T-1426: claude_sessions/worktrees.py:153-191 real session-to-worktree join at 026ea58e.

Selected candidates, not measured coverage.
Closest existing assertions: tests/test_plugins_worktrees.py replaces
_sessions_by_cwd with a lambda at :253, :271, :287, :321, :333, :343, :354, :433,
:612, so the join itself never runs there. Session listing and stats are faked;
transcripts are empty files under tmp_path and store.transcript_path is real.
"""

import os

import pytest

from claude_sessions import sessions, stats, worktrees


def _key(path):
    return os.path.normcase(os.path.normpath(path))


def _world(monkeypatch, tmp_path, accounts, fail_scan=(), fail_stats=()):
    """accounts: {name: {sid: (mtime, count, stats_dict)}}"""
    folders, rows, info = [], {}, {}
    for name, sess in accounts.items():
        folder = str(tmp_path / name / 'projects' / 'enc-proj')
        os.makedirs(folder, exist_ok=True)
        folders.append((name, folder))
        rows[folder] = []
        for sid, (mtime, count, st) in sess.items():
            open(os.path.join(folder, sid + '.jsonl'), 'w').close()
            rows[folder].append((mtime, sid, 'preview', count))
            info[sid] = st

    def scan(folder):
        if folder in fail_scan:
            raise OSError('scan failed')
        return rows[folder]

    def cached(path):
        sid = os.path.basename(path)[:-len('.jsonl')]
        if sid in fail_stats:
            raise OSError('stats failed')
        return info[sid]

    monkeypatch.setattr(sessions, 'account_folders_for', lambda enc: folders)
    monkeypatch.setattr(sessions, 'scan_sessions', scan)
    monkeypatch.setattr(stats, 'get_session_stats_cached', cached)
    return folders


def _join(tmp_path):
    return worktrees._sessions_by_cwd(str(tmp_path), os.path.join('projects', 'enc-proj'))


def test_newest_session_per_cwd_wins(monkeypatch, tmp_path):
    cwd = str(tmp_path / 'wt-a')
    for order in (['new', 'old'], ['old', 'new']):
        spec = {'old': (100.0, 1, {'cwd': cwd}), 'new': (200.0, 2, {'cwd': cwd})}
        _world(monkeypatch, tmp_path, {'a': {sid: spec[sid] for sid in order}})
        assert _join(tmp_path)[_key(cwd)]['sid'] == 'new'


def test_cwd_key_normalises_trailing_separator_and_dot(monkeypatch, tmp_path):
    wt = str(tmp_path / 'wt')
    _world(monkeypatch, tmp_path, {'a': {
        's1': (1.0, 1, {'cwd': wt}),
        's2': (2.0, 1, {'cwd': wt + os.sep}),
        's3': (3.0, 1, {'cwd': os.path.join(wt, '.')})}})
    out = _join(tmp_path)
    assert set(out) == {_key(wt)}
    assert out[_key(wt)]['sid'] == 's3'


def test_equal_mtime_keeps_first_seen(monkeypatch, tmp_path):
    cwd = str(tmp_path / 'wt')
    _world(monkeypatch, tmp_path, {'a': {
        'first': (50.0, 1, {'cwd': cwd}), 'second': (50.0, 1, {'cwd': cwd})}})
    assert _join(tmp_path)[_key(cwd)]['sid'] == 'first'


def test_stats_failure_skips_only_that_session(monkeypatch, tmp_path):
    cwd = str(tmp_path / 'wt')
    _world(monkeypatch, tmp_path, {'a': {
        'bad': (300.0, 1, {'cwd': cwd}), 'ok': (100.0, 1, {'cwd': cwd})}},
        fail_stats={'bad'})
    assert _join(tmp_path)[_key(cwd)]['sid'] == 'ok'


def test_blank_cwd_is_skipped(monkeypatch, tmp_path):
    _world(monkeypatch, tmp_path, {'a': {
        'empty': (1.0, 1, {'cwd': ''}), 'spaces': (2.0, 1, {'cwd': '   '})}})
    assert _join(tmp_path) == {}


def test_no_project_folder_or_lookup_error_gives_empty_board(monkeypatch, tmp_path):
    _world(monkeypatch, tmp_path, {'a': {'s': (1.0, 1, {'cwd': str(tmp_path)})}})
    assert worktrees._sessions_by_cwd(str(tmp_path), None) == {}

    def boom(enc):
        raise RuntimeError('lookup failed')

    monkeypatch.setattr(sessions, 'account_folders_for', boom)
    assert _join(tmp_path) == {}


def test_one_account_scan_failure_does_not_stop_others(monkeypatch, tmp_path):
    cwd = str(tmp_path / 'wt')
    folders = _world(monkeypatch, tmp_path, {
        'a': {'lost': (1.0, 1, {'cwd': cwd})},
        'b': {'kept': (2.0, 3, {'cwd': cwd})}},
        fail_scan={str(tmp_path / 'a' / 'projects' / 'enc-proj')})
    assert [name for name, _f in folders] == ['a', 'b']
    got = _join(tmp_path)[_key(cwd)]
    assert (got['sid'], got['account'], got['msgs']) == ('kept', 'b', 3)


def test_row_fields_and_stat_defaults(monkeypatch, tmp_path):
    cwd = str(tmp_path / 'wt')
    _world(monkeypatch, tmp_path, {'a': {'s': (42.5, 7, {'cwd': cwd})}})
    row = _join(tmp_path)[_key(cwd)]
    assert row == {'sid': 's', 'mtime': 42.5, 'account': 'a', 'msgs': 7,
                   'branch': '', 'title': '',
                   'cfgdir': str(tmp_path / 'a')}


def test_cfgdir_is_two_levels_above_session_folder(monkeypatch, tmp_path):
    cwd = str(tmp_path / 'wt')
    _world(monkeypatch, tmp_path, {'home': {'s': (1.0, 1, {'cwd': cwd, 'branch': 'main', 'title': 'T'})}})
    row = _join(tmp_path)[_key(cwd)]
    assert row['cfgdir'] == str(tmp_path / 'home')
    assert (row['branch'], row['title']) == ('main', 'T')


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/worktrees.py:175 store.transcript_path is outside the try at "
    ":176; store.py:92-94 raises ValueError for a stem that is not an encoded id, "
    "and board() at :212 has no guard, so one odd .jsonl name aborts the join"))
def test_unparseable_session_id_is_skipped_not_fatal(monkeypatch, tmp_path):
    cwd_good = str(tmp_path / 'wt-good')
    _world(monkeypatch, tmp_path, {'a': {
        'bad name': (300.0, 1, {'cwd': str(tmp_path / 'wt-bad')}),
        'good': (100.0, 1, {'cwd': cwd_good})}})
    assert _join(tmp_path)[_key(cwd_good)]['sid'] == 'good'
