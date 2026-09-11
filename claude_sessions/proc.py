"""Every subprocess and process-lifetime primitive, in one place.

There were three git wrappers (two identical with their arguments in the
opposite order), two byte-for-byte copies of `_pid_alive`, two copies of the
`taskkill /T` tree-kill, and four hand-rolled terminal spawns. That is four to
eight places to write each platform branch, which is why this module has to
exist before the POSIX port rather than after it.
"""

import os
import re as _re
import subprocess
import sys
import time

__all__ = ['run', 'git', 'pid_alive', 'kill_tree', 'spawn_terminal',
           'spawn_detached', 'wait_and_run', 'python_exe', 'new_console_flags',
           'no_window_flags', 'WINDOWS']

WINDOWS = os.name == 'nt'

#: CREATE_NEW_CONSOLE where it exists, 0 elsewhere — `getattr` because the
#: constant is not defined on POSIX and a bare reference is an AttributeError
#: at import, not at the call.
new_console_flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)

#: CREATE_NO_WINDOW — the opposite flag, and the one every CAPTURED call needs.
#: Without it Windows gives each console child its own console window: opening
#: the Repos or Tools tab runs git across a dozen repos and the user watches a
#: dozen black windows flash open and shut. Nothing is ever shown in them —
#: stdout and stderr are captured — so the window is pure visual noise.
no_window_flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

#: DETACHED_PROCESS — no console AT ALL, and no tie to ours. The child of a
#: detached spawn outlives archeus, which is the whole point of the deferred
#: upgrade worker: it starts here and does its work after we are gone.
detached_flags = getattr(subprocess, 'DETACHED_PROCESS', 0) or no_window_flags


def run(args, *, cwd=None, env=None, timeout=30, stdin=None, check=False):
    """`subprocess.run` with the decoding pinned and the console suppressed.
    Returns the CompletedProcess, or None if it could not be run at all.

    `text=True` alone decodes with the locale codepage — cp1252 on Windows —
    so one non-ASCII path or branch name raises *inside* subprocess and the
    caller concludes the command failed. Every call in this codebase goes
    through here for that reason.

    `creationflags` is the second reason: output is captured, so a console
    window would show nothing and only flash. See no_window_flags.

    With no `stdin`, the child gets DEVNULL rather than inheriting ours. A CLI
    that decides to ask a question would otherwise block forever on a terminal
    nobody is watching — and inside a captured run there is no prompt to see.
    """
    try:
        r = subprocess.run(args, cwd=cwd, env=env, capture_output=True,
                           text=True, encoding='utf-8', errors='ignore',
                           timeout=timeout, input=stdin,
                           stdin=None if stdin is not None else subprocess.DEVNULL,
                           creationflags=no_window_flags)
    except Exception:
        return None
    if check and r.returncode:
        return None
    return r


def git(args, cwd, timeout=15):
    """git stdout, or None when the command failed or git is absent."""
    r = run(['git'] + list(args), cwd=cwd, timeout=timeout)
    if r is None or r.returncode:
        return None
    return r.stdout


#: schemes a remote may use. Deliberately an allowlist, not a denylist of the
#: dangerous ones — git keeps adding transports.
_REMOTE_RE = _re.compile(r'^(?:https?://|ssh://|git://|git@[\w.-]+:)[\w.@:/~%-]')


def remote_url_ok(url):
    """Is this safe to hand to `git clone` / `claude plugin marketplace add`?

    Two separate hazards, and argv-list form only closes one of them:

      * `ext::sh -c <payload>` is a real git transport, and `protocol.ext.allow`
        defaults to `user` — which a direct CLI invocation is. Cloning that URL
        executes the payload. No shell is involved; git IS the shell.
      * a URL beginning `-` lands in an OPTION position (`--upload-pack=…`,
        `--config=…`), so callers must also pass `--` before it.

    An allowlist of schemes is the whole fix. Callers still add `--`.
    """
    u = str(url or '').strip()
    return bool(u) and len(u) < 2048 and bool(_REMOTE_RE.match(u))


def pid_alive(pid):
    """True / False, or None when it cannot be determined.

    NEVER `os.kill(pid, 0)` on Windows — that signal number is not a probe
    there, it terminates the process.
    """
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    if WINDOWS:
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
            if not h:
                return False
            try:
                # Opening a handle is not enough: an exited process keeps one
                # until every handle is closed, so ask for the exit code.
                code = ctypes.c_ulong()
                if k32.GetExitCodeProcess(h, ctypes.byref(code)):
                    return code.value == 259          # STILL_ACTIVE
                return False
            finally:
                k32.CloseHandle(h)
        except Exception:
            return None                               # unknown → age decides
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # exists, owned by someone else
    except Exception:
        return None


def spawn_detached(argv, *, cwd=None, env=None, log=None):
    """Start *argv* with no console and no tie to this process.

    Returns (Popen|None, error) — the same shape as spawn_terminal, because
    it is the same decision made the other way. A console is right for work
    the user is meant to watch (a Claude session, a shell in a project) and
    pure damage for work they are not: the upgrade worker's first act is to
    BLOCK until archeus exits, so its window stole focus and then sat there
    doing nothing until you quit.

    *log* is a file to append the output to, since a detached child has
    nowhere else to put it and its failure is the only record of why an
    upgrade did not happen.
    """
    sink = subprocess.DEVNULL
    if log:
        try:
            os.makedirs(os.path.dirname(log), exist_ok=True)
            sink = open(log, 'ab')
        except Exception:
            sink = subprocess.DEVNULL
    kw = {'cwd': cwd, 'env': env, 'stdin': subprocess.DEVNULL,
          'stdout': sink, 'stderr': subprocess.STDOUT}
    if WINDOWS:
        kw['creationflags'] = detached_flags
    else:
        kw['start_new_session'] = True
    try:
        return subprocess.Popen(list(argv), **kw), ''
    except Exception as e:
        return None, str(e)
    finally:
        if sink is not subprocess.DEVNULL:
            try:
                sink.close()          # the child holds its own handle now
            except Exception:
                pass


def python_exe():
    """`sys.executable`, but never `pythonw.exe`.

    This is the whole reason the self-update had never once worked from the
    desktop app. The GUI runs under `pythonw`, so `sys.executable` is
    `pythonw.exe`, and a `pythonw` child started with an inherited FILE handle
    gets `sys.stdout = None` — pip then exits 1 having printed nothing at all,
    not even the traceback, because its stderr is None too. The update log held
    the worker's own two lines and no pip output whatsoever, which reads as
    "the install never ran".

    Measured, both ways: `pythonw.exe -m pip --version` through the detached
    worker returns 1 with an empty log; `python.exe -m pip --version` through
    the same worker returns 0 and logs the version. Same family as the hook
    lesson already in CLAUDE.md — under `pythonw` there is no stdout, and
    anything that writes to one dies.
    """
    exe = sys.executable or ''
    base = os.path.basename(exe)
    if base.lower().startswith('pythonw'):
        cand = os.path.join(os.path.dirname(exe), 'python' + base[7:])
        if os.path.isfile(cand):
            return cand
    return exe


def _is_locked(path):
    """Can pip overwrite this file? Opening for append is the cheap probe: a
    running .exe is mapped by the loader and refuses write sharing."""
    try:
        with open(path, 'ab'):
            return False
    except OSError:
        return True


def free_locked(paths, out=print):
    """Move any locked file in *paths* aside, and say what was moved.

    An upgrade cannot overwrite the console script of the process running it —
    but Windows opens a running image with FILE_SHARE_DELETE, so it can be
    RENAMED, and pip then writes a fresh one beside it. That is the difference
    between "quit archeus and update" and "update now", and it is measured: with
    the script locked, `pip install -U` fails with WinError 32 **after it has
    already uninstalled the package**, leaving nothing installed at all. With
    the script moved aside first, the same install returns 0.

    Returns [(aside, original)] so a FAILED install can put them back — a user
    whose upgrade did not happen must still have the command they had before.
    """
    moved = []
    for path in paths or ():
        if not path or not os.path.isfile(path) or not _is_locked(path):
            continue
        # leftovers from a previous update, now that nothing holds them
        for old in _aside_siblings(path):
            try:
                os.remove(old)
            except OSError:
                pass
        aside = '%s.old-%d' % (path, int(time.time()))
        try:
            os.replace(path, aside)
        except OSError as e:
            out('could not move %s aside: %s' % (path, e))
            continue
        moved.append((aside, path))
        out('moved aside (in use): ' + path)
    return moved


def _aside_siblings(path):
    import glob
    return [p for p in glob.glob(path + '.old-*') if os.path.isfile(p)]


def restore_locked(moved, out=print):
    """Undo `free_locked` — only for the paths pip did not replace itself."""
    for aside, path in moved or ():
        if os.path.exists(path):
            continue                      # pip wrote a new one; keep that
        try:
            os.replace(aside, path)
            out('restored: ' + path)
        except OSError as e:
            out('could not restore %s: %s' % (path, e))


def wait_and_run(pid, argv, timeout=None, poll=0.5, out=print, after=(), free=()):
    """Wait for *pid* to exit, then run *argv* and return its exit code.

    This is what lets a program replace its own files: archeus's upgrade
    rewrites the console script it is running from, which Windows keeps locked
    until the process ends. Lives here rather than in versions.py so the waiting
    process can reach it without importing the package pip is replacing — this
    module imports only the standard library, nothing from archeus.

    The wait is UNBOUNDED, and that is the fix for the bug this shipped with: it
    was capped at five minutes, after which it ran the install anyway. The user
    is told "it installs when you close archeus" and then keeps working — a
    session lasts hours — so the cap fired first every time, pip met the locked
    console script it was told to wait for, and the whole thing failed into a
    log file nobody reads. Which is what "update now does nothing" was. A
    finite *timeout* is still honoured for a caller that wants one, but on
    expiry the command is SKIPPED rather than run against a live process: a
    deferral that gives up and does the unsafe thing anyway is worse than one
    that reports it could not.

    `pid_alive` returning None means "cannot tell"; that stops the wait rather
    than hanging on it, and the command's own error is then the honest report.

    *after* is argv lists to start once the command SUCCEEDS — the desktop
    notification saying the upgrade landed, and archeus itself when the user
    asked to restart into it. They are built by the caller before the install
    begins, because pip is replacing every file this package could import.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        pid = 0
    if not argv:
        return 2
    out('Waiting for archeus to exit...')
    deadline = None if timeout is None else time.time() + timeout
    while pid:
        if pid_alive(pid) is not True:
            break
        if deadline is not None and time.time() >= deadline:
            out('Gave up waiting for pid %d — NOT installing over a running '
                'archeus. Quit it and update again.' % pid)
            return 1
        time.sleep(poll)
    moved = free_locked(free, out)
    out('Running: ' + ' '.join(argv))
    # CAPTURED, never inherited, and this is the bug that made the self-update
    # fail silently for its whole life. This process is detached: its stdout is
    # a file handle, and a child started with no redirection of its own does not
    # inherit it — CreateProcess is called with bInheritHandles false — so pip
    # came up with `sys.stdout` None, printed nothing anywhere, and under
    # `pythonw` died of it with exit 1 and not one line of traceback. The log
    # held this function's own two lines and nothing else, which reads exactly
    # like "the install never ran". Capturing gives pip real pipes AND puts its
    # output in the log, which is the only place a windowless worker can speak.
    r = run(argv, timeout=1800)
    if r is None:
        out('Failed: could not run ' + argv[0])
        restore_locked(moved, out)
        return 1
    for chunk in (r.stdout, r.stderr):
        if chunk and chunk.strip():
            out(chunk.strip())
    rc = r.returncode
    if rc:
        out('Exit code %s' % rc)
        restore_locked(moved, out)
    else:
        for cmd in after or ():
            if cmd:
                spawn_detached(cmd)
    return rc


def kill_tree(proc):
    """Kill a process and everything it spawned. `Popen.kill` on Windows kills
    only the direct child, which for a `cmd /c claude ...` chain leaves the
    thing the user actually wanted stopped still running."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if WINDOWS:
            r = subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                               capture_output=True,
                               creationflags=no_window_flags)
            if r.returncode:      # no such pid, or access denied — try direct
                proc.kill()
        elif os.getpgid(proc.pid) == proc.pid:
            # Only when the child leads its own group. Otherwise its group is
            # OURS, and killpg would take down archeus along with it.
            os.killpg(proc.pid, 15)
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ── terminal windows ─────────────────────────────────────────

#: tried in order; the first one on PATH wins
_POSIX_TERMINALS = [
    ('x-terminal-emulator', ['-e']),
    ('gnome-terminal', ['--']),
    ('konsole', ['-e']),
    ('xfce4-terminal', ['-e']),
    ('alacritty', ['-e']),
    ('kitty', []),
    ('xterm', ['-e']),
]


def spawn_terminal(argv=None, *, cwd=None, env=None, title='', keep_open=False):
    """Open a NEW terminal window running *argv* (a plain shell when None).

    Returns (Popen|None, error). *keep_open* leaves the window up after the
    command exits — the "just give me a shell here" case. Otherwise the window
    closes on ANY exit code: ending a Claude session with Ctrl+C returns
    non-zero on Windows, and a `|| pause` left the window stuck on a keypress
    for every normal exit, not just crashes.
    """
    if WINDOWS:
        return _spawn_windows(argv, cwd, env, title, keep_open)
    return _spawn_posix(argv, cwd, env, title, keep_open)


def _spawn_windows(argv, cwd, env, title, keep_open):
    # argv-list form, never shell=True: list2cmdline quotes each argument, so a
    # project or account name containing " & | cannot break out of the title
    # and run something else.
    if argv is None:
        cmd = ['cmd', '/k'] + (['title', title] if title else [])
    elif keep_open:
        cmd = ['cmd', '/k'] + (['title', title, '&&'] if title else []) + list(argv)
    else:
        cmd = ['cmd', '/c'] + (['title', title, '&&'] if title else []) + list(argv)
    try:
        return subprocess.Popen(cmd, cwd=cwd, env=env,
                                creationflags=new_console_flags), ''
    except Exception as e:
        return None, str(e)


def _spawn_posix(argv, cwd, env, title, keep_open):
    import shutil

    inner = list(argv) if argv else [os.environ.get('SHELL') or '/bin/sh']
    if keep_open and argv:
        sh = os.environ.get('SHELL') or '/bin/sh'
        inner = [sh, '-c', _quote(inner) + '; exec ' + sh]

    if sys.platform == 'darwin':
        script = 'cd %s && %s' % (_quote([cwd or os.getcwd()]), _quote(inner))
        try:
            return subprocess.Popen(
                ['osascript', '-e',
                 'tell application "Terminal" to do script %s' % _applescript_str(script)],
                env=env), ''
        except Exception as e:
            return None, str(e)

    for name, flag in [(os.environ.get('TERMINAL') or '', ['-e'])] + _POSIX_TERMINALS:
        if not name or not shutil.which(name):
            continue
        try:
            return subprocess.Popen([name] + flag + inner, cwd=cwd, env=env,
                                    start_new_session=True), ''
        except Exception:
            continue
    # No terminal emulator at all (a headless box, or a container). Detaching is
    # still better than refusing: the caller reports the command so the user can
    # run it in their own window.
    try:
        return subprocess.Popen(inner, cwd=cwd, env=env, start_new_session=True), ''
    except Exception as e:
        return None, str(e)


def _quote(args):
    import shlex
    return ' '.join(shlex.quote(a) for a in args)


def _applescript_str(s):
    return '"%s"' % s.replace('\\', '\\\\').replace('"', '\\"')
