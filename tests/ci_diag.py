"""CI performance diagnostics (P12 Windows throughput investigation).

Off unless ARCHEUS_CI_DIAG names a file: then every record is one JSON line
appended to it, and `tools/ci_diag.py` summarises the file. Nothing here changes
what a test does or asserts; with the variable unset every call is a no-op.

What it can see, and what it cannot:
- process launches are counted through `sys.addaudithook` (the `subprocess.Popen`
  and `os.*spawn*`/`os.system`/`os.startfile` audit events), so a launch is
  counted however the code reached Popen. Only launches made by THIS pytest
  process: a grandchild started by a child Core or a fake agent is invisible
  to the counter, which is what the process census is for.
- the census counts processes system-wide by image name (Toolhelp on Windows,
  `ps` elsewhere): it sees leaked children and anything else on the runner.
"""

import json
import os
import sys
import threading
import time

PATH = os.environ.get('ARCHEUS_CI_DIAG')
enabled = bool(PATH)
_lock = threading.Lock()
launches = 0
_LAUNCH_EVENTS = frozenset(('subprocess.Popen', 'os.system', 'os.startfile', 'os.spawn',
                            'os.posix_spawn'))


def _audit(event, args):
    global launches
    if event in _LAUNCH_EVENTS:
        launches += 1


def install():
    """Once per interpreter: an audit hook cannot be removed."""
    if enabled and not getattr(sys, '_archeus_ci_diag', False):
        sys._archeus_ci_diag = True
        sys.addaudithook(_audit)


def record(kind, **fields):
    if not enabled:
        return
    line = json.dumps(dict(fields, kind=kind, t=round(time.time(), 3),
                           platform=sys.platform, py='%d.%d' % sys.version_info[:2],
                           job=os.environ.get('ARCHEUS_CI_JOB', '')),
                      default=str)
    with _lock, open(PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def census():
    """{'total': n, 'python': n, 'git': n, 'tops': {image: n}} or {'error': ...};
    None (and no work) when the diagnostics are off."""
    if not enabled:
        return None
    try:
        names = _windows_images() if sys.platform == 'win32' else _ps_images()
    except Exception as err:                    # a diagnostic must never fail a test
        return {'error': repr(err)}
    counts = {}
    for n in names:
        n = os.path.basename(n).lower()
        counts[n] = counts.get(n, 0) + 1
    py = sum(v for k, v in counts.items() if k.startswith('python'))
    tops = dict(sorted(counts.items(), key=lambda kv: -kv[1])[:8])
    return {'total': len(names), 'python': py, 'git': counts.get('git.exe', counts.get('git', 0)),
            'threads_here': threading.active_count(), 'tops': tops}


def _windows_images():
    import ctypes
    from ctypes import wintypes

    class PE(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_void_p),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', ctypes.c_long),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_wchar * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)               # TH32CS_SNAPPROCESS
    if snap in (None, wintypes.HANDLE(-1).value):
        raise OSError('CreateToolhelp32Snapshot failed')
    out, e = [], PE()
    e.dwSize = ctypes.sizeof(PE)
    try:
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append(e.szExeFile)
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return out


def _ps_images():
    import subprocess
    return subprocess.run(['ps', '-A', '-o', 'comm='], capture_output=True, text=True,
                          timeout=10).stdout.split()


def _fsync_probe(directory, n=100):
    """Seconds per write(4 KiB)+fsync, on the volume `directory` lives on."""
    path = os.path.join(directory, 'ci-diag-fsync.bin')
    lat = []
    try:
        with open(path, 'wb') as f:
            for _ in range(n):
                t = time.perf_counter()
                f.write(b'x' * 4096)
                f.flush()
                os.fsync(f.fileno())
                lat.append(time.perf_counter() - t)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return _stats(lat)


def _sqlite_probe(directory, n=200):
    """Seconds per single-row commit under the writer's own pragmas (WAL,
    synchronous=FULL), with none of the writer's code in the way."""
    import sqlite3
    path = os.path.join(directory, 'ci-diag.db')
    c = sqlite3.connect(path, isolation_level=None)
    lat = []
    try:
        c.execute('PRAGMA journal_mode = WAL')
        c.execute('PRAGMA synchronous = FULL')
        c.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, body TEXT)')
        for i in range(n):
            t = time.perf_counter()
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO t (body) VALUES (?)', ('x' * 300,))
            c.execute('COMMIT')
            lat.append(time.perf_counter() - t)
    finally:
        c.close()
        for suffix in ('', '-wal', '-shm'):
            try:
                os.remove(path + suffix)
            except OSError:
                pass
    return _stats(lat)


def _cpu_probe():
    """Best of three seconds for a fixed pure-Python workload."""
    best = None
    for _ in range(3):
        t = time.perf_counter()
        sum(i * i for i in range(1_000_000))
        d = time.perf_counter() - t
        best = d if best is None else min(best, d)
    return round(best, 4)


def _stats(xs):
    xs = sorted(xs)
    return {'n': len(xs), 'mean_ms': round(1000 * sum(xs) / len(xs), 3),
            'p50_ms': round(1000 * xs[len(xs) // 2], 3),
            'p95_ms': round(1000 * xs[int(len(xs) * 0.95) - 1], 3),
            'max_ms': round(1000 * xs[-1], 3)}


def probes(db_dir):
    """Disk, SQLite and CPU cost right now: on the volume the test database
    lives on and, on a runner, on RUNNER_TEMP (a different volume on the
    Windows images: C: vs D:)."""
    out = {'cpu_s': _cpu_probe()}
    dirs = {'db_dir': db_dir}
    if os.environ.get('RUNNER_TEMP'):
        dirs['runner_temp'] = os.environ['RUNNER_TEMP']
    for name, d in dirs.items():
        try:
            out[name] = {'path': d, 'fsync': _fsync_probe(d), 'sqlite_commit': _sqlite_probe(d)}
        except Exception as err:
            out[name] = {'path': d, 'error': repr(err)}
    return out
