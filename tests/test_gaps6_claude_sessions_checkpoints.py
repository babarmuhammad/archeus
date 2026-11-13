"""T-1294: claude_sessions/checkpoints.py:33-150 at 6bbd3b44; same current slice.

Selected probes, not measured coverage. Closest: test_ostyles_checkpoints.py.
129 traversal/absolute refusal; :238 checks source text, not escaped reads.
130 numeric filename normalization; :232 uses only integer versions.
135 character limit and OSError; :232 has no bounded read or faults.
99 missing/empty directory composition; :227 covers missing directory alone.
118 unmatched multiple versions; :201 has one renamed key, no orphan total.
80 supported/malformed block mix; :248 excludes Read only.
83 repeated first-touch order; :193 uses unique edited paths.
59 numeric sort/stat race; :193 uses 1,2 without invalid names/stat faults.
116 latest-version ordering/account; :193 does not fix snapshot mtimes.
145 missing versus empty diff; :232 compares two nonempty versions.
"""

import io
import os
from types import SimpleNamespace

import pytest

from claude_sessions import checkpoints as c, transcripts


@pytest.mark.xfail(strict=True, reason='Unchecked session id escapes history root: claude_sessions/checkpoints.py:129-134')
@pytest.mark.parametrize('absolute', [False, True])
def test_snapshot_sid_escape_refused_without_open(monkeypatch, tmp_path, absolute):
    root = str(tmp_path / 'history')
    sid = str(tmp_path / 'outside') if absolute else os.path.join('..', 'outside')
    monkeypatch.setattr(c, 'store_dir', lambda cfg=None: root)
    monkeypatch.setattr(c, 'os', SimpleNamespace(path=SimpleNamespace(
        join=os.path.join, isfile=lambda p: True)))
    opened = []
    monkeypatch.setattr(c, 'open', lambda p, **kw: opened.append(p) or io.StringIO('secret'),
                        raising=False)
    try:
        result = c.read_version(sid, 'file', 1, str(tmp_path))
    except ValueError:
        result = None
    assert result is None and opened == []


def test_version_rejects_suffix_before_open_and_normalizes_integer(monkeypatch, tmp_path):
    root = tmp_path / 'history'
    monkeypatch.setattr(c, 'store_dir', lambda cfg=None: str(root))
    checks, opened = [], []
    monkeypatch.setattr(c, 'os', SimpleNamespace(path=SimpleNamespace(
        join=os.path.join, isfile=lambda p: checks.append(p) or True)))
    monkeypatch.setattr(c, 'open', lambda p, **kw: opened.append(p) or io.StringIO('text'),
                        raising=False)
    with pytest.raises(ValueError):
        c.read_version('s', 'file', '1-suffix')
    assert checks == opened == []
    assert c.read_version('s', 'file', '002') == 'text'
    expected = str(root / 's' / f'{c._key("file")}@v2')
    assert checks == opened == [expected]


def test_snapshot_limit_counts_characters_and_read_fault_returns_none(monkeypatch, tmp_path):
    folder = tmp_path / 'file-history' / 's'
    folder.mkdir(parents=True)
    p = folder / f'{c._key("file")}@v1'
    p.write_text('é中🙂tail', encoding='utf-8')
    assert c.read_version('s', 'file', 1, str(tmp_path), limit=3) == 'é中🙂'
    assert c.read_version('s', 'file', 2, str(tmp_path)) is None

    def fail(*a, **k):
        raise OSError('read fault')

    monkeypatch.setattr(c, 'open', fail, raising=False)
    assert c.read_version('s', 'file', 1, str(tmp_path)) is None
    assert p.read_text(encoding='utf-8') == 'é中🙂tail'


def test_missing_then_empty_store_does_not_parse_transcript(monkeypatch, tmp_path):
    monkeypatch.setattr(c, '_edited_paths', lambda p: pytest.fail('empty store parsed'))
    expected = {'recognised': True, 'files': [], 'orphans': 0, 'store': False}
    assert c.history('s', 'synthetic', str(tmp_path)) == expected
    folder = tmp_path / 'file-history' / 's'
    folder.mkdir(parents=True)
    (folder / 'not-a-version').write_bytes(b'ignored')
    assert c.history('s', 'synthetic', str(tmp_path)) == expected


def test_unmatched_versions_count_unique_orphan_keys(monkeypatch, tmp_path):
    folder = tmp_path / 'file-history' / 's'
    folder.mkdir(parents=True)
    for name in ('aaaaaaaa@v1', 'aaaaaaaa@v2', 'bbbbbbbb@v1'):
        (folder / name).write_bytes(b'data')
    monkeypatch.setattr(c, '_edited_paths', lambda p: ['unmatched'])
    assert c.history('s', 'synthetic', str(tmp_path)) == {
        'recognised': False, 'files': [], 'orphans': 2, 'store': True}


def test_edit_block_filter_handles_malformed_outer_content(monkeypatch):
    blocks = [None, 'bad', {'type': 'text'},
              {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': 'read'}},
              {'type': 'tool_use', 'name': 'Bash', 'input': {'file_path': 'bash'}}]
    blocks += [{'type': 'tool_use', 'name': name, 'input': {'file_path': name}}
               for name in ('Write', 'Edit', 'MultiEdit', 'NotebookEdit')]
    seen = []

    def records(path, **kw):
        seen.append(kw)
        return iter([{'message': {'content': {}}}, {'message': {'content': blocks}}])

    monkeypatch.setattr(transcripts, 'iter_json', records)
    assert c._edited_paths('synthetic') == ['Write', 'Edit', 'MultiEdit', 'NotebookEdit']
    assert seen == [{'prefilter': 'file_path'}]


def test_repeated_paths_keep_first_touch_order(monkeypatch):
    records = [{'message': {'content': [{'type': 'tool_use', 'name': 'Edit',
                                        'input': {'file_path': path}}]}}
               for path in ('b', 'a', 'b', 'c', 'a')]
    monkeypatch.setattr(transcripts, 'iter_json', lambda *a, **kw: iter(records))
    assert c._edited_paths('synthetic') == ['b', 'a', 'c']


def test_numeric_versions_sort_and_stat_race_is_skipped(monkeypatch, tmp_path):
    folder = str(tmp_path / 'snapshots')
    names = ['aaaaaaaa@v10', 'bad@v2', 'aaaaaaaa@v2', 'aaaaaaaa@v3', 'AAAAAAAA@v1']

    def stat(path):
        if path.endswith('@v3'):
            raise OSError('snapshot vanished')
        return SimpleNamespace(st_size=10 if path.endswith('@v10') else 2, st_mtime=7.5)

    monkeypatch.setattr(c, 'os', SimpleNamespace(listdir=lambda p: names, stat=stat,
                                                path=SimpleNamespace(join=os.path.join)))
    assert c._versions(folder) == {'aaaaaaaa': [
        (2, os.path.join(folder, 'aaaaaaaa@v2'), 2, 7.5),
        (10, os.path.join(folder, 'aaaaaaaa@v10'), 10, 7.5)]}


def test_history_uses_latest_version_mtime_and_explicit_account(monkeypatch, tmp_path):
    cfg = str(tmp_path / 'account')
    target = str(tmp_path / 'account' / 'file-history' / 's')
    a, b = str(tmp_path / 'a'), str(tmp_path / 'b')
    seen = []
    monkeypatch.setattr(c, 'os', SimpleNamespace(path=SimpleNamespace(
        join=os.path.join, basename=os.path.basename, isdir=lambda p: p == target)))

    def versions(path):
        seen.append(path)
        return {c._key(a): [(1, '', 1, 99), (2, '', 2, 4.9)],
                c._key(b): [(1, '', 3, 8.8)], 'orphan': [(1, '', 1, 1), (2, '', 2, 2)]}

    monkeypatch.setattr(c, '_versions', versions)
    monkeypatch.setattr(c, '_edited_paths', lambda p: [a, b])
    got = c.history('s', 'synthetic', cfg)
    assert seen == [target]
    assert [f['name'] for f in got['files']] == ['b', 'a']
    assert got['files'][0]['versions'] == [{'v': 1, 'size': 3, 'mtime': 8}]
    assert got['orphans'] == 1 and got['recognised'] is True


def test_diff_distinguishes_missing_from_valid_empty(monkeypatch, tmp_path):
    path = str(tmp_path / 'nested' / 'file.txt')
    values = {1: '', 2: 'new\n', 3: None}
    calls = []

    def read(sid, fp, v, cfg):
        calls.append((sid, fp, v, cfg))
        return values[v]

    monkeypatch.setattr(c, 'read_version', read)
    cfg = str(tmp_path / 'account')
    assert c.diff_versions('s', path, 1, 2, cfg) == (
        '--- file.txt@v1\n+++ file.txt@v2\n@@ -0,0 +1 @@\n+new\n')
    assert c.diff_versions('s', path, 2, 1, cfg).endswith('-new\n')
    assert c.diff_versions('s', path, 3, 2, cfg) == ''
    assert c.diff_versions('s', path, 1, 3, cfg) == ''
    assert all(sid == 's' and fp == path and home == cfg for sid, fp, v, home in calls)
