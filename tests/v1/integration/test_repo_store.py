"""PV-20 K1 (T-048): the Core-owned store with real Git, in pytest-owned temp only.

Each hazard is a sentinel: a hook, filter, driver or upload-pack hook that
creates a file in `sent/` when Git runs it. The pinned operations run first,
under a hostile world (global config, an include, environment config, the
source repository's own config), and must leave `sent/` empty; then each
hazard is fired once WITHOUT the pin, so an empty `sent/` is evidence and not a
sentinel that could never fire. The user repository is a temp fixture: no real
repository, installed runtime or network is touched."""

import os
import shutil
import subprocess
import sys

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
            + '[filter "sent"]\n\tclean = %s\n\tsmudge = %s\n' % (self.cmd('g-clean'),
                                                                 self.cmd('g-smudge'))
            + '[uploadpack]\n\tpackObjectsHook = %s\n' % self.cmd('g-packhook'))
        #: the world a Core process could inherit: global config with an include,
        #: and command-scope config from the environment
        self.hostile = dict(base, HOME=str(home), XDG_CONFIG_HOME=str(home),
                            GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_COUNT='1',
                            GIT_CONFIG_KEY_0='core.hooksPath',
                            GIT_CONFIG_VALUE_0=_fwd(tmp / 'hooks-e'))
        self.user = tmp / 'user'
        self.git(self.tmp, 'init', '-q', '-b', 'main', str(self.user))
        (self.user / '.gitattributes').write_text('a.txt diff=sent filter=sent\nb.txt diff=tc\n')
        (self.user / 'a.txt').write_text('one\n')
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
    assert read('ls-tree', '--name-only', ref).split() == ['.gitattributes', 'a.txt', 'b.txt']
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

    # positive controls: the same hazards, unpinned, each fire
    h, u, scratch = world.hostile, world.user, world.tmp / 'scratch'
    world.git(world.tmp, 'init', '-q', str(scratch))
    world.git(scratch, 'commit', '-q', '--allow-empty', '-m', 'x', env=h)
    assert 'e-post-commit' in world.fired()        # command scope outranks the include
    world.git(scratch, 'commit', '-q', '--allow-empty', '-m', 'y',
              env=dict(h, GIT_CONFIG_COUNT='0'))                       # the include alone
    assert 'g-post-commit' in world.fired()
    world.git(u, 'commit', '-q', '--allow-empty', '-m', 'z')             # the repo's own hooksPath
    assert 'l-post-commit' in world.fired()
    world.git(u, 'diff', world.c1, world.c2, env=h)                       # driver and textconv
    assert {'g-extdiff', 'g-textconv'} <= set(world.fired())
    (u / 'a.txt').write_text('three\n')
    world.git(u, 'add', 'a.txt', env=h)                                   # clean filter
    assert 'g-clean' in world.fired()
    world.git(u, 'status', env=dict(h, GIT_CONFIG_COUNT='0'), check=False)  # fsmonitor
    assert 'l-fsmonitor' in world.fired() or 'g-fsmonitor' in world.fired()
    world.git(world.tmp, 'init', '-q', '--bare', str(world.tmp / 'scratch.git'))
    world.git(world.tmp / 'scratch.git', 'fetch', '-q', str(u), 'refs/heads/main:refs/x',
              env=dict(h, GIT_CONFIG_COUNT='0'), check=False)                 # source side
    assert 'g-packhook' in world.fired()
    unpinned = world.git(world.tmp, '--git-dir', store, 'cat-file', '-p', world.a2)
    assert unpinned == 'bee'                                               # the replace ref
    print('\nK1 controls fired unpinned: %s' % world.fired())


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


def _files(top):
    return sorted(os.path.join(d, f) for d, _s, fs in os.walk(str(top)) for f in fs)


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
    before = _files(outside)
    with pytest.raises(OSError, match='alias|plain'):
        LocalNode.store_open(pid, workdirs=())
    assert _files(outside) == before and not any(EMPTY_TREE[2:] in f for f in _files(outside))
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
    _both_refused(world.user, (), 'an include Core does not follow')
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
