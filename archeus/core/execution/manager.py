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

import json
import logging
import os
import secrets
import sys
import time
from dataclasses import replace

from ...harnesses import base
from ...infra.artifacts import store
from ...infra.db import rows
from ...infra.paths import ExecPaths, task_worktree
from ...node import staging
from ...node.local import LocalNode, PathTooLong
from ..application import errors, executions as X, optins, resources
from ..domain import entities, states
from ..redact import redact  # p11-design-gate §19; shared since P12, and P20's inventory
from . import canonical, pressure as P

log = logging.getLogger('archeus.execution')

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__)))), 'harnesses', 'hook.py')
_ENDED = states.terminal('execution')


def mission_branch(mission_id):
    """The mission branch a task's verified result is merged into (P13 §12.1);
    a task branch is `archeus/<mission-id>.<task-key>` beside it."""
    return 'archeus/%s' % mission_id
#: stops that do not wait for a boundary
_NOW = ('estop', 'limit', 'disarmed', 'breaker')
PROGRESS_S = 1.0
#: context pressure that hands an execution off (execution-architecture §6), and
#: what the PreCompact backstop counts as (p12-design-gate §13.1; ADR-0047 §3)
PRESSURE_HANDOFF, PRESSURE_PRECOMPACT = P.PRESSURE_HANDOFF, P.PRESSURE_PRECOMPACT
#: how long a pause may wait for a tool boundary before it becomes a stop (§13)
PAUSE_TIMEOUT_S = 120.0
ACCOUNTS_S = 5.0
USAGE_S = 30.0
#: how often the pass re-checks that no ended execution still holds an isolation
#: identity or a grant (PV-20 §3.2 Cleanup, §3.7)
ISOLATION_SWEEP_S = 5.0
#: defined beside the spawn that checks an isolated environment against it
CAPABILITY_ENV = base.CAPABILITY_ENV
#: a known-isolated execution's diff: Core runs no Git in its workdir (T-044)
UNMEASURED = '(not measured: an isolated execution; Core runs no Git in its workdir)'


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
        self._clock = {'accounts': 0.0, 'usage': 0.0, 'isolation': 0.0}
        self._isolation_fault = None        # the last sweep fault logged, so it logs once
        self._noted = set()                 # (execution id, op) registry notes already left
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
        if now - self._clock['isolation'] >= ISOLATION_SWEEP_S:
            # not counted as work done: it is the safety net under the end paths, so
            # an idle pass stays an idle pass
            self._clock['isolation'] = now
            self._sweep_isolation(live)
        return did

    def _step(self, e, m, disarmed):
        s = e.state
        if s == 'INTENT':
            if e.process_seq == 0:
                return self._first(e, m, disarmed)
            return self._reconcile_one(e, disarmed)       # prepared, never recorded
        if s in ('STARTING', 'RUNNING', 'PAUSING', 'STOPPING', 'HANDING_OFF'):
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
            rd = (rows.get(r, entities.RouteDecision, e.route_decision_id)
                  if account is None and e.route_decision_id else None)
        if not permitted:
            self._do(X.refuse, execution_id=e.id, reason='provider terms do not permit it',
                     stop_reason='binding')
            return True
        if e.isolated is True and self._isolation_record(e.id) is None:
            # T-037 rule 4: without its record a resume would be decided afresh and, if
            # its profile is gone, run under a new identity (R7). Refused before the
            # decision, the workspace and the inventory, never re-established.
            self._do(X.refuse, execution_id=e.id, stop_reason='binding',
                     reason='its isolation record is gone: an isolated execution resumes '
                            'only under the identity it was prepared with')
            return True
        # whether this process runs isolated is the node's isolation authority's
        # decision (§3.4), never the adapter's and never a setting: production dispatch
        # of isolated executions is E's, so today nothing is dispatched that way. Taken
        # once, before anything is chosen or recorded, and this one value is what the
        # node gets; a decision that cannot be taken starts nothing, never unisolated.
        try:
            iso = getattr(self.node, 'isolation', None)
            isolated = bool(iso is not None and iso.requested(e.id, adapter))
        except Exception as err:
            self._do(X.refuse, execution_id=e.id, stop_reason='binding',
                     reason='the isolation decision could not be taken: %s'
                     % type(err).__name__)
            return True
        hook = (sys.executable, HOOK)
        if isolated:
            # C4b (T-034): the isolated hook runs from Core's verified copy of the real
            # install (base_prefix, never a venv launcher's directory), verified again on
            # every process, a resume's included. No copy, no start: never Core's own
            try:
                stage = staging.stage(sys.base_prefix, HOOK)
            except OSError as err:
                self._do(X.refuse, execution_id=e.id, stop_reason='binding',
                         reason='the hook runtime could not be staged: %s' % err)
                return True
            hook = (os.path.join(stage, 'python.exe'), '-I', os.path.join(stage, staging.HOOK))
        try:
            workdir, branch = self._workspace(e, m, t, isolated=isolated)
        except PathTooLong as err:
            self._do(X.refuse, execution_id=e.id, reason='no workspace: %s' % err,
                     stop_reason='path_too_long', missions=self.missions)
            return True
        except OSError as err:
            self._do(X.refuse, execution_id=e.id, reason='no workspace: %s' % err,
                     stop_reason='workspace')
            return True
        token = 'hook_' + secrets.token_urlsafe(32)
        seq = e.process_seq + 1
        # a harness's default account runs on the home its decision recorded
        # (ADR-0048 D-25.2), never on whatever Core's environment holds
        accts = ((rd.entity.input_snapshot or {}).get('accounts') or ()) if rd else ()
        home = account.entity.home_ref if account is not None else next(
            (a.get('home_ref') for a in accts if a.get('id') is None
             and a['harness'] == e.harness_id and a.get('ref') == rd.entity.account_ref), None)
        prompt, continuation = '%s\n\n%s\n' % (m.objective, t.title), 0
        if e.handoff_from is not None:
            # a continuation (p12-design-gate §10.1): the checkpoint of the
            # execution it continues is the variable suffix of its prompt
            prompt, continuation = self._continuation(e, prompt)
        with self.db.read() as r:
            opt_ins = optins.effective(r, account_id=e.account_id, project_id=m.project_id)
        spec = base.ExecutionSpec(
            execution_id=e.id, prompt=prompt, workdir=workdir,
            attempt=e.attempt, model=e.model, effort=e.effort, process_seq=seq,
            account=base.AccountRef(e.account_id or e.harness_id, home),
            env=dict(CAPABILITY_ENV, ARCHEUS_HOOK_TOKEN=token),
            # an isolated execution's hook runs isolated (-I: no PYTHON* variables, no
            # user site, no script directory on sys.path), so the gate on every tool
            # call imports nothing the execution could plant (T-031 §3)
            hook_settings=hook,
            opt_ins=opt_ins,
            task_contract={'key': t.key, 'kind': t.kind, 'estimate': t.estimate,
                           'action_classes': list(t.action_classes),
                           'continuation': continuation,
                           'fake_scenario': self.scenarios.get(t.key, _DEFAULT)})
        # P20 (ADR-0049): what the settings sources load, taken and stored
        # before the process exists; the spawn's flags are read from exactly
        # what was stored. One that cannot be taken starts nothing, and is
        # charged like a workspace that cannot be made (P11 note 11): an
        # uncharged end re-dispatches the task, so a failure that persists
        # would start a new execution on every tick, forever.
        sha = size = None
        try:
            got = (adapter.inventory(spec, isolated=isolated) if hasattr(adapter, 'inventory')
                   else None)
            if got is not None:
                data = redact(json.dumps(got, sort_keys=True)).encode('utf-8')
                sha, size = store.put(data), len(data)
                spec = replace(spec, inventory=json.loads(data))
        except Exception as err:
            self._do(X.refuse, execution_id=e.id, stop_reason='workspace',
                     reason='the settings sources could not be inventoried: %s'
                     % type(err).__name__)
            return True
        out = self._do(X.prepare_process, execution_id=e.id, token_digest=X.token_hash(token),
                       workdir=workdir, branch=branch, process_seq=seq, isolated=isolated,
                       inventory_sha256=sha, inventory_size=size)
        if out['refused']:
            return True
        if self.node.disarmed():
            self._do(X.refuse, execution_id=e.id, reason='emergency stop: nothing starts',
                     stop_reason='disarmed')
            return True
        # where this process's output starts, taken BEFORE it can write any: a
        # size read after spawn() returns counts whatever the child wrote in
        # between as already read, so its first output is never seen
        offset = self._offset(e)
        try:
            handle = self.node.spawn(adapter, spec, resume_state=resume_state,
                                     isolated=isolated)
        except (base.SpawnFailed, base.AlreadySpawned) as err:
            # nothing started, and nothing started unisolated instead (§3.4, §6.3).
            # `binding` is the uncharged stop reason: an isolation-establishment
            # failure is infrastructure, not the user's task failing (P11's O7, as
            # decided 2026-10-08), and the task goes back to READY to be re-dispatched
            # under the bounded retry policy that policy owns.
            self._do(X.refuse, execution_id=e.id, reason='the process did not start: %s' % err,
                     stop_reason='binding')
            self._release_isolation(e)
            return True
        self._procs[e.id] = self._fresh(adapter, handle, seq, offset, None)
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

    @staticmethod
    def _fresh(adapter, handle, seq, offset, usage):
        """What the manager keeps about one live process."""
        return {'adapter': adapter, 'handle': handle, 'seq': seq, 'offset': offset,
                'reported': 0.0, 'events': 0, 'lines': [], 'usage': usage, 'since': None,
                'flagged': False, 'decisions': [], 'last_error': None, 'pressure': None,
                'window': None, 'window_source': 'none', 'context': None}

    def _continuation(self, e, prompt):
        """(prompt with the checkpoint suffix, hand-offs before this one)."""
        from . import checkpoint
        n, cur = 0, e
        with self.db.read() as r:
            cp = checkpoint.of_execution(r, e.handoff_from)
            while cur is not None and cur.handoff_from is not None and n < 1000:
                n += 1
                row = rows.get(r, entities.Execution, cur.handoff_from)
                cur = row.entity if row else None
        if cp is None:
            return prompt, n
        return '%s\n\n%s\n' % (prompt.rstrip('\n'), checkpoint.text_of(cp)), n

    def _window(self, e, adapter):
        """(window, source) of the execution's model (§13.1, ADR-0047 §2): the
        offer of the execution's own account (C-22: an offer is an account's),
        else the smallest window those offers declare; (None, 'none') when
        they declare none."""
        home = None
        if e.account_id is not None:
            with self.db.read() as r:
                row = rows.get(r, entities.Account, e.account_id)
            home = row.entity.home_ref if row is not None else None
        try:
            models = adapter.capabilities(base.AccountRef(e.account_id or e.harness_id,
                                                          home)).models
        except Exception:
            return None, 'none'
        known = {m.id: m.context_window for m in models
                 if not isinstance(m, str) and m.context_window}
        if e.model in known:
            return known[e.model], 'offer'
        return (min(known.values()), 'harness_smallest') if known else (None, 'none')

    def _workspace(self, e, m, t, *, isolated):
        """(workdir, branch) — §17. Recorded before the process starts."""
        if m.project_id is None:
            # the execution's own (class 7), never the Core-owned directory around it
            # (PV-20 §7.5)
            d = ExecPaths(e.id).work
            os.makedirs(d, exist_ok=True)
            return d, None
        if isolated:
            # A1 (PV-20 §3.2): an isolated execution never works in the user's project
            # root or in a worktree linked to its .git, and `in_place` is withdrawn for
            # it. Until a Core-seeded repository exists (T-016 W3 with W6) there is no
            # other place, so it is refused here, before any git probe of the root. This
            # is the interim refusal, charged and bounded by the task's attempts, not
            # the refusal before dispatch that A1 asks for (W5).
            raise OSError('an isolated execution has no project workspace yet (PV-20 A1)')
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
            path = task_worktree(m.project_id, m.id, t.key)
            # P13 (p13-design-gate D12): once the mission branch holds a merged
            # result, a later task starts from it, so it sees what it depends on
            mission = mission_branch(m.id)
            base = mission if self.node.branch_exists(root, mission) else 'HEAD'
            return self.node.add_worktree(root, path, want, base=base), want
        return root, branch

    # ── watching a live process ──

    def _watch(self, e, m, disarmed):
        p = self._procs[e.id]
        adapter, handle = p['adapter'], p['handle']
        did = self._tail(e, p)
        if self.node.precompacted(e.id) and (p['context'] or {}).get('signal') != 'precompact':
            # the PreCompact backstop: the harness's own signal, recorded as
            # one (quality signalled), with the policy stand-in as its pressure
            p['context'] = P.signalled(p['context'], p['offset'])
            p['pressure'] = max(p['pressure'] or 0.0, PRESSURE_PRECOMPACT)
            self._maybe_handoff(e, p)
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
                self._pressure(e, p, ev['usage'])
            _facts_from(ev, p)
            if ev.get('type') == 'limit' and e.account_id is not None and not p.get('limit'):
                p['limit'] = True
                self._progress(e, p)        # output was read: RUNNING before it hands off
                self._do(X.account_limited, account_id=e.account_id,
                         resets_at=ev.get('resets_at'))
                self._stop_account(e.account_id, 'limit', 'the provider refused for a limit')
        if time.monotonic() - p['reported'] >= PROGRESS_S:
            self._progress(e, p)
        return True

    def _pressure(self, e, p, usage):
        """Context pressure from a usage report (§13.1); at the threshold a
        running execution is handed off."""
        if p['window'] is None:
            w, p['window_source'] = self._window(e, p['adapter'])
            p['window'] = w or 0
        p['context'], got = P.reported(usage, p['window'], p['window_source'], p['offset'],
                                       p['context'])
        if got is None:
            return                      # no window, or no input figure: not measured
        p['pressure'] = max(p['pressure'] or 0.0, got)
        self._maybe_handoff(e, p)

    def _maybe_handoff(self, e, p):
        if (p['pressure'] or 0.0) < PRESSURE_HANDOFF or p.get('handing_off'):
            return
        self._progress(e, p)                # output was read: RUNNING before it hands off
        e = self._reload(e)
        if e.state != 'RUNNING':
            return
        p['handing_off'] = True
        self._do(X.request_handoff, execution_id=e.id, stop_reason='pressure',
                 reason=P.reason(p['context'], p['pressure']))

    def _progress(self, e, p):
        if not p['events'] and p['offset'] == e.stream_offset:
            return
        self._do(X.record_progress, execution_id=e.id, offset=p['offset'], events=p['events'],
                 lines=p['lines'], usage=p['usage'], pressure=p.get('pressure'),
                 context=p.get('context'))
        p['reported'], p['events'], p['lines'] = time.monotonic(), 0, []

    def _hooks(self, e, p, disarmed):
        did = False
        pending = self.node.pending_requests(e.id)
        if pending:
            # what the agent wrote before it asked is read before it is answered:
            # a usage report just ahead of a tool call is the pressure that hands
            # the execution off at that very call (p12-design-gate §10.1)
            self._tail(e, p)
            # the end's and the restart's rule, not the field alone: a resumed legacy
            # row keeps None beside the record that makes it isolated (T-036)
            known = self._isolated(e, self._isolation_record(e.id))
        for seq, req in pending:
            did = True
            if req is None:
                self.node.respond(e.id, seq, 'halt', 'the request could not be read')
                continue
            workdir = e.workdir or ExecPaths(e.id).work
            cwd = req.get('cwd')
            cwd_ok = cwd is None or _inside(cwd, workdir)
            git = e.branch and not known
            branch_now = self.node.git_branch(workdir) if git else None
            ctx = {'workdir': workdir, 'branch': branch_now,
                   'remotes': self.node.git_remotes(workdir) if git else {}}
            try:
                canon = canonical.canonicalise(req.get('tool'), req.get('input'), ctx)
                out = self._do(X.serve_hook, policy=self.policy, execution_id=e.id, seq=seq,
                               request=req, canon=canon, cwd_ok=cwd_ok,
                               branch_ok=e.branch is None or (not known
                                                              and branch_now == e.branch),
                               disarmed=disarmed)
            except Exception as err:        # never allow on a failure: fail closed
                log.warning('hook request %d of %s: %s', seq, e.id, err)
                out = {'decision': 'halt', 'reason': 'Archeus could not judge the request'}
            self.node.respond(e.id, seq, out['decision'], out['reason'])
        return did

    def _control(self, e, m, p, disarmed):
        state = e.state
        if disarmed and state in ('STARTING', 'RUNNING', 'PAUSING', 'HANDING_OFF'):
            self._do(X.stop, execution_id=e.id, reason='emergency stop', stop_reason='estop')
            state, e = 'STOPPING', self._reload(e)
        elif state in ('STARTING', 'RUNNING', 'PAUSING', 'HANDING_OFF') and (
                m is None or m.state in (
                'CANCELLED', 'FAILED', 'COMPLETED')):
            self._do(X.stop, execution_id=e.id, reason='the mission ended', stop_reason='cancel')
            state, e = 'STOPPING', self._reload(e)
        elif state == 'RUNNING' and m is not None and m.state == 'PAUSED':
            self._do(X.pause_work, mission_id=m.id)
            state, e = 'PAUSING', self._reload(e)
        if state not in ('PAUSING', 'STOPPING', 'HANDING_OFF'):
            p['since'], p['flagged'] = None, False
            return False
        if p['since'] is None:
            p['since'] = time.monotonic()
        if not p['flagged']:
            self.node.set_flag(e.id, {'PAUSING': 'PAUSE', 'HANDING_OFF': 'HANDOFF'}.get(
                state, 'STOP'))
            p['flagged'] = True
        waited = time.monotonic() - p['since']
        if state == 'HANDING_OFF':
            # the checkpoint is Core's: a hand-off that meets no tool boundary,
            # or one for an account change, needs nothing more from the process
            if e.stop_reason in _NOW or waited >= self.pause_timeout:
                self.node.kill(p['adapter'], p['handle'])
            return True
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
            self._release_isolation(e)                      # §3.2 Cleanup
            return
        isolated = self._isolated(e, self._isolation_record(e.id))
        facts = _unmeasured(p) if isolated else self._facts(e, p)
        # the adapter's figures are the harness's own total only when it says so;
        # the last progress report is a lower bound (ADR-0048 §3)
        usage, total = ((dict(result.usage), result.usage_total) if result.usage
                        else (p['usage'], False))
        if e.state == 'RUNNING' and result.failure == 'limit' and e.account_id is not None:
            # a limit seen only at the exit (p12-design-gate §10.1): the account
            # is LIMITED and the work continues elsewhere, by hand-off
            self._do(X.account_limited, account_id=e.account_id)
            self._do(X.request_handoff, execution_id=e.id, stop_reason='limit',
                     reason='the provider refused for a limit')
            e = self._reload(e)
        killed = result.exit_reason == 'killed'
        if isolated:
            # PV-20 §3.3 H2 / A7: Core's own state and observed exit decide; the halt
            # report never does. Any other end of an isolated hand-off is ENDED_ERROR.
            handoff = st.exit_code == 0 and not killed
        else:
            handoff = st.exit_code != 0 or result.halted or killed
        if e.state == 'HANDING_OFF' and handoff:
            self._do(X.record_handoff, policy=self.policy, missions=self.missions,
                     router=self.router, execution_id=e.id, now=time.time(),
                     exit_code=st.exit_code, usage=usage, usage_total=total,
                     adapter_state=result.adapter_state, final_offset=p['offset'],
                     facts=facts)
            self._release_isolation(e)                      # §3.2 Cleanup
            return
        self._do(X.record_end, execution_id=e.id, exit_code=st.exit_code,
                 killed=killed, halted=result.halted,
                 failure=result.failure, usage=usage, usage_total=total,
                 summary=result.reported_summary, adapter_state=result.adapter_state,
                 final_offset=p['offset'], output=p['offset'] > 0, facts=facts,
                 isolated=isolated)
        if self._reload(e).state in _ENDED:
            self._release_isolation(e)                      # §3.2 Cleanup

    def _facts(self, e, p):
        """What the checkpoint needs from outside the transaction (§8.2)."""
        workdir = e.workdir or ExecPaths(e.id).work
        return {'files_changed': self.node.diff_stat(workdir) if e.branch or e.workdir
                else [], 'decisions': list(p.get('decisions') or [])[-30:],
                'last_error': p.get('last_error'),
                'end_state': self.node.end_state(workdir) if e.branch or e.workdir else None}

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
                    if x.state == 'RUNNING' and reason in X.HANDOFF_CAUSES:
                        # an account change is continued elsewhere (§10.1)
                        self._do(X.request_handoff, execution_id=x.id, stop_reason=reason,
                                 reason=why)
                    else:
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
        # compaction keeps only unended spawns, so the notes the reconciles above left
        # are written again after it
        for execution_id, op in sorted(self._noted):
            self._registry_note(execution_id, op)
        # PV-20 §3.2/§3.7: a Core that comes up reclaims what the last one left — the
        # quarantine retried, and every identity whose execution is not live torn down
        self._sweep_isolation(live)
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
        iso = self._isolation_record(e.id)
        if self._isolated(e, iso):
            return self._reconcile_isolated(e, adapter, iso, handle, disarmed)
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

    def _isolation_record(self, execution_id):
        """Core's own isolation record (PV-20 §3.7), or None. It is the only thing that
        decides whether an execution was isolated: the registry is an instrument, and
        nothing in the execution's directory is authority (§3.3). A node without the
        isolation authority (a remote node, a test double) has none."""
        getter = getattr(self.node, 'isolation_record', None)
        return getter(execution_id) if getter is not None else None

    def _isolated(self, e, iso):
        """Whether the live end and the restart treat *e* as isolated (T-037 rule 1): its
        record exists (valid or not), or the row recorded Core's decision as isolated
        (T-036) and the record has gone missing. A row prepared before the field existed
        keeps the ordinary rules (the owner's N1) and is never written as ordinary. The
        field is a decision, not evidence of confinement; when it alone decides, or is
        unknown, the registry gets one line per execution per Core."""
        if iso is not None:
            return True
        if e.isolated is True:
            self._note(e, 'isolation_record_missing')
            return True
        if e.isolated is None and e.process_seq >= 1:
            self._note(e, 'isolation_decision_unknown')
        return False

    def _note(self, e, op):
        if (e.id, op) in self._noted:
            return
        self._noted.add((e.id, op))
        log.warning('execution %s: %s', e.id, op)
        self._registry_note(e.id, op)

    def _registry_note(self, execution_id, op):
        # an instrument only: a failed write must never stop the classification it
        # describes, which runs mid-end with the process handle already dropped
        try:
            self.node._registry({'op': op, 'execution_id': execution_id, 'at': time.time()})
        except OSError as err:
            log.warning('execution %s: the %s registry note was not written: %s',
                        execution_id, op, err)

    def _reconcile_isolated(self, e, adapter, iso, handle, disarmed):
        """Restart reconciliation of an isolated execution (PV-20 §3.7; ADR-0053
        §7.6–7.7 and the owner's decision of 2026-10-08): **a live isolated process is
        never re-adopted.** Its Job died with the Core that held it, so nothing of it
        survives to adopt; the record is resolved here, and no file the execution could
        have written — `halted.json` above all, which is the execution's own claim — is
        read as authority. `PAUSING` becomes `PAUSED`: an interrupted process is never
        reinterpreted as a failure, and never as success either.

        The remaining states resolve at the record level through terminate / reap / fail
        (R6-A). An isolation-establishment failure was never a process at all, so it
        keeps the uncharged end O7's decision gives it, and re-dispatches. *iso* is None
        when the record is gone and the row's decision alone says isolated (T-037): the
        same outcomes, and no record is synthesized for it."""
        self._procs.pop(e.id, None)
        if handle is not None and self.node.alive(handle):
            # R6-A: a live isolated process after a Core restart is a contradiction —
            # its sole Job holder died, so kill-on-close should have ended it. It is
            # killed by identity here and never adopted.
            self.node.kill(adapter, handle)
        if iso is not None and (iso.state == 'failed' or iso.failure):
            # `failure` outlives the cleanup that quarantines the profile afterwards
            self._tombstone(e)
            self._do(X.refuse, execution_id=e.id, stop_reason='binding',
                     reason='isolation could not be established: %s'
                            % (iso.failure or iso.reason or 'unknown'))
            return True
        if e.state in ('PAUSED', 'AWAITING_APPROVAL'):
            return False                       # no process of ours: the pass decides
        if e.state == 'PAUSING':
            self._tombstone(e)
            self._do(X.record_end, execution_id=e.id, exit_code=None, core_halt=True,
                     isolated=True, usage=e.usage, final_offset=e.stream_offset,
                     facts=_unmeasured({}))
            return True
        if e.state in ('STOPPING', 'HANDING_OFF'):
            self._tombstone(e)
            self._do(X.record_end, execution_id=e.id, exit_code=None, killed=True,
                     isolated=True, usage=e.usage, final_offset=e.stream_offset,
                     facts=_unmeasured({}))
            return True
        if e.state == 'INTENT' and handle is None:
            self._do(X.refuse, execution_id=e.id, reason='no process was started',
                     stop_reason='disarmed' if disarmed else 'binding')
            return True
        self._tombstone(e)
        self._do(X.lost, execution_id=e.id,
                 reason='Core restarted; the isolated process is gone and left no exit')
        return True

    def _release_isolation(self, e):
        """§3.2 Cleanup: an execution that has ended leaves no identity and no grants
        behind. Called on the end paths this pass watches; the sweep below is what
        makes it every end path rather than a list of call sites."""
        releaser = getattr(self.node, 'end_isolation', None)
        if releaser is None:
            return
        try:
            releaser(e.id, reason='ended')
        except OSError as err:
            # a write of this execution's own (its record, its ledger line, a registry
            # note) failed: the record stays on disk for the sweep to finish, and the
            # rest of this pass, and every other execution's Job, is not this one's to end
            log.warning('execution %s: isolation release did not complete: %s', e.id, err)

    def _sweep_isolation(self, live):
        """§3.2 Cleanup and §3.7, made structural: whatever ended an execution — this
        pass, the mission layer, a Core that died — its identity and grants go, and
        anything that will not go is quarantined and retried. Bounded, and it never
        touches an execution that is still live."""
        sweeper = getattr(self.node, 'reclaim_isolation', None)
        if sweeper is None:
            return []
        try:
            done = sweeper({x.id for x in live}) or []
        except OSError as err:
            # logged once per distinct fault, not once per pass: the sweep runs every
            # few seconds and a persistent fault would otherwise flood the log
            if str(err) != self._isolation_fault:
                log.warning('the isolation sweep did not complete: %s', err)
            self._isolation_fault = str(err)
            return []
        self._isolation_fault = None
        return done

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
        self._procs[e.id] = self._fresh(adapter, handle, e.process_seq, e.stream_offset,
                                        e.usage)
        self._procs[e.id]['context'] = e.context      # the basis recorded so far
        self._do(X.adopted, execution_id=e.id, pid=handle.pid, offset=e.stream_offset)

    def _collect_gone(self, e, adapter, handle):
        """The process is gone: collect what it left, as if observed (§15.3). An
        exit nobody can read is LOST, never success."""
        st = adapter.status(handle)
        p = self._fresh(adapter, handle, e.process_seq, e.stream_offset, e.usage)
        if st.state != 'exited' or st.exit_code is None:
            if e.state in ('STOPPING', 'HANDING_OFF'):
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


def _facts_from(ev, p):
    """DECISION: lines and the last error, collected as the stream is read."""
    t = ev.get('type')
    text = ev.get('text') if isinstance(ev.get('text'), str) else ''
    if t == 'assistant' and 'DECISION:' in text:
        for line in text.splitlines():
            if line.strip().startswith('DECISION:'):
                p['decisions'].append(redact(line.strip()[len('DECISION:'):].strip())[:300])
    if t in ('error', 'stderr', 'limit'):
        p['last_error'] = redact(str(ev.get('text') or ev.get('error') or ev.get('kind')
                                     or t))[:300]


def _unmeasured(p):
    """The facts of a known-isolated end (T-044): the stream's, and no diff or end state,
    which only Git in the execution's workdir would give."""
    return {'files_changed': [UNMEASURED], 'decisions': list(p.get('decisions') or [])[-30:],
            'last_error': p.get('last_error'), 'end_state': None}


def _inside(path, root):
    try:
        a, b = os.path.realpath(path), os.path.realpath(root)
        return os.path.commonpath([os.path.normcase(a), os.path.normcase(b)]) == \
            os.path.normcase(b)
    except ValueError:
        return False


#: what the fake agent does for a task no scenario is scripted for
_DEFAULT = [{'emit': {'type': 'result', 'summary': 'done'}}]
