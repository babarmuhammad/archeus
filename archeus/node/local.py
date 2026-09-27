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

import json
import os
import time

from claude_sessions import config, proc

from ..harnesses import base
from ..infra.paths import ExecPaths, processes_registry, run_dir, stop_sentinel

#: control flags the hook reads (P11 PAUSE/STOP; P12 HANDOFF, p12-design-gate §10.1)
FLAGS = ('PAUSE', 'STOP', 'HANDOFF')
#: Core's own git identity for the snapshot commit and merges (P13 §12), set per
#: command so the user's configuration is never read or changed
CORE_GIT_NAME, CORE_GIT_EMAIL = 'Archeus', 'archeus@localhost'
#: the tail of a check's output kept as evidence (p13-design-gate §8.2)
CHECK_OUTPUT_KEEP = 256 * 1024


class LocalNode:
    id = None       # the local node (ADR-0008): no ExecutionNode row in V1

    # ── processes ──

    def spawn(self, adapter, spec, *, resume_state=None):
        """Start one process of an execution (its first, or a resume) and record
        it in the registry. Raises base.SpawnFailed / base.AlreadySpawned."""
        self.clear_flags(spec.execution_id)
        handle = (adapter.start(spec) if resume_state is None
                  else adapter.resume(spec, resume_state))
        self._registry({'op': 'spawn', 'execution_id': spec.execution_id,
                        'process_seq': spec.process_seq, 'pid': handle.pid,
                        'create_time': handle.create_time, 'argv0': adapter.id,
                        'started_at': time.time()})
        return handle

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

    def compact_registry(self):
        """Keep only processes with no end line (boot, §15.2)."""
        lines = self.registry()
        ended = {(x['execution_id'], x.get('process_seq')) for x in lines if x.get('op') == 'end'}
        live = [x for x in lines if x.get('op') == 'spawn'
                and (x['execution_id'], x.get('process_seq')) not in ended]
        text = ''.join(json.dumps(x, sort_keys=True) + '\n' for x in live)
        os.makedirs(run_dir(), exist_ok=True)
        config.write_atomic(processes_registry(), text)

    # ── control flags and the e-stop sentinel (§10.2, §13) ──

    @staticmethod
    def set_flag(execution_id, flag):
        assert flag in FLAGS
        paths = ExecPaths(execution_id)
        os.makedirs(paths.dir, exist_ok=True)
        with open(os.path.join(paths.dir, flag), 'w', encoding='utf-8') as f:
            f.write(str(time.time()))

    @staticmethod
    def clear_flags(execution_id):
        d = ExecPaths(execution_id).dir
        for flag in FLAGS:
            try:
                os.remove(os.path.join(d, flag))
            except FileNotFoundError:
                pass

    @staticmethod
    def precompacted(execution_id):
        """The PreCompact backstop fired (the hook wrote it; p12-design-gate §13.1)."""
        return os.path.exists(os.path.join(ExecPaths(execution_id).dir, 'precompact.json'))

    @staticmethod
    def disarmed():
        return os.path.exists(stop_sentinel())

    @staticmethod
    def engage_estop():
        """The sentinel first: every hook halts on it even if Core dies next."""
        os.makedirs(run_dir(), exist_ok=True)
        with open(stop_sentinel(), 'w', encoding='utf-8') as f:
            f.write(json.dumps({'at': time.time()}))

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
        request is returned as None, so Core can answer it (fail closed)."""
        box = os.path.join(ExecPaths(execution_id).dir, 'hook')
        try:
            names = os.listdir(box)
        except FileNotFoundError:
            return []
        out = []
        for n in names:
            head, _, tail = n.partition('.')
            if tail != 'req.json' or not head.isdigit():
                continue
            if os.path.exists(os.path.join(box, '%s.res.json' % head)):
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
        box = os.path.join(ExecPaths(execution_id).dir, 'hook')
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

    # ── worktrees (§17) ──

    @staticmethod
    def add_worktree(root, path, branch, base='HEAD'):
        """`git worktree add -b <branch> <path> <base>` in *root* (P13 D12: a
        task forks from the mission branch once it exists). Returns the path,
        or raises OSError with git's reason."""
        if os.path.isdir(path):
            return path             # this execution's own, made before a restart
        os.makedirs(os.path.dirname(path), exist_ok=True)
        r = proc.run(['git', 'worktree', 'add', '-b', branch, '--', path, base], cwd=root,
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
