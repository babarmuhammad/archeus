"""PV-20 K1 (T-048) and K2 (T-066): the Core-owned store and the seed it builds,
with real Git, in pytest-owned temp only.

Each hazard is a sentinel: a hook, filter, driver or upload-pack hook that
creates a file in `sent/` when Git runs it. The pinned operations run first,
under a hostile world (global config, an include, environment config, the
source repository's own config), and must leave `sent/` empty; then each
hazard is fired once WITHOUT the pin, so an empty `sent/` is evidence and not a
sentinel that could never fire. The user repository is a temp fixture: no real
repository, installed runtime or network is touched."""

import hashlib
import os
import shutil
import stat
import subprocess
import sys
import time

import pytest

from archeus.core.domain import ids
from archeus.infra import paths
from archeus.node import local
from archeus.node.local import EMPTY_TREE, STORE_GIT_FLOOR, STORE_HEAD, LocalNode, StoreError

GIT = shutil.which('git')
pytestmark = pytest.mark.skipif(not GIT, reason='no git on PATH')
SENTINEL = 'import os, sys\nopen(os.path.join(sys.argv[1], sys.argv[2]), "w").close()\n'
HOOKS = ('reference-transaction', 'post-commit', 'post-checkout', 'post-merge', 'post-update')
#: what `init --bare -q --object-format=sha1 --template=<empty>` wrote at the
#: pinned 2.49.0.windows.1 (observed here, T-048): the shape local._INIT_CONFIG pins
WINDOWS_INIT_CONFIG = (b'[core]\n\trepositoryformatversion = 0\n\tfilemode = false\n'
                       b'\tbare = true\n\tsymlinks = false\n\tignorecase = true\n')


@pytest.fixture(autouse=True)
def fresh_git():
    local._git_exe.cache_clear()
    local._VERSION.clear()
    yield
    local._git_exe.cache_clear()
    local._VERSION.clear()


def _fwd(p):
    return str(p).replace('\\', '/')


class World:
    """The fixture repository and the hostile configuration around it."""

    def __init__(self, tmp):
        self.tmp, self.sent = tmp, tmp / 'sent'
        self.sent.mkdir()
        script = tmp / 'sentinel.py'
        script.write_text(SENTINEL)
        self.cmd = lambda name: '"%s" "%s" "%s" %s' % (_fwd(sys.executable), _fwd(script),
                                                        _fwd(self.sent), name)
        clean = tmp / 'clean'
        clean.mkdir()
        (clean / 'empty.cfg').write_text('')
        base = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        #: fixture setup: no global or system config at all
        self.clean = dict(base, HOME=str(clean), XDG_CONFIG_HOME=str(clean),
                          GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=str(clean / 'empty.cfg'))
        # hooks reached three ways: a global include, the environment, the repo's own config
        for who in ('g', 'e', 'l'):
            d = tmp / ('hooks-' + who)
            d.mkdir()
            for h in HOOKS:
                (d / h).write_text('#!/bin/sh\n%s\n' % self.cmd('%s-%s' % (who, h)))
        home = tmp / 'hostile'
        home.mkdir()
        (home / 'inc.cfg').write_text('[core]\n\thooksPath = %s\n' % _fwd(tmp / 'hooks-g'))
        (home / '.gitconfig').write_text(
            '[include]\n\tpath = %s\n' % _fwd(home / 'inc.cfg')
            + '[core]\n\tfsmonitor = %s\n' % self.cmd('g-fsmonitor')
            + '[diff "sent"]\n\tcommand = %s\n' % self.cmd('g-extdiff')
            + '[diff "tc"]\n\ttextconv = %s\n' % self.cmd('g-textconv')
            + '[filter "cl"]\n\tclean = %s\n' % self.cmd('g-clean')
            + '[filter "sm"]\n\tsmudge = %s\n' % self.cmd('g-smudge')
            + '[uploadpack]\n\tpackObjectsHook = %s\n' % self.cmd('g-packhook'))
        #: the world a Core process could inherit: global config with an include,
        #: and command-scope config from the environment
        self.hostile = dict(base, HOME=str(home), XDG_CONFIG_HOME=str(home),
                            GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_COUNT='1',
                            GIT_CONFIG_KEY_0='core.hooksPath',
                            GIT_CONFIG_VALUE_0=_fwd(tmp / 'hooks-e'))
        self.user = tmp / 'user'
        self.git(self.tmp, 'init', '-q', '-b', 'main', str(self.user))
        (self.user / '.gitattributes').write_text(
            'a.txt diff=sent filter=cl\nb.txt diff=tc\nc.txt filter=cl\ns.txt filter=sm\n')
        (self.user / 'a.txt').write_text('one\n')
        (self.user / 's.txt').write_text('ess\n')
        self.git(self.user, 'add', '-A')
        self.git(self.user, 'commit', '-q', '-m', 'c1')
        self.c1 = self.git(self.user, 'rev-parse', 'HEAD')
        (self.user / 'a.txt').write_text('two\n')
        (self.user / 'b.txt').write_text('bee\n')
        self.git(self.user, 'add', '-A')
        self.git(self.user, 'commit', '-q', '-m', 'c2')
        self.c2 = self.git(self.user, 'rev-parse', 'HEAD')
        self.a2 = self.git(self.user, 'rev-parse', 'HEAD:a.txt')
        self.b2 = self.git(self.user, 'rev-parse', 'HEAD:b.txt')
        # the source repository's OWN config: hooks and an fsmonitor (an include
        # would make Core refuse the source: test_a_source_config_git_wrote_with_an_inclusion_is_refused)
        self.git(self.user, 'config', 'core.hooksPath', _fwd(tmp / 'hooks-l'))
        self.git(self.user, 'config', 'core.fsmonitor', self.cmd('l-fsmonitor'))
        assert self.fired() == []

    def git(self, cwd, *args, env=None, check=True):
        r = subprocess.run([GIT, '-c', 'user.name=t', '-c', 'user.email=t@t'] + list(args),
                           cwd=str(cwd), env=env or self.clean, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', stdin=subprocess.DEVNULL)
        assert r.returncode == 0 or not check, (args, r.stderr)
        return r.stdout.strip()

    def fired(self):
        return sorted(os.listdir(self.sent))


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def _hostile(monkeypatch, world):
    for k in [k for k in os.environ if k.startswith('GIT_')]:
        monkeypatch.delenv(k)
    for k in ('HOME', 'XDG_CONFIG_HOME', 'GIT_CONFIG_NOSYSTEM', 'GIT_CONFIG_COUNT',
              'GIT_CONFIG_KEY_0', 'GIT_CONFIG_VALUE_0'):
        monkeypatch.setenv(k, world.hostile[k])


def test_the_installed_git_meets_the_floor_through_the_pin(capsys):
    """`git version`, run by the pinned runner in Core's empty pin directory."""
    local._pin_files(())
    v = local._git_version(())
    print('\nK1 git: %s | %s | floor %s' % (local._git_exe(), v,
                                            '.'.join(map(str, STORE_GIT_FLOOR))))
    assert os.path.isabs(local._git_exe())
    assert os.listdir(os.path.join(paths.repos_dir(), '.pin', 'empty')) == []


def test_a_store_is_created_bare_sealed_and_recorded(world):
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid, workdirs=())
    assert store == paths.repo_store(pid)
    pin = os.path.join(paths.repos_dir(), '.pin')
    with open(os.path.join(store, 'HEAD')) as f:
        assert f.read() == STORE_HEAD
    with open(os.path.join(store, 'config'), 'rb') as f:
        cfg = f.read()
    print('\nK1 init config (%s): %r' % (local._git_version(()), cfg))
    assert local._INIT_CONFIG.fullmatch(cfg.decode('ascii'))
    if sys.platform == 'win32':
        assert cfg == WINDOWS_INIT_CONFIG
    for absent in ('hooks', 'info', 'description', 'commondir', 'config.worktree',
                   os.path.join('objects', 'info', 'alternates')):
        assert not os.path.exists(os.path.join(store, absent)), absent
    import json
    with open(os.path.join(pin, pid + '.json')) as f:
        rec = json.load(f)
    assert rec['git'] == local._git_exe() and rec['empty_tree'] == EMPTY_TREE
    assert os.path.exists(os.path.join(pin, pid + '.owned'))
    assert LocalNode.store_read(pid, ['cat-file', '-t', EMPTY_TREE], workdirs=()).strip() == 'tree'
    assert LocalNode.store_open(pid, workdirs=()) == store                      # reopening is checking
    assert world.fired() == []


@pytest.mark.parametrize('plant', ['alternates', 'attributes', 'config', 'hook', 'head'])
def test_a_store_changed_after_its_seal_is_refused(world, plant):
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid, workdirs=())
    if plant == 'alternates':
        open(os.path.join(store, 'objects', 'info', 'alternates'), 'w').close()
    elif plant == 'attributes':
        os.makedirs(os.path.join(store, 'info'))
        open(os.path.join(store, 'info', 'attributes'), 'w').close()
    elif plant == 'config':
        with open(os.path.join(store, 'config'), 'a') as f:
            f.write('[core]\n\thooksPath = %s\n' % _fwd(world.tmp / 'hooks-g'))
    elif plant == 'hook':
        os.makedirs(os.path.join(store, 'hooks'))
        open(os.path.join(store, 'hooks', 'post-update'), 'w').close()
    else:
        with open(os.path.join(store, 'HEAD'), 'w') as f:
            f.write('ref: refs/heads/main\n')
    with pytest.raises(StoreError):
        LocalNode.store_open(pid, workdirs=())
    with pytest.raises(StoreError):
        LocalNode.store_read(pid, ['rev-parse', '--verify', '-q', EMPTY_TREE], workdirs=())


def test_a_crash_between_init_and_seal_is_sealed_on_the_next_open(world, monkeypatch):
    pid = ids.new_id('project')
    real = LocalNode.store_git

    def crash(mode, args, **kw):
        if mode == 'seal':
            raise StoreError('crashed before the seal')
        return real(mode, args, **kw)
    monkeypatch.setattr(LocalNode, 'store_git', staticmethod(crash))
    with pytest.raises(StoreError, match='crashed'):
        LocalNode.store_open(pid, workdirs=())
    assert os.path.isdir(paths.repo_store(pid))
    monkeypatch.setattr(LocalNode, 'store_git', staticmethod(real))
    assert LocalNode.store_open(pid, workdirs=()) == paths.repo_store(pid)


def test_a_sealed_store_whose_record_is_lost_is_refused_once_it_holds_refs(world, monkeypatch):
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    pid = ids.new_id('project')
    LocalNode.store_fetch(pid, str(world.user), 'refs/heads/main', world.c2,
                          'refs/archeus/exec/e1/seed', workdirs=())
    os.remove(os.path.join(paths.repos_dir(), '.pin', pid + '.json'))
    with pytest.raises(StoreError, match='holds refs'):
        LocalNode.store_open(pid, workdirs=())


def test_the_pinned_store_runs_nothing_the_world_configures(world, monkeypatch):
    """The pinned path, end to end, under every hazard at once; then each hazard
    fires without the pin (the positive controls)."""
    _hostile(monkeypatch, world)
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid, workdirs=())
    ref = 'refs/archeus/exec/e1/seed'
    assert LocalNode.store_fetch(pid, str(world.user), 'refs/heads/main', world.c2, ref,
                                 workdirs=()) == world.c2
    read = lambda *a: LocalNode.store_read(pid, list(a), workdirs=())
    assert read('rev-parse', ref).strip() == world.c2
    assert read('ls-tree', '--name-only', ref).split() == ['.gitattributes', 'a.txt', 'b.txt',
                                                              's.txt']
    assert read('merge-base', world.c1, world.c2).strip() == world.c1
    assert read('diff', '--numstat', world.c1, world.c2).splitlines() == [
        '1\t1\ta.txt', '1\t0\tb.txt']
    assert '+two' in read('diff', world.c1, world.c2) and '+bee' in read('diff', world.c1, world.c2)
    # a replace ref planted in the store: the pinned read sees the original object
    os.makedirs(os.path.join(store, 'refs', 'replace'))
    with open(os.path.join(store, 'refs', 'replace', world.a2), 'w') as f:
        f.write(world.b2 + '\n')
    assert read('cat-file', '-p', world.a2) == 'two\n'
    assert LocalNode.store_resolve_base(str(world.user), 'refs/heads/main',
                                        workdirs=()) == world.c2
    assert world.fired() == []                                    # the pinned path: nothing

    # positive controls: each hazard on its own, unpinned, with its own sentinel
    # that had not fired before the control and has after it
    h, u = world.hostile, world.user
    g_only = dict(h, GIT_CONFIG_COUNT='0')      # the global config (and its include) alone
    fired = []

    def fires(name, cwd, *args, env=None):
        assert name not in world.fired(), name
        world.git(cwd, *args, env=env, check=False)
        assert name in world.fired(), name
        fired.append(name)
    scratch, quiet = world.tmp / 'scratch', world.tmp / 'quiet'
    for r in (scratch, quiet):
        world.git(world.tmp, 'init', '-q', str(r))
        (r / 'f.txt').write_text('f\n')
        world.git(r, 'add', 'f.txt')
        world.git(r, 'commit', '-q', '-m', 'f')
    # fsmonitor first: every later control in these repositories refreshes an index
    fires('g-fsmonitor', quiet, 'status', env=g_only)    # global config, no local one
    fires('l-fsmonitor', u, 'status')                    # the repo's own config, no global
    fires('e-post-commit', scratch, 'commit', '-q', '--allow-empty', '-m', 'x', env=h)
    fires('g-post-commit', scratch, 'commit', '-q', '--allow-empty', '-m', 'y', env=g_only)
    fires('l-post-commit', u, 'commit', '-q', '--allow-empty', '-m', 'z')
    fires('g-extdiff', u, 'diff', world.c1, world.c2, '--', 'a.txt', env=h)
    fires('g-textconv', u, 'diff', world.c1, world.c2, '--', 'b.txt', env=h)
    (u / 'c.txt').write_text('see\n')
    fires('g-clean', u, 'add', 'c.txt', env=h)
    os.remove(str(u / 's.txt'))
    fires('g-smudge', u, 'checkout', '--', 's.txt', env=h)
    world.git(world.tmp, 'init', '-q', '--bare', str(world.tmp / 'scratch.git'))
    fires('g-packhook', world.tmp / 'scratch.git', 'fetch', '-q', str(u),
          'refs/heads/main:refs/x', env=g_only)          # the source side
    unpinned = world.git(world.tmp, '--git-dir', store, 'cat-file', '-p', world.a2)
    assert unpinned == 'bee'                                               # the replace ref
    print('\nK1 controls fired unpinned, one by one: %s' % fired)


def test_a_fetch_whose_ref_moved_is_refused_and_keeps_what_came(world, monkeypatch):
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    pid = ids.new_id('project')
    with pytest.raises(StoreError, match='lost race'):
        LocalNode.store_fetch(pid, str(world.user), 'refs/heads/main', world.c1,
                              'refs/archeus/exec/e1/seed', workdirs=())
    read = lambda *a: LocalNode.store_read(pid, list(a), workdirs=())
    assert read('rev-parse', 'refs/archeus/incoming/exec/e1/seed').strip() == world.c2
    with pytest.raises(StoreError):
        read('rev-parse', '--verify', '-q', 'refs/archeus/exec/e1/seed')
    assert world.fired() == []


def test_the_file_protocol_pin_governs_a_plain_local_path(world, monkeypatch):
    """GIT_ALLOW_PROTOCOL=file is what lets a fetch from a plain path through: the
    same pinned call with only `ext` allowed is refused."""
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid, workdirs=())
    argv, env, cwd = local._store_pin('trusted', store)
    fetch = argv + ['fetch', '--no-tags', '--no-write-fetch-head', str(world.user),
                    '+refs/heads/main:refs/archeus/incoming/probe']
    r = subprocess.run(fetch, cwd=cwd, env=dict(env, GIT_ALLOW_PROTOCOL='ext'),
                       capture_output=True, text=True)
    assert r.returncode != 0 and 'transport' in r.stderr.lower(), r.stderr
    r = subprocess.run(fetch, cwd=cwd, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── aliases (T-048 r2): nothing Git resolves in a store may be a link ────────

def _junction(link, target):
    """A directory alias in pytest temp: a junction on Windows (no privilege
    needed), a symlink elsewhere."""
    if sys.platform == 'win32':
        r = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    else:
        os.symlink(str(target), str(link), target_is_directory=True)


def _aliased(path, outside):
    """*path* moved to *outside*, and a directory alias left where it was."""
    os.rename(path, str(outside))
    _junction(path, outside)


def _snapshot(top):
    """Every entry under *top*: size, content hash (files), mode and mtime."""
    out = {}
    for d, dirs, files in os.walk(str(top)):
        for n in dirs + files:
            p = os.path.join(d, n)
            st = os.lstat(p)
            digest = None
            if stat.S_ISREG(st.st_mode):
                with open(p, 'rb') as f:
                    digest = hashlib.sha256(f.read()).hexdigest()
            out[os.path.relpath(p, str(top))] = (st.st_size, digest, st.st_mode, st.st_mtime_ns)
    return out


@pytest.mark.parametrize('what', ['store', 'objects', 'objects-info', 'objects-pack', 'refs',
                                  'refs-heads', 'info', 'repos', 'pin', 'pin-empty'])
def test_a_directory_alias_in_the_store_or_its_pin_is_refused(world, tmp_path, what):
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid, workdirs=())
    pin = os.path.join(paths.repos_dir(), '.pin')
    j = os.path.join
    path = {'store': store, 'objects': j(store, 'objects'), 'objects-info': j(store, 'objects', 'info'),
            'objects-pack': j(store, 'objects', 'pack'), 'refs': j(store, 'refs'),
            'refs-heads': j(store, 'refs', 'heads'), 'info': j(store, 'info'),
            'repos': paths.repos_dir(), 'pin': pin, 'pin-empty': j(pin, 'empty')}[what]
    if what == 'info':
        os.makedirs(path)                   # init with an empty template makes none
    _aliased(path, tmp_path / ('outside-' + what))
    with pytest.raises(OSError, match='alias|plain'):
        LocalNode.store_open(pid, workdirs=())
    with pytest.raises(OSError, match='alias|plain'):
        LocalNode.store_read(pid, ['rev-parse', EMPTY_TREE], workdirs=())


@pytest.mark.parametrize('what', ['objects', 'objects-4b'])
def test_a_seal_never_writes_through_an_objects_alias(world, tmp_path, monkeypatch, what):
    """A crash left a claimed, unsealed store; its objects (or the directory the
    empty tree goes to) became an alias: the seal is refused and writes nothing."""
    pid = ids.new_id('project')
    real = LocalNode.store_git

    def crash(mode, args, **kw):
        if mode == 'seal':
            raise StoreError('crashed before the seal')
        return real(mode, args, **kw)
    monkeypatch.setattr(LocalNode, 'store_git', staticmethod(crash))
    with pytest.raises(StoreError, match='crashed'):
        LocalNode.store_open(pid, workdirs=())
    monkeypatch.setattr(LocalNode, 'store_git', staticmethod(real))
    store, outside = paths.repo_store(pid), tmp_path / 'outside'
    if what == 'objects':
        _aliased(os.path.join(store, 'objects'), outside)
    else:
        outside.mkdir()
        _junction(os.path.join(store, 'objects', EMPTY_TREE[:2]), outside)
    before = _snapshot(outside)
    with pytest.raises(OSError, match='alias|plain'):
        LocalNode.store_open(pid, workdirs=())
    assert _snapshot(outside) == before and not any(EMPTY_TREE[2:] in f for f in before)
    with open(os.path.join(store, 'HEAD')) as f:
        assert f.read() != STORE_HEAD                     # the seal never started
    assert not os.path.exists(os.path.join(paths.repos_dir(), '.pin', pid + '.json'))


@pytest.mark.parametrize('which', ['config', 'HEAD', 'record', 'owned', 'pin-cfg', 'empty-tree'])
def test_a_hard_link_to_sealed_metadata_is_refused_even_with_matching_bytes(world, tmp_path,
                                                                            which):
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid, workdirs=())
    pin = os.path.join(paths.repos_dir(), '.pin')
    path = {'config': os.path.join(store, 'config'), 'HEAD': os.path.join(store, 'HEAD'),
            'record': os.path.join(pin, pid + '.json'), 'owned': os.path.join(pin, pid + '.owned'),
            'pin-cfg': os.path.join(pin, 'empty.cfg'),
            'empty-tree': os.path.join(store, 'objects', EMPTY_TREE[:2], EMPTY_TREE[2:])}[which]
    os.link(path, str(tmp_path / 'outside'))
    if which == 'empty-tree':           # a loose object file: not checked one by one (ponytail)
        assert LocalNode.store_open(pid, workdirs=()) == store
        return
    with pytest.raises(OSError, match='hard-linked'):
        LocalNode.store_open(pid, workdirs=())


@pytest.mark.parametrize('what', ['config', 'objects'])
def test_a_symlink_in_the_store_is_refused(world, tmp_path, what):
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid, workdirs=())
    path, outside = os.path.join(store, what), str(tmp_path / 'outside')
    os.rename(path, outside)
    try:
        os.symlink(outside, path, target_is_directory=what == 'objects')
    except OSError as e:
        os.rename(outside, path)
        pytest.skip('this account cannot create a symlink: %s' % e)
    with pytest.raises(OSError, match='alias|plain'):
        LocalNode.store_open(pid, workdirs=())


def test_a_root_linked_into_an_execution_area_is_refused(world, tmp_path, monkeypatch):
    """Resolved, not only as written: a junction whose target is an execution's
    workspace, or a workdir Core recorded, is that area."""
    work = paths.ExecPaths(ids.new_id('execution')).work
    os.makedirs(work)
    recorded = tmp_path / 'wd'
    recorded.mkdir()
    spawned = []
    monkeypatch.setattr(local.proc, 'run', lambda *a, **k: spawned.append(a))
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    for target in (work, str(recorded)):
        link = tmp_path / ('innocent-%d' % len(os.listdir(str(tmp_path))))
        _junction(link, target)
        with pytest.raises(StoreError, match='execution area'):
            LocalNode.store_resolve_base(str(link), 'refs/heads/main', workdirs=[str(recorded)])
        with pytest.raises(StoreError, match='execution area'):
            LocalNode.store_fetch(ids.new_id('project'), str(link), 'refs/heads/main', '0' * 40,
                                  'refs/archeus/exec/e1/seed', workdirs=[str(recorded)])
    assert spawned == []


@pytest.mark.parametrize('what', ['repos', 'pin', 'pin-empty'])
def test_a_pin_area_alias_to_an_empty_directory_receives_nothing(world, tmp_path, what):
    """A level of the pin area that already exists as an alias is refused before
    anything is made below it: the directory it points at stays empty."""
    repos, pin, empty, _cfg = local._pin_area()
    os.makedirs({'repos': paths.archeus_home(), 'pin': repos, 'pin-empty': pin}[what])
    external = tmp_path / 'external'
    external.mkdir()
    _junction({'repos': repos, 'pin': pin, 'pin-empty': empty}[what], external)
    for call in (lambda: LocalNode.store_open(ids.new_id('project'), workdirs=()),
                 lambda: LocalNode.store_resolve_base(str(world.user), 'refs/heads/main',
                                                      workdirs=())):
        with pytest.raises(OSError, match='alias|plain'):
            call()
        assert os.listdir(str(external)) == []


@pytest.mark.parametrize('where', ['run', 'worktrees', 'recorded'])
@pytest.mark.parametrize('kind', ['commondir', 'alternates'])
def test_a_common_dir_or_store_linked_into_an_execution_area_is_refused(world, tmp_path,
                                                                        monkeypatch, where, kind):
    """The file names an innocent path; the path is a junction into the area."""
    recorded = tmp_path / 'wd'
    target = {'run': os.path.join(paths.ExecPaths(ids.new_id('execution')).state, 'c'),
              'worktrees': os.path.join(paths.archeus_home(), 'worktrees', 'p', 'm', 't1', 'c'),
              'recorded': str(recorded / 'c')}[where]
    os.makedirs(target)
    link = tmp_path / 'innocent'
    _junction(link, target)
    gd = tmp_path / 'gd'
    (gd / 'objects' / 'info').mkdir(parents=True)
    (gd / kind if kind == 'commondir' else gd / 'objects' / 'info' / 'alternates').write_bytes(
        str(link).encode() + b'\n')
    root = tmp_path / 'root'
    root.mkdir()
    (root / '.git').write_text('gitdir: %s\n' % gd)
    spawned = []
    monkeypatch.setattr(local.proc, 'run', lambda *a, **k: spawned.append(a))
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(StoreError, match='execution area'):
        LocalNode.store_resolve_base(str(root), 'refs/heads/main', workdirs=[str(recorded)])
    with pytest.raises(StoreError, match='execution area'):
        LocalNode.store_fetch(ids.new_id('project'), str(root), 'refs/heads/main', '0' * 40,
                              'refs/archeus/exec/e1/seed', workdirs=[str(recorded)])
    assert spawned == []


def test_a_linked_worktree_is_read_through_its_real_common_dir(world, monkeypatch):
    """The control, with Git's own indirection: `git worktree add` writes a
    `.git` file and a relative commondir; both resolve outside every area."""
    wt = world.tmp / 'linked'
    world.git(world.user, 'worktree', 'add', '-q', '-b', 'side', str(wt))
    gd = world.git(wt, 'rev-parse', '--absolute-git-dir')
    fired = world.fired()                       # the worktree's own post-checkout, unpinned
    with open(os.path.join(gd, 'commondir')) as f:
        assert not os.path.isabs(f.read().strip())          # Git wrote a relative one
    assert LocalNode.store_resolve_base(str(wt), 'refs/heads/main', workdirs=()) == world.c2
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    pid = ids.new_id('project')
    assert LocalNode.store_fetch(pid, str(wt), 'refs/heads/main', world.c2,
                                 'refs/archeus/exec/e1/seed', workdirs=()) == world.c2
    assert world.fired() == fired


def _spy(monkeypatch):
    spawned = []
    monkeypatch.setattr(local.proc, 'run', lambda *a, **k: spawned.append(a))
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    return spawned


def _both_refused(root, workdirs, match):
    with pytest.raises(OSError, match=match):
        LocalNode.store_resolve_base(str(root), 'refs/heads/main', workdirs=workdirs)
    with pytest.raises(OSError, match=match):
        LocalNode.store_fetch(ids.new_id('project'), str(root), 'refs/heads/main', '0' * 40,
                              'refs/archeus/exec/e1/seed', workdirs=workdirs)


@pytest.mark.parametrize('how', ['include.path', 'includeIf.gitdir:**.path',
                                 'IncludeIf.onbranch:main.path'])
def test_a_source_config_git_wrote_with_an_inclusion_is_refused(world, monkeypatch, how):
    """As Git itself writes it: `git config include.path ...` in the source."""
    world.git(world.user, 'config', how, _fwd(world.tmp / 'nowhere.cfg'))
    spawned = _spy(monkeypatch)
    _both_refused(world.user, (), "saying 'include'")
    assert spawned == []


@pytest.mark.parametrize('what', ['objects', 'refs', 'refs-heads', 'dot-git'])
def test_a_source_metadata_directory_alias_is_refused(world, tmp_path, monkeypatch, what):
    """objects/ linked into a recorded workdir with no alternates file, refs/
    or one of its directories linked elsewhere, or .git itself a junction."""
    recorded = tmp_path / 'wd'
    recorded.mkdir()
    gd = world.user / '.git'
    path = {'objects': gd / 'objects', 'refs': gd / 'refs', 'refs-heads': gd / 'refs' / 'heads',
            'dot-git': gd}[what]
    assert not (gd / 'objects' / 'info' / 'alternates').exists()
    _aliased(str(path), recorded / what)
    spawned = _spy(monkeypatch)
    _both_refused(world.user, [str(recorded)], 'alias|plain|execution area')
    assert spawned == []


@pytest.mark.parametrize('which', ['config', 'HEAD', 'packed-refs', 'commondir'])
def test_a_hard_linked_metadata_file_of_a_real_source_is_refused(world, tmp_path, monkeypatch,
                                                                 which):
    root = world.user
    if which == 'packed-refs':
        world.git(root, 'pack-refs', '--all')
    if which == 'commondir':
        root = world.tmp / 'linked'
        world.git(world.user, 'worktree', 'add', '-q', '-b', 'side', str(root))
    gd = world.git(root, 'rev-parse', '--absolute-git-dir')
    path = os.path.join(world.git(root, 'rev-parse', '--git-common-dir') if which in (
        'config', 'packed-refs') else gd, which)
    os.link(os.path.join(root, path) if not os.path.isabs(path) else path,
            str(tmp_path / 'outside'))
    spawned = _spy(monkeypatch)
    _both_refused(root, (), 'hard-linked')
    assert spawned == []


def _file_url(p):
    return 'file:///' + _fwd(p).lstrip('/')


def test_a_lazy_fetch_source_is_refused_and_the_pin_alone_still_fetches_nothing(world,
                                                                                 monkeypatch):
    """A real partial clone (blob:none from a file:// source in pytest temp)
    whose main names a commit it does not hold; its promisor remote's
    upload-pack is a sentinel. Refused before anything starts; with that
    refusal taken away, GIT_NO_LAZY_FETCH alone keeps the commit lookup from
    fetching or writing anything; unpinned, the same lookup reaches the remote."""
    u, lazy = world.user, world.tmp / 'lazy'
    world.git(u, 'config', 'uploadpack.allowFilter', 'true')
    world.git(world.tmp, 'clone', '-q', '--filter=blob:none', _file_url(u), str(lazy))
    world.git(u, 'commit', '-q', '--allow-empty', '-m', 'c3')
    c3 = world.git(u, 'rev-parse', 'HEAD')
    (lazy / '.git' / 'refs' / 'heads' / 'main').write_bytes(c3.encode() + b'\n')
    world.git(lazy, 'config', 'remote.origin.uploadpack', world.cmd('lazy-fetch'))
    real_run = local.proc.run
    spawned = _spy(monkeypatch)
    _both_refused(lazy, (), 'which Core does not follow')
    assert spawned == []
    monkeypatch.setattr(local.proc, 'run', real_run)
    monkeypatch.setattr(local, '_SOURCE_CONFIG_REFUSED', (b'include',))
    monkeypatch.setattr(local, '_PROMISOR_PACK', '.never')
    before = _snapshot(lazy), _snapshot(u)
    with pytest.raises(StoreError, match='rev-parse failed'):
        LocalNode.store_resolve_base(str(lazy), 'refs/heads/main', workdirs=())
    assert 'lazy-fetch' not in world.fired() and (_snapshot(lazy), _snapshot(u)) == before
    world.git(lazy, 'rev-parse', '--verify', '-q', c3 + '^{commit}', check=False)
    assert 'lazy-fetch' in world.fired()                  # the positive control


def test_a_shallow_clone_is_a_plain_source(world):
    s = world.tmp / 'shallow'
    world.git(world.tmp, 'clone', '-q', '--depth', '1', _file_url(world.user), str(s))
    assert (s / '.git' / 'shallow').exists()
    assert LocalNode.store_resolve_base(str(s), 'refs/heads/main', workdirs=()) == world.c2


def test_a_source_with_graphs_and_indexes_is_read(world, monkeypatch):
    """commit-graph, multi-pack-index and reverse indexes are guarded, then read
    as data: Git writes them itself, so refusing them would refuse most repositories."""
    u = world.user
    world.git(u, 'repack', '-q', '-a', '-d')
    world.git(u, 'commit-graph', 'write', '--reachable')
    world.git(u, 'multi-pack-index', 'write')
    gd = u / '.git' / 'objects'
    assert (gd / 'info' / 'commit-graph').exists() and (gd / 'pack' / 'multi-pack-index').exists()
    assert LocalNode.store_resolve_base(str(u), 'refs/heads/main', workdirs=()) == world.c2
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    assert LocalNode.store_fetch(ids.new_id('project'), str(u), 'refs/heads/main', world.c2,
                                 'refs/archeus/exec/e1/seed', workdirs=()) == world.c2


@pytest.mark.parametrize('what', ['info', 'commit-graphs', 'multi-pack-index.d',
                                  'inside-commit-graphs'])
def test_a_source_info_or_object_index_alias_is_refused(world, tmp_path, monkeypatch, what):
    gd = world.user / '.git'
    path = {'info': gd / 'info', 'commit-graphs': gd / 'objects' / 'info' / 'commit-graphs',
            'multi-pack-index.d': gd / 'objects' / 'pack' / 'multi-pack-index.d',
            'inside-commit-graphs': gd / 'objects' / 'info' / 'commit-graphs' / 'x'}[what]
    path.mkdir(parents=True, exist_ok=True)
    _aliased(str(path), tmp_path / ('outside-' + what))
    spawned = _spy(monkeypatch)
    _both_refused(world.user, (), 'alias|plain')
    assert spawned == []


@pytest.mark.parametrize('what', ['junction', 'hard-link'])
@pytest.mark.parametrize('where', [('objects', 'info', 'commit-graphs'),
                                   ('objects', 'pack', 'multi-pack-index.d')])
def test_a_nested_alias_below_the_store_object_indexes_is_refused(world, tmp_path, monkeypatch,
                                                                   what, where):
    """gitformat-commit-graph: a chain lives in objects/info/commit-graphs/; an
    incremental multi-pack-index in objects/pack/multi-pack-index.d/."""
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid, workdirs=())
    nested = os.path.join(store, *where)
    os.makedirs(nested)
    if what == 'junction':
        (tmp_path / 'outside').mkdir()
        _junction(os.path.join(nested, 'x'), tmp_path / 'outside')
    else:
        f = os.path.join(nested, 'graph-1.graph')
        open(f, 'wb').close()
        os.link(f, str(tmp_path / 'outside-file'))
    spawned = _spy(monkeypatch)
    with pytest.raises(OSError, match='alias|plain|hard-linked'):
        LocalNode.store_read(pid, ['rev-parse', EMPTY_TREE], workdirs=())
    assert spawned == []



# ── K2 (T-066, T-049 + C-1013-T049): the seed, with real Git in pytest temp ──

#: the base tree: (mode, path, bytes); 160000 takes a commit id instead of bytes
BINARY = b'\xff\xfe\x00\x80\x00z'
LFS = b'version https://git-lfs.github.com/spec/v1\noid sha256:' + b'0' * 64 + b'\nsize 9\n'


def _bgit(cwd, *args, data=None, env):
    r = subprocess.run([GIT, '-c', 'user.name=t', '-c', 'user.email=t@t'] + list(args),
                       cwd=str(cwd), env=env, input=data, capture_output=True,
                       stdin=None if data is not None else subprocess.DEVNULL)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.decode('utf-8').strip()


def _project(world, extra=()):
    """A user repository in pytest temp whose HEAD tree holds every hazard T-049
    §9 names, built with plumbing (no attribute, filter or hook runs while it is
    made); then its own config is made hostile, after the commit."""
    proj, env = world.tmp / 'proj', world.clean
    _bgit(world.tmp, 'init', '-q', '-b', 'main', str(proj), env=env)
    files = [('100644', 'bin.dat', BINARY),
             ('100644', '.gitattributes',
              b'* text=auto\ncrlf.txt text eol=crlf\nenc.txt working-tree-encoding=UTF-16\n'
              b'sm.txt filter=sm\nlfs.bin filter=lfs diff=lfs merge=lfs -text\n'),
             ('100644', '.gitmodules', b'[submodule "sub"]\n\tpath = sub\n\turl = ./nowhere\n'
              b'\tupdate = !' + world.cmd('gitmodules').encode() + b'\n'),
             ('100644', '.lfsconfig', b'[lfs]\n\turl = http://127.0.0.1:9/\n'),
             ('100644', 'crlf.txt', b'a\nb\n'),
             ('100644', 'enc.txt', 'h\u00e9llo\n'.encode('utf-8')),
             ('100644', 'sm.txt', b'smudge me\n'),
             ('100644', 'lfs.bin', LFS),
             ('100755', 'run.sh', b'#!/bin/sh\necho hi\n'),
             ('100644', 'dir/nested/deep.txt', b'deep\n'),
             ('120000', 'link', b'bin.dat'),
             ('120000', 'dir/up', b'../crlf.txt')]
    for mode, path, data in files:
        oid = _bgit(proj, 'hash-object', '-w', '--no-filters', '--stdin', data=data, env=env)
        _bgit(proj, 'update-index', '--add', '--cacheinfo', '%s,%s,%s' % (mode, oid, path),
              env=env)
    _bgit(proj, 'update-index', '--add', '--cacheinfo', '160000,%s,sub' % world.c1, env=env)
    tree = _bgit(proj, 'write-tree', env=env)
    if extra:
        # names Git's own index refuses on Windows reach a tree through mktree,
        # top level only: how a hostile tree arrives (T-049 §9 UNVERIFIED part)
        listing = subprocess.run([GIT, 'ls-tree', '-z', tree], cwd=str(proj), env=env,
                                 capture_output=True, check=True).stdout
        for mode, name, data in extra:
            oid = _bgit(proj, 'hash-object', '-w', '--no-filters', '--stdin', data=data, env=env)
            listing += b'%s blob %s\t%s\0' % (mode.encode(), oid.encode(), name.encode('utf-8'))
            files.append((mode, name, data))
        tree = _bgit(proj, 'mktree', '-z', data=listing, env=env)
    head = _bgit(proj, 'commit-tree', tree, '-m', 'base', env=env)
    _bgit(proj, 'update-ref', 'refs/heads/main', head, env=env)
    world.git(proj, 'config', 'core.hooksPath', _fwd(world.tmp / 'hooks-l'))
    world.git(proj, 'config', 'core.fsmonitor', world.cmd('l-fsmonitor'))
    hooks = proj / '.git' / 'hooks'
    hooks.mkdir(exist_ok=True)
    (hooks / 'post-checkout').write_text('#!/bin/sh\n%s\n' % world.cmd('own-post-checkout'))
    return proj, head, {p: (m, d) for m, p, d in files}


def _seed(world, monkeypatch, proj, mid=None):
    """The first-attempt chain K6 will wire: resolve, fetch (T-048's fixture
    injection standing in for production fetch), seed."""
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    pid, eid, mid = ids.new_id('project'), ids.new_id('execution'), mid or ids.new_id('mission')
    name, base = LocalNode.resolve_base(str(proj), 'archeus/' + mid, workdirs=())
    LocalNode.store_fetch(pid, str(proj), name, base, 'refs/archeus/exec/%s/seed' % eid,
                          workdirs=())
    return pid, eid, base, 'archeus/%s.t1' % mid


def test_a_seed_holds_exactly_the_tree_and_runs_nothing_the_world_configures(world, monkeypatch):
    proj, head, files = _project(world)
    _hostile(monkeypatch, world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    assert base == head
    work = LocalNode.seed_workspace(pid, eid, base, branch, workdirs=())
    assert work == paths.ExecPaths(eid).work and not os.path.exists(paths.seed_staging(eid))
    for path, (mode, data) in files.items():
        p = os.path.join(work, *path.split('/'))
        st = os.lstat(p)
        assert stat.S_ISREG(st.st_mode) and st.st_nlink == 1, path
        assert not getattr(st, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        with open(p, 'rb') as f:
            assert f.read() == data, path        # no smudge, eol, encoding or LFS
    sub = os.path.join(work, 'sub')
    assert os.path.isdir(sub) and os.listdir(sub) == []             # a gitlink: empty
    dot = os.path.join(work, '.git')
    assert sorted(os.listdir(dot)) == sorted(local._SEED_META)
    with open(os.path.join(dot, 'shallow'), 'rb') as f:
        assert f.read() == base.encode() + b'\n'
    with open(os.path.join(dot, 'HEAD'), 'rb') as f:
        assert f.read() == b'ref: refs/heads/%s\n' % branch.encode()
    with open(os.path.join(dot, 'config'), 'rb') as f:
        assert f.read() == local.SEED_CONFIG
    # the execution's own Git sees exactly the seed, links and gitlink included
    assert world.git(work, 'rev-parse', 'HEAD') == base
    stage = world.git(work, 'ls-files', '-s', 'link', 'sub', 'run.sh').splitlines()
    assert [x.split()[0] for x in stage] == ['120000', '100755', '160000']
    assert world.fired() == []
    # no Core Git once the workspace exists: the pinned runner refuses it there
    spawned = _spy(monkeypatch)
    with pytest.raises(StoreError, match='execution area'):
        LocalNode.store_git('seed', ['rev-parse', 'HEAD'], workdirs=(), git_dir=dot)
    assert spawned == []
    # positive controls: the same tree checked out unpinned under the same world
    world.git(world.tmp, 'clone', '-q', str(proj), str(world.tmp / 'ctl'), env=world.hostile,
              check=False)
    assert {'g-smudge', 'e-post-checkout'} <= set(world.fired())
    with open(str(world.tmp / 'ctl' / 'crlf.txt'), 'rb') as f:
        assert f.read() == b'a\r\nb\r\n'                       # eol=crlf would have applied


def _other(world, proj, head):
    return _bgit(proj, 'commit-tree', head + '^{tree}', '-p', head, '-m', 'other',
                 env=world.clean)


def test_a_mission_branch_is_the_base_when_it_resolves(world):
    proj, head, _files = _project(world)
    mid, other = ids.new_id('mission'), _other(world, proj, head)
    (proj / '.git' / 'refs' / 'heads' / 'archeus').mkdir()
    (proj / '.git' / 'refs' / 'heads' / 'archeus' / mid).write_bytes(other.encode() + b'\n')
    assert LocalNode.resolve_base(str(proj), 'archeus/' + mid, workdirs=()) == (
        'refs/heads/archeus/' + mid, other)
    assert LocalNode.resolve_base(str(proj), 'archeus/' + ids.new_id('mission'),
                                  workdirs=()) == ('HEAD', head)


def test_a_detached_head_is_the_commit_it_names(world):
    proj, head, _files = _project(world)
    other = _other(world, proj, head)
    (proj / '.git' / 'HEAD').write_bytes(other.encode() + b'\n')
    assert LocalNode.resolve_base(str(proj), 'archeus/' + ids.new_id('mission'),
                                  workdirs=()) == ('HEAD', other)


def test_an_unborn_head_or_a_root_that_is_no_repository_is_refused(world):
    empty = world.tmp / 'empty'
    world.git(world.tmp, 'init', '-q', str(empty))
    plain = world.tmp / 'plain'
    plain.mkdir()
    for root in (empty, plain):
        with pytest.raises(OSError):
            LocalNode.resolve_base(str(root), 'archeus/' + ids.new_id('mission'), workdirs=())


def test_a_retry_points_its_own_seed_ref_at_a_commit_already_in_the_store(world, monkeypatch):
    proj, head, files = _project(world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    retry = ids.new_id('execution')
    assert LocalNode.store_seed_ref(pid, retry, base, workdirs=()) == base
    assert LocalNode.store_seed_ref(pid, retry, base, workdirs=()) == base     # idempotent
    with pytest.raises(StoreError, match='names'):
        LocalNode.store_seed_ref(pid, retry, world.c1, workdirs=())          # never moved
    work = LocalNode.seed_workspace(pid, retry, base, branch, workdirs=())
    with open(os.path.join(work, 'bin.dat'), 'rb') as f:
        assert f.read() == BINARY


def _refused(pid, eid, base, branch, match):
    store = paths.repo_store(pid)
    refs = _snapshot(os.path.join(store, 'refs'))
    with pytest.raises(OSError, match=match):
        LocalNode.seed_workspace(pid, eid, base, branch, workdirs=())
    assert not os.path.exists(paths.ExecPaths(eid).work)                  # nothing published
    assert _snapshot(os.path.join(store, 'refs')) == refs                 # no store ref moved


@pytest.mark.parametrize('which', ['work', 'stage'])
def test_an_existing_target_or_staging_directory_is_refused_and_left_as_it_is(world,
                                                                              monkeypatch,
                                                                              which):
    proj, _head, _files = _project(world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    there = paths.ExecPaths(eid).work if which == 'work' else paths.seed_staging(eid)
    os.makedirs(there)
    with open(os.path.join(there, 'mine'), 'wb') as f:
        f.write(b'x')
    before = _snapshot(there)
    with pytest.raises(StoreError, match='already exists'):
        LocalNode.seed_workspace(pid, eid, base, branch, workdirs=())
    assert _snapshot(there) == before


@pytest.mark.parametrize('bound', ['SEED_MAX_ENTRIES', 'SEED_MAX_BYTES', 'SEED_MAX_DEPTH',
                                   'SEED_MAX_PATH'])
def test_a_bounds_breach_refuses_before_anything_is_written(world, monkeypatch, bound):
    proj, _head, _files = _project(world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    small = {'SEED_MAX_ENTRIES': 3, 'SEED_MAX_BYTES': 10, 'SEED_MAX_DEPTH': 2,
             'SEED_MAX_PATH': len(paths.ExecPaths(eid).work) + 8}[bound]
    monkeypatch.setattr(local, bound, small)
    _refused(pid, eid, base, branch, 'past|too deep')
    assert not os.path.exists(paths.seed_staging(eid))                   # not even staging


@pytest.mark.parametrize('path', ['.GIT', 'git~1', 'CON', 'aux.txt', 'x:y', 'trail.',
                                  'back\\slash'])
def test_an_unsafe_path_in_the_base_refuses_the_seed(world, monkeypatch, path):
    proj, _head, _files = _project(world, extra=[('100644', path, b'evil\n')])
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    _refused(pid, eid, base, branch, 'does not seed')
    assert not os.path.exists(paths.seed_staging(eid))


def test_a_case_collision_in_the_base_refuses_the_seed(world, monkeypatch):
    proj, _head, _files = _project(world, extra=[('100644', 'Readme.md', b'1\n'),
                                                 ('100644', 'README.md', b'2\n')])
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    _refused(pid, eid, base, branch, 'case-insensitive')


def test_a_tampered_staging_file_refuses_the_rename_and_staging_is_kept(world, monkeypatch):
    """One byte changed after Core wrote it, same size: equal totals would pass it."""
    proj, _head, _files = _project(world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    real = local._seed_walk

    def tamper(top, *a):
        p = os.path.join(top, 'crlf.txt')
        with open(p, 'r+b') as f:
            f.write(b'X')
        return real(top, *a)
    monkeypatch.setattr(local, '_seed_walk', tamper)
    _refused(pid, eid, base, branch, 'differs from its tree')
    assert os.path.isdir(paths.seed_staging(eid))                            # kept


def test_a_seed_whose_ref_names_another_commit_is_refused(world, monkeypatch):
    proj, _head, _files = _project(world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    LocalNode.store_fetch(pid, str(world.user), 'refs/heads/main', world.c2,
                          'refs/archeus/exec/x/c2', workdirs=())
    _refused(pid, eid, world.c2, branch, 'does not name')


def test_a_junction_planted_in_staging_refuses_the_rename(world, monkeypatch, tmp_path):
    proj, _head, _files = _project(world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    real = local._seed_walk

    def plant(top, *a):
        (tmp_path / 'outside').mkdir()
        _junction(os.path.join(top, 'dir', 'j'), tmp_path / 'outside')
        return real(top, *a)
    monkeypatch.setattr(local, '_seed_walk', plant)
    _refused(pid, eid, base, branch, 'alias')
    assert os.path.isdir(paths.seed_staging(eid))                            # kept


def test_an_index_that_is_not_the_manifest_refuses_the_rename(world, monkeypatch):
    """`read-tree --empty` in place of the seed's tree: HEAD still names the seed,
    so only the ls-files check can see the index is not the tree."""
    proj, _head, _files = _project(world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    real = LocalNode.store_git

    def empty_index(mode, args, **kw):
        if args[:1] == ['read-tree']:
            args = ['read-tree', '--empty']
        return real(mode, args, **kw)
    monkeypatch.setattr(LocalNode, 'store_git', staticmethod(empty_index))
    _refused(pid, eid, base, branch, 'seed index')


def test_a_head_tree_that_is_not_the_seeds_refuses_the_rename(world, monkeypatch):
    proj, _head, _files = _project(world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    real = LocalNode.store_git

    def other_tree(mode, args, **kw):
        if mode == 'seed' and args == ['rev-parse', 'HEAD^{tree}']:
            return 'f' * 40 + '\n'
        return real(mode, args, **kw)
    monkeypatch.setattr(LocalNode, 'store_git', staticmethod(other_tree))
    _refused(pid, eid, base, branch, 'seed index')



# ── T-066 CHANGES r1: the one deadline reaches publication; a failed blob closes ──

def _late_clock(monkeypatch):
    """The seed's clock: real time plus an offset the test moves."""
    offset = [0.0]
    monkeypatch.setattr(local, '_clock', lambda: time.monotonic() + offset[0])
    return offset


@pytest.mark.parametrize('when', ['during-walk', 'during-final-parent', 'after-final-parent'])
def test_a_seed_late_at_its_last_checks_is_refused_and_never_published(world, monkeypatch,
                                                                       when):
    """The clock is past the deadline only while the step named runs (or, for
    the last, from then on), so only that step's own check can see it."""
    proj, _head, _files = _project(world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    offset, late = _late_clock(monkeypatch), 10.0 * local.SEED_DEADLINE
    name = '_seed_walk' if when == 'during-walk' else '_made'
    real = getattr(local, name)

    def step(*a):
        final = name == '_seed_walk' or a[0] == paths.archeus_home()
        if final and when != 'after-final-parent':
            offset[0] = late
            try:
                return real(*a)
            finally:
                offset[0] = 0.0
        out = real(*a)
        if final:
            offset[0] = late
        return out
    monkeypatch.setattr(local, name, step)
    _refused(pid, eid, base, branch, 'past its deadline')
    assert os.path.isdir(paths.seed_staging(eid))                            # kept


def test_a_blob_write_that_fails_leaves_nothing_open_or_published(world, monkeypatch):
    proj, _head, _files = _project(world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    files, real_open = [], open

    def opening(path, mode='r', *a, **k):
        f = real_open(path, mode, *a, **k)
        if 'x' in mode:
            files.append(f)
            if len(files) == 3:
                def full(data):
                    raise OSError('no space left on the device')
                f.write = full
        return f
    monkeypatch.setattr(local, 'open', opening, raising=False)
    _refused(pid, eid, base, branch, 'no space left')
    assert len(files) == 3 and all(f.closed for f in files)
    assert os.path.isdir(paths.seed_staging(eid))                            # kept



# ── K3 (T-067, T-051 + C-1013-T051): the import, with real Git in pytest temp ──

def _seeded(world, monkeypatch):
    proj, head, files = _project(world)
    pid, eid, base, branch = _seed(world, monkeypatch, proj)
    work = LocalNode.seed_workspace(pid, eid, base, branch, workdirs=())
    return pid, eid, base, work, files


def _tree_of(pid, rev):
    out = LocalNode.store_read(pid, ['ls-tree', '-r', '-z', '-l', '--full-tree', rev],
                               workdirs=())
    rows = {}
    for rec in out.split('\0'):
        if rec:
            head, path = rec.split('\t', 1)
            mode, _kind, oid, _size = head.split()
            rows[path] = (mode, oid)
    return rows


def test_an_import_is_exactly_the_workspace_on_its_seed_and_runs_nothing(world, monkeypatch):
    """Edits, a new file, a deletion and an emptied directory, in a workspace whose
    own .git is hostile; links and the gitlink untouched. Nothing the workspace or
    the world configures runs, and the tree is exactly what was on disk."""
    pid, eid, base, work, files = _seeded(world, monkeypatch)
    _hostile(monkeypatch, world)
    dot = os.path.join(work, '.git')
    with open(os.path.join(dot, 'config'), 'ab') as f:
        f.write(('[core]\n\tfsmonitor = %s\n[filter "cl"]\n\tclean = %s\n'
                 % (world.cmd('w-fsmonitor'), world.cmd('w-clean'))).encode())
    os.makedirs(os.path.join(dot, 'hooks'))
    with open(os.path.join(dot, 'hooks', 'post-commit'), 'w') as f:
        f.write('#!/bin/sh\n%s\n' % world.cmd('w-hook'))
    os.makedirs(os.path.join(dot, 'refs', 'replace'))
    with open(os.path.join(work, '.gitattributes'), 'wb') as f:
        f.write(b'* filter=cl text eol=crlf\n')
    new = b'\x00\xff\xfe invalid utf-8 \x80\r\n'
    with open(os.path.join(work, 'new.bin'), 'wb') as f:
        f.write(new)
    with open(os.path.join(work, 'crlf.txt'), 'wb') as f:
        f.write(b'changed\n')
    os.remove(os.path.join(work, 'dir', 'nested', 'deep.txt'))       # dir/nested now empty
    os.remove(os.path.join(work, 'run.sh'))
    got = LocalNode.import_workspace(pid, eid, base, workdirs=())
    assert world.fired() == []
    tree = _tree_of(pid, got['revision'])
    seed = _tree_of(pid, base)
    assert tree['link'] == seed['link'] and tree['link'][0] == '120000'
    assert tree['dir/up'] == seed['dir/up']
    assert tree['sub'] == ('160000', world.c1)                # a gitlink kept by its id
    assert tree['bin.dat'] == seed['bin.dat'] and tree['bin.dat'][0] == '100644'
    assert 'run.sh' not in tree and 'dir/nested/deep.txt' not in tree
    assert tree['new.bin'][0] == '100644'
    with open(os.path.join(work, 'new.bin'), 'rb') as f:
        assert hashlib.sha1(b'blob %d\0' % len(new) + f.read()).hexdigest() == tree['new.bin'][1]
    assert tree['crlf.txt'][1] == hashlib.sha1(b'blob 8\0changed\n').hexdigest()
    assert set(tree) == set(seed) - {'run.sh', 'dir/nested/deep.txt'} | {'new.bin'}
    assert (got['deleted'], got['dropped_dirs']) == (2, 1)
    assert 'A new.bin' in got['files_changed'] and 'D run.sh' in got['files_changed']
    parents = LocalNode.store_read(pid, ['rev-parse', got['revision'] + '^@'], workdirs=())
    assert parents.split() == [base]
    assert LocalNode.store_read(pid, ['rev-parse', got['revision'] + '^{tree}'],
                                workdirs=()).strip() == got['tree']
    # the import ref is written once
    with pytest.raises(StoreError, match='written once'):
        LocalNode.import_workspace(pid, eid, base, workdirs=())
    # the controls: the workspace's own config does fire under unpinned Git
    world.git(work, 'status', env=world.clean, check=False)
    assert 'w-fsmonitor' in world.fired()


def test_an_unchanged_workspace_imports_as_its_seed_tree(world, monkeypatch):
    pid, eid, base, work, _files = _seeded(world, monkeypatch)
    got = LocalNode.import_workspace(pid, eid, base, workdirs=())
    assert got['tree'] == LocalNode.store_read(pid, ['rev-parse', base + '^{tree}'],
                                               workdirs=()).strip()
    assert (got['deleted'], got['dropped_dirs'], got['files_changed']) == (0, 0, [])


@pytest.mark.parametrize('case', ['link-edited', 'link-now-a-dir', 'gitlink-filled',
                                  'gitlink-git', 'gitlink-now-a-file', 'nested-git',
                                  'hard-link'])
def test_a_refused_import_writes_no_ref_and_keeps_the_workspace(world, monkeypatch, tmp_path,
                                                                case):
    pid, eid, base, work, _files = _seeded(world, monkeypatch)
    j = lambda *p: os.path.join(work, *p)         # noqa: E731
    if case == 'link-edited':
        with open(j('link'), 'wb') as f:
            f.write(b'/etc/passwd')
    elif case == 'link-now-a-dir':
        os.remove(j('link'))
        os.mkdir(j('link'))
    elif case == 'gitlink-filled':
        with open(j('sub', 'x'), 'wb') as f:
            f.write(b'x')
    elif case == 'gitlink-git':
        os.mkdir(j('sub', '.git'))
    elif case == 'gitlink-now-a-file':
        os.rmdir(j('sub'))
        with open(j('sub'), 'wb') as f:
            f.write(b'')
    elif case == 'nested-git':
        os.makedirs(j('dir', '.GIT'))
    else:
        os.link(j('crlf.txt'), str(tmp_path / 'outside'))
    before = _snapshot(work)
    with pytest.raises(OSError):
        LocalNode.import_workspace(pid, eid, base, workdirs=())
    assert _snapshot(work) == before
    with pytest.raises(StoreError):
        LocalNode.store_read(pid, ['rev-parse', '--verify', '-q',
                                   'refs/archeus/exec/%s/import' % eid], workdirs=())


def test_a_stream_cut_short_commits_nothing_and_the_store_still_opens(world, monkeypatch):
    """A file that changes after the walk stops the stream before `done`: fast-import
    is killed, no ref is written, and what it leaves is recorded here."""
    pid, eid, base, work, _files = _seeded(world, monkeypatch)
    store = paths.repo_store(pid)
    before = _snapshot(store)
    real = local._import_plan

    def changed_after(work_, seed, deadline):
        plan, counts = real(work_, seed, deadline)
        with open(os.path.join(work_, 'crlf.txt'), 'ab') as f:
            f.write(b'more')
        return plan, counts
    monkeypatch.setattr(local, '_import_plan', changed_after)
    with pytest.raises(StoreError, match='changed after the walk'):
        LocalNode.import_workspace(pid, eid, base, workdirs=())
    with pytest.raises(StoreError):
        LocalNode.store_read(pid, ['rev-parse', '--verify', '-q',
                                   'refs/archeus/exec/%s/import' % eid], workdirs=())
    left = sorted(set(_snapshot(store)) - set(before))
    print('\nK3 a cut fast-import left: %s' % left)
    assert LocalNode.store_open(pid, workdirs=()) == store          # still opens


def test_a_bound_breached_by_the_workspace_refuses_before_the_writer_starts(world,
                                                                            monkeypatch):
    pid, eid, base, work, _files = _seeded(world, monkeypatch)
    with open(os.path.join(work, 'big'), 'wb') as f:
        f.write(b'x' * 64)
    monkeypatch.setattr(local, 'SEED_MAX_BYTES', 40)
    started = []
    real = local._stream
    monkeypatch.setattr(local, '_stream', lambda argv, *a: (started.append(argv[-3:]),
                                                           real(argv, *a))[1])
    with pytest.raises(StoreError, match='past 40 bytes'):
        LocalNode.import_workspace(pid, eid, base, workdirs=())
    assert not any('fast-import' in a for a in started)



@pytest.mark.parametrize('how', ['tree', 'parent'])
def test_a_commit_that_is_not_what_core_sent_is_never_returned(world, monkeypatch, how):
    """Core's read-back, not fast-import's word: the stream is altered between what
    Core records as sent and what reaches Git, and the import is refused."""
    pid, eid, base, work, _files = _seeded(world, monkeypatch)
    real = local._import_stream

    def altered(execution_id, seed_revision, plan, deadline, sent):
        for chunk in real(execution_id, seed_revision, plan, deadline, sent):
            if how == 'parent':
                chunk = chunk.replace(b'from %s\n' % seed_revision.encode(), b'')
            yield chunk
        if how == 'tree':
            sent['ghost.txt'] = ('100644', 'e' * 40)
    monkeypatch.setattr(local, '_import_stream', altered)
    with pytest.raises(StoreError, match='is not what Core sent'):
        LocalNode.import_workspace(pid, eid, base, workdirs=())
