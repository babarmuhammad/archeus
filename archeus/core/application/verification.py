"""P13: the commands that record verification, merge-back and review
(p13-design-gate §6-§14, §17, §19, §20).

Every verdict is written here, by the verification worker (core/verification/),
from evidence it observed itself; a user device can only decide a row that is
AWAITING_HUMAN, review a REVIEWING mission, or abandon a conflicting merge.
Each command re-derives the lineage it records from the rows in its own
transaction and refuses a mismatch (`Refused`, 422): nothing a caller passes
decides which task, plan, execution or revision a verdict is about.

    start           a Verification bound to (subject, plan, execution, revision)
    record          its checks -> PASSED | FAILED | ERROR, and the task's move
    retry / hold    an ERROR retried once, then the mission blocked (§6)
    await_human     GenericVerifier: AWAITING_HUMAN, the mission blocked (§17)
    decide          a user device accepts or rejects what waits on a human
    sweep           boot: a RUNNING row is `verifier_crashed` (§19)
    begin_merge / record_merge / abandon_integration     Integration (§12)
    note_integration_head                                 the mission branch moved (§11)
    record_review / user_review                           Review (§14, §7)
"""

from ...infra.artifacts import store
from ..domain import entities, guards, ids
from ..domain.events import new_event
from ..domain.values import Ref
from . import lifecycle
from .commands import active_plan
from .executions import charged_failure

#: the verifier implementation a row names (p13-design-gate §8.2)
VERIFIER_VERSION = 'p13.1'
#: an ERROR is retried once, then the mission waits for the user (§6)
ERROR_ATTEMPTS = 2
#: failed `review` calls per plan version before the worker waits for the user (§7)
REVIEW_CALL_ATTEMPTS = 2
_REVIEW = {'accept': 'verdict_accept', 'changes_requested': 'verdict_changes',
           'reject': 'verdict_reject'}


class Refused(ValueError):
    """A verification, merge or review whose lineage does not match durable
    state (§20): refused, nothing written."""


# ── pure: from checks to a verdict (§8.4) ──────────────────────────────────

def verdict_of(checks):
    """FAILED if any check failed, else ERROR if any errored, else PASSED —
    when at least one outcome (command) check ran. A CodeVerifier is started
    only with at least one command to run (the GenericVerifier decides the
    rest), so a battery with no outcome check here is ERROR, never PASSED."""
    results = [c['result'] for c in checks]
    if 'fail' in results:
        return 'FAILED'
    if 'error' in results:
        return 'ERROR'
    if not any(c['kind'] == 'command' for c in checks):
        return 'ERROR'
    return 'PASSED'


def readings(criteria, state):
    """Each criterion's reading of a verification in *state* (§8.4)."""
    of = {'PASSED': 'satisfied', 'FAILED': 'failed'}
    return tuple(dict(c, result=of.get(state, 'unknown') if c['check'] == 'automatic'
                      else c.get('result', 'unknown'))
                 for c in criteria)


# ── lineage (§9, §20) ───────────────────────────────────────────────────────

def verified_execution(conn, task):
    """The execution whose end moved *task* to VERIFYING: its latest ENDED_OK."""
    ok = [r.entity for r in _where(conn, entities.Execution, task_id=task.id)
          if r.entity.state == 'ENDED_OK']
    return max(ok, key=lambda e: (e.attempt, e.id), default=None)


def performed_by(conn, e):
    """The routed identity of execution *e*, copied from its rows (§22)."""
    rd = _get(conn, entities.RouteDecision, e.route_decision_id) if e.route_decision_id else None
    return {'harness_id': e.harness_id, 'account_id': e.account_id,
            'account_ref': rd.account_ref if rd is not None else None,
            'model': e.model, 'effort': e.effort, 'route_decision_id': e.route_decision_id,
            'session_id': e.session_id}


def _get(conn, cls, eid):
    from ...infra.db import rows
    r = rows.get(conn, cls, eid)
    return r.entity if r is not None else None


def _where(conn, cls, **eq):
    from ...infra.db import rows
    return rows.where(conn, cls, **eq)


def _in_force(tx, t):
    plan = active_plan(tx.conn, t.mission_id)
    return plan is not None and plan.entity.id == t.plan_id


def _task_lineage(tx, task_id, execution_id):
    t = lifecycle.load(tx, entities.Task, task_id).entity
    if t.state != 'VERIFYING':
        raise Refused('task %s is %s, not VERIFYING' % (task_id, t.state))
    if not _in_force(tx, t):
        raise Refused("task %s belongs to a plan that is not in force" % task_id)
    e = verified_execution(tx.conn, t)
    if e is None or e.id != execution_id:
        raise Refused('execution %s is not the one whose end moved task %s to VERIFYING'
                      % (execution_id, task_id))
    return t, e


def _mission(tx, mission_id):
    return lifecycle.load(tx, entities.Mission, mission_id).entity


def mission_open(m):
    """Is mission *m* being verified: VERIFYING, or BLOCKED out of it waiting
    for a human criterion (the engine may take `awaiting_human_acceptance`
    between the worker's transactions; the rows it still records are bound by
    plan and revision, not by the mission's state)."""
    return m.state == 'VERIFYING' or (m.state == 'BLOCKED' and m.held_from == 'VERIFYING')


def _event(tx, type_, subject, actor, mission, payload):
    return tx.append(new_event(type_, subject, actor, payload=payload,
                               workspace=mission.workspace_id, project=mission.project_id))


def _fire(tx, cls, eid, trigger, actor, reason, fields=None, machine=None, facts=None):
    return lifecycle.fire(tx, cls, eid, trigger, actor=actor, reason=reason, fields=fields,
                          machine=machine, facts=facts)[0]


# ── start (§6) ──────────────────────────────────────────────────────────────

def start(tx, *, actor, missions, subject, verifier, execution_id=None, criterion=None,
          revision=None, base_revision=None, workspace=None, provenance=None, criteria=()):
    """A Verification PENDING -> RUNNING (a CodeVerifier about to run its
    checks) or PENDING -> AWAITING_HUMAN (the GenericVerifier), bound to the
    lineage re-derived here."""
    subject = subject if isinstance(subject, Ref) else Ref(**subject)
    if subject.kind == 'task':
        t, e = _task_lineage(tx, subject.id, execution_id)
        m, plan_id, who = _mission(tx, t.mission_id), t.plan_id, performed_by(tx.conn, e)
    elif subject.kind == 'mission':
        m = _mission(tx, subject.id)
        if not mission_open(m):
            raise Refused('mission %s is %s, not verifying' % (m.id, m.state))
        if not (isinstance(criterion, int) and 0 <= criterion < len(m.success_criteria)):
            raise Refused('mission %s has no success criterion %r' % (m.id, criterion))
        if revision != m.integration_head:
            raise Refused('revision %s is not the mission branch head %s'
                          % (revision, m.integration_head))
        plan_id, who, execution_id = active_plan(tx.conn, m.id).entity.id, None, None
    else:
        raise Refused('a verification is of a task or a mission')
    v = entities.Verification(
        id=ids.new_id('verification'), subject=subject, verifier=verifier, plan_id=plan_id,
        criterion=criterion, execution_id=execution_id, revision=revision,
        base_revision=base_revision, workspace=workspace, performed_by=who,
        verifier_version=VERIFIER_VERSION, provenance=provenance, criteria=tuple(criteria))
    tx.insert(v, actor=actor)
    _event(tx, 'verification.created', Ref('verification', v.id), actor, m,
           {'subject': {'kind': subject.kind, 'id': subject.id}, 'criterion': criterion,
            'plan_id': plan_id, 'execution_id': execution_id, 'revision': revision,
            'verifier': verifier})
    if verifier == 'generic_human':
        row = _fire(tx, entities.Verification, v.id, 'generic_verifier', actor,
                    'nothing deterministic can decide this; waiting for your acceptance')
        if subject.kind == 'task':
            _hold(tx, actor, missions, m, row, 'waiting for your acceptance of task %s' % t.key)
        return {'verification_id': v.id, 'state': 'AWAITING_HUMAN'}
    _fire(tx, entities.Verification, v.id, 'start', actor, 'verifier %s' % verifier)
    return {'verification_id': v.id, 'state': 'RUNNING'}


# ── record (§8.4, §10, §20) ─────────────────────────────────────────────────

def record(tx, *, actor, missions, verification_id, checks, criteria=None, head=None):
    """The checks of a RUNNING verification and its verdict; a task's move in
    the same transaction. Lineage is re-checked against the row as started.
    *head* is the mission branch head read after the checks ran: one that moved
    while they ran is noted here, so no judgement sees the verdict without it (§11)."""
    row = lifecycle.load(tx, entities.Verification, verification_id)
    v = row.entity
    if v.state != 'RUNNING':
        raise Refused('verification %s is %s, not RUNNING' % (v.id, v.state))
    checks = tuple(dict(c) for c in checks)
    for c in checks:
        sha = c.get('output_sha256')
        if sha is None:
            continue
        try:
            data = store.get(sha)
        except (OSError, ValueError):
            raise Refused('check %r names evidence %s the store does not hold intact'
                          % (c.get('name'), sha)) from None
        if tx.get(entities.Artifact, sha) is None:
            tx.insert(entities.Artifact(id=sha, media_type='text/plain', size=len(data)),
                      actor=actor)
    if v.subject.kind == 'task':
        t, _e = _task_lineage(tx, v.subject.id, v.execution_id)
        m = _mission(tx, t.mission_id)
    else:
        m = _mission(tx, v.subject.id)
        if not mission_open(m) or v.revision != m.integration_head:
            raise Refused('mission %s moved since verification %s started' % (m.id, v.id))
        if v.plan_id != active_plan(tx.conn, m.id).entity.id:
            raise Refused('verification %s is of a plan that is not in force' % v.id)
    state = verdict_of(checks)
    trigger = {'PASSED': 'all_checks_pass', 'FAILED': 'a_check_fails',
               'ERROR': 'verifier_crashed'}[state]
    read = readings(criteria if criteria is not None else v.criteria, state)
    fields = {'checks': checks, 'criteria': read}
    why = '; '.join('%s: %s' % (c['name'], c['result']) for c in checks) or 'no checks'
    if state == 'ERROR':
        fields.update(errors=v.errors + 1,
                      error=next((c.get('detail') for c in checks if c['result'] == 'error'),
                                 'no outcome check could run'))
    _fire(tx, entities.Verification, v.id, trigger, actor, 'verifier %s: %s' % (v.verifier, why),
          fields=fields)
    if v.subject.kind == 'mission' and head and head != m.integration_head:
        note_integration_head(tx, actor=actor, mission_id=m.id, head=head)
    out = {'verification_id': v.id, 'state': state}
    if v.subject.kind == 'task' and state != 'ERROR':
        out['task_state'] = settle_task(tx, actor=actor, task_id=v.subject.id).get('state')
    return out


def settle_task(tx, *, actor, task_id):
    """Move a VERIFYING task by the verifications of its verified execution:
    any FAILED -> retry or FAILED; every one PASSED (none awaiting, none in
    error or running) -> SUCCEEDED, starting its merge-back when it ran in a
    worktree. Otherwise it keeps waiting."""
    t = lifecycle.load(tx, entities.Task, task_id).entity
    if t.state != 'VERIFYING':
        return {'state': t.state, 'changed': False}
    e = verified_execution(tx.conn, t)
    mine = [r.entity for r in tx.where(entities.Verification, plan_id=t.plan_id)
            if r.entity.subject == Ref('task', t.id) and e is not None
            and r.entity.execution_id == e.id]
    states_ = [x.state for x in mine]
    if 'FAILED' in states_:
        bad = next(x for x in mine if x.state == 'FAILED')
        t2 = charged_failure(tx, actor, t, 'checks_failed_retry', 'checks_failed_final',
                             'verification', 'verification %s failed' % bad.id).entity
        return {'state': t2.state, 'changed': True}
    if not mine or any(s != 'PASSED' for s in states_) or uncovered(t, mine):
        return {'state': t.state, 'changed': False}
    fields = None
    if e.branch == task_branch(t):              # it ran in its own worktree (§12)
        fields = {'integration_state': 'PENDING'}
    t2 = _fire(tx, entities.Task, t.id, 'checks_passed', actor,
               'verification %s passed' % ', '.join(x.id for x in mine), fields=fields)
    return {'state': t2.entity.state, 'changed': True}


def uncovered(t, vs):
    """Indexes of *t*'s acceptance criteria no PASSED verification satisfied:
    a task succeeds only when every one is (no criterion is skipped, §13)."""
    ok = {c['index'] for v in vs if v.state == 'PASSED' for c in v.criteria
          if c.get('result') == 'satisfied'}
    return [i for i in range(len(t.acceptance)) if i not in ok]


def _mission_branch(mission_id):
    from ..execution.manager import mission_branch
    return mission_branch(mission_id)


def task_branch(t):
    """The branch P11 gives a worktree task (p11-design-gate §27 item 4)."""
    return '%s.%s' % (_mission_branch(t.mission_id), t.key)


# ── ERROR: retry once, then the user (§6) ───────────────────────────────────

def retry(tx, *, actor, verification_id):
    """ERROR -> PENDING -> RUNNING on the same row (its lineage unchanged)."""
    v = lifecycle.load(tx, entities.Verification, verification_id).entity
    if v.subject.kind == 'task':
        _task_lineage(tx, v.subject.id, v.execution_id)
    _fire(tx, entities.Verification, v.id, 'retry', actor,
          'retrying after: %s' % (v.error or 'an error'), fields={'holds_mission': False})
    _fire(tx, entities.Verification, v.id, 'start', actor, 'verifier %s' % v.verifier)
    return {'verification_id': v.id, 'state': 'RUNNING'}


def hold(tx, *, actor, missions, verification_id):
    """A verification that could not run twice: the mission waits for the user,
    with the reason (§6, §17)."""
    row = lifecycle.load(tx, entities.Verification, verification_id)
    v = row.entity
    m = _mission(tx, v.subject.id if v.subject.kind == 'mission'
                 else lifecycle.load(tx, entities.Task, v.subject.id).entity.mission_id)
    return _hold(tx, actor, missions, m, row,
                 'verification could not run: %s' % (v.error or 'error'))


def _hold(tx, actor, missions, m, row, reason):
    """Block the mission for a verification that waits on the user; a mission
    not EXECUTING is left where it is (the verification still waits)."""
    tx.update(entities.Verification, row.entity.id, {'holds_mission': True}, actor=actor)
    _event(tx, 'verification.state_changed', Ref('verification', row.entity.id), actor, m,
           {'from': row.entity.state, 'to': row.entity.state, 'reason': reason,
            'holds_mission': True})
    if m.state == 'EXECUTING':
        missions.fire(tx, actor=actor, mission_id=m.id, trigger='block', reason=reason)
    return {'verification_id': row.entity.id, 'held': True}


# ── human decisions (§17) ───────────────────────────────────────────────────

class Decisions:
    """The user's P13 commands, bound to the runtime's `Missions` (a request's
    arguments are stored with its idempotency key, and an object is not one —
    the pattern of `Authorization.decide`)."""

    def __init__(self, missions):
        self.missions = missions

    def decide(self, tx, *, actor, verification_id, decision, note=''):
        return decide(tx, actor=actor, missions=self.missions,
                      verification_id=verification_id, decision=decision, note=note)

    def review(self, tx, *, actor, mission_id, verdict, note='', requirements_met=(),
               requirements_missing=()):
        return record_review(tx, actor=actor, missions=self.missions, mission_id=mission_id,
                             verdict=verdict, reviewer='user', user=True, summary=note or '',
                             requirements_met=list(requirements_met or ()),
                             requirements_missing=list(requirements_missing or ()))


def decide(tx, *, actor, missions, verification_id, decision, note=''):
    """A user device accepts or rejects a verification AWAITING_HUMAN; the task
    or mission it held moves, and a mission blocked only by it resumes."""
    if actor.kind != 'user_device':
        raise Refused('only a user device decides what waits on a human')
    if decision not in ('accept', 'reject'):
        raise ValueError('a decision is accept or reject')
    row = lifecycle.load(tx, entities.Verification, verification_id)
    v = row.entity
    if v.state != 'AWAITING_HUMAN':
        from .world import Conflict
        raise Conflict('verification %s is %s: nothing waits on a decision'
                       % (v.id, v.state), {'verification_id': v.id, 'state': v.state})
    state = 'PASSED' if decision == 'accept' else 'FAILED'
    crit = tuple(dict(c, result='satisfied' if state == 'PASSED' else 'failed')
                 for c in v.criteria)
    _fire(tx, entities.Verification, v.id,
          'user_accepts' if decision == 'accept' else 'user_rejects', actor,
          'decided by the user' + (': %s' % note if note else ''),
          fields={'decided_by': actor.id, 'note': note or None, 'criteria': crit,
                  'holds_mission': False})
    if v.subject.kind == 'task':
        t = lifecycle.load(tx, entities.Task, v.subject.id).entity
        settle_task(tx, actor=actor, task_id=t.id)
        m = _mission(tx, t.mission_id)
    else:
        m = _mission(tx, v.subject.id)
    resumed = False
    if m.state == 'BLOCKED' and not _still_held(tx, m):
        missions.resume(tx, actor=actor, mission_id=m.id,
                        reason='verification %s decided: %s' % (v.id, decision))
        resumed = True
    return {'verification_id': v.id, 'state': state, 'resumed': resumed}


def _still_held(tx, m):
    """Does anything P13 recorded still hold mission *m*: a verification
    awaiting a human (task rows mark it; mission criteria of the plan in force
    at the current head count by state), or a merge conflict?"""
    plan = active_plan(tx.conn, m.id)
    if plan is None:
        return False
    for r in tx.where(entities.Verification, plan_id=plan.entity.id):
        v = r.entity
        if v.holds_mission and v.state in ('AWAITING_HUMAN', 'ERROR'):
            return True
        if (v.subject == Ref('mission', m.id) and v.state == 'AWAITING_HUMAN'
                and v.revision == m.integration_head):
            return True
    return any(r.entity.integration_state == 'CONFLICT'
               for r in tx.where(entities.Task, plan_id=plan.entity.id))


# ── boot (§19) ──────────────────────────────────────────────────────────────

def sweep(tx, *, actor):
    """A verification RUNNING now was running under a Core that died: its
    evidence was never recorded, so it is `verifier_crashed` and retried like
    any error — re-observed, never replayed."""
    out = []
    for r in tx.where(entities.Verification):
        if r.entity.state != 'RUNNING':
            continue
        _fire(tx, entities.Verification, r.entity.id, 'verifier_crashed', actor,
              'Core restarted while it ran', fields={'errors': r.entity.errors + 1,
                                                     'error': 'core_restarted'})
        out.append(r.entity.id)
    return out


# ── integration (§12) ───────────────────────────────────────────────────────

def _integration_facts(tx, t, revision):
    passed = [r.entity for r in tx.where(entities.Verification, plan_id=t.plan_id)
              if r.entity.subject == Ref('task', t.id) and r.entity.state == 'PASSED'
              and r.entity.revision is not None]
    # positional (task state, plan in force, verified revision, revision): only
    # Tx.transition names a state field (test_guards)
    return guards.IntegrationFacts(t.state, _in_force(tx, t),
                                   passed[-1].revision if passed else None, revision)


def begin_merge(tx, *, actor, task_id, revision):
    """PENDING -> MERGING, guarded: only the revision a passing verification of
    the plan in force checked may be merged (D10)."""
    t = lifecycle.load(tx, entities.Task, task_id).entity
    facts = _integration_facts(tx, t, revision)
    _fire(tx, entities.Task, t.id, 'task_verified', actor, 'merging %s into %s'
          % (revision, _mission_branch(t.mission_id)), machine='integration', facts=facts)
    return {'task_id': t.id, 'integration_state': 'MERGING'}


def record_merge(tx, *, actor, missions, task_id, outcome, head=None, base=None, conflicts=()):
    """MERGING -> MERGED (the mission branch head moves in the same transaction)
    or CONFLICT (the mission waits for the user, §12.5)."""
    t = lifecycle.load(tx, entities.Task, task_id).entity
    m = _mission(tx, t.mission_id)
    if t.integration_state != 'MERGING':
        raise Refused('task %s is not merging (%s)' % (t.id, t.integration_state))
    if outcome == 'merged':
        _fire(tx, entities.Task, t.id, 'fast_forward_or_clean', actor,
              'merged into %s at %s' % (_mission_branch(m.id), head), machine='integration',
              fields={'merged_revision': head, 'conflicts': ()})
        note_integration_head(tx, actor=actor, mission_id=m.id, head=head,
                              base=m.integration_base or base)
        return {'task_id': t.id, 'integration_state': 'MERGED', 'head': head}
    if outcome != 'conflict':
        raise ValueError('a merge is merged or conflict')
    paths = tuple(conflicts)
    reason = "task %s's result conflicts with %s in %s" % (
        t.key, _mission_branch(m.id), ', '.join(paths) or 'unknown paths')
    _fire(tx, entities.Task, t.id, 'conflict', actor, reason, machine='integration',
          fields={'conflicts': paths})
    if m.state == 'EXECUTING':
        missions.fire(tx, actor=actor, mission_id=m.id, trigger='block', reason=reason)
    return {'task_id': t.id, 'integration_state': 'CONFLICT', 'conflicts': list(paths)}


def retry_merge(tx, *, actor, task_id):
    """CONFLICT -> PENDING when the mission was resumed after the user resolved
    it on the mission branch (`conflict_task_done`, D13)."""
    t = lifecycle.load(tx, entities.Task, task_id).entity
    _fire(tx, entities.Task, t.id, 'conflict_task_done', actor,
          'the mission was resumed: merging again', machine='integration')
    return {'task_id': t.id, 'integration_state': 'PENDING'}


def abandon_integration(tx, *, actor, task_id, reason):
    """CONFLICT -> ABANDONED: the task's result stays out of the mission branch;
    mission verification judges the branch without it (§12.5)."""
    if actor.kind != 'user_device':
        raise Refused('only a user device abandons a merge')
    t = lifecycle.load(tx, entities.Task, task_id).entity
    _fire(tx, entities.Task, t.id, 'user_abandons', actor,
          reason or 'abandoned by the user', machine='integration')
    return {'task_id': t.id, 'integration_state': 'ABANDONED'}


def note_integration_head(tx, *, actor, mission_id, head, base=None):
    """The mission branch head, recorded: every mission verification of another
    revision is stale from now on (§11)."""
    m = _mission(tx, mission_id)
    if (m.integration_head, m.integration_base) == (head, base or m.integration_base):
        return {'changed': False}
    fields = {'integration_head': head}
    if base and not m.integration_base:
        fields['integration_base'] = base
    tx.update(entities.Mission, m.id, fields, actor=actor)
    _event(tx, 'mission.updated', Ref('mission', m.id), actor, m,
           {'fields': sorted(fields), 'integration_head': head,
            'integration_base': fields.get('integration_base', m.integration_base)})
    return {'changed': True}


# ── review (§7, §14) ────────────────────────────────────────────────────────

def record_review(tx, *, actor, missions, mission_id, verdict, reviewer, independent=False,
                  user=False, route_decision_id=None, reviewer_resource=None, summary='',
                  **found):
    """A review of a REVIEWING mission and the mission's response: `accept` ->
    COMPLETED (the P3 `accept`), `changes_requested` -> REPLANNING, `reject`
    waits for the user. A user's review is `user_reviews`, always independent."""
    m = lifecycle.load(tx, entities.Mission, mission_id)
    if m.entity.state != 'REVIEWING':
        raise lifecycle.IllegalTrigger('mission', m.entity.state, 'review',
                                       'a review needs REVIEWING')
    if verdict not in _REVIEW:
        raise ValueError('a review verdict is accept, changes_requested or reject')
    if user and actor.kind != 'user_device':
        raise Refused('a user review is recorded by a user device')
    unknown = set(found) - set(entities.REVIEW_LISTS)
    if unknown:
        raise ValueError('unknown review fields: %s' % sorted(unknown))
    r = entities.Review(
        id=ids.new_id('review'), mission_id=mission_id, reviewer='user' if user else reviewer,
        independent=True if user else bool(independent),
        plan_id=active_plan(tx.conn, mission_id).entity.id,
        summary=summary or '', route_decision_id=route_decision_id,
        reviewer_resource=reviewer_resource, principal_id=actor.id if user else None,
        **{k: tuple(v) for k, v in found.items()})
    tx.insert(r, actor=actor)
    _event(tx, 'review.requested', Ref('review', r.id), actor, m.entity,
           {'mission_id': mission_id, 'plan_id': r.plan_id, 'independent': r.independent,
            'reviewer': r.reviewer, 'reviewer_resource': reviewer_resource})
    _fire(tx, entities.Review, r.id, 'user_reviews' if user else 'start', actor,
          'reviewer %s' % r.reviewer)
    _fire(tx, entities.Review, r.id, _REVIEW[verdict], actor,
          'reviewer %s: %s' % (r.reviewer, verdict), fields={'verdict': verdict})
    reason = 'review %s: %s' % (r.id, verdict)
    out = None
    if verdict == 'accept':
        out = missions.accept(tx, actor=actor, mission_id=mission_id, reason=reason)
    elif verdict == 'changes_requested':
        out = missions.request_changes(tx, actor=actor, mission_id=mission_id, reason=reason)
    return {'review_id': r.id, 'verdict': verdict, 'independent': r.independent,
            'mission': out}
