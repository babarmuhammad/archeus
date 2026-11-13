"""T-1317 · the highest-risk uncovered branches of `claude_sessions/paths.py`
lines 20-131 inclusive (tip 51f4af3f; relocated at the current tip): new
compositions beside the known path xfails, denial and fail-closed first.

Candidate list, ranked (file:line, closest existing test, why it misses):
 1. paths.py:43      relative cwd in a transcript must not be returned, a later
                     absolute line must win -> closest test_gaps3 ::test_a_relative_recorded_cwd_is_not_returned
                     (xfail, single value only); no test combines it with a valid later line.
                     -> test_a_relative_cwd_line_does_not_hide_a_later_absolute_one
 2. paths.py:43      relative dot cwd in the newer file must not suppress the absolute
                     cwd of an older file -> none exact.
                     -> test_a_relative_dot_cwd_in_the_newest_file_does_not_hide_an_older_one
 3. paths.py:80-83   cached success, target removed, folder mtime unchanged, second
                     valid line -> closest test_gaps3 ::test_a_cached_path_is_not_reused_once_it_has_vanished (xfail).
                     -> test_a_vanished_cached_target_yields_the_next_recorded_path
 4. paths.py:81      cached success replaced by a regular file at the same spelling
                     -> none exact.  -> test_a_cached_target_replaced_by_a_file_is_not_a_hit
 5. paths.py:76-78,80 transcript folder deleted after a cache hit -> none exact.
                     -> test_a_deleted_transcript_folder_does_not_return_the_cached_path
 6. paths.py:81-82   miss TTL boundary: 59.x s reuses, 60.0 s looks again
                     -> test_gaps3 test_primitives :308 only covers the mtime key.
                     -> test_a_miss_is_reused_just_under_its_ttl_and_refreshed_at_it
 7. paths.py:126     trailing encoded separator with prefix sibling -> test_gaps3
                     ::test_a_trailing_dash_run_is_not_answered_with_its_parent (xfail, one folder).
                     -> test_a_trailing_dot_folder_beside_a_prefix_sibling_is_its_own_answer
 8. paths.py:122-130 two trailing non-alnum characters plus an ambiguous sibling
                     -> none exact. -> test_a_double_trailing_run_is_not_collapsed_into_a_sibling
 9. paths.py:83      an invalid relative transcript value is never cached as success
                     -> none exact. -> test_an_unusable_transcript_value_is_not_cached_as_a_path
10. paths.py:27      resolve_dir relative input normalises to an absolute existing dir
                     -> none exact. -> test_resolve_dir_turns_a_relative_name_into_an_absolute_directory

For each test the source branch whose removal or inversion it breaks is the one
named in the candidate list above.

No defect in these ten: every test passes against the current source, so none is
marked xfail. Fakes: `paths_mod.os` is replaced by a virtual filesystem (posix
spelling) for the walk tests only; the transcript tests use invented files under
tmp_path; time is a fake clock. No subprocess, network, sleep, host environment or
real home read; the walk never touches the real filesystem root.
"""

import json
import os
import shutil
from types import SimpleNamespace

import pytest

from claude_sessions import paths as paths_mod


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(paths_mod, '_path_cache', {})


def _transcript(folder, name, cwds):
    folder.mkdir(parents=True, exist_ok=True)
    lines = ''.join(json.dumps({'cwd': c}) + '\n' for c in cwds)
    path = folder / name
    path.write_bytes(lines.encode('utf-8'))
    return path


class VirtualFS:
    """The `os` surface `_walk_for` uses, on a POSIX spelling, built by the test."""

    name = 'posix'

    def __init__(self):
        self.dirs = set()
        self.kids = {}
        self.files = set()
        self.listdir_calls = []
        self.path = SimpleNamespace(
            join=self._join, isdir=self._isdir, exists=self._exists,
            isabs=lambda p: p.startswith('/'))

    @staticmethod
    def _join(a, b):
        return (a if a.endswith('/') else a + '/') + b

    def _isdir(self, p):
        return p in self.dirs

    def _exists(self, p):
        return p in self.dirs or p in self.files

    def listdir(self, p):
        self.listdir_calls.append(p)
        if p not in self.dirs:
            raise FileNotFoundError(p)
        return list(self.kids.get(p, []))

    def add_dir(self, p, parent=None):
        self.dirs.add(p)
        self.kids.setdefault(p, [])
        if parent is not None:
            self.kids.setdefault(parent, []).append(p.rsplit('/', 1)[1])
        return p


def _tree(*chain):
    fs = VirtualFS()
    fs.add_dir('/')
    cur = '/'
    for name in chain:
        nxt = cur.rstrip('/') + '/' + name
        fs.add_dir(nxt, cur)
        cur = nxt
    return fs


def test_a_relative_cwd_line_does_not_hide_a_later_absolute_one(tmp_path):
    proj = tmp_path / 'proj'
    sibling = tmp_path / 'sibling'
    sibling.mkdir()
    proj.mkdir()
    folder = tmp_path / 'projects' / 'enc'
    _transcript(folder, 's.jsonl', ['../sibling', str(proj)])
    assert paths_mod.path_from_transcripts(str(folder)) == str(proj)


def test_a_relative_dot_cwd_in_the_newest_file_does_not_hide_an_older_one(tmp_path):
    proj = tmp_path / 'proj'
    proj.mkdir()
    folder = tmp_path / 'projects' / 'enc'
    older = _transcript(folder, 'old.jsonl', [str(proj)])
    newer = _transcript(folder, 'new.jsonl', ['.'])
    os.utime(older, ns=(1_000_000_000, 1_000_000_000))
    os.utime(newer, ns=(2_000_000_000, 2_000_000_000))
    assert paths_mod.path_from_transcripts(str(folder)) == str(proj)


def test_a_vanished_cached_target_yields_the_next_recorded_path(tmp_path, monkeypatch):
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    folder = tmp_path / 'projects' / 'enc'
    _transcript(folder, 's.jsonl', [str(first), str(second)])
    walked = []
    monkeypatch.setattr(paths_mod, '_walk_for', lambda *a, **k: walked.append(a) or None)
    assert paths_mod.find_actual_path('enc', folder=str(folder)) == str(first)
    shutil.rmtree(first)
    assert paths_mod.find_actual_path('enc', folder=str(folder)) == str(second)
    assert walked == []


def test_a_cached_target_replaced_by_a_file_is_not_a_hit(tmp_path, monkeypatch):
    target = tmp_path / 'target'
    target.mkdir()
    folder = tmp_path / 'projects' / 'enc'
    _transcript(folder, 's.jsonl', [str(target)])
    walked = []
    monkeypatch.setattr(paths_mod, '_walk_for', lambda *a, **k: walked.append(a) or None)
    assert paths_mod.find_actual_path('enc', folder=str(folder)) == str(target)
    shutil.rmtree(target)
    target.write_bytes(b'not a directory\n')
    assert paths_mod.find_actual_path('enc', folder=str(folder)) is None
    assert len(walked) == 1


def test_a_deleted_transcript_folder_does_not_return_the_cached_path(tmp_path, monkeypatch):
    target = tmp_path / 'target'
    target.mkdir()
    folder = tmp_path / 'projects' / 'enc'
    _transcript(folder, 's.jsonl', [str(target)])
    walked = []
    monkeypatch.setattr(paths_mod, '_walk_for', lambda *a, **k: walked.append(a) or None)
    assert paths_mod.find_actual_path('enc', folder=str(folder)) == str(target)
    shutil.rmtree(folder)
    assert paths_mod.find_actual_path('enc', folder=str(folder)) is None
    assert len(walked) == 1


def test_a_miss_is_reused_just_under_its_ttl_and_refreshed_at_it(tmp_path, monkeypatch):
    import time
    folder = tmp_path / 'projects' / 'enc'
    folder.mkdir(parents=True)
    clock = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: clock[0])
    walked = []
    monkeypatch.setattr(paths_mod, '_walk_for', lambda *a, **k: walked.append(a) or None)
    assert paths_mod.find_actual_path('enc', folder=str(folder)) is None
    clock[0] = 1000.0 + paths_mod._MISS_TTL - 0.5
    assert paths_mod.find_actual_path('enc', folder=str(folder)) is None
    assert len(walked) == 1
    clock[0] = 1000.0 + paths_mod._MISS_TTL
    assert paths_mod.find_actual_path('enc', folder=str(folder)) is None
    assert len(walked) == 2


def test_a_trailing_dot_folder_beside_a_prefix_sibling_is_its_own_answer(monkeypatch):
    fs = _tree('home', 'm')
    fs.add_dir('/home/m/proj', '/home/m')
    fs.add_dir('/home/m/proj.', '/home/m')
    monkeypatch.setattr(paths_mod, 'os', fs)
    assert paths_mod._walk_for('-home-m-proj-') == '/home/m/proj.'


def test_a_double_trailing_run_is_not_collapsed_into_a_sibling(monkeypatch):
    fs = _tree('home', 'm')
    fs.add_dir('/home/m/proj', '/home/m')
    fs.add_dir('/home/m/proj/x', '/home/m/proj')
    fs.add_dir('/home/m/proj..', '/home/m')
    monkeypatch.setattr(paths_mod, 'os', fs)
    assert paths_mod._walk_for('-home-m-proj--') == '/home/m/proj..'
    fs2 = _tree('home', 'm')
    fs2.add_dir('/home/m/proj', '/home/m')
    fs2.add_dir('/home/m/proj/x', '/home/m/proj')
    monkeypatch.setattr(paths_mod, 'os', fs2)
    assert paths_mod._walk_for('-home-m-proj--') is None


def test_an_unusable_transcript_value_is_not_cached_as_a_path(tmp_path, monkeypatch):
    folder = tmp_path / 'projects' / 'enc'
    _transcript(folder, 's.jsonl', ['relative/only'])
    walked = []
    monkeypatch.setattr(paths_mod, '_walk_for', lambda *a, **k: walked.append(a) or None)
    first = paths_mod.find_actual_path('enc', folder=str(folder))
    second = paths_mod.find_actual_path('enc', folder=str(folder))
    assert first is None and second is None
    assert paths_mod._path_cache[str(folder)][1] is None


def test_resolve_dir_turns_a_relative_name_into_an_absolute_directory(tmp_path, monkeypatch):
    (tmp_path / 'sub').mkdir()
    monkeypatch.chdir(tmp_path)
    got = paths_mod.resolve_dir('sub')
    assert os.path.isabs(got)
    assert got == os.path.join(os.getcwd(), 'sub')
    assert paths_mod.resolve_dir('missing') == ''
    assert paths_mod.resolve_dir('   ') == ''
