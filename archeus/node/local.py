"""The local execution node (execution-architecture §9; p11-design-gate §5).

Everything P11 does to the world outside the database goes through here:
spawning through an adapter, the process registry, checks and kills by process
identity, the per-execution control flags, the e-stop sentinel, the hook
mailbox, the few git reads the boundary checks need, and worktrees.

It never opens the database, never evaluates policy and never routes (a
boundary test holds it to that): it is what a remote node would be, in-process.

A process is identified by (pid, create_time), never by a pid alone
(p11-design-gate §15.1): every liveness check and kill re-reads the creation
time through the P0.5 seam `proc.process_create_time`.
"""

import functools
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import threading
import time

from claude_sessions import config, proc

from ..core.domain import ids
from ..harnesses import base
from ..infra.paths import (ExecPaths, archeus_home, processes_registry, repo_store, repos_dir,
                           run_dir, seed_staging, stop_sentinel)
from . import isolation as isolation_mod
from .staging import _entry, _present

#: control flags the hook reads (P11 PAUSE/STOP; P12 HANDOFF, p12-design-gate §10.1)
FLAGS = ('PAUSE', 'STOP', 'HANDOFF')
#: Core's own git identity for the snapshot commit and merges (P13 §12), set per
#: command so the user's configuration is never read or changed
CORE_GIT_NAME, CORE_GIT_EMAIL = 'Archeus', 'archeus@localhost'
#: the tail of a check's output kept as evidence (p13-design-gate §8.2)
CHECK_OUTPUT_KEEP = 256 * 1024

# PV-20 K1 (T-046 and its correction C-1013-T046): Core's own Git store, run by one
# pinned runner. The pins remove Git's configured execution points; they do not
# make Git a sandbox for hostile objects.

#: the oldest Git that honours every pin `_store_pin` sets: GIT_NO_LAZY_FETCH
#: first appears in the 2.45.0 git(1) manual and is absent from v2.44.0's git.c
#: and promisor-remote.c; `--attr-source`/GIT_ATTR_SOURCE from 2.41.0,
#: GIT_CONFIG_GLOBAL/SYSTEM earlier (absent from 2.31.0)
STORE_GIT_FLOOR = (2, 45, 0)
#: every store is created SHA-1, so this is the empty tree its attributes come from
EMPTY_TREE = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
#: a store's HEAD: unborn, so no tree of its content is ever "the current one"
STORE_HEAD = 'ref: refs/archeus/none\n'
#: the plumbing `store_read` may run in a trusted store
STORE_READS = ('rev-parse', 'cat-file', 'ls-tree', 'merge-base', 'diff')
#: per mode, the only subcommands the runner starts
_STORE_ARGS = {'version': ('version',), 'init': ('init',), 'seal': ('symbolic-ref', 'mktree'),
               'trusted': STORE_READS + ('fetch', 'update-ref'), 'base': ('rev-parse',),
               'seed': ('fetch', 'update-ref', 'symbolic-ref', 'read-tree', 'ls-files',
                        'rev-parse'),
               'import': ('fast-import',)}
#: exactly the config `init --bare` writes, whole: one [core] section, its keys
#: in Git's order, each once. Observed at 2.49.0.windows.1 (T-048): format 0,
#: filemode false, bare true, symlinks false, ignorecase true; symlinks,
#: ignorecase and precomposeunicode are platform probes written only when found
_INIT_CONFIG = re.compile(r'\[core\]\n\trepositoryformatversion = 0\n\tfilemode = (true|false)\n'
                          r'\tbare = true\n(\tsymlinks = false\n)?(\tignorecase = true\n)?'
                          r'(\tprecomposeunicode = true\n)?')
_REF = re.compile(r'refs/[A-Za-z0-9_][A-Za-z0-9_./-]*')
#: what a source's config may not say at all (case-insensitive bytes, fail
#: closed: a value that merely contains one is refused too): includes, promisor
#: remotes and partial clones (lazy fetch from them), another object format, a
#: ref backend other than files, and alternate-ref commands
_SOURCE_CONFIG_REFUSED = (b'include', b'promisor', b'partialclone', b'objectformat',
                          b'refstorage', b'alternaterefs')
#: a pack fetched from a promisor remote: its repository lazy-fetches
_PROMISOR_PACK = '.promisor'
#: a `.git` file larger than this is refused (Git reads up to 1 MiB: setup.c
#: read_gitfile_gently); no path Core resolves is anywhere near it
_GITFILE_MAX = 64 * 1024

# PV-20 K2 (T-049 and its correction C-1013-T049): an isolated execution's seed,
# built by Core outside the execution area and renamed in. Every bound below is
# checked before the write it guards; one breached refuses the whole seed.
SEED_MAX_ENTRIES = 100000
SEED_MAX_BYTES = 2 * 1024 ** 3
SEED_MAX_DEPTH = 64
#: a file's whole Windows path, long-path support assumed absent
SEED_MAX_PATH = 259
#: one `ls-tree -l` or `ls-files -s` record as received, and so the whole listing
SEED_MAX_RECORD = 4200
#: seconds for the whole seed; each Git call also keeps its own timeout
SEED_DEADLINE = 300
#: the stdout read size of the byte core; stderr keeps this much and drops the rest
_CHUNK, _STDERR_KEEP = 64 * 1024, 4096
#: mode -> type an entry may have; 120000 and 160000 seeded inertly (owner Q1, A)
_SEED_KINDS = {'100644': 'blob', '100755': 'blob', '120000': 'blob', '160000': 'commit'}
#: the seed's .git/config, exactly: no remote, include or filter
SEED_CONFIG = (b'[core]\n\trepositoryformatversion = 0\n\tfilemode = false\n'
               b'\tbare = false\n\tsymlinks = false\n\tautocrlf = false\n')
#: the seed's .git holds exactly these, and nothing else
_SEED_META = frozenset(('HEAD', 'config', 'shallow', 'index', 'objects', 'refs'))
#: a task branch, one segment under archeus/ (manager: archeus/<mission>.<key>)
_SEED_BRANCH = re.compile(r'archeus/[A-Za-z0-9_][A-Za-z0-9_.-]*')
_UNSAFE = re.compile(r'[\\:<>"|?*\x00-\x1f\x7f]')
_DEVICE = re.compile(r'(?i)(con|prn|aux|nul|conin\$|conout\$|(com|lpt)[0-9\u00b9\u00b2\u00b3])')


class StoreError(OSError):
    """A store, its pin or a Git call cannot be trusted: refused, nothing kept back."""


class LocalNode:
    id = None       # the local node (ADR-0008): no ExecutionNode row in V1

    #: what the hook reads (P11 PAUSE/STOP; P12 HANDOFF) — see FLAGS below
    def __init__(self, isolation=None):
        #: Core's isolation authority for this process (PV-20 §3.7): the per-execution
        #: identities, the Jobs only Core holds, the quarantine ledger. Injected by the
        #: synthetic fixtures; the production node gets the real boundary, which
        #: dispatches nothing isolated while production dispatch stays E's.
        self.isolation = isolation if isolation is not None else isolation_mod.Isolation(self)

    # ── processes ──

    def spawn(self, adapter, spec, *, isolated, resume_state=None):
        """Start one process of an execution (its first, or a resume) and record
        it in the registry. Raises base.SpawnFailed / base.AlreadySpawned.

        `isolated` (PV-20 §3.4) is the decision Core's manager took from this node's
        isolation authority before the workspace and the inventory; it is required,
        so nothing here can take a second one that disagrees. An isolated
        execution's registry line carries the identity it ran under — the instrument,
        never the authority (§3.7); the Job Core holds is the authority.
        """
        self.clear_flags(spec.execution_id)
        if isolated and spec.isolation is None:
            spec = self._isolate(spec)
        try:
            handle = (adapter.start(spec) if resume_state is None
                      else adapter.resume(spec, resume_state))
        except base.SpawnFailed as err:
            # the deterministic state of an isolation-establishment failure: the
            # record, the registry line and the tombstone agree on the reason, so a
            # Core that restarts into it reads what this one knew (§3.7, O7)
            self.isolation.note_failure(spec, err)
            raise
        line = {'op': 'spawn', 'execution_id': spec.execution_id,
                'process_seq': spec.process_seq, 'pid': handle.pid,
                'create_time': handle.create_time, 'argv0': adapter.id,
                'started_at': time.time()}
        if spec.isolation is not None:
            line.update(spec.isolation.facts())
        self._registry(line)
        return handle

    def _isolate(self, spec):
        """The isolated launch for one execution's process, riding on the spec into
        `base.spawn` (§3.4: the new mechanism behind the existing seam). The plan is
        Core's, never the adapter's."""
        return __import__('dataclasses').replace(
            spec, isolation=self.isolation.request_for(spec))

    # ── isolation (§3.2 Cleanup, §3.7) ──

    def isolation_record(self, execution_id):
        """Core's isolation record of an execution, or None. The one thing a restarted
        Core reads to know an execution was isolated — never a file the execution
        could have written (§3.3)."""
        return self.isolation.record(execution_id)

    def fence_isolation(self, execution_id):
        """Quiescence before an import (K3): None, or why there is none. The
        execution's Job is closed either way."""
        return self.isolation.fence(execution_id)

    def end_isolation(self, execution_id, *, reason=''):
        """The execution is over: identity torn down, whatever will not go quarantined
        (§3.2 Cleanup). S1 applies no access, so nothing is revoked. Safe on an
        execution that was never isolated."""
        return self.isolation.teardown(execution_id, reason=reason)

    def reclaim_isolation(self, live_execution_ids=()):
        """Boot and every pass: quarantine retried, stale identities reclaimed (§3.7).
        Returns the executions it released."""
        return self.isolation.reclaim(live_execution_ids)

    @staticmethod
    def handle(execution):
        """The recorded identity of an execution's current process, or None."""
        if execution.pid is None:
            return None
        return base.ProcessHandle(execution.id, execution.pid, execution.create_time,
                                  ExecPaths(execution.id).dir)

    @staticmethod
    def alive(handle):
        """Is the recorded process still that process? Unknown create time: no."""
        return (handle is not None and handle.create_time is not None
                and proc.process_create_time(handle.pid) == handle.create_time)

    def kill(self, adapter, handle):
        """'killed' (a kill was issued), 'gone' (nothing of ours is running) —
        a pid now held by another process is never touched."""
        if handle is None or not self.alive(handle):
            return 'gone'
        try:
            adapter.stop(handle, grace_s=0.0)
        except base.StopRefused:
            return 'gone'           # the pid was recycled: ours has exited
        return 'killed'

    def ended(self, handle, exit_code, process_seq):
        """The exit was observed: the `ended` tombstone and the registry's end."""
        paths = ExecPaths(handle.execution_id)
        if not os.path.exists(paths.ended):
            base.mark_ended(paths, exit_code)
        self._registry({'op': 'end', 'execution_id': handle.execution_id,
                        'process_seq': process_seq, 'ended_at': time.time()})

    @staticmethod
    def files(execution_id):
        """(marker, pid.json, ended?) of the process I/O contract."""
        paths = ExecPaths(execution_id)
        return (base.read_json(paths.spawning), base.read_json(paths.pid),
                os.path.exists(paths.ended))

    # ── the registry (§15.2) ──

    def _registry(self, line):
        path = processes_registry()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(line, sort_keys=True) + '\n')

    @staticmethod
    def registry():
        """Every registry line, oldest first (unreadable lines skipped)."""
        try:
            with open(processes_registry(), encoding='utf-8') as f:
                raw = f.read().splitlines()
        except FileNotFoundError:
            return []
        out = []
        for line in raw:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    @classmethod
    def unended(cls):
        """The registry's spawn lines with no end line: what may still run."""
        lines = cls.registry()
        ended = {(x['execution_id'], x.get('process_seq')) for x in lines if x.get('op') == 'end'}
        return [x for x in lines if x.get('op') == 'spawn'
                and (x['execution_id'], x.get('process_seq')) not in ended]

    def compact_registry(self):
        """Keep only processes with no end line (boot, §15.2)."""
        text = ''.join(json.dumps(x, sort_keys=True) + '\n' for x in self.unended())
        os.makedirs(run_dir(), exist_ok=True)
        config.write_atomic(processes_registry(), text)

    # ── control flags and the e-stop sentinel (§10.2, §13) ──

    @staticmethod
    def set_flag(execution_id, flag):
        assert flag in FLAGS
        d = ExecPaths(execution_id).ctl
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, flag), 'w', encoding='utf-8') as f:
            f.write(str(time.time()))

    @staticmethod
    def clear_flags(execution_id):
        d = ExecPaths(execution_id).ctl
        for flag in FLAGS:
            try:
                os.remove(os.path.join(d, flag))
            except FileNotFoundError:
                pass

    @staticmethod
    def precompacted(execution_id):
        """The PreCompact backstop fired (the hook wrote it; p12-design-gate §13.1)."""
        return os.path.exists(os.path.join(ExecPaths(execution_id).req, 'precompact.json'))

    @staticmethod
    def disarmed():
        return os.path.exists(stop_sentinel())

    @staticmethod
    def engage_estop():
        """The sentinel first: every hook halts on it even if Core dies next."""
        os.makedirs(run_dir(), exist_ok=True)
        with open(stop_sentinel(), 'w', encoding='utf-8') as f:
            f.write(json.dumps({'at': time.time()}))

    @classmethod
    def estop_without_core(cls):
        """The e-stop with Core down or unreachable (execution-architecture §10
        path 2, p11-design-gate §13.4): the sentinel first, so every hook halts
        on it and a Core starting meanwhile comes up disarmed, then a kill of
        every registry process that has no end line and is still the process
        recorded (pid and create_time; a reused pid is never touched).
        Returns (killed, not_running) as lists of registry lines.

        Isolated processes are covered here too: with Core gone the Job's only holder
        is gone, so kill-on-close has already ended those trees (§3.7); this kill is
        the belt for what outlived it, and never the authority.
        """
        cls.engage_estop()
        killed, gone = [], []
        for x in cls.unended():
            (killed if proc.kill_pid_tree(x.get('pid'), x.get('create_time')) else gone).append(x)
        return killed, gone

    @staticmethod
    def clear_estop():
        try:
            os.remove(stop_sentinel())
        except FileNotFoundError:
            pass

    # ── the hook mailbox (§10.2) ──

    @staticmethod
    def pending_requests(execution_id):
        """[(seq, request)] with no answer yet, lowest seq first. An unreadable
        request is returned as None, so Core can answer it (fail closed). Only
        Core's own answer in class 2 answers a request: an answer the execution
        put beside its request is not one (PV-20 §7.5)."""
        paths = ExecPaths(execution_id)
        box = paths.req
        try:
            names = os.listdir(box)
        except FileNotFoundError:
            return []
        out = []
        for n in names:
            head, _, tail = n.partition('.')
            if tail != 'req.json' or not head.isdigit():
                continue
            if os.path.exists(os.path.join(paths.res, '%s.res.json' % head)):
                continue
            try:
                with open(os.path.join(box, n), encoding='utf-8') as f:
                    body = json.load(f)
            except (OSError, ValueError):
                body = None
            out.append((int(head), body if isinstance(body, dict) else None))
        return sorted(out, key=lambda x: x[0])

    @staticmethod
    def respond(execution_id, seq, decision, reason=''):
        box = ExecPaths(execution_id).res
        os.makedirs(box, exist_ok=True)
        config.write_json_atomic(os.path.join(box, '%d.res.json' % seq),
                                 {'decision': decision, 'reason': reason}, indent=None)

    # ── git reads the boundary checks need (outside any transaction) ──

    @staticmethod
    def git_branch(workdir):
        """HEAD's branch in *workdir*, or None (not a repository, detached)."""
        if not workdir:
            return None
        name = (proc.git(['rev-parse', '--abbrev-ref', 'HEAD'], workdir) or '').strip()
        return name if name and name != 'HEAD' else None

    @staticmethod
    def git_remotes(workdir):
        """{remote name: host} of *workdir*."""
        if not workdir:
            return {}
        from ..core.execution.canonical import host_of
        out = {}
        for line in (proc.git(['remote', '-v'], workdir) or '').splitlines():
            parts = line.split()
            if len(parts) >= 2:
                url = parts[1]
                host = host_of(url) if '://' in url else url.split('@')[-1].split(':')[0]
                out.setdefault(parts[0], host or None)
        return out

    # ── a user's terminal (p12-design-gate §14.4) ──

    @staticmethod
    def open_terminal(argv, *, cwd, env, title=''):
        """Open a user's session in a new terminal window: (process | None,
        error). Launched, never supervised — the user drives it (§14.3)."""
        return proc.spawn_terminal(argv, cwd=cwd, env=env, title=title)

    @staticmethod
    def diff_stat(workdir):
        """`git diff --stat HEAD` lines of *workdir*, for a checkpoint; [] when it is
        not a repository (p12-design-gate §8.2)."""
        if not workdir or not os.path.isdir(workdir):
            return []
        out = proc.git(['diff', '--stat', 'HEAD'], workdir) or ''
        return [line.strip() for line in out.splitlines() if line.strip()][:30]

    @staticmethod
    def end_state(workdir):
        """The digest of *workdir*'s state at an execution's end (ADR-0047 §5):
        HEAD, the tracked diff against it and every untracked file's content
        hash. None when it cannot be measured (not a repository, no commit, a
        failed read) — the guard reads that as no progress.

        Read-only: `--no-optional-locks` keeps git from refreshing the index,
        and `hash-object` without `-w` stores nothing (ADR-0046, MG-6)."""
        if not workdir or not os.path.isdir(workdir):
            return None

        def git(*args, stdin=None):
            r = proc.run(['git', '--no-optional-locks', *args], cwd=workdir, stdin=stdin)
            return None if r is None or r.returncode else r.stdout
        head = git('rev-parse', '--verify', 'HEAD')
        diff = git('diff', '--binary', 'HEAD')
        others = git('ls-files', '--others', '--exclude-standard', '-z')
        if head is None or diff is None or others is None:
            return None
        paths = sorted(p for p in others.split('\0') if p)
        hashes = git('hash-object', '--stdin-paths', stdin='\n'.join(paths) + '\n') \
            if paths else ''
        if hashes is None:
            return None
        h = hashlib.sha256()
        for part in (head.strip(), diff, '\0'.join(paths), hashes):
            h.update(part.encode('utf-8', 'surrogateescape'))
            h.update(b'\0')
        return h.hexdigest()

    # ── worktrees (§17) ──

    @staticmethod
    def add_worktree(root, path, branch, base='HEAD'):
        """`git worktree add -b <branch> <path> <base>` in *root* (P13 D12: a
        task forks from the mission branch once it exists). Returns the path,
        or raises OSError with git's reason."""
        if os.path.isdir(path):
            return path             # this execution's own, made before a restart
        os.makedirs(os.path.dirname(path), exist_ok=True)
        flag = '-b'
        if LocalNode.branch_exists(root, branch):
            # left by an add that failed after creating it, or kept after its
            # merge (P13 §12.1) while plan versions reuse task keys: moved to
            # *base* only when that loses nothing, else `-b` fails on it forever
            if not LocalNode.git_is_ancestor(root, branch, base):
                raise OSError('branch %s holds commits %s does not; it is left as it is'
                              % (branch, base))
            flag = '-B'
        r = proc.run(['git', 'worktree', 'add', flag, branch, '--', path, base], cwd=root,
                     timeout=60)
        if r is None or r.returncode != 0:
            raise OSError('git worktree add failed: %s' % ((r.stderr or r.stdout or '').strip()
                                                          if r is not None else 'no git'))
        return path

    @staticmethod
    def remove_worktree(root, path):
        """Remove a worktree this node created, only when git lists it."""
        listed = any(os.path.normcase(os.path.abspath(line[len('worktree '):])) ==
                     os.path.normcase(os.path.abspath(path))
                     for line in (proc.git(['worktree', 'list', '--porcelain'], root)
                                  or '').splitlines() if line.startswith('worktree '))
        if listed:
            proc.git(['worktree', 'remove', '--force', '--', path], root, timeout=60)
        return listed

    # ── verification and merge-back (P13, p13-design-gate §8, §12) ──

    @staticmethod
    def git_head(workdir):
        """The commit HEAD names in *workdir*, or None (not a repository)."""
        if not workdir or not os.path.isdir(workdir):
            return None
        out = (proc.git(['rev-parse', '--verify', '-q', 'HEAD'], workdir) or '').strip()
        return out or None

    @staticmethod
    def git_resolve(root, rev):
        out = (proc.git(['rev-parse', '--verify', '-q', rev + '^{commit}'], root) or '').strip()
        return out or None

    @staticmethod
    def git_dirty(workdir, *, tracked_only=False):
        """Uncommitted changes in *workdir* (untracked files too, unless
        *tracked_only*); None when git cannot tell."""
        args = ['status', '--porcelain=v1'] + (['--untracked-files=no'] if tracked_only else [])
        out = proc.git(args, workdir)
        return None if out is None else bool(out.strip())

    @staticmethod
    def git_snapshot(workdir, message):
        """Commit everything *workdir* holds uncommitted, as Archeus (§12.2).
        Returns the new HEAD, or raises OSError."""
        ident = ['-c', 'user.name=' + CORE_GIT_NAME, '-c', 'user.email=' + CORE_GIT_EMAIL,
                 '-c', 'commit.gpgsign=false']
        for args in (['add', '-A'], ident + ['commit', '-q', '--no-verify', '-m', message]):
            r = proc.run(['git'] + args, cwd=workdir, timeout=60)
            if r is None or r.returncode != 0:
                raise OSError('git %s failed: %s' % (args[-1] if args[0] == 'add' else 'commit',
                                                    (r.stderr or r.stdout or '').strip()
                                                    if r is not None else 'no git'))
        return LocalNode.git_head(workdir)

    @staticmethod
    def git_merge_base(root, a, b):
        out = (proc.git(['merge-base', a, b], root) or '').strip()
        return out or None

    @staticmethod
    def git_is_ancestor(root, a, b):
        r = proc.run(['git', 'merge-base', '--is-ancestor', a, b], cwd=root, timeout=15)
        return r is not None and r.returncode == 0

    @staticmethod
    def git_numstat(root, base, rev):
        """[(added, deleted, path)] of base..rev; None when git cannot tell."""
        out = proc.git(['diff', '--numstat', base, rev, '--'], root, timeout=60)
        if out is None:
            return None
        rows = []
        for line in out.splitlines():
            parts = line.split('\t', 2)
            if len(parts) == 3:
                rows.append((parts[0], parts[1], parts[2]))
        return rows

    @staticmethod
    def branch_exists(root, branch):
        return LocalNode.git_resolve(root, 'refs/heads/' + branch) is not None

    @staticmethod
    def mission_worktree(root, path, branch, base):
        """The mission branch's Core-owned worktree: *branch* at *path*, created
        from *base* the first time (§12.1). Returns the path or raises OSError."""
        if os.path.isdir(path):
            return path
        if LocalNode.branch_exists(root, branch):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            r = proc.run(['git', 'worktree', 'add', '--', path, branch], cwd=root, timeout=60)
            if r is None or r.returncode != 0:
                raise OSError('git worktree add failed: %s'
                              % ((r.stderr or r.stdout or '').strip() if r else 'no git'))
            return path
        return LocalNode.add_worktree(root, path, branch, base=base)

    @staticmethod
    def git_merge(workdir, rev, message):
        """Merge commit *rev* into the branch checked out in *workdir* as Archeus
        (§12.4): ('merged', head) or ('conflict', paths); a conflict is aborted
        and the branch left as it was. Raises OSError when git cannot run."""
        ident = ['-c', 'user.name=' + CORE_GIT_NAME, '-c', 'user.email=' + CORE_GIT_EMAIL,
                 '-c', 'commit.gpgsign=false']
        r = proc.run(['git'] + ident + ['merge', '--no-ff', '--no-edit', '-m', message, rev],
                     cwd=workdir, timeout=120)
        if r is None:
            raise OSError('git merge could not run')
        if r.returncode == 0:
            return 'merged', LocalNode.git_head(workdir)
        paths = (proc.git(['diff', '--name-only', '--diff-filter=U'], workdir) or '').split()
        proc.run(['git', 'merge', '--abort'], cwd=workdir, timeout=60)
        if not paths:
            raise OSError('git merge failed: %s' % (r.stderr or r.stdout or '').strip())
        return 'conflict', paths

    @staticmethod
    def run_check(workdir, argv, *, timeout, out_path, keep=CHECK_OUTPUT_KEEP):
        """Run one verification command in *workdir* (§8.3), its output streamed
        to *out_path*. Returns {exit_code, duration_ms, error, output (the last
        *keep* bytes), output_bytes, truncated}. `error` is set when it could not
        run or did not finish (a verifier fault, never the work's)."""
        import subprocess
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        # the project's own commands, not Core's: nothing of a pytest that may be
        # running Core (a test) leaks into them
        env = {k: v for k, v in os.environ.items() if not k.startswith('PYTEST_')}
        env.update(PYTHONDONTWRITEBYTECODE='1', GIT_TERMINAL_PROMPT='0')
        t0 = time.monotonic()
        with open(out_path, 'wb') as out:
            try:
                child = subprocess.Popen(argv, cwd=workdir, env=env, stdout=out,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                         creationflags=proc.no_window_flags,
                                         start_new_session=os.name != 'nt')
            except OSError as e:
                return {'exit_code': None, 'duration_ms': 0, 'error': 'could not run: %s' % e,
                        'output': b'', 'output_bytes': 0, 'truncated': False}
            error = None
            try:
                child.wait(timeout)
            except subprocess.TimeoutExpired:
                proc.kill_tree(child)
                child.wait(30)
                error = 'timed out after %ds' % timeout
        size = os.path.getsize(out_path)
        with open(out_path, 'rb') as f:
            f.seek(max(0, size - keep))
            tail = f.read()
        return {'exit_code': None if error else child.returncode,
                'duration_ms': int((time.monotonic() - t0) * 1000), 'error': error,
                'output': tail, 'output_bytes': size, 'truncated': size > keep}

    # ── PV-20 K1: the Core-owned store (keep-all: nothing here deletes) ──

    #: no production caller may fetch until the source side of a local fetch is
    #: accepted on evidence (T-046 C1); only a test sets this, on purpose, by name
    store_fetch_accepted = False

    @staticmethod
    def store_git(mode, args, *, workdirs, git_dir=None, stdin=None, timeout=120, sink=None):
        """The one spawner of a pinned Git call; stdout, or StoreError. *workdirs*
        are the execution workdirs Core recorded (its database; the node has none).
        With a *sink* (K2, C-1013-T049 §1) stdout is never decoded or held: it goes
        to `sink.feed` in fixed chunks as it arrives, *stdin* is bytes, and a sink
        that refuses, or *timeout*, kills the child."""
        if not args or args[0] not in _STORE_ARGS[mode]:
            raise StoreError('git %s is not a %s call' % (args[:1], mode))
        argv, env, cwd = _store_pin(mode, git_dir)
        _outside_executions([cwd] + ([git_dir] if git_dir else []), workdirs)
        if sink is not None:
            return _stream(argv + list(args), cwd, env, stdin, sink, timeout)
        r = proc.run(argv + list(args), cwd=cwd, env=env, timeout=timeout, stdin=stdin)
        if r is None or r.returncode:
            raise StoreError('git %s failed: %s' % (args[0], (r.stderr or r.stdout).strip()
                                                     if r is not None else 'could not run'))
        return r.stdout

    @staticmethod
    def store_open(project_id, *, workdirs):
        """The project's store, created and sealed the first time and checked
        against its pin record every time (T-046 C1 steps 1-6). Returns its path."""
        store = repo_store(project_id)
        _outside_executions([store], workdirs)
        pin = _pin_files(workdirs)
        version = _git_version(workdirs)
        owned = os.path.join(pin, project_id + '.owned')
        record = os.path.join(pin, project_id + '.json')
        if not _present(store):
            try:
                open(owned, 'xb').close()       # Core claims the store before it exists
            except FileExistsError:
                pass                            # a claim a crash left before its init
            LocalNode.store_git('init', ['init', '--bare', '-q', '--object-format=sha1',
                                         '--template=' + os.path.join(pin, 'empty'), store],
                                workdirs=workdirs)
        elif not _present(owned):
            raise StoreError('a store Core never claimed: %s' % store)
        _layout(store, owned)
        cfg = os.path.join(store, 'config')
        if not _present(record):
            if _present(os.path.join(store, 'packed-refs')) or any(
                    files for _d, _s, files in os.walk(os.path.join(store, 'refs'))):
                raise StoreError('an unsealed store holds refs: %s' % store)
            with open(cfg, 'rb') as f:
                if not _INIT_CONFIG.fullmatch(f.read().decode('utf-8', 'replace')):
                    raise StoreError('an unsealed store has config Core did not write: %s'
                                     % store)
            LocalNode.store_git('seal', ['symbolic-ref', 'HEAD', 'refs/archeus/none'],
                                workdirs=workdirs, git_dir=store)
            tree = LocalNode.store_git('seal', ['mktree'], workdirs=workdirs, git_dir=store,
                                       stdin='').strip()
            if tree != EMPTY_TREE:
                raise StoreError('the empty tree is %s, not %s' % (tree, EMPTY_TREE))
            if not config.write_json_atomic(record, _pin_record(store, version)):
                raise StoreError('could not record the pin of %s' % store)
        _plain(record, False)
        with open(record, encoding='utf-8') as f:
            if json.load(f) != _pin_record(store, version):
                raise StoreError('the store or its Git is not the one Core sealed: %s' % store)
        with open(os.path.join(store, 'HEAD'), 'rb') as f:
            head = f.read().decode('utf-8', 'replace')
        if head != STORE_HEAD or not os.path.isfile(
                os.path.join(store, 'objects', EMPTY_TREE[:2], EMPTY_TREE[2:])):
            raise StoreError('the store is not as Core sealed it: %s' % store)
        return store

    @staticmethod
    def store_read(project_id, args, *, workdirs):
        """Plumbing in a trusted store; a diff never runs an external driver or textconv."""
        args = list(args)
        if not args or args[0] not in STORE_READS:
            raise StoreError('git %s is not a store read' % args[:1])
        store = LocalNode.store_open(project_id, workdirs=workdirs)
        if args[0] == 'diff':
            args[1:1] = ['--no-ext-diff', '--no-textconv']
        return LocalNode.store_git('trusted', args, workdirs=workdirs, git_dir=store)

    @staticmethod
    def store_fetch(project_id, root, rev_name, expect, ref, *, workdirs):
        """*rev_name* of the repository at *root* into the store as *ref*, only if
        it still names *expect*, the commit Core resolved (T-046 §4.2); the
        incoming ref is kept. Unavailable until `store_fetch_accepted`."""
        if LocalNode.store_fetch_accepted is not True:
            raise StoreError('no fetch into a store until its source side is accepted '
                             '(T-046 C1)')
        if not ((_REF.fullmatch(rev_name) or rev_name == 'HEAD') and _REF.fullmatch(ref)
                and ref.startswith('refs/archeus/')
                and '..' not in rev_name + ref and re.fullmatch(r'[0-9a-f]{40}', expect)
                and os.path.isabs(root)):
            raise StoreError('not a fetch Core may make: %r' % ((root, rev_name, expect, ref),))
        _source(root, workdirs)
        store = LocalNode.store_open(project_id, workdirs=workdirs)
        incoming = 'refs/archeus/incoming/' + ref[len('refs/archeus/'):]
        LocalNode.store_git('trusted', ['fetch', '--no-tags', '--no-recurse-submodules',
                                        '--no-write-fetch-head', '--no-auto-gc', '--end-of-options',
                                        root, '+%s:%s' % (rev_name, incoming)],
                            workdirs=workdirs, git_dir=store)
        got = LocalNode.store_git('trusted', ['rev-parse', '--verify', '-q', incoming + '^{commit}'],
                                  workdirs=workdirs, git_dir=store).strip()
        if got != expect:
            raise StoreError('lost race: %s is now %s, not %s' % (rev_name, got, expect))
        return _publish_once(ref, expect, store, workdirs)

    @staticmethod
    def store_resolve_base(root, rev, *, workdirs):
        """The commit *rev* names in the project repository at *root*, read under
        the pin: global and system config, hooks and replace refs are not read;
        the repository's own local config still is. Reads only; no caller yet."""
        # a ref name or a full id only: no reflog, upstream or path syntax, so
        # nothing beyond refs and objects is read to resolve it
        # HEAD too (K2, T-049 §2: a first attempt's base when the mission branch
        # does not resolve), read through the HEAD file `_source` checks
        if not ((_REF.fullmatch(rev) and '..' not in rev) or rev == 'HEAD'
                or re.fullmatch(r'[0-9a-f]{40}', rev)):
            raise StoreError('not a revision Core resolves: %r' % (rev,))
        git_dir = _source(root, workdirs)
        _pin_files(workdirs)
        _git_version(workdirs)
        return LocalNode.store_git('base', ['rev-parse', '--verify', '-q', '--end-of-options',
                                            rev + '^{commit}'], workdirs=workdirs,
                                   git_dir=git_dir).strip()

    # ── K2: the seed (T-049, C-1013-T049) ──

    @staticmethod
    def resolve_base(root, mission_branch, *, workdirs):
        """A first attempt's base (T-049 §2): (the name a fetch takes, the commit):
        the mission branch if it resolves, else HEAD, each read once under the pin.
        Only the commit is ever recorded."""
        rev = 'refs/heads/' + mission_branch
        if not (_REF.fullmatch(rev) and '..' not in rev):
            raise StoreError('not a mission branch: %r' % (mission_branch,))
        try:
            return rev, LocalNode.store_resolve_base(root, rev, workdirs=workdirs)
        except StoreError:
            return 'HEAD', LocalNode.store_resolve_base(root, 'HEAD', workdirs=workdirs)

    @staticmethod
    def store_seed_ref(project_id, execution_id, commit, *, workdirs):
        """The execution's own seed ref pointed at *commit*, already in the store (a
        retry's base, T-049 §3): written once, never moved; refused if it names
        anything else."""
        ref = _seed_ref(execution_id)
        if not re.fullmatch(r'[0-9a-f]{40}', commit):
            raise StoreError('not a commit Core seeds from: %r' % (commit,))
        return _publish_once(ref, commit, LocalNode.store_open(project_id, workdirs=workdirs),
                             workdirs)

    @staticmethod
    def import_workspace(project_id, execution_id, seed_revision, *, workdirs):
        """The execution's workspace as one commit on its *seed_revision* in the store
        (K3, T-051 §3-§5 with C-1013-T051), once the fence has confirmed quiescence.
        Core's own Python walks it, never Git, following nothing; one `fast-import`
        writes `refs/archeus/exec/<id>/import`, which must not exist yet, from a stream
        Core generates; the commit's parent and its whole tree are read back and must
        be exactly what Core sent. Returns {revision, tree, files_changed, deleted,
        dropped_dirs}; any refusal is StoreError, and the workspace and the store keep
        whatever exists (keep-all)."""
        deadline = _Deadline(execution_id)

        def git(mode, args, **kw):
            return LocalNode.store_git(mode, args, workdirs=workdirs, git_dir=store,
                                       timeout=deadline.left(), **kw)
        if not re.fullmatch(r'[0-9a-f]{40}', seed_revision):
            raise StoreError('not a seed Core imports onto: %r' % (seed_revision,))
        work, ref = ExecPaths(execution_id).work, _import_ref(execution_id)
        store = LocalNode.store_open(project_id, workdirs=workdirs)
        try:
            git('trusted', ['rev-parse', '--verify', '-q', ref])
        except StoreError:
            pass                        # absent: the only state an import starts from
        else:
            raise StoreError('%s exists already: an import is written once' % ref)
        seed = _Manifest(len(work))     # the seed map: the only authority for a mode
        git('trusted', ['ls-tree', '-r', '-z', '-l', '--full-tree', seed_revision], sink=seed)
        plan, counts = _import_plan(work, seed, deadline)
        sent = {}
        git('import', ['fast-import', '--done', '--quiet'], sink=_Silent(),
            stdin=_import_stream(execution_id, seed_revision, plan, deadline, sent))
        rev = git('trusted', ['rev-parse', '--verify', '-q', ref + '^{commit}']).strip()
        head = git('trusted', ['cat-file', 'commit', rev]).split('\n\n', 1)[0].split('\n')
        parents = [x[7:] for x in head if x.startswith('parent ')]
        tree = [x[5:] for x in head if x.startswith('tree ')]
        back = _Manifest(len(work))
        git('trusted', ['ls-tree', '-r', '-z', '-l', '--full-tree', rev], sink=back)
        if parents != [seed_revision] or len(tree) != 1 or \
                {p: (m, o) for m, o, _s, p in back.entries} != sent:
            raise StoreError('%s is not what Core sent: kept, never recorded' % ref)
        was = {p: (m, o) for m, o, _s, p in seed.entries}
        changed = sorted(['A ' + p for p in sent if p not in was]
                         + ['M ' + p for p in sent if p in was and was[p] != sent[p]]
                         + ['D ' + p for p in was if p not in sent])
        return dict(counts, revision=rev, tree=tree[0], files_changed=changed[:500])

    @staticmethod
    def seed_workspace(project_id, execution_id, seed_revision, branch, *, workdirs):
        """The execution's repository, holding exactly the tree of *seed_revision*,
        its own seed ref in the store (T-049 §4 with C-1013-T049): built in Core's
        staging directory, checked there, renamed into the execution's workspace,
        which it returns. A refusal publishes nothing and keeps what exists; no Git
        runs once the workspace exists."""
        deadline = _Deadline(execution_id)

        def git(mode, args, git_dir, **kw):
            return LocalNode.store_git(mode, args, workdirs=workdirs, git_dir=git_dir,
                                       timeout=min(120, deadline.left()), **kw)
        head = 'refs/heads/' + branch
        if not (re.fullmatch(r'[0-9a-f]{40}', seed_revision) and _SEED_BRANCH.fullmatch(branch)
                and '..' not in branch and not branch.endswith(('.', '.lock'))):
            raise StoreError('not a seed Core builds: %r' % ((seed_revision, branch),))
        work, stage = ExecPaths(execution_id).work, seed_staging(execution_id)
        for p in (work, stage):     # fresh, never reused or adopted (rule c)
            if _present(p):
                raise StoreError('a seed target that already exists: %s' % p)
        store = LocalNode.store_open(project_id, workdirs=workdirs)
        ref = _seed_ref(execution_id)
        if git('trusted', ['rev-parse', '--verify', '-q', ref + '^{commit}'],
               store).strip() != seed_revision:
            raise StoreError('%s does not name %s' % (ref, seed_revision))
        # the manifest, every bound checked as it arrives and before a byte is written
        tree = _Manifest(max(len(work), len(stage)))
        git('trusted', ['ls-tree', '-r', '-z', '-l', '--full-tree', seed_revision], store,
            sink=tree)
        # the skeleton: Core's config, the seed commit shallow, the index from its tree
        _made(repos_dir(), os.path.dirname(stage), deadline)
        os.mkdir(stage)
        git('init', ['init', '-q', '--object-format=sha1', '--template=' + _pin_area()[2],
                     stage], None)
        dot = os.path.join(stage, '.git')
        _plain(dot, True)
        _plain(os.path.join(dot, 'config'), False)
        with open(os.path.join(dot, 'config'), 'wb') as f:
            f.write(SEED_CONFIG)
        git('seed', ['fetch', '--depth=1', '--no-tags', '--no-recurse-submodules',
                     '--no-write-fetch-head', '--no-auto-gc', '--end-of-options', store, ref],
            dot)
        git('seed', ['update-ref', head, seed_revision, ''], dot)
        git('seed', ['symbolic-ref', 'HEAD', head], dot)
        git('seed', ['read-tree', seed_revision], dot)
        # the files, written by Core as data: a link is its target text, a gitlink an
        # empty directory (owner Q1, A); every blob checked against its id
        for d in sorted(tree.dirs, key=lambda d: d.count('/')):
            deadline.left()
            os.mkdir(os.path.join(stage, *d.split('/')))
        blobs = [(oid, size, os.path.join(stage, *path.split('/')))
                 for mode, oid, size, path in tree.entries if mode != '160000']
        if blobs:
            git('trusted', ['cat-file', '--batch'], store, sink=_Blobs(blobs),
                stdin=b''.join(oid.encode('ascii') + b'\n' for oid, _s, _p in blobs))
        # two domains, both before the rename: the working tree, exactly the tree's
        # map; and the .git Core made, exactly what it wrote
        if _seed_walk(stage, deadline) != tree.expected():
            raise StoreError('the seed of %s differs from its tree' % execution_id)
        _seed_meta(dot, head, seed_revision, deadline)
        index = _Index()
        git('seed', ['ls-files', '-s', '-z'], dot, sink=index)
        if index.found != {(m, o, p) for m, o, _s, p in tree.entries} or git(
                'seed', ['rev-parse', 'HEAD^{tree}'], dot) != git(
                'trusted', ['rev-parse', seed_revision + '^{tree}'], store):
            raise StoreError('the seed index of %s is not its tree' % execution_id)
        _made(archeus_home(), os.path.dirname(work), deadline)
        if _present(work):
            raise StoreError('a seed target that already exists: %s' % work)
        deadline.left()                 # immediately before publication
        os.rename(stage, work)
        return work


def _publish_once(ref, commit, store, workdirs):
    """*ref* created at *commit*, never moved (T-049 §3): a ref that already names
    *commit* is the same publication; one naming anything else is refused."""
    try:
        LocalNode.store_git('trusted', ['update-ref', ref, commit, ''], workdirs=workdirs,
                            git_dir=store)
    except StoreError:
        pass                            # it exists: what it names decides below
    got = LocalNode.store_git('trusted', ['rev-parse', '--verify', '-q', ref + '^{commit}'],
                              workdirs=workdirs, git_dir=store).strip()
    if got != commit:
        raise StoreError('%s names %s, not %s' % (ref, got, commit))
    return commit


@functools.lru_cache(maxsize=None)
def _git_exe():
    # resolved once per process; on Windows `which` also searches the current
    # directory first, which yields a relative path: refused, never run
    exe = shutil.which('git')
    if not exe or not os.path.isabs(exe):
        raise StoreError('no absolute git on PATH: %r' % (exe,))
    return exe


#: `git version` of each absolute executable, read once per process
_VERSION = {}


def _git_version(workdirs):
    """The version, refused below the floor. It runs in the pin's empty
    directory, so the caller's recorded workdirs are checked against the pin
    area every time: by the spawner when it runs, here when it is cached."""
    exe = _git_exe()
    if exe in _VERSION:
        _outside_executions(_pin_area(), workdirs)
        return _VERSION[exe]
    out = LocalNode.store_git('version', ['version'], workdirs=workdirs).strip()
    m = re.match(r'git version (\d+)\.(\d+)\.(\d+)', out)
    if not m or tuple(int(x) for x in m.groups()) < STORE_GIT_FLOOR:
        raise StoreError('git %r is older than %s or unreadable'
                         % (out, '.'.join(map(str, STORE_GIT_FLOOR))))
    _VERSION[exe] = out
    return out


def _store_pin(mode, git_dir):
    """The one pin (T-046 C1): argv prefix, environment and cwd of a store call.
    Of the inherited environment only the platform's own variables survive."""
    _repos, _pin, empty, cfg = _pin_area()
    exe = _git_exe()
    env = {k: os.environ[k] for k in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP') if k in os.environ}
    env.update(PATH=os.path.dirname(exe), HOME=empty, XDG_CONFIG_HOME=empty,
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=cfg, GIT_CONFIG_SYSTEM=cfg,
               GIT_TERMINAL_PROMPT='0', GIT_ALLOW_PROTOCOL='file', GIT_PROTOCOL_FROM_USER='0',
               GIT_NO_LAZY_FETCH='1')
    argv = [exe]
    if git_dir is None:                 # version, init: no repository may be discovered
        env['GIT_CEILING_DIRECTORIES'] = repos_dir()
        cwd = empty if mode == 'version' else repos_dir()
    else:
        argv += ['--git-dir', git_dir, '--no-replace-objects']
        if mode == 'trusted':
            argv += ['--attr-source', EMPTY_TREE]
        if mode == 'seed':              # Core's staging writes no reflog (C-1013-T049)
            argv += ['-c', 'core.logAllRefUpdates=false']
        cwd = git_dir
    for c in ('core.hooksPath=' + empty, 'core.fsmonitor=false', 'core.attributesFile=' + cfg,
              'submodule.recurse=false', 'gc.auto=0', 'maintenance.auto=false'):
        argv += ['-c', c]
    return argv, env, cwd


def _pin_area():
    """`repos/`, `repos/.pin/` and the empty directory and file every pin points Git at."""
    pin = os.path.join(repos_dir(), '.pin')
    return repos_dir(), pin, os.path.join(pin, 'empty'), os.path.join(pin, 'empty.cfg')


def _pin_files(workdirs):
    """The pin area, made by Core and refused once anything is in it. Nothing is
    made until the area is checked against the caller's recorded workdirs, and
    each level is checked as it is before the next is made below it, then
    again once made, so no write lands through an alias."""
    repos, pin, empty, cfg = _pin_area()
    _outside_executions([repos, pin, empty, cfg], workdirs)
    home = archeus_home()
    if not _present(home):
        os.makedirs(home)                   # its ancestors are not Core's
    for d in (home, repos, pin, empty):
        if not _present(d):
            try:
                os.mkdir(d)
            except FileExistsError:
                pass
        _plain(d, True)
    if not _present(cfg):
        try:
            open(cfg, 'xb').close()
        except FileExistsError:
            pass
    if os.listdir(empty) or _plain(cfg, False).st_size:
        raise StoreError('a pin file is not empty: %s' % pin)
    return pin


def _outside_executions(paths_, workdirs):
    """No store call names a path at or under an execution's area: run/ (every
    class 1-7 directory), the task worktrees, or a workdir Core recorded
    (*workdirs*, read from its database by the caller), as written or once its
    links are resolved."""
    if isinstance(workdirs, (str, bytes)):
        raise StoreError('workdirs is a collection of paths, not one path')
    areas = {os.path.normcase(f(a)) for a in [run_dir(), os.path.join(archeus_home(), 'worktrees')]
             + [w for w in workdirs if w] for f in (os.path.abspath, os.path.realpath)}
    for p in paths_:
        for q in {os.path.normcase(f(p)) for f in (os.path.abspath, os.path.realpath)}:
            for a in areas:
                try:
                    inside = os.path.commonpath([q, a]) == a
                except ValueError:      # another drive
                    inside = False
                if inside:
                    raise StoreError('a store call at or inside an execution area: %s' % p)


def _source(root, workdirs):
    """A repository Core reads from, refused when anything Git reads it through
    lies in an execution area or is an alias: its root, its `.git`, the git
    directory that names, the common directory that one names (config, objects
    and refs come from there), the config files and refs Git reads, and every
    object store it borrows from. Each is checked before the file naming the
    next is read, and nothing is started until all are. Returns the git dir."""
    if not os.path.isabs(root):
        raise StoreError('not a repository Core may read: %r' % (root,))
    _outside_executions([root], workdirs)
    # upload-pack's enter_repo tries <root>/.git, <root>, <root>.git/.git, <root>.git
    # (path.c): a sibling it could settle on instead of what is checked here is refused
    if _present(root.rstrip('/\\') + '.git'):
        raise StoreError('a source with a sibling %s.git upload-pack could take: %s'
                         % (os.path.basename(root), root))
    git_dir = _git_dir_of(root)
    _outside_executions([git_dir], workdirs)
    _plain(git_dir, True)
    common = git_dir
    if _present(os.path.join(git_dir, 'commondir')):
        _plain(os.path.join(git_dir, 'commondir'), False)
        # gitrepository-layout: one path; a relative one is against the git dir
        (common,) = _named_dirs(os.path.join(git_dir, 'commondir'), git_dir, one=True)
        _outside_executions([common], workdirs)
        _plain(common, True)
    # git-config FILES: the repository's config, and config.worktree when
    # extensions.worktreeConfig names it (read here whenever it exists)
    for cfg in (os.path.join(common, 'config'), os.path.join(git_dir, 'config.worktree')):
        if _present(cfg):
            _plain(cfg, False)
            with open(cfg, 'rb') as f:
                # git-config: section names are case-insensitive and only
                # alphanumerics, '-' and '.', so every include or includeIf
                # header holds these bytes; a value that merely says the word
                # is refused too (fail closed: Core follows no include)
                data = f.read().lower()
            for word in _SOURCE_CONFIG_REFUSED:
                if word in data:
                    raise StoreError('a source config saying %r, which Core does not follow: %s'
                                     % (word.decode(), cfg))
    if _present(os.path.join(common, 'reftable')):
        raise StoreError('a reftable source (extensions.refStorage): %s' % common)
    # commit.c prepare_commit_graft reads info/grafts and the shallow file to parse a commit
    for d in {git_dir, common}:
        for rel in (('HEAD',), ('packed-refs',), ('shallow',), ('info',), ('info', 'grafts')):
            p = os.path.join(d, *rel)
            if _present(p):
                _plain(p, rel == ('info',))
    if _present(os.path.join(common, 'packed-refs')):
        with open(os.path.join(common, 'packed-refs'), 'rb') as f:
            if b'refs/replace/' in f.read():
                raise StoreError('a source with replace refs: %s' % common)
    if _present(os.path.join(common, 'refs', 'replace')):
        raise StoreError('a source with replace refs: %s' % common)
    for refs in {os.path.join(git_dir, 'refs'), os.path.join(common, 'refs')}:
        if _present(refs):
            _plain(refs, True)
            for d, dirs, files in os.walk(refs):
                for n in dirs + files:      # checked before os.walk descends into it
                    _plain(os.path.join(d, n), None)
    stores = [(os.path.join(common, 'objects'), 0)]
    while stores:
        objects, depth = stores.pop()
        _objects_plain(objects)
        alternates = os.path.join(objects, 'info', 'alternates')
        if not _present(alternates):
            continue
        if depth == 5:                  # Git itself follows no deeper
            raise StoreError('alternates nested too deep: %s' % alternates)
        _plain(alternates, False)
        # gitrepository-layout: one per line; a relative one is against the objects dir
        for alt in _named_dirs(alternates, objects):
            _outside_executions([alt], workdirs)
            stores.append((alt, depth + 1))
    return git_dir


def _objects_plain(objects):
    """An object store, its fan-out directories and everything below `info/`
    and `pack/` (commit-graph chain, multi-pack-index, bitmaps, reverse
    indexes) are no alias. Their files are not held to one link: `clone
    --local` hard-links objects, and an object is named by its own hash. A
    promisor pack (lazy fetch) or http-alternates is refused."""
    # ponytail: loose object files inside the fan-out directories are not lstat'ed
    # (O(objects) per read); the directories that hold them are
    _plain(objects, True)
    for n in os.listdir(objects):
        _entry(os.path.join(objects, n), None)
    for top in (os.path.join(objects, 'info'), os.path.join(objects, 'pack')):
        if _present(top):
            _plain(top, True)
            for d, dirs, files in os.walk(top):
                for n in dirs + files:          # checked before os.walk descends into it
                    _entry(os.path.join(d, n), None)
                    if n.endswith(_PROMISOR_PACK) or n == 'http-alternates':
                        raise StoreError('a source with %s: %s' % (n, d))


def _git_dir_of(root):
    """The git directory Git takes for *root*: `.git` itself when it is a
    directory, *root* when there is none, else what the `.git` file names, read
    as setup.c read_gitfile_gently reads it: the whole file, the exact
    "gitdir: " prefix, only trailing CR and LF trimmed, a relative path against
    *root*. What Core could not match exactly is refused: an alias, a file over
    _GITFILE_MAX, invalid UTF-8, an empty path, a NUL or line break left in it,
    leading or trailing blanks Git would keep, and on Windows a drive-relative
    or root-relative path."""
    dot = os.path.join(root, '.git')
    if not _present(dot):
        return root
    st = _plain(dot, None)
    if stat.S_ISDIR(st.st_mode):
        return dot
    with open(dot, 'rb') as f:
        data = f.read(_GITFILE_MAX + 1)
    if len(data) > _GITFILE_MAX or not data.startswith(b'gitdir: '):
        raise StoreError('a .git file Core does not read: %s' % dot)
    try:
        path = data[8:].rstrip(b'\r\n').decode('utf-8')
    except UnicodeDecodeError:
        raise StoreError('a .git file that is not UTF-8: %s' % dot)
    drive, rest = os.path.splitdrive(path)
    if (not path or any(c in path for c in '\0\r\n') or path != path.strip(' \t')
            or os.name == 'nt' and bool(drive) != rest.startswith(('/', '\\'))):
        raise StoreError('a .git file naming a path Core does not resolve: %s' % dot)
    return os.path.join(root, path)


def _named_dirs(path, base, one=False):
    """The directories a commondir (*one*) or alternates file names, relative
    ones against *base*; StoreError when Core cannot read them exactly as Git
    would: unreadable, empty, a second line in a commondir, a comment or quoted
    line, a carriage return, or anything that is not a directory."""
    try:
        with open(path, 'rb') as f:
            text = f.read().decode('utf-8')
    except (OSError, UnicodeDecodeError) as e:
        raise StoreError('cannot read %s: %s' % (path, e))
    names = [text.rstrip('\r\n')] if one else [x for x in text.split('\n') if x]
    dirs = [os.path.join(base, x) for x in names]
    if not names or any(not x or x[0] in '#"' or '\r' in x or '\n' in x for x in names) \
            or not all(os.path.isdir(d) for d in dirs):
        raise StoreError('an indirection Core cannot resolve to directories: %s' % path)
    return dirs


def _plain(path, is_dir):
    """Core's own entry: no link, junction or reparse point, and a file with no
    second hard link (a linked file is some other path's bytes)."""
    st = _entry(path, is_dir)
    if not stat.S_ISDIR(st.st_mode) and st.st_nlink > 1:
        raise StoreError('a hard-linked file: %s' % path)
    return st


def _layout(store, owned):
    """Before any read or Git write: the claim, the store and every metadata
    entry Git resolves in it are plain, so no seal, fetch or ref update writes
    through an alias."""
    _plain(owned, False)
    _plain(store, True)
    for rel in ('objects', 'refs'):
        _plain(os.path.join(store, rel), True)
    for rel in ('config', 'HEAD'):
        _plain(os.path.join(store, rel), False)
    # ponytail: loose object files are not lstat'ed one by one (keep-all makes
    # that O(objects) per open); their directories are
    for top in (store, os.path.join(store, 'objects')):
        for n in os.listdir(top):
            _plain(os.path.join(top, n), None)
    # everything below these, however deep (commit-graph chains, multi-pack
    # indexes, bitmaps, reverse indexes): few files, all Git's own
    for top in ('info', 'refs', os.path.join('objects', 'info'), os.path.join('objects', 'pack')):
        for d, dirs, files in os.walk(os.path.join(store, top)):
            for n in dirs + files:      # checked before os.walk descends into it
                _plain(os.path.join(d, n), None)
    hooks = os.path.join(store, 'hooks')
    if _present(hooks) and os.listdir(hooks):
        raise StoreError('a store with hooks: %s' % store)
    for rel in (('info', 'attributes'), ('objects', 'info', 'alternates'), ('commondir',),
                ('config.worktree',)):
        if _present(os.path.join(store, *rel)):
            raise StoreError('a store with %s: %s' % ('/'.join(rel), store))


def _pin_record(store, version):
    with open(os.path.join(store, 'config'), 'rb') as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    return {'git': _git_exe(), 'version': version, 'empty_tree': EMPTY_TREE,
            'config_sha256': digest}


# ── K2: the byte core and the seed's consumers (C-1013-T049) ──

def _stream(argv, cwd, env, stdin, sink, timeout):
    """The byte core of `store_git`: stdout straight into *sink* in fixed chunks,
    never decoded or kept; stderr drained and capped; *stdin* fed by a thread so
    neither pipe fills; *stdin* is bytes or an iterable of byte chunks, and an error
    raised while producing it is the call's failure. A sink that raises, or
    *timeout*, kills the child, and the
    call raises; a read that ends because of the kill is a refusal too. On any
    failure the sink is aborted (it closes what it opened), and every stream is
    closed either way; neither can replace the failure that got there first."""
    p = subprocess.Popen(argv, cwd=cwd, env=env, creationflags=proc.no_window_flags,
                         stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    late, err, fed = threading.Event(), bytearray(), []

    def expire():
        late.set()
        p.kill()

    def drain():
        for chunk in iter(lambda: p.stderr.read(_CHUNK), b''):
            err.extend(chunk[:max(0, _STDERR_KEEP - len(err))])

    def feed():
        chunks = iter((stdin,) if isinstance(stdin, bytes) else stdin)
        try:
            while True:
                try:
                    chunk = next(chunks)
                except StopIteration:
                    break
                except BaseException as e:      # producing the stream failed: that is
                    fed.append(e)               # the failure, and nothing is finished
                    p.kill()
                    break
                try:
                    p.stdin.write(chunk)
                except OSError:
                    break               # the child is gone: its end decides
        finally:
            _quietly(p.stdin.close)     # EOF for the child, on every path
    # everything after Popen runs under the cleanup below: a helper that fails to
    # start must not leave the child, its pipes or stdin without an owner
    timer, started = threading.Timer(timeout, expire), []
    try:
        timer.start()
        for target in (drain, feed) if stdin is not None else (drain,):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            started.append((target, t))
        for chunk in iter(lambda: p.stdout.read1(_CHUNK), b''):
            sink.feed(chunk)
        p.wait()
        for t in helpers:
            t.join()
        if fed:
            raise fed[0]
        if late.is_set():
            raise StoreError('git %s ran past its deadline' % argv[-1:])
        if p.returncode:
            raise StoreError('git failed: %s' % bytes(err).decode('utf-8', 'replace').strip())
        sink.end()
    except BaseException:
        p.kill()
        _quietly(sink.abort)
        raise
    finally:
        timer.cancel()
        p.wait()
        for _target, t in started:
            t.join()
        if stdin is not None and feed not in [x for x, _t in started]:
            _quietly(p.stdin.close)     # no feeder started to close it
        for pipe in (p.stdout, p.stderr):  # stdin: the feeder's finally
            _quietly(pipe.close)


def _quietly(close):
    """Cleanup that must not replace the failure it runs under."""
    try:
        close()
    except Exception:
        pass


class _Records:
    """NUL-ended records handed to `take` as they arrive, bounded while receiving:
    the first record past SEED_MAX_ENTRIES, a record past SEED_MAX_RECORD or a
    listing past both multiplied refuses before anything past it is kept."""

    def __init__(self):
        self.buf, self.n, self.total = b'', 0, 0

    def feed(self, chunk):
        self.total += len(chunk)
        if self.total > SEED_MAX_ENTRIES * SEED_MAX_RECORD:
            raise StoreError('a listing past %d bytes' % (SEED_MAX_ENTRIES * SEED_MAX_RECORD))
        *recs, self.buf = (self.buf + chunk).split(b'\0')
        for rec in recs:
            self.n += 1
            if self.n > SEED_MAX_ENTRIES or len(rec) > SEED_MAX_RECORD:
                raise StoreError('a listing past its bounds at record %d' % self.n)
            self.take(rec)
        if len(self.buf) > SEED_MAX_RECORD:
            raise StoreError('a listing record past %d bytes' % SEED_MAX_RECORD)

    def end(self):
        if self.buf:
            raise StoreError('a listing that ends inside a record')

    def abort(self):
        pass                            # it holds nothing open


class _Manifest(_Records):
    """`ls-tree -r -z -l --full-tree`: every entry's mode, type, id, size and path
    checked as it arrives, and the totals (bytes, case-folded collisions) kept
    as they grow. *prefix* is the longest directory a file will sit under."""

    def __init__(self, prefix):
        super().__init__()
        self.prefix, self.entries, self.dirs, self.size, self.folded = prefix, [], set(), 0, {}

    def take(self, rec):
        head, tab, raw = rec.partition(b'\t')
        try:
            mode, kind, oid, size = head.decode('ascii').split()
            path = raw.decode('utf-8')
        except ValueError:
            raise StoreError('a tree entry Core cannot read: %r' % rec[:120])
        gitlink = mode == '160000'
        if not (tab and _SEED_KINDS.get(mode) == kind and re.fullmatch(r'[0-9a-f]{40}', oid)
                and (size == '-' if gitlink else re.fullmatch(r'[0-9]{1,12}', size))):
            raise StoreError('a tree entry Core does not seed: %r' % rec[:120])
        _seed_path(path, self.prefix)
        self.size += 0 if gitlink else int(size)
        if self.size > SEED_MAX_BYTES:
            raise StoreError('a tree past %d bytes' % SEED_MAX_BYTES)
        parts = path.split('/')
        for i in range(1, len(parts) + 1):
            p = '/'.join(parts[:i])
            if self.folded.setdefault(p.casefold(), p) != p:
                raise StoreError('two paths one case-insensitive name: %r, %r'
                                 % (self.folded[p.casefold()], p))
        self.dirs.update('/'.join(parts[:i]) for i in range(1, len(parts)))
        if gitlink:
            self.dirs.add(path)
        self.entries.append((mode, oid, None if gitlink else int(size), path))

    def expected(self):
        out = {d: ('d',) for d in self.dirs}
        out.update((p, ('f', s, o)) for m, o, s, p in self.entries if m != '160000')
        return out


class _Index(_Records):
    """`ls-files -s -z`: the (mode, id, path) set of the index Git built."""

    def __init__(self):
        super().__init__()
        self.found = set()

    def take(self, rec):
        head, _tab, raw = rec.partition(b'\t')
        try:
            mode, oid, _stage = head.decode('ascii').split()
            self.found.add((mode, oid, raw.decode('utf-8')))
        except ValueError:
            raise StoreError('an index entry Core cannot read: %r' % rec[:120])


class _Blobs:
    """`cat-file --batch` answers, in the order asked: each header must name the
    id, type and size the manifest gave, its body is streamed into a file Core
    creates exclusively while Core hashes it, and the id it hashes to must be
    the one asked for. A missing, truncated, overlong or trailing object refuses."""

    def __init__(self, want):
        self.want, self.i, self.head, self.left, self.f, self.h = want, 0, b'', None, None, None

    def feed(self, chunk):
        while chunk:
            if self.left is None:                       # a header
                if self.i == len(self.want):
                    raise StoreError('bytes after the last object')
                nl = chunk.find(b'\n')
                self.head += chunk if nl < 0 else chunk[:nl]
                if len(self.head) > 100:
                    raise StoreError('an object header Core cannot read')
                if nl < 0:
                    return
                chunk = chunk[nl + 1:]
                self._open()
            elif self.left:                             # its body
                part, chunk = chunk[:self.left], chunk[self.left:]
                self.f.write(part)
                self.h.update(part)
                self.left -= len(part)
            else:                                       # the newline that ends it
                if chunk[:1] != b'\n':
                    raise StoreError('an object longer than its header')
                chunk = chunk[1:]
                self._close()

    def _open(self):
        oid, size, path = self.want[self.i]
        if self.head != b'%s blob %d' % (oid.encode('ascii'), size):
            raise StoreError('git gave %r for %s, a blob of %d' % (self.head[:100], oid, size))
        self.head, self.left = b'', size
        self.f, self.h = open(path, 'xb'), hashlib.sha1(b'blob %d\0' % size)

    def _close(self):
        self.f.close()
        if self.h.hexdigest() != self.want[self.i][0]:
            raise StoreError('a blob that is not %s' % self.want[self.i][0])
        self.i, self.left, self.f = self.i + 1, None, None

    def end(self):
        if self.i != len(self.want) or self.left is not None or self.head:
            raise StoreError('the objects ended early, at %d of %d' % (self.i, len(self.want)))

    def abort(self):
        """The file a failure left open is closed; what was written stays in staging."""
        f, self.f = self.f, None
        if f is not None:
            f.close()


def _seed_ref(execution_id):
    if not ids.is_id(execution_id, 'execution'):
        raise StoreError('not an execution id: %r' % (execution_id,))
    return 'refs/archeus/exec/%s/seed' % execution_id


def _seed_path(path, prefix):
    """T-049 §5: a path Core will write on Windows, or StoreError."""
    parts = path.split('/')
    if len(parts) > SEED_MAX_DEPTH or prefix + 1 + len(path) > SEED_MAX_PATH:
        raise StoreError('a path too deep or too long to seed: %r' % path)
    for c in parts:
        if (c in ('', '.', '..') or _UNSAFE.search(c) or c[-1] in '. '
                or _DEVICE.fullmatch(c.split('.')[0].rstrip(' '))
                or c.casefold() in ('.git', 'git~1')):
            raise StoreError('a path Core does not seed: %r' % path)


#: the clock every seed deadline reads (a test moves it, never the code)
_clock = time.monotonic


class _Deadline:
    """The one deadline of a whole seed (T-049 §5): read before every Git call, at
    every entry and hashed MiB of the checks, and immediately before publication."""

    def __init__(self, what):
        self.end, self.what = _clock() + SEED_DEADLINE, what

    def left(self):
        left = self.end - _clock()
        if left <= 0:
            raise StoreError('the seed of %s ran past its deadline' % self.what)
        return left


def _blob_id(path, size, deadline):
    h = hashlib.sha1(b'blob %d\0' % size)
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            deadline.left()
            h.update(chunk)
    return h.hexdigest()


def _seed_walk(top, deadline):
    """The working tree under *top*, its root `.git` excluded:
    {path: ('f', size, blob id) | ('d',)}, every entry plain and singly linked."""
    found = {}

    def walk(d, rel):
        for name in os.listdir(d):
            deadline.left()
            if not rel and name == '.git':
                continue
            p, r = os.path.join(d, name), rel + name
            st = _plain(p, None)
            if stat.S_ISDIR(st.st_mode):
                found[r] = ('d',)
                walk(p, r + '/')
            else:
                found[r] = ('f', st.st_size, _blob_id(p, st.st_size, deadline))
    walk(top, '')
    return found


def _seed_meta(dot, head, rev, deadline):
    """The seed's `.git`, exactly as Core made it: these names and no other, Core's
    bytes in HEAD, config and shallow, one ref naming the seed, no borrowed store,
    and no alias anywhere below it."""
    names = set(os.listdir(dot))
    if names != _SEED_META:
        raise StoreError('a seed .git holding %s' % sorted(names ^ _SEED_META))
    for name, want in (('HEAD', b'ref: %s\n' % head.encode('ascii')), ('config', SEED_CONFIG),
                       ('shallow', rev.encode('ascii') + b'\n'), ('index', None)):
        _plain(os.path.join(dot, name), False)
        if want is not None:
            with open(os.path.join(dot, name), 'rb') as f:
                if f.read() != want:
                    raise StoreError('a seed .git/%s Core did not write' % name)
    refs = {}
    for top in ('objects', 'refs'):
        _plain(os.path.join(dot, top), True)
        for d, dirs, files in os.walk(os.path.join(dot, top)):
            for n in dirs + files:          # checked before os.walk descends into it
                deadline.left()
                _plain(os.path.join(d, n), None)
            if top == 'refs':
                for n in files:
                    with open(os.path.join(d, n), 'rb') as f:
                        refs[os.path.relpath(os.path.join(d, n), dot).replace(os.sep, '/')] = f.read()
    if refs != {head: rev.encode('ascii') + b'\n'} or os.listdir(os.path.join(dot, 'objects',
                                                                               'info')):
        raise StoreError('a seed .git with refs or object stores Core did not make')


def _made(top, path, deadline):
    """*path* and every directory between *top* (Core's) and it: each made by Core
    when absent, and each plain."""
    d = top
    for part in os.path.relpath(path, top).split(os.sep):
        deadline.left()
        d = os.path.join(d, part)
        if not _present(d):
            try:
                os.mkdir(d)
            except FileExistsError:
                pass
        _plain(d, True)


# ── K3: the import (T-051 §3-§5, C-1013-T051) ──

class _Silent:
    """`fast-import --quiet` answers nothing on stdout; anything there refuses."""

    def feed(self, chunk):
        raise StoreError('fast-import wrote to stdout: %r' % chunk[:120])

    def end(self):
        pass

    def abort(self):
        pass


def _import_ref(execution_id):
    return _seed_ref(execution_id)[:-len('seed')] + 'import'


def _import_plan(work, seed, deadline):
    """The workspace as Core will send it: [(mode, path, id, source)], with
    {deleted, dropped_dirs}. Core's own walk, never Git and never with *work* as a
    cwd, the root `.git` (or `git~1`) skipped by name. Every entry is lstat-ed and a
    link, junction, other reparse point or second hard link refuses the import, as
    a nested `.git` does (owner Q1, A); so does a path the seed would refuse, a
    case-insensitive collision, or a bound. A path's mode comes only from the seed
    map: a seeded 120000 or 160000 is kept by id when unchanged and refuses the
    import when edited or replaced (C-1013-T051 §3); any other file is the seed's
    100644/100755, or 100644 when new. A regular file's source is its lstat
    identity, re-checked when it is opened; an empty directory is dropped, counted."""
    seeded = {p: (m, o) for m, o, _s, p in seed.entries}
    plan, folded, count = [], {}, {'entries': 0, 'bytes': 0, 'dropped_dirs': 0}
    _plain(work, True)

    def walk(d, rel):
        for name in sorted(os.listdir(d)):
            deadline.left()
            if not rel and name.casefold() in ('.git', 'git~1'):
                continue
            r, p = rel + name, os.path.join(d, name)
            try:
                r.encode('utf-8')
            except UnicodeEncodeError:
                raise StoreError('a path that is not UTF-8: %r' % r)
            _seed_path(r, len(work))
            if folded.setdefault(r.casefold(), r) != r:
                raise StoreError('two paths one case-insensitive name: %r, %r'
                                 % (folded[r.casefold()], r))
            count['entries'] += 1
            if count['entries'] > SEED_MAX_ENTRIES:
                raise StoreError('a workspace past %d entries' % SEED_MAX_ENTRIES)
            st = _plain(p, None)            # never followed: refused before any use
            mode, oid = seeded.get(r, (None, None))
            isdir = stat.S_ISDIR(st.st_mode)
            if mode == '160000':
                if not isdir or os.listdir(p):
                    raise StoreError('the seeded gitlink %s was changed' % r)
                plan.append(('160000', r, oid, None))
            elif mode == '120000':
                if isdir or _blob_id(p, st.st_size, deadline) != oid:
                    raise StoreError('the seeded link %s was changed' % r)
                plan.append(('120000', r, oid, None))
            elif isdir:
                before = len(plan)
                walk(p, r + '/')
                if len(plan) == before:
                    count['dropped_dirs'] += 1
            else:
                count['bytes'] += st.st_size
                if count['bytes'] > SEED_MAX_BYTES:
                    raise StoreError('a workspace past %d bytes' % SEED_MAX_BYTES)
                plan.append((mode or '100644', r, None,
                             (st.st_dev, st.st_ino, st.st_size, p)))
    walk(work, '')
    kept = {r for _m, r, _o, _s in plan}
    return plan, {'deleted': len(set(seeded) - kept), 'dropped_dirs': count['dropped_dirs']}


def _import_stream(execution_id, seed_revision, plan, deadline, sent):
    """The one fast-import stream: a commit on *seed_revision* whose tree is exactly
    *plan*, Core's identity and time, `done` last so a stream cut short commits
    nothing. Each file is opened, checked to be the entry the walk saw, and hashed
    by Core while sent; *sent* fills with {path: (mode, id)}."""
    msg = b'archeus: the workspace of %s\n' % execution_id.encode('ascii')
    yield (b'commit %s\ncommitter %s <%s> %d +0000\ndata %d\n%s\nfrom %s\ndeleteall\n'
           % (_import_ref(execution_id).encode('ascii'), CORE_GIT_NAME.encode('ascii'),
              CORE_GIT_EMAIL.encode('ascii'), int(time.time()), len(msg), msg,
              seed_revision.encode('ascii')))
    for mode, path, oid, source in plan:
        deadline.left()
        name = path.encode('utf-8')
        if source is None:                      # a seeded link or gitlink, by its id
            yield b'M %s %s %s\n' % (mode.encode('ascii'), oid.encode('ascii'), name)
            sent[path] = (mode, oid)
            continue
        dev, ino, size, p = source
        with open(p, 'rb') as f:
            st = os.fstat(f.fileno())
            if (st.st_dev, st.st_ino, st.st_size) != (dev, ino, size):
                raise StoreError('%s changed after the walk' % path)
            h = hashlib.sha1(b'blob %d\0' % size)
            yield b'M %s inline %s\ndata %d\n' % (mode.encode('ascii'), name, size)
            left = size
            while left:
                deadline.left()
                chunk = f.read(min(left, 1 << 20))
                if not chunk:
                    raise StoreError('%s shrank while it was read' % path)
                h.update(chunk)
                left -= len(chunk)
                yield chunk
            if f.read(1):
                raise StoreError('%s grew while it was read' % path)
        yield b'\n'
        sent[path] = (mode, h.hexdigest())
    yield b'done\n'
