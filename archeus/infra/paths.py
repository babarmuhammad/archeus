"""`ARCHEUS_HOME` and every path derived from it (target-architecture §5.1).

Resolved at CALL time, never as a module constant: tests (and every execution
Core starts) set `ARCHEUS_HOME`, and an import-time path is a cache with no
invalidation — this codebase's recurring bug.

`~/.archeus/` is NOT the V1 home and is refused even when named explicitly: it
is already a legacy project workdir (the one for any project rooted at the home
directory), legacy code writes logs and memory there, and legacy cleanup may
delete below any `.archeus` directory. Nothing here creates, migrates or deletes
it — or anything else: these functions compute paths and touch no disk.
"""

import os
import sys

from ..core.domain import ids


LEGACY_DIRNAME = '.archeus'

#: What V1 owns directly under `<ARCHEUS_HOME>` (target-architecture §5.1). The
#: directory is NOT V1's alone: the legacy Qt shell names its application
#: `archeus`, so Qt's per-user locations land here too (`cache/` on Windows,
#: where NTFS makes `archeus` and `Archeus` one directory; its app-data dir on
#: Linux). V1 creates only these entries, and a reset removes only these —
#: never the directory as a whole.
V1_OWNED = ('archeus.db', 'archeus.db-wal', 'archeus.db-shm', 'artifacts', 'backups',
            'logs', 'repos', 'run', 'runtime', 'worktrees')

#: Entries the legacy Qt shell (claude_sessions/gui_qt.py) may keep here. V1
#: never writes, moves or deletes them.
QT_OWNED = ('cache', 'QtWebEngine')


def archeus_home(environ=None, platform=None):
    """The V1 data directory, as an absolute path.

    1. `ARCHEUS_HOME` (non-empty)
    2. Windows: `%LOCALAPPDATA%\\Archeus`
    3. macOS: `~/Library/Application Support/Archeus`
    4. Linux/other POSIX: `$XDG_DATA_HOME/archeus` (absolute values only, per
       the XDG spec), else `~/.local/share/archeus`

    `environ`/`platform` default to the live process; tests pass their own.
    """
    env = os.environ if environ is None else environ
    plat = sys.platform if platform is None else platform
    home = os.path.expanduser('~')
    explicit = env.get('ARCHEUS_HOME', '').strip()
    if explicit:
        path = os.path.expanduser(explicit)
    elif plat.startswith('win'):
        base = env.get('LOCALAPPDATA', '').strip() or os.path.join(home, 'AppData', 'Local')
        path = os.path.join(base, 'Archeus')
    elif plat == 'darwin':
        path = os.path.join(home, 'Library', 'Application Support', 'Archeus')
    else:
        xdg = env.get('XDG_DATA_HOME', '').strip()
        base = xdg if xdg and os.path.isabs(xdg) else os.path.join(home, '.local', 'share')
        path = os.path.join(base, 'archeus')
    path = os.path.abspath(path)
    # not just ~/.archeus itself: legacy cleanup (gui_api._managed_path_ok) may
    # delete below ANY directory named .archeus, so no V1 home may sit in one
    parts = os.path.normcase(path).replace('\\', '/').split('/')
    if LEGACY_DIRNAME in parts:
        raise ValueError('ARCHEUS_HOME may not be (or be inside) a legacy .archeus '
                         'directory, which holds legacy project data: %s' % path)
    return path


def run_dir():
    """`<ARCHEUS_HOME>/run` — liveness and e-stop files that work without Core."""
    return os.path.join(archeus_home(), 'run')


def runtime_dir():
    """`<ARCHEUS_HOME>/runtime` — Core-staged copies of the hook's runtime, one
    directory per content digest, kept (PV-20 C4a, node/staging.py)."""
    return os.path.join(archeus_home(), 'runtime')


def repos_dir():
    """`<ARCHEUS_HOME>/repos` — Core's own Git stores, one bare repository per
    project, and the pin files they run under (PV-20 K1, node/local.py); kept."""
    return os.path.join(archeus_home(), 'repos')


def repo_store(project_id):
    """`<ARCHEUS_HOME>/repos/<project_id>.git` — one project's Core-owned store."""
    if not ids.is_id(project_id, 'project'):
        raise ValueError('not a project id: %r' % (project_id,))
    return os.path.join(repos_dir(), '%s.git' % project_id)


def seed_staging(execution_id):
    """`<ARCHEUS_HOME>/repos/.seed/<execution_id>` — where Core builds an
    execution's seeded repository before renaming it into the execution's
    workspace (PV-20 K2, T-049 §4): Core's, never an execution's; kept."""
    if not ids.is_id(execution_id, 'execution'):
        raise ValueError('not an execution id: %r' % (execution_id,))
    return os.path.join(repos_dir(), '.seed', execution_id)


def stop_sentinel():
    """`<ARCHEUS_HOME>/run/STOP` — the e-stop sentinel (execution-architecture
    §10). P9 only reads whether it exists (every policy decision is DENY while
    it does); writing and clearing it is the e-stop's (P11)."""
    return os.path.join(run_dir(), 'STOP')


def processes_registry():
    """`<ARCHEUS_HOME>/run/processes.jsonl` — every spawned process, for e-stop
    and boot reconciliation without the database."""
    return os.path.join(run_dir(), 'processes.jsonl')


# ── PV-20 S1: Core's isolation state (pv20-execution-isolation-design §3.3, §3.7) ──
#
# Deliberately NOT under `run/exec/<id>/`: an isolation record is Core-owned state,
# and Core-owned state is what an execution's directory must not be able to author.


def isolation_dir():
    """`<ARCHEUS_HOME>/run/isolation` — Core's own record of which execution holds
    which identity, grants and Job (PV-20 §3.7). Core writes it, Core reads it."""
    return os.path.join(run_dir(), 'isolation')


#: A6 (T-054): a verifier attempt's key is `verify/<verification_id>.<attempt>`. An
#: execution's key is its own id, so every execution record path stays as it was.
VERIFY_KEY = 'verify/'
#: bounds the attempt so a verifier's profile name never reaches the 127-character cut
MAX_ATTEMPT = 10 ** 6


def verify_key_parts(key):
    """`(verification_id, attempt)` of a verifier key, or ValueError. The attempt is
    canonical decimal, so one attempt has one key."""
    rest = key[len(VERIFY_KEY):] if isinstance(key, str) and key.startswith(VERIFY_KEY) else ''
    vid, _, n = rest.rpartition('.')
    if not (ids.is_id(vid, 'verification') and n.isascii() and n.isdigit()
            and n == str(int(n)) and int(n) < MAX_ATTEMPT):
        raise ValueError('not a verifier key: %r' % (key,))
    return vid, int(n)


def isolation_state(key):
    """`<ARCHEUS_HOME>/run/isolation/<execution_id>.json` — one execution's isolation
    record: the state a restarted Core reconciles against (PV-20 §3.7). A verifier
    attempt's is `run/isolation/verify/<verification_id>.<attempt>.json`."""
    if isinstance(key, str) and key.startswith(VERIFY_KEY):
        vid, n = verify_key_parts(key)
        return os.path.join(isolation_dir(), 'verify', '%s.%d.json' % (vid, n))
    if not ids.is_id(key, 'execution'):
        raise ValueError('not an execution id: %r' % (key,))
    return os.path.join(isolation_dir(), '%s.json' % key)


def verify_consumed(key):
    """`run/isolation/verify/<verification_id>.<attempt>.consumed` — the marker that a
    verifier attempt was admitted once (A6). Created exclusively before anything else
    about the attempt, and never removed: teardown and reclaim delete the record, and
    the attempt must still never start again, under this Core or a restarted one."""
    vid, n = verify_key_parts(key)
    return os.path.join(isolation_dir(), 'verify', '%s.%d.consumed' % (vid, n))


def quarantine_log():
    """`<ARCHEUS_HOME>/run/isolation/quarantine.jsonl` — the grants and profiles Core
    could not remove, retried on boot (PV-20 §3.7)."""
    return os.path.join(isolation_dir(), 'quarantine.jsonl')


#: PV-20 §7.5 (R2): the directories inside an execution's own one, one per resource
#: class, so that what the execution may write is never where Core answers it. The
#: execution hook mirrors these names (it imports nothing from this package).
REQUEST_DIR = 'req'         # class 1: the execution's requests and reports, untrusted
RESPONSE_DIR = 'res'        # class 2: Core's answers and the spawn configuration it wrote
SENTINEL_DIR = 'ctl'        # class 3: the STOP / PAUSE / HANDOFF flags Core sets
PRIVATE_DIR = 'own'         # class 7: the execution's own workspace and state


class ExecPaths:
    """The per-execution files of the process I/O contract
    (execution-architecture §3.1), all in `<ARCHEUS_HOME>/run/exec/<execution_id>/`.
    That directory and the contract files in it are Core's (PV-20 class 4); the
    class 1, 2, 3 and 7 directories inside it are the execution's interface."""

    __slots__ = ('execution_id', 'dir', 'spawning', 'prompt', 'stream', 'pid', 'ended',
                 'req', 'res', 'ctl', 'work', 'state', 'config', 'tmp', 'home')

    def __init__(self, execution_id, run=None):
        # the id becomes a directory name: only a well-formed id may, so no
        # caller can walk out of run/exec with `..` or a separator
        if not ids.is_id(execution_id, 'execution'):
            raise ValueError('not an execution id: %r' % (execution_id,))
        self.execution_id = execution_id
        self.dir = os.path.join(run or run_dir(), 'exec', execution_id)
        self.spawning = os.path.join(self.dir, 'spawning')     # marker, before spawn
        self.prompt = os.path.join(self.dir, 'prompt.txt')     # the process's stdin
        self.stream = os.path.join(self.dir, 'stream.jsonl')   # stdout+stderr, tailed
        self.pid = os.path.join(self.dir, 'pid.json')          # {pid, create_time}
        self.ended = os.path.join(self.dir, 'ended')           # {exit_code, at}
        self.req = os.path.join(self.dir, REQUEST_DIR)
        self.res = os.path.join(self.dir, RESPONSE_DIR)
        self.ctl = os.path.join(self.dir, SENTINEL_DIR)
        self.work = os.path.join(self.dir, PRIVATE_DIR, 'work')   # a project-less workspace
        self.state = os.path.join(self.dir, PRIVATE_DIR, 'state')
        self.config = os.path.join(self.state, 'config')   # isolated CLAUDE_CONFIG_DIR (A2)
        self.tmp = os.path.join(self.state, 'tmp')          # isolated TEMP and TMP
        self.home = os.path.join(self.state, 'home')        # isolated profile (USERPROFILE...)


def exec_paths(execution_id):
    return ExecPaths(execution_id)


class VerifyPaths:
    """One verifier attempt's files (A6, T-054 §4), in
    `<ARCHEUS_HOME>/run/verify/<verification_id>/<attempt>/`. That directory and `out`
    are Core's; `own/` is the verifier's class 7, its checkout and scratch."""

    __slots__ = ('dir', 'out', 'checkout', 'home', 'tmp', 'config')

    def __init__(self, verification_id, attempt, run=None):
        vid, n = verify_key_parts('%s%s.%s' % (VERIFY_KEY, verification_id, attempt))
        self.dir = os.path.join(run or run_dir(), 'verify', vid, str(n))
        self.out = os.path.join(self.dir, 'out.log')
        own = os.path.join(self.dir, PRIVATE_DIR)
        self.checkout = os.path.join(own, 'checkout')
        self.home = os.path.join(own, 'home')
        self.tmp = os.path.join(own, 'tmp')
        self.config = os.path.join(own, 'config')
