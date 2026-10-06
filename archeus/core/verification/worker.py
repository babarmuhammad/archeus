"""`archeus-verify` (p13-design-gate §18): verification, merge-back and review,
driven by durable state.

A scan, not an event consumer: `plan()` reads the rows and lists what is due;
`pass_once()` does the first item. After G01, a continuation is found from rows,
so a lost wake-up can only delay work, never lose it. One item at a time; the
checks run outside any transaction; every record goes through
`application/verification.py`, which re-derives the lineage. The worker never
moves a mission: it writes rows and the engine's `advance` judges them.

    due                                                  step
    a VERIFYING task, nothing recorded for its execution  verify_task
    ... its automatic checks passed, a human criterion    verify_human
    an ERROR row, retries left / the mission resumed      retry
    an ERROR row, no retry left                           hold
    integration PENDING or MERGING                        merge
    integration CONFLICT and the mission resumed          retry_merge
    a VERIFYING mission, a criterion unrecorded at head   verify_mission
    a REVIEWING mission with no review of its plan        review
"""

import logging
import os

from ...infra import paths
from ...infra.db import rows
from ...node.local import LocalNode
from ..application import calls as C
from ..application import errors, verification as V
from ..application.commands import active_plan
from ..domain import entities
from ..domain.values import Ref
from ..engine import SETTLED
from ..execution.manager import mission_branch
from . import evidence, reviewer

log = logging.getLogger('archeus.core')

_CODE = 'code'
_HUMAN = 'generic_human'


def _rows(conn, cls, **eq):
    return [r.entity for r in rows.where(conn, cls, **eq)]


def _mission_wt(project_id, mission_id):
    return os.path.join(paths.archeus_home(), 'worktrees', project_id, mission_id, '_mission')


class VerifyWorker:
    """Verifies, merges and reviews for one Core. `missions` is its
    `commands.Missions`; `calls` its `OwnCalls` (None: no review calls — the
    engine's injected stub reviewer reviews instead); `verify` False leaves
    verification to the engine's injected stub verifier."""

    def __init__(self, db, *, actor, missions, calls=None, node=None, verify=True,
                 timeout_s=None):
        self.db, self.actor, self.missions, self.calls = db, actor, missions, calls
        self.node = node or LocalNode()
        self.verify = verify
        self.timeout_s = timeout_s or evidence.CHECK_TIMEOUT_S
        self.on_wake = None
        self.stopping = lambda: False

    def _do(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.actor))

    # ── the worker contract (WorldLoop) ──

    def pending(self):
        with self.db.read() as conn:
            n = len(self.plan(conn))
        if n and self.on_wake is not None:
            self.on_wake()
        return n

    def sweep(self):
        return self._do(V.sweep) if self.verify else []

    def pass_once(self):
        with self.db.read() as conn:
            due = self.plan(conn)
        for item in due:
            if self.stopping():
                break
            try:
                if getattr(self, '_' + item[0])(*item[1:]):
                    return {'changed': True, 'did': item[0]}
            except errors.WriterClosed:
                raise
            except (V.Refused,) + errors.LOST_RACE as e:
                log.info('verification: %s %s lost a race: %s', item[0], item[1:], e)
                return {'changed': True, 'did': 'lost_race'}
        return {'changed': False}

    # ── what is due (§18) ──

    def plan(self, conn):
        due = []
        for m in _rows(conn, entities.Mission):
            if m.state in SETTLED and m.state != 'BLOCKED':
                continue
            plan = active_plan(conn, m.id)
            if plan is None:
                continue
            vs = _rows(conn, entities.Verification, plan_id=plan.entity.id)
            tasks = _rows(conn, entities.Task, plan_id=plan.entity.id)
            if self.verify:
                for t in tasks:
                    due += self._task_due(conn, m, t, vs)
                if V.mission_open(m) and self._mission_due(m, vs):
                    due.append(('verify_mission', m.id))
            for t in tasks:
                if t.integration_state in ('PENDING', 'MERGING'):
                    due.append(('merge', t.id))
                elif t.integration_state == 'CONFLICT' and m.state == 'EXECUTING':
                    due.append(('retry_merge', t.id))
            if m.state == 'REVIEWING' and self.calls is not None and self._review_due(conn, m,
                                                                                    plan):
                due.append(('review', m.id))
        return due

    def _task_due(self, conn, m, t, vs):
        if t.state != 'VERIFYING':
            return []
        e = V.verified_execution(conn, t)
        if e is None:
            return []
        mine = [v for v in vs if v.subject == Ref('task', t.id) and v.execution_id == e.id]
        if not mine:
            return [('verify_task', t.id, e.id)]
        for v in mine:
            if v.state == 'ERROR':
                if m.state == 'EXECUTING' and (v.holds_mission or v.errors < V.ERROR_ATTEMPTS):
                    return [('retry', v.id)]
                if not v.holds_mission and m.state == 'EXECUTING':
                    return [('hold', v.id)]
                return []
        if any(v.state in ('RUNNING', 'AWAITING_HUMAN') for v in mine):
            return []
        if all(v.state == 'PASSED' for v in mine) and V.uncovered(t, mine):
            return [('verify_human', t.id, e.id)]
        return []

    def _mission_due(self, m, vs):
        at_head = [v for v in vs if v.subject == Ref('mission', m.id)
                   and v.revision == m.integration_head]
        for i, _c in enumerate(m.success_criteria):
            mine = [v for v in at_head if v.criterion == i]
            if not mine:
                return True
            last = mine[-1]
            if last.state == 'ERROR' and not last.holds_mission:
                return True
        return False

    def _review_due(self, conn, m, plan):
        if _rows(conn, entities.Review, plan_id=plan.entity.id):
            return False
        failed = [r for r in rows.where(conn, entities.RouteDecision, purpose='review')
                  if r.entity.source is not None and r.entity.source.id == m.id
                  and r.created_at >= plan.created_at
                  and r.entity.outcome is not None and r.entity.outcome.get('state') != 'ok']
        return len(failed) < V.REVIEW_CALL_ATTEMPTS

    # ── verifying a task (§8, §12.2, §13) ──

    def _workspace_of(self, conn, m, t, e):
        """(root, workspace, revision, base, commands) as observed now; a
        worktree task's uncommitted work is committed first (§12.2)."""
        root = evidence.project_root(conn, m.project_id)
        workspace = e.workdir
        head = self.node.git_head(workspace) if workspace else None
        if head is None:
            return root, workspace, None, None, ((), ())
        if e.branch == V.task_branch(t) and self.node.git_dirty(workspace):
            head = self.node.git_snapshot(
                workspace, 'archeus: result of task %s (attempt %d)' % (t.key, e.attempt))
        mb = mission_branch(m.id)
        against = mb if self.node.branch_exists(root, mb) else 'HEAD'
        base = (self.node.git_merge_base(root, head, against) if e.branch == V.task_branch(t)
                else None)
        return root, workspace, head, base, evidence.commands(conn, m.project_id, root)

    def _verify_task(self, task_id, execution_id):
        with self.db.read() as conn:
            t = rows.get(conn, entities.Task, task_id).entity
            m = rows.get(conn, entities.Mission, t.mission_id).entity
            e = rows.get(conn, entities.Execution, execution_id).entity
            root, ws, revision, base, (tests, builds) = self._workspace_of(conn, m, t, e)
        indexed = [dict(c, index=i) for i, c in enumerate(t.acceptance)]
        auto = [c for c in indexed if c['check'] == 'automatic']
        prov = evidence.provenance(e)
        cmds = [('test', c) for c in tests] + [('build', c) for c in builds]
        if not (auto and revision is not None and t.kind in evidence.CODE_KINDS and cmds):
            # nothing deterministic can decide it: a human does (§8.4, §13)
            self._do(V.start, missions=self.missions, subject=Ref('task', t.id),
                     verifier=_HUMAN, execution_id=e.id, revision=revision,
                     base_revision=base, workspace=ws, provenance=prov,
                     criteria=[dict(c, result='unknown') for c in indexed])
            return True
        out = self._do(V.start, missions=self.missions, subject=Ref('task', t.id),
                       verifier=_CODE, execution_id=e.id, revision=revision,
                       base_revision=base, workspace=ws, provenance=prov,
                       criteria=[dict(c, result='unknown') for c in auto])
        self._run_and_record(out['verification_id'], t, root, ws, revision, base, cmds)
        return True

    def _run_and_record(self, vid, t, root, ws, revision, base, cmds):
        checks = []
        if t.kind == 'code_change' and base is not None:
            checks.append(evidence.changes_check(self.node, root, base, revision))
        checks += evidence.run_commands(self.node, ws, cmds, verification_id=vid,
                                        timeout_s=self.timeout_s)
        now = self.node.git_head(ws)
        if now != revision or self.node.git_dirty(ws, tracked_only=True):
            checks.append({'name': 'workspace', 'kind': 'git', 'result': 'error',
                           'detail': 'the workspace moved during verification (%s -> %s)'
                                     % ((revision or '')[:12], (now or '')[:12])})
        self._do(V.record, missions=self.missions, verification_id=vid, checks=checks)

    def _verify_human(self, task_id, execution_id):
        """The automatic checks passed; the task's human criteria wait for you."""
        with self.db.read() as conn:
            t = rows.get(conn, entities.Task, task_id).entity
            vs = [v for v in _rows(conn, entities.Verification, plan_id=t.plan_id)
                  if v.subject == Ref('task', t.id) and v.execution_id == execution_id]
            e = rows.get(conn, entities.Execution, execution_id).entity
        first = vs[0]
        left = [dict(c, index=i, result='unknown') for i, c in enumerate(t.acceptance)
                if i in V.uncovered(t, vs)]
        self._do(V.start, missions=self.missions, subject=Ref('task', t.id), verifier=_HUMAN,
                 execution_id=e.id, revision=first.revision, base_revision=first.base_revision,
                 workspace=first.workspace, provenance=first.provenance, criteria=left)
        return True

    def _retry(self, verification_id):
        with self.db.read() as conn:
            v = rows.get(conn, entities.Verification, verification_id).entity
        self._do(V.retry, verification_id=v.id)
        if v.subject.kind == 'task':
            with self.db.read() as conn:
                t = rows.get(conn, entities.Task, v.subject.id).entity
                m = rows.get(conn, entities.Mission, t.mission_id).entity
                root = evidence.project_root(conn, m.project_id)
                tests, builds = evidence.commands(conn, m.project_id, root)
            cmds = [('test', c) for c in tests] + [('build', c) for c in builds]
            self._run_and_record(v.id, t, root, v.workspace, v.revision, v.base_revision, cmds)
        else:
            with self.db.read() as conn:
                m = rows.get(conn, entities.Mission, v.subject.id).entity
                root = evidence.project_root(conn, m.project_id)
                tests, builds = evidence.commands(conn, m.project_id, root)
            cmds = [('test', c) for c in tests] + [('build', c) for c in builds]
            checks = evidence.run_commands(self.node, v.workspace, cmds, verification_id=v.id,
                                           timeout_s=self.timeout_s)
            head = self.node.git_head(v.workspace) if m.integration_base is not None else None
            self._do(V.record, missions=self.missions, verification_id=v.id, checks=checks,
                     head=head)
        return True

    def _hold(self, verification_id):
        self._do(V.hold, missions=self.missions, verification_id=verification_id)
        return True

    # ── merge-back (§12) ──

    def _merge(self, task_id):
        with self.db.read() as conn:
            t = rows.get(conn, entities.Task, task_id).entity
            m = rows.get(conn, entities.Mission, t.mission_id).entity
            root = evidence.project_root(conn, m.project_id)
            passed = [v for v in _rows(conn, entities.Verification, plan_id=t.plan_id)
                      if v.subject == Ref('task', t.id) and v.state == 'PASSED'
                      and v.revision is not None]
            e = V.verified_execution(conn, t)
        revision = passed[-1].revision if passed else None
        if t.integration_state == 'PENDING':
            self._do(V.begin_merge, task_id=t.id, revision=revision)
        branch = mission_branch(m.id)
        base = m.integration_base or self.node.git_merge_base(root, revision, 'HEAD')
        wt = self.node.mission_worktree(root, _mission_wt(m.project_id, m.id), branch,
                                        base or revision)
        head = self.node.git_head(wt)
        if head is not None and self.node.git_is_ancestor(root, revision, head):
            outcome, got = 'merged', head          # merged before a restart (§12.4)
        else:
            outcome, got = self.node.git_merge(wt, revision, 'archeus: merge task %s (%s)'
                                               % (t.key, revision[:12]))
        if outcome == 'merged':
            self._do(V.record_merge, missions=self.missions, task_id=t.id, outcome='merged',
                     head=got, base=base)
            if e is not None and e.workdir and e.branch == V.task_branch(t):
                self.node.remove_worktree(root, e.workdir)   # the removal P11 deferred
        else:
            self._do(V.record_merge, missions=self.missions, task_id=t.id, outcome='conflict',
                     conflicts=got)
        return True

    def _retry_merge(self, task_id):
        self._do(V.retry_merge, task_id=task_id)
        return True

    # ── verifying a mission's criteria (§11, §13) ──

    def _verify_mission(self, mission_id):
        with self.db.read() as conn:
            m = rows.get(conn, entities.Mission, mission_id).entity
            root = evidence.project_root(conn, m.project_id)
            plan = active_plan(conn, m.id)
            vs = [v for v in _rows(conn, entities.Verification, plan_id=plan.entity.id)
                  if v.subject == Ref('mission', m.id)]
            tests, builds = evidence.commands(conn, m.project_id, root)
        if m.integration_base is not None:
            ws = _mission_wt(m.project_id, m.id)
            disk = self.node.git_head(ws)
            if disk != m.integration_head:
                # moved on disk since Core recorded it: what was verified is stale
                self._do(V.note_integration_head, mission_id=m.id, head=disk)
                return True
        else:
            ws = root if root and self.node.git_head(root) else None
        at_head = [v for v in vs if v.revision == m.integration_head]
        cmds = [('test', c) for c in tests] + [('build', c) for c in builds]
        auto, human = [], []
        for i, c in enumerate(m.success_criteria):
            mine = [v for v in at_head if v.criterion == i]
            last = mine[-1] if mine else None
            crit = [{'index': i, 'text': c['text'], 'check': c['check'], 'result': 'unknown'}]
            if last is None:
                (auto if c['check'] == 'automatic' and ws and cmds else human).append((i, crit))
            elif last.state == 'ERROR' and not last.holds_mission:
                if last.errors < V.ERROR_ATTEMPTS:
                    self._retry(last.id)
                    return True
                human.append((i, crit))     # it could not run twice: a human decides
        for i, crit in human:
            self._do(V.start, missions=self.missions, subject=Ref('mission', m.id),
                     verifier=_HUMAN, criterion=i, revision=m.integration_head, workspace=ws,
                     criteria=crit)
        if auto:
            started = [self._do(V.start, missions=self.missions, subject=Ref('mission', m.id),
                                verifier=_CODE, criterion=i, revision=m.integration_head,
                                base_revision=m.integration_base, workspace=ws,
                                criteria=crit)['verification_id'] for i, crit in auto]
            checks = evidence.run_commands(self.node, ws, cmds, verification_id=started[0],
                                           timeout_s=self.timeout_s)
            # the branch may have moved while the commands ran: the last record notes it
            head = self.node.git_head(ws) if m.integration_base is not None else None
            for n, vid in enumerate(started, 1):
                self._do(V.record, missions=self.missions, verification_id=vid, checks=checks,
                         head=head if n == len(started) else None)
        return bool(auto or human)

    # ── review (§14) ──

    def _review(self, mission_id):
        with self.db.read() as conn:
            m = rows.get(conn, entities.Mission, mission_id).entity
            root = evidence.project_root(conn, m.project_id)
            executed = reviewer.executions_of(conn, m)
        diff = (self.node.git_numstat(root, m.integration_base, m.integration_head)
                if m.integration_base and m.integration_head else None)
        with self.db.read() as conn:
            text = reviewer.prompt(conn, m, diff)
        ask = dict(purpose='review', source={'kind': 'mission', 'id': m.id},
                   workspace_id=m.workspace_id, project_id=m.project_id, prompt=text,
                   schema=reviewer.SCHEMA, check=reviewer.check,
                   workdir=paths.archeus_home())
        c = self.calls.run(forbidden=reviewer.forbidden(executed), **ask)
        if c.state == 'unavailable':
            # no independent resource is free: the review runs anyway (§14.3)
            c = self.calls.run(**ask)
        if c.state != 'ok':
            return True             # the call ended itself; counted by `_review_due`
        with self.db.read() as conn:
            res = reviewer.resource_of(conn, c.route_decision_id)
        found = {k: list(c.parsed.get(k) or ()) for k in entities.REVIEW_LISTS}
        self._do(_record_review, missions=self.missions, mission_id=m.id, called=c,
                 verdict=c.parsed['verdict'], summary=c.parsed.get('summary') or '',
                 independent=reviewer.independent(
                     (res['harness_id'], res['account'], res['model']), executed),
                 reviewer_resource=res, found=found)
        return True


def _record_review(tx, *, actor, missions, mission_id, called, verdict, summary, independent,
                   reviewer_resource, found):
    """The review and the call's end in one transaction (as the planner records
    a plan with its call's end, P8)."""
    C.end_call(tx, actor=actor, route_decision_id=called.route_decision_id,
               outcome={'state': 'ok', 'attempts': called.attempts,
                        'account_ref': called.account_ref},
               usage=called.usage or None)
    return V.record_review(tx, actor=actor, missions=missions, mission_id=mission_id,
                           verdict=verdict, reviewer='model', independent=independent,
                           route_decision_id=called.route_decision_id,
                           reviewer_resource=reviewer_resource, summary=summary, **found)

