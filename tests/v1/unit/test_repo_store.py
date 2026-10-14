"""PV-20 K1 (T-048) and K2 (T-066): the Core-owned store's one pin and the seed's
byte core and checks, with no process started.

Every Git call here is answered by a fake `proc.run` that records argv, env and
cwd; a refusal is asserted together with zero calls. Real Git runs only in
tests/v1/integration/test_repo_store.py."""

import ast
import hashlib
import os
import threading
import time
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
               'GIT_CEILING_DIRECTORIES', 'GIT_NO_LAZY_FETCH'}


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
    local._VERSION.clear()
    monkeypatch.setattr(local.shutil, 'which', lambda name: GIT)
    s = Spawns()
    monkeypatch.setattr(local.proc, 'run', s)
    yield s
    local._git_exe.cache_clear()
    local._VERSION.clear()


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
        assert env['GIT_NO_LAZY_FETCH'] == '1'                 # no lazy fetch, any mode
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
    pid = ids.new_id('project')
    with pytest.raises(StoreError, match='execution area'):      # the store alone, not the pin
        LocalNode.store_open(pid, workdirs=[paths.repo_store(pid)])
    assert not os.path.lexists(paths.repos_dir())
    with pytest.raises(StoreError, match='a collection'):
        LocalNode.store_git('base', ['rev-parse', 'HEAD'], workdirs=wd, git_dir=wd)
    assert spawns.calls == []
    LocalNode.store_git('base', ['rev-parse', 'HEAD'], workdirs=[wd + '-other'], git_dir=wd)
    assert len(spawns.calls) == 1                       # the control: not recorded, it runs


def _repo(where, gitdir_to=None, config=b'[core]\n\tbare = false\n'):
    """A repository root and its git directory's metadata; with *gitdir_to*, its
    `.git` is a file naming that directory."""
    os.makedirs(where, exist_ok=True)
    gd = os.path.join(where, '.git') if gitdir_to is None else gitdir_to
    if gitdir_to is not None:
        with open(os.path.join(where, '.git'), 'w') as f:
            f.write('gitdir: %s\n' % gitdir_to)
    for d in (('objects', 'info'), ('objects', 'pack'), ('refs', 'heads')):
        os.makedirs(os.path.join(gd, *d), exist_ok=True)
    with open(os.path.join(gd, 'HEAD'), 'wb') as f:
        f.write(b'ref: refs/heads/main\n')
    with open(os.path.join(gd, 'config'), 'wb') as f:
        f.write(config)
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


def _tree(top):
    return sorted(os.path.join(d, n) for d, ds, fs in os.walk(top) for n in ds + fs)


@pytest.mark.parametrize('recorded', ['home', 'repos', 'pin', 'empty'])
@pytest.mark.parametrize('cache', ['cold', 'warm'])
def test_a_pin_area_inside_a_recorded_workdir_makes_and_starts_nothing(spawns, tmp_path,
                                                                       cache, recorded):
    """A recorded workdir that holds the pin area: no entry point makes anything
    there or starts Git there, with the version not read yet or already cached."""
    root = _repo(tmp_path / 'u')
    if cache == 'warm':
        LocalNode.store_resolve_base(root, 'refs/heads/main', workdirs=())
        assert spawns.calls[0].argv[-1] == 'version'
        spawns.calls.clear()
    repos, pin, empty, _cfg = local._pin_area()
    wd = {'home': paths.archeus_home(), 'repos': repos, 'pin': pin, 'empty': empty}[recorded]
    before = _tree(paths.archeus_home())
    for call in (lambda: LocalNode.store_resolve_base(root, 'refs/heads/main', workdirs=[wd]),
                 lambda: LocalNode.store_open(ids.new_id('project'), workdirs=[wd]),
                 lambda: local._git_version([wd])):
        with pytest.raises(StoreError, match='execution area'):
            call()
    assert spawns.calls == [] and _tree(paths.archeus_home()) == before


def _areas(tmp_path):
    """One existing directory in each kind of execution area, and the recorded workdir."""
    wd = str(tmp_path / 'recorded-wd')
    areas = {'run': os.path.join(paths.ExecPaths(ids.new_id('execution')).state, 'c'),
             'worktrees': os.path.join(paths.archeus_home(), 'worktrees', 'p', 'm', 't1', 'c'),
             'recorded': os.path.join(wd, 'c')}
    for d in areas.values():
        os.makedirs(d)
    return areas, wd


def _indirect(tmp_path, commondir=None, alternates=None, nested=None):
    """A repository whose `.git` names a git directory outside it, which may name
    a common directory (*commondir*, the file's exact bytes) and whose objects may
    borrow stores (*alternates*); *nested* is a second store's alternates."""
    gd = tmp_path / 'gd'
    (gd / 'objects' / 'info').mkdir(parents=True)
    root = _repo(tmp_path / 'u', str(gd))
    if commondir is not None:
        (gd / 'commondir').write_bytes(commondir)
    if alternates is not None:
        (gd / 'objects' / 'info' / 'alternates').write_bytes(alternates)
    if nested is not None:
        alt = tmp_path / 'alt1'
        (alt / 'info').mkdir(parents=True)
        (alt / 'info' / 'alternates').write_bytes(nested)
        (gd / 'objects' / 'info' / 'alternates').write_bytes(str(alt).encode())
    return root, str(gd)


def _read_through(root, call, wd):
    if call == 'base':
        return LocalNode.store_resolve_base(root, 'refs/heads/main', workdirs=[wd])
    return LocalNode.store_fetch(ids.new_id('project'), root, 'refs/heads/main', '0' * 40,
                                 'refs/archeus/exec/e1/seed', workdirs=[wd])


@pytest.mark.parametrize('call', ['base', 'fetch'])
@pytest.mark.parametrize('form', ['absolute', 'relative'])
@pytest.mark.parametrize('kind', ['commondir', 'alternates', 'nested-alternates'])
@pytest.mark.parametrize('where', ['run', 'worktrees', 'recorded'])
def test_a_common_dir_or_borrowed_store_in_an_execution_area_is_refused(
        spawns, monkeypatch, tmp_path, where, kind, form, call):
    """gitrepository-layout: config, objects and refs come from `commondir` (a
    relative one against the git dir), objects also from every alternate (a
    relative one against the objects dir). Each is checked before any spawn."""
    areas, wd = _areas(tmp_path)
    target = areas[where]
    gd = tmp_path / 'gd'
    against = {'commondir': gd, 'alternates': gd / 'objects', 'nested-alternates':
               tmp_path / 'alt1'}[kind]
    text = (target if form == 'absolute' else os.path.relpath(target, str(against))).encode()
    root, _gd = _indirect(tmp_path, **{'commondir': {'commondir': text + b'\n'},
                                       'alternates': {'alternates': text + b'\n'},
                                       'nested-alternates': {'nested': text}}[kind])
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(StoreError, match='execution area'):
        _read_through(root, call, wd)
    assert spawns.calls == []


@pytest.mark.parametrize('call', ['base', 'fetch'])
@pytest.mark.parametrize('case', ['commondir-empty', 'commondir-two-lines', 'commondir-a-file',
                                  'commondir-missing', 'commondir-crlf-inside',
                                  'alternates-comment', 'alternates-quoted', 'alternates-missing',
                                  'alternates-cr', 'alternates-too-deep'])
def test_an_indirection_core_cannot_read_as_git_would_is_refused(spawns, monkeypatch, tmp_path,
                                                                 case, call):
    out = tmp_path / 'outside'
    out.mkdir()
    (tmp_path / 'a-file').write_bytes(b'')
    o = str(out).encode()
    kw = {'commondir-empty': {'commondir': b''},
          'commondir-two-lines': {'commondir': o + b'\n' + o + b'\n'},
          'commondir-a-file': {'commondir': str(tmp_path / 'a-file').encode()},
          'commondir-missing': {'commondir': str(tmp_path / 'nowhere').encode()},
          'commondir-crlf-inside': {'commondir': o + b'\r\nx'},
          'alternates-comment': {'alternates': b'# ' + o + b'\n'},
          'alternates-quoted': {'alternates': b'"' + o + b'"\n'},
          'alternates-missing': {'alternates': str(tmp_path / 'nowhere').encode()},
          'alternates-cr': {'alternates': o + b'\r\n'},
          'alternates-too-deep': {'alternates': b'.'}}[case]
    root, gd = _indirect(tmp_path, **kw)
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(StoreError, match='cannot resolve|cannot read|too deep'):
        _read_through(root, call, str(tmp_path / 'wd'))
    assert spawns.calls == []


@pytest.mark.parametrize('form', ['absolute', 'relative'])
def test_a_common_dir_and_borrowed_stores_outside_every_area_are_read(spawns, monkeypatch,
                                                                      tmp_path, form):
    common = tmp_path / 'common'
    (common / 'objects' / 'info').mkdir(parents=True)
    alt = tmp_path / 'alt'
    alt.mkdir()
    gd = tmp_path / 'gd'
    rel = lambda p, base: (str(p) if form == 'absolute' else os.path.relpath(str(p), str(base)))
    (common / 'objects' / 'info' / 'alternates').write_bytes(
        rel(alt, common / 'objects').encode() + b'\n')
    root, _gd = _indirect(tmp_path, commondir=rel(common, gd).encode() + b'\n')
    LocalNode.store_resolve_base(root, 'refs/heads/main', workdirs=[str(tmp_path / 'wd')])
    assert [c.argv[-1] for c in spawns.calls] == ['version', 'refs/heads/main^{commit}']
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(OSError) as err:          # past the source: the fake init makes no store
        LocalNode.store_fetch(ids.new_id('project'), root, 'refs/heads/main', '0' * 40,
                              'refs/archeus/exec/e1/seed', workdirs=[str(tmp_path / 'wd')])
    assert 'execution area' not in str(err.value)
    assert any('init' in c.argv for c in spawns.calls)


#: every way a config file can hold an include (git-config "Syntax", "Includes",
#: "Conditional includes"): section names are case-insensitive, a variable may
#: follow its header on the same line, and the deprecated dotted subsection form
INCLUDES = [b'[include]\n\tpath = %s\n', b'[includeIf "gitdir:**"]\n\tpath = %s\n',
            b'[INCLUDE]\n\tPATH = %s\n', b'[IncludeIF "onbranch:main"]\n\tpath = %s\n',
            b'[core]\n\tbare = false\n[include] path = %s\n', b'[includeif.gitdir/i:x]\n\tpath = %s\n',
            b'[core]\n\tbare = false\n  [  Include  ]\n  path = %s\n']


@pytest.mark.parametrize('call', ['base', 'fetch'])
@pytest.mark.parametrize('form', range(len(INCLUDES)))
@pytest.mark.parametrize('where', ['run', 'worktrees', 'recorded', 'outside'])
def test_a_source_config_holding_any_include_is_refused(spawns, monkeypatch, tmp_path, where,
                                                         form, call):
    """Fail closed: Core follows no include, wherever it points. A source with
    none is read (test_a_root_and_git_dir_outside_every_area_are_read)."""
    areas, wd = _areas(tmp_path)
    areas['outside'] = str(tmp_path / 'outside')
    os.makedirs(areas['outside'])
    target = os.path.join(areas[where], 'x.cfg')
    open(target, 'wb').close()
    root = _repo(tmp_path / 'u', str(tmp_path / 'gd'), config=INCLUDES[form] % target.encode())
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(StoreError, match="saying 'include'"):
        _read_through(root, call, wd)
    assert spawns.calls == []


@pytest.mark.parametrize('call', ['base', 'fetch'])
@pytest.mark.parametrize('extension', [True, False])
def test_a_config_worktree_holding_an_include_is_refused(spawns, monkeypatch, tmp_path,
                                                         extension, call):
    """git-config FILES: $GIT_DIR/config.worktree is read when
    extensions.worktreeConfig is set; Core reads it whenever it exists."""
    gd = tmp_path / 'gd'
    root = _repo(tmp_path / 'u', str(gd), config=b'[core]\n\tbare = false\n' + (
        b'[extensions]\n\tworktreeConfig = true\n' if extension else b''))
    (gd / 'config.worktree').write_bytes(b'[include]\n\tpath = %s\n'
                                         % str(tmp_path / 'x.cfg').encode())
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(StoreError, match="saying 'include'"):
        _read_through(root, call, str(tmp_path / 'wd'))
    assert spawns.calls == []


@pytest.mark.parametrize('call', ['base', 'fetch'])
@pytest.mark.parametrize('which', ['dot-git-file', 'config', 'config.worktree', 'HEAD',
                                   'packed-refs', 'loose-ref', 'commondir', 'alternates'])
def test_a_hard_linked_source_metadata_file_is_refused(spawns, monkeypatch, tmp_path, which,
                                                       call):
    """Same bytes, another file: what Git reads a source through is the source's own."""
    gd = tmp_path / 'gd'
    root = _repo(tmp_path / 'u', str(gd))
    common = tmp_path / 'common'
    for d in (('objects',), ('refs',)):
        (common.joinpath(*d)).mkdir(parents=True)
    path = {'dot-git-file': os.path.join(root, '.git'), 'config': str(gd / 'config'),
            'config.worktree': str(gd / 'config.worktree'), 'HEAD': str(gd / 'HEAD'),
            'packed-refs': str(gd / 'packed-refs'), 'loose-ref': str(gd / 'refs' / 'heads' / 'x'),
            'commondir': str(gd / 'commondir'),
            'alternates': str(gd / 'objects' / 'info' / 'alternates')}[which]
    if not os.path.exists(path):
        with open(path, 'wb') as f:
            f.write({'commondir': str(common).encode(), 'alternates': str(common / 'objects')
                     .encode()}.get(which, b''))
    os.link(path, str(tmp_path / 'outside'))
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(OSError, match='hard-linked'):
        _read_through(root, call, str(tmp_path / 'wd'))
    assert spawns.calls == []


@pytest.mark.parametrize('call', ['base', 'fetch'])
@pytest.mark.parametrize('config', [
    pytest.param(b'[extensions]\n\tpartialClone = origin\n', id='partialclone'),
    pytest.param(b'[remote "origin"]\n\tPromisor = true\n', id='promisor'),
    pytest.param(b'[remote "origin"]\n\tpartialCloneFilter = blob:none\n', id='filter'),
    pytest.param(b'[extensions]\n\tobjectFormat = sha256\n', id='objectformat'),
    pytest.param(b'[extensions]\n\tcompatObjectFormat = sha256\n', id='compatobjectformat'),
    pytest.param(b'[EXTENSIONS]\n\tREFSTORAGE = reftable\n', id='refstorage'),
    pytest.param(b'[core]\n\talternateRefsCommand = x\n', id='alternaterefscommand'),
    pytest.param(b'[core]\n\tAlternateRefsPrefixes = refs/heads\n', id='alternaterefsprefixes'),
])
def test_a_source_config_naming_what_core_does_not_follow_is_refused(spawns, monkeypatch,
                                                                     tmp_path, config, call):
    """Lazy fetch from a promisor remote, another object format or ref backend,
    alternate-ref commands: refused before anything starts, in any case."""
    root = _repo(tmp_path / 'u', str(tmp_path / 'gd'), config=b'[core]\n\tbare = false\n' + config)
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(StoreError, match='which Core does not follow'):
        _read_through(root, call, str(tmp_path / 'wd'))
    assert spawns.calls == []


@pytest.mark.parametrize('call', ['base', 'fetch'])
@pytest.mark.parametrize('case', ['reftable', 'promisor-pack', 'http-alternates', 'replace-loose',
                                  'replace-packed', 'sibling-dot-git'])
def test_a_source_form_core_refuses_starts_nothing(spawns, monkeypatch, tmp_path, case, call):
    gd = tmp_path / 'gd'
    root = _repo(tmp_path / 'u', str(gd))
    if case == 'reftable':
        (gd / 'reftable').mkdir()
    elif case == 'promisor-pack':
        (gd / 'objects' / 'pack' / 'pack-1.promisor').write_bytes(b'')
    elif case == 'http-alternates':
        (gd / 'objects' / 'info' / 'http-alternates').write_bytes(b'x\n')
    elif case == 'replace-loose':
        (gd / 'refs' / 'replace').mkdir()
        (gd / 'refs' / 'replace' / ('1' * 40)).write_bytes(b'2' * 40 + b'\n')
    elif case == 'replace-packed':
        (gd / 'packed-refs').write_bytes(b'2' * 40 + b' refs/replace/' + b'1' * 40 + b'\n')
    else:
        (tmp_path / 'u.git').mkdir()           # upload-pack's enter_repo could take it
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(StoreError):
        _read_through(root, call, str(tmp_path / 'wd'))
    assert spawns.calls == []


@pytest.mark.parametrize('call', ['base', 'fetch'])
@pytest.mark.parametrize('which', ['shallow', 'grafts', 'common-shallow', 'common-grafts'])
def test_a_hard_linked_shallow_or_grafts_file_is_refused(spawns, monkeypatch, tmp_path, which,
                                                         call):
    """commit.c reads both to parse a commit: they are the source's own."""
    gd, common = tmp_path / 'gd', tmp_path / 'common'
    root = _repo(tmp_path / 'u', str(gd))
    if which.startswith('common'):
        _repo(tmp_path / 'c', str(common))
        (gd / 'commondir').write_bytes(str(common).encode() + b'\n')
    base = common if which.startswith('common') else gd
    path = base / 'shallow' if which.endswith('shallow') else base / 'info' / 'grafts'
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b'')
    os.link(str(path), str(tmp_path / 'outside'))
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(OSError, match='hard-linked'):
        _read_through(root, call, str(tmp_path / 'wd'))
    assert spawns.calls == []


def test_a_plain_shallow_and_grafts_file_are_read(spawns, tmp_path):
    gd = tmp_path / 'gd'
    root = _repo(tmp_path / 'u', str(gd))
    (gd / 'shallow').write_bytes(b'1' * 40 + b'\n')
    (gd / 'info').mkdir()
    (gd / 'info' / 'grafts').write_bytes(b'')
    LocalNode.store_resolve_base(root, 'refs/heads/main', workdirs=())
    assert [c.argv[-1] for c in spawns.calls] == ['version', 'refs/heads/main^{commit}']


@pytest.mark.parametrize('rev', ['-x', 'main', 'head', 'refs/heads/main@{1}', 'main@{upstream}',
                                 'HEAD~1', 'refs/heads/main:a.txt', ':/fix', 'refs/heads/../x',
                                 'refs/heads/main^2', '1' * 39])
def test_base_resolution_takes_a_ref_name_or_a_full_id_only(spawns, tmp_path, rev):
    """No reflog, upstream, path or ancestry syntax: nothing but refs and objects."""
    root = _repo(tmp_path / 'u')
    with pytest.raises(StoreError, match='not a revision Core resolves'):
        LocalNode.store_resolve_base(root, rev, workdirs=())
    assert spawns.calls == []
    LocalNode.store_resolve_base(root, '1' * 40, workdirs=())
    assert spawns.calls[-1].argv[-1] == '1' * 40 + '^{commit}'
    LocalNode.store_resolve_base(root, 'HEAD', workdirs=())         # K2: HEAD itself, only
    assert spawns.calls[-1].argv[-1] == 'HEAD^{commit}'


@pytest.mark.parametrize('call', ['base', 'fetch'])
@pytest.mark.parametrize('content', [
    pytest.param(lambda gd: b'gitdir: ' + b'x' * (64 * 1024), id='over-the-cap'),
    pytest.param(lambda gd: b'gitdir: ' + gd + b'\xff\n', id='invalid-utf8'),
    pytest.param(lambda gd: b'gitdir:  ' + gd + b'\n', id='leading-space'),
    pytest.param(lambda gd: b'gitdir: \t' + gd + b'\n', id='leading-tab'),
    pytest.param(lambda gd: b'gitdir: ' + gd + b' \n', id='trailing-space'),
    pytest.param(lambda gd: b'gitdir: ' + gd + b'\t\r\n', id='trailing-tab'),
    pytest.param(lambda gd: b'gitdir:' + gd + b'\n', id='no-space-after-prefix'),
    pytest.param(lambda gd: b'GITDIR: ' + gd + b'\n', id='prefix-case'),
    pytest.param(lambda gd: gd + b'\n', id='no-prefix'),
    pytest.param(lambda gd: b'gitdir: \r\n', id='empty'),
    pytest.param(lambda gd: b'gitdir: ' + gd + b'\x00x\n', id='nul'),
    pytest.param(lambda gd: b'gitdir: ' + gd + b'\nsecond\n', id='second-line'),
])
def test_a_git_file_core_cannot_read_as_git_does_is_refused(spawns, monkeypatch, tmp_path,
                                                            content, call):
    """setup.c read_gitfile_gently: the whole file, the exact prefix, only
    trailing CR and LF trimmed. Blanks Git would keep, bytes it would read
    differently and anything over the cap are refused before anything starts."""
    gd = tmp_path / 'gd'
    root = _repo(tmp_path / 'u', str(gd))
    (tmp_path / 'u' / '.git').write_bytes(content(str(gd).encode()))
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    with pytest.raises(StoreError, match=r'\.git file'):
        _read_through(root, call, str(tmp_path / 'wd'))
    assert spawns.calls == []


@pytest.mark.skipif(os.name != 'nt', reason='drive and root relative paths are Windows forms')
@pytest.mark.parametrize('path', [b'C:gd', b'\\gd', b'/gd'])
def test_a_drive_or_root_relative_git_file_is_refused(spawns, tmp_path, path):
    root = _repo(tmp_path / 'u', str(tmp_path / 'gd'))
    (tmp_path / 'u' / '.git').write_bytes(b'gitdir: ' + path + b'\n')
    with pytest.raises(StoreError, match=r'\.git file'):
        LocalNode.store_resolve_base(root, 'refs/heads/main', workdirs=())
    assert spawns.calls == []


@pytest.mark.parametrize('ending', [b'\n', b'\r\n', b'\r\n\r\n', b''])
def test_a_git_file_resolves_where_git_resolves_it(spawns, tmp_path, ending):
    gd = tmp_path / 'gd'
    root = _repo(tmp_path / 'u', str(gd))
    (tmp_path / 'u' / '.git').write_bytes(b'gitdir: ' + str(gd).encode() + ending)
    LocalNode.store_resolve_base(root, 'refs/heads/main', workdirs=())
    argv = spawns.calls[-1].argv
    assert argv[argv.index('--git-dir') + 1] == str(gd)


def test_a_relative_git_file_resolves_against_its_root(spawns, tmp_path):
    gd = tmp_path / 'gd'
    root = _repo(tmp_path / 'u', str(gd))
    (tmp_path / 'u' / '.git').write_bytes(b'gitdir: ../gd\n')
    LocalNode.store_resolve_base(root, 'refs/heads/main', workdirs=())
    argv = spawns.calls[-1].argv
    assert os.path.normpath(argv[argv.index('--git-dir') + 1]) == str(gd)


def test_a_long_git_file_is_read_whole(tmp_path):
    """The legacy reader stopped at 4096 characters; Git reads the whole file."""
    root = tmp_path / 'u'
    root.mkdir()
    (root / '.git').write_bytes(b'gitdir: ' + b'a' * 5000 + b'\n')
    assert local._git_dir_of(str(root)) == os.path.join(str(root), 'a' * 5000)


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


@pytest.mark.parametrize('version', ['git version 2.44.9\n', 'git version 2.40.9\n', 'git version 1.9.0\n', 'garbage\n',
                                     ''])
def test_an_old_or_unreadable_git_is_refused_after_its_one_version_call(spawns, version):
    spawns.version = version
    pid = ids.new_id('project')
    with pytest.raises(StoreError, match='older than 2.45.0'):
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
    pin = local._pin_files(())
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
              'GIT_ALLOW_PROTOCOL', 'GIT_PROTOCOL_FROM_USER', 'GIT_CEILING_DIRECTORIES',
              'GIT_NO_LAZY_FETCH')
STORE_C = ('core.hooksPath=', 'core.fsmonitor=', 'core.attributesFile=', 'gc.auto=',
           'maintenance.auto=', 'submodule.recurse=', 'core.logAllRefUpdates=')
LOCAL = 'archeus/node/local.py'
#: who may call the spawner and the builder (later cards add theirs by name)
CALLERS = {'store_git': ('store_open', 'store_read', 'store_fetch', 'store_resolve_base',
                         '_git_version', 'store_seed_ref', 'seed_workspace',
                         'import_workspace', '_export_tree'),
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
    ("def _seed_check(dot):\n    LocalNode.store_git('seed', ['ls-files', '-s', '-z'])", LOCAL),
    ("argv += ['-c', 'core.logAllRefUpdates=false']", 'archeus/core/execution/manager.py'),
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



# ── K2 (T-066, T-049 + C-1013-T049): the seed's pin, byte core and checks ─────

def test_the_seed_mode_runs_under_the_whole_pin_and_writes_no_reflog():
    _pin_, empty, cfg = _pin()
    dot = os.path.join(paths.seed_staging(ids.new_id('execution')), '.git')
    argv, env, cwd = local._store_pin('seed', dot)
    cs = [argv[i + 1] for i, a in enumerate(argv) if a == '-c']
    assert set(cs) == set(PINS) | {'core.hooksPath=' + empty, 'core.attributesFile=' + cfg,
                                   'core.logAllRefUpdates=false'}
    assert argv[argv.index('--git-dir') + 1] == dot and cwd == dot
    assert '--no-replace-objects' in argv and '--attr-source' not in argv
    assert set(env) <= ALLOWED_ENV and env['HOME'] == empty


def test_seed_staging_is_cores_and_named_by_the_execution():
    eid = ids.new_id('execution')
    assert paths.seed_staging(eid) == os.path.join(paths.repos_dir(), '.seed', eid)
    for bad in ('..', 'exe_x', ids.new_id('project'), ''):
        with pytest.raises(ValueError):
            paths.seed_staging(bad)


@pytest.mark.parametrize('mode,args', [('seed', ['config', 'core.hooksPath', 'x']),
                                       ('seed', ['checkout', 'HEAD']),
                                       ('seed', ['cat-file', '--batch']),
                                       ('seed', ['init'])])
def test_a_seed_subcommand_outside_its_mode_is_refused(spawns, mode, args):
    with pytest.raises(StoreError, match='is not a'):
        LocalNode.store_git(mode, args, workdirs=(), git_dir=paths.repos_dir())
    assert spawns.calls == []


class Child:
    """A child process answered in-process: stdout handed out one chunk per read,
    then, with *stall*, nothing until it is killed. Nothing is started. Each pipe
    records its close; with *close_fails* every close raises."""

    def __init__(self, chunks=(), code=0, stall=False, close_fails=False):
        self.chunks, self.code, self.stall = list(chunks), code, stall
        self.killed, self.written, self.returncode = threading.Event(), b'', None
        self.closed = set()
        err = [b'boom'] if code else []

        def closer(name):
            def close():
                self.closed.add(name)
                if close_fails:
                    raise OSError('close failed: %s' % name)
            return close
        self.stdout = SimpleNamespace(read1=self._read1, close=closer('stdout'))
        self.stderr = SimpleNamespace(read=lambda n: err.pop() if err else b'',
                                      close=closer('stderr'))
        self.stdin = SimpleNamespace(write=self._write, close=closer('stdin'))

    def _read1(self, n):
        if self.chunks and not self.killed.is_set():
            return self.chunks.pop(0)
        if self.stall:
            self.killed.wait(10)
        return b''

    def _write(self, data):
        if self.code == 'gone':
            raise BrokenPipeError('the child is gone')
        self.written += data

    def kill(self):
        self.killed.set()

    def wait(self):
        self.returncode = -9 if self.killed.is_set() else 0 if self.code == 'gone' else self.code
        return self.returncode


@pytest.fixture
def child(monkeypatch):
    """`subprocess.Popen` answered by a `Child`: the call is recorded, never started."""
    box = SimpleNamespace(made=[], child=None)

    def popen(argv, **kw):
        box.made.append(SimpleNamespace(argv=argv, **kw))
        return box.child
    monkeypatch.setattr(local.subprocess, 'Popen', popen)
    box.use = lambda c: setattr(box, 'child', c) or c
    return box


class Sink:
    def __init__(self, refuse_at=None):
        self.got, self.ended, self.refuse_at = [], False, refuse_at

    def feed(self, chunk):
        self.got.append(chunk)
        if self.refuse_at is not None and len(self.got) >= self.refuse_at:
            raise StoreError('refused by the sink')

    def end(self):
        self.ended = True

    def abort(self):
        self.aborted = True


STORE = lambda: paths.repo_store(ids.new_id('project'))     # noqa: E731


def test_the_byte_core_hands_raw_bytes_to_the_sink_and_feeds_stdin_as_bytes(child, spawns):
    raw = [b'\xff\xfe\x00', b'\x80\x00z']
    c = child.use(Child(raw))
    sink = Sink()
    LocalNode.store_git('trusted', ['cat-file', '--batch'], workdirs=(), git_dir=STORE(),
                        stdin=b'abc\n', sink=sink)
    assert sink.got == raw and sink.ended and c.written == b'abc\n'
    made = child.made[0]
    assert made.argv[0] == GIT and made.argv[-2:] == ['cat-file', '--batch']
    assert made.creationflags == local.proc.no_window_flags and spawns.calls == []


def test_a_sink_that_refuses_kills_the_child_before_it_reads_on(child):
    c = child.use(Child([b'x' * 10] * 50))
    with pytest.raises(StoreError, match='refused by the sink'):
        LocalNode.store_git('trusted', ['ls-tree', 'x'], workdirs=(), git_dir=STORE(),
                            sink=Sink(refuse_at=3))
    assert c.killed.is_set() and len(c.chunks) == 47


def test_a_child_that_stalls_is_killed_at_the_deadline(child):
    c = child.use(Child(stall=True))
    t = time.monotonic()
    with pytest.raises(StoreError, match='deadline'):
        LocalNode.store_git('trusted', ['ls-tree', 'x'], workdirs=(), git_dir=STORE(),
                            sink=Sink(), timeout=0.2)
    assert c.killed.is_set() and time.monotonic() - t < 5


def test_a_failed_child_is_a_refusal_and_its_output_is_not_taken(child):
    child.use(Child([b'partial'], code=1))
    sink = Sink()
    with pytest.raises(StoreError, match='git failed'):
        LocalNode.store_git('trusted', ['ls-tree', 'x'], workdirs=(), git_dir=STORE(), sink=sink)
    assert not sink.ended


@pytest.mark.parametrize('where', ['work', 'dot'])
def test_a_byte_call_in_an_execution_area_is_refused_before_a_spawn(child, where):
    work = paths.ExecPaths(ids.new_id('execution')).work
    with pytest.raises(StoreError, match='execution area'):
        LocalNode.store_git('seed', ['ls-files', '-s', '-z'], workdirs=(),
                            git_dir=work if where == 'work' else os.path.join(work, '.git'),
                            sink=Sink())
    assert child.made == []


# the manifest, record by record (`ls-tree -r -z -l --full-tree`)

OID = lambda data: hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()   # noqa: E731
COMMIT = 'c' * 40


def _rec(mode, path, data=b'x', kind=None, oid=None, size=None):
    kind = kind or ('commit' if mode == '160000' else 'blob')
    oid = oid or (COMMIT if mode == '160000' else OID(data))
    size = size if size is not None else ('-' if mode == '160000' else str(len(data)))
    return (b'%s %s %s %7s\t' % (mode.encode(), kind.encode(), oid.encode(), size.encode())
            + (path.encode('utf-8') if isinstance(path, str) else path) + b'\0')


def _manifest(records, chunk=7, prefix=40):
    m = local._Manifest(prefix)
    data = b''.join(records)
    for i in range(0, len(data), chunk):
        m.feed(data[i:i + chunk])
    m.end()
    return m


def test_a_manifest_maps_links_to_files_and_gitlinks_to_empty_directories():
    m = _manifest([_rec('100644', 'a.txt', b'A'), _rec('100755', 'bin/run', b'R'),
                   _rec('120000', 'link', b'a.txt'), _rec('160000', 'deps/sub')])
    assert m.expected() == {'a.txt': ('f', 1, OID(b'A')), 'bin': ('d',),
                            'bin/run': ('f', 1, OID(b'R')), 'link': ('f', 5, OID(b'a.txt')),
                            'deps': ('d',), 'deps/sub': ('d',)}
    assert [e[0] for e in m.entries] == ['100644', '100755', '120000', '160000']


@pytest.mark.parametrize('path', [
    '', 'a//b', './a', 'a/./b', 'a/../b', '..', 'a\\b', 'a:b', 'C:x', 'a\x01b', 'a\x1fb',
    'a\x7fb', 'x<y', 'x>y', 'x"y', 'x|y', 'x?y', 'x*y', 'CON', 'con.txt', 'Aux', 'nul .txt',
    'COM1', 'lpt9.log', 'com\u00b9', 'CONIN$', 'a/PRN/b', 'trail.', 'trail ', 'd./x',
    '.git', '.GIT', 'a/.Git/b', 'git~1', 'a/GIT~1/x', 'a/' * 64 + 'b',
    'x' * 300])
def test_a_path_core_does_not_write_on_windows_refuses_the_seed(path):
    with pytest.raises(StoreError):
        _manifest([_rec('100644', 'ok.txt'), _rec('100644', path)])


def test_a_path_that_is_not_utf8_refuses_the_seed():
    with pytest.raises(StoreError, match='cannot read'):
        _manifest([_rec('100644', b'bad\xff')])


def test_the_full_path_counts_the_directory_it_lands_in():
    name = 'x' * 50
    _manifest([_rec('100644', name)], prefix=local.SEED_MAX_PATH - 51)
    with pytest.raises(StoreError, match='too long'):
        _manifest([_rec('100644', name)], prefix=local.SEED_MAX_PATH - 50)


@pytest.mark.parametrize('rec', [
    _rec('100644', 'a', kind='commit'), _rec('160000', 'a', kind='blob'),
    _rec('040000', 'a', kind='tree'), _rec('100664', 'a'), _rec('100644', 'a', size='-'),
    _rec('160000', 'a', size='1'), _rec('100644', 'a', oid='a' * 64),
    _rec('100644', 'a', oid='A' * 40), _rec('100644', 'a', size='-1'),
    b'100644 blob ' + b'a' * 40 + b'a\0', b'garbage\0'])
def test_an_entry_core_does_not_seed_refuses_it(rec):
    with pytest.raises(StoreError):
        _manifest([rec])


@pytest.mark.parametrize('paths_', [('Readme.md', 'README.md'), ('A/x', 'a/y'), ('a', 'A/b'),
                                    ('d/E', 'D/e')])
def test_two_paths_one_name_under_case_folding_refuse_before_any_write(paths_):
    with pytest.raises(StoreError, match='case-insensitive'):
        _manifest([_rec('100644', p) for p in paths_])


def test_a_listing_past_its_count_is_refused_while_it_arrives(monkeypatch):
    monkeypatch.setattr(local, 'SEED_MAX_ENTRIES', 3)
    m, fed = local._Manifest(40), 0
    data = b''.join(_rec('100644', 'f%d' % i) for i in range(10))
    chunk = 64
    with pytest.raises(StoreError, match='past its bounds'):
        for i in range(0, len(data), chunk):
            fed += 1
            m.feed(data[i:i + chunk])
    assert len(m.entries) == 3 and fed * chunk <= 4 * len(_rec('100644', 'f0')) + chunk


def test_a_record_past_its_size_is_refused_before_its_end_arrives(monkeypatch):
    monkeypatch.setattr(local, 'SEED_MAX_RECORD', 100)
    m = local._Manifest(40)
    with pytest.raises(StoreError, match='past'):
        m.feed(b'1' * 101)                      # no NUL yet: refused on its length alone
    with pytest.raises(StoreError, match='past its bounds'):
        local._Manifest(40).feed(_rec('100644', 'x' * 60) + _rec('100644', 'y' * 20))


def test_a_listing_past_its_total_bytes_is_refused(monkeypatch):
    monkeypatch.setattr(local, 'SEED_MAX_ENTRIES', 2)
    monkeypatch.setattr(local, 'SEED_MAX_RECORD', 80)
    m = local._Manifest(40)
    m.feed(b'x' * 80)
    with pytest.raises(StoreError, match=r'a listing past 160 bytes'):
        m.feed(b'x' * 81)               # the total trips before the record does


def test_a_tree_past_its_bytes_or_depth_is_refused(monkeypatch):
    monkeypatch.setattr(local, 'SEED_MAX_BYTES', 10)
    with pytest.raises(StoreError, match='past 10 bytes'):
        _manifest([_rec('100644', 'a', b'x' * 6), _rec('100644', 'b', b'x' * 5)])
    monkeypatch.setattr(local, 'SEED_MAX_DEPTH', 2)
    _manifest([_rec('100644', 'a/b')])
    with pytest.raises(StoreError, match='too deep'):
        _manifest([_rec('100644', 'a/b/c')])


def test_a_listing_that_ends_inside_a_record_is_refused():
    m = local._Manifest(40)
    m.feed(_rec('100644', 'a')[:-1])
    with pytest.raises(StoreError, match='ends inside'):
        m.end()


# the blobs (`cat-file --batch`), streamed into files Core creates

def _blobs(tmp_path, wanted):
    """(sink, [(oid, size, path)]) for *wanted*: {name: bytes}."""
    want = [(OID(d), len(d), str(tmp_path / n)) for n, d in wanted.items()]
    return local._Blobs(want), want


def _answer(*objs):
    return b''.join(b'%s blob %d\n%s\n' % (OID(d).encode(), len(d), d) for d in objs)


@pytest.mark.parametrize('chunk', [1, 3, 64 * 1024])
def test_a_binary_blob_round_trips_byte_for_byte(tmp_path, chunk):
    data = {'bin': b'\xff\xfe\x00\x80\x00z', 'empty': b'', 'two': b'\xff\xfe\x00\x80\x00z'}
    sink, want = _blobs(tmp_path, data)
    raw = _answer(*data.values())
    for i in range(0, len(raw), chunk):
        sink.feed(raw[i:i + chunk])
    sink.end()
    for (oid, size, path), d in zip(want, data.values()):
        with open(path, 'rb') as f:
            assert f.read() == d


def test_a_blob_core_already_has_a_file_for_is_refused_not_overwritten(tmp_path):
    (tmp_path / 'bin').write_bytes(b'mine')
    sink, _want = _blobs(tmp_path, {'bin': b'theirs'})
    with pytest.raises(FileExistsError):
        sink.feed(_answer(b'theirs'))
    assert (tmp_path / 'bin').read_bytes() == b'mine'


@pytest.mark.parametrize('case', ['truncated', 'overlong-header', 'longer-body', 'trailing',
                                  'wrong-type', 'missing', 'other-content', 'other-id'])
def test_a_blob_answer_core_did_not_ask_for_is_refused(tmp_path, case):
    d = b'\xff\xfe\x00\x80\x00z'
    sink, _want = _blobs(tmp_path, {'bin': d})
    o = OID(d).encode()
    raw = {'truncated': b'%s blob 6\n%s' % (o, d[:5]),
           'overlong-header': b'%s blob 7\n%s?\n' % (o, d),
           'longer-body': b'%s blob 6\n%s?\n' % (o, d),
           'trailing': _answer(d) + b'x',
           'wrong-type': b'%s tree 6\n%s\n' % (o, d),
           'missing': b'%s missing\n' % o,
           'other-content': b'%s blob 6\n%s\n' % (o, b'\xff\xfe\x00\x80\x00Z'),
           'other-id': b'%s blob 6\n%s\n' % (b'0' * 40, d)}[case]
    with pytest.raises(StoreError):
        sink.feed(raw)
        sink.end()


# the two domains of a staged seed (C-1013-T049 §2), on plain files only

BRANCH = 'refs/heads/archeus/m.t1'
REV = 'd' * 40


def _staged(tmp_path):
    """A staging directory exactly as a good seed leaves it, and its manifest."""
    top = tmp_path / 'stage'
    files = {'a.txt': b'A\n', 'd/e.txt': b'E\n', 'link': b'a.txt'}
    m = _manifest([_rec('100644', 'a.txt', files['a.txt']), _rec('100644', 'd/e.txt', b'E\n'),
                   _rec('120000', 'link', b'a.txt'), _rec('160000', 'sub')])
    for p, d in files.items():
        (top / p).parent.mkdir(parents=True, exist_ok=True)
        (top / p).write_bytes(d)
    (top / 'sub').mkdir()
    dot = top / '.git'
    for d in (('objects', 'info'), ('objects', 'pack'), ('refs', 'heads', 'archeus'),
              ('refs', 'tags')):
        (dot.joinpath(*d)).mkdir(parents=True)
    (dot / 'objects' / 'pack' / 'pack-1.pack').write_bytes(b'P')
    (dot / 'HEAD').write_bytes(b'ref: %s\n' % BRANCH.encode())
    (dot / 'config').write_bytes(local.SEED_CONFIG)
    (dot / 'shallow').write_bytes(REV.encode() + b'\n')
    (dot / 'index').write_bytes(b'DIRC')
    (dot / 'refs' / 'heads' / 'archeus' / 'm.t1').write_bytes(REV.encode() + b'\n')
    return top, dot, m


def test_a_good_staging_directory_passes_both_domains(tmp_path):
    top, dot, m = _staged(tmp_path)
    assert local._seed_walk(str(top), _Ample()) == m.expected()
    local._seed_meta(str(dot), BRANCH, REV, _Ample())


@pytest.mark.parametrize('plant', [
    ('hooks', 'post-checkout'), ('info', 'attributes'), ('objects', 'info', 'alternates'),
    ('objects', 'info', 'http-alternates'), ('commondir',), ('config.worktree',),
    ('logs', 'HEAD'), ('description',), ('FETCH_HEAD',), ('packed-refs',),
    ('refs', 'heads', 'other'), ('refs', 'replace', 'x')])
def test_metadata_core_did_not_make_refuses_the_seed(tmp_path, plant):
    top, dot, _m = _staged(tmp_path)
    p = dot.joinpath(*plant)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(REV.encode() + b'\n')
    with pytest.raises(StoreError):
        local._seed_meta(str(dot), BRANCH, REV, _Ample())


@pytest.mark.parametrize('name,data', [('HEAD', b'ref: refs/heads/main\n'),
                                       ('shallow', b'e' * 40 + b'\n'),
                                       ('config', local.SEED_CONFIG + b'[remote "o"]\n'),
                                       (os.path.join('refs', 'heads', 'archeus', 'm.t1'),
                                        b'e' * 40 + b'\n')])
def test_metadata_core_wrote_with_other_bytes_refuses_the_seed(tmp_path, name, data):
    top, dot, _m = _staged(tmp_path)
    (dot / name).write_bytes(data)
    with pytest.raises(StoreError, match='did not'):
        local._seed_meta(str(dot), BRANCH, REV, _Ample())


@pytest.mark.parametrize('case', ['tampered', 'extra-file', 'missing-file', 'extra-dir',
                                  'full-gitlink', 'other-link-text', 'nested-git', 'file-for-dir'])
def test_a_working_tree_that_is_not_the_trees_map_refuses_the_seed(tmp_path, case):
    """Accounting by domain, never by totals: a same-size edit is caught."""
    top, _dot, m = _staged(tmp_path)
    if case == 'tampered':
        (top / 'a.txt').write_bytes(b'B\n')
    elif case == 'extra-file':
        (top / 'd' / 'x').write_bytes(b'')
    elif case == 'missing-file':
        (top / 'd' / 'e.txt').unlink()
    elif case == 'extra-dir':
        (top / 'empty').mkdir()
    elif case == 'full-gitlink':
        (top / 'sub' / 'x').write_bytes(b'')
    elif case == 'other-link-text':
        (top / 'link').write_bytes(b'b.txt')
    elif case == 'nested-git':
        (top / 'd' / '.GIT').mkdir()
    else:
        (top / 'sub').rmdir()
        (top / 'sub').write_bytes(b'')
    assert local._seed_walk(str(top), _Ample()) != m.expected()


def test_a_hard_linked_working_file_refuses_the_seed(tmp_path):
    top, _dot, _m = _staged(tmp_path)
    os.link(str(top / 'a.txt'), str(tmp_path / 'outside'))
    with pytest.raises(StoreError, match='hard-linked'):
        local._seed_walk(str(top), _Ample())


# the node's seed entry points, refused with nothing started

@pytest.mark.parametrize('rev,branch', [('e' * 39, 'archeus/m.t'), ('E' * 40, 'archeus/m.t'),
                                        ('e' * 64, 'archeus/m.t'), ('e' * 40, 'a..b'),
                                        ('e' * 40, '-x'), ('e' * 40, 'a b'), ('e' * 40, '')])
def test_a_seed_core_does_not_build_is_refused_before_anything(spawns, child, rev, branch):
    with pytest.raises(StoreError, match='not a seed'):
        LocalNode.seed_workspace(ids.new_id('project'), ids.new_id('execution'), rev, branch,
                                 workdirs=())
    assert spawns.calls == [] and child.made == []
    assert not os.path.exists(paths.repos_dir())


@pytest.mark.parametrize('eid,commit', [('exe_x', 'e' * 40), (None, 'e' * 39),
                                        (None, 'HEAD')])
def test_a_seed_ref_core_does_not_write_is_refused_before_anything(spawns, eid, commit):
    with pytest.raises(StoreError):
        LocalNode.store_seed_ref(ids.new_id('project'), eid or ids.new_id('execution'), commit,
                                 workdirs=())
    assert spawns.calls == []


def test_a_first_attempt_takes_the_mission_branch_else_head(spawns, monkeypatch, tmp_path):
    root = _repo(tmp_path / 'u')
    calls = []

    def run(argv, **kw):
        calls.append(argv[-1])
        if argv[-1] == 'version':
            return SimpleNamespace(returncode=0, stdout='git version 2.49.0\n', stderr='')
        found = argv[-1] == 'HEAD^{commit}'
        return SimpleNamespace(returncode=0 if found else 1, stdout='1' * 40 + '\n' if found
                               else '', stderr='')
    monkeypatch.setattr(local.proc, 'run', run)
    assert LocalNode.resolve_base(root, 'archeus/m', workdirs=()) == ('HEAD', '1' * 40)
    assert calls == ['version', 'refs/heads/archeus/m^{commit}', 'HEAD^{commit}']
    calls.clear()
    with pytest.raises(StoreError, match='not a mission branch'):
        LocalNode.resolve_base(root, 'a..b', workdirs=())
    assert calls == []



# ── T-066 CHANGES r1: one shared deadline, aborted sinks, closed streams ───────

class _Ample:
    """A deadline that never runs out, for the checks tested for something else."""

    def left(self):
        return 1.0


@pytest.fixture
def clock(monkeypatch):
    """The seed's clock, under the test's hand."""
    now = [1000.0]
    monkeypatch.setattr(local, '_clock', lambda: now[0])
    return now


def test_the_seed_deadline_runs_out_once_its_seconds_have_passed(clock):
    d = local._Deadline('exe_x')
    assert d.left() == local.SEED_DEADLINE
    clock[0] += local.SEED_DEADLINE - 1
    assert d.left() == 1
    clock[0] += 1
    with pytest.raises(StoreError, match='exe_x ran past its deadline'):
        d.left()


def _expired(clock):
    d = local._Deadline('exe_x')
    clock[0] += local.SEED_DEADLINE
    return d


def test_every_python_check_of_a_seed_reads_the_deadline(clock, tmp_path):
    top, dot, _m = _staged(tmp_path)
    (tmp_path / 'dirs' / 'x').mkdir(parents=True)        # nothing to hash: the walk itself
    for check in (lambda d: local._seed_walk(str(top), d),
                  lambda d: local._seed_walk(str(tmp_path / 'dirs'), d),
                  lambda d: local._seed_meta(str(dot), BRANCH, REV, d),
                  lambda d: local._made(str(tmp_path), str(tmp_path / 'a' / 'b'), d)):
        with pytest.raises(StoreError, match='deadline'):
            check(_expired(clock))
    assert not (tmp_path / 'a').exists()                 # nothing made past it


def test_hashing_a_big_file_reads_the_deadline_per_mib(clock, tmp_path):
    p = tmp_path / 'big'
    p.write_bytes(b'x' * (3 << 20))
    d = local._Deadline('exe_x')
    reads = []

    def late():
        reads.append(1)
        if len(reads) == 2:
            clock[0] += local.SEED_DEADLINE
        return local._Deadline.left(d)
    d.left = late
    with pytest.raises(StoreError, match='deadline'):
        local._blob_id(str(p), 3 << 20, d)
    assert len(reads) == 2                    # refused at the first MiB read once it is late


@pytest.mark.parametrize('how', ['ok', 'stdin-unwritable', 'sink-refuses', 'child-fails',
                                 'timeout'])
def test_every_stream_the_byte_core_opened_is_closed_whatever_happened(child, how):
    code = {'child-fails': 1, 'stdin-unwritable': 'gone'}.get(how, 0)
    c = child.use(Child([b'a', b'b'], code=code, stall=how == 'timeout'))
    sink = Sink(refuse_at=1 if how == 'sink-refuses' else None)
    call = lambda: LocalNode.store_git('trusted', ['cat-file', '--batch'], workdirs=(),  # noqa
                                       git_dir=STORE(), stdin=b'q\n', sink=sink, timeout=0.3)
    if how in ('ok', 'stdin-unwritable'):
        call()
        assert not hasattr(sink, 'aborted')
    else:
        with pytest.raises(StoreError):
            call()
        assert sink.aborted
    assert c.closed == {'stdin', 'stdout', 'stderr'}


class _Opened:
    """`open` as `local` sees it, every file it hands out kept; with *fail_at*, the
    n-th file's write raises the way a full disk does."""

    def __init__(self, fail_at=None):
        self.files, self.fail_at = [], fail_at

    def __call__(self, path, mode='r', *a, **k):
        f = open(path, mode, *a, **k)
        self.files.append(f)
        if len(self.files) == self.fail_at:
            def full(data):
                raise OSError('no space left on the device')
            f.write = full
        return f


def _batch(*objs):
    return b''.join(b'%s blob %d\n%s\n' % (OID(d).encode(), len(d), d) for d in objs)


@pytest.mark.parametrize('case', ['truncated', 'write-error', 'timeout', 'wrong-content'])
def test_a_blob_stream_that_fails_leaves_no_file_open_and_keeps_its_error(child, monkeypatch,
                                                                          tmp_path, case):
    one, two = b'\xff\xfe\x00\x80\x00z', b'second blob\n'
    raw = _batch(one, two)
    chunks = {'truncated': [raw[:-5]], 'write-error': [raw], 'timeout': [raw[:-5]],
              'wrong-content': [raw.replace(b'second', b'SECOND')]}[case]
    c = child.use(Child(chunks, stall=case == 'timeout'))
    opened = _Opened(fail_at=2 if case == 'write-error' else None)
    monkeypatch.setattr(local, 'open', opened, raising=False)
    sink = local._Blobs([(OID(one), len(one), str(tmp_path / 'one')),
                         (OID(two), len(two), str(tmp_path / 'two'))])
    want = {'truncated': 'ended early', 'write-error': 'no space left',
            'timeout': 'past its deadline', 'wrong-content': 'not'}[case]
    with pytest.raises(OSError, match=want):
        LocalNode.store_git('trusted', ['cat-file', '--batch'], workdirs=(), git_dir=STORE(),
                            stdin=b'q\n', sink=sink, timeout=0.3)
    assert len(opened.files) == 2 and all(f.closed for f in opened.files)
    assert c.closed == {'stdin', 'stdout', 'stderr'} and c.killed.is_set()


def test_cleanup_that_fails_never_replaces_the_failure_it_runs_under(child):
    c = child.use(Child([b'a'], close_fails=True))

    class Failing(Sink):
        def feed(self, chunk):
            raise ValueError('the first failure')

        def abort(self):
            raise RuntimeError('the abort failed too')
    with pytest.raises(ValueError, match='the first failure'):
        LocalNode.store_git('trusted', ['cat-file', '--batch'], workdirs=(), git_dir=STORE(),
                            stdin=b'q\n', sink=Failing())
    assert c.closed == {'stdin', 'stdout', 'stderr'}



# ── K3 (T-067, T-051 §3-§4 + C-1013-T051): the import, with no process started ──

LINK, SUB, GITLINK_C = b'target.txt', 'sub', 'e' * 40


def _seedmap(*extra):
    """A seed: a.txt 100644, run.sh 100755, link 120000, sub 160000."""
    return _manifest([_rec('100644', 'a.txt', b'A\n'), _rec('100755', 'run.sh', b'R\n'),
                      _rec('120000', 'link', LINK), _rec('160000', SUB, oid=GITLINK_C)]
                     + list(extra))


def _workspace(tmp_path, **changes):
    """The seed as K2 leaves it on disk, then *changes*: name -> bytes, a dict for
    a directory (its entries), or None to delete."""
    work = tmp_path / 'work'
    work.mkdir()
    (work / '.git').mkdir()
    (work / '.git' / 'config').write_bytes(b'[core]\n\tfsmonitor = evil\n')
    tree = {'a.txt': b'A\n', 'run.sh': b'R\n', 'link': LINK, SUB: {}}
    tree.update(changes)

    def put(d, entries):
        for name, v in entries.items():
            if v is None:
                continue
            if isinstance(v, dict):
                (d / name).mkdir()
                put(d / name, v)
            else:
                (d / name).write_bytes(v)
    put(work, tree)
    return str(work)


def _plan(work, seed=None):
    plan, counts = local._import_plan(work, seed or _seedmap(), _Ample())
    return {p: (m, o) for m, p, o, _s in plan}, counts, plan


def test_an_unchanged_workspace_plans_exactly_its_seed(tmp_path):
    got, counts, _ = _plan(_workspace(tmp_path))
    assert got == {'a.txt': ('100644', None), 'run.sh': ('100755', None),
                   'link': ('120000', OID(LINK)), SUB: ('160000', GITLINK_C)}
    assert counts == {'deleted': 0, 'dropped_dirs': 0}


@pytest.mark.parametrize('change,want', [
    ({'link': None}, {'deleted': 1}), ({SUB: None}, {'deleted': 1}),
    ({'a.txt': b'edited\n'}, {}), ({'new.txt': b'target.txt'}, {}),
    ({'empty': {}}, {'dropped_dirs': 1}), ({'d': {'e': {}}}, {'dropped_dirs': 2})])
def test_the_seed_table_and_its_controls(tmp_path, change, want):
    got, counts, _ = _plan(_workspace(tmp_path, **change))
    assert counts == dict({'deleted': 0, 'dropped_dirs': 0}, **want)
    if 'a.txt' in change:
        assert got['a.txt'] == ('100644', None)              # the seed's mode, new bytes
    if 'new.txt' in change:
        assert got['new.txt'] == ('100644', None)            # never 120000 by its bytes
    for gone in [k for k, v in change.items() if v is None]:
        assert gone not in got


@pytest.mark.parametrize('change,why', [
    ({'link': b'/etc/passwd'}, 'seeded link link was changed'),
    ({'link': {}}, 'seeded link link was changed'),
    ({SUB: {'x': b'x'}}, 'seeded gitlink sub was changed'),
    ({SUB: {'.git': {}}}, 'seeded gitlink sub was changed'),
    ({SUB: b''}, 'seeded gitlink sub was changed'),
    ({'d': {'.GIT': {}}}, 'does not seed'), ({'d': {'git~1': {}}}, 'does not seed'),
    ({'aux.txt': b''}, 'does not seed')])
def test_an_edited_or_replaced_representation_or_a_nested_git_refuses(tmp_path, change, why):
    with pytest.raises(StoreError, match=why):
        _plan(_workspace(tmp_path, **change))


def test_the_root_git_is_skipped_by_name_and_never_read(tmp_path, monkeypatch):
    work = _workspace(tmp_path)
    os.rename(os.path.join(work, '.git'), os.path.join(work, 'GIT~1'))
    got, _c, _p = _plan(work)
    assert 'GIT~1' not in got and not any(p.startswith('.git') for p in got)


def _fake_lstat(monkeypatch, target, **attrs):
    """`os.lstat` answering *target* as the alias *attrs* describe, everything else as
    the disk does: no real link, junction or reparse point is made (T-067)."""
    real = os.lstat

    def lstat(path, *a, **k):
        st = real(path, *a, **k)
        if os.path.normcase(os.fspath(path)) != os.path.normcase(target):
            return st
        return SimpleNamespace(**dict({n: getattr(st, n) for n in dir(st)
                                       if n.startswith('st_')}, **attrs))
    monkeypatch.setattr(os, 'lstat', lstat)


@pytest.mark.parametrize('name', ['a.txt', 'link', SUB, 'd', os.path.join('d', 'f')])
@pytest.mark.parametrize('alias', ['symlink', 'junction', 'reparse-file', 'hard-link'])
def test_a_link_anywhere_refuses_the_import_and_is_never_followed(tmp_path, monkeypatch,
                                                                  name, alias):
    import stat as st_
    work = _workspace(tmp_path, d={'f': b'f'})
    attrs = {'symlink': {'st_mode': st_.S_IFLNK | 0o777},
             'junction': {'st_mode': st_.S_IFDIR | 0o777,
                          'st_file_attributes': st_.FILE_ATTRIBUTE_REPARSE_POINT},
             'reparse-file': {'st_file_attributes': st_.FILE_ATTRIBUTE_REPARSE_POINT},
             'hard-link': {'st_nlink': 2}}[alias]
    if alias == 'hard-link' and name in (SUB, 'd'):
        attrs = {'st_nlink': 2, 'st_mode': st_.S_IFREG | 0o644}   # a "directory" that is a file
    _fake_lstat(monkeypatch, os.path.join(work, name), **attrs)
    opened = []
    real_open = open
    monkeypatch.setattr(local, 'open', lambda p, *a, **k: (opened.append(p),
                                                           real_open(p, *a, **k))[1],
                        raising=False)
    with pytest.raises(OSError):
        _plan(work)
    assert os.path.join(work, name) not in opened


def test_a_name_that_is_not_utf8_refuses(tmp_path, monkeypatch):
    work = _workspace(tmp_path)
    real = os.listdir
    monkeypatch.setattr(os, 'listdir', lambda d: real(d) + ['bad\udc80'] if d == work
                        else real(d))
    with pytest.raises(StoreError, match='not UTF-8'):
        _plan(work)


def test_two_names_one_under_case_folding_refuse(tmp_path, monkeypatch):
    work = _workspace(tmp_path)
    (tmp_path / 'work' / 'X.txt').write_bytes(b'1')
    real = os.listdir
    monkeypatch.setattr(os, 'listdir', lambda d: real(d) + ['x.txt'] if d == work
                        else real(d))
    with pytest.raises(StoreError, match='case-insensitive'):
        _plan(work)


@pytest.mark.parametrize('bound,value,match', [('SEED_MAX_ENTRIES', 3, 'entries'),
                                               ('SEED_MAX_BYTES', 4, 'bytes'),
                                               ('SEED_MAX_DEPTH', 1, 'too deep')])
def test_a_bound_breached_by_the_walk_refuses(tmp_path, monkeypatch, bound, value, match):
    work, seed = _workspace(tmp_path, d={'f': b'f'}), _seedmap()
    monkeypatch.setattr(local, bound, value)
    with pytest.raises(StoreError, match=match):
        _plan(work, seed)


def test_the_walk_reads_the_deadline_at_every_entry(tmp_path):
    work = _workspace(tmp_path, d={'e': {}})
    reads = []

    class Counting:
        def left(self):
            reads.append(1)
            if len(reads) > 6:
                raise StoreError('ran past its deadline')
            return 1.0
    with pytest.raises(StoreError, match='deadline'):
        local._import_plan(work, _seedmap(), Counting())


# the stream: one commit on the seed, each file re-checked and hashed as it goes

def _stream_of(plan, sent=None):
    return b''.join(local._import_stream(ids.new_id('execution'), REV, plan, _Ample(),
                                         {} if sent is None else sent))


def test_the_stream_is_one_commit_on_the_seed_ending_with_done(tmp_path):
    work = _workspace(tmp_path, **{'n.bin': b'\x00\xff\x80\n'})
    _got, _c, plan = _plan(work)
    sent = {}
    raw = _stream_of(plan, sent)
    head, rest = raw.split(b'deleteall\n', 1)
    assert head.startswith(b'commit refs/archeus/exec/exe_') and b'/import\n' in head
    assert b'\nfrom %s\n' % REV.encode() in head and head.count(b'\ncommitter Archeus ') == 1
    assert rest.endswith(b'done\n')
    assert b'M 120000 %s link\n' % OID(LINK).encode() in rest
    assert b'M 160000 %s sub\n' % GITLINK_C.encode() in rest
    assert b'M 100644 inline n.bin\ndata 4\n\x00\xff\x80\n\n' in rest
    assert b'M 100755 inline run.sh\n' in rest
    assert sent == {'a.txt': ('100644', OID(b'A\n')), 'run.sh': ('100755', OID(b'R\n')),
                    'link': ('120000', OID(LINK)), SUB: ('160000', GITLINK_C),
                    'n.bin': ('100644', OID(b'\x00\xff\x80\n'))}


@pytest.mark.parametrize('how', ['replaced', 'grew', 'shrank'])
def test_a_file_that_is_not_the_one_walked_stops_the_stream_before_done(tmp_path, how):
    work = _workspace(tmp_path)
    _got, _c, plan = _plan(work)
    p = os.path.join(work, 'a.txt')
    if how == 'replaced':
        os.remove(p)
        with open(p, 'wb') as f:
            f.write(b'A\n')                     # same size, another file
    else:
        with open(p, 'wb' if how == 'shrank' else 'ab') as f:
            f.write(b'' if how == 'shrank' else b'more')
    chunks = []
    with pytest.raises(StoreError, match='changed after the walk|grew|shrank'):
        for c in local._import_stream(ids.new_id('execution'), REV, plan, _Ample(), {}):
            chunks.append(c)
    assert not b''.join(chunks).endswith(b'done\n')


def test_the_import_mode_runs_only_fast_import_under_the_whole_pin(spawns):
    _pin_, empty, cfg = _pin()
    store = paths.repo_store(ids.new_id('project'))
    argv, env, cwd = local._store_pin('import', store)
    assert argv[argv.index('--git-dir') + 1] == store and cwd == store
    assert '--no-replace-objects' in argv and set(env) <= ALLOWED_ENV
    for args in (['fetch'], ['update-ref', 'x', 'y'], ['cat-file', '--batch'], ['init']):
        with pytest.raises(StoreError, match='is not a'):
            LocalNode.store_git('import', args, workdirs=(), git_dir=store)
    assert spawns.calls == []


# the byte core carries the stream: chunks as produced, a producer's error is the failure

def test_the_byte_core_feeds_a_stream_of_chunks_in_order(child):
    c = child.use(Child([b'']))
    LocalNode.store_git('import', ['fast-import', '--done'], workdirs=(), git_dir=STORE(),
                        stdin=iter([b'one ', b'two ', b'done\n']), sink=Sink())
    assert c.written == b'one two done\n' and 'stdin' in c.closed


def test_a_stream_that_fails_while_produced_is_the_failure_and_kills_the_writer(child):
    c = child.use(Child([b''], stall=True))

    def produced():
        yield b'commit x\n'
        raise StoreError('a.txt changed after the walk')
    sink = Sink()
    with pytest.raises(StoreError, match='changed after the walk'):
        LocalNode.store_git('import', ['fast-import', '--done'], workdirs=(), git_dir=STORE(),
                            stdin=produced(), sink=sink, timeout=5)
    assert c.killed.is_set() and c.written == b'commit x\n' and sink.aborted
    assert c.closed == {'stdin', 'stdout', 'stderr'}


def test_fast_import_writing_to_stdout_refuses():
    with pytest.raises(StoreError, match='stdout'):
        local._Silent().feed(b'x')


@pytest.mark.parametrize('rev', ['e' * 39, 'E' * 40, 'e' * 64, 'HEAD'])
def test_an_import_onto_anything_but_a_commit_id_starts_nothing(spawns, child, rev):
    with pytest.raises(StoreError, match='not a seed Core imports onto'):
        LocalNode.import_workspace(ids.new_id('project'), ids.new_id('execution'), rev,
                                   workdirs=())
    assert spawns.calls == [] and child.made == []
