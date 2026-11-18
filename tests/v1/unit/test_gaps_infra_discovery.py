"""T-721: the highest-risk uncovered branches of archeus/infra/discovery.py.

Fail-closed and denial paths first, then boundary values, then error paths.
Style and fixtures follow the discovery section of
tests/v1/unit/test_pv20_isolation.py: every OS boundary is faked through a seam
the existing tests already use — `discovery._try_lock`, `discovery.WINDOWS`,
`discovery._home_dacl`, `proc.process_create_time`, `config.write_json_atomic`
and a fake `msvcrt` in `sys.modules` — and every byte lands under the v1
conftest's `archeus_home` fixture (tmp_path), so nothing here needs Windows,
a real process, the network or anything but tmp_path.
"""

import json
import os
import sys

import pytest

from archeus.infra import discovery, paths
from claude_sessions import config, proc

POSIX_ONLY = pytest.mark.skipif(
    sys.platform == 'win32',
    reason='chmod/st_mode and the POSIX branch of token_protection do not exist on Windows')

VALID = b'{"pid": 4242, "create_time": 1.5, "port": 8123, "extra": [1, 2]}'


# ── fakes at the seams the existing tests use ──

def _fake_try_lock(monkeypatch, outcomes):
    """`discovery._try_lock` → scripted results (an Exception raises, anything
    else returns); records the fd of every call, the last outcome repeats."""
    calls = []
    real = discovery._try_lock

    def fake(fd):
        calls.append(fd)
        out = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        if isinstance(out, Exception):
            raise out
        real(fd)                                # a success really locks: release unlocks it
    monkeypatch.setattr(discovery, '_try_lock', fake)
    return calls


def _closed(fd):
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


def _make_lock_file():
    discovery.ensure_run_dir()
    with open(discovery.lock_path(), 'wb') as f:
        f.write(b'')


def _write_core_json(data):
    discovery.ensure_run_dir()
    with open(discovery.core_json_path(), 'wb') as f:
        f.write(data)


class _Clock:
    """A fake `discovery.time`: monotonic() replays the given values (the last
    one repeats), sleep is recorded instead of slept."""

    def __init__(self, *at):
        self.at = list(at)
        self.slept = []

    def monotonic(self):
        return self.at.pop(0) if len(self.at) > 1 else self.at[0]

    def sleep(self, seconds):
        self.slept.append(seconds)


class _FakeMsvcrt:
    """Sentinels for the only msvcrt surface discovery touches."""
    LK_NBLCK = 'LK_NBLCK'
    LK_UNLCK = 'LK_UNLCK'

    def __init__(self, log, refuse=False):
        self.log = log
        self.refuse = refuse

    def locking(self, fd, mode, count):
        self.log.append(('lock', fd, mode, count))
        if self.refuse:
            raise OSError('mock: the byte range is already held')


def _fake_windows(monkeypatch, log, refuse=False):
    monkeypatch.setattr(discovery, 'WINDOWS', True)
    monkeypatch.setitem(sys.modules, 'msvcrt', _FakeMsvcrt(log, refuse))


def _spy_os_calls(monkeypatch, log):
    real_lseek, real_close = os.lseek, os.close

    def lseek(fd, pos, how):
        log.append(('lseek', fd, pos, how))
        return real_lseek(fd, pos, how)

    def close(fd):
        log.append(('close', fd))
        return real_close(fd)

    monkeypatch.setattr(os, 'lseek', lseek)
    monkeypatch.setattr(os, 'close', close)


# ── acquire / the core.lock (fail-closed first) ──

def test_acquire_raises_lockheld_and_closes_its_fd_when_the_lock_never_frees(monkeypatch):
    calls = _fake_try_lock(monkeypatch, [OSError('mock: the core.lock is held')])
    with pytest.raises(discovery.LockHeld) as excinfo:
        discovery.acquire(retry_s=0)
    assert str(excinfo.value) == discovery.lock_path()
    assert len(calls) == 1 and _closed(calls[0])       # no retry beyond the deadline,
    #                                                    and no fd leaked past the refusal


def test_acquire_waits_out_a_momentary_holder_and_then_takes_the_lock(monkeypatch):
    """The CLI probe holds the lock for an instant; a Core must retry, not refuse."""
    calls = _fake_try_lock(monkeypatch, [OSError('mock: held'), OSError('mock: held'), None])
    lock = discovery.acquire(retry_s=5)
    try:
        assert len(calls) == 3
    finally:
        lock.release()


def test_lock_is_held_is_false_without_a_lock_file_and_never_creates_one(monkeypatch):
    def must_not_acquire(*a, **k):
        pytest.fail('the probe opened/acquired a lock when no lock file existed')
    monkeypatch.setattr(discovery, 'acquire', must_not_acquire)
    assert discovery.lock_is_held() is False
    assert not os.path.exists(discovery.lock_path())   # a probe never leaves a lock behind


def test_lock_is_held_is_true_when_the_lock_cannot_be_taken(monkeypatch):
    _make_lock_file()
    calls = _fake_try_lock(monkeypatch, [OSError('mock: the core.lock is held')])
    assert discovery.lock_is_held() is True            # fail-closed: core.json stays untrusted
    assert len(calls) == 1 and _closed(calls[0])


def test_lock_is_held_takes_and_releases_a_free_lock(monkeypatch):
    _make_lock_file()
    calls = _fake_try_lock(monkeypatch, [None])
    assert discovery.lock_is_held() is False
    assert len(calls) == 1 and _closed(calls[0])       # the probe gave the free lock straight back


def test_a_core_lock_closes_its_fd_once_and_ignores_a_second_release():
    lock = discovery.acquire(retry_s=0)
    fd = lock._fd
    lock.release()
    assert _closed(fd)
    lock.release()                                      # must not close a possibly-reused fd


# ── Windows byte-lock: fake msvcrt, never the real one ──

def test_on_windows_the_core_lock_is_an_msvcrt_byte_lock_seeked_to_zero_then_unlocked_close(
        monkeypatch):
    log = []
    _fake_windows(monkeypatch, log)
    _spy_os_calls(monkeypatch, log)
    discovery.acquire(retry_s=0).release()
    assert [entry[0] for entry in log] == ['lseek', 'lock', 'lseek', 'lock', 'close']
    _lseek0, lock0, _lseek1, unlock, closed = log
    assert lock0[2] is _FakeMsvcrt.LK_NBLCK and lock0[3] == 1
    assert unlock[2] is _FakeMsvcrt.LK_UNLCK and unlock[1] == lock0[1]
    assert closed[1] == lock0[1]


def test_a_refused_msvcrt_lock_raises_lockheld_on_windows_too(monkeypatch):
    log = []
    _fake_windows(monkeypatch, log, refuse=True)
    opened = []
    real_open = os.open

    def spy_open(path, flags, mode=0o777):
        fd = real_open(path, flags, mode)
        opened.append(fd)
        return fd

    monkeypatch.setattr(os, 'open', spy_open)
    with pytest.raises(discovery.LockHeld):
        discovery.acquire(retry_s=0)
    assert len(log) == 1 and log[0][2] is _FakeMsvcrt.LK_NBLCK
    assert opened and _closed(opened[-1])               # refused loudly, fd closed


# ── read_core_json: the shape gate (fail-closed) ──

_REFUSALS = [
    (None, 'missing'),
    (b'', 'empty'),
    (b'{not json', 'not-json'),
    (b'\xff\xfe', 'bad-utf8'),
    (b'[4242]', 'json-list'),
    (b'4242', 'json-number'),
    (b'null', 'json-null'),
    (b'"8123"', 'json-string'),
    (b'{"pid": "4242", "create_time": 1, "port": 8123}', 'pid-str'),
    (b'{"pid": null, "create_time": 1, "port": 8123}', 'pid-null'),
    (b'{"pid": 4242, "create_time": 1, "port": "8123"}', 'port-str'),
    (b'{"pid": 4242, "create_time": 1, "port": 8123.0}', 'port-float'),
    (b'{"pid": 4242, "port": 8123}', 'no-create-time'),
]


@pytest.mark.parametrize('data', [case for case, _ in _REFUSALS],
                         ids=[name for _, name in _REFUSALS])
def test_read_core_json_refuses_a_record_a_core_could_not_have_written(data):
    if data is not None:
        _write_core_json(data)
    assert discovery.read_core_json() is None


def test_a_deeply_nested_core_json_is_refused_not_a_crash(monkeypatch):
    _write_core_json(b'[' * 100000 + b']' * 100000)
    assert discovery.read_core_json() is None
    monkeypatch.setattr(discovery, 'lock_is_held', lambda: True)
    assert discovery.discover() == ('unreadable', None)


def test_read_core_json_returns_a_record_that_names_a_process_by_pid_and_creation_time():
    _write_core_json(VALID)
    assert discovery.read_core_json() == json.loads(VALID)   # extra keys and floats pass:
    #                                                          the gate is the three members only


# ── discover: only `running` may ever be sent the local token ──

def test_discover_shares_nothing_while_the_lock_is_free(monkeypatch):
    _write_core_json(VALID)                              # a stale record IS on disk
    monkeypatch.setattr(discovery, 'lock_is_held', lambda: False)
    monkeypatch.setattr(discovery, 'read_core_json',
                        lambda: pytest.fail('core.json read with the lock free'))
    assert discovery.discover() == ('not_running', None)


def test_discover_refuses_a_missing_or_malformed_core_json_under_a_held_lock(monkeypatch):
    monkeypatch.setattr(discovery, 'lock_is_held', lambda: True)
    assert discovery.discover() == ('unreadable', None)  # nothing written yet
    _write_core_json(b'{not json')
    assert discovery.discover() == ('unreadable', None)


def test_discover_refuses_a_pid_that_is_not_the_recorded_process(monkeypatch):
    """A5: the OS reuses pids; a stale record must never name a stranger's port."""
    _write_core_json(VALID)
    monkeypatch.setattr(discovery, 'lock_is_held', lambda: True)
    monkeypatch.setattr(proc, 'process_create_time', lambda pid: 1.6)
    state, info = discovery.discover()
    assert state == 'unreadable' and info['pid'] == 4242


def test_discover_says_running_only_for_a_live_record_it_can_verify(monkeypatch):
    _write_core_json(VALID)
    seen = []

    def create_time(pid):
        seen.append(pid)
        return 1.5

    monkeypatch.setattr(discovery, 'lock_is_held', lambda: True)
    monkeypatch.setattr(proc, 'process_create_time', create_time)
    state, info = discovery.discover()
    assert state == 'running' and info['port'] == 8123
    assert seen == [4242]                                # the check really ran


# ── write_core_json / remove_core_json ──

def test_write_core_json_refuses_when_the_atomic_replace_never_lands(monkeypatch):
    tries = []

    def never(path, obj, indent=2, mode=None):
        tries.append(path)
        return False

    monkeypatch.setattr(config, 'write_json_atomic', never)
    with pytest.raises(OSError):                         # never a silent None
        discovery.write_core_json({'pid': 1, 'create_time': 1, 'port': 7}, retry_s=0)
    assert tries == [discovery.core_json_path()]
    assert discovery.read_core_json() is None


def test_write_core_json_waits_out_a_flaky_replace_and_then_really_writes(monkeypatch):
    real = config.write_json_atomic
    tries = []

    def flaky(path, obj, indent=2, mode=None):
        tries.append(path)
        if len(tries) < 3:
            return False
        return real(path, obj, indent=indent, mode=mode)

    monkeypatch.setattr(config, 'write_json_atomic', flaky)
    discovery.write_core_json({'pid': 1, 'create_time': 1, 'port': 7})
    assert len(tries) == 3 and discovery.read_core_json()['port'] == 7


def test_remove_core_json_is_quiet_when_there_is_nothing_to_remove():
    discovery.remove_core_json()                         # no run dir, no file
    _write_core_json(VALID)
    discovery.remove_core_json()
    assert not os.path.exists(discovery.core_json_path())
    discovery.remove_core_json()                         # and again


# ── token_protection: the POSIX refusal, the Windows never-refusal ──

@POSIX_ONLY
def test_core_refuses_to_start_when_the_run_dir_is_group_readable(monkeypatch):
    monkeypatch.setattr(discovery, 'WINDOWS', False)
    discovery.ensure_run_dir()
    os.chmod(paths.run_dir(), 0o755)
    ok, msg = discovery.token_protection()
    assert ok is False and paths.run_dir() in msg and 'chmod 700' in msg


@POSIX_ONLY
def test_core_refuses_to_start_when_the_local_token_is_world_readable(monkeypatch):
    monkeypatch.setattr(discovery, 'WINDOWS', False)
    discovery.write_local_token('tok-A')
    os.chmod(discovery.local_token_path(), 0o644)
    ok, msg = discovery.token_protection()
    assert ok is False and discovery.local_token_path() in msg and 'chmod 600' in msg


@POSIX_ONLY
def test_a_token_only_the_owner_can_read_passes_on_posix(monkeypatch):
    monkeypatch.setattr(discovery, 'WINDOWS', False)
    discovery.write_local_token('tok-A')
    assert discovery.token_protection() == (True, None)


@POSIX_ONLY
def test_a_local_token_not_yet_written_is_not_a_refusal_yet(monkeypatch):
    """The FileNotFoundError branch: a fresh home (token never written) is checked,
    not crashed on, and not refused."""
    monkeypatch.setattr(discovery, 'WINDOWS', False)
    discovery.ensure_run_dir()
    assert discovery.token_protection() == (True, None)


def test_on_windows_a_broad_acl_is_a_warning_and_never_a_refusal(monkeypatch):
    """T-089/T-096: every pytest temp home has a broad ACL; Core must still start."""
    class Reader:
        def broad_writer(self, path):
            return 'S-1-5-11'

        def broad_reader(self, path):
            return None

    monkeypatch.setattr(discovery, 'WINDOWS', True)
    monkeypatch.setattr(discovery, '_home_dacl', Reader)
    ok, msg = discovery.token_protection()
    assert ok is True                                    # warning only, never a refusal
    assert 'ARCHEUS_HOME' in msg and 'written by Authenticated Users (S-1-5-11)' in msg


# ── the local token file ──

def test_read_local_token_is_none_unless_a_token_was_actually_written():
    assert discovery.read_local_token() is None          # missing file: OSError branch
    discovery.ensure_run_dir()
    with open(discovery.local_token_path(), 'wb') as f:
        f.write(b'\n \t\r')                              # whitespace is not a token
    assert discovery.read_local_token() is None
    with open(discovery.local_token_path(), 'wb') as f:
        f.write(b'tok-A\n')
    assert discovery.read_local_token() == 'tok-A'


def test_write_local_token_replaces_the_file_so_only_the_new_token_is_on_disk():
    discovery.write_local_token('one')                   # the remove-before-O_EXCL
    discovery.write_local_token('two')                   # dance must not explode the second time
    with open(discovery.local_token_path(), 'rb') as f:
        assert f.read() == b'two'
    assert discovery.read_local_token() == 'two'


@POSIX_ONLY
def test_write_local_token_creates_the_file_readable_only_by_its_owner():
    discovery.write_local_token('tok-A')
    assert os.stat(discovery.local_token_path()).st_mode & 0o777 == 0o600


def test_ensure_run_dir_creates_run_under_the_home_and_returns_it():
    assert discovery.ensure_run_dir() == paths.run_dir()
    assert os.path.isdir(paths.run_dir())


@POSIX_ONLY
def test_ensure_run_dir_creates_run_private_to_the_user():
    discovery.ensure_run_dir()
    assert os.stat(paths.run_dir()).st_mode & 0o777 == 0o700


# ── public_account_secret: one id per install, minted once ──

def _secret_path():
    return os.path.join(paths.run_dir(), 'public-account-secret')


def test_the_public_account_secret_is_minted_once_and_read_back_identically(monkeypatch):
    _fake_try_lock(monkeypatch, [None])
    first = discovery.public_account_secret()
    assert isinstance(first, bytes) and len(first) == 32
    with open(_secret_path(), 'rb') as f:
        assert f.read() == first
    assert discovery.public_account_secret() == first    # a re-read, not a re-mint


@pytest.mark.parametrize('blob', [b'x' * 31, b'x' * 33, b'x' * 64], ids=['31', '33', '64'])
def test_a_corrupt_public_account_secret_is_refused_rather_than_reminted(monkeypatch, blob):
    _fake_try_lock(monkeypatch, [None])
    discovery.ensure_run_dir()
    with open(_secret_path(), 'wb') as f:
        f.write(blob)
    with pytest.raises(ValueError):
        discovery.public_account_secret()
    with open(_secret_path(), 'rb') as f:                 # never silently replaced
        assert f.read() == blob


def test_a_contended_secret_lock_raises_lockheld_instead_of_minting_a_second_id(monkeypatch):
    calls = _fake_try_lock(monkeypatch, [OSError('mock: the secret is locked')])
    clock = _Clock(0.0, 5.0)
    monkeypatch.setattr(discovery, 'time', clock)
    with pytest.raises(discovery.LockHeld) as excinfo:
        discovery.public_account_secret()
    assert 'public-account-secret' in str(excinfo.value)
    assert len(calls) == 1 and clock.slept == [] and _closed(calls[0])


def test_the_secret_mint_waits_out_an_instant_holder_of_the_secret_lock(monkeypatch):
    calls = _fake_try_lock(monkeypatch, [OSError('mock: the secret is locked'), None])
    secret = discovery.public_account_secret()
    assert len(secret) == 32 and len(calls) == 2         # retried, not refused
