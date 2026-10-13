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
            LocalNode.store_git(mode, args, git_dir=path)
    assert spawns.calls == []


@pytest.mark.parametrize('mode,args', [('trusted', ['config', '--list']),
                                       ('trusted', ['gc']), ('seal', ['update-ref', 'x', 'y']),
                                       ('base', ['fetch', 'x']), ('version', ['init']),
                                       ('init', ['version']), ('trusted', [])])
def test_a_subcommand_outside_its_mode_is_refused(spawns, mode, args):
    with pytest.raises(StoreError):
        LocalNode.store_git(mode, args, git_dir=paths.repo_store(ids.new_id('project')))
    with pytest.raises(StoreError, match='not a store read'):
        LocalNode.store_read(ids.new_id('project'), ['update-ref', 'refs/x', 'y'])
    assert spawns.calls == []


@pytest.mark.parametrize('bad', ['../x', 'prj_x', ids.new_id('execution'), '', None])
def test_an_ill_formed_project_id_names_no_store(spawns, bad):
    with pytest.raises(ValueError, match='not a project id'):
        LocalNode.store_open(bad)
    assert spawns.calls == []


@pytest.mark.parametrize('found', [None, os.path.join(os.curdir, 'git.EXE')])
def test_no_absolute_git_means_no_store(spawns, monkeypatch, found):
    monkeypatch.setattr(local.shutil, 'which', lambda name: found)
    with pytest.raises(StoreError, match='no absolute git'):
        LocalNode.store_open(ids.new_id('project'))
    assert spawns.calls == []


@pytest.mark.parametrize('version', ['git version 2.40.9\n', 'git version 1.9.0\n', 'garbage\n',
                                     ''])
def test_an_old_or_unreadable_git_is_refused_after_its_one_version_call(spawns, version):
    spawns.version = version
    pid = ids.new_id('project')
    with pytest.raises(StoreError, match='older than 2.41.0'):
        LocalNode.store_open(pid)
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
        LocalNode.store_open(ids.new_id('project'))
    assert spawns.calls == []


def test_a_store_core_never_claimed_is_refused_not_adopted(spawns):
    pid = ids.new_id('project')
    store = paths.repo_store(pid)
    os.makedirs(os.path.join(store, 'refs'))
    with open(os.path.join(store, 'config'), 'wb') as f:
        f.write(b'[core]\n\trepositoryformatversion = 0\n\tbare = true\n')
    with pytest.raises(StoreError, match='never claimed'):
        LocalNode.store_open(pid)
    assert [c.argv[-1] for c in spawns.calls] == ['version']


@pytest.mark.parametrize('config,refs', [
    (b'[core]\n\tbare = true\n[include]\n\tpath = x\n', False),
    (b'[core]\n\tbare = true\n\thooksPath = x\n', False),
    (b'[core]\n\tbare = true\n\tfsmonitor = x\n', False),
    (b'[core]\n\tbare = true\n', True),
])
def test_an_unsealed_store_is_never_blessed_by_what_it_holds(spawns, config, refs):
    """Core claimed it and a crash came before the seal: it is sealed only while
    its config is exactly what `init --bare` writes and it holds no ref."""
    pid = ids.new_id('project')
    store = paths.repo_store(pid)
    pin = local._pin_files()
    open(os.path.join(pin, pid + '.owned'), 'xb').close()
    os.makedirs(os.path.join(store, 'refs', 'heads'))
    with open(os.path.join(store, 'config'), 'wb') as f:
        f.write(config)
    if refs:
        with open(os.path.join(store, 'refs', 'heads', 'main'), 'w') as f:
            f.write('0' * 40 + '\n')
    with pytest.raises(StoreError, match='unsealed store'):
        LocalNode.store_open(pid)
    assert [c.argv[-1] for c in spawns.calls] == ['version']
    assert not os.path.lexists(os.path.join(pin, pid + '.json'))


@pytest.mark.parametrize('plant', [('hooks', 'post-update'), ('info', 'attributes'),
                                   ('objects', 'info', 'alternates'), ('commondir',),
                                   ('config.worktree',)])
def test_a_store_with_an_execution_point_is_refused(spawns, plant):
    pid = ids.new_id('project')
    store = paths.repo_store(pid)
    pin = local._pin_files()
    open(os.path.join(pin, pid + '.owned'), 'xb').close()
    os.makedirs(os.path.join(store, *plant[:-1]), exist_ok=True)
    open(os.path.join(store, *plant), 'wb').close()
    with pytest.raises(StoreError, match='a store with'):
        LocalNode.store_open(pid)
    assert [c.argv[-1] for c in spawns.calls] == ['version']


def test_no_environment_or_test_marker_unlocks_a_fetch(spawns, monkeypatch):
    for k in ('PYTEST_CURRENT_TEST', 'ARCHEUS_STORE_FETCH', 'ARCHEUS_REAL_BOUNDARY', 'CI'):
        monkeypatch.setenv(k, '1')
    with pytest.raises(StoreError, match='no fetch into a store'):
        LocalNode.store_fetch(ids.new_id('project'), os.path.abspath(os.sep), 'refs/heads/main',
                              '0' * 40, 'refs/archeus/exec/x/seed')
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', 1)        # truthy is not accepted
    with pytest.raises(StoreError, match='no fetch into a store'):
        LocalNode.store_fetch(ids.new_id('project'), os.path.abspath(os.sep), 'refs/heads/main',
                              '0' * 40, 'refs/archeus/exec/x/seed')
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
                              expect, ref)
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
