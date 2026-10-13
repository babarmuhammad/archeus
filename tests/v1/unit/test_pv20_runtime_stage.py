"""PV-20 C4a (T-039): the standalone runtime stager, on synthetic trees only.

Nothing here reads or copies a real Python install, starts a process or calls a
native API. Aliases are presented through a faked `os.lstat` (a real symlink is
used only where the OS lets this user make one), so the logic is proven and
race resistance is not (C-1013-T034 C1.8)."""

import ast
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
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

SOURCE = {
    'python.exe': b'MZ a fake interpreter',
    'python3.dll': b'stable abi',
    'python310.dll': b'versioned',
    'vcruntime140.dll': b'crt',
    'pyvenv.cfg': b'home = elsewhere',
    'Lib/os.py': b'# os',
    'Lib/encodings/__init__.py': b'# encodings',
    'Lib/json/__init__.py': b'# json',
    'Lib/pyvenv.cfg': b'home = elsewhere',
    'Lib/site-packages/evil.py': b'evil',
    'Lib/test/x.py': b'test',
    'Lib/__pycache__/os.cpython-310.pyc': b'pyc',
    'DLLs/_x.pyd': b'pyd',
}
COPIED = ('python.exe', 'python3.dll', 'python310.dll', 'vcruntime140.dll', 'Lib/os.py',
          'Lib/encodings/__init__.py', 'Lib/json/__init__.py', 'DLLs/_x.pyd')
STAGED = set(COPIED) | {'hook.py', 'python310._pth', MANIFEST}


@pytest.fixture
def rt(tmp_path, archeus_home):
    src = tmp_path / 'py'
    for rel, data in SOURCE.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    hook = tmp_path / 'hooks' / 'hook.py'
    hook.parent.mkdir()
    hook.write_bytes(b'# the hook')
    archeus_home.mkdir()
    return SimpleNamespace(src=str(src), hook=str(hook), home=str(archeus_home), tmp=tmp_path)


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


def _fake_lstat(monkeypatch, target, after=0, **over):
    """`os.lstat` of *target* reports *over*, from its (after+1)-th call on."""
    real, want, calls = os.lstat, os.path.normcase(os.path.abspath(target)), []

    def fake(p, *a, **k):
        st = real(p, *a, **k)
        if os.path.normcase(os.path.abspath(p)) != want:
            return st
        calls.append(p)
        if len(calls) <= after:
            return st
        f = {n: getattr(st, n) for n in ('st_mode', 'st_ino', 'st_dev', 'st_size',
                                          'st_mtime_ns', 'st_nlink')}
        f['st_file_attributes'] = getattr(st, 'st_file_attributes', 0)
        f.update(over)
        return SimpleNamespace(**f)
    monkeypatch.setattr(os, 'lstat', fake)


# ── what a stage holds ──────────────────────────────────────────────────────

def test_a_stage_is_fresh_copies_of_the_closure_and_the_source_is_untouched(rt):
    before = _files(rt.src), _files(os.path.dirname(rt.hook))
    out = _stage(rt)
    assert os.path.dirname(out) == paths.runtime_dir()
    got = _files(out)
    assert set(got) == STAGED          # site-packages, test, __pycache__, pyvenv.cfg left out
    for rel in COPIED:
        assert got[rel] == SOURCE[rel]
        s, d = os.lstat(os.path.join(rt.src, rel)), os.lstat(os.path.join(out, rel))
        assert d.st_nlink == 1 and (d.st_ino, d.st_dev) != (s.st_ino, s.st_dev)
    assert got['hook.py'] == b'# the hook'
    assert (_files(rt.src), _files(os.path.dirname(rt.hook))) == before
    assert sorted(os.listdir(rt.tmp)) == ['archeus-home', 'hooks', 'py']
    assert _runtime() == [os.path.basename(out)]          # the temporary name was renamed


def test_the_pth_pins_the_stage_and_never_imports_site(rt):
    pth = _files(_stage(rt))['python310._pth']
    assert pth == b'Lib\nDLLs\n' and b'import site' not in pth


def test_the_pth_and_the_dll_follow_the_version(rt):
    with open(os.path.join(rt.src, 'python312.dll'), 'wb') as f:
        f.write(b'3.12')
    got = _files(_stage(rt, version=(3, 12)))
    assert {'python312._pth', 'python312.dll'} <= set(got)
    assert not {'python310._pth', 'python310.dll'} & set(got)


@pytest.mark.parametrize('missing', ['python.exe', 'python310.dll', 'Lib'])
def test_a_runtime_without_its_interpreter_dll_or_stdlib_is_refused(rt, missing):
    p = os.path.join(rt.src, missing)
    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    with pytest.raises(StageError, match=missing):
        _stage(rt)
    assert os.listdir(rt.home) == []


@pytest.mark.parametrize('name', ['python.exe', 'python310.dll', 'python3.dll', 'Lib', 'DLLs'])
def test_a_part_of_the_wrong_type_is_refused_before_anything_is_written(rt, name):
    p = os.path.join(rt.src, name)
    was_dir = os.path.isdir(p)
    shutil.rmtree(p) if was_dir else os.remove(p)
    if was_dir:
        with open(p, 'wb') as f:
            f.write(b'a file where a directory belongs')
    else:
        os.mkdir(p)
        with open(os.path.join(p, 'x'), 'wb') as f:
            f.write(b'x')
    with pytest.raises(StageError, match='not the plain entry expected'):
        _stage(rt)
    assert os.listdir(rt.home) == []


@pytest.mark.parametrize('missing', ['python3.dll', 'vcruntime140.dll', 'DLLs'])
def test_an_optional_part_may_be_absent(rt, missing):
    p = os.path.join(rt.src, missing)
    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    got = _files(_stage(rt))
    assert not [r for r in got if r == missing or r.startswith(missing + '/')]


def test_the_manifest_lists_every_other_file_and_names_the_stage(rt):
    out = _stage(rt)
    with open(os.path.join(out, MANIFEST), 'rb') as f:
        raw = f.read()
    m = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == os.path.basename(out)
    assert (m['python'], m['source_root']) == ('3.10', os.path.realpath(rt.src))
    got = _files(out)
    del got[MANIFEST]
    assert {r: (n, h) for r, n, h in m['files']} == \
        {r: (len(b), hashlib.sha256(b).hexdigest()) for r, b in got.items()}


def test_the_digest_is_stable_and_follows_the_content_and_its_metadata(rt):
    first = _stage(rt)
    assert _stage(rt) == first
    with open(rt.hook, 'wb') as f:
        f.write(b'# a changed hook')
    second = _stage(rt)
    with open(os.path.join(rt.src, 'python312.dll'), 'wb') as f:
        f.write(b'3.12')
    third = _stage(rt, version=(3, 12))
    moved = os.path.join(str(rt.tmp), 'py2')
    shutil.copytree(rt.src, moved)
    fourth = staging.stage(moved, rt.hook, version=(3, 12))
    assert len({first, second, third, fourth}) == 4
    assert _runtime() == sorted(os.path.basename(p) for p in (first, second, third, fourth))


def test_an_existing_stage_is_reused_and_never_rewritten(rt):
    out = _stage(rt)
    snap = {p: (os.lstat(os.path.join(out, p)).st_ino, os.lstat(os.path.join(out, p)).st_mtime_ns)
            for p in _files(out)}
    assert _stage(rt) == out
    assert {p: (os.lstat(os.path.join(out, p)).st_ino,
                os.lstat(os.path.join(out, p)).st_mtime_ns) for p in _files(out)} == snap
    assert _runtime() == [os.path.basename(out)]


# ── a stage that fails verification is refused, never repaired ──────────────

def _corrupt(out, kind, tmp):
    p = os.path.join(out, 'Lib', 'os.py')
    if kind == 'changed':
        with open(p, 'wb') as f:
            f.write(b'# planted')
    elif kind == 'added':
        with open(os.path.join(out, 'Lib', 'sitecustomize.py'), 'wb') as f:
            f.write(b'planted')
    elif kind == 'removed':
        os.remove(p)
    elif kind == 'no manifest':
        os.remove(os.path.join(out, MANIFEST))
    elif kind == 'unreadable manifest':
        with open(os.path.join(out, MANIFEST), 'wb') as f:
            f.write(b'not json')
    elif kind == 'manifest not its name':
        m = os.path.join(out, MANIFEST)
        with open(m, 'rb') as f:
            data = json.loads(f.read())
        with open(m, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1)          # the same listing, other bytes
    elif kind == 'second name':
        os.link(p, os.path.join(str(tmp), 'second-name'))


@pytest.mark.parametrize('kind', ['changed', 'added', 'removed', 'no manifest',
                                  'unreadable manifest', 'manifest not its name',
                                  'second name'])
def test_a_corrupt_stage_is_refused_and_left_exactly_as_it_is(rt, kind):
    out = _stage(rt)
    _corrupt(out, kind, rt.tmp)
    snap, listing = _files(out), _runtime()
    with pytest.raises(StageError):
        staging.verify(out)
    with pytest.raises(StageError):
        _stage(rt)
    assert (_files(out), _runtime()) == (snap, listing)      # no repair, no other name


def test_a_leftover_temporary_directory_is_never_a_stage(rt, tmp_path, monkeypatch):
    digest = os.path.basename(_stage(rt))
    other = tmp_path / 'other-home'
    other.mkdir()
    monkeypatch.setenv('ARCHEUS_HOME', str(other))
    os.mkdir(paths.runtime_dir())
    leftover = os.path.join(paths.runtime_dir(), '.tmp-%s-1-0000000000000000' % digest)
    shutil.copytree(os.path.join(rt.home, 'runtime', digest), leftover)  # finished, never renamed
    snap = _files(leftover)
    with pytest.raises(StageError):
        staging.verify(leftover)               # its content is valid; its name is not a digest
    out = _stage(rt)
    assert out == os.path.join(paths.runtime_dir(), digest)
    assert _files(leftover) == snap
    assert _runtime() == sorted([digest, os.path.basename(leftover)])


def test_a_stage_outside_the_runtime_directory_is_refused(rt, tmp_path):
    out = _stage(rt)
    copy = tmp_path / 'elsewhere' / os.path.basename(out)
    shutil.copytree(out, copy)
    with pytest.raises(StageError):
        staging.verify(str(copy))


# ── aliases, on the source ─────────────────────────────────────────────────

@pytest.mark.parametrize('rel,over', [
    ('Lib/os.py', {'st_file_attributes': REPARSE}),
    ('Lib/encodings', {'st_file_attributes': REPARSE}),             # a junction
    ('Lib/json', {'st_mode': stat.S_IFLNK | 0o777}),                # a directory symlink
    ('python.exe', {'st_mode': stat.S_IFLNK | 0o777}),
    ('DLLs/_x.pyd', {'st_mode': stat.S_IFIFO | 0o644}),            # neither file nor dir
    ('', {'st_file_attributes': REPARSE}),                          # the source root itself
])
def test_an_alias_or_special_entry_in_the_source_refuses_before_anything_is_written(
        rt, monkeypatch, rel, over):
    _fake_lstat(monkeypatch, os.path.join(rt.src, rel), **over)
    with pytest.raises(StageError):
        _stage(rt)
    assert os.listdir(rt.home) == []


def test_a_real_symlink_in_the_source_refuses(rt):
    try:
        os.symlink(os.path.join(rt.src, 'Lib', 'os.py'), os.path.join(rt.src, 'Lib', 'ln.py'))
    except (OSError, NotImplementedError):
        pytest.skip('this user may not create a symlink here')
    with pytest.raises(StageError):
        _stage(rt)
    assert os.listdir(rt.home) == []


def test_an_entry_that_resolves_outside_the_source_refuses(rt, monkeypatch, tmp_path):
    real, target = os.path.realpath, os.path.normcase(os.path.join(rt.src, 'Lib', 'os.py'))
    monkeypatch.setattr(os.path, 'realpath', lambda p, *a, **k: str(tmp_path / 'os.py')
                        if os.path.normcase(os.path.abspath(p)) == target else real(p, *a, **k))
    with pytest.raises(StageError, match='outside'):
        _stage(rt)
    assert os.listdir(rt.home) == []


def test_a_hook_reached_through_an_alias_refuses(rt, monkeypatch, tmp_path):
    _fake_lstat(monkeypatch, rt.hook, st_file_attributes=REPARSE)
    with pytest.raises(StageError):
        _stage(rt)
    monkeypatch.undo()
    real, target = os.path.realpath, os.path.normcase(rt.hook)
    monkeypatch.setattr(os.path, 'realpath', lambda p, *a, **k: str(tmp_path / 'real-hook.py')
                        if os.path.normcase(os.path.abspath(p)) == target else real(p, *a, **k))
    with pytest.raises(StageError, match='hook'):
        _stage(rt)
    assert os.listdir(rt.home) == []


def test_a_source_that_changes_while_it_is_copied_refuses(rt, monkeypatch):
    p = os.path.join(rt.src, 'Lib', 'os.py')
    _fake_lstat(monkeypatch, p, after=1, st_mtime_ns=1)      # the plan's view, then another
    with pytest.raises(StageError, match='changed'):
        _stage(rt)
    assert _published() == [] and len(_runtime()) == 1        # the temporary tree stays


def test_a_source_whose_bytes_change_under_the_same_metadata_refuses(rt, monkeypatch):
    p = os.path.join(rt.src, 'Lib', 'os.py')
    st, real = os.lstat(p), staging._runtime

    def swap():
        with open(p, 'wb') as f:
            f.write(b'# zz')                                  # same size
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
        return real()
    monkeypatch.setattr(staging, '_runtime', swap)
    with pytest.raises(StageError, match='changed'):
        _stage(rt)
    assert _published() == []


# ── aliases, on the destination ───────────────────────────────────────────

def test_an_aliased_archeus_home_refuses_before_any_write(rt, monkeypatch):
    _fake_lstat(monkeypatch, rt.home, st_file_attributes=REPARSE)
    with pytest.raises(StageError):
        _stage(rt)
    assert os.listdir(rt.home) == []


def test_an_aliased_runtime_directory_refuses_before_any_write(rt, monkeypatch):
    os.mkdir(paths.runtime_dir())
    _fake_lstat(monkeypatch, paths.runtime_dir(), st_file_attributes=REPARSE)
    with pytest.raises(StageError):
        _stage(rt)
    assert _runtime() == []


@pytest.mark.parametrize('rel', ['', 'Lib', 'Lib/encodings/__init__.py'])
def test_an_alias_inside_a_published_stage_refuses(rt, monkeypatch, rel):
    out = _stage(rt)
    listing = _runtime()
    _fake_lstat(monkeypatch, os.path.join(out, rel), st_file_attributes=REPARSE)
    with pytest.raises(StageError):
        staging.verify(out)
    with pytest.raises(StageError):
        _stage(rt)
    assert _runtime() == listing


def _planting(monkeypatch, name, data=b'planted'):
    """A writer that drops *name* into the temporary directory as it is made."""
    real = os.mkdir

    def mkdir(p, *a, **k):
        real(p, *a, **k)
        if os.path.basename(p).startswith('.tmp-'):
            with open(os.path.join(p, name), 'wb') as f:
                f.write(data)
    monkeypatch.setattr(os, 'mkdir', mkdir)


@pytest.mark.parametrize('rel,writes,left', [
    ('Lib', 0, {}),
    ('Lib/encodings', 0, {}),
    # swapped once the first file beneath it is written: nothing after that one
    ('Lib', sum('/' not in r for r in COPIED) + 1,
     {'encodings/__init__.py': b'# encodings'})])
def test_a_directory_made_in_the_temporary_tree_is_checked_before_every_write_beneath_it(
        rt, monkeypatch, rel, writes, left):
    # the directory the stager made reports a reparse point once *writes* files are in
    # the tree, as a junction swapped in for it would: nothing more is written through it
    real, real_write, done = os.lstat, staging._write, []
    tail = os.path.normcase(os.path.join(*rel.split('/')))

    def write(dst, chunks):
        got = real_write(dst, chunks)
        done.append(dst)
        return got

    def fake(p, *a, **k):
        st = real(p, *a, **k)
        parent = os.path.dirname(os.path.abspath(p))
        while os.path.basename(parent) and not os.path.basename(parent).startswith('.tmp-'):
            parent = os.path.dirname(parent)
        if len(done) < writes or not os.path.basename(parent) or \
                os.path.normcase(os.path.relpath(os.path.abspath(p), parent)) != tail:
            return st
        return SimpleNamespace(st_mode=st.st_mode, st_ino=st.st_ino, st_dev=st.st_dev,
                               st_size=st.st_size, st_mtime_ns=st.st_mtime_ns,
                               st_nlink=st.st_nlink, st_file_attributes=REPARSE)
    monkeypatch.setattr(staging, '_write', write)
    monkeypatch.setattr(os, 'lstat', fake)
    with pytest.raises(StageError, match='an alias'):
        _stage(rt)
    (tmp,) = _runtime()
    assert _files(os.path.join(paths.runtime_dir(), tmp, *rel.split('/'))) == left
    assert _published() == []


TOP = sum('/' not in r for r in COPIED)
DIRS = {'/'.join(r.split('/')[:i]) for r in COPIED for i in range(1, r.count('/') + 1)}


@pytest.mark.parametrize('which', ['home', 'runtime', 'tmp'])
@pytest.mark.parametrize('writes,dirs', [
    (1, 0),                         # after the first copy
    (TOP, 0),                       # before the first mkdir
    (len(STAGED) - 2, len(DIRS))])  # before the _pth
def test_the_destination_chain_is_checked_again_before_every_write(rt, monkeypatch, which,
                                                                   writes, dirs):
    # once *writes* files are in the temporary tree, *which* reports a reparse point,
    # as a junction swapped in for it would: nothing more is written. The checks narrow
    # that window; they do not close it (C-1013-T034 C1.8)
    real_lstat, real_write, done = os.lstat, staging._write, []

    def write(dst, chunks):
        got = real_write(dst, chunks)
        done.append(dst)
        return got

    def target(p):
        p = os.path.normcase(os.path.abspath(p))
        runtime = os.path.normcase(os.path.abspath(paths.runtime_dir()))
        return {'home': p == os.path.normcase(os.path.abspath(paths.archeus_home())),
                'runtime': p == runtime,
                'tmp': os.path.dirname(p) == runtime and
                os.path.basename(p).startswith('.tmp-')}[which]

    def fake(p, *a, **k):
        st = real_lstat(p, *a, **k)
        if len(done) < writes or not target(p):
            return st
        return SimpleNamespace(st_mode=st.st_mode, st_ino=st.st_ino, st_dev=st.st_dev,
                               st_size=st.st_size, st_mtime_ns=st.st_mtime_ns,
                               st_nlink=st.st_nlink, st_file_attributes=REPARSE)
    monkeypatch.setattr(staging, '_write', write)
    monkeypatch.setattr(os, 'lstat', fake)
    with pytest.raises(StageError, match='an alias'):
        _stage(rt)
    (tmp,) = _runtime()
    top = os.path.join(paths.runtime_dir(), tmp)
    assert len(done) == writes
    assert len(_files(top)) == writes
    assert sum(len(ds) for _d, ds, _n in os.walk(top)) == dirs     # nor made through it
    assert _published() == []


def test_a_name_planted_in_the_temporary_directory_is_never_written_through(rt, monkeypatch):
    _planting(monkeypatch, 'python.exe')
    with pytest.raises(FileExistsError):
        _stage(rt)
    (tmp,) = _runtime()
    assert _published() == []
    with open(os.path.join(paths.runtime_dir(), tmp, 'python.exe'), 'rb') as f:
        assert f.read() == b'planted'


def test_a_temporary_tree_that_is_not_what_was_planned_is_never_published(rt, monkeypatch):
    _planting(monkeypatch, 'sitecustomize.py')
    with pytest.raises(StageError):
        _stage(rt)
    assert _published() == [] and len(_runtime()) == 1


# ── publication ────────────────────────────────────────────────────────────

def test_a_lost_publication_race_uses_the_winner_and_keeps_its_own_tree(rt, monkeypatch):
    def winner_first(a, b):
        shutil.copytree(a, b)                         # another stager published first
        raise FileExistsError(b)
    monkeypatch.setattr(os, 'rename', winner_first)
    out = _stage(rt)
    (tmp,) = [n for n in _runtime() if n.startswith('.tmp-')]
    assert _files(out) == _files(os.path.join(paths.runtime_dir(), tmp))


def test_a_corrupt_winner_is_refused_and_left_as_it_is(rt, monkeypatch):
    def corrupt_winner(a, b):
        shutil.copytree(a, b)
        with open(os.path.join(b, 'Lib', 'os.py'), 'wb') as f:
            f.write(b'# planted')
        raise FileExistsError(b)
    monkeypatch.setattr(os, 'rename', corrupt_winner)
    with pytest.raises(StageError):
        _stage(rt)
    (final,) = _published()
    assert _files(os.path.join(paths.runtime_dir(), final))['Lib/os.py'] == b'# planted'
    assert len(_runtime()) == 2


def test_the_real_rename_never_replaces_a_published_stage(rt, monkeypatch):
    real = os.rename

    def racing(a, b):
        shutil.copytree(a, b)
        real(a, b)          # Windows: FileExistsError; POSIX: a non-empty target refuses too
    monkeypatch.setattr(os, 'rename', racing)
    out = _stage(rt)
    assert len(_runtime()) == 2 and staging.verify(out) == out


@pytest.mark.skipif(os.name != 'nt', reason="POSIX rename(2) replaces an empty directory; "
                                             "isolated dispatch exists only on Windows")
def test_on_windows_the_rename_never_replaces_even_an_empty_directory(rt, monkeypatch):
    real = os.rename

    def racing(a, b):
        os.mkdir(b)
        real(a, b)
    monkeypatch.setattr(os, 'rename', racing)
    with pytest.raises(StageError):
        _stage(rt)
    (final,) = _published()
    assert os.listdir(os.path.join(paths.runtime_dir(), final)) == []
    assert len(_runtime()) == 2


# ── nothing here deletes, and nothing resets it ─────────────────────────────

def test_the_stager_holds_no_primitive_that_deletes_replaces_or_follows():
    with open(staging.__file__, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    banned = {'remove', 'unlink', 'rmdir', 'removedirs', 'rmtree', 'replace', 'truncate',
              'stat', 'isdir', 'isfile', 'exists', 'islink', 'copy', 'copy2', 'copyfile',
              'copytree', 'link', 'symlink'}           # `stat` as os.stat: it follows links
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not attrs & banned, attrs & banned
    assert 'shutil' not in names and 'rename' in attrs
    modes = {c.args[1].value for c in ast.walk(tree) if isinstance(c, ast.Call)
             and isinstance(c.func, ast.Name) and c.func.id == 'open'}
    assert modes == {'rb', 'xb'}


def test_the_runtime_is_v1s_and_no_reset_names_it(archeus_home):
    assert 'runtime' in paths.V1_OWNED
    assert paths.runtime_dir() == os.path.join(str(archeus_home), 'runtime')
    with open(os.path.join(ROOT, 'docs', 'architecture', 'migration-plan.md'),
              encoding='utf-8') as f:
        text = f.read()
    reset = text[text.index('To reset V1'):text.index('is **never** deleted')]
    assert '`run/`' in reset and 'runtime' not in reset
