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


def write_core_json(info, retry_s=2.0):
    # a reader holding the old core.json open fails the replace on Windows for
    # that instant: waited out, as a probe holding the lock is
    deadline = time.monotonic() + retry_s
    while not config.write_json_atomic(core_json_path(), info, indent=None):
        if time.monotonic() >= deadline:
            raise OSError('could not write %s' % core_json_path())
        time.sleep(0.05)


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

def _home_dacl():
    from ..node import isolation
    return isolation.WindowsBoundary()


def _home_warning(home, token=None):
    """A warning when a broad principal may write or read *home* (or, before it exists,
    the folder it will be created in and inherit from), or the local *token* once it
    exists, else None. Writing is checked before reading. Read only."""
    from ..node.isolation import BROAD_PRINCIPALS, IsolationUnavailable
    at = os.path.abspath(home)
    while not os.path.isdir(at) and os.path.dirname(at) != at:
        at = os.path.dirname(at)
    reader = _home_dacl()
    for what, path in (('ARCHEUS_HOME', at), ('the local token', token)):
        if what != 'ARCHEUS_HOME' and not (path and os.path.exists(path)):
            continue
        try:
            sid, how = reader.broad_writer(path), 'written'
            if sid is None:
                sid, how = reader.broad_reader(path), 'read'
        except IsolationUnavailable as e:
            return 'the ACL of %s %s could not be read: %s' % (what, path, e)
        if sid is None:
            continue
        harm = ('change Core\'s database, run/ and worktrees' if how == 'written'
                else 'read Core\'s full-scope local token')
        return ('%s %s can be %s by %s (%s), so any signed-in user of this machine can %s; '
                'move ARCHEUS_HOME to a folder under your user profile'
                % (what, path, how, BROAD_PRINCIPALS[sid], sid, harm))
    return None


def token_protection():
    """(ok, warning). POSIX: the token file and run/ must not be readable by
    group or others — `ok` is False and Core refuses to start. Windows: a home (or
    local token) a broad principal may write or read (a folder under a drive root
    such as D:\\ inherits MODIFY for Authenticated Users) is a warning, never a
    refusal - every pytest temp home and many existing installs have it (T-089, T-096)."""
    path = local_token_path()
    if WINDOWS:
        return True, _home_warning(paths.archeus_home(), path)
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
