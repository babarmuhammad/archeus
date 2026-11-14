"""T-1420: claude_sessions/diffview.py snapshot-version helpers, lines 139-214.

Ranked candidate branches, fail-closed and data-loss first:
1. _trim_versions 206-211   numeric, not string, ordering: keeps 100 and 10, removes 9
2. _version_files 197-200   only all-digit middles are versions; 1a, -5 and prev.prev survive
3. _version_files 197       key 'a' never trims the files of key 'a.1'
4. _trim_versions 208-211   a locked (OSError) old version does not stop the trim
5. _version_files 195-202   missing or unlistable dir: [] and a silent no-op
6. _read_index 158-164      non-list JSON, null, corrupt JSON and bad UTF-8 read as empty
7. record 176-181           failed first write falls through to the next dir, no index there
8. _candidate_dirs 139-145  empty paths are skipped, project dir first, (None, None) writes nothing
9. _read_text / record 179  old=None writes an empty snapshot, not the text 'None'
10. record 182-184          the index keeps the newest 40 rows in order

Not written: a same-second double record() for one key. No single operation in
claude_md.py calls record() twice for 'claude_md' (every fallback in
ai_scaffold_claude_md returns after scaffold_claude_md), so no strict xfail.
"""

import os

import pytest

from claude_sessions import diffview


SUB = diffview._SNAP_SUBDIR
INDEX = diffview._INDEX


@pytest.fixture
def snap(tmp_path, monkeypatch):
    d = tmp_path / 'snap'
    d.mkdir()
    monkeypatch.setattr(diffview, 'KEEP_VERSIONS', 2)
    return str(d)


def _touch(d, *names):
    for nm in names:
        with open(os.path.join(d, nm), 'w', encoding='utf-8') as f:
            f.write(nm)


def _names(d):
    return sorted(os.listdir(d))


def test_trim_keeps_newest_by_numeric_timestamp(snap):
    _touch(snap, 'k.9.prev', 'k.10.prev', 'k.100.prev', 'k.prev')
    diffview._trim_versions(snap, 'k')
    assert _names(snap) == ['k.10.prev', 'k.100.prev', 'k.prev']


def test_trim_never_removes_non_numeric_names(snap, monkeypatch):
    monkeypatch.setattr(diffview, 'KEEP_VERSIONS', 0)
    _touch(snap, 'k.1.prev', 'k.1a.prev', 'k.-5.prev', 'k.prev.prev', 'k.prev')
    diffview._trim_versions(snap, 'k')
    assert _names(snap) == ['k.-5.prev', 'k.1a.prev', 'k.prev', 'k.prev.prev']


def test_key_prefix_collision_does_not_trim_other_key(snap, monkeypatch):
    monkeypatch.setattr(diffview, 'KEEP_VERSIONS', 0)
    _touch(snap, 'a.2.prev', 'a.1.5.prev')
    diffview._trim_versions(snap, 'a')
    assert _names(snap) == ['a.1.5.prev']
    diffview._trim_versions(snap, 'a.1')
    assert _names(snap) == []


def test_locked_old_version_does_not_stop_trim(snap, monkeypatch):
    _touch(snap, 'k.1.prev', 'k.2.prev', 'k.3.prev')
    real_remove = os.remove
    locked = os.path.join(snap, 'k.2.prev')

    def remove(p):
        if p == locked:
            raise PermissionError(13, 'locked', p)
        real_remove(p)

    monkeypatch.setattr(diffview.os, 'remove', remove)
    diffview._trim_versions(snap, 'k')
    assert _names(snap) == ['k.2.prev', 'k.3.prev']


def test_missing_snapshot_dir_trims_nothing(tmp_path):
    missing = str(tmp_path / 'nope')
    assert diffview._version_files(missing, 'k') == []
    diffview._trim_versions(missing, 'k')
    assert not os.path.exists(missing)


@pytest.mark.parametrize('payload', [
    b'{"a": 1}',
    b'"text"',
    b'null',
    b'{bad json',
    b'\xff\xfe\x00 not utf-8',
])
def test_read_index_non_list_or_corrupt_is_empty(snap, payload):
    with open(os.path.join(snap, INDEX), 'wb') as f:
        f.write(payload)
    assert diffview._read_index(snap) == []


def test_failed_write_falls_through_to_next_dir(tmp_path, monkeypatch):
    proj = tmp_path / 'proj'
    folder = tmp_path / 'folder'
    dir_a = os.path.join(str(proj), SUB)
    dir_b = os.path.join(str(folder), SUB)
    real_write = diffview._c.write_atomic

    def write(path, text, mode=None):
        if path.startswith(dir_a + os.sep):
            return False
        return real_write(path, text, mode=mode)

    monkeypatch.setattr(diffview._c, 'write_atomic', write)
    assert diffview.record(str(proj), str(folder), 'k', 'old', 'new') is True
    assert not os.path.exists(os.path.join(dir_a, INDEX))
    assert _names(dir_a) == []
    assert os.path.exists(os.path.join(dir_b, INDEX))


def test_candidate_dirs_skips_empty_and_orders_project_first(tmp_path):
    assert diffview._candidate_dirs('', '') == []
    assert diffview._candidate_dirs(None, None) == []
    assert diffview._candidate_dirs('P', 'F') == [os.path.join('P', SUB), os.path.join('F', SUB)]
    assert diffview._candidate_dirs('', 'F') == [os.path.join('F', SUB)]
    assert diffview.record(None, None, 'k', 'old', 'new') is False


def test_none_old_writes_empty_snapshot(tmp_path):
    proj = str(tmp_path / 'proj')
    assert diffview.record(proj, None, 'k', None, 'new') is True
    d = os.path.join(proj, SUB)
    with open(os.path.join(d, 'k.prev'), encoding='utf-8') as f:
        assert f.read() == ''


def test_index_keeps_last_forty_rows(tmp_path):
    proj = str(tmp_path / 'proj')
    d = os.path.join(proj, SUB)
    for i in range(40):
        diffview.record(proj, None, 'k', f'v{i}', f'v{i + 1}')
    before = diffview._read_index(d)
    assert len(before) == 40
    diffview.record(proj, None, 'k', 'v40', 'v41')
    after = diffview._read_index(d)
    assert len(after) == 40
    assert after[:-1] == before[1:]
    assert after[-1]['key'] == 'k'
