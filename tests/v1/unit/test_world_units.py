"""P4's pure parts over real git repositories (p4-design-gate §6.2–§6.4):
HEAD resolution, discovery, the deterministic pass, drift per constraint
kind, the constraint-set token and constraint validation."""

import os
import subprocess

import pytest

from archeus.core.domain import entities
from archeus.core.world import drift, inspection
from claude_sessions import repos
from v1.judge.support import FixtureRepo


def _git(path, *args):
    return FixtureRepo(path).git(*args)


@pytest.fixture
def py_repo(tmp_path):
    return FixtureRepo.create('layered-python', str(tmp_path))


@pytest.fixture
def no_subprocess(monkeypatch):
    """Fail if HEAD resolution falls back to `git rev-parse`."""
    def boom(*a, **k):
        raise AssertionError('HEAD was resolved with a subprocess')
    monkeypatch.setattr(repos, '_git', boom)


# ── HEAD from .git alone (§6.2) ──

def test_head_is_read_from_the_loose_ref(py_repo, no_subprocess):
    assert inspection.head_revision(py_repo.path) == py_repo.head()


def test_head_is_read_from_packed_refs(py_repo):
    want = py_repo.head()
    py_repo.git('pack-refs', '--all')
    assert not os.path.exists(os.path.join(py_repo.path, '.git', 'refs', 'heads', 'main'))
    real = repos._git
    repos._git = lambda *a, **k: (_ for _ in ()).throw(AssertionError('subprocess'))
    try:
        assert inspection.head_revision(py_repo.path) == want
    finally:
        repos._git = real


def test_a_detached_head_is_its_sha(py_repo, no_subprocess):
    sha = py_repo.head()
    py_repo.git('checkout', '-q', '--detach')
    assert inspection.head_revision(py_repo.path) == sha


def test_a_linked_worktree_resolves_through_the_common_dir(py_repo, tmp_path, no_subprocess):
    wt = str(tmp_path / 'wt')
    py_repo.git('worktree', 'add', '-q', '-b', 'feature', wt)
    FixtureRepo(wt).commit('on the worktree', {'app/w.py': 'w = 1\n'})
    assert inspection.head_revision(wt) == FixtureRepo(wt).head() != py_repo.head()


def test_a_submodule_resolves_through_its_gitdir_file(py_repo, tmp_path, no_subprocess):
    lib = FixtureRepo.create('layered-ts', str(tmp_path))
    py_repo.git('-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', lib.path, 'vendor/lib')
    sub = os.path.join(py_repo.path, 'vendor', 'lib')
    assert repos.classify(sub) == 'submodule'
    assert inspection.head_revision(sub) == lib.head()


@pytest.mark.parametrize('make,reason', [
    (lambda d: None, 'repository_missing'),
    (lambda d: os.makedirs(d), 'head_unresolvable'),
    (lambda d: (os.makedirs(d), subprocess.run(['git', 'init', '-q', d], check=True)),
     'head_unresolvable'),                                   # a repository with no commit
])
def test_an_unreadable_head_is_a_reason_not_a_guess(tmp_path, make, reason):
    d = str(tmp_path / 'r')
    make(d)
    with pytest.raises(inspection.Unreadable) as e:
        inspection.head_revision(d)
    assert e.value.reason == reason


# ── identity and discovery ──

def test_one_directory_is_one_key_however_it_is_spelled(py_repo):
    p = py_repo.path
    spellings = {p, p + os.sep, os.path.join(p, '.', ''), os.path.join(p, 'app', '..')}
    if os.name == 'nt':
        spellings |= {p.upper(), p.lower(), p.replace('\\', '/')}
    assert len({inspection.path_key(s) for s in spellings}) == 1


def test_discovery_finds_the_repo_and_its_submodule_but_not_its_worktree(py_repo, tmp_path):
    lib = FixtureRepo.create('layered-ts', str(tmp_path))
    py_repo.git('-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', lib.path, 'vendor/lib')
    wt = os.path.join(py_repo.path, 'wt')
    py_repo.git('worktree', 'add', '-q', '-b', 'feature', wt)
    got = dict((os.path.relpath(p, py_repo.path), k) for p, k in inspection.discover([py_repo.path]))
    assert got == {'.': 'repo', os.path.join('vendor', 'lib'): 'submodule'}
    assert inspection.discover([wt]) == [(os.path.normpath(wt), 'worktree')]


def test_the_same_root_twice_is_one_repository(py_repo):
    assert len(inspection.discover([py_repo.path, py_repo.path + os.sep])) == 1


@pytest.mark.parametrize('root', ['relative/path', None])
def test_a_root_must_be_an_absolute_directory(tmp_path, root):
    with pytest.raises(ValueError):
        inspection.discover([root])
    with pytest.raises(ValueError):
        inspection.discover([str(tmp_path / 'missing')])
    with pytest.raises(ValueError, match='no git repository'):
        inspection.discover([str(tmp_path)])
    with pytest.raises(ValueError):
        inspection.discover([])


# ── the deterministic pass (§6.3) ──

def test_the_python_fixture_is_observed(py_repo):
    obs, payload = inspection.inspect(py_repo.path)
    assert obs['languages'][0] == ['Python', 5]
    assert {d['name'] for d in obs['dependencies']} == {'fastapi', 'pydantic'}
    assert obs['frameworks'] == ['fastapi']
    assert obs['test_commands'] == ['python -m pytest'] and 'python -m build' in obs['build_commands']
    assert obs['docs'] == ['README.md'] and obs['dirty'] is False and obs['complete'] is True
    assert ['app/api/__init__.py', 'app/core/models.py'] in payload['edges']
    assert payload['extractor_version'] == inspection.EXTRACTOR_VERSION


def test_the_ts_fixture_is_observed(tmp_path):
    ts = FixtureRepo.create('layered-ts', str(tmp_path))
    obs, payload = inspection.inspect(ts.path)
    assert obs['test_commands'] == ['npm test'] and obs['build_commands'] == ['npm run build']
    assert set(obs['frameworks']) == {'react', 'vitest'}
    assert ['src/ui/app.ts', 'src/core/model.ts'] in payload['edges']


def test_a_dirty_tree_is_said_to_be(py_repo):
    with open(os.path.join(py_repo.path, 'app', 'core', 'new.py'), 'w') as f:
        f.write('x = 1\n')
    assert inspection.inspect(py_repo.path)[0]['dirty'] is True


def test_the_graph_cache_the_builder_writes_is_ignored_by_git(py_repo):
    """D8: `.archeus/connections-cache.json` is derived state, and it never
    makes the working tree dirty or moves HEAD."""
    head = py_repo.head()
    inspection.inspect(py_repo.path)
    assert os.path.isfile(os.path.join(py_repo.path, '.archeus', 'connections-cache.json'))
    assert py_repo.git('status', '--porcelain') == '' and py_repo.head() == head


def test_a_same_second_edit_is_seen(py_repo):
    """The builder's own cache key is (file count, whole-second mtime): an
    edit that keeps both — same file count, the newest mtime unchanged — must
    still be seen, so its cache is never trusted."""
    inspection.inspect(py_repo.path)
    src = [os.path.join(dp, f) for dp, _d, fs in os.walk(py_repo.path)
           if '.git' not in dp and '.archeus' not in dp for f in fs]
    newest = max(os.stat(p).st_mtime for p in src)
    target = os.path.join(py_repo.path, 'app', 'core', 'models.py')
    with open(target, 'w') as f:
        f.write('import app.api\n')
    os.utime(target, (newest, newest))
    edges = inspection.inspect(py_repo.path)[1]['edges']
    assert ['app/core/models.py', 'app/api/__init__.py'] in edges


def test_a_submodule_is_not_part_of_its_parent(py_repo, tmp_path):
    lib = FixtureRepo.create('layered-ts', str(tmp_path))
    py_repo.git('-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', lib.path, 'vendor/lib')
    py_repo.commit('add the submodule', {})
    payload = inspection.inspect(py_repo.path)[1]
    assert not [f for f in payload['files'] if f.startswith('vendor/lib/')]
    assert payload['nested'] == ['vendor/lib']


def test_the_diff_names_what_changed(py_repo):
    _o1, before = inspection.inspect(py_repo.path)
    py_repo.commit('more', {'app/core/extra.py': 'y = 2\n', 'README.md': None})
    _o2, after = inspection.inspect(py_repo.path)
    d = inspection.diff(before, after)
    assert (d['files_added'], d['files_removed']) == (1, 1)     # the walk includes docs
    assert inspection.diff(None, after) is None


# ── drift (§6.4): each kind, positive and negative ──

def _c(kind, spec, i=1, v=1, statement='s'):
    return {'id': 'kno_%026d' % i, 'version': v, 'statement': statement,
            'constraint': None if kind is None else {'kind': kind, 'spec': spec}}


P = {'files': ['app/api/__init__.py', 'app/core/models.py', 'app/ui/view.py'],
     'edges': [['app/api/__init__.py', 'app/core/models.py'],
               ['app/ui/view.py', 'app/api/__init__.py']],
     'dependencies': [{'name': 'fastapi', 'spec': '>=0.110', 'manifest': 'pyproject.toml'},
                      {'name': 'react', 'spec': '^19.3.0', 'manifest': 'package.json'}],
     'truncated': False}


@pytest.mark.parametrize('kind,spec,status', [
    ('forbid_dependency', {'from': 'app/core/**', 'to': 'app/api/**'}, 'satisfied'),
    ('forbid_dependency', {'from': 'app/api/**', 'to': 'app/core/**'}, 'violated'),
    ('require_layering', {'layers': ['app/ui/**', 'app/api/**', 'app/core/**']}, 'satisfied'),
    ('require_layering', {'layers': ['app/core/**', 'app/api/**']}, 'violated'),
    ('module_exists', {'path': 'app/core/*.py'}, 'satisfied'),
    ('module_exists', {'path': 'app/db/*.py'}, 'violated'),
    ('framework_pinned', {'package': 'FastAPI'}, 'satisfied'),
    ('framework_pinned', {'package': 'react', 'version': '19'}, 'satisfied'),
    ('framework_pinned', {'package': 'react', 'version': '18'}, 'violated'),
    ('framework_pinned', {'package': 'django'}, 'violated'),
    ('doc_matches_code', {'doc': 'docs/*.md', 'code': 'app/**'}, 'unchecked'),
    (None, None, 'unchecked'),
])
def test_each_kind_has_a_positive_and_a_negative(kind, spec, status):
    (f,) = drift.evaluate(P, [_c(kind, spec)])
    assert f['status'] == status, f
    if status == 'violated' and kind in ('forbid_dependency', 'require_layering'):
        assert f['violations'] and f['violation_count'] == len(f['violations'])


def test_a_truncated_graph_never_satisfies_an_edge_constraint():
    t = dict(P, truncated=True)
    (ok, bad, mod) = drift.evaluate(t, [
        _c('forbid_dependency', {'from': 'app/core/**', 'to': 'app/api/**'}, 1),
        _c('forbid_dependency', {'from': 'app/api/**', 'to': 'app/core/**'}, 2),
        _c('module_exists', {'path': 'app/db/*'}, 3)])
    assert (ok['status'], ok['reason']) == ('unchecked', 'graph_truncated')
    assert bad['status'] == 'violated'          # a violation seen is a violation
    assert mod['status'] == 'unchecked'


def test_the_token_names_ids_and_versions_not_order():
    a, b = _c('module_exists', {'path': 'x'}, 1), _c('module_exists', {'path': 'y'}, 2)
    assert drift.token([a, b]) == drift.token([b, a])
    assert drift.token([a]) != drift.token([a, b]) != drift.token([])
    assert drift.token([a]) != drift.token([dict(a, version=2)])


@pytest.mark.parametrize('constraint', [
    {'kind': 'forbid_dependency', 'spec': {'from': '/abs/**', 'to': 'b'}},
    {'kind': 'forbid_dependency', 'spec': {'from': '../up/**', 'to': 'b'}},
    {'kind': 'forbid_dependency', 'spec': {'from': 'C:/x', 'to': 'b'}},
    {'kind': 'forbid_dependency', 'spec': {'from': 'a\\b', 'to': 'b'}},
    {'kind': 'forbid_dependency', 'spec': {'from': 'a'}},
    {'kind': 'forbid_dependency', 'spec': {'from': 'a', 'to': 'b', 'extra': 1}},
    {'kind': 'require_layering', 'spec': {'layers': ['only-one']}},
    {'kind': 'framework_pinned', 'spec': {'package': ' '}},
    {'kind': 'teleport', 'spec': {}},
    {'kind': 'module_exists'},
])
def test_a_constraint_that_could_leave_the_repository_or_mean_nothing_is_refused(constraint):
    with pytest.raises(ValueError):
        entities.check_constraint(constraint)
