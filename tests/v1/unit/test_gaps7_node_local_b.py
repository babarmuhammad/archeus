"""T-1301: the highest-risk uncovered branches of `archeus/node/local.py` lines
**1859-1924 inclusive** (`_project_git`: the guarded argv, its environment and the
refusal pins), at the current branch tip. Every subprocess is a fake recorded by
`local.subprocess.run` or `local.proc.run_capped`; the Git executable is a synthetic
path under tmp_path, and the configuration freeze is the pass-through seam that
tests/conftest.py installs off Windows, copied here so the file behaves the same on
every platform. The real freeze is not reached: it belongs to test_gaps7_node_local_a.py.

Ten selected branches, ranked by risk:

1. local.py:1904 (`_frozen_config`'s `with`, the attribute lookup) — a failed
   `rev-parse --git-path info/attributes` refuses before enumeration or the request.
2. local.py:1909 — non-comment content in info/attributes refuses; comments and blank
   lines alone let the call run.
3. local.py:1915 — driver enumeration exit status 2 refuses; status 1 (no keys) allows.
4. local.py:1919 — each filter, merge and diff driver key becomes its own empty `-c`
   pin before the requested arguments, with its spelling kept.
5. local.py:1883 — the complete pin vector of the base argv, with no Windows metadata
   pin (no --git-dir, --work-tree or GIT_COMMON_DIR under the pass-through).
6. local.py:1877 — the child environment is built from an explicit synthetic set; the
   ambient GIT_CONFIG_COUNT and GIT_SSH sentinels never reach it.
7. local.py:1896 — a version below the floor or unparseable refuses before any repository
   call and is not cached, so it is asked again.
8. local.py:1890 — the capped final call keeps the whole argv and environment and passes
   timeout and max_bytes; the metadata calls stay uncapped.
9. local.py:1898 — the supported-version cache is keyed by executable path: an alternate
   executable is asked its version, a repeated one is not.
10. local.py:1923 — stdout and stderr decode with replacement, CRLF is preserved, and a
    nonzero CompletedProcess stays observable.

Closest existing tests: tests/v1/unit/test_repo_store.py::test_the_guarded_project_git_call_carries_the_whole_pin
(one complete argv, no driver keys, no failure branch) and tests/v1/unit/test_repo_config_freeze.py
(real Windows freeze only). No test here runs Git, the network or a Windows API.
"""

import contextlib
import os
import subprocess
import types

import pytest

from archeus.node import local

EXE_NAME = 'git'
FLOOR_OK = b'git version 2.49.0\n'


@pytest.fixture(autouse=True)
def _passthrough(monkeypatch, tmp_path):
    @contextlib.contextmanager
    def passthrough(root, argv, env, run, empty):
        yield argv
    passthrough._seam = True
    monkeypatch.setattr(local, '_frozen_config', passthrough)
    monkeypatch.setattr(local, '_VERSION', {})
    monkeypatch.setattr(local.proc, 'which', lambda name, path=None, avoid=(): EXE(tmp_path))


def EXE(tmp_path):
    return str(tmp_path / 'bin' / EXE_NAME)


def _root(tmp_path):
    root = str(tmp_path / 'repo')
    os.makedirs(root, exist_ok=True)
    return root


def _reply(argv, *, attrs=b'info/attributes\n', drivers=(0, b''), version=FLOOR_OK):
    if 'version' in argv:
        return 0, version, b''
    if 'rev-parse' in argv:
        return 0, attrs, b''
    if 'config' in argv:
        return drivers[0], drivers[1], b''
    return 0, b'OUT\r\n', b'ERR\r\n'


def _fake(monkeypatch, reply=_reply):
    calls = []

    def run(argv, **kw):
        calls.append((list(argv), kw))
        rc, out, err = reply(list(argv))
        return subprocess.CompletedProcess(argv, rc, out, err)
    monkeypatch.setattr(local.subprocess, 'run', run)
    return calls


def _has(argv, word):
    return word in argv


# ── 1 · a failed attribute lookup refuses (local.py:1904) ───────────────────

def test_a_failed_attribute_lookup_refuses_before_enumeration_or_the_request(tmp_path, monkeypatch):
    """local.py:1904 — `if where.returncode != 0 or not where.stdout.strip(): return None`.
    The lookup exits 128: the call is refused, and neither the driver enumeration nor
    the requested `status` is ever launched. Inverting or dropping the check would run
    the request on a repository whose attributes were never read."""
    calls = _fake(monkeypatch, lambda argv: (128, b'', b'') if _has(argv, 'rev-parse')
                  else _reply(argv))
    assert local._project_git(_root(tmp_path), ['status', '--porcelain']) is None
    assert [_has(a, 'rev-parse') for a, _ in calls] == [False, True]
    assert not any(_has(a, 'config') or _has(a, 'status') for a, _ in calls)


# ── 2 · only comments and blank lines in info/attributes allow (local.py:1909) ─

@pytest.mark.parametrize('content,allowed', [
    (b'# a comment\n\n   \n', True),
    (b'  * text=auto\n', False),
], ids=['comments_and_blanks', 'attribute_line'])
def test_non_comment_attributes_refuse_and_comments_alone_allow(tmp_path, monkeypatch,
                                                                content, allowed):
    """local.py:1909 — `if line.strip() and not line.lstrip().startswith(b'#')`. A file
    with only comments and blank lines sets no attribute, so the call runs; an indented
    attribute line still refuses, which a `line.startswith` test would miss."""
    root = _root(tmp_path)
    os.makedirs(os.path.join(root, 'info'))
    with open(os.path.join(root, 'info', 'attributes'), 'wb') as f:
        f.write(content)
    calls = _fake(monkeypatch)
    r = local._project_git(root, ['status', '--porcelain'])
    assert (r is not None) == allowed
    assert _has(calls[-1][0], 'status') == allowed
    assert any(_has(a, 'config') for a, _ in calls) == allowed


# ── 3 · driver enumeration: status 2 refuses, status 1 allows (local.py:1915) ─

@pytest.mark.parametrize('rc,allowed', [(2, False), (1, True)], ids=['status2', 'status1_no_keys'])
def test_driver_enumeration_status_two_refuses_and_one_means_no_keys(tmp_path, monkeypatch,
                                                                     rc, allowed):
    """local.py:1915 — `if drivers.returncode not in (0, 1): return None`. `git config
    --get-regexp` exits 1 when no key matches, which is no driver and a normal case; 2
    is a config error and the repository is refused."""
    calls = _fake(monkeypatch, lambda argv: _reply(argv, drivers=(rc, b'')))
    r = local._project_git(_root(tmp_path), ['status', '--porcelain'])
    assert (r is not None) == allowed
    assert _has(calls[-1][0], 'status') == allowed


# ── 4 · each driver key is emptied on the command line (local.py:1919) ──────

def test_each_driver_key_is_emptied_by_its_own_pin_before_the_requested_arguments(tmp_path,
                                                                                  monkeypatch):
    """local.py:1919 — `pins += ['-c', name.strip() + '=']` for every enumerated key, in
    enumeration order, before `list(args)`. The spellings are kept, and a driver named
    only by its key is emptied even though the repository sets it to a command."""
    keys = b'filter.lfs.clean\nmerge.x.driver\ndiff.y.textconv\n'
    calls = _fake(monkeypatch, lambda argv: _reply(argv, drivers=(0, keys)))
    local._project_git(_root(tmp_path), ['status', '--porcelain'])
    final = calls[-1][0]
    assert final[-8:] == ['-c', 'filter.lfs.clean=', '-c', 'merge.x.driver=', '-c',
                          'diff.y.textconv=', 'status', '--porcelain']


# ── 5 · the complete base pin vector (local.py:1883) ────────────────────────

def test_the_base_argv_pins_every_repository_setting_and_no_windows_metadata(tmp_path, monkeypatch):
    """local.py:1883 — the argv is `exe --no-replace-objects` followed by eleven `-c`
    pins, in this order. The hooks and attributes paths are the temporary directory's
    and are matched by prefix. Under the pass-through there is no --git-dir, --work-tree
    or GIT_COMMON_DIR: those belong to the real freeze, not to this argv."""
    calls = _fake(monkeypatch)
    local._project_git(_root(tmp_path), ['status', '--porcelain'])
    final, kw = calls[-1]
    assert final[0] == EXE(tmp_path) and final[1] == '--no-replace-objects'
    assert final[2:24:2] == ['-c'] * 11
    values = final[3:24:2]
    expected = ['core.hooksPath=', 'core.fsmonitor=false', 'core.attributesFile=',
                'merge.default=text', 'merge.verifySignatures=false', 'commit.gpgsign=false',
                'tag.gpgSign=false', 'submodule.recurse=false', 'gc.auto=0',
                'maintenance.auto=false', 'core.longpaths=true']
    assert len(values) == len(expected)
    for got, want in zip(values, expected):
        if want.endswith('='):
            assert got.startswith(want) and len(got) > len(want)
        else:
            assert got == want
    assert final[24:] == ['status', '--porcelain']
    assert not any(a.startswith('--git-dir') or a.startswith('--work-tree') for a in final)
    assert 'GIT_COMMON_DIR' not in kw['env']


# ── 6 · the child environment is explicit (local.py:1877) ───────────────────

def test_the_child_environment_is_built_from_explicit_keys_never_the_ambient_sentinels(
        tmp_path, monkeypatch):
    """local.py:1877 — the environment is the four Windows keys that are present plus the
    explicit set. Sentinels set here stand in for an ambient configuration that must not
    leak; the test asserts only which keys the child receives, never their values."""
    monkeypatch.setenv('GIT_CONFIG_COUNT', '1')
    monkeypatch.setenv('GIT_SSH', 'sentinel')
    calls = _fake(monkeypatch)
    local._project_git(_root(tmp_path), ['status', '--porcelain'])
    env = calls[-1][1]['env']
    explicit = {'PATH', 'HOME', 'XDG_CONFIG_HOME', 'GIT_CONFIG_NOSYSTEM', 'GIT_CONFIG_GLOBAL',
                'GIT_ATTR_NOSYSTEM', 'GIT_ATTR_SOURCE', 'GIT_TERMINAL_PROMPT',
                'GIT_ALLOW_PROTOCOL', 'GIT_PROTOCOL_FROM_USER', 'GIT_NO_LAZY_FETCH'}
    assert explicit <= set(env)
    assert set(env) - explicit <= {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}
    assert 'GIT_CONFIG_COUNT' not in env and 'GIT_SSH' not in env


# ── 7 · a version below the floor refuses and is not cached (local.py:1896) ──

@pytest.mark.parametrize('version', [b'git version 2.44.9\n', b'not a version\n'],
                         ids=['below_floor', 'malformed'])
def test_a_version_below_the_floor_refuses_before_any_repository_call_and_is_asked_again(
        tmp_path, monkeypatch, version):
    """local.py:1896 — `if not _at_floor(out): return None`, before `_VERSION[exe]` is
    set. Only the version call runs, nothing is cached, and a second call asks again."""
    calls = _fake(monkeypatch, lambda argv: _reply(argv, version=version))
    root = _root(tmp_path)
    assert local._project_git(root, ['status']) is None
    assert local._project_git(root, ['status']) is None
    assert [_has(a, 'version') for a, _ in calls] == [True, True]
    assert local._VERSION == {}


# ── 8 · the capped call keeps its pins and limits (local.py:1890) ───────────

def test_the_capped_final_call_keeps_the_whole_pin_and_env_and_metadata_stays_uncapped(
        tmp_path, monkeypatch):
    """local.py:1890 — `proc.run_capped(argv, cwd, env, timeout, max_bytes=cap)` for the
    requested command only. Its argv and environment equal those of the metadata call
    that preceded it, and its timeout is the default 60 s; the metadata calls go through
    `subprocess.run` with no cap."""
    capped = []

    def run_capped(argv, *, cwd=None, env=None, timeout=None, max_bytes=None):
        capped.append((list(argv), cwd, env, timeout, max_bytes))
        return subprocess.CompletedProcess(argv, 0, b'x', b'')
    monkeypatch.setattr(local.proc, 'run_capped', run_capped)
    calls = _fake(monkeypatch)
    r = local._project_git(_root(tmp_path), ['status'], max_bytes=64)
    assert r is not None and r.stdout == 'x'
    (argv, _cwd, env, timeout, max_bytes), = capped
    assert argv[-1] == 'status' and max_bytes == 64 and timeout == 60
    assert env == calls[-1][1]['env']
    assert all('max_bytes' not in kw for _, kw in calls)


# ── 9 · the version cache is keyed by executable (local.py:1898) ────────────

def test_the_version_is_asked_once_per_executable_path(tmp_path, monkeypatch):
    """local.py:1898 — `if exe not in _VERSION`. Two executables are each asked their
    version once; a repeat of the first is answered from the cache."""
    chosen = {'exe': EXE(tmp_path)}
    other = str(tmp_path / 'other' / EXE_NAME)
    monkeypatch.setattr(local.proc, 'which', lambda name, path=None, avoid=(): chosen['exe'])
    calls = _fake(monkeypatch)
    root = _root(tmp_path)
    local._project_git(root, ['status'])
    chosen['exe'] = other
    local._project_git(root, ['status'])
    chosen['exe'] = EXE(tmp_path)
    local._project_git(root, ['status'])
    versions = [a[0] for a, _ in calls if _has(a, 'version')]
    assert versions == [EXE(tmp_path), other]
    assert set(local._VERSION) == {EXE(tmp_path), other}


# ── 10 · decoding is lenient and CRLF survives (local.py:1923) ──────────────

def test_stdout_and_stderr_decode_with_replacement_keep_crlf_and_a_failure_stays_observable(
        tmp_path, monkeypatch):
    """local.py:1923 — the decode uses 'replace', so a stray 0xff becomes U+FFFD without
    losing the CRLF pairs, and a nonzero exit is returned as is, not turned into None."""
    def reply(argv):
        if _has(argv, 'status'):
            return 1, b'a\r\n\xff', b'e\r\n'
        return _reply(argv)
    _fake(monkeypatch, reply)
    r = local._project_git(_root(tmp_path), ['status'])
    assert r.returncode == 1
    assert r.stdout == 'a\r\n�'
    assert r.stderr == 'e\r\n'
