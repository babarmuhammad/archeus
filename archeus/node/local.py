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

FLAGS = ('PAUSE', 'STOP')


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

    # ── worktrees (§17) ──

    @staticmethod
    def add_worktree(root, path, branch):
        """`git worktree add -b <branch> <path>` from HEAD of *root*. Returns the
        path, or raises OSError with git's reason."""
        if os.path.isdir(path):
            return path             # this execution's own, made before a restart
        os.makedirs(os.path.dirname(path), exist_ok=True)
        r = proc.run(['git', 'worktree', 'add', '-b', branch, '--', path, 'HEAD'], cwd=root,
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
