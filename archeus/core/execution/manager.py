"""The execution manager (P11, p11-design-gate §5): every process of every
execution, from its first spawn to its end.

    tick()   one bounded pass over every live execution, never blocking:
             INTENT            -> prepare (binding, workspace, token), spawn
             STARTING/RUNNING  -> exit? output? hook requests? limit? control?
             PAUSING/STOPPING  -> the flag, the grace or the timeout, the kill
             PAUSED            -> resume once the mission is EXECUTING (§14)
             AWAITING_APPROVAL -> resume once the approval is APPROVED; end on
                                  REJECTED/EXPIRED
             + the runtime ceiling (§12.2) and the account clocks (§12.3, §12.4)
    boot()   adopt or reconcile every execution a previous Core left (§15.3)

Never inside a transaction: it reads, acts on the world through the node, and
records what happened through one writer command (application/executions.py).
Policy is P9's (`authorization`, through those commands); resources are P10's
(`ResourceRouter`, asked again only on resume). The manager itself decides
neither.
"""

import logging
import os
import re
import secrets
import sys
import time

from ...harnesses import base
from ...infra.db import rows
from ...infra.paths import ExecPaths
from ...node.local import LocalNode
from ..application import errors, executions as X, resources
from ..domain import entities, states
from . import canonical

log = logging.getLogger('archeus.execution')

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__)))), 'harnesses', 'hook.py')
_ENDED = states.terminal('execution')
#: stops that do not wait for a boundary
_NOW = ('estop', 'limit', 'disarmed', 'breaker')
PROGRESS_S = 1.0
#: how long a pause may wait for a tool boundary before it becomes a stop (§13)
PAUSE_TIMEOUT_S = 120.0
ACCOUNTS_S = 5.0
USAGE_S = 30.0
#: what a progress event may never carry (p11-design-gate §19)
_SECRET = re.compile(r'(hook_[A-Za-z0-9_\-]{8,}|dev_[A-Za-z0-9_\-]{8,}|node_[A-Za-z0-9_\-]{8,}'
                     r'|sk-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}'
                     r'|AKIA[0-9A-Z]{12,}|(?i:bearer)\s+[A-Za-z0-9._\-]{8,})')

#: the environment every execution runs in (execution-architecture §2): it can
#: commit locally, it cannot push with the user's credentials
CAPABILITY_ENV = {'GIT_TERMINAL_PROMPT': '0', 'GIT_ASKPASS': '', 'SSH_AUTH_SOCK': None,
                  'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'credential.helper',
                  'GIT_CONFIG_VALUE_0': ''}


def redact(text):
    return _SECRET.sub('[redacted]', text)


def line_of(ev):
    """One short, redacted line for a normalised event."""
    t = ev.get('type', '?')
    if t == 'tool':
        what = ev.get('input')
        what = what.get('command') or what.get('file_path') or what if isinstance(
            what, dict) else what
        s = 'tool %s: %s' % (ev.get('name'), what)
    elif t in ('assistant', 'stderr', 'result'):
        s = '%s: %s' % (t, ev.get('text') or ev.get('summary') or '')
    else:
        s = t
    return redact(str(s))[:200]


class ExecutionManager:
    def __init__(self, db, *, actor, registry, work, node=None, usage=None, scenarios=None,
                 grace_s=10.0, pause_timeout=None, start_timeout=60.0, lost_after=90.0):
        self.db, self.actor, self.registry, self.work = db, actor, registry, work
        self.policy, self.missions, self.router = work.policy, work.missions, work.router
        self.node = node or LocalNode()
        self.usage = usage
        self.scenarios = {} if scenarios is None else scenarios
        self.grace_s = grace_s
        self.pause_timeout = PAUSE_TIMEOUT_S if pause_timeout is None else pause_timeout
        self.start_timeout, self.lost_after = start_timeout, lost_after
        # execution id -> what this manager knows about its current process
        self._procs = {}
        self._clock = {'accounts': 0.0, 'usage': 0.0}
        self.booted = False

    def _do(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.actor))

    def _read(self):
        with self.db.read() as r:
            live = [x.entity for x in rows.where(r, entities.Execution)
                    if x.entity.state not in _ENDED]
            ms = {m.entity.id: m.entity for m in rows.where(r, entities.Mission)}
        return live, ms

    # ── the pass ──

    def tick(self):
        """One bounded pass; returns how many things it did."""
        did = 0
        disarmed = self.node.disarmed()
        live, missions = self._read()
        for e in live:
            try:
                did += bool(self._step(e, missions.get(e.mission_id), disarmed))
            except errors.LOST_RACE as err:
                log.info('execution %s: lost a race: %s', e.id, err)
            except errors.WriterClosed:
                raise
        now = time.monotonic()
        if now - self._clock['accounts'] >= ACCOUNTS_S:
            self._clock['accounts'] = now
            did += bool(self._do(X.accounts_tick)['moved'])
        if self.usage is not None and now - self._clock['usage'] >= USAGE_S:
            self._clock['usage'] = now
            did += self._ceilings(live)
        return did

    def _step(self, e, m, disarmed):
        s = e.state
        if s == 'INTENT':
            if e.process_seq == 0:
                return self._first(e, m, disarmed)
            return self._reconcile_one(e, disarmed)       # prepared, never recorded
        if s in ('STARTING', 'RUNNING', 'PAUSING', 'STOPPING'):
            if e.id not in self._procs:
                return self._reconcile_one(e, disarmed)
            return self._watch(e, m, disarmed)
        if s == 'PAUSED':
            return self._paused(e, m, disarmed)
        if s == 'AWAITING_APPROVAL':
            if e.id in self._procs:
                return self._watch(e, m, disarmed)        # the halt is still exiting
            return self._awaiting(e, m, disarmed)
        if s == 'LOST':
            return self._reconcile_one(e, disarmed)
        return False

    # ── starting a process ──

    def _first(self, e, m, disarmed):
        if disarmed:
            self._do(X.refuse, execution_id=e.id, reason='emergency stop: nothing starts',
                     stop_reason='disarmed')
            return True
        if m is None or m.state in ('CANCELLED', 'FAILED', 'COMPLETED'):
            self._do(X.refuse, execution_id=e.id, reason='the mission is %s'
                     % (m.state if m else 'gone'), stop_reason='cancel')
            return True
        if m.state != 'EXECUTING':
            return False                                  # paused or blocked: wait
        return self._spawn(e, m)

    def _spawn(self, e, m, resume_state=None):
        adapter = self.registry.get(e.harness_id)
        with self.db.read() as r:           # ADR-0021, immediately before the adapter runs
            permitted = resources.terms_permit(r, adapter)
            t = rows.get(r, entities.Task, e.task_id).entity
            account = rows.get(r, entities.Account, e.account_id) if e.account_id else None
        if not permitted:
            self._do(X.refuse, execution_id=e.id, reason='provider terms do not permit it',
                     stop_reason='binding')
            return True
        try:
            workdir, branch = self._workspace(e, m, t)
        except OSError as err:
            self._do(X.refuse, execution_id=e.id, reason='no workspace: %s' % err,
                     stop_reason='binding')
            return True
        token = 'hook_' + secrets.token_urlsafe(32)
        seq = e.process_seq + 1
        out = self._do(X.prepare_process, execution_id=e.id, token_digest=X.token_hash(token),
                       workdir=workdir, branch=branch, process_seq=seq)
        if out['refused']:
            return True
        if self.node.disarmed():
            self._do(X.refuse, execution_id=e.id, reason='emergency stop: nothing starts',
                     stop_reason='disarmed')
            return True
        home = account.entity.home_ref if account is not None else None
        spec = base.ExecutionSpec(
            execution_id=e.id, prompt='%s\n\n%s\n' % (m.objective, t.title), workdir=workdir,
            attempt=e.attempt, model=e.model, effort=e.effort, process_seq=seq,
            account=base.AccountRef(e.account_id or e.harness_id, home),
            env=dict(CAPABILITY_ENV, ARCHEUS_HOOK_TOKEN=token),
            hook_settings=(sys.executable, HOOK),
            task_contract={'key': t.key, 'kind': t.kind, 'estimate': t.estimate,
                           'action_classes': list(t.action_classes),
                           'fake_scenario': self.scenarios.get(t.key, _DEFAULT)})
        try:
            handle = self.node.spawn(adapter, spec, resume_state=resume_state)
        except (base.SpawnFailed, base.AlreadySpawned) as err:
            self._do(X.refuse, execution_id=e.id, reason='the process did not start: %s' % err,
                     stop_reason='binding')
            return True
        self._procs[e.id] = {'adapter': adapter, 'handle': handle, 'seq': seq,
                             'offset': self._offset(e), 'reported': 0.0, 'events': 0,
                             'lines': [], 'usage': None, 'since': None, 'flagged': False}
        self._do(X.record_process, execution_id=e.id, pid=handle.pid,
                 create_time=handle.create_time, process_seq=seq)
        if self.node.disarmed():            # the e-stop raced the spawn: it loses
            self._do(X.stop, execution_id=e.id, reason='emergency stop during the spawn',
                     stop_reason='disarmed')
        return True

    @staticmethod
    def _offset(e):
        try:
            return os.path.getsize(ExecPaths(e.id).stream)
        except OSError:
            return 0

    def _workspace(self, e, m, t):
        """(workdir, branch) — §17. Recorded before the process starts."""
        if m.project_id is None:
            d = ExecPaths(e.id).dir
            os.makedirs(d, exist_ok=True)
            return d, None
        with self.db.read() as r:
            p = rows.get(r, entities.Project, m.project_id)
        roots = list(p.entity.root_paths) if p is not None else []
        if not roots:
            raise OSError('project %s has no root' % m.project_id)
        root = roots[0]
        branch = self.node.git_branch(root)
        if t.workspace_mode == 'worktree' and branch is not None:
            # one segment under archeus/: P9's profiles bound commits to `archeus/*`,
            # where `*` never crosses a `/` (p11-design-gate §28)
            want = 'archeus/%s.%s' % (m.id, t.key)
            from ...infra.paths import archeus_home
            path = os.path.join(archeus_home(), 'worktrees', m.project_id, m.id, t.key)
            return self.node.add_worktree(root, path, want), want
        return root, branch

    # ── watching a live process ──

    def _watch(self, e, m, disarmed):
        p = self._procs[e.id]
        adapter, handle = p['adapter'], p['handle']
        did = self._tail(e, p)
        did |= self._hooks(e, p, disarmed)
        did |= self._control(e, m, p, disarmed)
        st = adapter.status(handle)
        if st.state != 'running':
            self._collect(e, p, st)
            return True
        return did

    def _tail(self, e, p):
        snap = p['adapter'].inspect(p['handle'], p['offset'])
        if not snap.events and snap.offset == p['offset']:
            return False
        p['offset'] = snap.offset
        for ev in snap.events:
            p['events'] += 1
            p['lines'].append(line_of(ev))
            if isinstance(ev.get('usage'), dict):
                p['usage'] = ev['usage']
            if ev.get('type') == 'limit' and e.account_id is not None and not p.get('limit'):
                p['limit'] = True
                self._do(X.account_limited, account_id=e.account_id,
                         resets_at=ev.get('resets_at'))
                self._stop_account(e.account_id, 'limit', 'the provider refused for a limit')
        if time.monotonic() - p['reported'] >= PROGRESS_S:
            self._progress(e, p)
        return True

    def _progress(self, e, p):
        if not p['events'] and p['offset'] == e.stream_offset:
            return
        self._do(X.record_progress, execution_id=e.id, offset=p['offset'], events=p['events'],
                 lines=p['lines'], usage=p['usage'])
        p['reported'], p['events'], p['lines'] = time.monotonic(), 0, []

    def _hooks(self, e, p, disarmed):
        did = False
        for seq, req in self.node.pending_requests(e.id):
            did = True
            if req is None:
                self.node.respond(e.id, seq, 'halt', 'the request could not be read')
                continue
            workdir = e.workdir or ExecPaths(e.id).dir
            cwd = req.get('cwd')
            cwd_ok = cwd is None or _inside(cwd, workdir)
            branch_now = self.node.git_branch(workdir) if e.branch else None
            ctx = {'workdir': workdir, 'branch': branch_now,
                   'remotes': self.node.git_remotes(workdir) if e.branch else {}}
            try:
                canon = canonical.canonicalise(req.get('tool'), req.get('input'), ctx)
                out = self._do(X.serve_hook, policy=self.policy, execution_id=e.id, seq=seq,
                               request=req, canon=canon, cwd_ok=cwd_ok,
                               branch_ok=e.branch is None or branch_now == e.branch,
                               disarmed=disarmed)
            except Exception as err:        # never allow on a failure: fail closed
                log.warning('hook request %d of %s: %s', seq, e.id, err)
                out = {'decision': 'halt', 'reason': 'Archeus could not judge the request'}
            self.node.respond(e.id, seq, out['decision'], out['reason'])
        return did

    def _control(self, e, m, p, disarmed):
        state = e.state
        if disarmed and state in ('STARTING', 'RUNNING', 'PAUSING'):
            self._do(X.stop, execution_id=e.id, reason='emergency stop', stop_reason='estop')
            state, e = 'STOPPING', self._reload(e)
        elif state in ('STARTING', 'RUNNING', 'PAUSING') and (m is None or m.state in (
                'CANCELLED', 'FAILED', 'COMPLETED')):
            self._do(X.stop, execution_id=e.id, reason='the mission ended', stop_reason='cancel')
            state, e = 'STOPPING', self._reload(e)
        elif state == 'RUNNING' and m is not None and m.state == 'PAUSED':
            self._do(X.pause_work, mission_id=m.id)
            state, e = 'PAUSING', self._reload(e)
        if state not in ('PAUSING', 'STOPPING'):
            p['since'], p['flagged'] = None, False
            return False
        if p['since'] is None:
            p['since'] = time.monotonic()
        if not p['flagged']:
            self.node.set_flag(e.id, 'PAUSE' if state == 'PAUSING' else 'STOP')
            p['flagged'] = True
        waited = time.monotonic() - p['since']
        if state == 'PAUSING' and waited >= self.pause_timeout:
            self._do(X.pause_timed_out, execution_id=e.id)
            p['since'], p['flagged'] = time.monotonic(), False
            return True
        if state == 'STOPPING' and (disarmed or e.stop_reason in _NOW
                                    or waited >= self.grace_s):
            self.node.kill(p['adapter'], p['handle'])
        return True

    def _reload(self, e):
        with self.db.read() as r:
            return rows.get(r, entities.Execution, e.id).entity

    def _collect(self, e, p, st):
        adapter, handle = p['adapter'], p['handle']
        self._tail(e, p)
        result = adapter.collect_result(handle)
        self.node.ended(handle, st.exit_code, p['seq'])
        self._progress(e, p)
        e = self._reload(e)
        self._procs.pop(e.id, None)
        if e.state in _ENDED:
            return
        self._do(X.record_end, execution_id=e.id, exit_code=st.exit_code,
                 killed=result.exit_reason == 'killed', halted=result.halted,
                 failure=result.failure, usage=dict(result.usage or {}) or p['usage'],
                 summary=result.reported_summary, adapter_state=result.adapter_state,
                 final_offset=p['offset'], output=p['offset'] > 0)

    # ── halted executions ──

    def _paused(self, e, m, disarmed):
        if disarmed or m is None or m.state in ('CANCELLED', 'FAILED', 'COMPLETED'):
            self._do(X.refuse, execution_id=e.id, reason='paused work cannot resume: %s'
                     % ('emergency stop' if disarmed else 'the mission ended'),
                     stop_reason='disarmed' if disarmed else 'cancel')
            return True
        if m.state != 'EXECUTING':
            return False
        return self._resume(e, m)

    def _awaiting(self, e, m, disarmed):
        if disarmed or m is None or m.state in ('CANCELLED', 'FAILED', 'COMPLETED'):
            self._do(X.refuse, execution_id=e.id, reason='the approval wait ended: %s'
                     % ('emergency stop' if disarmed else 'the mission ended'),
                     stop_reason='disarmed' if disarmed else 'cancel')
            return True
        with self.db.read() as r:
            a = X.waiting_approval(r, e)
        if a is None or a.state in ('REJECTED', 'EXPIRED', 'SUPERSEDED'):
            self._do(X.approval_answered, execution_id=e.id)
            return True
        if a.state not in ('APPROVED', 'CONSUMED') or m.state != 'EXECUTING':
            return False
        return self._resume(e, m)

    def _resume(self, e, m):
        adapter = self.registry.get(e.harness_id)
        caps = adapter.capabilities(None) if adapter.discover().installed else None
        if caps is None or 'resume' not in caps.capabilities:
            self._do(X.refuse, execution_id=e.id, reason='%s cannot resume a halted process'
                     % e.harness_id, stop_reason='binding')
            return True
        out = self._do(X.resume_checked, policy=self.policy, missions=self.missions,
                       router=self.router, execution_id=e.id, now=time.time())
        if out['refused']:
            return True
        return self._spawn(self._reload(e), m, resume_state=dict(e.adapter_state or {}))

    # ── stops beyond one execution ──

    def _stop_account(self, account_id, reason, why):
        live, _m = self._read()
        for x in live:
            if x.account_id == account_id and x.state in ('STARTING', 'RUNNING', 'PAUSING',
                                                          'INTENT', 'PAUSED',
                                                          'AWAITING_APPROVAL'):
                try:
                    self._do(X.stop, execution_id=x.id, reason=why, stop_reason=reason)
                except errors.LOST_RACE:
                    pass

    def _ceilings(self, live):
        """§12.2: every account with a live execution, against `allocation_pct`."""
        accounts = sorted({x.account_id for x in live if x.account_id is not None
                           and x.state in ('STARTING', 'RUNNING', 'PAUSING')})
        did = 0
        for aid in accounts:
            with self.db.read() as r:
                a = rows.get(r, entities.Account, aid).entity
                (pol,) = rows.where(r, entities.ResourcePolicy, account_id=aid)
            got = self.usage.read({'id': a.id, 'harness_id': a.harness_id,
                                   'home_ref': a.home_ref})
            if not got:
                continue
            self._do(resources.observe, readings={aid: got})
            worst = max(got['windows'].values()) if got.get('windows') else None
            if worst is not None and worst >= pol.entity.allocation_pct:
                self._stop_account(aid, 'ceiling', 'usage %g%% reached the %g%% allocation'
                                   % (worst, pol.entity.allocation_pct))
                did += 1
        return did

    # ── boot: adopt or reconcile (§15.3) ──

    def boot(self):
        """Every non-terminal execution a previous Core left: adopted when its
        process is alive by identity, else reconciled. One that fails does not
        stop the others; the first failure is raised after the sweep."""
        disarmed = self.node.disarmed()
        live, _m = self._read()
        failed = None
        done = []
        for e in live:
            if e.id in self._procs:
                continue
            try:
                self._reconcile_one(e, disarmed)
                done.append(e.id)
            except Exception as err:
                failed = failed or err
        self.node.compact_registry()
        self.booted = True
        if failed is not None:
            raise failed
        return done

    def _reconcile_one(self, e, disarmed):
        marker, pid, ended = self.node.files(e.id)
        seq = (pid or {}).get('process_seq', 1) if pid else None
        handle = None
        if pid is not None and (seq == e.process_seq or e.state == 'INTENT'):
            handle = base.ProcessHandle(e.id, pid['pid'], pid['create_time'], ExecPaths(e.id).dir)
        adapter = self.registry.get(e.harness_id)
        alive = handle is not None and self.node.alive(handle)
        if alive and disarmed:
            self.node.kill(adapter, handle)
            alive = False
        if e.state == 'INTENT':
            if marker is None or (ended and pid is None):
                self._do(X.refuse, execution_id=e.id, reason='no process was started',
                         stop_reason='disarmed' if disarmed else 'binding')
                return True
            if pid is None:
                self._tombstone(e)
                self._do(X.lost, execution_id=e.id,
                         reason='a spawn was begun and never confirmed')
                return True
            if alive:
                self._do(X.record_process, execution_id=e.id, pid=handle.pid,
                         create_time=handle.create_time, process_seq=e.process_seq or 1)
                self._adopt(self._reload(e), adapter, handle)
                return True
            return self._collect_gone(e, adapter, handle)
        if e.state in ('PAUSED', 'AWAITING_APPROVAL'):
            if marker is not None and marker.get('process_seq', 1) == e.process_seq \
                    and not ended and alive and e.pid is None:
                # a resume was spawned and never recorded
                self._do(X.record_process, execution_id=e.id, pid=handle.pid,
                         create_time=handle.create_time, process_seq=e.process_seq)
                self._adopt(self._reload(e), adapter, handle)
                return True
            return False                    # no process: the pass decides
        if alive:
            self._adopt(e, adapter, handle)
            return True
        if handle is None:
            self._tombstone(e)
            self._do(X.lost, execution_id=e.id, reason='Core restarted; no process was recorded')
            return True
        return self._collect_gone(e, adapter, handle)

    def _tombstone(self, e):
        """A process that may have existed and is not ours to watch: its
        `ended` tombstone (reconciled) and the registry's end, so nothing reads
        it as possibly alive again."""
        paths = ExecPaths(e.id)
        if os.path.exists(paths.spawning) and not os.path.exists(paths.ended):
            base.mark_ended(paths, None, reconciled=True)
            self.node._registry({'op': 'end', 'execution_id': e.id,
                                 'process_seq': e.process_seq, 'ended_at': time.time()})

    def _adopt(self, e, adapter, handle):
        self._procs[e.id] = {'adapter': adapter, 'handle': handle, 'seq': e.process_seq,
                             'offset': e.stream_offset, 'reported': 0.0, 'events': 0,
                             'lines': [], 'usage': e.usage, 'since': None, 'flagged': False}
        self._do(X.adopted, execution_id=e.id, pid=handle.pid, offset=e.stream_offset)

    def _collect_gone(self, e, adapter, handle):
        """The process is gone: collect what it left, as if observed (§15.3). An
        exit nobody can read is LOST, never success."""
        st = adapter.status(handle)
        p = {'adapter': adapter, 'handle': handle, 'seq': e.process_seq,
             'offset': e.stream_offset, 'reported': 0.0, 'events': 0, 'lines': [],
             'usage': e.usage}
        if st.state != 'exited' or st.exit_code is None:
            if e.state == 'STOPPING':
                self._collect(e, p, base.ProcStatus('exited', None))
                return True
            if e.state == 'PAUSING':
                self._collect(e, p, base.ProcStatus('exited', None))
                return True
            self._tombstone(e)
            self._do(X.lost, execution_id=e.id,
                     reason='Core restarted; the process is gone and left no exit')
            return True
        self._collect(e, p, st)
        return True


def _inside(path, root):
    try:
        a, b = os.path.realpath(path), os.path.realpath(root)
        return os.path.commonpath([os.path.normcase(a), os.path.normcase(b)]) == \
            os.path.normcase(b)
    except ValueError:
        return False


#: what the fake agent does for a task no scenario is scripted for
_DEFAULT = [{'emit': {'type': 'result', 'summary': 'done'}}]
