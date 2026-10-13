"""PV-20 K1 (T-048): the Core-owned store's one pin, with no process started.

Every Git call here is answered by a fake `proc.run` that records argv, env and
cwd; a refusal is asserted together with zero calls. Real Git runs only in
tests/v1/integration/test_repo_store.py."""

import ast
import os
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.infra import paths
from archeus.node import local
from archeus.node.local import EMPTY_TREE, LocalNode, StoreError

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
GIT = os.path.abspath(os.path.join(os.sep, 'fake', 'git', 'cmd', 'git.exe'))
PINS = ('core.fsmonitor=false', 'submodule.recurse=false', 'gc.auto=0', 'maintenance.auto=false')
ALLOWED_ENV = {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH', 'HOME', 'XDG_CONFIG_HOME',
               'GIT_CONFIG_NOSYSTEM', 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_SYSTEM',
               'GIT_TERMINAL_PROMPT', 'GIT_ALLOW_PROTOCOL', 'GIT_PROTOCOL_FROM_USER',
               'GIT_CEILING_DIRECTORIES'}


class Spawns:
    """`proc.run` answered in-process: the call is recorded, never started."""

    def __init__(self, version='git version 2.47.1.windows.1\n'):
        self.calls, self.version = [], version

    def __call__(self, argv, *, cwd=None, env=None, timeout=30, stdin=None, check=False):
        self.calls.append(SimpleNamespace(argv=argv, cwd=cwd, env=env))
        out = self.version if argv[-1] == 'version' else ''
        return SimpleNamespace(returncode=0, stdout=out, stderr='')


@pytest.fixture(autouse=True)
def spawns(monkeypatch):
    local._git_exe.cache_clear()
    local._git_version.cache_clear()
    monkeypatch.setattr(local.shutil, 'which', lambda name: GIT)
    s = Spawns()
    monkeypatch.setattr(local.proc, 'run', s)
    yield s
    local._git_exe.cache_clear()
    local._git_version.cache_clear()


def _pin():
    pin = os.path.join(paths.repos_dir(), '.pin')
    return pin, os.path.join(pin, 'empty'), os.path.join(pin, 'empty.cfg')


def test_every_mode_runs_one_absolute_git_under_the_whole_pin():
    pin, empty, cfg = _pin()
    store = paths.repo_store(ids.new_id('project'))
    for mode, git_dir in (('version', None), ('init', None), ('seal', store),
                          ('trusted', store), ('base', store)):
        argv, env, cwd = local._store_pin(mode, git_dir)
        assert argv[0] == GIT and os.path.isabs(argv[0])
        cs = [argv[i + 1] for i, a in enumerate(argv) if a == '-c']
        assert set(cs) == set(PINS) | {'core.hooksPath=' + empty, 'core.attributesFile=' + cfg}
        assert (env['HOME'], env['XDG_CONFIG_HOME']) == (empty, empty)
        assert (env['GIT_CONFIG_GLOBAL'], env['GIT_CONFIG_SYSTEM']) == (cfg, cfg)
        assert env['GIT_CONFIG_NOSYSTEM'] == '1' and env['GIT_ALLOW_PROTOCOL'] == 'file'
        assert env['PATH'] == os.path.dirname(GIT)
        if git_dir is None:
            assert '--git-dir' not in argv and '--attr-source' not in argv
            assert env['GIT_CEILING_DIRECTORIES'] == paths.repos_dir()
            assert cwd == (empty if mode == 'version' else paths.repos_dir())
        else:
            assert argv[argv.index('--git-dir') + 1] == store and cwd == store
            assert '--no-replace-objects' in argv
            assert ('--attr-source' in argv) == (mode == 'trusted')
    argv, _env, _cwd = local._store_pin('trusted', store)
    assert argv[argv.index('--attr-source') + 1] == EMPTY_TREE


def test_nothing_inherited_steers_the_child(monkeypatch):
    for k, v in (('GIT_DIR', 'x'), ('GIT_WORK_TREE', 'x'), ('GIT_INDEX_FILE', 'x'),
                 ('GIT_OBJECT_DIRECTORY', 'x'), ('GIT_ALTERNATE_OBJECT_DIRECTORIES', 'x'),
                 ('GIT_CONFIG_COUNT', '1'), ('GIT_CONFIG_KEY_0', 'core.hooksPath'),
                 ('GIT_CONFIG_VALUE_0', 'x'), ('GIT_CONFIG_PARAMETERS', "'core.hooksPath'='x'"),
                 ('GIT_EXTERNAL_DIFF', 'x'), ('GIT_SSH_COMMAND', 'x'), ('GIT_EXEC_PATH', 'x'),
                 ('GIT_ATTR_SOURCE', 'x'), ('GIT_ASKPASS', 'x'), ('GIT_TRACE', '1'),
                 ('PYTEST_SOMETHING', 'x'), ('HOME', 'x'), ('XDG_CONFIG_HOME', 'x'),
                 ('PATH', 'x')):
        monkeypatch.setenv(k, v)
    _pin_, empty, _cfg = _pin()
    for mode, git_dir in (('version', None), ('trusted', paths.repo_store(ids.new_id('project')))):
        _argv, env, _cwd = local._store_pin(mode, git_dir)
        assert set(env) <= ALLOWED_ENV, set(env) - ALLOWED_ENV
        assert env['HOME'] == empty and env['PATH'] == os.path.dirname(GIT)


@pytest.mark.parametrize('where', ['work', 'state', 'exec', 'run', 'worktree'])
def test_a_store_call_in_an_execution_area_is_refused_before_a_spawn(spawns, where):
    e = paths.ExecPaths(ids.new_id('execution'))
    path = {'work': e.work, 'state': e.state, 'exec': e.dir, 'run': paths.run_dir(),
            'worktree': os.path.join(paths.archeus_home(), 'worktrees', 'prj', 'msn', 't1')}[where]
    for mode, args in (('seal', ['mktree']), ('trusted', ['rev-parse', 'HEAD']),
                       ('base', ['rev-parse', 'HEAD'])):
        with pytest.raises(StoreError, match='execution area'):
            LocalNode.store_git(mode, args, workdirs=(), git_dir=path)
    assert spawns.calls == []


def test_a_recorded_workdir_is_an_execution_area_wherever_it_lies(spawns, tmp_path):
    """The node has no database: Core passes the workdirs it recorded, and a
    call at or under any of them is refused like one in run/ or worktrees/."""
    wd = str(tmp_path / 'recorded-wd')
    for git_dir in (wd, os.path.join(wd, '.git'), os.path.join(wd, 'a', 'b')):
        with pytest.raises(StoreError, match='execution area'):
            LocalNode.store_git('base', ['rev-parse', 'HEAD'], workdirs=[None, '', wd],
                                git_dir=git_dir)
    with pytest.raises(StoreError, match='execution area'):
        LocalNode.store_open(ids.new_id('project'), workdirs=[paths.repos_dir()])
    with pytest.raises(StoreError, match='a collection'):
        LocalNode.store_git('base', ['rev-parse', 'HEAD'], workdirs=wd, git_dir=wd)
    assert spawns.calls == []
    LocalNode.store_git('base', ['rev-parse', 'HEAD'], workdirs=[wd + '-other'], git_dir=wd)
    assert len(spawns.calls) == 1                       # the control: not recorded, it runs


def _repo(where, gitdir_to=None):
    """A repository root; with *gitdir_to*, its `.git` is a file naming that directory."""
    os.makedirs(where, exist_ok=True)
    if gitdir_to is None:
        os.makedirs(os.path.join(where, '.git'), exist_ok=True)
    else:
        with open(os.path.join(where, '.git'), 'w') as f:
            f.write('gitdir: %s\n' % gitdir_to)
    return str(where)


@pytest.mark.parametrize('case', ['root-in-work', 'root-recorded', 'root-under-recorded',
                                  'root-in-work-gitdir-outside', 'root-recorded-gitdir-outside',
                                  'gitdir-in-state', 'gitdir-in-recorded', 'gitdir-in-worktrees'])
@pytest.mark.parametrize('call', ['base', 'fetch'])
def test_a_root_or_the_git_dir_it_names_in_an_execution_area_is_refused(spawns, monkeypatch,
                                                                        tmp_path, case, call):
    """Class-7 `.git` indirection: the root AND the git directory its `.git`
    names are checked before anything runs."""
    e = paths.ExecPaths(ids.new_id('execution'))
    wd = str(tmp_path / 'recorded-wd')
    root = {'root-in-work': lambda: _repo(e.work),
            'root-recorded': lambda: _repo(wd),
            'root-under-recorded': lambda: _repo(os.path.join(wd, 'sub')),
            'root-in-work-gitdir-outside': lambda: _repo(e.work, str(tmp_path / 'out' / 'g')),
            'root-recorded-gitdir-outside': lambda: _repo(wd, str(tmp_path / 'out' / 'g')),
            'gitdir-in-state': lambda: _repo(tmp_path / 'u1', os.path.join(e.state, 'g')),
            'gitdir-in-recorded': lambda: _repo(tmp_path / 'u2', os.path.join(wd, 'g')),
            'gitdir-in-worktrees': lambda: _repo(tmp_path / 'u3', os.path.join(
                paths.archeus_home(), 'worktrees', 'p', 'm', 't1', '.git'))}[case]()
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(StoreError, match='execution area'):
        if call == 'base':
            LocalNode.store_resolve_base(root, 'refs/heads/main', workdirs=[wd])
        else:
            LocalNode.store_fetch(ids.new_id('project'), root, 'refs/heads/main', '0' * 40,
                                  'refs/archeus/exec/e1/seed', workdirs=[wd])
    assert spawns.calls == []


def test_a_root_and_git_dir_outside_every_area_are_read(spawns, tmp_path):
    root = _repo(tmp_path / 'u', str(tmp_path / 'elsewhere' / 'g'))
    LocalNode.store_resolve_base(root, 'refs/heads/main', workdirs=[str(tmp_path / 'wd')])
    (call,) = [c for c in spawns.calls if c.argv[-1] != 'version']
    assert call.argv[call.argv.index('--git-dir') + 1] == str(tmp_path / 'elsewhere' / 'g')


@pytest.mark.parametrize('mode,args', [('trusted', ['config', '--list']),
                                       ('trusted', ['gc']), ('seal', ['update-ref', 'x', 'y']),
                                       ('base', ['fetch', 'x']), ('version', ['init']),
                                       ('init', ['version']), ('trusted', [])])
def test_a_subcommand_outside_its_mode_is_refused(spawns, mode, args):
    with pytest.raises(StoreError):
        LocalNode.store_git(mode, args, workdirs=(),
                            git_dir=paths.repo_store(ids.new_id('project')))
    with pytest.raises(StoreError, match='not a store read'):
        LocalNode.store_read(ids.new_id('project'), ['update-ref', 'refs/x', 'y'], workdirs=())
    assert spawns.calls == []


@pytest.mark.parametrize('bad', ['../x', 'prj_x', ids.new_id('execution'), '', None])
def test_an_ill_formed_project_id_names_no_store(spawns, bad):
    with pytest.raises(ValueError, match='not a project id'):
        LocalNode.store_open(bad, workdirs=())
    assert spawns.calls == []


@pytest.mark.parametrize('found', [None, os.path.join(os.curdir, 'git.EXE')])
def test_no_absolute_git_means_no_store(spawns, monkeypatch, found):
    monkeypatch.setattr(local.shutil, 'which', lambda name: found)
    with pytest.raises(StoreError, match='no absolute git'):
        LocalNode.store_open(ids.new_id('project'), workdirs=())
    assert spawns.calls == []


@pytest.mark.parametrize('version', ['git version 2.40.9\n', 'git version 1.9.0\n', 'garbage\n',
                                     ''])
def test_an_old_or_unreadable_git_is_refused_after_its_one_version_call(spawns, version):
    spawns.version = version
    pid = ids.new_id('project')
    with pytest.raises(StoreError, match='older than 2.41.0'):
        LocalNode.store_open(pid, workdirs=())
    assert [c.argv[-1] for c in spawns.calls] == ['version']
    assert spawns.calls[0].cwd == _pin()[1]
    assert not os.path.lexists(paths.repo_store(pid))


@pytest.mark.parametrize('which', ['file', 'dir'])
def test_a_pin_file_with_anything_in_it_is_refused(spawns, which):
    _pin_, empty, cfg = _pin()
    os.makedirs(empty)
    with open(cfg, 'wb') as f:
        f.write(b'[core]\n\thooksPath = x\n' if which == 'file' else b'')
    if which == 'dir':
        open(os.path.join(empty, 'post-commit'), 'wb').close()
    with pytest.raises(StoreError, match='not empty'):
        LocalNode.store_open(ids.new_id('project'), workdirs=())
    assert spawns.calls == []


#: what `init --bare` wrote at 2.49.0.windows.1 (pinned by the integration test)
INIT_CONFIG = (b'[core]\n\trepositoryformatversion = 0\n\tfilemode = false\n\tbare = true\n'
               b'\tsymlinks = false\n\tignorecase = true\n')


def _unsealed(pid, config=INIT_CONFIG, claimed=True):
    """A store as `init --bare --template=<empty>` leaves it, claimed by Core,
    before the seal: what a crash between init and seal leaves behind."""
    store = paths.repo_store(pid)
    pin = local._pin_files()
    if claimed:
        open(os.path.join(pin, pid + '.owned'), 'xb').close()
    for d in (('objects', 'info'), ('objects', 'pack'), ('refs', 'heads'), ('refs', 'tags')):
        os.makedirs(os.path.join(store, *d))
    with open(os.path.join(store, 'HEAD'), 'wb') as f:
        f.write(b'ref: refs/heads/master\n')
    with open(os.path.join(store, 'config'), 'wb') as f:
        f.write(config)
    return store, pin


def test_a_store_core_never_claimed_is_refused_not_adopted(spawns):
    pid = ids.new_id('project')
    _unsealed(pid, claimed=False)
    with pytest.raises(StoreError, match='never claimed'):
        LocalNode.store_open(pid, workdirs=())
    assert [c.argv[-1] for c in spawns.calls] == ['version']


def test_an_unsealed_store_with_exactly_the_init_config_is_sealed(spawns):
    pid = ids.new_id('project')
    _unsealed(pid)
    with pytest.raises(StoreError, match='the empty tree is'):    # the fake writes no tree
        LocalNode.store_open(pid, workdirs=())
    assert [c.argv[-1] for c in spawns.calls] == ['version', 'refs/archeus/none', 'mktree']


@pytest.mark.parametrize('config', [
    pytest.param(b'', id='empty'),
    pytest.param(INIT_CONFIG.replace(b'\tbare = true\n', b''), id='missing-bare'),
    pytest.param(INIT_CONFIG.replace(b'\trepositoryformatversion = 0\n', b''),
                 id='missing-format'),
    pytest.param(INIT_CONFIG.replace(b'\tfilemode = false\n', b''), id='missing-filemode'),
    pytest.param(INIT_CONFIG.replace(b'bare = true', b'bare = false'), id='bare-false'),
    pytest.param(INIT_CONFIG.replace(b'version = 0', b'version = 1'), id='format-1'),
    pytest.param(INIT_CONFIG.replace(b'symlinks = false', b'symlinks = true'), id='symlinks-true'),
    pytest.param(INIT_CONFIG + b'\tbare = true\n', id='duplicate-bare'),
    pytest.param(INIT_CONFIG.replace(b'\tbare = true\n', b'\tbare = true\n\tbare = false\n'),
                 id='contradictory-bare'),
    pytest.param(INIT_CONFIG + b'[core]\n\tbare = true\n', id='second-core'),
    pytest.param(INIT_CONFIG + b'[include]\n\tpath = x\n', id='include'),
    pytest.param(INIT_CONFIG + b'\thooksPath = x\n', id='extra-key'),
    pytest.param(INIT_CONFIG + b'\tfsmonitor = x\n', id='fsmonitor'),
    pytest.param(INIT_CONFIG.replace(b'\n', b'\r\n'), id='crlf'),
    pytest.param(INIT_CONFIG.replace(b'\tfilemode = false\n\tbare = true\n',
                                     b'\tbare = true\n\tfilemode = false\n'), id='reordered'),
    pytest.param(INIT_CONFIG[:-1], id='no-final-newline'),
])
def test_an_unsealed_store_is_sealed_only_with_exactly_the_init_config(spawns, config):
    """Core claimed it and a crash came before the seal: only the whole config
    `init --bare` writes is Core's, never a set of individually plausible lines."""
    pid = ids.new_id('project')
    _store, pin = _unsealed(pid, config)
    with pytest.raises(StoreError, match='config Core did not write'):
        LocalNode.store_open(pid, workdirs=())
    assert [c.argv[-1] for c in spawns.calls] == ['version']
    assert not os.path.lexists(os.path.join(pin, pid + '.json'))


def test_an_unsealed_store_that_holds_a_ref_is_refused(spawns):
    pid = ids.new_id('project')
    store, _pin_ = _unsealed(pid)
    with open(os.path.join(store, 'refs', 'heads', 'main'), 'w') as f:
        f.write('0' * 40 + '\n')
    with pytest.raises(StoreError, match='holds refs'):
        LocalNode.store_open(pid, workdirs=())
    assert [c.argv[-1] for c in spawns.calls] == ['version']


@pytest.mark.parametrize('plant', [('hooks', 'post-update'), ('info', 'attributes'),
                                   ('objects', 'info', 'alternates'), ('commondir',),
                                   ('config.worktree',)])
def test_a_store_with_an_execution_point_is_refused(spawns, plant):
    pid = ids.new_id('project')
    store, _pin_ = _unsealed(pid)
    os.makedirs(os.path.join(store, *plant[:-1]), exist_ok=True)
    open(os.path.join(store, *plant), 'wb').close()
    with pytest.raises(StoreError, match='a store with'):
        LocalNode.store_open(pid, workdirs=())
    assert [c.argv[-1] for c in spawns.calls] == ['version']


@pytest.mark.parametrize('which', ['config', 'HEAD', 'owned', 'pin-cfg', 'pack-file'])
def test_a_hard_linked_metadata_file_is_refused_before_it_is_read(spawns, tmp_path, which):
    """Same bytes, another file: a hard link makes a store file somebody else's."""
    pid = ids.new_id('project')
    store, pin = _unsealed(pid)
    path = {'config': os.path.join(store, 'config'), 'HEAD': os.path.join(store, 'HEAD'),
            'owned': os.path.join(pin, pid + '.owned'), 'pin-cfg': os.path.join(pin, 'empty.cfg'),
            'pack-file': os.path.join(store, 'objects', 'pack', 'pack-x.pack')}[which]
    if not os.path.exists(path):
        open(path, 'wb').close()
    os.link(path, str(tmp_path / ('outside-' + which)))
    assert os.lstat(path).st_nlink == 2
    with pytest.raises(OSError, match='hard-linked'):
        LocalNode.store_open(pid, workdirs=())
    assert [c.argv[-1] for c in spawns.calls] in ([], ['version'])


def test_no_environment_or_test_marker_unlocks_a_fetch(spawns, monkeypatch):
    for k in ('PYTEST_CURRENT_TEST', 'ARCHEUS_STORE_FETCH', 'ARCHEUS_REAL_BOUNDARY', 'CI'):
        monkeypatch.setenv(k, '1')
    with pytest.raises(StoreError, match='no fetch into a store'):
        LocalNode.store_fetch(ids.new_id('project'), os.path.abspath(os.sep), 'refs/heads/main',
                              '0' * 40, 'refs/archeus/exec/x/seed', workdirs=())
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', 1)        # truthy is not accepted
    with pytest.raises(StoreError, match='no fetch into a store'):
        LocalNode.store_fetch(ids.new_id('project'), os.path.abspath(os.sep), 'refs/heads/main',
                              '0' * 40, 'refs/archeus/exec/x/seed', workdirs=())
    assert spawns.calls == []


@pytest.mark.parametrize('root,rev,expect,ref', [
    ('relative', 'refs/heads/main', '0' * 40, 'refs/archeus/x'),
    (None, 'refs/heads/main:refs/heads/x', '0' * 40, 'refs/archeus/x'),
    (None, '-uhack', '0' * 40, 'refs/archeus/x'),
    (None, 'refs/heads/../x', '0' * 40, 'refs/archeus/x'),
    (None, 'refs/heads/main', 'HEAD', 'refs/archeus/x'),
    (None, 'refs/heads/main', '0' * 40, 'refs/heads/main'),
])
def test_an_accepted_fetch_still_takes_only_what_core_may_ask(spawns, monkeypatch,
                                                              root, rev, expect, ref):
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(StoreError, match='not a fetch Core may make'):
        LocalNode.store_fetch(ids.new_id('project'), root or os.path.abspath(os.sep), rev,
                              expect, ref, workdirs=())
    assert spawns.calls == []


def test_the_fetch_gate_is_set_in_one_place_and_never_by_production_code():
    hits = []
    for rel, tree in _production_trees():
        for n in ast.walk(tree):
            targets = n.targets if isinstance(n, ast.Assign) else []
            for t in targets:
                name = t.attr if isinstance(t, ast.Attribute) else getattr(t, 'id', None)
                if name == 'store_fetch_accepted':
                    hits.append((rel, ast.unparse(n)))
            if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'setattr' and any(
                    isinstance(a, ast.Constant) and a.value == 'store_fetch_accepted'
                    for a in n.args):
                hits.append((rel, ast.unparse(n)))
    assert hits == [('archeus/node/local.py', 'store_fetch_accepted = False')]


def test_the_store_is_v1s_and_no_reset_names_it(archeus_home):
    assert 'repos' in paths.V1_OWNED
    pid = ids.new_id('project')
    assert paths.repo_store(pid) == os.path.join(str(archeus_home), 'repos', pid + '.git')
    with open(os.path.join(REPO, 'docs', 'architecture', 'migration-plan.md'),
              encoding='utf-8') as f:
        text = f.read()
    reset = text[text.index('To reset V1'):text.index('is **never** deleted')]
    assert '`run/`' in reset and '`repos' not in reset and 'repos/' not in reset


# ── no second store pin (T-046 C2) ──────────────────────────────────────────

#: the literals only the store pin uses; `-c` values by prefix
STORE_KEYS = ('--git-dir', '--attr-source', '--no-replace-objects', 'GIT_CONFIG_GLOBAL',
              'GIT_CONFIG_SYSTEM', 'GIT_ATTR_SOURCE', 'GIT_NO_REPLACE_OBJECTS',
              'GIT_ALLOW_PROTOCOL', 'GIT_PROTOCOL_FROM_USER', 'GIT_CEILING_DIRECTORIES')
STORE_C = ('core.hooksPath=', 'core.fsmonitor=', 'core.attributesFile=', 'gc.auto=',
           'maintenance.auto=', 'submodule.recurse=')
LOCAL = 'archeus/node/local.py'
#: who may call the spawner and the builder (later cards add theirs by name)
CALLERS = {'store_git': ('store_open', 'store_read', 'store_fetch', 'store_resolve_base',
                         '_git_version'),
           '_store_pin': ('store_git',)}


def _store_pin_violations(tree, rel, keys=STORE_KEYS):
    prose = {id(n.value) for n in ast.walk(tree)
             if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    owner = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fn):
                owner.setdefault(id(n), fn.name)       # outermost first: ast.walk is BFS
    out = []
    for n in ast.walk(tree):
        fn = owner.get(id(n))
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in prose:
            v = n.value
            if (v in keys or v.startswith(STORE_C)) and not (rel == LOCAL and fn == '_store_pin'):
                out.append((rel, getattr(n, 'lineno', 0), v))
        if isinstance(n, ast.keyword) and n.arg in keys and not (rel == LOCAL
                                                                 and fn == '_store_pin'):
            out.append((rel, getattr(n, 'lineno', 0), n.arg))       # env.update(KEY=...)
        if isinstance(n, ast.Call):
            name = getattr(n.func, 'attr', None) or getattr(n.func, 'id', None)
            if name in CALLERS and not (rel == LOCAL and fn in CALLERS[name]):
                out.append((rel, n.lineno, name))
            if name == 'join' and any(isinstance(a, ast.Constant) and a.value == 'repos'
                                      for a in n.args) and any(
                    'archeus_home' in ast.unparse(a) or 'ARCHEUS_HOME' in ast.unparse(a)
                    for a in n.args) and not (rel == 'archeus/infra/paths.py'
                                              and fn == 'repos_dir'):
                out.append((rel, n.lineno, 'repos'))
    return out


def _production_trees():
    for top in ('archeus', 'claude_sessions', 'tools'):
        for dirpath, dirnames, files in os.walk(os.path.join(REPO, top)):
            dirnames[:] = [d for d in dirnames if d != '__pycache__']
            for f in files:
                if f.endswith('.py'):
                    p = os.path.join(dirpath, f)
                    with open(p, encoding='utf-8-sig') as fh:
                        yield os.path.relpath(p, REPO).replace('\\', '/'), ast.parse(fh.read())


@pytest.mark.parametrize('snippet,rel', [
    ("env['GIT_CONFIG_GLOBAL'] = os.devnull", 'archeus/core/verification/worker.py'),
    ("env.update(GIT_CONFIG_GLOBAL=os.devnull)", 'claude_sessions/x.py'),
    ("def log(d):\n    return ['git', '-c', 'core.hooksPath=' + d, 'log']", LOCAL),
    ("def other(s):\n    return [git, '--git-dir', s, 'cat-file']", LOCAL),
    ("os.path.join(archeus_home(), 'repos', pid + '.git')", 'archeus/core/execution/manager.py'),
    ("def _merge(self):\n    LocalNode.store_git('trusted', ['merge-base'])",
     'archeus/core/verification/worker.py'),
    ("def store_open(pid):\n    _store_pin('trusted', s)", LOCAL),
    ("CAPABILITY_ENV = {'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_GLOBAL': ''}",
     'archeus/harnesses/base.py'),
])
def test_the_detector_sees_a_second_store_pin(snippet, rel):
    assert _store_pin_violations(ast.parse(snippet), rel)


def test_no_second_store_pin_exists_and_the_reviewed_env_pins_are_untouched():
    found, scanned, seen = [], 0, set()
    for rel, tree in _production_trees():
        found += _store_pin_violations(tree, rel)
        scanned += 1
        # the scan reaches the reviewed execution and verifier pins: a rule that
        # did name their keys would flag them, so a clean result is not a miss
        wide = ('GIT_CONFIG_NOSYSTEM', 'GIT_CONFIG_COUNT', 'GIT_TERMINAL_PROMPT')
        seen |= {(r, v) for r, _l, v in _store_pin_violations(tree, rel, keys=wide)
                 if v in wide}
    assert scanned > 100                      # a gate that scans nothing passes
    assert found == []
    assert {('archeus/harnesses/base.py', 'GIT_CONFIG_NOSYSTEM'),
            ('archeus/harnesses/base.py', 'GIT_CONFIG_COUNT'),
            ('archeus/harnesses/base.py', 'GIT_TERMINAL_PROMPT'),
            ('archeus/node/local.py', 'GIT_TERMINAL_PROMPT')} <= seen
