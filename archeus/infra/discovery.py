"""Which process is THE Core for a home (p3.5b design gate §7, §18.1).

    run/core.lock    empty; an OS lock held for the life of the Core process
    run/core.json    {pid, create_time, port, started_at, version, schema}
    run/local-token  the CLI's device token (the one plaintext secret at rest)

The lock is `msvcrt.locking` / `fcntl.flock`, never a pid file, so a Core that
dies releases it with its process and there is no stale lock to clean up. The
Core runtime and the in-process judge binding take it through `acquire()`, so
two engine hosts on one home fail loudly instead of killing each other's
children (A1). `core.json` is only ever trusted while the lock is held AND its
pid is alive with its recorded creation time: a port named by a stale file may
belong to someone else by now (A5).

Stdlib plus the P0.5 `proc` seam only: the CLI imports this.
"""

import json
import os
import sys
import time

from claude_sessions import config, proc

from . import paths

WINDOWS = sys.platform.startswith('win')


class LockHeld(RuntimeError):
    """Another process holds this home's core.lock."""


def lock_path():
    return os.path.join(paths.run_dir(), 'core.lock')


def core_json_path():
    return os.path.join(paths.run_dir(), 'core.json')


def local_token_path():
    return os.path.join(paths.run_dir(), 'local-token')


def ensure_run_dir():
    run = paths.run_dir()
    os.makedirs(run, mode=0o700, exist_ok=True)
    return run


def _try_lock(fd):
    if WINDOWS:
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


class CoreLock:
    def __init__(self, fd):
        self._fd = fd

    def release(self):
        if self._fd is None:
            return
        try:
            if WINDOWS:
                import msvcrt
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(self._fd)
            self._fd = None


def acquire(retry_s=2.0):
    """Take this home's core.lock, retrying for *retry_s* (a CLI probe holds
    it for an instant), or raise LockHeld. Nothing else is opened first."""
    ensure_run_dir()
    fd = os.open(lock_path(), os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + retry_s
    while True:
        try:
            _try_lock(fd)
            return CoreLock(fd)
        except OSError:
            if time.monotonic() >= deadline:
                os.close(fd)
                raise LockHeld(lock_path()) from None
            time.sleep(0.05)


def lock_is_held():
    """True when some process holds core.lock. A free lock is taken and
    released at once — the probe the CLI runs before it trusts core.json."""
    if not os.path.exists(lock_path()):
        return False
    try:
        acquire(retry_s=0).release()
    except LockHeld:
        return True
    return False


def write_core_json(info):
    if not config.write_json_atomic(core_json_path(), info, indent=None):
        raise OSError('could not write %s' % core_json_path())


def read_core_json():
    """The discovery record, or None when it is missing or malformed."""
    try:
        with open(core_json_path(), encoding='utf-8') as f:
            info = json.load(f)
    except (OSError, ValueError):
        return None
    if not (isinstance(info, dict) and isinstance(info.get('pid'), int)
            and isinstance(info.get('port'), int) and 'create_time' in info):
        return None
    return info


def remove_core_json():
    try:
        os.remove(core_json_path())
    except FileNotFoundError:
        pass


def discover():
    """(state, info) for this home's Core, reading files only and opening no
    socket: `not_running` (the lock is free), `unreadable` (the lock is held
    but core.json is missing, malformed or names a process that is not alive
    with its recorded creation time) or `running`. Only `running` may be sent
    the local token."""
    if not lock_is_held():
        return 'not_running', None
    info = read_core_json()
    if info is None or proc.process_create_time(info['pid']) != info['create_time']:
        return 'unreadable', info
    return 'running', info


# ── the local token file (D5) ──

def _outside_profile(path):
    profile = os.environ.get('USERPROFILE') or os.path.expanduser('~')
    try:
        return os.path.commonpath([os.path.normcase(os.path.abspath(path)),
                                   os.path.normcase(os.path.abspath(profile))]) != \
            os.path.normcase(os.path.abspath(profile))
    except ValueError:                  # different drives
        return True


def token_protection():
    """(ok, warning). POSIX: the token file and run/ must not be readable by
    group or others — `ok` is False and Core refuses to start. Windows: the
    default home inherits the user-profile ACL; a home outside the profile is
    protected only by that directory's ACL, which is a warning, not a refusal."""
    path = local_token_path()
    if WINDOWS:
        if _outside_profile(paths.archeus_home()):
            return True, ('ARCHEUS_HOME is outside your user profile: the local token is '
                          'protected only by that directory\'s ACL')
        return True, None
    for p in (paths.run_dir(), path):
        try:
            mode = os.stat(p).st_mode
        except FileNotFoundError:
            continue
        if mode & 0o077:
            return False, ('%s is readable by other users (mode %o); run: chmod 700 %s && '
                           'chmod 600 %s' % (p, mode & 0o777, paths.run_dir(), path))
    return True, None


def read_local_token():
    try:
        with open(local_token_path(), encoding='utf-8') as f:
            return f.read().strip() or None
    except OSError:
        return None


def write_local_token(token):
    """Replace the token file, created 0600 with O_EXCL so it is never briefly
    readable by anyone else."""
    ensure_run_dir()
    path = local_token_path()
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(token)
