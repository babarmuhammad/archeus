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


@pytest.fixture(autouse=True)
def fresh_git():
    local._git_exe.cache_clear()
    local._git_version.cache_clear()
    yield
    local._git_exe.cache_clear()
    local._git_version.cache_clear()


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
        # the source repository's OWN config: an include to hooks, an fsmonitor
        (tmp / 'local-inc.cfg').write_text('[core]\n\thooksPath = %s\n' % _fwd(tmp / 'hooks-l'))
        self.git(self.user, 'config', 'include.path', _fwd(tmp / 'local-inc.cfg'))
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
    local._pin_files()
    v = local._git_version()
    print('\nK1 git: %s | %s | floor %s' % (local._git_exe(), v,
                                            '.'.join(map(str, STORE_GIT_FLOOR))))
    assert os.path.isabs(local._git_exe())
    assert os.listdir(os.path.join(paths.repos_dir(), '.pin', 'empty')) == []


def test_a_store_is_created_bare_sealed_and_recorded(world):
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid)
    assert store == paths.repo_store(pid)
    pin = os.path.join(paths.repos_dir(), '.pin')
    with open(os.path.join(store, 'HEAD')) as f:
        assert f.read() == STORE_HEAD
    with open(os.path.join(store, 'config')) as f:
        assert 'bare = true' in f.read()
    for absent in ('hooks', 'info', 'description', 'commondir', 'config.worktree',
                   os.path.join('objects', 'info', 'alternates')):
        assert not os.path.exists(os.path.join(store, absent)), absent
    import json
    with open(os.path.join(pin, pid + '.json')) as f:
        rec = json.load(f)
    assert rec['git'] == local._git_exe() and rec['empty_tree'] == EMPTY_TREE
    assert os.path.exists(os.path.join(pin, pid + '.owned'))
    assert LocalNode.store_read(pid, ['cat-file', '-t', EMPTY_TREE]).strip() == 'tree'
    assert LocalNode.store_open(pid) == store                      # reopening is checking
    assert world.fired() == []


@pytest.mark.parametrize('plant', ['alternates', 'attributes', 'config', 'hook', 'head'])
def test_a_store_changed_after_its_seal_is_refused(world, plant):
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid)
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
        LocalNode.store_open(pid)
    with pytest.raises(StoreError):
        LocalNode.store_read(pid, ['rev-parse', '--verify', '-q', EMPTY_TREE])


def test_a_crash_between_init_and_seal_is_sealed_on_the_next_open(world, monkeypatch):
    pid = ids.new_id('project')
    real = LocalNode.store_git

    def crash(mode, args, **kw):
        if mode == 'seal':
            raise StoreError('crashed before the seal')
        return real(mode, args, **kw)
    monkeypatch.setattr(LocalNode, 'store_git', staticmethod(crash))
    with pytest.raises(StoreError, match='crashed'):
        LocalNode.store_open(pid)
    assert os.path.isdir(paths.repo_store(pid))
    monkeypatch.setattr(LocalNode, 'store_git', staticmethod(real))
    assert LocalNode.store_open(pid) == paths.repo_store(pid)


def test_a_sealed_store_whose_record_is_lost_is_refused_once_it_holds_refs(world, monkeypatch):
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    pid = ids.new_id('project')
    LocalNode.store_fetch(pid, str(world.user), 'refs/heads/main', world.c2,
                          'refs/archeus/exec/e1/seed')
    os.remove(os.path.join(paths.repos_dir(), '.pin', pid + '.json'))
    with pytest.raises(StoreError, match='holds refs'):
        LocalNode.store_open(pid)


def test_the_pinned_store_runs_nothing_the_world_configures(world, monkeypatch):
    """The pinned path, end to end, under every hazard at once; then each hazard
    fires without the pin (the positive controls)."""
    _hostile(monkeypatch, world)
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid)
    ref = 'refs/archeus/exec/e1/seed'
    assert LocalNode.store_fetch(pid, str(world.user), 'refs/heads/main', world.c2, ref) == world.c2
    read = lambda *a: LocalNode.store_read(pid, list(a))
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
    assert LocalNode.store_resolve_base(str(world.user), 'refs/heads/main') == world.c2
    assert world.fired() == []                                    # the pinned path: nothing

    # positive controls: the same hazards, unpinned, each fire
    h, u, scratch = world.hostile, world.user, world.tmp / 'scratch'
    world.git(world.tmp, 'init', '-q', str(scratch))
    world.git(scratch, 'commit', '-q', '--allow-empty', '-m', 'x', env=h)
    assert 'e-post-commit' in world.fired()        # command scope outranks the include
    world.git(scratch, 'commit', '-q', '--allow-empty', '-m', 'y',
              env=dict(h, GIT_CONFIG_COUNT='0'))                       # the include alone
    assert 'g-post-commit' in world.fired()
    world.git(u, 'commit', '-q', '--allow-empty', '-m', 'z')             # the repo's own include
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
                              'refs/archeus/exec/e1/seed')
    read = lambda *a: LocalNode.store_read(pid, list(a))
    assert read('rev-parse', 'refs/archeus/incoming/exec/e1/seed').strip() == world.c2
    with pytest.raises(StoreError):
        read('rev-parse', '--verify', '-q', 'refs/archeus/exec/e1/seed')
    assert world.fired() == []


def test_the_file_protocol_pin_governs_a_plain_local_path(world, monkeypatch):
    """GIT_ALLOW_PROTOCOL=file is what lets a fetch from a plain path through: the
    same pinned call with only `ext` allowed is refused."""
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    pid = ids.new_id('project')
    store = LocalNode.store_open(pid)
    argv, env, cwd = local._store_pin('trusted', store)
    fetch = argv + ['fetch', '--no-tags', '--no-write-fetch-head', str(world.user),
                    '+refs/heads/main:refs/archeus/incoming/probe']
    r = subprocess.run(fetch, cwd=cwd, env=dict(env, GIT_ALLOW_PROTOCOL='ext'),
                       capture_output=True, text=True)
    assert r.returncode != 0 and 'transport' in r.stderr.lower(), r.stderr
    r = subprocess.run(fetch, cwd=cwd, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
