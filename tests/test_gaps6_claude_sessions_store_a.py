"""T-1271: claude_sessions/store.py:26-118 at 6bbd3b44 (wire path validation before filesystem dispatch).

Selected probes, denial first, then boundaries, then error paths:
72 project_folder refuses wire enc before any path is built (test_project_folder_refuses_wire_enc_before_any_path_is_built)
59 is_encoded accepts exactly ASCII alnum and hyphen (test_is_encoded_accepts_only_ascii_alnum_and_hyphen)
54 workfile is a pure join and creates nothing (test_workfile_is_pure_join_and_creates_nothing)
40 workdir marker error propagates (test_workdir_error_propagates_and_returns_no_directory)
87 transcript_path dispatches on the folder's harness (test_transcript_path_dispatches_on_folder_harness_not_active_account)
92 direct Claude sid cannot escape the folder (test_direct_claude_transcript_sid_cannot_escape_folder, strict xfail)
105 missing projects root returns [] before listing (test_missing_projects_root_returns_empty_without_listing)
109 non-directory entry skipped before the decoder (test_non_directory_entry_skipped_before_decoder)
112 unresolved actual path excluded before getmtime (test_unresolved_project_excluded_before_getmtime)
111 decoder gets the exact folder of its own home (test_decoder_gets_exact_folder_per_home)
118 _has_project_claude validates enc before isdir (test_has_project_claude_rejects_wire_enc_before_isdir)
"""

import os

import pytest

from claude_sessions import config, paths, store


def _refuse(*_a, **_k):
    raise AssertionError('filesystem touched')


def test_project_folder_refuses_wire_enc_before_any_path_is_built(monkeypatch, tmp_path):
    monkeypatch.setattr(store.os.path, 'isdir', _refuse)
    for bad in ['', '.', '..', 'a/b', 'a\\b', '/abs', '../x', 'C:x']:
        with pytest.raises(ValueError):
            store.project_folder(str(tmp_path), bad)
        with pytest.raises(ValueError):
            store.session_file(str(tmp_path), bad, 'abc')


def test_is_encoded_accepts_only_ascii_alnum_and_hyphen():
    assert store.is_encoded('C-work-a9')
    assert store.is_encoded('-')
    assert store.is_encoded('A')
    assert not store.is_encoded('')
    assert not store.is_encoded('a b')
    assert not store.is_encoded('a.b')
    assert not store.is_encoded('\t')
    assert not store.is_encoded('é')
    assert not store.is_encoded('١')


def test_workfile_is_pure_join_and_creates_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, '_ensure_dir', _refuse)
    proj = str(tmp_path / 'proj')
    assert store.workfile(proj, 'memory', 'graph.json') == \
        os.path.join(proj, config.WORKDIR, 'memory', 'graph.json')
    assert not os.path.exists(os.path.join(proj, config.WORKDIR))


def test_workdir_error_propagates_and_returns_no_directory(monkeypatch, tmp_path):
    calls = []

    def failing(d):
        calls.append(d)
        raise OSError('marker not writable')

    monkeypatch.setattr(config, '_ensure_dir', failing)
    proj = str(tmp_path / 'proj')
    with pytest.raises(OSError):
        store.workdir(proj)
    assert calls == [os.path.join(proj, config.WORKDIR)]


def test_transcript_path_dispatches_on_folder_harness_not_active_account(monkeypatch, tmp_path):
    folder = str(tmp_path / 'acct' / 'projects' / 'C-work-a')
    seen = {}

    def of_path(path):
        seen['of'] = path
        return {'id': 'codex'}

    def impl(key, hid=None):
        seen['key'] = (key, hid)
        return lambda f, sid: '/rollouts/opaque-' + sid

    monkeypatch.setattr(store._harnesses, 'of_path', of_path)
    monkeypatch.setattr(store._harnesses, 'impl', impl)
    monkeypatch.setattr(config, 'config_dir', str(tmp_path / 'other'))
    assert store.transcript_path(folder, 'thr1') == '/rollouts/opaque-thr1'
    assert seen == {'of': folder, 'key': ('transcript_path', 'codex')}


@pytest.mark.xfail(strict=True, reason=(
    "store.py:92 _transcript_claude joins the wire sid unchecked, while "
    "store.py:183 session_file validates the same wire value before joining it"))
def test_direct_claude_transcript_sid_cannot_escape_folder(monkeypatch, tmp_path):
    folder = os.path.abspath(str(tmp_path / 'acct' / 'projects' / 'C-work-a'))
    monkeypatch.setattr(store._harnesses, 'of_path', lambda p: {'id': 'claude'})
    monkeypatch.setattr(store._harnesses, 'impl', lambda key, hid=None: store._transcript_claude)
    out = os.path.abspath(store.transcript_path(folder, '../../secret'))
    assert os.path.commonpath([out, folder]) == folder


def test_missing_projects_root_returns_empty_without_listing(monkeypatch, tmp_path):
    home = str(tmp_path / 'acct')
    monkeypatch.setattr(store.os, 'listdir', _refuse)
    monkeypatch.setattr(store.os.path, 'getmtime', _refuse)
    monkeypatch.setattr(paths, 'find_actual_path', _refuse)
    assert store._projects_claude(home) == []


def test_non_directory_entry_skipped_before_decoder(monkeypatch, tmp_path):
    home = str(tmp_path / 'acct')
    root = store.projects_root(home)
    os.makedirs(os.path.join(root, 'C-work-a'))
    with open(os.path.join(root, 'stray.txt'), 'w', encoding='utf-8', newline='') as f:
        f.write('not a project\n')
    decoded = []

    def find(enc, folder=None):
        decoded.append(folder)
        return 'W-' + enc

    monkeypatch.setattr(paths, 'find_actual_path', find)
    got = store._projects_claude(home)
    assert [enc for _m, _a, enc in got] == ['C-work-a']
    assert decoded == [os.path.join(root, 'C-work-a')]


def test_unresolved_project_excluded_before_getmtime(monkeypatch, tmp_path):
    home = str(tmp_path / 'acct')
    root = store.projects_root(home)
    os.makedirs(os.path.join(root, 'C-work-a'))
    os.makedirs(os.path.join(root, 'C-work-b'))
    stat_calls = []
    real_getmtime = os.path.getmtime

    def spy_getmtime(p):
        stat_calls.append(p)
        return real_getmtime(p)

    monkeypatch.setattr(store.os.path, 'getmtime', spy_getmtime)
    monkeypatch.setattr(paths, 'find_actual_path',
                        lambda enc, folder=None: '' if enc == 'C-work-b' else 'W-' + enc)
    got = store._projects_claude(home)
    assert [enc for _m, _a, enc in got] == ['C-work-a']
    assert stat_calls == [os.path.join(root, 'C-work-a')]


def test_decoder_gets_exact_folder_per_home(monkeypatch, tmp_path):
    h1, h2 = str(tmp_path / 'one'), str(tmp_path / 'two')
    for h in (h1, h2):
        os.makedirs(os.path.join(store.projects_root(h), 'C-same'))
    monkeypatch.setattr(paths, 'find_actual_path',
                        lambda enc, folder=None: 'actual:' + folder)
    got1 = store._projects_claude(h1)
    got2 = store._projects_claude(h2)
    assert got1[0][1] == 'actual:' + os.path.join(store.projects_root(h1), 'C-same')
    assert got2[0][1] == 'actual:' + os.path.join(store.projects_root(h2), 'C-same')


def test_has_project_claude_rejects_wire_enc_before_isdir(monkeypatch, tmp_path):
    checked = []
    monkeypatch.setattr(store.os.path, 'isdir', lambda p: checked.append(p) or True)
    with pytest.raises(ValueError):
        store._has_project_claude(str(tmp_path), '..')
    assert checked == []
