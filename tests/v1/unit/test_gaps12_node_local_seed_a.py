"""T-1437: the uncovered branches of `archeus/node/local.py` lines 2539-2665 inclusive
(`_seed_path`, `_Deadline`, `_blob_id`, `_seed_walk`, `_seed_meta`, `_made`) at tip
026ea58e. No source file is edited.

Ten selected branches, denial and fail-closed first, then boundaries, then error paths:

1. 2542-2543 _seed_path: depth SEED_MAX_DEPTH is accepted, one more is refused; length
   prefix + 1 + len(path) == SEED_MAX_PATH is accepted, one more is refused.
   Catches: either comparison off by one.
2. 2544-2546 _seed_path: a component refused_component() flags is refused, naming the path.
   Catches: the refused_component test removed.
3. 2561-2564 _Deadline.left: time left is returned while positive; zero or negative refuses
   with 'ran past its deadline'. Catches: the boundary inverted or the raise removed.
4. 2576-2578 _blob_id: a multi-chunk file hashes to sha1(b'blob N\\0' + bytes); an expired
   deadline raises mid-file. Catches: the per-chunk left() removed.
5. 2572-2575 _blob_id with seen: a dev, inode or size that differs from the walk refuses before
   any byte is read; a matching lstat lets it through. Catches: the identity test removed or
   one of the three fields dropped.
6. 2587-2599 _seed_walk: the root `.git` is skipped, a nested file named `.git` is seen as an
   entry, directories become ('d',), files ('f', size, id), and the deadline is consulted once
   per listed name. Catches: the skip, the recursion prefix or the per-entry check removed.
7. 2590 _seed_walk root-only skip: the `not rel` clause removed would drop nested `.git` names.
   The walk keeps `sub/.git` as an entry.
8. 2607-2609 _seed_meta: a name outside _SEED_META, or a missing one, raises listing the
   symmetric difference. Catches: the names test or the difference reporting removed.
9. 2610-2616 _seed_meta: HEAD, config and shallow must hold Core's bytes; one differing byte
   refuses; index is only checked as a plain entry. Catches: any of the four byte checks removed.
10. 2633-2645 _made: a present directory is not re-created, an absent one is made with
    os.mkdir, a FileExistsError from a race is swallowed, and an expired deadline raises before
    any mkdir. Catches: the _present test, the except clause or the deadline call removed.

Real files under tmp_path, monkeypatched _clock and seam namespaces only. No git, no subprocess,
no Win32, no network.
"""

import hashlib
import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import local
from archeus.node.local import StoreError


def _blob(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


class _Counting:
    def __init__(self, ok=10 ** 9):
        self.calls, self.ok = 0, ok

    def left(self):
        self.calls += 1
        if self.calls > self.ok:
            raise StoreError('the seed of t ran past its deadline')
        return 1.0


def test_depth_and_length_at_the_limits_are_accepted_and_one_more_is_refused():
    local._seed_path('/'.join(['a'] * local.SEED_MAX_DEPTH), 0)
    with pytest.raises(StoreError, match='too deep or too long'):
        local._seed_path('/'.join(['a'] * (local.SEED_MAX_DEPTH + 1)), 0)
    local._seed_path('a' * (local.SEED_MAX_PATH - 11), 10)
    with pytest.raises(StoreError, match='too deep or too long'):
        local._seed_path('a' * (local.SEED_MAX_PATH - 10), 10)


def test_a_component_core_does_not_seed_is_refused_by_name(monkeypatch):
    monkeypatch.setattr(local, 'refused_component', lambda c: c == 'bad')
    local._seed_path('ok/fine', 0)
    with pytest.raises(StoreError, match="a path Core does not seed: 'ok/bad/x'"):
        local._seed_path('ok/bad/x', 0)


def test_the_deadline_gives_time_left_then_refuses_at_zero_and_below(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(local, '_clock', lambda: now[0])
    d = local._Deadline('w')
    assert d.left() == pytest.approx(local.SEED_DEADLINE)
    now[0] = 100.0 + local.SEED_DEADLINE - 1
    assert d.left() == pytest.approx(1)
    now[0] = 100.0 + local.SEED_DEADLINE
    with pytest.raises(StoreError, match='ran past its deadline'):
        d.left()
    now[0] += 5
    with pytest.raises(StoreError, match='ran past its deadline'):
        d.left()


def test_a_multi_chunk_file_hashes_to_the_blob_id_and_an_expired_deadline_stops_it(tmp_path):
    data = bytes(range(256)) * 10240
    p = tmp_path / 'big.bin'
    p.write_bytes(data)
    assert local._blob_id(str(p), len(data), _Counting()) == _blob(data)
    with pytest.raises(StoreError, match='ran past its deadline'):
        local._blob_id(str(p), len(data), _Counting(ok=1))


@pytest.mark.parametrize('field', ['st_dev', 'st_ino', 'st_size'])
def test_a_file_changed_after_the_walk_is_refused_before_any_byte_is_read(tmp_path, field):
    p = tmp_path / 'f.txt'
    p.write_bytes(b'walked')
    real = os.lstat(str(p))
    seen = {f: getattr(real, f) for f in ('st_dev', 'st_ino', 'st_size')}
    seen[field] += 1
    clock = _Counting()
    with pytest.raises(StoreError, match='changed after the walk'):
        local._blob_id(str(p), 6, clock, seen=SimpleNamespace(**seen))
    assert clock.calls == 0


def test_a_file_that_still_is_the_walked_entry_is_hashed(tmp_path):
    p = tmp_path / 'f.txt'
    p.write_bytes(b'walked')
    assert local._blob_id(str(p), 6, _Counting(), seen=os.lstat(str(p))) == _blob(b'walked')


def test_the_walk_skips_only_the_root_git_and_keeps_a_nested_one(tmp_path):
    (tmp_path / '.git').mkdir()
    (tmp_path / '.git' / 'config').write_bytes(b'x')
    (tmp_path / 'a.txt').write_bytes(b'one')
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / '.git').write_bytes(b'gitdir: x')
    (tmp_path / 'sub' / 'x.txt').write_bytes(b'two')
    clock = _Counting()
    found = local._seed_walk(str(tmp_path), clock)
    assert found == {
        'a.txt': ('f', 3, _blob(b'one')),
        'sub': ('d',),
        'sub/.git': ('f', 9, _blob(b'gitdir: x')),
        'sub/x.txt': ('f', 3, _blob(b'two')),
    }
    assert clock.calls == 8


def test_a_nested_git_file_stays_in_the_walk(tmp_path):
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / '.git').write_bytes(b'gitdir: x')
    assert 'sub/.git' in local._seed_walk(str(tmp_path), _Counting())


def _meta(tmp_path, head='refs/heads/seed', rev='a' * 40):
    dot = tmp_path / '.git'
    (dot / 'objects' / 'info').mkdir(parents=True)
    (dot / 'refs' / 'heads').mkdir(parents=True)
    (dot / 'HEAD').write_bytes(b'ref: %s\n' % head.encode('ascii'))
    (dot / 'config').write_bytes(local.SEED_CONFIG)
    (dot / 'shallow').write_bytes(rev.encode('ascii') + b'\n')
    (dot / 'index').write_bytes(b'')
    (dot / 'refs' / 'heads' / 'seed').write_bytes(rev.encode('ascii') + b'\n')
    return str(dot)


def test_a_seed_git_with_a_name_outside_the_set_or_a_missing_one_is_refused(tmp_path):
    dot = _meta(tmp_path)
    (tmp_path / '.git' / 'packed-refs').write_bytes(b'')
    with pytest.raises(StoreError, match=r"holding \['packed-refs'\]"):
        local._seed_meta(dot, 'refs/heads/seed', 'a' * 40, _Counting())
    os.remove(os.path.join(dot, 'packed-refs'))
    os.remove(os.path.join(dot, 'index'))
    with pytest.raises(StoreError, match=r"holding \['index'\]"):
        local._seed_meta(dot, 'refs/heads/seed', 'a' * 40, _Counting())


def test_a_complete_seed_git_as_core_wrote_it_passes(tmp_path):
    local._seed_meta(_meta(tmp_path), 'refs/heads/seed', 'a' * 40, _Counting())


@pytest.mark.parametrize('name,corrupt', [
    ('HEAD', lambda b: b'ref: refs/heads/other\n'),
    ('config', lambda b: b[:-1] + bytes([b[-1] ^ 1])),
    ('shallow', lambda b: b'b' * 40 + b'\n'),
])
def test_a_head_config_or_shallow_that_core_did_not_write_is_refused(tmp_path, name, corrupt):
    dot = _meta(tmp_path)
    path = os.path.join(dot, name)
    with open(path, 'rb') as f:
        original = f.read()
    with open(path, 'wb') as f:
        f.write(corrupt(original))
    with pytest.raises(StoreError, match='a seed .git/%s Core did not write' % name):
        local._seed_meta(dot, 'refs/heads/seed', 'a' * 40, _Counting())


def test_index_is_only_checked_as_a_plain_entry(tmp_path):
    dot = _meta(tmp_path)
    with open(os.path.join(dot, 'index'), 'wb') as f:
        f.write(b'any bytes at all')
    local._seed_meta(dot, 'refs/heads/seed', 'a' * 40, _Counting())


def test_made_leaves_a_present_directory_alone_and_makes_an_absent_one(tmp_path, monkeypatch):
    top = str(tmp_path)
    (tmp_path / 'a').mkdir()
    made = []
    real_mkdir = os.mkdir
    monkeypatch.setattr(local, 'os', SimpleNamespace(
        path=os.path, sep=os.sep,
        mkdir=lambda d: (made.append(d), real_mkdir(d))))
    local._made(top, os.path.join(top, 'a', 'b'), _Counting())
    assert made == [os.path.join(top, 'a', 'b')]


def test_a_mkdir_race_is_swallowed_and_the_directory_stands(tmp_path, monkeypatch):
    top = str(tmp_path)
    real_mkdir = os.mkdir

    def raced(d):
        real_mkdir(d)
        raise FileExistsError(17, 'exists', d)
    monkeypatch.setattr(local, 'os', SimpleNamespace(path=os.path, sep=os.sep, mkdir=raced))
    local._made(top, os.path.join(top, 'race'), _Counting())
    assert stat.S_ISDIR(os.lstat(os.path.join(top, 'race')).st_mode)


def test_an_expired_deadline_raises_before_any_directory_is_made(tmp_path, monkeypatch):
    top = str(tmp_path)
    made = []
    monkeypatch.setattr(local, 'os', SimpleNamespace(
        path=os.path, sep=os.sep, mkdir=lambda d: made.append(d)))
    with pytest.raises(StoreError, match='ran past its deadline'):
        local._made(top, os.path.join(top, 'x', 'y'), _Counting(ok=0))
    assert made == []
