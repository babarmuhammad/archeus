import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import local

pytestmark = pytest.mark.real_config_freeze
from archeus.node.win32_mxc import INVALID_HANDLE, Win32Error

DELETE = 0x00010000
GENERIC_WRITE = 0x40000000
FILE_WRITE_DATA = 0x00000002
FILE_APPEND_DATA = 0x00000004
FILE_WRITE_EA = 0x00000010
FILE_WRITE_ATTRIBUTES = 0x00000100
FILE_SHARE_WRITE = 0x02
FILE_SHARE_DELETE = 0x04
CREATE_NEW, CREATE_ALWAYS, OPEN_ALWAYS, TRUNCATE_EXISTING = 1, 2, 4, 5
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_DELETE_ON_CLOSE = 0x04000000
ERROR_SHARING_VIOLATION = 32

BASE_ARGV = ['/usr/local/bin/git', '--no-replace-objects', '-c', 'core.hooksPath=/empty']
BASE_ENV = {'PATH': '/usr/local/bin', 'GIT_CONFIG_NOSYSTEM': '1'}

FIRST_HANDLE = 101

WORKTREE_KEY = 'extensions.worktreeconfig'


def _ancestors(path):
    out = [path]
    while True:
        parent = os.path.dirname(path)
        if parent == path:
            return out
        out.append(parent)
        path = parent


def _walks(asked):
    out, current = [], []
    for path in asked:
        if current and os.path.dirname(current[-1]) != path:
            out.append(current)
            current = []
        current.append(path)
    if current:
        out.append(current)
    return out


class _Stat:
    __slots__ = ('st_mode', 'st_file_attributes')

    def __init__(self, st_mode, st_file_attributes):
        self.st_mode = st_mode
        self.st_file_attributes = st_file_attributes


class _Result:
    __slots__ = ('returncode', 'stdout', 'stderr')

    def __init__(self, returncode=0, stdout=b'', stderr=b''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _Call:
    __slots__ = ('path', 'args')

    def __init__(self, path, args):
        self.path = path
        self.args = args


class _RunCall:
    __slots__ = ('argv', 'cwd', 'cap')

    def __init__(self, argv, cwd, cap):
        self.argv = argv
        self.cwd = cwd
        self.cap = cap


class Api:
    def __init__(self, refuse=(), error=ERROR_SHARING_VIOLATION):
        self.refuse = set(refuse)
        self.error_code = error
        self.created = []
        self.closed = []
        self.privates = []
        self._next = FIRST_HANDLE - 1
        self.functions = {'CreateFileW': self.create_file_w}

    def create_file_w(self, path, access, share, security, disposition, options, template):
        self.created.append(_Call(path, (access, share, security, disposition,
                                         options, template)))
        if path in self.refuse:
            return INVALID_HANDLE
        self._next += 1
        return self._next

    def _error(self, name):
        return Win32Error(name, self.error_code)

    def close_handle(self, handle):
        self.closed.append(handle)

    def created_paths(self):
        return [call.path for call in self.created]


class Run:
    def __init__(self, rev, include, worktree_config, root, arm=None):
        self.rev, self.include = dict(rev), dict(include)
        self.worktree_config = worktree_config
        self.expected_root = root
        self.arm = arm
        self.calls = []

    def __call__(self, argv, cwd, cap=None):
        argv = list(argv)
        self.calls.append(_RunCall(argv, cwd, cap))
        assert cwd == self.expected_root, 'a guard command ran outside the project: %r' % (cwd,)
        assert cap is None, 'the guard passed a byte cap: %r' % (cap,)
        if '--path-format=absolute' in argv:
            return self.rev.get(argv[-1], _Result(1, b''))
        if '--file' in argv:
            assert '--no-includes' in argv, 'a configuration file was read with includes on'
            path = argv[argv.index('--file') + 1]
            tail = argv[argv.index('--file') + 2:]
            if '--get-regexp' in tail:
                return self.include.get(path, _Result(1, b''))
            if tail[:1] == ['--bool']:
                if self.arm is not None:
                    self.arm()
                return _Result(0, self.worktree_config)
        raise AssertionError('the guard ran a command it must never run: %r' % (argv[-4:],))


class Os:
    def __init__(self, allowed, links=(), reparse=(), failing=(), late=None):
        self.allowed = set(allowed)
        self.links, self.reparse, self.failing = set(links), set(reparse), set(failing)
        self.late = dict(late or {})
        self.armed = False
        self.asked = []

    def arm(self):
        self.armed = True

    def _kind(self, path):
        if path in self.failing:
            return 'unreadable'
        if path in self.links:
            return 'symlink'
        if path in self.reparse:
            return 'reparse'
        if self.armed and path in self.late:
            return self.late[path]
        return None

    def lstat(self, path):
        self.asked.append(path)
        assert path in self.allowed, 'the guard read outside what it was given: %s' % path
        kind = self._kind(path)
        if kind == 'unreadable':
            raise OSError(13, 'the seam refuses this read', path)
        if kind == 'symlink':
            return _Stat(stat.S_IFLNK, 0)
        if kind == 'reparse':
            return _Stat(stat.S_IFREG, stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return _Stat(stat.S_IFREG, 0)


class _Namespace:
    __slots__ = ('path', '_os')

    def __init__(self, fake_os):
        self.path = os.path
        self._os = fake_os

    def lstat(self, path):
        return self._os.lstat(path)


class _NoProcess:
    DEVNULL = None

    @staticmethod
    def run(*args, **kwargs):
        raise AssertionError('the freeze started a process')

    @staticmethod
    def Popen(*args, **kwargs):
        raise AssertionError('the freeze started a process')


class Passage:
    def __init__(self, tmp_path, monkeypatch, *, layout='nested', rev=None,
                 include=None, worktree_config=b'false', refuse=(), links=(), reparse=(),
                 failing=(), late=None, error=ERROR_SHARING_VIOLATION):
        self.tmp = tmp_path
        self.alias = {'<root>': str(tmp_path / 'repo')}
        self.alias['<common>'] = os.path.join(self.alias['<root>'], '.git')
        if layout == 'separate':
            self.alias['<common>'] = str(tmp_path / 'main' / '.git')
        self.alias['<gitdir>'] = os.path.join(self.alias['<common>'], 'worktrees', 'wt7')
        self.alias['<main>'] = os.path.join(self.alias['<common>'], 'config')
        self.alias['<worktree>'] = os.path.join(self.alias['<gitdir>'], 'config.worktree')
        root = self.alias['<root>']
        allowed = set()
        for path in self.alias.values():
            allowed.update(_ancestors(path))
        self.allowed = allowed
        answered = {self.alias.get(key, key): value for key, value in (include or {}).items()}
        self.api = Api(refuse=[self.alias.get(p, p) for p in refuse], error=error)
        self.os = Os(allowed, links=[self.alias.get(p, p) for p in links],
                     reparse=[self.alias.get(p, p) for p in reparse],
                     failing=[self.alias.get(p, p) for p in failing],
                     late={self.alias.get(k, k): v for k, v in (late or {}).items()})
        rev = {self.alias.get(k, k): v for k, v in (rev or {}).items()}
        rev.setdefault('--git-dir', _Result(0, self.alias['<gitdir>'].encode() + b'\n'))
        rev.setdefault('--git-common-dir', _Result(0, self.alias['<common>'].encode() + b'\n'))
        self.run = Run(rev, answered, worktree_config, root, arm=self.os.arm)
        self.empty = str(tmp_path / 'pinned-empty')
        self.env = dict(BASE_ENV)
        self.yielded = None
        self.at_yield = None
        monkeypatch.setattr(local, 'sys', SimpleNamespace(platform='win32'))
        monkeypatch.setattr(local, 'Win32Api', self._make_api)
        monkeypatch.setattr(local, 'os', _Namespace(self.os))
        monkeypatch.setattr(local, 'subprocess', _NoProcess)

    def path(self, alias):
        return self.alias[alias]

    def _make_api(self, private):
        self.api.privates.append(private)
        return self.api

    def enter(self):
        try:
            with local._frozen_config(self.alias['<root>'], list(BASE_ARGV), self.env,
                                      self.run, self.empty) as pinned:
                self.yielded = list(pinned)
                self.at_yield = {'closed': list(self.api.closed),
                                 'created': self.api.created_paths(),
                                 'env': dict(self.env)}
        finally:
            assert list(self.tmp.iterdir()) == [], 'the freeze wrote to this machine'

    def queries(self, *needles):
        return [c for c in self.run.calls
                if 'config' in c.argv and all(n in c.argv for n in needles)]

    def rev_parses(self):
        return [c for c in self.run.calls if 'rev-parse' in c.argv]

    def include_queries(self, alias=None):
        out = self.queries('--get-regexp')
        if alias is None:
            return out
        target = self.alias[alias]
        return [c for c in out if c.argv[c.argv.index('--file') + 1] == target]

    def bool_query(self):
        return [c for c in self.queries('--bool', '--get')
                if c.argv[-1].lower() == WORKTREE_KEY.lower()]

    def assert_walks_terminate(self, stopped_at=None):
        walks = _walks(self.os.asked)
        assert walks, 'no reparse scan ran at all'
        for walk in walks:
            assert walk[0] in self.alias.values(), 'a walk started somewhere else: %s' % walk[0]
            last = walk[-1]
            if os.path.dirname(last) == last:
                continue
            assert stopped_at is not None and last == stopped_at, \
                'a walk stopped early at %s' % last
        assert set(self.os.asked) <= self.allowed


@pytest.fixture
def passage(tmp_path, monkeypatch):
    def make(**script):
        return Passage(tmp_path, monkeypatch, **script)
    return make


def test_a_failed_main_acquisition_raises_and_reads_nothing(passage):
    p = passage(refuse=['<main>'])
    with pytest.raises(Win32Error) as caught:
        p.enter()
    assert caught.value.api == 'CreateFileW'
    assert caught.value.code == ERROR_SHARING_VIOLATION
    assert p.yielded is None, 'a guard with no handle yielded a command line'
    assert p.api.created_paths() == [p.path('<main>')]
    assert p.api.closed == [], 'INVALID_HANDLE was handed to CloseHandle'
    assert p.queries() == [], 'a configuration key was read although nothing was held'
    assert {'--git-dir', '--git-common-dir'} <= {c.argv[-1] for c in p.rev_parses()}
    assert 'GIT_COMMON_DIR' not in p.env
    assert p.api.privates == [p.empty], 'the api was built without the private directory'


@pytest.mark.parametrize('answer', [0, 2, -1], ids=['match', 'git-error', 'signalled'])
def test_an_include_query_that_is_not_exactly_one_match_is_refused(passage, answer):
    p = passage(include={'<main>': _Result(answer, b'include.path')})
    with pytest.raises(OSError) as caught:
        p.enter()
    assert 'include in the repository configuration' in str(caught.value)
    assert p.path('<main>') in str(caught.value)
    assert p.yielded is None
    assert p.api.created_paths() == [p.path('<main>')]
    assert p.api.closed == [FIRST_HANDLE], 'the already-held main handle must go exactly once'
    assert INVALID_HANDLE not in p.api.closed
    assert p.include_queries('<main>'), 'the include query must run'
    assert p.bool_query() == [], 'the worktree probe ran after the refusal'
    assert 'GIT_COMMON_DIR' not in p.env
    got = p.include_queries('<main>')[0].argv
    assert got[len(BASE_ARGV):] == ['config', '--no-includes', '--file', p.path('<main>'),
                                    '--name-only', '--get-regexp', local._INCLUDE_KEYS]
    p.assert_walks_terminate()


def test_a_failed_worktree_acquisition_releases_the_main_handle(passage):
    p = passage(worktree_config=b'true', refuse=['<worktree>'])
    with pytest.raises(Win32Error) as caught:
        p.enter()
    assert caught.value.api == 'CreateFileW'
    assert p.yielded is None, 'the caller was handed a command line with no worktree hold'
    assert p.api.created_paths() == [p.path('<main>'), p.path('<worktree>')]
    assert p.api.closed == [FIRST_HANDLE], \
        'the main handle must go, and no worktree handle may be fabricated for it'
    assert INVALID_HANDLE not in p.api.closed
    assert p.include_queries('<worktree>') == [], 'an unheld worktree file was queried'
    assert p.include_queries('<main>')
    assert 'GIT_COMMON_DIR' not in p.env
    p.assert_walks_terminate()


@pytest.mark.parametrize('where', ['<main>', '<common>', '<root>'])
@pytest.mark.parametrize('how', ['symlink', 'reparse'])
def test_a_link_on_a_config_path_is_refused_after_the_handle_is_held(passage, where, how):
    p = passage(**{({'symlink': 'links'}).get(how, how): [where]})
    with pytest.raises(OSError) as caught:
        p.enter()
    assert 'a link or reparse point in the repository path' in str(caught.value)
    assert p.path(where) in str(caught.value)
    assert p.yielded is None
    assert p.api.created_paths() == [p.path('<main>')]
    assert p.api.closed == [FIRST_HANDLE], 'the handle held before the scan was never released'
    assert p.queries() == [], 'the configuration was read although the scan refused'
    assert p.api.privates == [p.empty]
    assert list(p.tmp.iterdir()) == [], 'a real link was created instead of the fake'
    p.assert_walks_terminate(stopped_at=p.path(where))


@pytest.mark.parametrize('answer', [_Result(0, b'   \n'), _Result(128, b'not a repo')],
                         ids=['blank', 'nonzero'])
def test_a_useless_common_dir_answer_holds_no_handle_and_yields_nothing(passage, answer):
    p = passage(rev={'--git-common-dir': answer})
    with pytest.raises(OSError) as caught:
        p.enter()
    assert 'not a repository' in str(caught.value)
    assert p.path('<root>') in str(caught.value)
    assert p.api.created == [] and p.api.closed == [], 'a handle was taken before the paths'
    assert p.yielded is None
    assert {'--git-dir', '--git-common-dir'} <= {c.argv[-1] for c in p.rev_parses()}
    assert p.queries() == []
    assert 'GIT_COMMON_DIR' not in p.env


def test_an_include_only_in_the_worktree_config_refuses_and_releases_both(passage):
    p = passage(worktree_config=b'true', include={'<main>': _Result(1, b''),
                                                  '<worktree>': _Result(0, b'include.path')})
    with pytest.raises(OSError) as caught:
        p.enter()
    assert 'include in the repository configuration' in str(caught.value)
    assert p.path('<worktree>') in str(caught.value)
    assert p.path('<main>') not in str(caught.value), 'the refusal blamed the wrong file'
    assert p.yielded is None
    assert p.api.created_paths() == [p.path('<main>'), p.path('<worktree>')]
    assert sorted(p.api.closed) == [FIRST_HANDLE, FIRST_HANDLE + 1], \
        'both acquired handles must be released exactly once'
    assert p.api.closed.count(FIRST_HANDLE) == 1 and p.api.closed.count(FIRST_HANDLE + 1) == 1
    assert p.include_queries('<main>') and p.include_queries('<worktree>')
    assert 'GIT_COMMON_DIR' not in p.env
    p.assert_walks_terminate()


def test_every_acquisition_asks_for_read_access_and_read_only_sharing(passage):
    p = passage(worktree_config=b'true')
    p.enter()
    assert p.yielded is not None
    assert len(p.api.created) == 2
    for call in p.api.created:
        access, share, security, disposition, options, template = call.args
        assert access == local._GENERIC_READ == 0x80000000
        assert not access & (GENERIC_WRITE | DELETE | FILE_WRITE_DATA | FILE_APPEND_DATA
                             | FILE_WRITE_EA | FILE_WRITE_ATTRIBUTES), \
            'a write or delete right was added to the hold: %08x' % access
        assert share == local._FILE_SHARE_READ == 1, 'the share mask is not read-only'
        assert not share & (FILE_SHARE_WRITE | FILE_SHARE_DELETE), \
            'a writer or a deleter could still share the held configuration'
        assert disposition == local._OPEN_EXISTING == 3
        assert disposition not in (CREATE_NEW, CREATE_ALWAYS, OPEN_ALWAYS,
                                   TRUNCATE_EXISTING), \
            'the guard is allowed to create or truncate the repository configuration'
        assert options == local._FILE_ATTRIBUTE_NORMAL == 0x80
        assert not options & (FILE_FLAG_DELETE_ON_CLOSE | FILE_FLAG_BACKUP_SEMANTICS)
        assert security is None, 'an inheritable security descriptor would hand the hold out'
        assert template is None
    assert p.api.created_paths() == [p.path('<main>'), p.path('<worktree>')]
    assert sorted(p.api.closed) == [FIRST_HANDLE, FIRST_HANDLE + 1]
    p.assert_walks_terminate()


@pytest.mark.parametrize('value, second', [
    (b'true', True), (b'true\n', True), (b'  true \r\n', True), (b'trueX', False),
    (b'TRUE', False), (b'false', False), (b'', False), (b'1', False), (b'trueish', False)],
    ids=['true', 'true-nl', 'true-padded', 'trueX', 'TRUE', 'false', 'empty', 'one',
         'trueish'])
def test_only_exactly_true_after_stripping_freezes_the_worktree_config(passage, value, second):
    p = passage(worktree_config=value)
    p.enter()
    assert p.yielded is not None, 'a clean freeze must still yield its pinned argv'
    expected = [p.path('<main>'), p.path('<worktree>')] if second else [p.path('<main>')]
    assert p.api.created_paths() == expected, '%r decided the worktree hold wrongly' % (value,)
    assert sorted(p.api.closed) == list(range(FIRST_HANDLE, FIRST_HANDLE + len(expected)))
    assert p.bool_query()
    bool_call = p.bool_query()[0]
    assert bool_call.argv[bool_call.argv.index('--file') + 1] == p.path('<main>'), \
        'the worktreeConfig probe must read the main config'
    assert bool_call.argv[bool_call.argv.index('--bool'):-1] == ['--bool', '--get']
    assert bool_call.argv[-1].lower() == WORKTREE_KEY.lower()
    assert bool(p.include_queries('<worktree>')) == second
    assert p.include_queries('<main>')
    p.assert_walks_terminate()


def test_the_yield_pins_the_observed_paths_while_every_handle_is_still_held(passage):
    p = passage(worktree_config=b'true')
    p.enter()
    assert p.yielded == list(BASE_ARGV) + ['--git-dir=' + p.path('<gitdir>'),
                                           '--work-tree=' + p.path('<root>')]
    assert p.path('<gitdir>') != p.path('<common>') != p.path('<root>'), \
        'the fixture must not pin one path three times'
    assert p.at_yield is not None
    assert p.at_yield['env'].get('GIT_COMMON_DIR') == p.path('<common>')
    assert p.at_yield['env']['GIT_COMMON_DIR'] != p.path('<gitdir>'), \
        'GIT_COMMON_DIR must carry the common dir, not the worktree git dir'
    assert p.at_yield['created'] == [p.path('<main>'), p.path('<worktree>')]
    assert p.at_yield['closed'] == [], 'a handle was released before the guarded call ran'
    assert sorted(p.api.closed) == [FIRST_HANDLE, FIRST_HANDLE + 1], \
        'both handles go only once the body has finished'
    assert p.env.get('GIT_COMMON_DIR') == p.path('<common>')
    assert {'--git-dir', '--git-common-dir'} <= {c.argv[-1] for c in p.rev_parses()}


@pytest.mark.parametrize('where', ['<root>', '<gitdir>'])
@pytest.mark.parametrize('layout', ['nested', 'separate'])
@pytest.mark.parametrize('how', ['symlink', 'reparse', 'unreadable'])
def test_a_root_or_gitdir_link_after_validation_refuses_before_any_yield(passage, where,
                                                                          layout, how):
    p = passage(late={where: how}, layout=layout)
    with pytest.raises(OSError) as caught:
        p.enter()
    assert p.yielded is None, 'a component that turned hostile was handed a command line'
    assert p.api.created_paths() == [p.path('<main>')]
    assert p.api.closed == [FIRST_HANDLE], 'the held main handle must go on a failed scan'
    assert INVALID_HANDLE not in p.api.closed
    assert p.include_queries('<main>') and p.bool_query(), \
        'the scan must run after the configuration was validated, not before'
    assert 'GIT_COMMON_DIR' not in p.env
    assert p.os.armed
    if layout == 'separate':
        assert not p.path('<common>').startswith(p.path('<root>')), \
            'a separate metadata dir that still walks under the work tree probes nothing'
    target = p.path(where)
    if how == 'unreadable':
        assert caught.value.filename == target, \
            'a scan that could not read a component says which one it could not read'
    else:
        assert 'a link or reparse point in the repository path' in str(caught.value)
        assert target in str(caught.value)
    assert target in p.os.asked
    p.assert_walks_terminate(stopped_at=target)
