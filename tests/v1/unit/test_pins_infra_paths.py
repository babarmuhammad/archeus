"""Hand-mutant pins for `archeus/infra/paths.py` (T-827): one test per condition
the existing suite would still pass if it were inverted, removed or loosened.
Each test names, in its assertion, the mutated code it would fail on."""

import os

import pytest

from archeus.core.domain import ids
from archeus.infra import paths


def test_a_leading_tilde_in_the_override_is_expanded(monkeypatch, tmp_path):
    # mutated: `path = explicit` (no expanduser) -> the '~' survives into abspath
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    got = paths.archeus_home({'ARCHEUS_HOME': '~/v1home'}, 'linux')
    assert got == os.path.join(str(tmp_path), 'v1home')


def test_a_relative_override_is_refused_not_bound_to_the_working_directory(monkeypatch, tmp_path):
    # mutated: drop the `os.path.isabs` guard -> abspath binds 'v1home' to the cwd
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match='absolute'):
        paths.archeus_home({'ARCHEUS_HOME': 'v1home'}, 'linux')


def test_an_absolute_override_is_normalised(tmp_path):
    # mutated: drop `os.path.abspath` -> the '..' survives into every derived path
    got = paths.archeus_home({'ARCHEUS_HOME': os.path.join(str(tmp_path), 'a', '..', 'v1home')},
                             'linux')
    assert got == os.path.join(str(tmp_path), 'v1home')


def test_a_backslash_separated_legacy_component_is_refused(tmp_path):
    # mutated: drop `.replace('\\', '/')` before the split -> on POSIX the whole
    # backslash string is one part and the '.archeus' inside it is never seen
    base = str(tmp_path)
    with pytest.raises(ValueError, match='legacy'):
        paths.archeus_home({'ARCHEUS_HOME': '%s/x\\.archeus\\v1' % base}, 'linux')
    got = paths.archeus_home({'ARCHEUS_HOME': '%s/x\\plain\\v1' % base}, 'linux')
    assert got == os.path.abspath('%s/x\\plain\\v1' % base)


def test_a_bytes_verifier_key_is_a_value_error_not_a_type_error():
    # mutated: drop `isinstance(key, str)` -> bytes.startswith(str) raises TypeError
    key = ('verify/%s.1' % ids.new_id('verification')).encode()
    for fn in (paths.verify_key_parts, paths.isolation_state, paths.verify_consumed):
        with pytest.raises(ValueError):
            fn(key)


@pytest.mark.parametrize('n', ['-1', '\uff11', '+1', '\u0661'],
                         ids=['minus', 'wide', 'plus', 'arabic'])
def test_a_non_canonical_attempt_is_refused(n):
    # mutated: drop `n.isdigit()` -> '-1' is accepted (`int('-1') < MAX_ATTEMPT`
    # and `'-1' == str(int('-1'))`) and names a `verify/<vid>.-1.json` record.
    # The non-ASCII digits are refused by the canonical-equal guard as long as it
    # stands; removing `n.isascii()` alone is an equivalent mutant (the equal
    # implies ASCII), so these cases pin that check only jointly with the equal.
    key = 'verify/%s.%s' % (ids.new_id('verification'), n)
    with pytest.raises(ValueError):
        paths.verify_key_parts(key)
    with pytest.raises(ValueError):
        paths.isolation_state(key)


def test_the_last_allowed_attempt_is_accepted_and_the_next_refused():
    # mutated: `int(n) < MAX_ATTEMPT` -> `int(n) < MAX_ATTEMPT - 1` (or `<=`, or
    # dropped) -> the accept-side or refuse-side assertion below fails
    vid = ids.new_id('verification')
    top = paths.MAX_ATTEMPT - 1
    key = 'verify/%s.%d' % (vid, top)
    assert paths.verify_key_parts(key) == (vid, top)
    assert paths.isolation_state(key) == os.path.join(paths.isolation_dir(), 'verify',
                                                      '%s.%d.json' % (vid, top))
    assert paths.verify_consumed(key) == os.path.join(paths.isolation_dir(), 'verify',
                                                      '%s.%d.consumed' % (vid, top))
    over = 'verify/%s.%d' % (vid, paths.MAX_ATTEMPT)
    with pytest.raises(ValueError):
        paths.verify_key_parts(over)
    with pytest.raises(ValueError):
        paths.verify_consumed(over)


def test_an_empty_run_argument_falls_back_to_the_run_dir(archeus_home):
    # mutated: `run or run_dir()` -> `run` (or `run and run_dir()`) -> run='' names
    # a relative `exec/<id>` outside ARCHEUS_HOME instead of the run dir's
    exe = ids.new_id('execution')
    p = paths.ExecPaths(exe, run='')
    assert p.dir == os.path.join(str(archeus_home), 'run', 'exec', exe)
    vid = ids.new_id('verification')
    v = paths.VerifyPaths(vid, 3, run='')
    assert v.dir == os.path.join(str(archeus_home), 'run', 'verify', vid, '3')
    assert v.out == os.path.join(v.dir, 'out.log')
