"""The guards of the state machines (state-machines §2 guard table, §5 approve).

A guard is a PURE function of the entity and a read-only snapshot (its
*facts*): no I/O, no clock, no randomness, no model call — the same inputs give
the same `GuardResult` every time. Whatever a guard needs from outside — the
plan's tasks, verification results, policy decisions — is gathered by the
application layer into the facts BEFORE the guard runs, inside the transaction
that will commit the move (archeus/core/application/lifecycle.py), so a guard
is never judged against a state other than the one being changed.

Guards fail closed: a fact that is unknown (no active plan, no success
criteria, no cost band yet) is a reason to refuse, never a reason to pass.

`GUARDS` holds exactly the edges `states.TABLE` marks as guarded; a test keeps
the two in step.
"""

from dataclasses import dataclass

#: Policy decisions that let a plan through without asking (state-machines §2).
AUTO_OK = ('ALLOW', 'ALLOW_WITHIN_BOUNDARY')
#: Failure classes a replan cannot fix (`task_failed_retryable`).
NOT_RETRYABLE = ('policy', 'credential', 'human')
#: States with an approved plan in force: a mission held from one of them may
#: go straight back to EXECUTING (`redispatch`); from anywhere else it may not.
PLAN_IN_FORCE = ('EXECUTING', 'VERIFYING')


@dataclass(frozen=True)
class GuardResult:
    """One evaluation of one guard against one row at one version. A passing
    one becomes a generic `states.TransitionProof` (application/lifecycle.py),
    which is all the persistence primitive ever sees — never this type."""
    guard: str
    passed: bool
    reason: str
    entity_id: str = None
    version: int = None


@dataclass(frozen=True)
class TaskFact:
    key: str
    kind: str
    state: str
    action_classes: tuple = ()
    attempts: int = 0
    max_attempts: int = 2
    failure_class: str = None       # set when the task FAILED


@dataclass(frozen=True)
class CriterionFact:
    """A mission success criterion (domain-model §7.1) and the state of the
    verification that checks it (None: not verified yet)."""
    check: str                      # automatic | human
    verification: str = None


@dataclass(frozen=True)
class MissionFacts:
    """The snapshot the mission guards read. `plan_version` None means the
    mission has no active plan. `policy` is filled by the application layer
    from the Policy port: one `(task_key, action_class, decision)` per action
    class of every task. `declared_by` is the kind of the principal asking."""
    plan_version: int = None
    tasks: tuple = ()
    criteria: tuple = ()
    cost_within_ceiling: bool = None    # None: no cost band estimated
    missing_capability: bool = False
    policy: tuple = ()
    declared_by: str = None
    review: str = None                  # state of the latest review of the plan in force


@dataclass(frozen=True)
class PlanFacts:
    """What the plan `ready` guard reads (P8): the problems Core's validator
    found in this version (empty: none) and the digest of its content as
    recomputed from the row, which must equal the digest recorded with it."""
    problems: tuple = ()
    digest: str = None


@dataclass(frozen=True)
class ApprovalFacts:
    """What the `approve` guard reads: the deciding principal and the command."""
    actor_kind: str
    actor_scopes: tuple
    action_hash: str
    step_up_valid: bool = False


def _r(name, passed, reason):
    return GuardResult(name, bool(passed), reason)


# ── mission (state-machines §2) ─────────────────────────────────────────────

def _already_decided(mission, f):
    """The plan in force was decided before (the plan a REPLANNING mission is
    replacing, or one sent back with request_changes): it is never decided again."""
    return (mission.decided_plan_version is not None
            and f.plan_version <= mission.decided_plan_version)


def _stale(name, f):
    return _r(name, False, 'plan v%d was already decided; the mission needs a new plan'
              % f.plan_version)


def plan_auto_approved(mission, f):
    if f.plan_version is None or not f.tasks:
        return _r('plan_auto_approved', False, 'no active plan with tasks')
    if _already_decided(mission, f):
        return _stale('plan_auto_approved', f)
    asked = [(k, c, d) for k, c, d in f.policy if d not in AUTO_OK]
    if asked:
        k, c, d = asked[0]
        return _r('plan_auto_approved', False, 'policy says %s for %s on task %s' % (d, c, k))
    if f.cost_within_ceiling is not True:
        return _r('plan_auto_approved', False,
                  'the estimated cost band is not under the auto-approve ceiling'
                  if f.cost_within_ceiling is False else 'no estimated cost band')
    return _r('plan_auto_approved', True,
              'every action class is allowed and the cost band is under the ceiling')


def plan_needs_approval(mission, f):
    """A new plan with something a human must answer: an ASK, or a cost band
    that is not (known to be) under the ceiling. A DENY is not a question — no
    approval can make a denied action permitted."""
    if f.plan_version is None or not f.tasks:
        return _r('plan_needs_approval', False, 'no active plan with tasks')
    denied = [(k, c) for k, c, d in f.policy if d == 'DENY']
    if denied:
        return _r('plan_needs_approval', False,
                  'policy denies %s on task %s: not a question for approval' % denied[0][::-1])
    if _already_decided(mission, f):
        return _stale('plan_needs_approval', f)
    asked = [(k, c, d) for k, c, d in f.policy if d not in AUTO_OK]
    if asked:
        k, c, d = asked[0]
        return _r('plan_needs_approval', True, 'policy says %s for %s on task %s' % (d, c, k))
    if f.cost_within_ceiling is not True:
        return _r('plan_needs_approval', True,
                  'the estimated cost band is not under the auto-approve ceiling'
                  if f.cost_within_ceiling is False else 'no estimated cost band')
    return _r('plan_needs_approval', False,
              'nothing to ask: every action class is allowed and the cost band is under '
              'the ceiling')


def all_tasks_done(mission, f):
    if f.plan_version is None or not f.tasks:
        return _r('all_tasks_done', False, 'no active plan with tasks')
    open_ = [t.key for t in f.tasks
             if t.kind != 'human' and t.state not in ('SUCCEEDED', 'SKIPPED')]
    if open_:
        return _r('all_tasks_done', False, 'tasks not done: %s' % ', '.join(open_))
    return _r('all_tasks_done', True, 'every non-human task succeeded or was skipped')


def verified(mission, f):
    if not f.criteria:
        return _r('verified', False, 'no success criteria to verify')
    auto = [c for c in f.criteria if c.check == 'automatic']
    if not auto:
        return _r('verified', False, 'no automatic success criterion')
    pending = [c for c in auto if c.verification != 'PASSED']
    if pending:
        return _r('verified', False, '%d automatic criteria have not passed' % len(pending))
    if any(c.check == 'human' and c.verification != 'PASSED' for c in f.criteria):
        return _r('verified', False, 'a human criterion is still open')
    return _r('verified', True, 'every automatic criterion passed')


def awaiting_human_acceptance(mission, f):
    if any(c.check == 'human' and c.verification != 'PASSED' for c in f.criteria):
        return _r('awaiting_human_acceptance', True, 'waiting for your acceptance')
    return _r('awaiting_human_acceptance', False, 'no human criterion is open')


def replan_budget_exhausted(mission, f):
    if f.plan_version is None:
        return _r('replan_budget_exhausted', False, 'no active plan')
    used = f.plan_version - 1
    return _r('replan_budget_exhausted', used >= mission.max_replans,
              '%d of %d replans used' % (used, mission.max_replans))


def task_failed_retryable(mission, f):
    for t in f.tasks:
        if (t.state == 'FAILED' and t.attempts >= t.max_attempts
                and t.failure_class not in NOT_RETRYABLE):
            return _r('task_failed_retryable', True,
                      'task %s failed after %d attempts (%s)'
                      % (t.key, t.attempts, t.failure_class or 'unclassified'))
    return _r('task_failed_retryable', False, 'no task failed retryably')


def verification_failed(mission, f):
    failed = [c for c in f.criteria if c.check == 'automatic' and c.verification == 'FAILED']
    if failed:
        return _r('verification_failed', True, 'an automatic criterion failed')
    return _r('verification_failed', False, 'no automatic criterion failed')


def redispatch(mission, f):
    if mission.held_from in PLAN_IN_FORCE:
        return _r('redispatch', True, 'held from %s with an approved plan in force'
                  % mission.held_from)
    return _r('redispatch', False, 'held from %s: no approved plan is in force; the mission '
              'starts over (redispatch_before_plan)' % mission.held_from)


def accepted(mission, f):
    if f.review == 'ACCEPTED':
        return _r('accepted', True, 'the latest review of the plan in force accepts it')
    return _r('accepted', False, 'no accepting review of the plan in force'
              + ('' if f.review is None else ' (the latest is %s)' % f.review))


def unrecoverable(mission, f):
    denied = [(k, c) for k, c, d in f.policy if d == 'DENY']
    if denied:
        return _r('unrecoverable', True, 'policy denies %s on task %s' % denied[0][::-1])
    if f.missing_capability:
        return _r('unrecoverable', True, 'a required capability has no resource')
    if f.declared_by == 'user_device':
        return _r('unrecoverable', True, 'declared failed by the user')
    return _r('unrecoverable', False, 'nothing makes the mission unrecoverable')


# ── plan (state-machines §2.1, P8) ──────────────────────────────────────────

def ready(plan, f):
    """Structurally valid and ready for the policy stage — never approved."""
    if f.problems:
        return _r('ready', False, 'the plan is not valid: %s' % '; '.join(f.problems[:5]))
    if not plan.digest or plan.digest != f.digest:
        return _r('ready', False, 'the plan content does not match its recorded digest')
    return _r('ready', True, 'Core validated the plan; it is ready for the policy stage')


# ── approval (state-machines §5) ────────────────────────────────────────────

def approve(approval, f):
    if f.actor_kind != 'user_device' or 'approve' not in f.actor_scopes:
        return _r('approve', False, 'only a user device with the approve scope decides')
    if f.action_hash != approval.action_hash:
        return _r('approve', False, 'the decision is for a different action')
    if approval.step_up and not f.step_up_valid:
        return _r('approve', False, 'this approval needs a valid step-up proof')
    return _r('approve', True, 'approved by a user device for this exact action')


# ── architecture (state-machines §10) ───────────────────────────────────────

@dataclass(frozen=True)
class ArchitectureFacts:
    """The assessment a repository is being moved to: the inspection it was
    evaluated on (whose repository, in which state) and whether any finding is
    `violated`. The revision recorded is that inspection's own, so it cannot
    disagree with it. Gathered from the rows inside the moving transaction."""
    inspection_repository_id: str = None
    inspection_state: str = None
    violated: bool = None

    @classmethod
    def of(cls, inspection, violated):
        return cls(inspection.repository_id, inspection.state, violated)


def _assessed(name, repo, f, drift):
    if f.inspection_repository_id != repo.id:
        return _r(name, False, 'the assessment is not of an inspection of this repository')
    if f.inspection_state != 'COMPLETED':
        return _r(name, False, 'the inspection it rests on is %s, not COMPLETED'
                  % f.inspection_state)
    if f.violated is None:
        return _r(name, False, 'no findings were evaluated')
    if f.violated != drift:
        return _r(name, False, 'a constraint is violated' if f.violated
                  else 'no constraint is violated')
    return _r(name, True, 'constraints violated' if drift else 'no constraint violated')


def first_inspection(repo, f):
    return _assessed('first_inspection', repo, f, False)


def first_inspection_drift(repo, f):
    return _assessed('first_inspection_drift', repo, f, True)


def reinspected_no_drift(repo, f):
    return _assessed('reinspected_no_drift', repo, f, False)


def reinspected_drift(repo, f):
    return _assessed('reinspected_drift', repo, f, True)


#: (machine, trigger) -> guard. Exactly the guarded edges of states.TABLE.
GUARDS = {
    ('mission', 'plan_auto_approved'): plan_auto_approved,
    ('mission', 'plan_needs_approval'): plan_needs_approval,
    ('mission', 'all_tasks_done'): all_tasks_done,
    ('mission', 'verified'): verified,
    ('mission', 'awaiting_human_acceptance'): awaiting_human_acceptance,
    ('mission', 'replan_budget_exhausted'): replan_budget_exhausted,
    ('mission', 'task_failed_retryable'): task_failed_retryable,
    ('mission', 'unrecoverable'): unrecoverable,
    ('mission', 'verification_failed'): verification_failed,
    ('mission', 'redispatch'): redispatch,
    ('mission', 'accepted'): accepted,
    ('plan', 'ready'): ready,
    ('approval', 'approve'): approve,
    ('architecture', 'first_inspection'): first_inspection,
    ('architecture', 'first_inspection_drift'): first_inspection_drift,
    ('architecture', 'reinspected_no_drift'): reinspected_no_drift,
    ('architecture', 'reinspected_drift'): reinspected_drift,
}


def evaluate(machine, trigger, entity, facts, *, version=None):
    """The guard's verdict, bound to the row it was judged on."""
    try:
        fn = GUARDS[(machine, trigger)]
    except KeyError:
        raise LookupError('%s.%s has no guard' % (machine, trigger)) from None
    r = fn(entity, facts)
    return GuardResult(r.guard, r.passed, r.reason, entity_id=entity.id, version=version)
