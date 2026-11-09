"""T-718: the highest-risk uncovered branches of `archeus/infra/paths.py`.

Style and fixtures follow `tests/v1/unit/test_paths.py`, the closest existing
test of this module: the `archeus_home` fixture of `tests/v1/conftest.py` gives
every test its own `ARCHEUS_HOME` under `tmp_path`, ids come from
`archeus.core.domain.ids`, and nothing touches the disk except where a branch
reads it (`_worktree` asks `os.path.isdir`, `fresh_call_dir` creates). No OS call is
faked here at all — every branch is reached with the values the function takes or
with real files under `tmp_path` — nothing here needs one platform over the other,
and nothing is written outside `tmp_path`.

The branches below were found by grepping `tests/v1` for every public name of
the module and reading what no test reaches. Each test names the source branch
whose removal or inversion it would catch. The worktree resolver's refusals
(task key, project and mission id) are covered in `test_paths.py`.

GAP 3   paths.py:68-71     the legacy .archeus refusal in any path spelling
GAP 4   paths.py:62-64     the same refusal for a home built from XDG/LOCALAPPDATA
GAP 5   paths.py:65-69     the refusal is component-exact, after the collapse
GAP 6   paths.py:53-71     an oversized ARCHEUS_HOME: whole, and still checked
GAP 7   paths.py:181-183   only an execution id names an execution record
GAP 8   paths.py:178-192   the execution and verifier record namespaces never meet
GAP 9   paths.py:166-171   one attempt, one key: a non-canonical attempt is refused
GAP 10  paths.py:169,290   the attempt bound and the one directory it names
GAP 11  paths.py:210,222   fresh_call_dir on a missing home / a file named `run`
GAP 12  paths.py:117,126   a project id names no seed directory, an execution id no store
"""

import os

import pytest

from archeus.core.domain import ids
from archeus.infra import paths


def _under(root, path):
    """True when the normalised `path` lies strictly under the normalised `root`."""
    r, p = os.path.normcase(os.path.normpath(root)), os.path.normcase(os.path.normpath(path))
    try:
        return os.path.commonpath([r, p]) == r and p != r
    except ValueError:                      # another drive: not under it
        return False


# ── GAP 3 to GAP 6: the legacy `.archeus` refusal, the only deletion guard here ──

@pytest.mark.parametrize('sep', ['/', '\\'], ids=['slash', 'backslash'])
def test_a_legacy_archeus_directory_is_refused_in_every_spelling(tmp_path, sep):
    """paths.py:68, `os.path.normcase(path).replace('\\', '/')`, and the raise at
    69-71: the component split happens on both separators, so a value written the
    other platform's way cannot smuggle a legacy directory through. Splitting on `/`
    alone lets `...\\.archeus\\v1` through on any platform, and legacy cleanup may
    delete below any directory named `.archeus`. Nothing is created: the value is
    judged as a string."""
    bad = sep.join([str(tmp_path), '.archeus', 'v1'])
    for plat in ('linux', 'win32', 'darwin'):
        with pytest.raises(ValueError, match='legacy'):
            paths.archeus_home({'ARCHEUS_HOME': bad}, plat)


@pytest.mark.parametrize('key,plat', [('XDG_DATA_HOME', 'linux'), ('LOCALAPPDATA', 'win32')],
                         ids=['xdg', 'localappdata'])
def test_a_home_built_from_a_hostile_environment_is_refused_too(tmp_path, key, plat):
    """paths.py:62-64 feed paths.py:69: the refusal covers the home the resolver
    builds itself, not only the one it was handed. Deleting the check into the
    `if explicit:` arm leaves these two defaults writable by legacy cleanup."""
    deep = os.path.join(str(tmp_path), '.archeus', 'data')
    with pytest.raises(ValueError, match='legacy'):
        paths.archeus_home({key: deep}, plat)


@pytest.mark.parametrize('leaf', ['.archeus-v1', 'archeus.legacy', 'my.archeus',
                                  '.archeus_backup'],
                         ids=['suffix', 'prefix', 'infix', 'underscore'])
def test_a_directory_that_merely_looks_like_the_legacy_one_is_not_refused(tmp_path, leaf):
    """paths.py:69, `if LEGACY_DIRNAME in parts` — a whole-component test, not a
    substring one. Invert it to `LEGACY_DIRNAME in os.path.normcase(path)` and every
    install under such a directory is refused (a denial of service, and the failure
    no test above can see)."""
    want = os.path.abspath(str(tmp_path / leaf))
    assert paths.archeus_home({'ARCHEUS_HOME': want}, 'linux') == want


def test_the_legacy_check_runs_on_the_collapsed_path(tmp_path):
    """paths.py:65 (`os.path.abspath`) before paths.py:68-69: a value that collapses
    *away* from a legacy directory is allowed and one that collapses *into* one is
    refused, so it is the resolved location that is judged. Catches: the check moved
    above line 65, or line 68 reading the raw `explicit` instead of `path`, which
    would make `..` able to walk the guard away."""
    allowed = os.path.join(str(tmp_path), '.archeus', 'p', '..', '..')      # -> tmp_path
    assert paths.archeus_home({'ARCHEUS_HOME': allowed}, 'linux') == os.path.abspath(tmp_path)
    refused = os.path.join(str(tmp_path), '.archeus', 'p', '..', 'v1')      # -> .archeus/v1
    with pytest.raises(ValueError, match='legacy'):
        paths.archeus_home({'ARCHEUS_HOME': refused}, 'linux')


def test_an_oversized_home_is_returned_whole_and_still_checked(tmp_path):
    """GAP 6, paths.py:53-71. A deep, long value is neither truncated nor exempt:
    `strip`, `expanduser`, `abspath` and the component split are all whole-string
    operations. Catches: any length cap or early return added to line 53-55, which
    would silently drop the tail of the path and, with it, the `.archeus` component
    that line 69 looks for."""
    deep = os.path.join(str(tmp_path), *['d%03d' % i for i in range(150)], 'x' * 200)
    got = paths.archeus_home({'ARCHEUS_HOME': deep}, 'linux')
    assert got == os.path.abspath(deep) and len(got) > 1000 and got.endswith('x' * 200)
    with pytest.raises(ValueError, match='legacy'):
        paths.archeus_home({'ARCHEUS_HOME': os.path.join(deep, '.archeus', 'v1')}, 'linux')


# ── GAP 7, GAP 8: Core's isolation records — who may name which file ──

@pytest.mark.parametrize('bad', ['', 'verify/', 'exe_' + '0' * 25, 'exe_' + '0' * 25 + 'O',
                                 '../../x', 'exe_../../x', 42, None],
                         ids=['empty', 'prefix-only', 'short', 'bad-char', 'relative',
                              'dots', 'number', 'none'])
def test_only_an_execution_id_names_an_execution_record(archeus_home, bad):
    """paths.py:181-182, `if not ids.is_id(key, 'execution'): raise ValueError`. The
    key becomes a file name under `run/isolation`, Core's own record of who holds
    which identity; an inversion of that guard (or reading `key` without the
    `isinstance` split at 178) would let a caller name a Core-owned file with `..`,
    a separator or a non-string, and a restarted Core would reconcile against a
    record an execution wrote."""
    with pytest.raises(ValueError):
        paths.isolation_state(bad)


def test_a_bare_verification_id_names_no_record_of_any_kind(archeus_home):
    """GAP 7, paths.py:181: the `verify/` prefix is what tells the two key kinds
    apart (paths.py:178), so a verification id on its own is neither a verifier
    key nor an execution id and must name nothing at all."""
    with pytest.raises(ValueError, match='not an execution id'):
        paths.isolation_state(ids.new_id('verification'))


def test_the_execution_and_verifier_record_namespaces_never_meet(archeus_home):
    """GAP 8, paths.py:178-183 and 191-192. An execution record is
    `<iso>/<id>.json`; a verifier's is `<iso>/verify/<vid>.<n>.json` beside its
    `.consumed` marker, never `<iso>/<vid>.<n>.json`. Catches: line 178 inverted to
    treat an un-prefixed key as a verifier key, or line 180 flattening `verify/`
    away — either lets an execution's own record path collide with the marker that
    says a verifier attempt was already admitted."""
    exe, vid = ids.new_id('execution'), ids.new_id('verification')
    iso = os.path.join(str(archeus_home), 'run', 'isolation')
    rec = paths.isolation_state(exe)
    key = '%s%s.%d' % (paths.VERIFY_KEY, vid, 3)
    ver, consumed = paths.isolation_state(key), paths.verify_consumed(key)
    assert os.path.dirname(rec) == iso
    assert not os.path.normcase(rec).startswith(os.path.normcase(os.path.join(iso, 'verify')))
    assert (os.path.dirname(ver), os.path.dirname(consumed)) == (os.path.join(iso, 'verify'),
                                                                 os.path.join(iso, 'verify'))
    assert (os.path.basename(ver), os.path.basename(consumed)) == ('%s.3.json' % vid,
                                                                    '%s.3.consumed' % vid)


@pytest.mark.parametrize('bad', ['execution', 'bare-verification-id', 'prefix-only',
                                 'number'],
                         ids=['execution', 'verification', 'prefix-only', 'number'])
def test_no_key_that_is_not_a_verifier_key_names_a_consumed_marker(archeus_home, bad):
    """GAP 8/9, paths.py:191 (`verify_key_parts(key)`, unguarded by the isinstance
    split at 178): an execution id, a bare verification id, the bare `verify/` prefix
    or a number name no `.consumed` marker. The marker is what makes a verifier
    attempt single-use, so a caller able to name one with an execution key could
    silence a verification before it started."""
    exe, vid = ids.new_id('execution'), ids.new_id('verification')
    key = {'execution': exe, 'bare-verification-id': vid, 'prefix-only': paths.VERIFY_KEY,
           'number': 3}[bad]
    with pytest.raises(ValueError, match='not a verifier key'):
        paths.verify_consumed(key)


@pytest.mark.parametrize('tail', ['.07', '.+7', '.7_0', '. 7', '.\u0661', '.\u00b2', '.7.1',
                                  '.', '.x', ''],
                         ids=['leading-zero', 'plus', 'digit-group', 'space', 'arabic-digit',
                              'superscript', 'two-dots', 'no-attempt', 'word', 'nothing'])
def test_one_verifier_attempt_has_exactly_one_key(archeus_home, tail):
    """GAP 9, paths.py:166-169: the `isinstance`/`startswith` split, then
    `ids.is_id(vid, 'verification') and n.isascii() and n.isdigit() and
    n == str(int(n)) and int(n) < MAX_ATTEMPT`. Each of these is load-bearing:
    without `isascii` an Arabic-Indic or superscript digit parses as a number
    (`str.isdigit` is not ASCII), and without `n == str(int(n))` the same attempt
    has two keys, `7` and `07` — two records, and a consumed marker that only
    ever covers one of them."""
    vid = ids.new_id('verification')
    with pytest.raises(ValueError, match='not a verifier key'):
        paths.verify_key_parts('%s%s%s' % (paths.VERIFY_KEY, vid, tail))
    assert paths.verify_key_parts('%s%s.%d' % (paths.VERIFY_KEY, vid, 7)) == (vid, 7)
    assert paths.verify_key_parts('%s%s.0' % (paths.VERIFY_KEY, vid)) == (vid, 0)


def test_a_key_that_is_not_a_string_is_refused_rather_than_raising_typeerror(archeus_home):
    """GAP 9, paths.py:166 (`isinstance(key, str)`) and 168-169 (no bare `int(n)`
    before the digit tests). Catches: dropping the isinstance guard — bytes would
    raise TypeError at `key.startswith`/`rpartition`, and `int('²')` would raise
    TypeError too, instead of the ValueError every caller here turns into a
    refusal."""
    for bad in (b'verify/ver_01J000000000000000000000000.1', 7.5, ['verify/'], {'a': 1}):
        with pytest.raises(ValueError, match='not a verifier key'):
            paths.verify_key_parts(bad)


def test_the_attempt_is_bounded_by_the_profile_name_cut(archeus_home):
    """GAP 10, paths.py:169-170: `int(n) < MAX_ATTEMPT`, the boundary value.
    `MAX_ATTEMPT - 1` is the last admissible attempt and `MAX_ATTEMPT` is refused;
    inverting `<` to `<=` (or deleting the bound) puts an unbounded attempt into
    the verifier profile name, which is what the 127-character cut cannot hold."""
    vid = ids.new_id('verification')
    last = '%s%s.%d' % (paths.VERIFY_KEY, vid, paths.MAX_ATTEMPT - 1)
    assert paths.verify_key_parts(last) == (vid, paths.MAX_ATTEMPT - 1)
    for over in (paths.MAX_ATTEMPT, paths.MAX_ATTEMPT + 1, 10 ** 30):
        with pytest.raises(ValueError, match='not a verifier key'):
            paths.verify_key_parts('%s%s.%d' % (paths.VERIFY_KEY, vid, over))


def test_one_attempt_names_one_verifier_directory_however_it_is_written(archeus_home):
    """GAP 10, paths.py:290-291: the attempt goes through `verify_key_parts` and the
    directory is named by the canonical `str(n)`, so `7` and `'7'` are the same
    attempt and `'07'`, `True`, `1.0`, `-1` and `None` name nothing. Two directories
    for one attempt would give one verifier two checkouts, and the consumed marker
    (named from the same key) would only ever block the first."""
    vid = ids.new_id('verification')
    base = os.path.join(str(archeus_home), 'run', 'verify', vid)
    want = os.path.join(base, '7')
    assert paths.VerifyPaths(vid, 7).dir == paths.VerifyPaths(vid, '7').dir == want
    p = paths.VerifyPaths(vid, 7)
    assert _under(base, p.dir) and all(_under(p.dir, x) for x in
                                       (p.out, p.checkout, p.home, p.tmp, p.config))
    for bad in ('07', True, 1.0, -1, None, 'seven'):
        with pytest.raises(ValueError, match='not a verifier key'):
            paths.VerifyPaths(vid, bad)


# ── GAP 11, GAP 12: the fail-closed disk reads ──

def test_a_missing_home_is_refused_and_never_created_by_the_call_directory(tmp_path,
                                                                           monkeypatch):
    """GAP 11, paths.py:222 (`_plain_dir(chain[0])` before any `makedirs`): with no
    `ARCHEUS_HOME` on disk the call directory is refused and NOTHING is created.
    Catches: line 222 deleted or moved after the loop at 223-225, which would let
    one own call silently mint a whole new data directory somewhere else."""
    missing = tmp_path / 'no-such-home'
    monkeypatch.setenv('ARCHEUS_HOME', str(missing))
    with pytest.raises(OSError):
        paths.fresh_call_dir(ids.new_id('route_decision'))
    assert not missing.exists()


def test_a_file_named_run_is_refused_and_untouched_by_the_call_directory(tmp_path,
                                                                         monkeypatch):
    """GAP 11, paths.py:223-225: `os.makedirs(d, exist_ok=True)` then `_plain_dir(d)`
    for `run` and for `run/calls`. `run` already exists as a *file* (a planted one,
    or a leftover): the call directory is refused as an OSError and the file is
    neither replaced nor followed. The existing tests of this function only fake
    `os.lstat`, so the real `makedirs` failure path below it is uncovered."""
    home = tmp_path / 'home'
    home.mkdir()
    run = home / 'run'
    run.write_bytes(b'planted\n')
    monkeypatch.setenv('ARCHEUS_HOME', str(home))
    with pytest.raises(OSError):
        paths.fresh_call_dir(ids.new_id('route_decision'))
    assert run.read_bytes() == b'planted\n'
    assert not os.path.exists(os.path.join(str(run), 'calls'))


@pytest.mark.parametrize('bad', ['', 'prj_' + '0' * 25, 'prj_' + '0' * 25 + 'U', '../store',
                                 'prj_x/../y', 42, None],
                         ids=['empty', 'short', 'bad-char', 'relative', 'dots', 'number',
                              'none'])
def test_only_a_project_id_names_a_store_and_only_an_execution_id_names_a_seed(bad):
    """GAP 12, paths.py:117-118 and 126-127: `repo_store` asks for a *project* id and
    `seed_staging` for an *execution* id, and each refuses the other's kind. Catches:
    either guard weakened to "any string" — the seed area and the stores are both
    under `repos/`, and it is the id check that keeps an execution from naming its
    own seed directory or a caller from naming a store outside it."""
    exe, pid = ids.new_id('execution'), ids.new_id('project')
    for name in (bad, exe, ids.new_id('mission')):            # not a project id
        with pytest.raises(ValueError, match='not a project id'):
            paths.repo_store(name)
    for name in (bad, pid, ids.new_id('mission')):            # not an execution id
        with pytest.raises(ValueError, match='not an execution id'):
            paths.seed_staging(name)


def test_a_seed_directory_and_a_store_never_name_one_another(archeus_home):
    """GAP 12, paths.py:119 and 128: the store is `repos/<pid>.git`, the seed is
    `repos/.seed/<exe>` — the `'%s.git'` suffix and the `.seed` parent are what keep
    an execution's staging directory from being read as a Core-owned store. Catches:
    dropping the `.git` suffix at 119, which would let a project id name a directory
    in the seed area."""
    pid, exe = ids.new_id('project'), ids.new_id('execution')
    store, seed = paths.repo_store(pid), paths.seed_staging(exe)
    repos = os.path.join(str(archeus_home), 'repos')
    assert os.path.dirname(store) == repos and os.path.basename(store) == '%s.git' % pid
    assert os.path.dirname(seed) == os.path.join(repos, '.seed')
    assert not _under(os.path.join(repos, '.seed'), store)
    assert not _under(store, seed)
