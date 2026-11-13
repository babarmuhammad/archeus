"""T-1168 · the highest-risk uncovered branches of `claude_sessions/paths.py`
lines 1-132 inclusive (tip 56d53504): fail-closed and denial first, then
boundaries, then error paths.

Nothing here edits source. Every branch listed below was confirmed unexecuted by
tracing `claude_sessions/paths.py` while the existing coverage named by the card
ran (tests/test_paths.py, tests/test_encoding_and_atomicity.py,
tests/v1/unit/test_paths.py, tests/test_context_inject.py, tests/test_gui_parity.py,
tests/test_memhub.py, tests/test_pi.py): the never-executed lines are 77-78,
96-103, 109, 113, 115, 119-120, 125, 127-129, and no existing test asserts the
denial for the cases below.

The ten selected branches, ranked, in the order they appear in this file:

1. paths.py:98-101 - a name with a leading `--` (a UNC project) must be refused
   as a GUESS, by `if not drive_part`, before `os.path.exists(base)`/`os.listdir`
   is reached. Closest: tests/test_paths.py:106
   `test_find_actual_path_resolves_a_unc_project`, whose `find_actual_path(enc)
   is None` only answers on the branch the host happens to take (POSIX on this
   container, where a leading `--` can never match anything anyway), so deleting
   the empty-drive guard fails nothing.
   -> `test_an_unc_name_is_refused_before_the_walk_asks_the_os`
2. paths.py:98-101 - a drive part that is not one letter (`AB--proj`, `..--x`)
   still becomes `base = drive_part + ':\\'` and is walked. Closest:
   tests/test_paths.py:31 `test_find_actual_path_missing_drive`, which uses a
   single letter and asserts only an OR (`is None or isinstance(str)`), so it
   cannot fail either way. -> `test_a_drive_part_that_is_not_one_letter_is_refused`
   (xfail)
3. paths.py:42-44 - a transcript's recorded `cwd` is returned verbatim after
   only an `isdir` test, so a RELATIVE value is handed to callers that use it as
   `cwd=` (gui.py:506 and gui_api.py:3298 spawn_terminal, main.py:1061
   subprocess.call). Closest: tests/test_paths.py:125
   `test_path_from_transcripts_ignores_junk_and_dead_paths`, whose dead value is
   absolute. -> `test_a_relative_recorded_cwd_is_not_returned` (xfail)
4. paths.py:80-86 - a cached SUCCESS is trusted while the folder's mtime stands
   still, and the folder's mtime cannot see the TARGET disappearing (the comment
   at :64-67 admits exactly that, for misses only). Closest:
   tests/test_primitives.py:308 `test_the_memo_expires_when_the_folder_changes`,
   which only ever replaces the cached value with a live one.
   -> `test_a_cached_path_is_not_reused_once_it_has_vanished` (xfail)
5. paths.py:75-78 and :84-85 - `os.stat(folder)` failing must not raise, must not
   block the answer, and must not store a cache entry under a `None` mtime.
   Closest: tests/test_paths.py:137
   `test_a_folder_that_cannot_be_resolved_is_only_walked_once`, which only ever
   stats a folder that exists. ->
   `test_a_folder_that_cannot_be_stat_still_resolves_and_caches_nothing`
6. paths.py:40-41 - `max_files=3` / `max_lines=40` and the fallthrough to the
   NEXT transcript when the newest one yields nothing (a transcript truncated
   mid-write is the normal case, not the exotic one). Closest:
   tests/test_paths.py:125 again: one file, no limits, no order. ->
   `test_the_transcript_limits_and_the_fallthrough_to_the_next_file_hold`
7. paths.py:114-115 - `if depth > max_depth` is the only thing that bounds the
   recursive guess. Closest: none - no existing test builds a tree deeper than two
   levels or passes `max_depth`. -> `test_the_walk_stops_at_the_exact_depth_limit`
8. paths.py:116-120 - a `PermissionError`/`OSError` out of `os.listdir` (or out of
   the `isdir` filter beside it) must answer `None` rather than escape into the
   /api/state caller or become a guess. Closest:
   tests/test_paths.py:137, which monkeypatches `_walk_for` itself, so the walk's
   own error path is never run. ->
   `test_a_permission_failure_in_the_walk_is_not_answered_with_a_guess`
9. paths.py:104-107 and :121-126 - the POSIX branch folds with `fold = str`, so a
   name that differs only in CASE must not resolve; the two names are two
   different projects. Closest: tests/test_paths.py:86
   `test_find_actual_path_case_insensitive`, which is `skipif(os.name != 'nt')`
   and pins the opposite direction, on the other platform only. ->
   `test_the_posix_walk_does_not_fold_case`
10. paths.py:122-130 - when the first prefix candidate dead-ends the loop must
    CONTINUE (`if r:`) and still try the sibling whose whole name matches, and a
    component may only be consumed on a '-' boundary (`rem_l.startswith(enc +
    '-')`), which is the difference between "a prefix of the run" and "a prefix
    of the PATH". Closest: tests/test_paths.py:40 `test_find_actual_path_resolves`
    (nt-only, skipped here), whose tree has exactly one child per level, so
    neither backtracking nor a crossed candidate ever happens. ->
    `test_an_ambiguous_hyphen_falls_back_to_the_matching_sibling`

Three control tests accompany them, so that no denial above can pass because the
fake answered "nothing exists" instead of because the code refused:
`test_a_posix_unc_name_never_walks_below_the_root` (the same UNC name on the
platform whose drive split does not refuse it),
`test_a_credential_shaped_cwd_string_is_still_only_a_string` (paths.py:42-43, the
falsy-`cwd` half of the guard), and `test_the_walk_answers_with_the_paths_the_fake_says_exist`.

One further uncovered branch turned up while writing them and is kept as its own
test rather than folded into a tenth, so that each test above stays sensitive to
exactly one mutation: paths.py:111-113. A folder name that ENDS in a non-alnum
character ends in '-' (`/home/m/proj.` encodes to `-home-m-proj-`), and consuming
that last boundary calls `match` with an empty `remaining`, which answers the
PARENT - a directory that is a different project and is handed to the same
callers as a cwd. -> `test_a_trailing_dash_run_is_not_answered_with_its_parent`
(xfail).

Fakes: `claude_sessions.paths` looks `os` and `_path_cache` up at call time, so
those are the seams. No real `listdir`, `stat`, `isdir` or `exists` runs in the
walk tests; the transcript tests write their own invented files under `tmp_path`
only. No network, no subprocess, no thread, no sleep, no host environment, no
credential or config read, no host home, no editor/pager/scheduler/process call.
"""

import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import paths as paths_mod      # noqa: E402

BACKSLASH = '\\'


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch):
    """A fresh memo per test: the module dict is shared by the whole suite, and
    this file has to pass alone, in any order, beside its sibling cards."""
    monkeypatch.setattr(paths_mod, '_path_cache', {})


# ── the seam: an in-memory filesystem served through `paths.os` ──────────────

class _Stat:
    def __init__(self, mtime_ns):
        self.st_mtime_ns = mtime_ns


class FakeOS:
    """Stands in for the `os` name `claude_sessions/paths.py` reads at call time.

    Only the calls that module actually makes are implemented, and every one of
    them is recorded, so `assert fake.listdir_calls == []` is an assertion about a
    denial that happened BEFORE the filesystem was asked. `name` is the platform
    switch at paths.py:95, and setting it is what lets the nt branch run in this
    Linux container and the POSIX branch run in the Windows review, with neither
    skipped. Nothing here is derived from the host: the tree is built by the test.
    """

    def __init__(self, name='posix'):
        self.name = name
        self.children = {}      # existing dir -> its child dir names, in listdir order
        self.nodes = set()      # every path that exists at all
        self.faults = {}        # ('listdir', path) -> exception to raise from it
        self.mtimes = {}        # path -> st_mtime_ns
        self.calls = []
        self.path = _FakePath(self)

    # ── building the tree ────────────────────────────────────────────────
    def join(self, *parts):
        out = ''
        for part in parts:
            if out == '':
                out = part
            elif out.endswith(('/', BACKSLASH)):
                out += part
            else:
                out = out + '/' + part
        return out

    def add_tree(self, base, rel):
        """Create `base/rel` (rel is '/'-separated) with every parent, and return
        the leaf. `base` is spelled exactly as paths.py builds it: '/' or 'D:' +
        a colon and a backslash."""
        self.add_dir(base)
        cur = base
        for part in rel.split('/'):
            kids = self.children.setdefault(cur, [])
            if part not in kids:
                kids.append(part)
            cur = self.join(cur, part)
            self.add_dir(cur)
        return cur

    def add_dir(self, path):
        self.nodes.add(path)
        self.children.setdefault(path, [])

    def add_ghost_tree(self, base, rel):
        """A listing that would answer although nothing here `exists`.

        Only a mutation of paths.py:108-109 can reach it - that guard is what keeps
        a drive the os says is absent from being listed - and that is exactly why
        the tests assert the recorded calls and not only the answer."""
        cur = base
        self.children.setdefault(base, [])
        for part in rel.split('/'):
            kids = self.children.setdefault(cur, [])
            if part not in kids:
                kids.append(part)
            cur = self.join(cur, part)
            self.children.setdefault(cur, [])
        return cur

    def drive_base(self, drive_part):
        """The base paths.py:101 would build for this drive part - spelled by the
        test, never by copying the source's expression."""
        return drive_part + ':' + BACKSLASH

    # ── the recorded calls, for "it denied before it looked" assertions ──
    def _calls(self, kind):
        return [p for k, p in self.calls if k == kind]

    @property
    def listdir_calls(self):
        return self._calls('listdir')

    @property
    def exists_calls(self):
        return self._calls('exists')

    @property
    def stat_calls(self):
        return self._calls('stat')

    # ── what the module calls ────────────────────────────────────────────
    def _fault(self, kind, path):
        fault = self.faults.get((kind, path))
        if fault is not None:
            raise fault

    def listdir(self, path):
        self.calls.append(('listdir', path))
        self._fault('listdir', path)
        if path not in self.children:
            raise OSError(2, 'no such directory', path)
        return list(self.children[path])

    def stat(self, path):
        self.calls.append(('stat', path))
        self._fault('stat', path)
        if path not in self.nodes:
            raise OSError(2, 'no such folder', path)
        return _Stat(self.mtimes.get(path, 1000))

    def use(self, monkeypatch, name='os'):
        """Install this fake as `paths_mod.<name>` for the rest of the test."""
        monkeypatch.setattr(paths_mod, name, self)


class _FakePath:
    def __init__(self, owner):
        self._owner = owner

    def join(self, *parts):
        return self._owner.join(*parts)

    def exists(self, path):
        self._owner.calls.append(('exists', path))
        self._owner._fault('exists', path)
        return path in self._owner.nodes

    def isdir(self, path):
        self._owner.calls.append(('isdir', path))
        self._owner._fault('isdir', path)
        return path in self._owner.children

    # Not reached by these tests; present so replacing `paths.os` cannot make a
    # call inside the slice raise AttributeError instead of failing loudly.
    def abspath(self, path):
        return os.path.abspath(path)

    def expanduser(self, path):
        return os.path.expanduser(path)

    def expandvars(self, path):
        return os.path.expandvars(path)


def _parts(path):
    """Split a resolved walk answer into components on either separator, so a path
    spelled with '\\' on Windows and '/' here is compared by its contents."""
    return [c for c in str(path).replace(BACKSLASH, '/').split('/') if c]


def _write_jsonl(folder, name, lines, mtime=None):
    """One transcript of OUR OWN invented lines, with explicit '\\n' bytes, under
    tmp_path. `lines` go out verbatim, which is the point: a truncated last line
    is written with no newline at all."""
    text = ''.join(line if line.endswith('\n') else line + '\n' for line in lines)
    path = os.path.join(str(folder), name)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


# ── 1 · denial: a UNC name is refused before the os is asked anything ────────

def test_an_unc_name_is_refused_before_the_walk_asks_the_os(monkeypatch):
    """paths.py:98-101. A UNC project folder name begins with two dashes, and the
    only correct answer is "the transcript knows", because the walk would have to
    invent a base out of an empty drive part.

    The fake filesystem CONTAINS a tree that the walk would happily return if the
    `if not drive_part` guard were dropped (the base it would build exists here
    and holds the matching chain), so this fails on the mutation instead of
    passing because there was nothing to find.
    """
    fake = FakeOS(name='nt')
    fake.add_tree(fake.drive_base(''), 'server/share/Project')
    fake.use(monkeypatch)

    assert paths_mod._walk_for('--server-share-Project') is None
    assert fake.exists_calls == []
    assert fake.listdir_calls == []


def test_a_posix_unc_name_never_walks_below_the_root(monkeypatch):
    """paths.py:104-107 on the platform Claude Code does not run on: the same
    leading '--' name has no drive to refuse, so it walks from the root once and
    must come back with nothing - an encoded component can never begin with '-',
    and a component that starts with one must not open a descent either."""
    fake = FakeOS(name='posix')
    fake.add_tree('/', 'server/share/Project')
    fake.add_tree('/', '-weird-/share')
    fake.add_tree('/', 'home/m/proj')                  # would answer a name that never
    fake.use(monkeypatch)                              # came from an absolute path

    assert paths_mod._walk_for('--server-share-Project') is None
    # and a name with no root marker at all is refused before the walk starts
    assert paths_mod._walk_for('home-m-proj') is None
    assert fake.listdir_calls == ['/']      # one listing, no recursion into the root


# ── 3 · denial: a transcript is user data, not a path to trust ───────────────

def test_a_relative_recorded_cwd_is_not_returned(tmp_path, monkeypatch):
    folder = tmp_path / 'proj-folder'
    folder.mkdir()
    (tmp_path / 'rel').mkdir()
    _write_jsonl(folder, 'a.jsonl', [json.dumps({'type': 'user', 'cwd': 'rel'})])
    monkeypatch.chdir(tmp_path)                     # 'rel' exists only relative to here

    assert paths_mod.path_from_transcripts(str(folder)) is None


def test_a_credential_shaped_cwd_string_is_still_only_a_string(tmp_path):
    """paths.py:42-43: a transcript line is user data, so a value shaped like a
    credential path, a drive path or an empty string is answered by the same two
    tests - is it non-empty, is it a directory - and by nothing else. No invented
    value here is opened, read, expanded or trusted; only the last one exists."""
    folder = tmp_path / 'proj-folder'
    folder.mkdir()
    target = tmp_path / 'the-project'
    target.mkdir()
    _write_jsonl(folder, 'a.jsonl', [
        json.dumps({'cwd': str(tmp_path / 'never-existed')}),        # dead: skipped
        json.dumps({'cwd': ''}),                                     # falsy: skipped
        json.dumps({'cwd': '   '}),                                  # blank: skipped
        json.dumps({'cwd': 'Z:' + BACKSLASH + 'invent3d' + BACKSLASH + 'creds'}),
        json.dumps({'cwd': str(target)}),                            # the only one real
    ])

    assert paths_mod.path_from_transcripts(str(folder)) == str(target)


# ── 4 · stale cache: a hit whose target has vanished is not an answer ────────

def test_a_cached_path_is_not_reused_once_it_has_vanished(tmp_path):
    folder = tmp_path / 'Z--gone-tomorrow'
    folder.mkdir()
    target = tmp_path / 'project'
    target.mkdir()
    _write_jsonl(folder, 'a.jsonl', [json.dumps({'cwd': str(target)})])

    assert paths_mod.find_actual_path('Z--gone-tomorrow', folder=str(folder)) == str(target)
    before = os.stat(str(folder)).st_mtime_ns
    shutil.rmtree(str(target))                     # the project goes away; the
    assert os.stat(str(folder)).st_mtime_ns == before       # folder mtime does not

    got = paths_mod.find_actual_path('Z--gone-tomorrow', folder=str(folder))
    assert got is None or os.path.isdir(got), 'reused a dead path: %r' % (got,)


# ── 5 · error path: a folder that cannot be stat'd is not a failure ─────────

def test_a_folder_that_cannot_be_stat_still_resolves_and_caches_nothing(tmp_path,
                                                                         monkeypatch):
    """paths.py:75-78 and :84-85. A folder can vanish (or be unreadable) between
    the listing and this call; the answer must still be the walk's, and the memo
    must not gain an entry keyed by a folder with no mtime - such an entry can
    never be read back (the hit test needs `mtime is not None`) and nothing
    prunes it."""
    fake = FakeOS(name='nt')
    fake.add_tree(fake.drive_base('D'), 'proj')
    fake.use(monkeypatch)

    # an absolute path that is simply not on disk: os.stat raises OSError here, and
    # the transcript reader below finds no folder either, so only the walk answers
    folder = os.path.join(str(tmp_path), 'project-folder-that-is-gone')
    assert paths_mod.find_actual_path('D--proj', max_depth=4, folder=folder) == \
        fake.drive_base('D') + 'proj'
    assert fake.stat_calls == [folder]
    assert paths_mod._path_cache == {}, paths_mod._path_cache


# ── 6 · boundary: the transcript limits and the fallthrough between files ───

def test_the_transcript_limits_and_the_fallthrough_to_the_next_file_hold(tmp_path):
    """paths.py:40-41, through the real transcript reader. The newest transcript
    is the one most likely to be half-written, so "read the next file" is the path
    that answers; `max_files` and `max_lines` are the two bounds that stop a 100 MB
    transcript being parsed for every project on every poll."""
    late = tmp_path / 'late-project'
    late.mkdir()
    early = tmp_path / 'early-project'
    early.mkdir()

    # the three newest yield nothing at all; only the FOURTH knows the path
    dead = tmp_path / 'four-files'
    dead.mkdir()
    _write_jsonl(dead, 's1.jsonl', ['{"cwd": "/def', 'garbage'], 500)     # truncated
    _write_jsonl(dead, 's2.jsonl', [json.dumps({'type': 'user'})], 400)    # no cwd
    _write_jsonl(dead, 's3.jsonl', [json.dumps(['not', 'a', 'dict'])], 300)
    _write_jsonl(dead, 's4.jsonl', [json.dumps({'cwd': str(late)})], 200)
    assert paths_mod.path_from_transcripts(str(dead)) is None

    # the very same fourth file answers as soon as it is inside max_files=3
    three = tmp_path / 'three-files'
    three.mkdir()
    _write_jsonl(three, 's1.jsonl', ['{"cwd": "/def', 'garbage'], 500)
    _write_jsonl(three, 's2.jsonl', [json.dumps({'type': 'user'})], 400)
    _write_jsonl(three, 's4.jsonl', [json.dumps({'cwd': str(late)})], 200)
    assert paths_mod.path_from_transcripts(str(three)) == str(late)

    # and `max_lines=40`: the recorded cwd is only looked for in the first 40
    # parsed objects, which is where a session writes its own cwd.
    filler = [json.dumps({'type': 'user', 'i': i}) for i in range(40)]
    deep = tmp_path / 'cwd-on-41'
    deep.mkdir()
    _write_jsonl(deep, 'a.jsonl', filler + [json.dumps({'cwd': str(early)})])
    assert paths_mod.path_from_transcripts(str(deep)) is None

    at_limit = tmp_path / 'cwd-on-40'
    at_limit.mkdir()
    _write_jsonl(at_limit, 'a.jsonl', filler[:39] + [json.dumps({'cwd': str(early)})])
    assert paths_mod.path_from_transcripts(str(at_limit)) == str(early)


# ── 7 · boundary: the depth cap is exact ────────────────────────────────────

def test_the_walk_stops_at_the_exact_depth_limit(monkeypatch):
    """paths.py:114-115. `match` recurses from the root, so the cap is the only
    thing bounding a guess over a real home directory; `>` vs `>=` here either
    loses every deep project or walks the whole disk on every poll. Nine
    components below the root is the last answerable depth with max_depth=8."""
    fake = FakeOS(name='posix')
    nine = fake.add_tree('/', 'home/m/a/b/c/d/e/f/g')          # 9 components
    fake.add_tree(nine, 'h')                                   # the tenth, unreachably
    fake.use(monkeypatch)

    assert _parts(paths_mod._walk_for('-home-m-a-b-c-d-e-f-g')) == \
        ['home', 'm', 'a', 'b', 'c', 'd', 'e', 'f', 'g']
    assert paths_mod._walk_for('-home-m-a-b-c-d-e-f-g-h') is None
    # the caller-supplied bound is honoured at its own boundary too
    assert _parts(paths_mod._walk_for('-home-m-a-b', max_depth=3)) == \
        ['home', 'm', 'a', 'b']
    assert paths_mod._walk_for('-home-m-a-b', max_depth=2) is None


# ── 8 · error path: a denied directory is a refusal, not a crash or a guess ──

def test_a_permission_failure_in_the_walk_is_not_answered_with_a_guess(monkeypatch):
    """paths.py:116-120. /api/state calls this once per project (paths.py:48-53),
    so an escaping PermissionError - which a roaming profile, a share or another
    user's home raises routinely - is a failed request, and a swallowed one that
    keeps guessing is a project nobody owns."""
    fake = FakeOS(name='posix')
    fake.add_tree('/', 'home/m/proj')
    fake.add_tree('/', 'locked/other')
    fake.add_tree('/', 'private/other')
    fake.faults[('listdir', '/locked')] = PermissionError(13, 'denied')
    fake.faults[('listdir', '/private')] = OSError(20, 'not a directory')
    fake.use(monkeypatch)

    assert paths_mod._walk_for('-locked-other') is None
    assert paths_mod._walk_for('-private-other') is None
    # the answer came from a listing that WAS attempted and refused there
    assert '/locked' in fake.listdir_calls and '/private' in fake.listdir_calls
    # the faulted listings are abandoned, and a healthy sibling still answers
    assert _parts(paths_mod._walk_for('-home-m-proj')) == ['home', 'm', 'proj']


# ── 9 · boundary: POSIX does not fold case ──────────────────────────────────

def test_the_posix_walk_does_not_fold_case(monkeypatch):
    """paths.py:107 and :121-126. `fold = str` on the POSIX branch is what keeps
    two directories that differ only in case - two different projects on a
    case-sensitive filesystem, which is where part of this suite runs - from
    becoming each other's answer. The nt-only test in tests/test_paths.py pins the
    opposite direction and is skipped here, so lowering this line fails nothing."""
    fake = FakeOS(name='posix')
    fake.add_tree('/', 'myapp/src')
    fake.use(monkeypatch)

    assert paths_mod._walk_for('-MyApp-src') is None
    assert paths_mod._walk_for('-myapp-SRC') is None
    assert _parts(paths_mod._walk_for('-myapp-src')) == ['myapp', 'src']


# ── 10 · ambiguity: the first prefix candidate is not the answer ────────────

def test_an_ambiguous_hyphen_falls_back_to_the_matching_sibling(monkeypatch):
    """paths.py:122-130. One dash-separated run names two different real paths,
    and the lossy encoding cannot tell them apart, so which one is returned is
    decided here: the loop must finish the first candidate (whose descent answers
    None) and still reach the sibling whose whole remaining string matches.
    Turning `if r:` into an unconditional `return r` keeps every existing test
    green and makes the answer depend on the order the disk returns."""
    fake = FakeOS(name='posix')
    fake.add_tree('/', 'a')                            # '/a' has no child 'b'
    fake.add_tree('/', 'a-b')                          # the real project
    fake.use(monkeypatch)

    got = paths_mod._walk_for('-a-b')
    assert got is not None
    assert _parts(got) == ['a-b']
    assert fake.listdir_calls == ['/', '/a']

    # paths.py:126, the other half of the same ambiguity: a component may only be
    # consumed on a '-' boundary. '/a-b' is a string-prefix of the run 'a-bc' but
    # is not a prefix of it, so it must be passed over for '/a-bc' even though it
    # comes first and even though it has a child that would complete the guess.
    crossed = FakeOS(name='posix')
    crossed.add_tree('/', 'a-b/c')
    crossed.add_tree('/', 'a-bc')
    crossed.use(monkeypatch)

    assert _parts(paths_mod._walk_for('-a-bc')) == ['a-bc']
    assert crossed.listdir_calls == ['/']       # '/a-b' was never even listed


# ── 11 (extra) · the last boundary must not resolve to the parent ─────────────

def test_a_trailing_dash_run_is_not_answered_with_its_parent(monkeypatch):
    fake = FakeOS(name='posix')
    fake.add_tree('/', 'home/m/proj')        # '/home/m/proj.' is the real project
    fake.add_tree('/', 'home/m/proj/deeper')
    fake.use(monkeypatch)

    assert fake.listdir_calls == []                      # nothing asked yet
    assert paths_mod._walk_for('-home-m-proj-') is None
    assert fake.listdir_calls == ['/', '/home', '/home/m']   # it did look, then guessed


# ── the denials above must fail because of the code, not because of the fake ─

def test_the_walk_answers_with_the_paths_the_fake_says_exist(monkeypatch):
    """The mutation check for `FakeOS` itself: if it never said anything existed,
    most of the denials above would pass for the wrong reason. Each positive here
    is the same shape as those denials."""
    fake = FakeOS(name='posix')
    fake.add_tree('/', 'home/m/proj')
    fake.add_tree('/', 'home/m/pro j')                  # a space encodes to '-'
    fake.use(monkeypatch)

    assert _parts(paths_mod._walk_for('-home-m-proj')) == ['home', 'm', 'proj']
    assert _parts(paths_mod._walk_for('-home-m-pro-j')) == ['home', 'm', 'pro j']
    # nothing matched: refused, and the fake - not the disk - decided that
    assert paths_mod._walk_for('-home-m-other') is None
    assert set(fake.listdir_calls) <= {'/', '/home', '/home/m'}
    assert fake.stat_calls == []

    # and a root that does not exist is never listed at all (paths.py:108-109, the
    # one guard between "this drive is not here" and a recursive walk of it)
    absent = FakeOS(name='nt')
    absent.add_ghost_tree(absent.drive_base('Q'), 'proj')   # the guess WOULD match here
    absent.use(monkeypatch)

    assert paths_mod._walk_for('Q--proj') is None
    assert absent.exists_calls == [absent.drive_base('Q')]
    assert absent.listdir_calls == []
