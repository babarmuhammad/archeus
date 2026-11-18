"""T-781: the highest-risk uncovered branches of `archeus/node/staging.py`.

Companion to tests/v1/unit/test_pv20_runtime_stage.py, tests/v1/unit/test_pv20_mxc_staging.py
and tests/v1/unit/test_pv20_mxc_staging_gaps.py, whose fixtures and seam fakes this copies.
Offline unit tests only: no installed Python is read, no process is started, nothing is
installed or executed, no network, no Windows API and no real link — every OS entry point
the source reaches for is faked through the very seams those files use (`os.lstat`,
`os.path.realpath`, `os.mkdir`, `os.rename`, `staging._write`), so the same rows run and
mean the same thing on Windows as on this Linux box.

Each numbered section is one branch: the line of the source whose refusal it is, and what
would go unnoticed if that branch were removed or inverted. `coverage` is not installed in
this container; the list was measured with a `sys.monitoring` line probe plus a
`sys.settrace` arc probe run over the four files that already exercise this module. Rows 1
and 2 are the only two statements of the module that no existing test ever executes; the
rest are decision paths that no existing input reaches, each written here so that removing
the guard it guards lets the test through.
"""

import errno
import hashlib
import json
import os
import shutil
import stat
from types import SimpleNamespace

import pytest

from archeus.infra import paths
from archeus.node import staging
from archeus.node.staging import MANIFEST, StageError

V = (3, 10)
REPARSE = stat.FILE_ATTRIBUTE_REPARSE_POINT

SOURCE = {
    'python.exe': b'MZ a fake interpreter',
    'python3.dll': b'stable abi',
    'python310.dll': b'versioned',
    'vcruntime140.dll': b'crt',
    'Lib/os.py': b'# os\n',
    'Lib/encodings/__init__.py': b'# encodings\n',
    'Lib/json/__init__.py': b'# json\n',
    'Lib/site-packages/evil.py': b'evil\n',
    'DLLs/_x.pyd': b'pyd\n',
}
DEEP = {'Lib/deep/er/x.py': b'deep\n', 'Lib/deep/er/more/y.py': b'more\n'}


@pytest.fixture
def make_rt(tmp_path, archeus_home):
    """A synthetic install, a hook and an ARCHEUS_HOME: nothing under this fixture is
    a real runtime, and *extra* adds files to the install before anything is staged."""
    archeus_home.mkdir()

    def make(extra=None, name='py'):
        src = tmp_path / name
        for rel, data in dict(SOURCE, **(extra or {})).items():
            p = src / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        hook = tmp_path / (name + '-hooks') / 'hook.py'
        hook.parent.mkdir()
        hook.write_bytes(b'# the hook\n')
        return SimpleNamespace(src=str(src), hook=str(hook), home=str(archeus_home), tmp=tmp_path)
    return make


@pytest.fixture
def rt(make_rt):
    return make_rt()


@pytest.fixture
def rt_deep(make_rt):
    return make_rt(extra=DEEP)


@pytest.fixture
def sdk(tmp_path):
    root = tmp_path / 'sdk'
    files = {
        'package.json': json.dumps({'name': staging.MXC_PACKAGE,
                                    'version': staging.MXC_VERSION}).encode(),
        staging.MXC_EXE: b'fake x64 launcher',
        'bin/x64/runtime.dll': b'fake runtime',
    }
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    pins = {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()}
    return root, pins


def _stage(rt, version=V):
    return staging.stage(rt.src, rt.hook, version=version)


def _files(top):
    out = {}
    for d, _dirs, names in os.walk(top):
        for n in names:
            p = os.path.join(d, n)
            with open(p, 'rb') as f:
                out[os.path.relpath(p, top).replace(os.sep, '/')] = f.read()
    return out


def _runtime():
    return sorted(os.listdir(paths.runtime_dir()))


def _published():
    return [n for n in _runtime() if not n.startswith('.tmp-')]


def _tempories():
    return [n for n in _runtime() if n.startswith('.tmp-')]


def _planned_digest(rt):
    """The name this install and hook would be published under, from the module's own
    planner: nothing here re-derives the manifest and so nothing here can drift from it."""
    _root, _rows, _pth, manifest = staging._plan(rt.src, rt.hook, V)
    return hashlib.sha256(manifest).hexdigest()


def _reparse(st):
    return SimpleNamespace(st_mode=st.st_mode, st_ino=st.st_ino, st_dev=st.st_dev,
                           st_size=st.st_size, st_mtime_ns=st.st_mtime_ns,
                           st_nlink=st.st_nlink, st_file_attributes=REPARSE)


def _alias_once_writes(monkeypatch, rel, writes=1):
    """`os.lstat` reports *rel* inside the temporary stage as a reparse point from the
    moment *writes* files have been written into it, as a junction swapped in for the
    directory would. Returns the list of `_write` destinations, in order."""
    real_lstat, real_write, done = os.lstat, staging._write, []
    tail = os.path.normcase(rel.replace('/', os.sep))

    def tmp_child(p):
        parent = os.path.dirname(os.path.abspath(p))
        while os.path.basename(parent) and not os.path.basename(parent).startswith('.tmp-'):
            parent = os.path.dirname(parent)
        if not os.path.basename(parent):
            return None
        return os.path.normcase(os.path.relpath(os.path.abspath(p), parent))

    def write(dst, chunks):
        got = real_write(dst, chunks)
        done.append(dst)
        return got

    def fake(p, *a, **k):
        st = real_lstat(p, *a, **k)
        if len(done) < writes or tmp_child(p) != tail:
            return st
        return _reparse(st)

    monkeypatch.setattr(staging, '_write', write)
    monkeypatch.setattr(os, 'lstat', fake)
    return done


# ── 1. staging.py:244-245 `_tree(tmp) != digest`: nothing is published that is not ──
# ──    exactly what was planned. No existing test ever reaches line 245: every one  ──
# ──    of them breaks `_tree` instead of making it return another digest, so the    ──
# ──    publication gate itself is dark. Deleting it renames a tree whose manifest   ──
# ──    is not the planned bytes into the name of the planned digest.                ──

def _manifest_redumped(monkeypatch, **dump):
    """`_write` that re-dumps MANIFEST.json with *dump*: the same listing, other bytes,
    so `_tree` reads it happily and still returns a digest that is not the planned one."""
    def write(dst, chunks):
        data = b''.join(chunks)
        if os.path.basename(dst) == MANIFEST:
            data = json.dumps(json.loads(data), **dump).encode()
        with open(dst, 'xb') as out:
            out.write(data)
        return hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(staging, '_write', write)


def test_a_temporary_tree_whose_manifest_bytes_are_not_the_planned_ones_is_never_published(
        rt, monkeypatch):
    _manifest_redumped(monkeypatch, sort_keys=True, indent=1)
    with pytest.raises(StageError, match='not what was planned'):
        _stage(rt)
    assert _published() == []                       # never renamed into place: the gate,
    assert len(_tempories()) == 1                   # not the later verify, stopped it


def test_a_temporary_tree_whose_manifest_bytes_are_the_planned_ones_is_published(rt, monkeypatch):
    # the positive control of the row above: same write path, same listing, same bytes
    _manifest_redumped(monkeypatch, sort_keys=True, separators=(',', ':'))
    out = _stage(rt)
    assert _published() == [os.path.basename(out)]
    assert _tempories() == []


# ── 2. staging.py:249-252: a rename that fails with no winner published is a failure, ──
# ──    not a race lost. Line 252 is never executed by any existing test: the two      ──
# ──    publication-race tests both have the winner present. Delete the bare `raise`   ──
# ──    and the call falls through to verify() a directory that was never made, so the ──
# ──    real cause (the disk refusing the rename) is lost and replaced by a            ──
# ──    FileNotFoundError for a name nobody published.                                 ──

def test_a_rename_that_fails_with_nothing_published_refuses_with_its_own_error(rt, monkeypatch):
    def losing(a, b):
        raise OSError(errno.EXDEV, 'fixture rename failure')
    monkeypatch.setattr(os, 'rename', losing)
    with pytest.raises(OSError) as got:
        _stage(rt)
    assert got.value.errno == errno.EXDEV and 'fixture rename failure' in str(got.value)
    assert not isinstance(got.value, FileNotFoundError)   # the cause, not a missing stage
    assert _published() == []                             # nothing was ever renamed
    assert len(_tempories()) == 1                         # its own tree is left where it is


def test_a_rename_that_fails_after_a_winner_published_keeps_the_winner(rt, monkeypatch):
    # the other arm of the same except, so the row above cannot be vacuous
    real = os.rename

    def winner_first(a, b):
        shutil.copytree(a, b)
        raise FileExistsError(errno.EEXIST, 'fixture: another stager won', b)
    monkeypatch.setattr(os, 'rename', winner_first)
    out = _stage(rt)
    assert _published() == [os.path.basename(out)]
    assert staging.verify(out) == out


# ── 3. staging.py:71 `_inside`: the copied file must be inside the pinned root, and ──
# ──    `startswith(rootc + os.sep)` is what keeps a sibling directory whose name just ──
# ──    begins with that root out. Every existing 'outside' test points a source at an ──
# ──    unrelated folder, so dropping the separator and comparing with the bare prefix ──
# ──    would be caught by none of them.                                               ──

def test_a_source_that_resolves_into_a_lookalike_sibling_of_the_pinned_root_refuses(
        rt, monkeypatch):
    real, root = os.path.realpath, os.path.realpath(rt.src)
    want = os.path.normcase(os.path.join(rt.src, 'Lib', 'os.py'))
    lookalike = os.path.join(root + '-evil', 'Lib', 'os.py')     # `root` is its prefix
    monkeypatch.setattr(os.path, 'realpath', lambda p, *a, **k: lookalike
                        if os.path.normcase(os.path.abspath(p)) == want else real(p, *a, **k))
    with pytest.raises(StageError, match='outside'):
        _stage(rt)
    assert not os.path.exists(paths.runtime_dir())   # refused while planning: nothing was made


def test_a_source_inside_a_deeper_folder_of_the_pinned_root_is_admitted(rt):
    # the same `startswith`, taken the honest way: depth is not escape
    for rel, data in DEEP.items():
        p = os.path.join(rt.src, *rel.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(data)
    out = _stage(rt)
    assert set(DEEP) <= set(_files(out))


# ── 4. staging.py:206-208 `verify`: a stage is a name under `runtime/`, and only ──
# ──    under it. The existing test of this branch hands verify() a copy in a folder ──
# ──    with nothing in common with the runtime directory, so a weakening from `==`   ──
# ──    to a prefix match would be caught by no test at all: a full copy of a stage   ──
# ──    beside the real one — `runtime-evil` beside `runtime`, a name the real one is ──
# ──    a prefix of — is not a stage.                                                 ──

def test_a_complete_copy_of_a_stage_beside_the_runtime_directory_is_not_a_stage(rt):
    out = _stage(rt)
    copy = os.path.join(paths.runtime_dir() + '-evil', os.path.basename(out))
    shutil.copytree(out, copy)
    assert staging.verify(out) == out                       # the real one still verifies
    assert _files(copy) == _files(out)                      # and the copy is complete
    with pytest.raises(StageError, match='not a stage'):
        staging.verify(copy)


# ── 5. staging.py:193-196 `_tree`: the manifest is read as data written by whoever ──
# ──    put the tree there, and every shape it can be written wrong in is a refusal. ──
# ──    Only one shape is tested today — `b'not json'`, the ValueError of `loads`. A  ──
# ──    manifest that is valid JSON but has no `files`, or a `files` that is not a    ──
# ──    list of [name, size, digest] rows, escapes through the KeyError/TypeError     ──
# ──    arms of line 195; narrow that tuple and they become bare tracebacks.          ──

@pytest.mark.parametrize('raw', [
    b'{"python": "3.10", "source_root": "x"}',       # KeyError: no 'files'
    b'{"files": 5}',                                  # TypeError: not iterable
    b'[]',                                            # TypeError: not an object
    b'{"files": [["a", 1]]}',                         # ValueError: short row
    b'{"files": [["a", 1, "d", 4]]}',                 # ValueError: long row
], ids=['no-files', 'files-int', 'array', 'short-row', 'long-row'])
def test_a_manifest_that_cannot_be_read_as_a_listing_refuses_and_is_left(rt, raw):
    out = _stage(rt)
    with open(os.path.join(out, MANIFEST), 'wb') as f:
        f.write(raw)
    before = _files(out)
    with pytest.raises(StageError, match='unreadable manifest'):
        staging.verify(out)
    with pytest.raises(StageError, match='unreadable manifest'):
        _stage(rt)                                    # the reuse path reads it again
    assert _files(out) == before                      # refused, never repaired
    assert _runtime() == [os.path.basename(out)]      # and left exactly where it was


def test_a_manifest_that_is_an_empty_listing_still_refuses_a_stage_with_files(rt):
    # the same line's sibling: a readable manifest that names nothing is not a
    # permission to accept a tree that does, and it is caught as a difference
    out = _stage(rt)
    raw = json.dumps({'python': '3.10', 'source_root': out, 'files': []},
                     sort_keys=True, separators=(',', ':')).encode()
    with open(os.path.join(out, MANIFEST), 'wb') as f:
        f.write(raw)
    with pytest.raises(StageError, match='differs from its manifest'):
        staging.verify(out)
    assert _published() == [os.path.basename(out)]


# ── 6. staging.py:336 `stage_mxc`: every artifact is re-scan_granted immediately ──
# ──    before it is opened, on the source. The SDK-wide `verify_mxc` ran before the ──
# ──    copy; this is the one that catches an alias swapped in for the file between   ──
# ──    that scan and the copy. Delete line 336 and the copy still verifies: the     ──
# ──    bytes it reads are the pinned ones, the destination is scanned as itself, so ──
# ──    the staged launcher would have been reached through an alias and accepted.    ──

def test_an_artifact_that_becomes_an_alias_mid_copy_is_never_copied(sdk, tmp_path, monkeypatch):
    root, pins = sdk
    dest = tmp_path / 'stage'
    want = os.path.normcase(os.path.abspath(str(root / staging.MXC_EXE)))
    real_lstat, real_write, done = os.lstat, staging._write, []

    def write(dst, chunks):
        got = real_write(dst, chunks)
        done.append(dst)                                # the copy has begun: the scans of
        return got                                      # verify_mxc are behind us

    def fake(p, *a, **k):
        st = real_lstat(p, *a, **k)
        if done and os.path.normcase(os.path.abspath(p)) == want:
            return _reparse(st)
        return st

    monkeypatch.setattr(staging, '_write', write)
    monkeypatch.setattr(os, 'lstat', fake)
    with pytest.raises(StageError, match='an alias'):
        staging.stage_mxc(root, dest, pins=pins)
    assert len(done) == 1                               # only the artifact before it
    assert not os.path.exists(str(dest / staging.MXC_EXE))
    with pytest.raises(StageError, match='differ from reviewed hashes'):
        staging.verify_mxc(dest, pins=pins)             # a half copy is not a staged SDK


# ── 7. staging.py:268-286 `scan_grants`: a grant it cannot look at is a refusal, and ──
# ──    a grant reached through an alias is refused before it is walked. The walk has  ──
# ──    no failure arm of its own, so anything the OS refuses — a grant that is gone,  ──
# ──    a directory it cannot open — must travel out as it came; the danger is an      ──
# ──    `except OSError: continue` in that walk, which would hand the launcher an      ──
# ──    unscanned grant, and no existing test distinguishes a refusal from a pass. The ──
# ──    `_ancestors(path)` of line 284 is the only thing that looks above a grant: the ──
# ──    walk starts at the grant itself, so delete that call and an SDK reached through ──
# ──    a junction is scanned, hashed and verified as the pinned one — the reviewed    ──
# ──    hashes match, and nothing ever looked at the link that led to it.              ──

def test_a_grant_that_cannot_be_lstat_ed_is_refused_not_skipped(tmp_path):
    gone = str(tmp_path / 'gone')
    with pytest.raises(StageError, match='unreadable entry') as got:
        staging.scan_grants((gone,))
    assert got.value.__cause__.errno == errno.ENOENT
    with pytest.raises(StageError, match='unreadable entry') as got:     # the same through the MXC gate
        staging.verify_mxc(gone, pins={'package.json': 'a' * 64, staging.MXC_EXE: 'b' * 64})
    assert got.value.__cause__.errno == errno.ENOENT


def test_a_grant_whose_entry_cannot_be_read_is_refused_not_skipped(tmp_path, monkeypatch):
    grant = tmp_path / 'grant'
    (grant / 'nested').mkdir(parents=True)
    (grant / 'nested' / 'f.bin').write_bytes(b'f\n')
    real, want = os.lstat, os.path.normcase(os.path.abspath(str(grant / 'nested' / 'f.bin')))

    def fake(p, *a, **k):
        if os.path.normcase(os.path.abspath(p)) == want:
            raise OSError(errno.EACCES, 'fixture: the volume refuses the read')
        return real(p, *a, **k)
    monkeypatch.setattr(os, 'lstat', fake)
    with pytest.raises(StageError, match='unreadable entry') as got:
        staging.scan_grants((str(grant),))
    assert got.value.__cause__.errno == errno.EACCES


def test_a_grant_reached_through_an_aliased_ancestor_is_refused_before_anything_is_copied(
        sdk, tmp_path, monkeypatch):
    # the same SDK, one folder deeper, with that folder reporting a junction: the walk
    # of `scan_grants` never looks above the grant it was handed, and the reviewed pins
    # match either way, so only `_ancestors` can tell the pinned SDK from a look-alike
    # parked behind a link
    root, pins = sdk
    nest = tmp_path / 'nest'
    shutil.copytree(str(root), str(nest / 'sdk'))
    real, below = os.lstat, os.path.abspath(str(nest))

    def fake(p, *a, **k):
        st = real(p, *a, **k)
        return _reparse(st) if os.path.abspath(p) == below else st
    monkeypatch.setattr(os, 'lstat', fake)
    dest = tmp_path / 'stage'
    with pytest.raises(StageError, match='an alias'):
        staging.verify_mxc(nest / 'sdk', pins=pins)
    with pytest.raises(StageError, match='an alias'):
        staging.stage_mxc(nest / 'sdk', dest, pins=pins)
    assert not dest.exists()                            # nothing was staged, and the SDK
    assert set(os.listdir(nest / 'sdk')) == {'bin', 'package.json'}   # is as it was


def test_a_grant_that_cannot_be_lstat_ed_is_refused_with_the_refusal_class(tmp_path):
    with pytest.raises(StageError):
        staging.scan_grants((str(tmp_path / 'gone'),))


# ── 8. staging.py:143-157 and 233-236: every directory above a write is plain before ──
# ──    the write, and every directory of a nested relative path is made before the    ──
# ──    file it holds. Every fixture of every existing test is two levels deep, so a   ──
# ──    `parts[:-1]` that became `parts[-1:]`, or a `range(1, len(parts))` that became  ──
# ──    `range(1, 2)`, would check and make one level and be thanked by the suite.      ──

def test_a_tree_of_three_levels_is_copied_whole(rt_deep):
    out = _stage(rt_deep)
    assert set(DEEP) <= set(_files(out))                # the shape these rows stand on


def test_an_alias_in_a_deep_temporary_directory_stops_every_write_beneath_it(rt_deep,
                                                                             monkeypatch):
    _alias_once_writes(monkeypatch, os.path.join('Lib', 'deep'), writes=1)
    with pytest.raises(StageError, match='an alias'):
        _stage(rt_deep)
    (tmp,) = _tempories()
    top = os.path.join(paths.runtime_dir(), tmp)
    made = set(_files(top))
    assert 'python.exe' in made                           # the copy was well under way
    assert not [r for r in made if r.startswith('Lib/')]  # nothing beneath it was written
    deep = os.path.join(top, 'Lib', 'deep')
    assert os.path.isdir(deep) and os.listdir(deep) == []          # the checked name itself
    assert not os.path.exists(os.path.join(deep, 'er'))            # nothing made through it
    assert _published() == []


def test_an_alias_in_a_deep_source_directory_stops_its_copy(rt_deep, monkeypatch):
    # `_source` walks every component of the relative path from the pinned root down;
    # a loop that started below the middle component would let this one through. The
    # swap happens once planning is over, as a junction swapped in for a directory that
    # was already checked would: `_entry`, `realpath` and the copy all read `os.lstat`.
    target = os.path.normcase(os.path.join(rt_deep.src, 'Lib', 'deep', 'er'))
    real_lstat, real_plan, planned = os.lstat, staging._plan, []

    def plan(*a, **k):
        got = real_plan(*a, **k)
        planned.append(True)
        return got

    def fake(p, *a, **k):
        st = real_lstat(p, *a, **k)
        if planned and os.path.normcase(os.path.abspath(p)) == target:
            return _reparse(st)
        return st
    monkeypatch.setattr(staging, '_plan', plan)
    monkeypatch.setattr(os, 'lstat', fake)
    with pytest.raises(StageError, match='an alias'):
        _stage(rt_deep)
    assert _published() == []


# ── 9. staging.py:75-80 `_hook`: the hook script is only trusted when nothing above ──
# ──    it is an alias, which is what `realpath(...) == abspath(...)` says. The two   ──
# ──    existing tests of it fake the hook's own entry or its own realpath; a check    ──
# ──    narrowed to the leaf — `lstat(hook)` alone, the natural way to get the same    ──
# ──    line count — passes both, and stages a hook read through a junction out of the ──
# ──    pinned tree: plan and copy would follow the same link and agree on its digest. ──

def test_a_hook_reached_through_an_aliased_folder_refuses(rt, monkeypatch):
    # what is aliased is the folder above the hook: its own entry stays a plain file,
    # so only the realpath/abspath comparison of `_hook` can see the junction. A check
    # narrowed to the leaf it opens would let a hook from outside the pinned tree be
    # hashed and copied: plan and copy follow the same link, and agree on its digest.
    real, hook = os.path.realpath, os.path.abspath(rt.hook)
    assert stat.S_ISREG(os.lstat(rt.hook).st_mode)             # plain, as a junction reports
    monkeypatch.setattr(os.path, 'realpath', lambda p, *a, **k: os.path.join(
        str(rt.tmp), 'elsewhere-hooks', os.path.basename(rt.hook))
        if os.path.normcase(os.path.abspath(p)) == os.path.normcase(hook) else real(p, *a, **k))
    with pytest.raises(StageError, match='hook'):
        _stage(rt)
    assert os.listdir(rt.home) == []                     # refused before anything was made


def test_a_hook_under_a_real_symlinked_folder_refuses(rt):
    folder = os.path.dirname(rt.hook)
    link = os.path.join(str(rt.tmp), 'link-to-hooks')
    try:
        os.symlink(folder, link)
    except (OSError, NotImplementedError):
        pytest.skip('this user may not create a symlink here')
    with pytest.raises(StageError, match='hook'):
        staging.stage(rt.src, os.path.join(link, 'hook.py'), version=V)
    assert os.listdir(rt.home) == []


# ── 10. staging.py:133-140 `_runtime` and 49-54 `_present`: `runtime` being there as ──
# ──    a plain file is not a runtime directory. `os.mkdir` reports FileExistsError and ──
# ──    is thanked, so everything after it has to notice on its own; if `_present`      ──
# ──    swallowed the ENOTDIR of the lookup below it — the usual shape of a "treat an   ──
# ──    unreadable path as absent" bug — the stager would go on to build a stage inside ──
# ──    a file and call the outcome a refusal of its own choosing.                      ──

def test_a_runtime_directory_that_is_a_plain_file_refuses_and_is_untouched(make_rt):
    rt = make_rt()
    runtime = paths.runtime_dir()
    with open(runtime, 'wb') as f:
        f.write(b'not a directory\n')
    before = os.lstat(runtime)
    with pytest.raises(StageError, match='not the plain entry expected') as got:
        _stage(rt)
    assert '.tmp-' not in str(got.value)
    assert os.lstat(runtime) == before                   # the same file, never replaced
    with open(runtime, 'rb') as f:
        assert f.read() == b'not a directory\n'


def test_a_name_the_planned_digest_was_published_under_as_a_file_refuses(make_rt, monkeypatch):
    # `_present` says a name is there; `_tree` has to say it is not a directory, and
    # nothing may be written through it or over it
    rt = make_rt()
    digest = _planned_digest(rt)
    os.mkdir(paths.runtime_dir())
    planted = os.path.join(paths.runtime_dir(), digest)
    with open(planted, 'wb') as f:
        f.write(b'in the way\n')
    before = os.lstat(planted)
    with pytest.raises(StageError, match='not the plain entry expected'):
        _stage(rt)
    assert os.lstat(planted) == before and not _tempories()


# ── 11. beyond the ten: staging.py:160-168 `_write` opens `xb` only; staging.py ──
# ──    261-266 `_ancestors` is called at three places (284, 330, 338) and the middle ──
# ──    one is what test_pv20_mxc_staging_gaps.py::test_destination_below_an_aliased_  ──
# ──    parent_refused already pins, while the last — the artifact's own directory,    ──
# ──    re-checked between `os.makedirs` and the write — is pinned by nothing at all.  ──

def test_the_copy_never_opens_a_name_that_is_already_there(sdk, tmp_path):
    root, pins = sdk
    dest = staging.stage_mxc(root, tmp_path / 'stage', pins=pins)
    there = os.path.join(dest, 'package.json')
    with pytest.raises(FileExistsError):
        staging._write(there, [b'replaced\n'])
    with open(there, 'rb') as f:
        assert json.loads(f.read())['name'] == staging.MXC_PACKAGE


def test_a_destination_whose_parent_was_never_there_is_refused_before_it_is_made(sdk, tmp_path):
    root, pins = sdk
    below = os.path.join(str(tmp_path), 'no-such-parent', 'stage')
    with pytest.raises(StageError, match='unreadable entry') as got:
        staging.stage_mxc(root, below, pins=pins)
    assert got.value.__cause__.errno == errno.ENOENT and not os.path.exists(below)


def test_an_alias_swapped_in_for_a_staged_artifact_directory_is_refused_before_the_write(
        sdk, tmp_path, monkeypatch):
    # `os.makedirs` makes `bin/x64` in the fresh copy and `_ancestors` says it is still
    # plain before `open(dst, 'xb')`; without that second look the artifact is written
    # *through* a junction planted in the copy, and only the final `verify_mxc` — after
    # the bytes have gone somewhere else — would notice the name at all
    root, pins = sdk
    dest = tmp_path / 'stage'
    below = os.path.abspath(str(dest / 'bin' / 'x64'))
    real = os.lstat

    def fake(p, *a, **k):
        st = real(p, *a, **k)
        return _reparse(st) if os.path.abspath(p) == below else st
    monkeypatch.setattr(os, 'lstat', fake)
    with pytest.raises(StageError, match='an alias'):
        staging.stage_mxc(root, dest, pins=pins)
    assert os.listdir(below) == []                       # nothing was written through it
    assert 'package.json' not in os.listdir(str(dest))   # the sorted pins stopped at bin
    with pytest.raises(StageError, match='an alias'):     # and the copy is no staged SDK
        staging.verify_mxc(dest, pins=pins)
