"""T-842 pins for archeus/node/local.py lines 1300-1898: every test here fails
when the condition it names is inverted, removed or loosened. The proof of each
pin is a mutated copy of the module under /work/scratch, never in the repo.
Git is resolved to a fake absolute path and never started: `proc.run` records,
`Popen` refuses."""

import hashlib
import os
import subprocess
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.infra import paths
from archeus.node import local
from archeus.node.local import StoreError

GIT = os.path.abspath(os.path.join(os.sep, 'fake', 'git', 'cmd', 'git.exe'))
BLOB = hashlib.sha1(b'blob 1\0x').hexdigest()
COMMIT = hashlib.sha1(b'commit 0\0').hexdigest()


class Spawns:
    def __init__(self):
        self.calls, self.version = [], 'git version 2.47.1\n'

    def __call__(self, argv, *, cwd=None, env=None, timeout=30, stdin=None, check=False):
        self.calls.append(SimpleNamespace(argv=argv, cwd=cwd, env=env))
        return SimpleNamespace(returncode=0, stdout=self.version, stderr='')


@pytest.fixture(autouse=True)
def no_git(monkeypatch):
    local._git_exe.cache_clear()
    local._VERSION.clear()
    monkeypatch.setattr(local.shutil, 'which', lambda name: GIT)
    monkeypatch.setattr(subprocess, 'Popen', _no_child)
    spawns = Spawns()
    monkeypatch.setattr(local.proc, 'run', spawns)
    yield spawns
    local._git_exe.cache_clear()
    local._VERSION.clear()


def _no_child(*a, **k):
    raise AssertionError('no child may be started: %r' % (a[:1],))


class _Ample:
    def left(self):
        return 1.0


def _tree(dirs, entries):
    return SimpleNamespace(dirs=list(dirs), entries=list(entries))


def test_the_seed_makes_shallow_directories_before_deep_ones(monkeypatch, tmp_path):
    made, real = [], os.mkdir

    def record(path):
        made.append(os.path.relpath(path, str(tmp_path)).replace(os.sep, '/'))
        real(path)
    monkeypatch.setattr(local.os, 'mkdir', record)
    local._write_tree(_tree(['a/b/c', 'a/b0', 'a/b', 'a'], []), str(tmp_path), _Ample(),
                      lambda **kw: None)
    assert made == ['a', 'a/b0', 'a/b', 'a/b/c']


def test_a_tree_with_nothing_to_hash_starts_no_blob_call(tmp_path):
    calls = []
    local._write_tree(_tree(['sub'], [('160000', COMMIT, None, 'sub')]), str(tmp_path),
                      _Ample(), lambda **kw: calls.append(kw))
    assert calls == []
    assert (tmp_path / 'sub').is_dir()


@pytest.mark.parametrize('out,want', [('git version 2.45.0\n', 'git version 2.45.0'),
                                      ('git version 2.44.99\n', 'older than'),
                                      ('git version 2.45.0-rc1\n', 'git version 2.45.0-rc1'),
                                      ('not a version\n', 'older than')],
                         ids=['floor', 'below', 'suffix', 'unreadable'])
def test_the_version_floor_is_held_at_its_own_number(no_git, out, want):
    no_git.version = out
    if want == 'older than':
        with pytest.raises(StoreError, match=r'older than 2\.45\.0'):
            local._git_version(())
    else:
        assert local._git_version(()) == out.strip()
    assert [c.argv[-1] for c in no_git.calls] == ['version']


@pytest.mark.parametrize('which', ['path', 'area'])
def test_an_execution_area_reached_through_an_alias_is_refused(tmp_path, which):
    alias = str(tmp_path / 'alias')
    if which == 'path':
        work = paths.ExecPaths(ids.new_id('execution')).work
        os.makedirs(work)
        _link(work, alias)
        with pytest.raises(StoreError, match='execution area'):
            local._outside_executions([alias], ())
    else:
        wd = str(tmp_path / 'wd')
        os.makedirs(os.path.join(wd, 'inside'))
        _link(wd, alias)
        with pytest.raises(StoreError, match='execution area'):
            local._outside_executions([os.path.join(wd, 'inside')], [alias])


def _link(target, link):
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError):
        pytest.skip('this user may not make a symlink')


def test_a_root_that_is_itself_a_git_directory_is_read_as_one(no_git, tmp_path):
    root = tmp_path / 'store'
    (root / 'objects' / 'info').mkdir(parents=True)
    (root / 'objects' / 'pack').mkdir()
    (root / 'refs' / 'heads').mkdir(parents=True)
    (root / 'HEAD').write_bytes(b'ref: refs/heads/main\n')
    (root / 'config').write_bytes(b'[core]\n\tbare = true\n')
    assert local._git_dir_of(str(root)) == str(root)
    assert local._source(str(root), ()) == str(root)
    assert no_git.calls == []


def test_the_index_holds_exactly_the_entries_git_listed():
    m = local._Index()
    data = (b'100644 ' + BLOB.encode('ascii') + b' 1\ts/a.txt\0'
            + b'100755 ' + BLOB.encode('ascii') + b' 0\trun\0')
    for i in range(0, len(data), 5):
        m.feed(data[i:i + 5])
    m.end()
    assert m.found == {('100644', BLOB, 's/a.txt'), ('100755', BLOB, 'run')}


@pytest.mark.parametrize('rec', [b'100644 ' + BLOB.encode('ascii') + b' 1 path',
                                 b'100644', b''],
                         ids=['no-tab', 'short', 'empty'])
def test_an_index_record_core_cannot_read_is_a_refusal(rec):
    m = local._Index()
    with pytest.raises(StoreError, match='index entry Core cannot read'):
        m.feed(rec + b'\0')
        m.end()
