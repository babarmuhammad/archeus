import contextlib
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from archeus.node import local

pytestmark = pytest.mark.real_config_freeze
PLATFORM = ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP')
SENTINELS = {k: 'SYNTH-SENTINEL-' + k for k in PLATFORM}
LEAK_KEY = 'ARCHEUS_T1224_MUST_NOT_FORWARD'
LEAK_VALUE = 'SYNTH-SENTINEL-LEAK'

VERSION_OK = 'git version 2.49.0'
ATTRS = b'.git/info/attributes\n'
PINS = ('core.hooksPath=', 'core.fsmonitor=false', 'core.attributesFile=',
        'merge.default=text', 'merge.verifySignatures=false', 'commit.gpgsign=false',
        'tag.gpgSign=false', 'submodule.recurse=false', 'gc.auto=0',
        'maintenance.auto=false', 'core.longpaths=true')


def pinned_argv(exe, empty, none):
    argv = [exe, '--no-replace-objects']
    for c in (PINS[0] + empty, PINS[1], PINS[2] + none) + PINS[3:]:
        argv += ['-c', c]
    return argv


def user_args(call):
    return call.argv[call.argv.index(next(a for a in call.argv if a.startswith('--work-tree='))) + 1:]


@pytest.fixture(autouse=True)
def no_stray_version_cache():
    local._VERSION.clear()
    yield
    local._VERSION.clear()


@pytest.fixture
def repo(tmp_path):
    root = str(tmp_path / 'repo')
    os.makedirs(os.path.join(root, '.git', 'info'))
    with open(os.path.join(root, '.git', 'config'), 'w') as f:
        f.write('[core]\n\trepositoryformatversion = 0\n')
    return root


def completed(argv, returncode, stdout=b'', stderr=b''):
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def plant(path, text='planted\n'):
    with open(path, 'w') as f:
        f.write(text)
    return path


class FakeSys:
    def __init__(self, platform):
        self.platform = platform

    def __getattr__(self, name):
        return getattr(sys, name)


class Seam:
    def __init__(self, monkeypatch, tmp_path, root=None):
        self.monkeypatch = monkeypatch
        self.tmp = str(tmp_path)
        self.root = root
        self.exe = os.path.join(self.tmp, 'pin', 'git')
        self.asked = []
        self.ran = []
        self.capped = []
        self.temp_dirs = []
        self.temp_args = []
        self.guards = []
        self.answers = {}
        self.which_result = self.exe
        self.which_fn = self._which_default
        self.gitdir = os.path.join(root or self.tmp, '.git')
        monkeypatch.setattr(local.proc, 'which', self._which)
        monkeypatch.setattr(local.proc, 'run_capped', self._run_capped)
        monkeypatch.setattr(local, 'subprocess', SimpleNamespace(
            run=self._run, DEVNULL=subprocess.DEVNULL, Popen=self._popen_unreachable,
            TimeoutExpired=subprocess.TimeoutExpired))
        monkeypatch.setattr(local, 'tempfile', SimpleNamespace(TemporaryDirectory=self._temp))
        monkeypatch.setattr(local, '_VERSION', {})
        monkeypatch.setattr(local, '_frozen_config', self._guard)
        monkeypatch.setattr(local, 'sys', FakeSys('win32'))
    def _which(self, name, path=None, avoid=()):
        self.asked.append(SimpleNamespace(name=name, path=path, avoid=list(avoid or ())))
        return self.which_fn(name, path=path, avoid=list(avoid or ()))

    def _which_default(self, name, path=None, avoid=()):
        return self.which_result

    def _run(self, argv, **kw):
        kw = dict(kw, env=dict(kw['env']))
        self.ran.append(SimpleNamespace(argv=[str(a) for a in argv], kind=self.kind(argv),
                                        cwd=kw.get('cwd'), env=kw.get('env'),
                                        timeout=kw.get('timeout'), kw=kw))
        return self._answer(self.ran[-1])

    def _run_capped(self, argv, **kw):
        kw = dict(kw, env=dict(kw['env']))
        self.capped.append(SimpleNamespace(argv=[str(a) for a in argv], kind=self.kind(argv),
                                           cwd=kw.get('cwd'), env=kw.get('env'),
                                           timeout=kw.get('timeout'), max_bytes=kw.get('max_bytes'),
                                           kw=kw))
        return self._answer(self.capped[-1])

    def _popen_unreachable(self, *a, **k):
        raise AssertionError('the guarded runner started a real child: %r' % (a[:1],))

    def _temp(self, **kw):
        path = os.path.join(self.tmp, 'empty-%d' % (len(self.temp_dirs) + 1))
        os.makedirs(path)
        self.temp_dirs.append(path)
        self.temp_args.append(dict(kw))
        return contextlib.nullcontext(path)

    def _guard(self, root, argv, env, run, empty):
        self.guards.append(SimpleNamespace(root=root, argv=list(argv), env=dict(env),
                                           run=run, empty=empty,
                                           temp_kwargs=dict(self.temp_args[-1])))
        run(argv + ['config', '--no-includes', '--file', os.path.join(self.gitdir, 'config'),
                    '--name-only', '--get-regexp', local._INCLUDE_KEYS], root)
        env['GIT_COMMON_DIR'] = self.gitdir
        return contextlib.nullcontext(list(argv) + ['--git-dir=' + self.gitdir,
                                                     '--work-tree=' + root])
    def kind(self, argv):
        last = argv[-1] if argv else ''
        if '--file' in argv:
            return 'include'
        if '--get-regexp' in argv:
            return 'drivers'
        if 'info/attributes' in last:
            return 'attrs'
        if last == 'version':
            return 'version'
        return 'command'

    def _answer(self, call):
        answer = self.answers.get(call.kind, self._default)
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer):
            answer = answer(call.argv)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def _default(self, argv):
        kind = self.kind(argv)
        out = {'version': (VERSION_OK + '\n').encode(), 'attrs': ATTRS, 'drivers': b'',
               'include': b'', 'path': self.gitdir.encode() + b'\n', 'command': b''}[kind]
        return completed(argv, 1 if kind in ('drivers', 'include') else 0, out, b'')
    def argvs(self, channel='subprocess'):
        return [c.argv for c in (self.ran if channel == 'subprocess' else self.capped)]

    def kinds(self, channel='subprocess'):
        return [c.kind for c in (self.ran if channel == 'subprocess' else self.capped)]

    def force_windows(self):
        self.monkeypatch.setattr(local, 'sys', FakeSys('win32'))

    def command_call(self, channel='subprocess'):
        calls = [c for c in (self.ran if channel == 'subprocess' else self.capped)
                 if c.kind == 'command']
        assert calls, 'the guarded command never ran: %r' % (self.kinds(),)
        return calls[-1]


@pytest.fixture
def seam(monkeypatch, tmp_path, repo):
    for k, v in SENTINELS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv(LEAK_KEY, LEAK_VALUE)
    monkeypatch.setenv('HOME', str(tmp_path / 'synthetic-home'))
    return Seam(monkeypatch, tmp_path, root=repo)


def test_a_refused_executable_is_refused_before_the_pin_is_made(seam):
    seam.which_fn = lambda name, **kw: None
    assert local._project_git(seam.root, ['status', '--porcelain']) is None
    assert len(seam.asked) == 1 and seam.asked[0].name == 'git'
    assert seam.ran == [] and seam.capped == []
    assert seam.temp_dirs == []
    assert local._VERSION == {}


def _which_honouring_avoid(dirs):
    def which(name, path=None, avoid=()):
        if os.path.dirname(name):
            return None
        norm = lambda p: os.path.normcase(os.path.abspath(p))
        barred = [norm(a) for a in avoid if a]
        for d in dirs:
            p = os.path.join(d, name)
            if any(norm(p) == b or norm(p).startswith(b + os.sep) for b in barred):
                continue
            if os.path.isfile(p):
                return os.path.abspath(p)
        return None
    return which


def test_the_executable_is_sought_outside_the_repository(seam):
    root = seam.root
    inside = os.path.join(root, 'bin')
    outside = os.path.join(seam.tmp, 'bindir')
    for d in (inside, outside):
        os.makedirs(d)
    plant(os.path.join(inside, 'git'), '# planted inside the repository\n')
    seam.which_fn = _which_honouring_avoid([inside, outside])

    assert local._project_git(root, ['status', '--porcelain']) is None
    assert len(seam.asked) == 1 and seam.asked[0].name == 'git' and seam.asked[0].path is None
    assert [os.path.normcase(a) for a in seam.asked[0].avoid] == [os.path.normcase(root)]
    assert seam.ran == [] and seam.capped == []
    plant(os.path.join(outside, 'git'), '# planted outside\n')
    assert local._project_git(root, ['status', '--porcelain']) is not None
    asked_exe = {c.argv[0] for c in seam.ran}
    assert asked_exe == {os.path.join(outside, 'git')}
    assert not any(os.path.normcase(a.argv[0]).startswith(os.path.normcase(root) + os.sep)
                   for a in seam.ran)


@pytest.mark.parametrize('reported, accept', [
    pytest.param(b'git version 2.39.0\n', False, id='older-than-the-floor'),
    pytest.param(('git version %d.%d.%d\n' % (local.STORE_GIT_FLOOR[0],
                                              local.STORE_GIT_FLOOR[1] - 1,
                                              local.STORE_GIT_FLOOR[2])).encode(),
                 False, id='one-minor-below'),
    pytest.param(b'not git at all\n', False, id='not-a-version'),
    pytest.param(('git version %d.%d.%d\n' % local.STORE_GIT_FLOOR).encode(), True,
                 id='exactly-the-floor'),
    pytest.param(('git version %d.%d.%d\n' % (local.STORE_GIT_FLOOR[0] + 4,
                                              local.STORE_GIT_FLOOR[1],
                                              local.STORE_GIT_FLOOR[2] + 1)).encode(),
                 True, id='above-the-floor'),
])
def test_a_git_below_the_floor_is_refused_and_not_cached(seam, repo, reported, accept):
    seam.answers['version'] = lambda argv: completed(argv, 0, reported, b'')
    first = local._project_git(repo, ['status', '--porcelain'])
    second = local._project_git(repo, ['status', '--porcelain'])
    asked = [a for a in seam.argvs() if a[-1] == 'version']
    assert seam.capped == []
    if accept:
        assert first is not None and second is not None and first.returncode == 0
        assert dict(local._VERSION) == {seam.exe: reported.decode().strip()}
        assert len(asked) == 1
        assert seam.ran[0].kind == 'version' and seam.ran[0].cwd == seam.temp_dirs[0]
        assert seam.ran[0].env['HOME'] == seam.temp_dirs[0]
        assert seam.ran[0].env['PATH'] == os.path.dirname(seam.exe)
        assert seam.ran[0].kw['capture_output'] is True
    else:
        assert first is None and second is None
        assert dict(local._VERSION) == {}
        assert asked == [[seam.exe, 'version']] * 2
        assert seam.kinds() == ['version'] * 2


@pytest.mark.parametrize('boom', [
    pytest.param(lambda argv: OSError(2, 'cannot start'), id='oserror'),
    pytest.param(lambda argv: subprocess.TimeoutExpired(argv, 60), id='timeout'),
])
def test_a_child_that_cannot_start_or_times_out_leaves_nothing_behind(seam, repo, boom):
    seam.answers['command'] = boom
    assert local._project_git(repo, ['status', '--porcelain']) is None
    assert set(seam.kinds()) == {'version', 'include', 'attrs', 'drivers', 'command'}
    assert seam.capped == []
    assert seam.command_call().argv[-2:] == ['status', '--porcelain']
    assert local._VERSION[seam.exe] == VERSION_OK


def expected_pin_env(empty, exe, extra=()):
    env = {k: SENTINELS[k] for k in PLATFORM if k in os.environ}
    env.update(PATH=os.path.dirname(exe), HOME=empty, XDG_CONFIG_HOME=empty,
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.path.join(empty, 'none'),
               GIT_ATTR_NOSYSTEM='1', GIT_ATTR_SOURCE=local.EMPTY_TREE,
               GIT_TERMINAL_PROMPT='0', GIT_ALLOW_PROTOCOL='file',
               GIT_PROTOCOL_FROM_USER='0', GIT_NO_LAZY_FETCH='1')
    env.update(extra)
    return env


def test_the_windows_guard_runs_inside_the_pinned_environment(seam, repo):
    seam.force_windows()
    seam.answers['command'] = lambda argv: completed(argv, 0, b'ok\n', b'')
    assert local._project_git(repo, ['status', '--porcelain']) is not None

    guard, = seam.guards
    assert guard.root == repo and guard.empty == seam.temp_dirs[0]
    assert guard.temp_kwargs == {'ignore_cleanup_errors': True}
    empty, none = guard.empty, os.path.join(guard.empty, 'none')
    assert guard.argv == pinned_argv(seam.exe, empty, none)
    assert guard.env == expected_pin_env(empty, seam.exe)
    include = [c for c in seam.ran if c.kind == 'include']
    assert len(include) == 1 and include[0].cwd == repo
    assert include[0].env == expected_pin_env(empty, seam.exe)
    assert include[0].timeout == 60

    call = seam.command_call()
    want_env = expected_pin_env(empty, seam.exe, extra={'GIT_COMMON_DIR': seam.gitdir})
    assert call.env == want_env and set(call.env) == set(want_env)
    assert call.cwd == repo and call.timeout == 60
    assert call.kw['capture_output'] is True and call.kw['stdin'] is subprocess.DEVNULL
    assert call.kw['creationflags'] == local.proc.no_window_flags
    assert call.argv == pinned_argv(seam.exe, empty, none) + [
        '--git-dir=' + seam.gitdir, '--work-tree=' + repo] + ['status', '--porcelain']
    assert LEAK_KEY not in call.env
    assert call.env['HOME'] == empty and call.env['PATH'] == os.path.dirname(seam.exe)


@pytest.mark.parametrize('stdout, code, text, dirty', [
    pytest.param(b'', 0, '', False, id='clean'),
    pytest.param(b' M f.txt\n', 0, ' M f.txt\n', True, id='modified'),
    pytest.param(b'  \n', 0, '  \n', False, id='whitespace-is-clean'),
    pytest.param(b'', 128, None, None, id='failed'),
])
def test_the_stdout_of_a_clean_command_is_empty_and_of_a_failed_one_none(
        seam, repo, stdout, code, text, dirty):
    seam.answers['command'] = lambda argv: completed(argv, code, stdout, b'fatal: probe\n')
    assert local._project_git_text(repo, ['status', '--porcelain']) == text
    assert local.LocalNode.git_dirty(repo) is dirty
    assert local.LocalNode.git_dirty(repo, tracked_only=True) is dirty
    assert [user_args(c) for c in seam.ran if c.kind == 'command'] == [
        ['status', '--porcelain'], ['status', '--porcelain=v1'],
        ['status', '--porcelain=v1', '--untracked-files=no']]


@pytest.mark.parametrize('raw, cached', [
    pytest.param(b'git version 2.49.0 (build \xff\xfe)\n',
                 'git version 2.49.0 (build \ufffd\ufffd)', id='above-the-floor'),
    pytest.param(b'git version 2.49.\xff\n', None, id='undecodable-number'),
])
def test_a_version_that_is_not_utf8_is_replaced_and_then_judged(seam, repo, raw, cached):
    seam.answers['version'] = lambda argv: completed(argv, 0, raw, b'')
    seam.answers['command'] = lambda argv: completed(argv, 0, b'ok\n', b'')
    r = local._project_git(repo, ['status', '--porcelain'])
    assert local._VERSION.get(seam.exe) == cached
    assert seam.ran[0].env == expected_pin_env(seam.temp_dirs[0], seam.exe)
    assert seam.ran[0].env['GIT_CONFIG_NOSYSTEM'] == '1'
    assert seam.ran[0].env['GIT_CONFIG_GLOBAL'] == os.path.join(seam.temp_dirs[0], 'none')
    if cached is None:
        assert r is None and seam.kinds() == ['version']
    else:
        assert r is not None and r.returncode == 0 and r.stdout == 'ok\n'
        assert '\ufffd' in local._VERSION[seam.exe]


def test_the_version_is_asked_once_per_executable(seam, repo):
    other = os.path.join(seam.tmp, 'other', 'git')
    seam.which_result = seam.exe
    assert local._project_git(repo, ['status', '--porcelain']) is not None
    assert local._project_git(repo, ['status', '--porcelain']) is not None
    assert seam.argvs()[:1] == [[seam.exe, 'version']]
    assert seam.kinds().count('version') == 1
    assert local._VERSION == {seam.exe: VERSION_OK}

    seam.which_result = other
    assert local._project_git(repo, ['status', '--porcelain']) is not None
    assert [a[0] for a in seam.argvs() if a[-1] == 'version'] == [seam.exe, other]
    assert set(local._VERSION) == {seam.exe, other}
    before = len(seam.ran)
    assert local._project_git(repo, ['status', '--porcelain']) is not None
    assert set(c.kind for c in seam.ran[before:]) == {'include', 'attrs', 'drivers', 'command'}
    assert seam.ran[-1].env == expected_pin_env(
        seam.temp_dirs[-1], other, extra={'GIT_COMMON_DIR': seam.gitdir})
    assert seam.ran[-1].env['GIT_ATTR_SOURCE'] == local.EMPTY_TREE


@pytest.mark.parametrize('max_bytes, timeout, capped_expected', [
    pytest.param(None, None, False, id='uncapped-defaults'),
    pytest.param(4096, 15, True, id='capped-explicit-timeout'),
])
def test_max_bytes_and_timeout_reach_run_capped_with_the_same_pin(
        seam, repo, max_bytes, timeout, capped_expected):
    seam.answers['command'] = lambda argv: completed(argv, 3, b'a' * 8192, b'') \
        if capped_expected else completed(argv, 3, b'output\n', b'')
    kw = {} if timeout is None else {'timeout': timeout}
    if max_bytes is not None:
        kw['max_bytes'] = max_bytes
    r = local._project_git(repo, ['status', '--porcelain'], **kw)
    want = 60 if timeout is None else timeout
    text_kw = {} if timeout is None else {'timeout': timeout}

    if capped_expected:
        assert len(seam.capped) == 1
        assert set(seam.kinds()) == {'version', 'include', 'attrs', 'drivers'}
        call = seam.capped[0]
        assert call.max_bytes == 4096 and call.timeout == want
        assert call.argv[-2:] == ['status', '--porcelain']
        assert call.env == expected_pin_env(
            seam.temp_dirs[0], seam.exe, extra={'GIT_COMMON_DIR': seam.gitdir})
        assert call.cwd == repo
        assert r.returncode == 3 and r.stdout == 'a' * 8192
    else:
        assert seam.capped == []
        assert seam.ran[-1].kw['capture_output'] is True
        assert r.returncode == 3 and r.stderr == ''
    assert all(c.timeout == want for c in seam.ran)
    for c in seam.ran:
        extra = {} if c.kind in ('version', 'include') else {'GIT_COMMON_DIR': seam.gitdir}
        assert c.env == expected_pin_env(seam.temp_dirs[0], seam.exe, extra=extra)
    assert seam.temp_args and all(a == {'ignore_cleanup_errors': True} for a in seam.temp_args)
    assert all(a.startswith(seam.tmp + os.sep) for a in seam.temp_dirs)
    assert local._project_git_text(repo, ['status', '--porcelain'], **text_kw) is None


def test_the_result_text_is_decoded_with_replacement_and_the_newlines_are_untouched(seam, repo):
    seam.answers['command'] = lambda argv: completed(argv, 0, b'a\r\nb\r\rc\xff\n', b'no \xff\r\n')
    r = local._project_git(repo, ['status', '--porcelain'])
    assert r is not None and r.returncode == 0
    assert isinstance(r.stdout, str) and isinstance(r.stderr, str)
    assert r.stdout == 'a\r\nb\r\rc\ufffd\n'
    assert r.stderr == 'no \ufffd\r\n'
    assert r.stdout.count('\r') == b'a\r\nb\r\rc\xff\n'.count(b'\r')
    assert r.stdout.count('\n') == b'a\r\nb\r\rc\xff\n'.count(b'\n')
    assert seam.ran[-1].env['GIT_ALLOW_PROTOCOL'] == 'file'
    assert seam.ran[-1].env['GIT_PROTOCOL_FROM_USER'] == '0'
