"""T-232 — the ten highest-risk GAPs of `archeus/node/local.py` (and the one open row
of `node/staging.py`) named by the T-210 inventory, as unit tests.

T-210 measured these two modules against `test_pv20_isolation.py` and
`test_pv20_runtime_stage.py` only, and listed what those two never reach. Each class
below is one numbered GAP of its "ten highest-risk GAPs" list, in that order:

1  TestStoreSeal            `store_open` — the K1 seal, its refusals, what they leave
2  TestStoreFetch           `store_fetch` — the gate, the shapes, the lost race
3  TestImportPlan           `import_workspace` — the seed map as the only authority
4  TestSeed                 `seed_workspace` — fresh-only, shapes, `_seed_meta`, the clock
5  TestByteCore             `_stream` — the byte core every store read goes through
6  TestHostileSource        `_source`, `_store_pin`, `_pin_files`, `_outside_executions`
7  TestChecks               `run_check` and `run_confined_check` over a faked isolation
8  TestEStop                `estop_without_core` — the sentinel first, pid reuse honoured
9  TestRegistryMailbox      `registry`/`unended`/`compact_registry`, `pending_requests`
9  TestStagingPresent       `_present` (staging.py) — the one GAP row of table B
10 TestWorktreesAndMerge    `add_worktree`/`mission_worktree`/`git_snapshot`/`git_merge`

Style follows the two pattern files: a synthetic fixture per hazard, an assertion of
what a refusal left behind, and a positive control wherever a refusal alone could be
vacuous. Tests marked `needs_git` are the only ones that start Git; the rest prove the
pure-Python refusals without it and say so, by tripping on any attempt to start it.
Every child is this interpreter, started with an absolute argv, as the pattern files
start theirs.

T-246 ran this file on Windows 11 and fixed what the machine, not Core, decided there: no
assertion was dropped or loosened. The environment each child is handed drops values past
the 32767 characters `Popen` refuses (pytest's own bookkeeping, which no assertion reads),
the oversized `.git` file row keeps a short id and brings Core's cap down for its row
alone, the fixture repository states its `core.autocrlf` instead of inheriting the
installer's, the thread check names the two threads `_stream` starts rather than asking
which threads happen to be alive, and the fresh-only refusal is named by exception type
and errno instead of the operating system's wording. Five rows are skipped where Windows
has a genuinely different file system to answer with: the names `?`, `:` and a reserved
device name, the backslash that is a separator there and not a character of a name, and
the case-folded pair that NTFS collapses into one file — each with its reason on the
marker, and every other row running on both platforms.
"""

import errno
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import zlib
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.infra import paths
from archeus.node import local, staging
from archeus.node.local import EMPTY_TREE, STORE_HEAD, LocalNode, StoreError

GIT = shutil.which('git')
needs_git = pytest.mark.skipif(not GIT, reason='no absolute git on PATH')
#: Windows refuses to start a child carrying an environment value longer than this
#: (`Popen` raises ValueError for it), and pytest names the running test in
#: `PYTEST_CURRENT_TEST`, whose parametrized id a row can make long: no child this
#: file starts carries one, and no assertion here reads such a value (T-246 cause 1)
ENV_MAX = 32767
#: the same refusal on the two file systems where a name cannot exist at all: `?`, `:`
#: and a device name are not Windows file-name characters, so the file the row makes
#: cannot be made, and Core is never asked about it (T-246 cause 5)
nt_no_such_name = pytest.mark.skipif(
    sys.platform == 'win32',
    reason='not a name the Windows file system carries: the file cannot be made to be '
           'refused, so the refusal is not a behaviour Windows has')
#: the version string a pin record holds where Git is never started
VERSION = 'git version 2.50.0'
#: what `init --bare -q --object-format=sha1 --template=<empty folder>` writes (T-048)
INIT_CONFIG = (b'[core]\n\trepositoryformatversion = 0\n\tfilemode = false\n'
               b'\tbare = true\n\tsymlinks = false\n\tignorecase = true\n')


#: the real resolver, taken before any test can cover it
_EXE = local._git_exe


@pytest.fixture(autouse=True)
def no_stray_git(monkeypatch):
    """This module's own guard: a test that never meant to run Git says so the moment it
    tries, instead of passing or failing on whatever Git the machine happens to have.
    A test that does mean it asks for `real_git`, which uncovers the resolver again."""
    def boom(*a, **k):
        raise AssertionError('Git was reached by a call that must never reach it: %r'
                             % (a[:1] or k,))
    monkeypatch.setattr(local, '_git_exe', boom)
    local._VERSION.clear()
    yield
    _EXE.cache_clear()
    local._VERSION.clear()


@pytest.fixture
def real_git(monkeypatch):
    """The one place the pinned Git is really resolved and really run."""
    monkeypatch.setattr(local, '_git_exe', _EXE)
    _EXE.cache_clear()
    local._VERSION.clear()
    return _EXE()


def _blob(data):
    """Git's own blob id of *data*: the id a seeded entry has to keep."""
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def _children(monkeypatch):
    """Every child started through `Popen` (`run_check` and `_stream` reach it
    themselves), so a test can name who was started, who was killed, who was not."""
    real, started = subprocess.Popen, []

    def guard(argv, *a, **k):
        p = real(argv, *a, **k)
        started.append(p)
        return p
    monkeypatch.setattr(subprocess, 'Popen', guard)
    return started


def _child_env(base):
    """A copy of *base* that a Windows `Popen` accepts: values past `ENV_MAX` dropped,
    which are pytest's own bookkeeping and never what a test here asserts on."""
    return {k: v for k, v in base.items() if len(v) <= ENV_MAX}


def _threads(monkeypatch):
    """Every `threading.Thread` the code under test starts with a target, as
    (target, thread), so a test can name the feeder and the drainer it is checking
    for. Which threads happen to be alive is not a stable comparison on Windows, where
    the test runner keeps worker threads of its own that Core never started (T-246
    cause 6). A subclass, not a wrapper: `threading.Timer` calls `Thread.__init__(self)`
    through this name and must still initialize the object it was called on."""
    made, real = [], threading.Thread

    class Recorder(real):
        def __init__(self, *a, **k):
            real.__init__(self, *a, **k)      # not super(): `self` may be a plain Thread
            if k.get('target') is not None:   # or a Timer, whose own base is the real one
                made.append((k['target'], self))
    monkeypatch.setattr(threading, 'Thread', Recorder)
    return made


def _pinned(monkeypatch):
    """Core's pin area, with Git resolved but never started: enough for `_pin_record`,
    which only names the executable and its version."""
    exe = os.path.abspath(sys.executable)
    monkeypatch.setattr(local, '_git_exe', lambda: exe)
    local._VERSION[exe] = VERSION
    return local._pin_files(()), exe


def _sealed_store(monkeypatch, pid=None):
    """A store exactly as a seal leaves it, made by hand: Core's own config, HEAD and
    empty-tree object, Core's claim and Core's pin record. `store_open` then needs no
    Git at all, which is what makes every one of its refusals provable in this file."""
    pid = pid or ids.new_id('project')
    _pinned(monkeypatch)
    store = paths.repo_store(pid)
    os.makedirs(os.path.join(store, 'refs'))
    with open(os.path.join(store, 'config'), 'wb') as f:
        f.write(INIT_CONFIG)
    with open(os.path.join(store, 'HEAD'), 'wb') as f:
        f.write(STORE_HEAD.encode())
    objects = os.path.join(store, 'objects', EMPTY_TREE[:2])
    os.makedirs(objects)
    with open(os.path.join(objects, EMPTY_TREE[2:]), 'wb') as f:
        f.write(zlib.compress(b'tree 0\x00'))
    open(os.path.join(paths.repos_dir(), '.pin', pid + '.owned'), 'xb').close()
    _write_record(store, pid)
    return pid, store


def _write_record(store, pid, **over):
    """Core's own pin record, optionally made to lie."""
    record = dict(local._pin_record(store, VERSION))
    record.update(over)
    with open(os.path.join(paths.repos_dir(), '.pin', pid + '.json'), 'w',
              encoding='utf-8') as f:
        json.dump(record, f, sort_keys=True)
    return record


def _manifest(prefix, rows):
    """A seed map as `ls-tree -r -z -l --full-tree` hands it over, every record checked
    on the way in: rows of (mode, object id, size, path)."""
    m = local._Manifest(prefix)
    m.feed(b''.join(b'%s %s %s %s\t%s\0' % (
        mode.encode(), b'commit' if mode == '160000' else b'blob', oid.encode(),
        b'-' if mode == '160000' else str(size).encode(), path.encode())
        for mode, oid, size, path in rows))
    m.end()
    return m


def _tree(top, files=(), dirs=()):
    """A working tree of literal files and directories, no Git involved."""
    os.makedirs(top, exist_ok=True)
    for rel, data in files:
        p = os.path.join(top, *rel.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(data)
    for rel in dirs:
        os.makedirs(os.path.join(top, *rel.split('/')), exist_ok=True)
    return top


def _snapshot(top):
    """Every entry of a tree with what it is, so a refusal can be shown to have removed
    nothing it disliked (keep-all, A4-4)."""
    out = {}
    for d, dirs, names in os.walk(top):
        for n in dirs + names:
            p = os.path.join(d, n)
            st = os.lstat(p)
            out[os.path.relpath(p, top)] = (st.st_mode, st.st_ino, st.st_size)
    return out


def _symlink_ok(tmp_path):
    probe = str(tmp_path / 'probe')
    try:
        os.symlink(str(tmp_path), probe)
    except (OSError, NotImplementedError):
        return False
    os.remove(probe)
    return True


def _clean_env(tmp_path):
    """A Git that can see nobody's global or system configuration, in an environment
    that is told nothing about Git."""
    (tmp_path / 'global.cfg').write_text('')
    base = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    base.update(HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path), GIT_CONFIG_NOSYSTEM='1',
                GIT_CONFIG_GLOBAL=str(tmp_path / 'global.cfg'))
    return _child_env(base)


def _git(cwd, *args, env, data=None):
    r = subprocess.run([GIT, '-c', 'user.name=t', '-c', 'user.email=t@t'] + list(args),
                       cwd=str(cwd), env=env, capture_output=True,
                       input=data, stdin=None if data is not None else subprocess.DEVNULL)
    assert r.returncode == 0, (args, r.returncode, r.stderr)
    return r.stdout.decode('utf-8', 'replace').strip()


def _repo(tmp_path, name='source'):
    """A user repository of two commits made in pytest temp, with the text-filter answer
    the test cannot leave to the machine it runs on. `tip` is what the branch names when
    the fixture is done, `base` the commit before it: an expectation taken before the
    branch moved is what a lost race looks like."""
    env = _clean_env(tmp_path)
    root = tmp_path / name
    root.mkdir()
    _git(root, 'init', '-q', '-b', 'main', env=env)
    # the repository's own answer to core.autocrlf, said before anything is committed or
    # checked out: Git for Windows installs it as true in the user's config, which the
    # test's own `_git` never reads (its config is pinned empty) while the plain `git`
    # calls Core makes to add a worktree and merge in this repository do, and a fixture
    # byte checked out under it comes back with a CR in it (T-246 cause 3)
    _git(root, 'config', 'core.autocrlf', 'false', env=env)
    (root / 'a.txt').write_bytes(b'one\n')
    _git(root, 'add', '-A', env=env)
    _git(root, 'commit', '-q', '-m', 'c1', env=env)
    base = _git(root, 'rev-parse', 'HEAD', env=env)
    (root / 'a.txt').write_bytes(b'two\n')
    _git(root, 'add', '-A', env=env)
    _git(root, 'commit', '-q', '-m', 'c2', env=env)
    return root, base, _git(root, 'rev-parse', 'HEAD', env=env), env


# ── GAP 1: `store_open`, the K1 seal ─────────────────────────────────────────

class TestStoreSeal:
    def test_a_store_below_an_execution_area_is_refused_before_core_makes_anything(
            self, monkeypatch):
        pid = ids.new_id('project')
        store = paths.repo_store(pid)                 # repos/<pid> under ARCHEUS_HOME
        with pytest.raises(StoreError, match='inside an execution area'):
            LocalNode.store_open(pid, workdirs=[os.path.dirname(store)])
        assert not os.path.exists(paths.repos_dir())  # not even the pin area was made

    def test_a_store_past_the_length_git_writes_is_refused_naming_what_to_change(
            self, monkeypatch):
        windows_only = local.STORE_MAX is None        # the cap exists on nt alone (T-115d)
        monkeypatch.setattr(local, 'STORE_MAX', 20)
        with pytest.raises(StoreError, match='Set ARCHEUS_HOME to a shorter folder'):
            LocalNode.store_open(ids.new_id('project'), workdirs=())
        assert local.STORE_MAX == 20 and windows_only == (os.name != 'nt')
        assert not os.path.exists(paths.repos_dir())

    def test_a_sealed_store_is_reopened_by_checking_alone_and_starts_no_git(self, monkeypatch):
        pid, store = _sealed_store(monkeypatch)
        asked = []
        monkeypatch.setattr(LocalNode, 'store_git',
                            staticmethod(lambda *a, **k: asked.append((a, k))))
        assert LocalNode.store_open(pid, workdirs=()) == store
        assert LocalNode.store_open(pid, workdirs=()) == store
        assert asked == []                            # a reopen only checks
        with open(os.path.join(store, 'HEAD'), 'rb') as f:
            assert f.read().decode() == STORE_HEAD    # unborn: no tree is ever current
        assert os.path.isfile(os.path.join(store, 'objects', EMPTY_TREE[:2], EMPTY_TREE[2:]))
        assert os.path.isfile(os.path.join(paths.repos_dir(), '.pin', pid + '.owned'))

    @pytest.mark.parametrize('what', ['config', 'head', 'object', 'record', 'claim',
                                      'held-refs', 'unsealed-config', 'hooks', 'alternates',
                                      'hardlink', 'alias'])
    def test_every_way_a_seal_can_lie_is_refused_and_leaves_the_store_whole(
            self, monkeypatch, tmp_path, what):
        pid, store = _sealed_store(monkeypatch)
        pin = os.path.join(paths.repos_dir(), '.pin')
        record, cfg = os.path.join(pin, pid + '.json'), os.path.join(store, 'config')
        if what == 'config':                          # not the config Core sealed
            with open(cfg, 'ab') as f:
                f.write(b'[core]\n\thooksPath = /tmp\n')
        elif what == 'head':
            with open(os.path.join(store, 'HEAD'), 'wb') as f:
                f.write(b'ref: refs/heads/main\n')
        elif what == 'object':
            os.remove(os.path.join(store, 'objects', EMPTY_TREE[:2], EMPTY_TREE[2:]))
        elif what == 'record':
            _write_record(store, pid, version='git version 1.0.0')
        elif what == 'claim':
            os.remove(os.path.join(pin, pid + '.owned'))
        elif what == 'held-refs':                     # refs with nothing sealing them
            os.makedirs(os.path.join(store, 'refs', 'heads'))
            with open(os.path.join(store, 'refs', 'heads', 'x'), 'wb') as f:
                f.write(b'0' * 40)
            os.remove(record)
        elif what == 'unsealed-config':
            with open(cfg, 'ab') as f:
                f.write(b'[user]\n\tname = somebody\n')
            os.remove(record)
        elif what == 'hooks':
            os.makedirs(os.path.join(store, 'hooks'))
            open(os.path.join(store, 'hooks', 'post-commit'), 'wb').close()
        elif what == 'alternates':
            os.makedirs(os.path.join(store, 'objects', 'info'))
            open(os.path.join(store, 'objects', 'info', 'alternates'), 'wb').close()
        elif what == 'hardlink':
            if not hasattr(os, 'link'):
                pytest.skip('this platform makes no hard links')
            os.link(cfg, os.path.join(store, 'borrowed'))     # some other path's bytes
        else:
            if not _symlink_ok(tmp_path):
                pytest.skip('this user may not make a symlink')
            os.remove(os.path.join(store, 'HEAD'))            # HEAD is somebody else's now
            os.symlink(str(tmp_path / 'elsewhere'), os.path.join(store, 'HEAD'))
        before = _snapshot(store)                     # from here nothing may change
        wants = {'config': 'not the one Core sealed', 'head': 'not as Core sealed it',
                 'object': 'not as Core sealed it', 'record': 'not the one Core sealed',
                 'claim': 'never claimed', 'held-refs': 'holds refs',
                 'unsealed-config': 'config Core did not write', 'hooks': 'a store with hooks',
                 'alternates': 'objects/info/alternates', 'hardlink': 'a hard-linked file',
                 'alias': 'alias'}
        with pytest.raises(OSError, match=wants[what]):
            LocalNode.store_open(pid, workdirs=())
        assert _snapshot(store) == before             # keep-all: nothing removed either

    @needs_git
    def test_a_store_is_claimed_made_and_sealed_once_by_the_pinned_git(self, monkeypatch,
                                                                       real_git):
        pid = ids.new_id('project')
        asked, real = [], LocalNode.store_git

        def spy(mode, args, **kw):
            asked.append((mode, tuple(args)))
            return real(mode, args, **kw)
        monkeypatch.setattr(LocalNode, 'store_git', staticmethod(spy))
        store = LocalNode.store_open(pid, workdirs=())
        assert store == paths.repo_store(pid)
        assert [m for m, _a in asked] == ['version', 'init', 'seal', 'seal']
        with open(os.path.join(store, 'config'), 'rb') as f:
            written = f.read()
        # `_INIT_CONFIG` is a text pattern over the bytes init wrote: decoded whole, with
        # the bytes themselves kept for the digest below (a str pattern on bytes raises
        # TypeError, which is what Windows showed at this line: T-246 cause 2)
        assert local._INIT_CONFIG.fullmatch(written.decode('utf-8'))   # what init --bare wrote
        with open(os.path.join(store, 'HEAD'), 'rb') as f:
            assert f.read().decode() == STORE_HEAD
        with open(os.path.join(paths.repos_dir(), '.pin', pid + '.json'), encoding='utf-8') as f:
            assert json.load(f) == {'git': real_git, 'version': local._VERSION[real_git],
                                    'empty_tree': EMPTY_TREE,
                                    'config_sha256': hashlib.sha256(written).hexdigest()}
        assert LocalNode.store_read(pid, ['cat-file', '-t', EMPTY_TREE], workdirs=()).strip() \
            == 'tree'
        asked.clear()
        assert LocalNode.store_open(pid, workdirs=()) == store       # reopened by checking
        assert asked == []


# ── GAP 2: `store_fetch` — the gate, the shapes, the lost race ───────────────

class TestStoreFetch:
    FETCH = ('refs/heads/main', '0' * 40)

    def test_nothing_is_fetched_before_the_source_side_is_accepted(self, monkeypatch):
        started = _children(monkeypatch)
        monkeypatch.setattr(LocalNode, 'store_fetch_accepted', False)
        with pytest.raises(StoreError, match='until its source side is accepted'):
            LocalNode.store_fetch(ids.new_id('project'), '/tmp/source', self.FETCH[0],
                                  self.FETCH[1], local.seed_ref(ids.new_id('execution')),
                                  workdirs=())
        assert started == [] and not os.path.exists(paths.repos_dir())

    @pytest.mark.parametrize('accepted', [None, 1, 'True', 1.0])
    def test_only_the_literal_true_opens_the_gate(self, monkeypatch, accepted):
        monkeypatch.setattr(LocalNode, 'store_fetch_accepted', accepted)
        with pytest.raises(StoreError, match='until its source side is accepted'):
            LocalNode.store_fetch(ids.new_id('project'), '/tmp/source', self.FETCH[0],
                                  self.FETCH[1], local.seed_ref(ids.new_id('execution')),
                                  workdirs=())
        assert not os.path.exists(paths.repos_dir())

    @pytest.mark.parametrize('root,rev_name,expect,ref', [
        (str('/tmp/source'), 'heads/main', '0' * 40, 'refs/archeus/x'),      # no refs/
        (str('/tmp/source'), 'refs/heads/..', '0' * 40, 'refs/archeus/x'),   # dots
        (str('/tmp/source'), 'refs/heads/main', '0' * 40, 'refs/heads/x'),   # elsewhere
        (str('/tmp/source'), 'HEAD', '0' * 40, 'refs/tags/x'),               # not archeus's
        (str('/tmp/source'), 'refs/heads/main', 'abc', 'refs/archeus/x'),    # short id
        (str('/tmp/source'), 'refs/heads/main', 'A' * 40, 'refs/archeus/x'),  # capitals
        ('source', 'refs/heads/main', '0' * 40, 'refs/archeus/x'),           # relative
    ])
    def test_a_fetch_core_did_not_describe_is_refused_before_the_store_is_opened(
            self, monkeypatch, root, rev_name, expect, ref):
        monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
        with pytest.raises(StoreError, match='not a fetch Core may make'):
            LocalNode.store_fetch(ids.new_id('project'), root, rev_name, expect, ref,
                                  workdirs=())
        assert not os.path.exists(paths.repos_dir())

    def test_a_ref_the_store_cannot_hold_is_refused_before_anything_is_written(
            self, monkeypatch, tmp_path):
        monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
        with pytest.raises(StoreError, match='a store takes at most %d' % local.REF_MAX):
            LocalNode.store_fetch(ids.new_id('project'), str(tmp_path), 'refs/heads/main',
                                  '0' * 40, 'refs/archeus/' + 'x' * local.REF_MAX,
                                  workdirs=())
        assert not os.path.exists(paths.repos_dir())

    @needs_git
    def test_a_source_that_moved_between_resolve_and_fetch_loses_the_race(self, monkeypatch,
                                                                         tmp_path, real_git):
        root, base, tip, env = _repo(tmp_path)
        monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
        pid, eid = ids.new_id('project'), ids.new_id('execution')
        ref = local._import_ref(eid)
        # what a resolve sees is what the branch names at that moment: the tip the fixture
        # left it at, on either file system (`base` is the commit before it, which is what
        # the fetch below is told to expect and no longer finds: T-246 cause 3)
        assert LocalNode.store_resolve_base(str(root), 'refs/heads/main', workdirs=()) == tip
        # the branch moves after the resolve, written as a file: no hook of the source runs
        (root / '.git' / 'refs' / 'heads' / 'main').write_bytes(base.encode() + b'\n')
        with pytest.raises(StoreError, match='lost race'):
            LocalNode.store_fetch(pid, str(root), 'refs/heads/main', tip, ref, workdirs=())
        # the branch back where the resolve saw it: the same fetch with the truth it can
        # check, and the same publication twice over
        (root / '.git' / 'refs' / 'heads' / 'main').write_bytes(tip.encode() + b'\n')
        assert LocalNode.store_fetch(pid, str(root), 'refs/heads/main', tip, ref,
                                     workdirs=()) == tip
        assert LocalNode.store_fetch(pid, str(root), 'refs/heads/main', tip, ref,
                                     workdirs=()) == tip
        assert LocalNode.store_read(pid, ['rev-parse', '--verify', '-q', ref],
                                    workdirs=()).strip() == tip


# ── GAP 3: `import_workspace` — the seed map as the only authority ───────────

class TestImportPlan:
    SEED = [('100644', _blob(b'one\n'), 4, 'a.txt'),
            ('100755', _blob(b'#!/bin/sh\n'), 10, 'run.sh')]

    def _plan(self, tmp_path, rows, files=(), dirs=()):
        work = _tree(str(tmp_path / 'work'), files=files, dirs=dirs)
        return local._import_plan(work, _manifest(len(work), rows), local._Deadline('t'))

    def test_a_plain_edit_is_planned_from_the_seed_map_never_from_the_disk(self, tmp_path):
        files = [('a.txt', b'one\n'), ('run.sh', b'#!/bin/sh\n'), ('new.txt', b'new\n')]
        plan, counts = self._plan(tmp_path, self.SEED, files=files, dirs=['empty'])
        assert sorted((m, p) for m, p, _o, _s in plan) == [('100644', 'a.txt'),
                                                           ('100644', 'new.txt'),
                                                           ('100755', 'run.sh')]
        assert counts == {'deleted': 0, 'dropped_dirs': 1}   # an empty directory is dropped
        os.chmod(os.path.join(str(tmp_path / 'work'), 'new.txt'), 0o755)
        # a mode comes from the map: what the disk says about it is never asked
        assert [m for m, p, _o, _s in self._plan(tmp_path, self.SEED, files=files,
                                                 dirs=['empty'])[0] if p == 'new.txt'] \
            == ['100644']

    def test_a_file_that_is_no_longer_there_is_counted_as_deleted(self, tmp_path):
        assert self._plan(tmp_path, self.SEED, files=[('a.txt', b'one\n')])[1] == \
            {'deleted': 1, 'dropped_dirs': 0}

    @pytest.mark.parametrize('data', [b'bin.dae', b'bin.da', b''])
    def test_a_seeded_link_that_is_not_the_bytes_it_was_seeded_with_refuses(self, tmp_path,
                                                                           data):
        target = b'bin.dat'
        with pytest.raises(StoreError, match='the seeded link link was changed'):
            self._plan(tmp_path, [('120000', _blob(target), len(target), 'link')],
                       files=[('link', data)])

    def test_a_seeded_link_replaced_by_a_directory_refuses(self, tmp_path):
        target = b'bin.dat'
        with pytest.raises(StoreError, match='the seeded link link was changed'):
            self._plan(tmp_path, [('120000', _blob(target), len(target), 'link')],
                       dirs=['link'])

    @pytest.mark.parametrize('kind', ['filled', 'replaced'])
    def test_a_seeded_gitlink_that_was_used_refuses(self, tmp_path, kind):
        rows = [('160000', 'c' * 40, None, 'sub')]
        over = {'files': [('sub/x', b'x')]} if kind == 'filled' else \
            {'files': [('sub', b'not a repository')]}
        with pytest.raises(StoreError, match='the seeded gitlink sub was changed'):
            self._plan(tmp_path, rows, **over)

    def test_an_empty_gitlink_is_kept_by_its_id_without_being_read(self, tmp_path):
        plan, counts = self._plan(tmp_path, [('160000', 'c' * 40, None, 'sub')], dirs=['sub'])
        assert plan == [('160000', 'sub', 'c' * 40, None)] and counts['dropped_dirs'] == 0

    @pytest.mark.parametrize('rel', ['pkg/.git/config', 'pkg/git~1/x', 'pkg/sub/deep/.git'])
    def test_a_nested_repository_refuses(self, tmp_path, rel):
        with pytest.raises(StoreError, match='a path Core does not seed'):
            self._plan(tmp_path, [('100644', _blob(b'x'), 1, 'pkg/x')], files=[(rel, b'x')])

    @pytest.mark.parametrize('rel', [
        pytest.param('pkg/in:valid', id='colon', marks=nt_no_such_name),
        pytest.param('pkg/na?me', id='question', marks=nt_no_such_name),
        pytest.param('pkg/wei\\rd', id='backslash', marks=pytest.mark.skipif(
            sys.platform == 'win32',
            reason='a backslash is a separator on Windows and not a character of a name: '
                   'the path the row makes is an ordinary nested one there, which Core '
                   'seeds')),
        pytest.param('pkg/con.txt', id='device', marks=nt_no_such_name),
    ])
    def test_a_name_git_could_be_tricked_by_refuses(self, tmp_path, rel):
        with pytest.raises(StoreError, match='a path Core does not seed'):
            self._plan(tmp_path, [], files=[(rel, b'x')])

    def test_the_workspaces_own_root_git_is_skipped_by_name_and_kept(self, tmp_path):
        files = [('a.txt', b'one\n'), ('.git/HEAD', b'ref: refs/heads/whoever\n')]
        plan, counts = self._plan(tmp_path, [('100644', _blob(b'one\n'), 4, 'a.txt')],
                                  files=files)
        assert [p for _m, p, _o, _s in plan] == ['a.txt'] and counts['deleted'] == 0
        assert os.path.isfile(os.path.join(str(tmp_path / 'work'), '.git', 'HEAD'))

    @pytest.mark.skipif(sys.platform == 'win32',
                        reason='a case-insensitive file system answers the second name with '
                               'the first file: nothing is left on disk for the case fold to '
                               'catch, so the collision is genuinely not a behaviour there')
    def test_two_paths_one_case_insensitive_name_refuse(self, tmp_path):
        with pytest.raises(StoreError, match='two paths one case-insensitive name'):
            self._plan(tmp_path, [], files=[('a.txt', b'1'), ('A.txt', b'2')])

    def test_a_link_in_the_workspace_refuses_never_followed(self, tmp_path):
        if not _symlink_ok(tmp_path):
            pytest.skip('this user may not make a symlink')
        work = _tree(str(tmp_path / 'work'), files=[('a.txt', b'one\n')])
        os.symlink(str(tmp_path), os.path.join(work, 'out'))
        with pytest.raises(staging.StageError, match='alias'):
            local._import_plan(work, _manifest(len(work), []), local._Deadline('t'))

    def test_a_workspace_past_the_bound_of_entries_refuses(self, tmp_path, monkeypatch):
        monkeypatch.setattr(local, 'SEED_MAX_ENTRIES', 1)
        with pytest.raises(StoreError, match='a workspace past 1 entries'):
            self._plan(tmp_path, [], files=[('a', b'1'), ('b', b'2')])

    def test_a_workspace_walked_past_the_deadline_refuses(self, tmp_path, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(local, '_clock', lambda: now[0])
        plan = local._Deadline('t')
        now[0] += local.SEED_DEADLINE + 1
        with pytest.raises(StoreError, match='ran past its deadline'):
            local._import_plan(_tree(str(tmp_path / 'work'), files=[('a', b'1')]),
                               _manifest(20, []), plan)

    def test_fast_import_answering_anything_on_stdout_refuses(self):
        silent = local._Silent()
        with pytest.raises(StoreError, match='fast-import wrote to stdout'):
            silent.feed(b'error: something\n')
        assert silent.end() is None and silent.abort() is None   # neither says anything else

    @needs_git
    def test_a_clean_import_is_read_back_and_written_only_once(self, monkeypatch, tmp_path,
                                                               real_git):
        root, _base, tip, env = _repo(tmp_path)
        monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
        pid, eid = ids.new_id('project'), ids.new_id('execution')
        assert LocalNode.store_fetch(pid, str(root), 'refs/heads/main', tip,
                                     local.seed_ref(eid), workdirs=()) == tip
        _tree(paths.ExecPaths(eid).work, files=[('a.txt', b'two\n'), ('new.txt', b'new\n')],
              dirs=['emptyd'])
        got = LocalNode.import_workspace(pid, eid, tip, workdirs=())
        assert len(got['revision']) == 40 and len(got['tree']) == 40
        assert got['files_changed'] == ['A new.txt']              # the seed itself unchanged
        assert got['deleted'] == 0 and got['dropped_dirs'] == 1
        assert LocalNode.store_read(pid, ['rev-parse', '--verify', '-q',
                                          local._import_ref(eid)], workdirs=()).strip() \
            == got['revision']
        with pytest.raises(StoreError, match='written once'):     # the ref is a once-only act
            LocalNode.import_workspace(pid, eid, tip, workdirs=())
        # a dropped seed file and an edited one are reported against the map, not the disk
        other = ids.new_id('execution')
        _tree(paths.ExecPaths(other).work, files=[('new.txt', b'changed\n')])
        again = LocalNode.import_workspace(pid, other, tip, workdirs=())
        assert again['files_changed'] == ['A new.txt', 'D a.txt'] and again['deleted'] == 1
        assert tip in _git(root, 'log', '--format=%H', env=env)


# ── GAP 4: `seed_workspace` and the checks the rename has to pass ────────────

class TestSeed:
    def test_a_target_that_already_exists_refuses_before_anything_of_cores_is_made(
            self, monkeypatch, tmp_path):
        eid, rev, branch = ids.new_id('execution'), 'a' * 40, 'archeus/mission.key'
        for target in (paths.ExecPaths(eid).work, paths.seed_staging(eid)):
            os.makedirs(target)
            open(os.path.join(target, 'mine'), 'wb').close()
            before = _snapshot(target)
            with pytest.raises(StoreError, match='already exists'):
                LocalNode.seed_workspace(ids.new_id('project'), eid, rev, branch, workdirs=())
            assert _snapshot(target) == before                    # never copied over nor removed
            assert not os.path.exists(os.path.join(paths.repos_dir(), '.pin'))
            shutil.rmtree(target)

    @pytest.mark.parametrize('rev,branch', [
        ('a' * 39, 'archeus/m.k'), ('aaaa', 'archeus/m.k'), ('A' * 40, 'archeus/m.k'),
        ('a' * 40, 'main'), ('a' * 40, 'archeus/..'), ('a' * 40, 'archeus/m.lock'),
        ('a' * 40, 'archeus/m.'), ('a' * 40, 'archeus/sub/m'), ('a' * 40, 'archeus/'),
    ])
    def test_a_seed_core_was_not_told_to_build_is_refused(self, monkeypatch, rev, branch):
        with pytest.raises(StoreError, match='not a seed Core builds'):
            LocalNode.seed_workspace(ids.new_id('project'), ids.new_id('execution'), rev,
                                     branch, workdirs=())
        assert not os.path.exists(os.path.join(paths.repos_dir(), '.pin'))

    def test_a_second_id_for_the_same_seed_ref_is_refused(self):
        with pytest.raises(StoreError, match='not an execution id'):
            local.seed_ref('exe_' + 'x' * 12)
        with pytest.raises(ValueError, match='execution'):
            paths.ExecPaths('nope')

    def _seed_git(self, dot, branch, rev):
        """A seed's `.git` exactly as Core's own steps leave it."""
        os.makedirs(os.path.join(dot, 'objects', 'info'))
        os.makedirs(os.path.join(dot, 'refs', 'heads', 'archeus'))
        for name, data in (('HEAD', b'ref: refs/heads/%s\n' % branch.encode()),
                           ('config', local.SEED_CONFIG), ('shallow', rev.encode() + b'\n'),
                           ('index', b'INDEX')):
            with open(os.path.join(dot, name), 'wb') as f:
                f.write(data)
        with open(os.path.join(dot, 'refs', 'heads', 'archeus', branch.split('/', 1)[-1]),
                  'wb') as f:
            f.write(rev.encode() + b'\n')
        return dot

    def test_the_seeds_git_is_let_through_exactly_as_core_made_it(self, tmp_path):
        dot = _tree(str(tmp_path / 'seed' / '.git'))
        self._seed_git(dot, 'archeus/m.k', 'a' * 40)
        assert local._seed_meta(dot, 'refs/heads/archeus/m.k', 'a' * 40,
                                local._Deadline('t')) is None

    @pytest.mark.parametrize('what', ['extra', 'missing', 'head', 'config', 'shallow',
                                      'ref-moved', 'ref-extra', 'no-ref', 'object-index'])
    def test_a_seeds_git_that_is_not_what_core_wrote_refuses(self, tmp_path, what):
        rev, branch = 'a' * 40, 'archeus/m.k'
        dot = _tree(str(tmp_path / 'seed' / '.git'))
        self._seed_git(dot, branch, rev)
        inside = lambda *p: os.path.join(dot, *p)                  # noqa: E731
        if what == 'extra':
            open(inside('COMMIT_EDITMSG'), 'wb').close()
        elif what == 'missing':
            os.remove(inside('index'))
        elif what == 'head':
            with open(inside('HEAD'), 'wb') as f:
                f.write(b'ref: refs/heads/elsewhere\n')
        elif what == 'config':
            with open(inside('config'), 'ab') as f:
                f.write(b'[remote "origin"]\n\turl = http://127.0.0.1:9/\n')
        elif what == 'shallow':
            with open(inside('shallow'), 'wb') as f:
                f.write(b'b' * 40 + b'\n')
        elif what == 'ref-moved':
            with open(inside('refs', 'heads', 'archeus', 'm.k'), 'wb') as f:
                f.write(b'b' * 40 + b'\n')
        elif what == 'ref-extra':
            with open(inside('refs', 'heads', 'other'), 'wb') as f:
                f.write(rev.encode() + b'\n')
        elif what == 'no-ref':
            os.remove(inside('refs', 'heads', 'archeus', 'm.k'))
        else:
            open(inside('objects', 'info', 'commit-graph'), 'wb').close()
        wants = {'extra': 'a seed .git holding', 'missing': 'a seed .git holding',
                 'head': 'a seed .git/HEAD', 'config': 'a seed .git/config',
                 'shallow': 'a seed .git/shallow', 'ref-moved': 'refs or object stores',
                 'ref-extra': 'refs or object stores', 'no-ref': 'refs or object stores',
                 'object-index': 'refs or object stores'}
        with pytest.raises(StoreError, match=wants[what]):
            local._seed_meta(dot, 'refs/heads/' + branch, rev, local._Deadline('t'))

    def test_the_working_tree_must_be_exactly_the_trees_map(self, tmp_path):
        rows = [('100644', _blob(b'one\n'), 4, 'a.txt'), ('100755', _blob(b'sh\n'), 3,
                                                             'bin/sh'),
                ('160000', 'c' * 40, None, 'sub')]
        work = _tree(str(tmp_path / 'work'), files=[('a.txt', b'one\n'), ('bin/sh', b'sh\n')],
                     dirs=['sub'])
        tree = _manifest(len(work), rows)
        deadline = local._Deadline('t')
        assert local._seed_walk(work, deadline) == tree.expected()   # the positive control
        with open(os.path.join(work, 'a.txt'), 'wb') as f:
            f.write(b'two\n')
        assert local._seed_walk(work, deadline) != tree.expected()

    def test_a_file_replaced_under_the_walk_refuses(self, tmp_path, monkeypatch):
        work = _tree(str(tmp_path / 'work'), files=[('a.txt', b'one\n')])
        path, real = os.path.join(work, 'a.txt'), os.fstat
        assert local._blob_id(path, 4, local._Deadline('t'), seen=os.lstat(path)) \
            == _blob(b'one\n')                                      # a still file answers

        def moved(fd):                                              # swapped after the look
            st = real(fd)
            return SimpleNamespace(st_mode=st.st_mode, st_ino=st.st_ino + 1,
                                   st_dev=st.st_dev, st_size=st.st_size, st_nlink=st.st_nlink,
                                   st_atime=st.st_atime, st_mtime=st.st_mtime,
                                   st_ctime=st.st_ctime, st_uid=st.st_uid, st_gid=st.st_gid)
        monkeypatch.setattr(os, 'fstat', moved)
        with pytest.raises(StoreError, match='changed after the walk'):
            local._blob_id(path, 4, local._Deadline('t'), seen=os.lstat(path))

    def test_the_clock_stops_every_step_of_a_seed_including_the_last(self, monkeypatch,
                                                                     tmp_path):
        now = [1000.0]
        monkeypatch.setattr(local, '_clock', lambda: now[0])
        deadline = local._Deadline('seed')
        step = local._Deadline('seed')            # a second step, made while there is time
        assert 0 < deadline.left() <= local.SEED_DEADLINE
        now[0] += local.SEED_DEADLINE + 1
        with pytest.raises(StoreError, match='ran past its deadline'):
            deadline.left()
        top = str(tmp_path / 'home')                    # a tree Core has not made yet
        with pytest.raises(StoreError, match='ran past its deadline'):
            local._made(top, os.path.join(top, 'a', 'b'), step)
        assert not os.path.exists(os.path.join(top, 'a'))         # nothing was made for it

    @needs_git
    def test_a_seed_is_built_in_staging_and_renamed_in_once(self, monkeypatch, tmp_path,
                                                            real_git):
        root, _base, tip, _env = _repo(tmp_path)
        monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
        pid, eid = ids.new_id('project'), ids.new_id('execution')
        branch = 'archeus/mission.key'
        assert LocalNode.store_fetch(pid, str(root), 'refs/heads/main', tip,
                                     local.seed_ref(eid), workdirs=()) == tip
        work = LocalNode.seed_workspace(pid, eid, tip, branch, workdirs=())
        assert work == paths.ExecPaths(eid).work
        assert not os.path.exists(paths.seed_staging(eid))        # renamed in, never copied
        with open(os.path.join(work, 'a.txt'), 'rb') as f:
            assert f.read() == b'two\n'
        assert sorted(os.listdir(os.path.join(work, '.git'))) == sorted(local._SEED_META)
        assert os.path.isdir(os.path.join(work, '.git', 'objects', 'info'))
        with pytest.raises(StoreError, match='already exists'):   # a workspace is never reused
            LocalNode.seed_workspace(pid, eid, tip, branch, workdirs=())


# ── GAP 5: `_stream`, the byte core every store read goes through ────────────

class Sink:
    """What `_stream` hands its stdout: the chunks as they arrive, then one of
    `end`/`abort` — never both, and never after a refusal of its own."""

    def __init__(self, fail_after=None):
        self.chunks, self.state, self.fail_after = [], None, fail_after

    def feed(self, chunk):
        if not chunk:
            raise AssertionError('an empty chunk is not a read')
        if len(chunk) > local._CHUNK:
            raise AssertionError('a chunk past the read size: %d' % len(chunk))
        self.chunks.append(chunk)
        if self.fail_after is not None and len(self.chunks) == self.fail_after:
            raise StoreError('the sink said no')

    def end(self):
        assert self.state is None, 'the sink answered twice'
        self.state = 'end'

    def abort(self):
        assert self.state is None, 'the sink answered twice'
        self.state = 'abort'

    @property
    def data(self):
        return b''.join(self.chunks)


def _child(code):
    """One of Core's own children: this interpreter, an absolute argv, no shell."""
    return [sys.executable, '-c', code]


ECHO = ('import sys;d=sys.stdin.buffer.read();sys.stdout.buffer.write(d);'
        'sys.stdout.flush();sys.stderr.write("noise");sys.stderr.flush()')


class TestByteCore:
    def _stream(self, monkeypatch, code, sink, stdin=None, timeout=30, cwd=None):
        return local._stream(_child(code), str(cwd or os.getcwd()), _child_env(os.environ),
                             stdin, sink, timeout)

    def test_stdout_goes_to_the_sink_untouched_and_the_child_is_reaped(self, monkeypatch,
                                                                      tmp_path):
        started, made = _children(monkeypatch), _threads(monkeypatch)
        sink = Sink()
        payload = b'\xff' * (3 * local._CHUNK + 7)         # undecodable, longer than a chunk
        self._stream(monkeypatch, ECHO, sink, stdin=payload, cwd=tmp_path)
        assert sink.data == payload and sink.state == 'end'  # never decoded, never truncated
        assert [p.returncode for p in started] == [0]
        # the two threads the byte core started are the ones that must be gone: which
        # threads are alive in the process is not a comparison Windows answers the same
        # way, where the runner keeps worker threads Core never started (cause 6)
        assert [t.__name__ for t, _h in made] == ['drain', 'feed']
        assert [h.name for t, h in made if h.is_alive()] == []   # no feeder or drainer survived

    def test_a_sink_that_refuses_mid_stream_kills_the_child_and_is_aborted(self, monkeypatch,
                                                                           tmp_path):
        started = _children(monkeypatch)
        sink = Sink(fail_after=1)
        with pytest.raises(StoreError, match='the sink said no'):
            self._stream(monkeypatch, 'import sys;sys.stdout.buffer.write(b"x"*200000)', sink,
                         cwd=tmp_path)
        assert sink.state == 'abort'
        assert len(started) == 1 and started[0].returncode is not None   # reaped, not orphaned
        if os.name != 'nt':
            assert started[0].returncode < 0                             # killed, not exited

    def test_a_deadline_that_fires_is_a_refusal_not_a_short_read(self, monkeypatch, tmp_path):
        started = _children(monkeypatch)
        sink = Sink()
        with pytest.raises(StoreError, match='ran past its deadline'):
            self._stream(monkeypatch, 'import time;time.sleep(30)', sink, timeout=1,
                         cwd=tmp_path)
        assert sink.state == 'abort' and sink.chunks == []
        assert len(started) == 1 and started[0].returncode is not None

    def test_a_feed_that_breaks_is_the_failure_and_nothing_else_says_so(self, monkeypatch,
                                                                       tmp_path):
        started = _children(monkeypatch)
        sink = Sink()

        def broken():
            yield b'first chunk, the child is reading it'
            raise RuntimeError('the feed broke')
        with pytest.raises(RuntimeError, match='the feed broke'):
            self._stream(monkeypatch, 'import sys;sys.stdin.buffer.read()', sink,
                         stdin=broken(), cwd=tmp_path)
        assert sink.state == 'abort' and sink.chunks == []      # the child never answered
        assert len(started) == 1 and started[0].returncode is not None

    def test_a_child_that_fails_names_its_own_stderr(self, monkeypatch, tmp_path):
        _children(monkeypatch)
        with pytest.raises(StoreError, match='git said something'):
            self._stream(monkeypatch, 'import sys;sys.stderr.write("git said something");'
                                       'sys.exit(3)', Sink(), cwd=tmp_path)

    def test_stderr_past_its_cap_is_kept_only_to_its_cap(self, monkeypatch, tmp_path):
        _children(monkeypatch)
        with pytest.raises(StoreError, match='git failed') as got:
            self._stream(monkeypatch, 'import sys;sys.stderr.write("e"*200000);sys.exit(1)',
                         Sink(), cwd=tmp_path)
        assert len(str(got.value)) <= local._STDERR_KEEP + 60

    def test_a_silent_child_still_gets_an_eof_and_a_clean_end(self, monkeypatch, tmp_path):
        started = _children(monkeypatch)
        sink = Sink()
        self._stream(monkeypatch, 'import sys;sys.stdin.buffer.read()', sink, stdin=b'',
                     cwd=tmp_path)
        assert sink.state == 'end' and sink.data == b'' and [p.returncode for p in started] == [0]


# ── GAP 6: `_source`, `_store_pin`, `_pin_files`, `_outside_executions` ──────

class TestHostileSource:
    def _src(self, tmp_path, files=(), dirs=(), name='src'):
        """A source repository as a directory with a `.git` in it: only what
        `_source` reads, none of it started."""
        root = str(tmp_path / name)
        os.makedirs(os.path.join(root, '.git', 'objects'))
        os.makedirs(os.path.join(root, '.git', 'refs'))
        for rel, data in (('HEAD', b'ref: refs/heads/main\n'), ('config', b'[core]\n')):
            with open(os.path.join(root, '.git', rel), 'wb') as f:
                f.write(data)
        return _tree(root, files=files, dirs=dirs)

    def test_a_plain_source_is_accepted_before_anything_is_started(self, monkeypatch,
                                                                  tmp_path):
        started = _children(monkeypatch)
        root = self._src(tmp_path)
        assert local._source(root, ()) == os.path.join(root, '.git')
        assert started == []

    def test_a_relative_root_is_refused(self, tmp_path):
        with pytest.raises(StoreError, match='not a repository Core may read'):
            local._source('src', ())

    def test_a_source_inside_an_execution_area_is_refused(self, tmp_path):
        root = self._src(tmp_path)
        with pytest.raises(StoreError, match='inside an execution area'):
            local._source(root, workdirs=[str(tmp_path)])

    def test_a_sibling_dot_git_upload_pack_could_settle_on_is_refused(self, monkeypatch,
                                                                      tmp_path):
        started = _children(monkeypatch)
        root = self._src(tmp_path)
        _tree(str(tmp_path / 'src.git'), files=[('HEAD', b'ref: refs/heads/other\n')])
        with pytest.raises(StoreError, match='a source with a sibling src.git'):
            local._source(root, ())
        assert started == []

    @pytest.mark.parametrize('word', [w.decode() for w in local._SOURCE_CONFIG_REFUSED])
    def test_a_config_saying_any_refused_word_is_refused_without_reading_it_again(
            self, monkeypatch, tmp_path, word):
        started = _children(monkeypatch)
        root = self._src(tmp_path, files=[('.git/config', ('[core]\n\tsay = %s\n' % word)
                                           .encode().upper())])
        with pytest.raises(StoreError, match='which Core does not follow'):
            local._source(root, ())
        assert started == []

    def test_a_reftable_source_is_refused(self, monkeypatch, tmp_path):
        root = self._src(tmp_path, dirs=['.git/reftable'])
        with pytest.raises(StoreError, match='a reftable source'):
            local._source(root, ())

    @pytest.mark.parametrize('how', ['packed', 'loose'])
    def test_replace_refs_are_refused(self, monkeypatch, tmp_path, how):
        files = [('.git/packed-refs', b'# pack-refs\n0' * 20 + b' refs/replace/' + b'0' * 40)] \
            if how == 'packed' else []
        dirs = [] if how == 'packed' else ['.git/refs/replace']
        root = self._src(tmp_path, files=files, dirs=dirs)
        with pytest.raises(StoreError, match='a source with replace refs'):
            local._source(root, ())

    def test_an_alternates_chain_past_what_git_follows_is_refused(self, monkeypatch, tmp_path):
        root = self._src(tmp_path)
        objects = os.path.join(root, '.git', 'objects')
        chain = objects
        for step in range(6):
            os.makedirs(os.path.join(chain, 'info'))
            nxt = str(tmp_path / ('alt%d' % step))
            _tree(nxt)                                   # Git follows only real directories
            with open(os.path.join(chain, 'info', 'alternates'), 'wb') as f:
                f.write((nxt + '\n').encode())
            chain = nxt
        with pytest.raises(StoreError, match='alternates nested too deep'):
            local._source(root, ())

    def test_a_promisor_pack_is_refused(self, monkeypatch, tmp_path):
        root = self._src(tmp_path, files=[('.git/objects/pack/p-.promisor', b'')])
        with pytest.raises(StoreError, match='.promisor'):
            local._source(root, ())

    @pytest.mark.parametrize('raw,want', [
        (b'gitdir:/no-space\n', 'a .git file Core does not read'),
        (b'gitdir: ', 'naming a path Core does not resolve'),
        (b'gitdir: ok\nmore\n', 'naming a path Core does not resolve'),
        (b'gitdir: \xff\xfe\n', 'not UTF-8'),
        # the oversized row names itself rather than carry 64 KiB of `x` into the test id,
        # the tmp folder named from it and the environment value pytest puts the running
        # test in: a Windows file name and an environment value both hold less than that,
        # so the row made two setup errors there (T-246 cause 1 and the ids note)
        pytest.param('past-the-cap', 'a .git file Core does not read', id='oversized'),
    ], ids=['no-space', 'empty', 'second-line', 'not-utf8', 'oversized'])
    def test_a_git_file_git_would_not_read_the_same_way_is_refused(self, monkeypatch, tmp_path,
                                                                   raw, want):
        started = _children(monkeypatch)
        root = str(tmp_path / 'src')
        if raw == 'past-the-cap':
            # past the cap by one byte, with the cap brought down for this row alone: the
            # same `len(data) > _GITFILE_MAX` branch, on a fixture that stays below the
            # Windows bound cause 1 names instead of a value nothing can carry there
            monkeypatch.setattr(local, '_GITFILE_MAX', 4096)
            raw = b'gitdir: ' + b'x' * (local._GITFILE_MAX + 1)
        assert len(raw) <= ENV_MAX                     # what the row is kept under
        _tree(root, files=[('.git', raw)])
        with pytest.raises(StoreError, match=want):
            local._source(root, ())
        assert started == []

    def test_an_alias_in_the_object_store_is_refused_never_followed(self, monkeypatch, tmp_path):
        if not _symlink_ok(tmp_path):
            pytest.skip('this user may not make a symlink')
        started = _children(monkeypatch)
        root = self._src(tmp_path)
        os.symlink(str(tmp_path), os.path.join(root, '.git', 'objects', 'borrowed'))
        with pytest.raises(staging.StageError, match='alias'):
            local._source(root, ())
        assert started == []

    def test_the_pin_is_exactly_the_pinned_argv_env_and_cwd(self, monkeypatch, tmp_path):
        _pinned(monkeypatch)
        d, exe = str(tmp_path / 'store'), os.path.abspath(sys.executable)
        argv, env, cwd = local._store_pin('trusted', d)
        assert argv[0] == exe and cwd == d
        assert argv[1:4] == ['--git-dir', d, '--no-replace-objects']
        assert argv[argv.index('--attr-source') + 1] == EMPTY_TREE
        six = [argv[i + 1] for i, a in enumerate(argv) if a == '-c']
        assert six == ['core.hooksPath=' + os.path.join(paths.repos_dir(), '.pin', 'empty'),
                       'core.fsmonitor=false',
                       'core.attributesFile=' + os.path.join(paths.repos_dir(), '.pin',
                                                             'empty.cfg'),
                       'submodule.recurse=false', 'gc.auto=0', 'maintenance.auto=false']
        assert env['GIT_CONFIG_GLOBAL'] == env['GIT_CONFIG_SYSTEM'] \
            == os.path.join(paths.repos_dir(), '.pin', 'empty.cfg')
        assert env['GIT_CONFIG_NOSYSTEM'] == '1' and env['HOME'] == env['XDG_CONFIG_HOME'] \
            == os.path.join(paths.repos_dir(), '.pin', 'empty')
        assert env['GIT_ALLOW_PROTOCOL'] == 'file' and env['GIT_NO_LAZY_FETCH'] == '1' \
            and env['GIT_PROTOCOL_FROM_USER'] == '0' and env['GIT_TERMINAL_PROMPT'] == '0'
        assert env['PATH'] == os.path.dirname(exe)
        # of what a child may inherit: ten pinned names and the platform's own four, nothing
        pinned = {'PATH', 'HOME', 'XDG_CONFIG_HOME', 'GIT_CONFIG_NOSYSTEM',
                  'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_SYSTEM', 'GIT_TERMINAL_PROMPT',
                  'GIT_ALLOW_PROTOCOL', 'GIT_PROTOCOL_FROM_USER', 'GIT_NO_LAZY_FETCH'}
        assert set(env) == pinned | (set(os.environ) & {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'})
        assert not [k for k in env if k.startswith('GIT_') and k not in pinned]
        assert not [k for k in env if k.startswith(('PYTHON', 'PYTEST', 'ARCHEUS', 'CLAUDE'))]

    @pytest.mark.parametrize('mode,no_repo', [('version', True), ('init', True),
                                              ('seed', False), ('base', False)])
    def test_each_mode_gets_the_argv_its_own_needs(self, monkeypatch, tmp_path, mode, no_repo):
        _pinned(monkeypatch)
        d = str(tmp_path / 'store')
        argv, env, cwd = local._store_pin(mode, None if no_repo else d)
        assert ('--git-dir' in argv) == (not no_repo) and ('--attr-source' in argv) is False
        assert ('-c' in argv and 'core.logAllRefUpdates=false' in argv) == (mode == 'seed')
        if no_repo:                                   # no repository may be discovered
            assert env['GIT_CEILING_DIRECTORIES'] == paths.repos_dir()
            assert cwd == os.path.join(paths.repos_dir(), '.pin', 'empty') \
                if mode == 'version' else paths.repos_dir()
        else:
            assert cwd == d

    def test_the_pin_area_is_made_by_core_alone_and_refused_once_anything_is_in_it(
            self, monkeypatch, tmp_path):
        _pinned(monkeypatch)
        pin, exe = os.path.join(paths.repos_dir(), '.pin'), os.path.abspath(sys.executable)
        assert local._pin_files(()) == pin
        assert local._pin_files(()) == pin                            # twice says the same
        assert os.path.isfile(os.path.join(pin, 'empty.cfg'))
        assert os.path.getsize(os.path.join(pin, 'empty.cfg')) == 0
        assert os.listdir(os.path.join(pin, 'empty')) == []
        store = _tree(str(tmp_path / 'store'), files=[('config', b'')])
        assert local._pin_record(store, VERSION) == {'git': exe, 'version': VERSION,
                                                    'empty_tree': EMPTY_TREE,
                                                    'config_sha256':
                                                        hashlib.sha256(b'').hexdigest()}
        with open(os.path.join(pin, 'empty.cfg'), 'wb') as f:          # Git's config is now
            f.write(b'[user]\n\tname = somebody\n')                    # somebody else's
        with pytest.raises(StoreError, match='a pin file is not empty'):
            local._pin_files(())
        with open(os.path.join(pin, 'empty.cfg'), 'wb') as f:
            f.write(b'')
        open(os.path.join(pin, 'empty', 'one-of-yours'), 'wb').close()  # the hooks folder too
        with pytest.raises(StoreError, match='a pin file is not empty'):
            local._pin_files(())

    def test_workdirs_is_a_collection_of_paths_never_one_path(self, tmp_path):
        for wrong in (str(tmp_path), str(tmp_path).encode()):
            with pytest.raises(StoreError, match='collection of paths'):
                local._outside_executions([str(tmp_path / 'nowhere')], wrong)
        assert local._outside_executions([str(tmp_path / 'nowhere')], []) is None
        with pytest.raises(StoreError, match='inside an execution area'):
            local._outside_executions([paths.run_dir()], [])


# ── GAP 7: `run_check` and its confined twin ─────────────────────────────────

class FakeConfinement:
    """`Isolation.run_confined` without a principal, a Job or a process. It keeps the
    order that matters: the caller's fresh-only `prepare` runs where the real one does —
    after admission, before anything is launched — and whatever it raises is a verdict
    of its own, recorded, with nothing started."""

    def __init__(self):
        self.calls, self.raised = [], []

    def run_confined(self, request, argv, *, env, timeout, out_path, stdin_path, record,
                     keep, prepare=None):
        built, error = None, None
        if prepare is not None:
            try:
                built = prepare()
            except (OSError, ValueError) as err:
                # the exception is kept as well as its wording: what a test names is the
                # refusal itself (type, errno), never how the OS happened to word it
                self.raised.append(err)
                error = 'prepare_failed: %s' % err
        result = {'exit_code': None, 'duration_ms': 0, 'error': error, 'output': b'',
                  'output_bytes': 0, 'truncated': False,
                  'confinement': {'isolated': True}}
        self.calls.append(SimpleNamespace(request=request, argv=argv, env=env,
                                          timeout=timeout, out_path=out_path,
                                          stdin_path=stdin_path, record=record, keep=keep,
                                          built=built, result=result))
        record(result)                                  # the verdict is written, then…
        return result


class TestChecks:
    def test_a_known_command_reports_its_exit_code_its_tail_and_its_length(self, tmp_path):
        out = str(tmp_path / 'logs' / 'check.log')            # the parent does not exist yet
        r = LocalNode.run_check(str(tmp_path), _child(
            'import sys;sys.stdout.buffer.write(b"0123456789" * 100)'), timeout=60,
            out_path=out, keep=64)
        assert r['exit_code'] == 0 and r['error'] is None
        assert r['output'] == (b'0123456789' * 100)[-64:]     # the tail, and only the tail
        assert r['output_bytes'] == 1000 and r['truncated'] is True
        assert open(out, 'rb').read() == b'0123456789' * 100  # the file holds everything
        assert isinstance(r['duration_ms'], int) and r['duration_ms'] >= 0

    def test_a_command_that_fails_reports_a_number_not_an_error(self, tmp_path):
        r = LocalNode.run_check(str(tmp_path), _child('import sys;sys.exit(4)'), timeout=60,
                                out_path=str(tmp_path / 'o'), keep=100)
        assert r['exit_code'] == 4 and r['error'] is None and r['truncated'] is False

    def test_a_command_that_cannot_run_is_a_dict_and_never_a_raise(self, tmp_path):
        r = LocalNode.run_check(str(tmp_path), ['definitely-not-a-program-anywhere'],
                                timeout=60, out_path=str(tmp_path / 'o'), keep=100)
        assert r['error'].startswith('could not run:') and r['exit_code'] is None
        assert r['output'] == b'' and r['output_bytes'] == 0 and r['truncated'] is False

    def test_a_hanging_command_is_tree_killed_and_named_as_a_fault(self, monkeypatch, tmp_path):
        started, killed = _children(monkeypatch), []
        real_kill = local.proc.kill_tree

        def record(child):
            killed.append(child.pid)
            return real_kill(child)
        monkeypatch.setattr(local.proc, 'kill_tree', record)
        t0 = time.monotonic()
        r = LocalNode.run_check(str(tmp_path), _child('import time;time.sleep(60)'), timeout=1,
                                out_path=str(tmp_path / 'o'), keep=100)
        assert r['error'] == 'timed out after 1s' and r['exit_code'] is None
        assert killed == [started[0].pid] and time.monotonic() - t0 < 20
        assert started[0].poll() is not None                  # nothing of it is left running

    def test_nothing_of_the_test_running_core_reaches_the_command_it_runs(self, monkeypatch,
                                                                         tmp_path):
        monkeypatch.setenv('PYTEST_CURRENT_TEST', 'a test that runs Core')
        monkeypatch.setenv('PYTEST_XDIST_WORKER', 'gw0')
        monkeypatch.setenv('ARCHEUS_EXECUTION_ID', 'exe_01M669GMZAZ7WMNJPM3PCK4QDE')
        monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path / 'core-state'))
        monkeypatch.setenv('ARCHEUS_LOCAL_TOKEN', 'a secret of Core')
        r = LocalNode.run_check(str(tmp_path), _child(
            'import os,sys;sys.stdout.write("\\n".join(sorted(os.environ)))'), timeout=60,
            out_path=str(tmp_path / 'o'), keep=100000)
        seen = r['output'].decode().splitlines()
        assert r['exit_code'] == 0
        assert not [k for k in seen if k.startswith(('PYTEST_', 'ARCHEUS_'))]
        assert 'ARCHEUS_HOME' not in seen and 'ARCHEUS_LOCAL_TOKEN' not in seen
        assert {'PYTHONDONTWRITEBYTECODE', 'GIT_TERMINAL_PROMPT'} <= set(seen)

    def test_the_confined_check_builds_one_attempt_request_and_launches_nothing(
            self, monkeypatch, tmp_path):
        from archeus.node import isolation as isolation_mod
        started = _children(monkeypatch)
        fake, recorded = FakeConfinement(), []
        node = LocalNode(isolation=fake)
        vid, attempt = ids.new_id('verification'), 3
        toolchain = [str(tmp_path / 'tool'), str(tmp_path / 'lib')]
        argv = _child('raise SystemExit(0)')
        got = node.run_confined_check(vid, attempt, argv, toolchain=toolchain, timeout=7,
                                      record=recorded.append, project_id=ids.new_id('project'),
                                      revision='not a revision', workdirs=(), keep=1234)
        assert len(fake.calls) == len(recorded) == 1 and recorded[0] is got
        assert got['error'].startswith('prepare_failed:') and 'not a revision Core exports' \
            in got['error']
        call = fake.calls[0]
        p = paths.VerifyPaths(vid, attempt)
        assert call.request.execution_id == isolation_mod.Principal('verify', vid,
                                                                    attempt).key
        assert call.request.kind == 'verify' and call.request.workspace == p.checkout
        assert call.argv == argv and call.env is None and call.timeout == 7 and call.keep == 1234
        assert call.out_path == p.out and call.stdin_path == os.path.join(p.dir, 'stdin')
        rows = {g.row: (os.path.normpath(g.path), g.access) for g in call.request.grants}
        assert rows['checkout'] == (os.path.normpath(p.checkout), 'rw')
        assert rows['scratch'] == (os.path.normpath(os.path.dirname(p.checkout)), 'rw')
        assert [g.access for g in call.request.grants if g.row == 'toolchain'] == ['rx', 'rx']
        assert [g.path for g in call.request.grants if g.row == 'toolchain'] == toolchain
        # Core's own state is named as ungranted, and never reached through a grant
        run = os.path.normcase(paths.run_dir())
        assert call.request.core_state == paths.run_dir()
        assert not [g for g in call.request.grants
                    if os.path.normcase(g.path) == run              # no grant on run/ itself,
                    or os.path.normcase(run).startswith(            # nor on anything holding it
                        os.path.normcase(g.path) + os.sep)]
        assert started == []                                   # a tree Core cannot export
        assert LocalNode.disarmed() is False                   # starts nothing at all

    def test_an_attempts_own_files_are_made_once_and_never_written_over(self, monkeypatch,
                                                                       tmp_path):
        fake, recorded = FakeConfinement(), []
        node = LocalNode(isolation=fake)
        vid, attempt = ids.new_id('verification'), 1
        export = []
        monkeypatch.setattr(local, '_export_tree',
                            lambda pid, rev, top, workdirs, dl: export.append((pid, rev, top)))
        monkeypatch.setattr(local.base, '_verifier_env',
                            lambda toolchain, scratch: {'the': 'environment', 'of': scratch})
        first = node.run_confined_check(vid, attempt, _child('pass'),
                                        toolchain=[str(tmp_path)], timeout=5,
                                        record=recorded.append, project_id='prj_x',
                                        revision='a' * 40, workdirs=())
        assert first['error'] is None and first['confinement'] == {'isolated': True}
        assert export == [('prj_x', 'a' * 40, paths.VerifyPaths(vid, attempt).checkout)]
        p = paths.VerifyPaths(vid, attempt)
        assert fake.calls[0].built['of'] == os.path.dirname(p.checkout)
        assert sorted(os.listdir(p.dir)) == ['out.log', 'own', 'stdin']
        assert sorted(os.listdir(os.path.join(p.dir, 'own'))) == ['checkout', 'config', 'home',
                                                                  'tmp']
        assert os.path.getsize(p.out) == 0 and os.path.getsize(os.path.join(p.dir, 'stdin')) == 0
        before = _snapshot(p.dir)                             # what the first attempt left
        second = node.run_confined_check(vid, attempt, _child('pass'),
                                         toolchain=[str(tmp_path)], timeout=5,
                                         record=recorded.append, project_id='prj_x',
                                         revision='a' * 40, workdirs=())
        # the export was never reached a second time: the attempt's own files came first
        assert len(export) == 1 and second['error'].startswith('prepare_failed:')
        # the OS's own 'already there', named by type and errno: nt words the very same
        # refusal (WinError 183, which CPython raises as FileExistsError/EEXIST) in the
        # user's language, so the wording cause 7 quotes is never asserted on
        assert len(fake.raised) == 1 and isinstance(fake.raised[0], FileExistsError)
        assert fake.raised[0].errno == errno.EEXIST           # refused, not written over
        assert _snapshot(p.dir) == before                     # and nothing of it was changed


# ── GAP 8: `estop_without_core` — the sentinel first, the pid rule kept ──────

class TestEStop:
    def _lines(self, *lines):
        os.makedirs(paths.run_dir(), exist_ok=True)
        with open(paths.processes_registry(), 'w', encoding='utf-8') as f:
            for x in lines:
                f.write(json.dumps(x, sort_keys=True) + '\n')

    def test_the_sentinel_is_wedged_in_before_any_kill_and_the_pid_rule_is_kept(
            self, monkeypatch):
        mine, other = os.getpid(), os.getpid() + 1               # one pid, two identities
        now = {mine: 1000.0}                                     # what the OS says a pid is
        self._lines({'op': 'spawn', 'execution_id': ids.new_id('execution'), 'process_seq': 1,
                     'pid': mine, 'create_time': 1000.0},
                    {'op': 'spawn', 'execution_id': ids.new_id('execution'), 'process_seq': 2,
                     'pid': mine, 'create_time': 999.0},          # recycled: ours has exited
                    {'op': 'spawn', 'execution_id': ids.new_id('execution'), 'process_seq': 3,
                     'pid': other, 'create_time': None},          # unknown: never touched
                    {'op': 'end', 'execution_id': ids.new_id('execution'), 'process_seq': 4,
                     'ended_at': 1})
        seen = []

        def kill_pid_tree(pid, create_time):                     # the pid-reuse rule of §15.2
            seen.append((pid, create_time, LocalNode.disarmed()))
            return bool(create_time is not None and now.get(pid) == create_time)
        monkeypatch.setattr(local.proc, 'kill_pid_tree', kill_pid_tree)
        assert LocalNode.disarmed() is False
        killed, gone = LocalNode.estop_without_core()
        assert [x['process_seq'] for x in killed] == [1]
        assert [x['process_seq'] for x in gone] == [2, 3]
        assert [s[0] for s in seen] == [mine, mine, other]        # the same pid, twice, judged
        assert [s[1] for s in seen] == [1000.0, 999.0, None]      # by its create time, not pid
        assert [s[2] for s in seen] == [True, True, True]         # every kill followed the flag
        assert LocalNode.disarmed() is True
        body = json.load(open(paths.stop_sentinel(), encoding='utf-8'))
        assert set(body) == {'at'} and body['at'] > 0
        LocalNode.clear_estop()
        assert LocalNode.disarmed() is False and LocalNode.clear_estop() is None

    def test_an_empty_registry_disarms_nothing_and_kills_nothing(self, monkeypatch):
        seen = []
        monkeypatch.setattr(local.proc, 'kill_pid_tree',
                            lambda pid, ct: seen.append((pid, ct)) or False)
        killed, gone = LocalNode.estop_without_core()
        assert killed == [] and gone == [] and seen == []
        assert LocalNode.disarmed() is True                       # even with nothing to kill
        LocalNode.clear_estop()


# ── GAP 9: the registry and the hook mailbox read fail closed ────────────────

class TestRegistryMailbox:
    def test_a_torn_line_is_skipped_and_spawn_pairs_with_end_by_identity(self, tmp_path):
        mine = ids.new_id('execution')
        good = json.dumps({'op': 'spawn', 'execution_id': mine, 'process_seq': 7, 'pid': 5})
        ended = json.dumps({'op': 'end', 'execution_id': mine, 'process_seq': 8})
        os.makedirs(paths.run_dir(), exist_ok=True)
        with open(paths.processes_registry(), 'w', encoding='utf-8') as f:      # made below
            f.write(good + '\n' + '{"op": "spawn", "execution_id": ' + '\n' + ended + '\n')
        assert LocalNode.registry() == [{'op': 'spawn', 'execution_id': mine,
                                         'process_seq': 7, 'pid': 5},
                                        {'op': 'end', 'execution_id': mine, 'process_seq': 8}]
        assert [x['process_seq'] for x in LocalNode.unended()] == [7]   # the torn line is none
        other = ids.new_id('execution')
        with open(paths.processes_registry(), 'a', encoding='utf-8') as f:
            f.write(json.dumps({'op': 'spawn', 'execution_id': other, 'process_seq': 7}) + '\n')
            f.write(json.dumps({'op': 'end', 'execution_id': other, 'process_seq': 9}) + '\n')
        # an end line pairs with one process only: another seq of the same id still runs
        assert [(x['execution_id'], x['process_seq']) for x in LocalNode.unended()] == \
            [(mine, 7), (other, 7)]
        assert LocalNode.registry() == LocalNode.registry()               # reading changes nil

    def test_compacting_keeps_only_the_unended_lines_and_survives_an_absent_file(self):
        node = LocalNode(isolation=object())
        assert LocalNode.registry() == [] and LocalNode.unended() == []
        assert node.compact_registry() is None               # no file yet: none made of nothing
        mine, other = ids.new_id('execution'), ids.new_id('execution')
        os.makedirs(paths.run_dir(), exist_ok=True)
        with open(paths.processes_registry(), 'w', encoding='utf-8') as f:
            f.write('{"op": "spawn", "execution_id": "x",,,\n')                # torn away
            f.write(json.dumps({'op': 'spawn', 'execution_id': mine, 'process_seq': 1}) + '\n')
            f.write(json.dumps({'op': 'spawn', 'execution_id': other, 'process_seq': 2}) + '\n')
            f.write(json.dumps({'op': 'end', 'execution_id': other, 'process_seq': 2}) + '\n')
        assert node.compact_registry() is None
        assert [(x['execution_id'], x['process_seq']) for x in LocalNode.registry()] == \
            [(mine, 1)]
        node.compact_registry()                            # twice keeps the same one line
        assert [(x['execution_id'], x['process_seq']) for x in LocalNode.registry()] == \
            [(mine, 1)]

    def _box(self, execution_id):
        p = paths.ExecPaths(execution_id)
        os.makedirs(p.req)
        os.makedirs(p.res)
        return p

    def test_an_unreadable_request_is_still_returned_so_only_core_can_answer_it(self, tmp_path):
        eid = ids.new_id('execution')
        p = self._box(eid)
        for seq, body in ((2, b'{"ask": "go"}'), (10, b'{"ask":'), (3, b'[]')):
            with open(os.path.join(p.req, '%d.req.json' % seq), 'wb') as f:
                f.write(body)
        for junk in ('x.req.json', '4.req.json.bak', 'notes.txt'):
            open(os.path.join(p.req, junk), 'wb').close()
        # an answer the execution wrote beside its own request is not an answer (PV-20 §7.5)
        with open(os.path.join(p.req, '2.res.json'), 'wb') as f:
            f.write(b'{"decision": "allow", "reason": "I answered myself"}')
        assert LocalNode.pending_requests(eid) == [(2, {'ask': 'go'}), (3, None), (10, None)]
        assert LocalNode.pending_requests(ids.new_id('execution')) == []   # no box, nothing due
        LocalNode.respond(eid, 2, 'deny', 'not this one')
        assert LocalNode.pending_requests(eid) == [(3, None), (10, None)]  # Core's file decides
        assert json.load(open(os.path.join(p.res, '2.res.json'), encoding='utf-8')) == \
            {'decision': 'deny', 'reason': 'not this one', 'nonce': None}
        assert sorted(os.listdir(p.res)) == ['2.res.json']    # respond wrote it, alone
        LocalNode.respond(eid, 2, 'allow', 'changed my mind')
        assert json.load(open(os.path.join(p.res, '2.res.json'), encoding='utf-8')) == \
            {'decision': 'allow', 'reason': 'changed my mind', 'nonce': None}
        assert sorted(os.listdir(p.res)) == ['2.res.json']    # the one writer, still one file

    def test_a_request_answered_in_class_two_stops_being_due(self, tmp_path):
        eid = ids.new_id('execution')
        p = self._box(eid)
        with open(os.path.join(p.req, '1.req.json'), 'wb') as f:
            f.write(b'{"ask": "handoff"}')
        LocalNode.respond(eid, 1, 'allow')
        with open(os.path.join(p.req, '2.req.json'), 'wb') as f:
            f.write(b'{"ask": "again"}')
        os.remove(os.path.join(p.res, '1.res.json'))
        assert [s for s, _b in LocalNode.pending_requests(eid)] == [1, 2]


class TestStagingPresent:
    def test_an_alias_whose_target_is_gone_is_still_there_to_the_check_that_must_see_it(
            self, tmp_path):
        missing = str(tmp_path / 'nothing-here-at-all')
        link = str(tmp_path / 'link')
        try:
            os.symlink(missing, link)
        except (OSError, NotImplementedError):
            pytest.skip('this user may not make a symlink')
        assert os.path.exists(link) is False                  # the trap `exists` would fall in
        assert staging._present(link) is True                 # Core sees it, and so refuses
        with pytest.raises(staging.StageError, match='an alias, never followed'):
            staging._entry(link)
        assert staging._present(str(tmp_path / 'genuinely-absent')) is False
        assert staging._present(str(tmp_path)) is True

    def test_a_broken_lstat_is_a_refusal_not_an_absence(self, monkeypatch, tmp_path):
        def broken(path):
            raise OSError(13, 'the volume is gone')
        monkeypatch.setattr(os, 'lstat', broken)
        with pytest.raises(OSError, match='the volume is gone'):
            staging._present(str(tmp_path / 'anything'))

    def test_an_entry_is_held_to_the_kind_it_was_come_for(self, tmp_path):
        (tmp_path / 'file').write_text('x')
        st = staging._entry(str(tmp_path / 'file'))
        assert st.st_size == 1
        for path, want in ((str(tmp_path / 'file'), True), (str(tmp_path), False)):
            with pytest.raises(staging.StageError, match='not the plain entry expected'):
                staging._entry(path, want)
        if not hasattr(os, 'mkfifo'):
            return                                            # nt has no fifos
        fifo = str(tmp_path / 'fifo')
        os.mkfifo(fifo)
        assert staging._present(fifo) is True                 # there, and neither of the two
        with pytest.raises(staging.StageError, match='not the plain entry expected'):
            staging._entry(fifo, None)


# ── GAP 10: the worktree and merge pair ──────────────────────────────────────

class TestWorktreesAndMerge:
    def test_the_length_cap_pre_empts_only_where_git_for_windows_refuses(self, tmp_path):
        assert isinstance(local.PathTooLong(), OSError)
        assert (local.GIT_DIR_MAX is None) == (os.name != 'nt')      # measured, T-077
        far = os.path.join(str(tmp_path), os.sep.join('x' * 24 for _ in range(8)))
        if os.name == 'nt':
            with pytest.raises(local.PathTooLong, match='Set ARCHEUS_HOME to a shorter folder'):
                local.check_worktree_path(far)
            with pytest.raises(local.PathTooLong, match='accepts at most'):
                local.check_worktree_path(os.path.join(str(tmp_path), 'y' * 300))
        else:
            assert local.check_worktree_path(far) is None       # no such cap elsewhere

    def test_a_worktree_dir_that_is_already_there_is_taken_as_ours_without_asking_git(
            self, monkeypatch, tmp_path):
        started = _children(monkeypatch)
        mine = str(tmp_path / 'wt' / 'task')                    # left by an add before a restart
        os.makedirs(mine)
        open(os.path.join(mine, 'work-in-progress'), 'wb').close()
        assert LocalNode.add_worktree(str(tmp_path), mine, 'task.key', base='main') == mine
        assert LocalNode.mission_worktree(str(tmp_path), mine, 'mission.key', 'main') == mine
        assert started == []                                    # not one process was started
        assert sorted(os.listdir(mine)) == ['work-in-progress']  # and nothing was written in it

    @needs_git
    def test_a_branch_is_moved_only_when_nothing_would_be_lost(self, tmp_path, real_git):
        root, base, tip, env = _repo(tmp_path)
        behind = str(tmp_path / 'wt-behind')                    # ours, and behind the base
        _git(root, 'branch', 'task-behind', base, env=env)
        assert LocalNode.add_worktree(str(root), behind, 'task-behind', 'main') == behind
        assert _git(root, 'rev-parse', 'task-behind', env=env) == tip   # -B: nothing lost
        assert open(os.path.join(behind, 'a.txt'), 'rb').read() == b'two\n'
        # a branch holding work the base has never seen is left exactly as it was
        _git(root, 'checkout', '-q', '-b', 'task-kept', env=env)
        (root / 'only-mine.txt').write_bytes(b'mine\n')
        _git(root, 'add', '-A', env=env)
        _git(root, 'commit', '-q', '-m', 'work of mine', env=env)
        held = _git(root, 'rev-parse', 'task-kept', env=env)
        _git(root, 'checkout', '-q', 'main', env=env)
        ahead = str(tmp_path / 'wt-kept')
        with pytest.raises(OSError, match='holds commits main does not; it is left as it is'):
            LocalNode.add_worktree(str(root), ahead, 'task-kept', 'main')
        assert _git(root, 'rev-parse', 'task-kept', env=env) == held
        assert not os.path.exists(ahead)                        # nothing made on the way out
        listed = _git(root, 'worktree', 'list', '--porcelain', env=env).splitlines()
        assert sum(line.startswith('worktree ') for line in listed) == 2   # the source and wt-behind

    @needs_git
    def test_the_mission_worktree_is_created_from_the_base_once(self, tmp_path, real_git):
        root, base, tip, env = _repo(tmp_path)
        wt = str(tmp_path / 'mission-wt')
        assert LocalNode.mission_worktree(str(root), wt, 'mission.key', 'main') == wt
        assert _git(root, 'rev-parse', 'mission.key', env=env) == tip
        assert LocalNode.git_head(wt) == tip                      # the branch, checked out
        (root / 'later.txt').write_bytes(b'later\n')             # the branch moves on
        _git(root, 'add', '-A', env=env)
        _git(root, 'commit', '-q', '-m', 'later', env=env)
        moved = _git(root, 'rev-parse', 'main', env=env)
        assert LocalNode.mission_worktree(str(root), wt, 'mission.key', 'main') == wt
        assert _git(root, 'rev-parse', 'mission.key', env=env) == tip   # made once, never moved
        assert _git(root, 'rev-parse', 'HEAD', env=env) == moved

    @needs_git
    def test_a_snapshot_commits_as_archeus_and_only_what_there_is_to_commit(self, tmp_path,
                                                                           real_git):
        root, _base, tip, env = _repo(tmp_path)
        before = _git(root, 'rev-list', '--count', 'HEAD', env=env)
        assert LocalNode.git_snapshot(str(root), 'nothing of mine') == tip
        assert _git(root, 'rev-list', '--count', 'HEAD', env=env) == before   # no empty commit
        assert _git(root, 'log', '-1', '--format=%an', env=env) != 'Archeus'
        (root / 'a.txt').write_bytes(b'edited by the task\n')
        head = LocalNode.git_snapshot(str(root), 'Core commits what the task left')
        assert head != tip and LocalNode.git_head(str(root)) == head
        assert _git(root, 'rev-list', '--count', 'HEAD', env=env) == str(int(before) + 1)
        assert _git(root, 'log', '-1', '--format=%an <%ae> %s', env=env) == \
            'Archeus <archeus@localhost> Core commits what the task left'
        assert LocalNode.git_dirty(str(root)) is False          # everything of it is in
        with open(root / '.git' / 'config', 'rb') as f:            # nobody's config but this
            assert b'[user]' not in f.read()                       # command's own

    @pytest.mark.parametrize('branch,want', [('other-clean', 'merged'),
                                              ('other-clash', 'conflict')])
    @needs_git
    def test_a_merge_either_lands_as_archeus_or_is_aborted_leaving_the_branch(self, monkeypatch,
                                                                             tmp_path, real_git,
                                                                             branch, want):
        root, _base, tip, env = _repo(tmp_path)
        _git(root, 'checkout', '-q', '-b', branch, env=env)
        if branch == 'other-clean':
            (root / 'only-theirs.txt').write_bytes(b'theirs\n')
        else:
            (root / 'a.txt').write_bytes(b'theirs\n')            # the very line main changed
        _git(root, 'add', '-A', env=env)
        _git(root, 'commit', '-q', '-m', 'their side', env=env)
        theirs = _git(root, 'rev-parse', 'HEAD', env=env)
        _git(root, 'checkout', '-q', 'main', env=env)
        (root / 'a.txt').write_bytes(b'ours\n')
        _git(root, 'add', '-A', env=env)
        _git(root, 'commit', '-q', '-m', 'our side', env=env)
        ours = _git(root, 'rev-parse', 'HEAD', env=env)
        kind, detail = LocalNode.git_merge(str(root), theirs, 'Merge the task back')
        if want == 'merged':
            assert kind == 'merged' and detail == LocalNode.git_head(str(root))
            assert _git(root, 'log', '-1', '--format=%P', env=env).split() == [ours, theirs]
            assert _git(root, 'log', '-1', '--format=%an <%ae>', env=env) == \
                'Archeus <archeus@localhost>'                    # Core's own identity, never
            assert open(root / 'only-theirs.txt', 'rb').read() == b'theirs\n'
        else:
            assert kind == 'conflict' and detail == ['a.txt']
            assert not os.path.exists(root / '.git' / 'MERGE_HEAD')      # the merge was aborted
            assert _git(root, 'rev-parse', 'HEAD', env=env) == ours      # the branch as it was
            assert open(root / 'a.txt', 'rb').read() == b'ours\n'
            assert LocalNode.git_dirty(str(root), tracked_only=True) is False
            assert _git(root, 'log', '-1', '--format=%s', env=env) == 'our side'

    @needs_git
    def test_a_conflicted_file_with_a_space_in_its_name_is_reported_whole(self, tmp_path,
                                                                         real_git):
        root, _base, _tip, env = _repo(tmp_path)
        name = 'q4 report.txt'

        def commit(content, message):
            (root / name).write_bytes(content)
            _git(root, 'add', '-A', env=env)
            _git(root, 'commit', '-q', '-m', message, env=env)
        commit(b'base\n', 'the file')
        _git(root, 'checkout', '-q', '-b', 'other', env=env)
        commit(b'theirs\n', 'their side')
        theirs = _git(root, 'rev-parse', 'HEAD', env=env)
        _git(root, 'checkout', '-q', 'main', env=env)
        commit(b'ours\n', 'our side')
        assert LocalNode.git_merge(str(root), theirs, 'Merge the task back') == ('conflict', [name])
