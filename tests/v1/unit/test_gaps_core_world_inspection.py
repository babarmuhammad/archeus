"""T-323: the ten highest-risk uncovered branches of archeus/core/world/inspection.py.

Fail-closed and denial paths first — a HEAD file the OS will not open, a `.git`
pointer that leads nowhere, a `git status` that fails, a manifest that cannot be
read, a tree that is not a directory — then the boundary values (the packed-refs
line that is almost the ref, the 80-character failure record, the nested
repository prefix, the requirement line cuts, the 40/64-hex SHA), then the error
paths that must become a note rather than a crash.

Style, fixtures and seams follow tests/v1/unit/test_world_units.py, with one
difference this container forces: `git` is not installed here, so nothing in this
file shells out. Every git answer arrives through the seams the existing tests
already use (`repos._git`, `repos.find_git_repos`) and every OS failure is faked
the way test_execution_units.py and test_pv20_isolation.py fake it (`builtins.open`,
`os.path.realpath`). Every file is written with explicit newlines and ASCII-only
names, no assertion reads an OS error message, and nothing is platform-skipped:
the same assertions hold on Linux and on Windows.
"""

import errno
import os
import pathlib

import pytest

from archeus.core.world import inspection
from claude_sessions import connections, repos

SHA_A = 'a' * 40
SHA_B = 'b' * 40
SHA_C = 'c' * 40


# ── the seams the existing tests use ────────────────────────────────────────

def _write(root, rel, text):
    """One file, exactly these bytes, the same on both platforms."""
    p = os.path.join(root, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return p


def _refuse(monkeypatch, *names):
    """`open` says no to files with these names. The errno and the message are
    ours, so no test has to read (or match) what a given OS calls EACCES."""
    real = open

    def deny(file, *a, **k):
        name = os.fspath(file) if isinstance(file, (str, bytes, os.PathLike)) else None
        if isinstance(name, str) and os.path.basename(name) in names:
            raise PermissionError(errno.EACCES, 'synthetic denial', name)
        return real(file, *a, **k)
    monkeypatch.setattr('builtins.open', deny)


@pytest.fixture
def git(monkeypatch):
    """`repos._git` — the only git inspection makes (`status --porcelain`) and
    the last resort of `head_revision` (`rev-parse HEAD`). A clean tree answers
    status and nothing answers anything else; every call is recorded."""
    calls = []

    def run(args, cwd, timeout=None):
        calls.append((list(args), cwd, timeout))
        return '' if list(args)[0] == 'status' else None
    monkeypatch.setattr(repos, '_git', run)
    return calls


@pytest.fixture
def no_subprocess(monkeypatch):
    """Fail if HEAD resolution falls back to `git rev-parse` — what a SHA from
    this test must have come from is the file it was written into."""
    def boom(*a, **k):
        raise AssertionError('HEAD was resolved with a subprocess')
    monkeypatch.setattr(repos, '_git', boom)


@pytest.fixture
def tree(tmp_path):
    """A working tree laid out for the nested-repository and manifest branches:
    `vendor/lib` (which a test names a repository of its own), siblings whose
    names merely start with that prefix, and one edge crossing the boundary."""
    root = str(tmp_path / 'proj')
    os.makedirs(root)
    for rel, text in {
        'app/__init__.py': '',
        'app/api/__init__.py': 'import app.core.models\n',
        'app/core/models.py': 'x = 1\n',
        'app/ui/view.py': 'import app.api\n',
        'vendor/lib/inner.py': 'import app.core.models\n',
        'vendor/library.py': 'import vendor.lib.inner\n',
        'vendor/librarian.py': 'z = 3\n',
        'README.md': '# proj\n',
        'docs/guide.md': 'guide\n',
    }.items():
        _write(root, rel, text)
    return root


@pytest.fixture
def nested(tree, monkeypatch):
    """`vendor/lib` is a submodule: `find_git_repos` names it (and the root
    itself), the graph is built over the whole tree, `inspect` must cut it out."""
    def found(root, *a, **k):
        return [root, os.path.join(root, 'vendor', 'lib')]
    monkeypatch.setattr(repos, 'find_git_repos', found)
    return 'vendor/lib'


# ── denial: the observation that cannot be taken (fail-closed) ───────────────

def test_a_denied_head_file_is_a_reason_and_never_a_guess(tmp_path, git, monkeypatch):
    """inspection.py:67-70 — `except OSError: head = ''`. The commit SHA is
    sitting in the loose ref, and it is still not used: without the ref name
    there is no way to know which ref it is, so the answer is a reason."""
    root = str(tmp_path / 'r')
    _write(root, '.git/HEAD', 'ref: refs/heads/main\n')
    _write(root, '.git/refs/heads/main', SHA_A + '\n')
    _refuse(monkeypatch, 'HEAD')
    with pytest.raises(inspection.Unreadable) as e:
        inspection.head_revision(root)
    assert e.value.reason == 'head_unresolvable'
    assert SHA_A not in str(e.value)
    assert [c[0][0] for c in git] == ['rev-parse']       # only the last resort left


@pytest.mark.parametrize('content,tail', [
    ('gitdir: .git/nowhere\n', 'empty HEAD'),      # the gitdir it points at is gone
    ('not a gitdir pointer\n', 'no .git'),         # a file where .git should be
], ids=['dangling-gitdir', 'not-a-gitdir-file'])
def test_a_git_pointer_that_leads_nowhere_is_a_reason_not_a_crash(tmp_path, git, content, tail):
    """inspection.py:65-66 and 67-70 — `.git` as a file: a `gitdir:` line to a
    directory that has gone, and a file that is not a gitdir pointer at all."""
    root = str(tmp_path / 'r')
    _write(root, '.git', content)
    with pytest.raises(inspection.Unreadable) as e:
        inspection.head_revision(root)
    assert e.value.reason == 'head_unresolvable'
    assert str(e.value).endswith(tail)


@pytest.mark.parametrize('written,tail', [
    ('', 'empty HEAD'),
    ('x' * 200, 'x' * 80),                          # the record is capped, not dumped
], ids=['empty-head', 'junk-head'])
def test_a_head_with_nothing_resolvable_in_says_only_what_it_can(tmp_path, git, written, tail):
    """inspection.py:97 — `head[:80] or 'empty HEAD'`: the failure the worker
    records quotes HEAD as found, bounded to 80 characters, and says
    `empty HEAD` when there was nothing to quote."""
    root = str(tmp_path / 'r')
    _write(root, '.git/HEAD', written)
    with pytest.raises(inspection.Unreadable) as e:
        inspection.head_revision(root)
    assert e.value.reason == 'head_unresolvable'
    assert str(e.value).endswith(tail)
    assert 'x' * 81 not in str(e.value)


def test_a_failed_git_status_leaves_the_tree_dirty_and_says_so(tree, monkeypatch):
    """inspection.py:259-260 and 270 — `status is None` is not `clean`: the
    note is written and `dirty` is True. A git that cannot answer must never
    hand the architecture machine a tree it believes is untouched."""
    monkeypatch.setattr(repos, '_git', lambda args, cwd, timeout=None: None)
    obs, _payload = inspection.inspect(tree)
    assert obs['dirty'] is True
    assert obs['notes'] == ['git status failed: the working tree is treated as dirty']


def test_a_tree_that_is_not_a_directory_is_reported_and_not_walked(tmp_path, git):
    """inspection.py:237-238 — `inspect` of a missing path and of a plain file:
    the reason is `repository_missing`, not an OSError from deep in the walk."""
    missing = str(tmp_path / 'gone')
    _write(str(tmp_path), 'afile/x.py', 'x = 1\n')
    for path in (missing, str(tmp_path / 'afile' / 'x.py')):
        with pytest.raises(inspection.Unreadable) as e:
            inspection.inspect(path)
        assert e.value.reason == 'repository_missing'
        assert path in str(e.value)
    assert git == []                                   # nothing was asked of git


def test_a_manifest_the_os_wont_let_us_read_is_a_note_and_the_pass_survives(
        tree, git, monkeypatch):
    """inspection.py:195-196 — the `except (OSError, ValueError)` inside the
    manifest loop: a denied pyproject.toml is named in `notes`, the other
    manifest still counts, and the inspection still completes."""
    _write(tree, 'pyproject.toml', '[project]\nname = "p"\ndependencies = ["fastapi>=0.110"]\n')
    _write(tree, 'requirements.txt', 'requests==2.31.0\n')
    _refuse(monkeypatch, 'pyproject.toml')
    obs, payload = inspection.inspect(tree)
    assert [n.split(':')[0] for n in obs['notes']] == ['pyproject.toml could not be read']
    assert [(d['name'], d['spec'], d['manifest']) for d in payload['dependencies']] == \
        [('requests', '==2.31.0', 'requirements.txt')]


def test_a_manifest_that_is_not_parseable_is_a_note_too(tree, git):
    """inspection.py:195-196 — the ValueError half of the same branch: half a
    package.json is reported by name, and `_commands` (inspection.py:202-205)
    draws no npm command from a file it cannot read."""
    _write(tree, 'package.json', '{"dependencies": {"react": "^19.0.0"}, ')
    _write(tree, 'requirements.txt', 'requests==2.31.0\n')
    obs, payload = inspection.inspect(tree)
    assert [n.split(':')[0] for n in obs['notes']] == ['package.json could not be read']
    assert [d['name'] for d in payload['dependencies']] == ['requests']
    assert obs['test_commands'] == [] and obs['build_commands'] == []


# ── boundary values: the answer that is almost right ────────────────────────

def _head_and_packed(root, *lines):
    """A gitdir with no loose ref at all, so the only answer can come from
    packed-refs."""
    _write(root, '.git/HEAD', 'ref: refs/heads/main\n')
    _write(root, '.git/packed-refs', '\n'.join(lines) + '\n')
    return root


def test_only_the_line_that_is_really_its_ref_gives_a_packed_sha(tmp_path, no_subprocess):
    """inspection.py:87-91 — the packed-refs scan has to pick the one line for
    its own ref out of a header, another branch, a non-SHA, a three-field
    peeled-tag line and a branch that merely starts with the name."""
    root = _head_and_packed(
        str(tmp_path / 'r'),
        '# pack-refs with: peeled fully-peeled sorted ',
        SHA_B + ' refs/heads/other',
        'z' * 40 + ' refs/heads/main',
        SHA_C + ' refs/heads/main peeled',
        SHA_A + ' refs/heads/main',
        SHA_C + ' refs/heads/main/nested',
        '^' + SHA_C,
    )
    assert inspection.head_revision(root) == SHA_A


@pytest.mark.parametrize('line', [
    SHA_B + ' refs/heads/other',                     # right shape, another branch
    SHA_A + 'z refs/heads/main',                     # 41 characters is not a commit
    (SHA_A * 2)[:63] + ' refs/heads/main',            # 63 is one short of 64
    SHA_A + ' refs/heads/main/nested',                # a name that only starts with ours
    SHA_A + ' refs/heads/main extra',                 # three fields
], ids=['other-branch', '41-hex', '63-hex', 'prefixed-name', 'three-fields'])
def test_a_packed_line_that_is_not_the_ref_is_not_a_commit(tmp_path, git, line):
    """inspection.py:90 — every guard on that line has to hold: a wrong SHA is
    worse than no SHA, because the whole inspection, its diff and its
    assessment are then filed under a revision that was never tested."""
    root = _head_and_packed(str(tmp_path / 'r'), line)
    with pytest.raises(inspection.Unreadable) as e:
        inspection.head_revision(root)
    assert e.value.reason == 'head_unresolvable'
    assert [c[0][0] for c in git] == ['rev-parse']


def test_rev_parse_is_asked_last_for_that_repository_with_that_deadline(tmp_path, monkeypatch):
    """inspection.py:94-96 — the fallback that answers when `.git` cannot: it
    must be `rev-parse HEAD` of the path we were given, with its 10 s timeout.
    The wrong cwd reads another repository's HEAD, and a missing timeout hangs
    the world worker on a git that will never answer."""
    root = str(tmp_path / 'r')
    _write(root, '.git/HEAD', 'ref: refs/heads/main\n')
    calls = []

    def run(args, cwd, timeout=None):
        calls.append((list(args), cwd, timeout))
        return SHA_A + '\n'
    monkeypatch.setattr(repos, '_git', run)
    assert inspection.head_revision(root) == SHA_A
    assert calls == [(['rev-parse', 'HEAD'], root, 10)]


@pytest.mark.parametrize('answer', [None, '', '  \n'], ids=['none', 'empty', 'blank'])
def test_a_silent_rev_parse_is_a_reason_not_a_crash(tmp_path, monkeypatch, answer):
    """inspection.py:94 — the `or ''` guard: a fallback that returns None has to
    surface as `head_unresolvable`, not as an AttributeError inside the worker's
    `head_revision` call."""
    root = str(tmp_path / 'r')
    _write(root, '.git/HEAD', 'ref: refs/heads/main\n')
    monkeypatch.setattr(repos, '_git', lambda args, cwd, timeout=None: answer)
    with pytest.raises(inspection.Unreadable) as e:
        inspection.head_revision(root)
    assert e.value.reason == 'head_unresolvable'


def test_a_sibling_of_a_nested_repository_is_not_cut_out_with_it(tree, nested, git):
    """inspection.py:226-227 and 240-248 — `rel == p or rel.startswith(p + '/')`
    and the two `in fileset` guards. Drop the '/' and `vendor/library.py`
    vanishes from the payload, which drift then reports as deleted files; drop
    the guards and an edge into the excluded submodule survives."""
    raw = {(e['source'], e['target'])
           for e in connections.build_hierarchy(tree, force=True)['dep_edges']}
    assert ('file:vendor/library.py', 'file:vendor/lib/inner.py') in raw   # the filter has work to do
    _obs, payload = inspection.inspect(tree)
    assert payload['nested'] == ['vendor/lib']                     # the root itself is not nested
    assert [f for f in payload['files'] if f.startswith('vendor/')] == \
        ['vendor/librarian.py', 'vendor/library.py']
    files = set(payload['files'])
    assert all(s in files and t in files for s, t in payload['edges'])
    assert ['vendor/library.py', 'vendor/lib/inner.py'] not in payload['edges']


def test_one_repository_behind_two_names_is_discovered_once(tmp_path, monkeypatch):
    """inspection.py:50 and 122-123 — `path_key` resolves links and `discover` keys
    on it, so the same repository seen through a junction or a second spelling
    is one Repository, and the first spelling is the one that is kept."""
    root = str(tmp_path / 'proj')
    alias = str(tmp_path / 'alias')
    for d in (root, alias):
        _write(d, '.git/HEAD', 'ref: refs/heads/main\n')
        _write(d, 'app.py', 'x = 1\n')
    real = os.path.realpath

    def resolves(p, *a, **k):
        p = os.fspath(p)
        if p == alias or p.startswith(alias + os.sep):
            p = os.path.join(root, *os.path.relpath(p, alias).split(os.sep))
        return real(p, *a, **k)
    monkeypatch.setattr(os.path, 'realpath', resolves)
    assert inspection.discover([root, alias]) == [(os.path.normpath(root), 'repo')]
    assert inspection.discover([alias, root]) == [(os.path.normpath(alias), 'repo')]


def test_a_path_object_is_refused_where_a_string_is_required(tmp_path):
    """inspection.py:111-112 — `isinstance(root, str)` refuses what
    `os.path.isabs` would accept: a repository handed in as a `Path` is a
    contract break at the caller, and discovering it anyway would quietly seed
    rows from a root the project never declared."""
    root = tmp_path / 'proj'
    _write(str(root), '.git/HEAD', 'ref: refs/heads/main\n')
    _write(str(root), 'app.py', 'x = 1\n')
    with pytest.raises(ValueError):
        inspection.discover([pathlib.Path(root)])


def test_a_directory_named_like_a_manifest_is_neither_a_note_nor_a_dependency(tree, git):
    """inspection.py:170-171 — the `isfile` gate: a *directory* called
    `package.json` is not a manifest. Without the gate the open fails as
    OSError and the loop writes a note about a manifest nobody wrote."""
    os.makedirs(os.path.join(tree, 'package.json'))
    os.makedirs(os.path.join(tree, 'requirements-x.txt'))
    obs, payload = inspection.inspect(tree)
    assert obs['notes'] == []
    assert payload['dependencies'] == []


@pytest.mark.parametrize('line,want', [
    ('requests ==2.31.0  # the pins we test with', ('requests', '==2.31.0')),
    ('rich[progress,theme]==13.0 ; python_version >= "3.10"', ('rich', '==13.0')),
    ('Fuzzy_Wuzzy~=1.2', ('fuzzy-wuzzy', '~=1.2')),
], ids=['comment', 'extras-and-marker', 'normalised-name'])
def test_a_requirement_line_keeps_only_the_name_and_the_spec(tree, git, line, want):
    """inspection.py:141-149 — the `#` cut, the `;` cut and `norm_package`.
    A spec that keeps its comment or its environment marker is compared
    character by character by `framework_pinned`, so an almost-right spec
    flips a satisfied constraint into a violated one and back."""
    _write(tree, 'requirements-dev.txt',
           '\n'.join(['# a heading', line, '-r base.txt', '--index-url not.a.host',
                      '!!! broken', '']) + '\n')
    _obs, payload = inspection.inspect(tree)
    got = [(d['name'], d['spec']) for d in payload['dependencies']]
    assert got == [want]
    assert [d['manifest'] for d in payload['dependencies']] == ['requirements-dev.txt']


def test_only_the_project_section_of_a_pyproject_is_a_dependency_list():
    """inspection.py:152-163 — the `[project]`-to-next-section boundary and the
    two early `return []`s: a tool section's `dependencies` array is not the
    project's even when `[project]` has none of its own (the regex reads with
    no TOML parser, so the section boundary is the only thing that keeps
    `[tool.poetry]` out of the dependency list and therefore out of drift)."""
    def names(text):
        return [(d['name'], d['spec']) for d in inspection._pyproject(text)]
    assert names('[tool.poetry]\ndependencies = ["ghost"]\n') == []
    assert names('[project]\nname = "p"\nversion = "1"\n') == []
    assert names('[project]\nname = "p"\n\n[tool.poetry]\ndependencies = ["ghost"]\n') == []
    assert names('[project]\ndependencies = [\n  "real>=1",   # keep\n]\n'
                 '[tool.black]\ndependencies = ["ghost"]\n') == [('real', '>=1')]
    assert names('[project]\ndependencies = [\'single-quoted==2\']\n') == [('single-quoted', '==2')]


@pytest.mark.parametrize('files,deps,want', [
    # a tests/ directory proves nothing on its own: it needs a manifest or setup.py
    ({'tests/test_a.py': 'def test_a(): pass\n'}, [], ([], [])),
    ({'tests/test_a.py': 'def test_a(): pass\n', 'setup.py': 'from setuptools import setup\n'},
     [], (['python -m pytest'], [])),
    ({'Cargo.toml': '[dependencies]\nserde = "1"\n', 'go.mod': 'module example.com/x\n'},
     [], (['cargo test', 'go test ./...'], ['cargo build', 'go build ./...'])),
    ({'package.json': '{"scripts": {"build": "tsc"}}\n'}, [], ([], ['npm run build'])),
    ({'package.json': '{"scripts": null}\n'}, [], ([], [])),           # `.get('scripts') or {}`
    ({}, [{'name': 'pytest', 'spec': '', 'manifest': 'pyproject.toml'}],
     (['python -m pytest'], [])),
], ids=['tests-dir-only', 'tests-and-setup-py', 'cargo-and-go', 'build-script-only',
        'null-scripts', 'pytest-as-a-dependency'])
def test_a_command_is_offered_only_for_what_the_tree_proves(tmp_path, files, deps, want):
    """inspection.py:200-223 — each command has its own precondition
    (`or {}` on a null scripts block, the `tests/`-and-manifest conjunction,
    the per-ecosystem pairs). A test command that does not exist is a run that
    fails for the wrong reason, and a missing one is an unverified release."""
    root = str(tmp_path / 'proj')
    os.makedirs(root)
    for rel, text in files.items():
        _write(root, rel, text)
    assert inspection._commands(root, deps) == want


# ── what the diff and the model feed are allowed to claim ───────────────────

def test_the_first_inspection_adds_no_models_and_later_ones_only_what_is_new():
    """inspection.py:31-34 — the `previous is None` baseline, the set difference
    and `sorted`: a first inspection is a baseline, not a burst of
    `repository.model_added` events, a schema file that was already there is not
    new just because the next inspection saw it again, and the list the digest
    quotes is the same list every run. `fnmatchcase` (not `fnmatch`) is what
    makes `Docs/Models/Notes.MD` not a model directory; on Linux the two are
    the same function, so only a Windows run can see that one go wrong."""
    base = {'files': ['app/core/usermodels.py', 'schema.prisma', 'docs/note.md']}
    assert inspection.models_added(None, base) == []
    later = {'files': base['files'] + ['app/models/new.py', 'app/db/schema.sql',
                                       'app/models/a.py', 'notes/models/x.md',
                                       'Docs/Models/Notes.MD']}
    assert inspection.models_added(base, later) == ['app/db/schema.sql', 'app/models/a.py',
                                                    'app/models/new.py', 'notes/models/x.md']


def test_a_dependency_change_is_named_by_name_and_only_by_name():
    """inspection.py:287-290 — `dependencies_added/removed/changed`: a spec that
    moved is `changed`, not an add plus a remove, and the names are sorted, so
    the digest that quotes them is stable."""
    before = {'files': ['a.py', 'b.py'],
              'dependencies': [{'name': 'fastapi', 'spec': '>=0.1'}, {'name': 'gone', 'spec': '1'}]}
    after = {'files': ['a.py', 'c.py', 'd.py'],
             'dependencies': [{'name': 'fastapi', 'spec': '>=0.2'}, {'name': 'new', 'spec': '1'}]}
    assert inspection.diff(before, after) == {
        'files_added': 2, 'files_removed': 1,
        'dependencies_added': ['new'], 'dependencies_removed': ['gone'],
        'dependencies_changed': ['fastapi']}


_BASE_OBS = {'test_commands': ['python -m pytest'], 'build_commands': [],
             'agent_config': [], 'frameworks': ['fastapi'], 'notes': []}
#: the same observation with one more test command and one more framework: the
#: only way `changed` can be right is if both lists are compared as they are
_MOVED_OBS = dict(_BASE_OBS, test_commands=['python -m pytest', 'npm test'],
                  frameworks=['fastapi', 'react'])


@pytest.mark.parametrize('prev_obs,obs,want', [
    (_MOVED_OBS, _BASE_OBS, ['test_commands', 'frameworks']),
    (_BASE_OBS, _BASE_OBS, None),               # nothing moved: no `changed` key at all
    (_MOVED_OBS, None, None),                   # half an observation names no change
    (None, _MOVED_OBS, None),
], ids=['two-changes', 'nothing-changed', 'no-observation', 'no-previous-observation'])
def test_an_observation_change_is_named_only_from_two_observations(prev_obs, obs, want):
    """inspection.py:291-294 — the `prev_obs is not None and obs is not None`
    guard and the four keys it compares. Comparing against `{}` when one side is
    missing would report every command list as changed on the first inspection,
    and dropping one key from the tuple would hide that kind of change forever."""
    payload = {'files': ['a.py'], 'dependencies': []}
    d = inspection.diff(payload, payload, prev_obs, obs)
    assert d.get('changed') == want
