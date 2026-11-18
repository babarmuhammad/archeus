import os
import subprocess
from types import SimpleNamespace

import pytest

from archeus.node import local

pytestmark = pytest.mark.real_config_freeze

EXE_A = '/synth/bin/git-a'
EXE_B = '/synth/bin/git-b'
SYNTH_ENV = {'SYSTEMROOT': '/synth/systemroot', 'TEMP': '/synth/temp'}
ARGS = ['status', '--porcelain']


def _c(rc, stdout=b'', stderr=b'', cut=None):
    r = SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)
    if cut is not None:
        r.cut = cut
    return r


class _FakePath:
    def __init__(self, harness):
        self._h = harness

    def isfile(self, path):
        self._h.isfile_paths.append(str(path))
        return os.path.isfile(path)

    def __getattr__(self, name):
        return getattr(os.path, name)


class _FakeOS:
    def __init__(self, harness):
        self.path = _FakePath(harness)
        self.environ = dict(SYNTH_ENV)


class _FakeTD:
    def __init__(self, harness, kwargs):
        harness.td_kwargs = kwargs
        self.path = harness.empty

    def __enter__(self):
        return self.path

    def __exit__(self, *exc):
        return False


class Harness:
    def __init__(self, monkeypatch, tmp_path, exe=EXE_A, win32=True, seed_version=True):
        self.tmp = str(tmp_path)
        self.root = os.path.join(self.tmp, 'repo')
        self.empty = os.path.join(self.tmp, 'empty')
        os.makedirs(os.path.join(self.root, '.git'), exist_ok=True)
        os.makedirs(self.empty, exist_ok=True)
        self.exe0 = exe
        self.exes = [exe]
        self.which_calls = []
        self.calls = []
        self.events = []
        self.held, self.closed, self.reparse = [], [], []
        self.api_built, self.isfile_paths, self.td_kwargs = [], [], None
        self.answers = {
            'version': _c(0, b'git version 2.45.0\n'),
            'freeze-path': None,
            'freeze-include': _c(1),
            'freeze-bool': _c(1),
            'attrs': _c(0, b'.git/info/attributes\n'),
            'drivers': _c(1),
            'final': _c(0, b'', b''),
        }
        monkeypatch.setattr(local, 'os', _FakeOS(self))
        monkeypatch.setattr(local, 'tempfile', SimpleNamespace(TemporaryDirectory=self._td))
        monkeypatch.setattr(local, 'sys', SimpleNamespace(platform='win32' if win32 else 'linux'))
        monkeypatch.setattr(local.proc, 'which', self._which)
        monkeypatch.setattr(local.proc, 'run_capped', self._capped)
        monkeypatch.setattr(local.subprocess, 'run', self._run)
        if win32:
            monkeypatch.setattr(local, 'Win32Api', self._fake_api_class())
            monkeypatch.setattr(local, '_reparse_free', self._reparse)
        monkeypatch.setattr(local, '_VERSION', {exe: 'git version 2.45.0'} if seed_version else {})

    def _which(self, name, path=None, avoid=()):
        self.which_calls.append((name, tuple(avoid)))
        return self.exes[min(len(self.which_calls) - 1, len(self.exes) - 1)]

    def _td(self, **kwargs):
        return _FakeTD(self, kwargs)

    def _reparse(self, path):
        self.reparse.append(str(path))
        self.events.append('reparse')

    def _fake_api_class(self):
        outer = self

        class FakeWin32Api:
            def __init__(self, private_directory):
                outer.api_built.append(private_directory)
                self.functions = {'CreateFileW': self._create}

            def _create(self, path, *rest):
                h = 1000 + len(outer.held)
                assert h != local.INVALID_HANDLE
                outer.held.append(h)
                outer.events.append('hold')
                return h

            def _error(self, name):
                return OSError('fake %s failed' % name)

            def close_handle(self, handle):
                outer.closed.append(handle)
                outer.events.append('close')
        return FakeWin32Api

    def _stage(self, argv):
        if argv[1:2] == ['version']:
            return 'version'
        if 'rev-parse' in argv:
            return 'freeze-path' if '--path-format=absolute' in argv else 'attrs'
        if 'config' in argv:
            if '--file' in argv:
                return 'freeze-include' if '--get-regexp' in argv else 'freeze-bool'
            return 'drivers'
        return 'final'

    def _answer(self, stage, argv, cwd, cap, kw):
        kw = dict(kw)
        if 'env' in kw:
            kw['env'] = dict(kw['env'])
        self.calls.append(SimpleNamespace(stage=stage, argv=list(argv), cap=cap, kw=kw))
        self.events.append(stage + ('_capped' if stage == 'final' and cap is not None else ''))
        a = self.answers[stage]
        if stage == 'freeze-path':
            return _c(0, (os.path.join(self.root, '.git') + '\n').encode())
        if isinstance(a, BaseException):
            raise a
        if callable(a):
            return a(list(argv))
        r = SimpleNamespace(returncode=a.returncode, stdout=a.stdout, stderr=a.stderr)
        if hasattr(a, 'cut'):
            r.cut = a.cut
        return r

    def _run(self, argv, **kw):
        return self._answer(self._stage(list(argv)), list(argv), kw.get('cwd'), None, kw)

    def _capped(self, argv, cwd=None, env=None, timeout=None, max_bytes=None):
        return self._answer(self._stage(list(argv)), list(argv), cwd, max_bytes,
                            {'cwd': cwd, 'env': env, 'timeout': timeout})

    def expected_env(self, exe=None):
        exe = exe or self.exe0
        env = dict(SYNTH_ENV)
        env.update(PATH=os.path.dirname(exe), HOME=self.empty, XDG_CONFIG_HOME=self.empty,
                   GIT_CONFIG_GLOBAL=os.path.join(self.empty, 'none'), GIT_CONFIG_NOSYSTEM='1',
                   GIT_ATTR_NOSYSTEM='1', GIT_ATTR_SOURCE=local.EMPTY_TREE,
                   GIT_TERMINAL_PROMPT='0', GIT_ALLOW_PROTOCOL='file',
                   GIT_PROTOCOL_FROM_USER='0', GIT_NO_LAZY_FETCH='1')
        return env

    def static_pins(self, exe=None):
        none = os.path.join(self.empty, 'none')
        argv = [exe or self.exe0, '--no-replace-objects']
        for c in ('core.hooksPath=' + self.empty, 'core.fsmonitor=false',
                  'core.attributesFile=' + none, 'merge.default=text',
                  'merge.verifySignatures=false', 'commit.gpgsign=false', 'tag.gpgSign=false',
                  'submodule.recurse=false', 'gc.auto=0', 'maintenance.auto=false',
                  'core.longpaths=true'):
            argv += ['-c', c]
        return argv

    def stages(self):
        return [c.stage for c in self.calls]


@pytest.mark.parametrize('broken', [_c(128, b'', b'fatal: not a repository'),
                                    _c(0, b''), _c(0, b'   \r\n')])
def test_a_failed_or_blank_attributes_lookup_refuses_with_no_enumeration_and_the_freeze_exits(
        tmp_path, monkeypatch, broken):
    h = Harness(monkeypatch, tmp_path, win32=True)
    h.answers['attrs'] = broken
    r = local._project_git(h.root, ARGS)
    assert r is None
    stages = h.stages()
    assert 'drivers' not in stages and 'final' not in stages
    assert stages[-1] == 'attrs'
    assert h.held and sorted(h.closed) == sorted(h.held)
    assert h.events[-1] == 'close'
    assert h.events.index('hold') < h.events.index('attrs')


@pytest.mark.parametrize('content,allowed', [
    (b'#only comments\n\n   \n\t\n   # indented\n', True),
    (b'#comment\n\nf.txt filter=foo\n', False),
    (b'\n   \n# c\nmerge.txt merge=bad\n', False),
])
def test_a_comment_only_attributes_file_permits_enumeration_and_an_active_line_refuses(
        tmp_path, monkeypatch, content, allowed):
    h = Harness(monkeypatch, tmp_path)
    A = os.path.join(h.root, '.git/info/attributes')
    os.makedirs(os.path.dirname(A), exist_ok=True)
    with open(A, 'wb') as f:
        f.write(content)
    r = local._project_git(h.root, ARGS)
    stages = h.stages()
    if allowed:
        assert r is not None and r.returncode == 0
        assert stages[-2:] == ['drivers', 'final']
    else:
        assert r is None
        assert 'drivers' not in stages and 'final' not in stages
    assert [os.path.normpath(p) for p in h.isfile_paths] == [os.path.normpath(A)]
    assert all(p.startswith(str(tmp_path) + os.sep) for p in h.isfile_paths)


@pytest.mark.parametrize('rc', [2, 3, 128])
def test_a_broken_driver_lookup_is_not_read_as_an_empty_config(tmp_path, monkeypatch, rc):
    h = Harness(monkeypatch, tmp_path)
    h.answers['drivers'] = _c(rc, b'')
    assert local._project_git(h.root, ARGS) is None
    assert h.stages()[-1] == 'drivers'
    assert 'final' not in h.stages()


def test_a_driver_lookup_with_no_matches_allows_the_pinned_call(tmp_path, monkeypatch):
    h = Harness(monkeypatch, tmp_path)
    h.answers['drivers'] = _c(1, b'')
    r = local._project_git(h.root, ARGS)
    assert r is not None and r.returncode == 0
    final = [c for c in h.calls if c.stage == 'final'][0]
    G = os.path.join(h.root, '.git')
    F = h.static_pins() + ['--git-dir=' + G, '--work-tree=' + h.root]
    assert final.argv == F + ARGS


def test_multiple_driver_keys_each_get_a_command_line_neutralization_before_the_caller_args(
        tmp_path, monkeypatch):
    h = Harness(monkeypatch, tmp_path)
    h.answers['drivers'] = _c(0, b'filter.a.clean\n  merge.b.process  \ndiff.c.textconv\n')
    r = local._project_git(h.root, ARGS)
    assert r is not None and r.returncode == 0
    final = [c for c in h.calls if c.stage == 'final'][0]
    G = os.path.join(h.root, '.git')
    F = h.static_pins() + ['--git-dir=' + G, '--work-tree=' + h.root]
    assert final.argv == F + ['-c', 'filter.a.clean=', '-c', 'merge.b.process=',
                              '-c', 'diff.c.textconv='] + ARGS
    drivers = [c for c in h.calls if c.stage == 'drivers'][0]
    assert drivers.argv == F + ['config', '--name-only', '--get-regexp',
                               local._DRIVER_KEYS]


def test_hostile_repository_signing_and_merge_options_cannot_remove_the_command_line_pins(
        tmp_path, monkeypatch):
    h = Harness(monkeypatch, tmp_path)
    h.answers['drivers'] = _c(0, b'merge.default.driver\nfilter.evil.process\n')
    r = local._project_git(h.root, ARGS)
    assert r is not None and r.returncode == 0
    argv = [c for c in h.calls if c.stage == 'final'][0].argv
    opts = [argv[i + 1] for i in range(len(argv) - 1) if argv[i] == '-c']
    for pin in ('merge.default=text', 'merge.verifySignatures=false',
                'commit.gpgsign=false', 'tag.gpgSign=false'):
        same_key = [o for o in opts if o.split('=')[0] == pin.split('=')[0]]
        assert same_key and all(o == pin for o in same_key)
    assert 'merge.default.driver=' in opts
    assert 'filter.evil.process=' in opts
    assert argv[-2:] == ARGS
    drivers = [c for c in h.calls if c.stage == 'drivers'][0].argv
    assert 'merge.default=text' in drivers
    assert 'commit.gpgsign=false' in drivers and 'tag.gpgSign=false' in drivers


@pytest.mark.parametrize('mode', ['uncapped', 'capped', 'raises'])
def test_the_freeze_is_entered_before_the_lookup_and_exits_only_after_the_final_call(
        tmp_path, monkeypatch, mode):
    h = Harness(monkeypatch, tmp_path, win32=True)
    kw = {}
    if mode == 'capped':
        kw['max_bytes'] = 8
    if mode == 'raises':
        h.answers['final'] = subprocess.TimeoutExpired(['git'], 1)
    r = local._project_git(h.root, ARGS, **kw)
    ev = h.events
    final = 'final_capped' if mode == 'capped' else 'final'
    assert ev.index('hold') < ev.index('attrs')
    assert ev.index('drivers') < ev.index(final)
    assert 'close' not in ev[:ev.index(final)]
    assert ev[-1] == 'close' and sorted(h.closed) == sorted(h.held) and h.held
    assert (r is None) == (mode == 'raises')
    attrs = [c for c in h.calls if c.stage == 'attrs'][0]
    assert ('--git-dir=' + os.path.join(h.root, '.git')) in attrs.argv
    assert ('--work-tree=' + h.root) in attrs.argv
    fin = [c for c in h.calls if c.stage == 'final'][0]
    assert fin.kw['env'].get('GIT_COMMON_DIR') == os.path.join(h.root, '.git')
    if mode == 'capped':
        assert fin.cap == 8
    assert h.api_built and all(p == h.empty for p in h.api_built)
    assert h.reparse and h.root in h.reparse


def test_max_bytes_zero_still_uses_the_capped_runner_with_the_exact_timeout_env_and_cwd(
        tmp_path, monkeypatch):
    h = Harness(monkeypatch, tmp_path, seed_version=False)
    r = local._project_git(h.root, ARGS, timeout=17, max_bytes=0)
    assert r is not None
    capped = [c for c in h.calls if c.cap is not None]
    assert len(capped) == 1 and capped[0].stage == 'final'
    assert capped[0].cap == 0
    assert capped[0].kw['timeout'] == 17 and capped[0].kw['cwd'] == h.root
    G = os.path.join(h.root, '.git')
    F = h.static_pins() + ['--git-dir=' + G, '--work-tree=' + h.root]
    E = dict(h.expected_env(), GIT_COMMON_DIR=G)
    assert capped[0].kw['env'] == E
    assert capped[0].argv == F + ARGS
    unc = [c for c in h.calls if c.cap is None]
    assert {'version', 'freeze-path', 'freeze-include', 'freeze-bool', 'attrs', 'drivers'} <= {
        c.stage for c in unc}
    assert all(c.cap is None for c in h.calls if c.stage != 'final')
    assert all(c.kw['env'] == E for c in unc if c.stage in ('attrs', 'drivers'))
    ver = next(c for c in unc if c.stage == 'version')
    assert ver.argv == [EXE_A, 'version']
    assert ver.kw == {'cwd': h.empty, 'env': h.expected_env(), 'capture_output': True,
                      'timeout': 17, 'stdin': subprocess.DEVNULL,
                      'creationflags': local.proc.no_window_flags}


@pytest.mark.parametrize('bad', [b'git version 2.44.9.windows.1\n', b'git version cat\n', b''])
def test_a_version_below_the_floor_is_refused_and_never_cached(tmp_path, monkeypatch, bad):
    h = Harness(monkeypatch, tmp_path, seed_version=False)
    h.answers['version'] = _c(0, bad)
    assert local._project_git(h.root, ARGS) is None
    assert local._VERSION == {}
    assert h.stages() == ['version']


def test_a_valid_version_is_cached_once_and_each_executable_caches_for_itself(
        tmp_path, monkeypatch):
    h = Harness(monkeypatch, tmp_path, seed_version=False)
    h.exes = [EXE_A, EXE_A, EXE_B]

    def version(argv):
        return _c(0, b'git version 2.45.0\n' if argv[0] == EXE_A else b'git version 2.47.1\n')
    h.answers['version'] = version
    assert local._project_git(h.root, ARGS) is not None
    assert local._VERSION == {EXE_A: 'git version 2.45.0'}
    assert local._project_git(h.root, ARGS) is not None
    assert local._project_git(h.root, ARGS) is not None
    assert [c.argv for c in h.calls if c.stage == 'version'] == [[EXE_A, 'version'],
                                                                 [EXE_B, 'version']]
    assert local._VERSION == {EXE_A: 'git version 2.45.0', EXE_B: 'git version 2.47.1'}


@pytest.mark.parametrize('stage', ['attrs', 'drivers', 'final'])
def test_a_timeout_in_any_runner_refuses_and_releases_every_held_handle(
        tmp_path, monkeypatch, stage):
    h = Harness(monkeypatch, tmp_path, win32=True)
    h.answers[stage] = subprocess.TimeoutExpired(['git'] + ARGS, 1)
    assert local._project_git(h.root, ARGS, max_bytes=64) is None
    assert h.held and sorted(h.closed) == sorted(h.held)
    cut = h.stages().index(stage)
    assert h.stages()[cut + 1:] == []


def test_the_final_result_is_decoded_with_replacement_and_keeps_crlf_and_the_cut_flag(
        tmp_path, monkeypatch):
    h = Harness(monkeypatch, tmp_path, win32=True)
    h.answers['final'] = SimpleNamespace(returncode=0, stdout=b'done\r\nnext\r\n\xed\xa0\x80',
                                         stderr=b'warn\r\n\xff', cut=True)
    r = local._project_git(h.root, ARGS, max_bytes=4096)
    assert r is not None and r.returncode == 0
    assert isinstance(r.stdout, str) and isinstance(r.stderr, str)
    assert r.stdout == 'done\r\nnext\r\n' + '\ufffd\ufffd\ufffd'
    assert r.stderr == 'warn\r\n\ufffd'
    assert r.cut is True
