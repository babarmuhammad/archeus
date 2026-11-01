"""Native script common helpers with safety guards (card T-460).

Contract: /work/inputs/common_api.md. Stdlib only. Scripts import exactly
``StopRun``, ``safe_root``, ``remove_fixture``, ``Recorder``, ``Children``
and ``redact`` from this module and nothing else.

Every Windows-specific system call sits behind one of the small module-level
injectables below (``_popen``, ``_process_creation_time``,
``_terminate_process``, ``_is_link_or_junction``, ``_profile_dir``,
``_repo_root``, ``_username``, ``_machine_name``, ``_IS_WINDOWS``) so the
unit tests run on Linux with fakes. A value that must never reach a terminal
(SID, username, machine name) is removed by ``redact`` before printing, and
error messages quote no caller path.
"""

import ctypes
import ntpath
import os
import platform
import posixpath
import re
import stat
import subprocess
import uuid

from tools.pv20_mxc.protocol import STAGES

MARKER = '.pv20-fixture'

# The injectable switch: tests flip this to True to exercise the Windows
# path grammar on Linux; production sets it from the running OS.
_IS_WINDOWS = os.name == 'nt'

_HEX32 = re.compile(r'\A[0-9a-f]{32}\Z')
_SID = re.compile(r'S-\d+(?:-\d+)+')


class StopRun(Exception):
    """Raised by Recorder.record after printing a FAIL: scripts stop here."""


# --------------------------------------------------------------------------
# Injectable seams (faked by tests on Linux)
# --------------------------------------------------------------------------

def _drv():
    return ntpath if _IS_WINDOWS else posixpath


def _isabs(path):
    return _drv().isabs(path)


def _normpath(path):
    return _drv().normpath(path)


def _dirname(path):
    return _drv().dirname(path)


def _basename(path):
    return _drv().basename(path)


def _join(a, b):
    return _drv().join(a, b)


def _parts(path):
    """Path components; the drive with its root separator counts as one."""
    drive, rest = _drv().splitdrive(path)
    parts = []
    if rest[:1] in ('\\', '/'):
        parts.append((drive + rest[0]) if drive else _drv().sep)
    elif drive:
        parts.append(drive)
    for piece in rest.replace('\\', '/').split('/'):
        if piece:
            parts.append(piece)
    return parts


def _is_under(path, prefix):
    """True if path == prefix or path sits below prefix (platform casing)."""
    a = _drv().normcase(_normpath(path))
    b = _drv().normcase(_normpath(prefix))
    if a == b:
        return True
    return a.startswith(b.rstrip('\\/') + _drv().sep)


def _profile_dir():
    return os.environ.get('USERPROFILE') or os.path.expanduser('~')


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, '..', '..', '..'))


def _is_link_or_junction(path):
    """Symlink or Windows reparse point (junction), decided without following."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _username():
    name = os.environ.get('USERNAME')
    if name:
        return name
    try:
        import getpass
        return getpass.getuser() or ''
    except Exception:
        return ''


def _machine_name():
    name = os.environ.get('COMPUTERNAME')
    if name:
        return name
    try:
        return platform.node() or ''
    except OSError:
        return ''


def _popen(argv, **popen_kwargs):
    return subprocess.Popen(argv, **popen_kwargs)


def _process_creation_time(pid):
    """Windows FILETIME creation time for pid, or None if unverifiable.

    On non-Windows hosts this returns None, which makes Children.kill_own
    refuse every kill (fail closed); tests fake this seam instead.
    """
    if not _IS_WINDOWS:
        return None
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, int(pid))  # QUERY_LIMITED
    if not handle:
        return None
    try:
        class _FileTime(ctypes.Structure):
            _fields_ = [('lo', ctypes.c_uint32), ('hi', ctypes.c_uint32)]
        creation = _FileTime()
        exited = _FileTime()
        kernel = _FileTime()
        user = _FileTime()
        if not kernel32.GetProcessTimes(handle, ctypes.byref(creation),
                                        ctypes.byref(exited), ctypes.byref(kernel),
                                        ctypes.byref(user)):
            return None
        return (creation.hi << 32) | creation.lo
    finally:
        kernel32.CloseHandle(handle)


def _terminate_process(pid):
    """Terminate a process this script started; True on success."""
    if _IS_WINDOWS:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x0001 | 0x1000, False, int(pid))  # TERMINATE|QUERY_LIMITED
        if not handle:
            return False
        try:
            return bool(kernel32.TerminateProcess(handle, 1))
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 15)  # SIGTERM; scripts only ever run on Windows
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------
# Fixture root lifecycle
# --------------------------------------------------------------------------

def _validate_parent(parent):
    """Every refusal shared by safe_root and remove_fixture. ValueError only.

    Refuses: non-string, relative path, device-prefixed or driveless Windows
    path, drive or filesystem root, fewer than three components, the user
    profile / an ancestor of it / a path inside it, a path inside the
    repository, a parent that is (or is reached through a link or junction),
    a non-canonical spelling of the path, and a missing parent directory.
    """
    if not isinstance(parent, str) or not parent:
        raise ValueError('parent must be a non-empty string')
    if not _isabs(parent):
        raise ValueError('parent must be an absolute path')
    if _IS_WINDOWS and parent.replace('/', '\\').startswith(('\\\\?\\', '\\\\.\\')):
        raise ValueError('parent must not use a device path prefix')
    parent = _normpath(parent)
    drive, rest = _drv().splitdrive(parent)
    if _IS_WINDOWS and not drive:
        raise ValueError('parent must include a drive or UNC share')
    if _dirname(parent) == parent or rest in ('', '\\', '/'):
        raise ValueError('parent must not be a drive or filesystem root')
    if len(_parts(parent)) < 3:
        raise ValueError('parent must have at least three path components')
    prof = _profile_dir()
    for known in (prof, prof and os.path.realpath(prof)):
        if known and (_is_under(parent, known) or _is_under(known, parent)):
            raise ValueError('parent is the user profile, an ancestor of it, or inside it')
    repo = _repo_root()
    for known in (repo, repo and os.path.realpath(repo)):
        if known and _is_under(parent, known):
            raise ValueError('parent is inside the repository')
    chain = []
    cursor = parent
    while True:
        chain.append(cursor)
        nxt = _dirname(cursor)
        if nxt == cursor:
            break
        cursor = nxt
    for node in reversed(chain):
        if _is_link_or_junction(node):
            raise ValueError('parent is or passes through a link or junction')
    if not os.path.isdir(parent):
        raise ValueError('parent must be an existing directory')
    # realpath expands 8.3 short names, trailing dots and drive substitution,
    # which the lexical profile and repository checks above cannot see.
    if _drv().normcase(os.path.realpath(parent)) != _drv().normcase(parent):
        raise ValueError('parent is not in canonical form (short name, alias or substituted drive)')
    return parent


def safe_root(parent):
    """Validate parent, create parent/<uuid4 hex> plus the marker file, return it."""
    parent = _validate_parent(parent)
    root = _join(parent, uuid.uuid4().hex)
    os.mkdir(root)
    marker = _join(root, MARKER)
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, b'pv20-mxc fixture marker\n')
    finally:
        os.close(fd)
    return os.path.abspath(root)


def _delete_no_follow(path):
    """Delete path without ever descending into a link or junction."""
    for entry in os.scandir(path):
        if _is_link_or_junction(entry.path):
            try:
                os.unlink(entry.path)
            except OSError:
                os.rmdir(entry.path)  # junction: removes the link, not the target
        elif entry.is_dir(follow_symlinks=False):
            _delete_no_follow(entry.path)
            os.rmdir(entry.path)
        else:
            os.unlink(entry.path)
    os.rmdir(path)


def remove_fixture(root):
    """Delete a safe_root fixture tree; anything else raises ValueError."""
    if not isinstance(root, str) or not root:
        raise ValueError('root must be a non-empty string')
    if not _isabs(root):
        raise ValueError('root must be an absolute path')
    root = _normpath(root)
    base = _basename(root)
    if not _HEX32.match(base):
        raise ValueError('root name must be the uuid4 hex created by safe_root')
    parent = _dirname(root)
    if _HEX32.match(_basename(parent)):
        raise ValueError('root must sit directly under the validated parent')
    _validate_parent(parent)
    if _is_link_or_junction(root):
        raise ValueError('root is a link or junction')
    try:
        info = os.lstat(root)
    except OSError:
        raise ValueError('root does not exist')
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('root is not a real directory')
    marker = _join(root, MARKER)
    try:
        minfo = os.lstat(marker)
    except OSError:
        raise ValueError('marker file missing: not a fixture tree')
    if not stat.S_ISREG(minfo.st_mode) or minfo.st_nlink != 1:
        raise ValueError('marker is not a plain single-link file')
    _delete_no_follow(root)


# --------------------------------------------------------------------------
# Case recording
# --------------------------------------------------------------------------

class Recorder:
    """One redacted line per case; FAIL raises StopRun; exit_code sums the run."""

    def __init__(self, stage):
        if stage not in STAGES:
            raise ValueError('stage is not a protocol STAGES key')
        self.stage = stage
        self.results = []

    def record(self, case, status, detail=''):
        if status not in ('PASS', 'FAIL', 'INCONCLUSIVE'):
            raise ValueError('status must be PASS, FAIL or INCONCLUSIVE')
        if case not in STAGES[self.stage].cases:
            raise ValueError('case is not a protocol case of this stage')
        self.results.append((case, status))
        line = 'pv20 %s %s %s' % (self.stage, case, status)
        if detail:
            line = line + ' ' + detail
        print(redact(line), flush=True)
        if status == 'FAIL':
            raise StopRun('%s %s' % (self.stage, case))

    def exit_code(self):
        statuses = [status for _, status in self.results]
        if not statuses:
            return 2  # a run that recorded nothing can never pass
        if 'FAIL' in statuses:
            return 1
        if 'INCONCLUSIVE' in statuses:
            return 2
        return 0


# --------------------------------------------------------------------------
# Owned children
# --------------------------------------------------------------------------

class Children:
    """Processes this script started, remembered by (pid, creation time)."""

    def __init__(self):
        self._own = []

    def start(self, argv, **popen_kwargs):
        if isinstance(argv, str):
            raise ValueError('argv must be an argument list, never a shell string')
        argv = list(argv)
        if not all(isinstance(a, str) for a in argv):
            raise ValueError('argv must be an argument list of strings')
        proc = _popen(argv, **popen_kwargs)
        pid = int(proc.pid)
        self._own.append((pid, _process_creation_time(pid)))
        return pid

    def kill_own(self):
        killed = 0
        owned, self._own = self._own, []
        for pid, when in owned:
            if when is None:
                continue  # identity unverifiable: refuse the kill
            if _process_creation_time(pid) == when:
                if _terminate_process(pid):
                    killed += 1
        return killed


# --------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------

def redact(text):
    """Remove SIDs, the current username and the machine name from text."""
    out = _SID.sub('[REDACTED-SID]', text)
    tokens = [(_username(), '[REDACTED-USER]'), (_machine_name(), '[REDACTED-HOST]')]
    for token, label in sorted(tokens, key=lambda pair: -len(pair[0] or '')):
        token = (token or '').strip()
        if len(token) < 2:
            continue  # too short to substitute safely; never rewrite everything
        flags = re.IGNORECASE if _IS_WINDOWS else 0
        out = re.sub(re.escape(token), label, out, flags=flags)
    return out
