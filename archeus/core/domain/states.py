"""Every lifecycle, declared once (state-machines.md §0).

`TABLE` is the flat `(machine, from_state, to_state, trigger, guard_name)` list.
The Mermaid diagrams in docs/architecture/state-machines.md document it, and
tests/v1/unit/test_state_tables.py fails when a diagram edge is missing here or
an edge here is missing from the diagrams. `START`/`END` are the diagrams'
`[*]`: an edge from START names a machine's initial state, an unlabelled edge
to END marks a terminal one.

P1 declares the edges, and this table stays authoritative. P2's
`Tx.transition()` (archeus/infra/db/writer.py) is the persistence primitive and
the only thing that assigns a state: it checks the edge here, the expected
version and the reason, and commits the state, the version bump and the
`<machine>.state_changed` event together. It refuses a guarded edge unless a
`TransitionProof` (below) for that edge, row and version comes with it. P3 builds
the application-level transition on top of it — the guard functions the names
below refer to, action semantics, policy interaction, lifecycle orchestration.
"""

from dataclasses import dataclass

START = END = '[*]'


@dataclass(frozen=True)
class TransitionProof:
    """The application layer's statement that ONE edge may be taken on ONE row
    at ONE version: built after the edge's guard (if any) passed, and checked
    field by field by the persistence primitive against the row it changes.
    Generic on purpose — it names an edge of this table, never a guard's
    meaning — so the primitive can refuse an unproven guarded edge without
    knowing any machine's semantics. `guard` is the table's guard name for the
    edge (None when unguarded) and `guard_reason` why it passed."""
    entity_id: str
    version: int
    frm: str
    to: str
    trigger: str
    guard: str = None
    guard_reason: str = None

#: Machines in the order their diagrams appear in state-machines.md.
MACHINES = (
    'idea', 'mission', 'plan', 'task', 'execution', 'approval', 'verification',
    'review', 'automation', 'automation_run', 'account_health',
    'repository_inspection', 'architecture', 'knowledge_item', 'device',
    'execution_node', 'integration',
)

_S, _E = START, END

_EDGES = {
    'idea': (
        (_S, 'CAPTURED', None),
        ('CAPTURED', 'UNDERSTOOD', 'clarify'),
        ('CAPTURED', 'SCHEDULED', 'schedule'),
        ('CAPTURED', 'PARKED', 'park'),
        ('UNDERSTOOD', 'EXPLORED', 'explore'),
        ('UNDERSTOOD', 'PLANNED', 'plan'),
        ('EXPLORED', 'VALIDATED', 'validate'),
        ('EXPLORED', 'DISCARDED', 'discard'),
        ('VALIDATED', 'CONCEPT', 'conceptualise'),
        ('VALIDATED', 'PLANNED', 'plan'),
        ('CONCEPT', 'PLANNED', 'plan'),
        ('PLANNED', 'SCHEDULED', 'schedule'),
        ('PLANNED', 'IMPLEMENTING', 'promote'),
        ('SCHEDULED', 'IMPLEMENTING', 'promote'),
        ('IMPLEMENTING', 'COMPLETED', 'mission_completed'),
        ('IMPLEMENTING', 'PLANNED', 'mission_cancelled'),
        ('COMPLETED', 'LEARNED', 'learn'),
        ('PARKED', 'CAPTURED', 'revive'),
        ('DISCARDED', 'CAPTURED', 'revive'),
        ('LEARNED', _E, None),
    ),
    # No LEARNED: learning is an outbox consumer that stamps `learned_at` after
    # COMPLETED, never a state (state-machines §2).
    'mission': (
        (_S, 'CREATED', None),
        ('CREATED', 'UNDERSTANDING', 'start'),
        ('UNDERSTANDING', 'CONTEXT_GATHERING', 'understood'),
        ('UNDERSTANDING', 'BLOCKED', 'needs_clarification'),
        ('CONTEXT_GATHERING', 'REASONING', 'context_ready'),
        ('REASONING', 'PLANNING', 'reasoned'),
        ('REASONING', 'BLOCKED', 'challenge_raised'),
        # a policy DENY of the plan (P9, p9-design-gate D11): never a challenge
        ('REASONING', 'BLOCKED', 'plan_denied'),
        ('PLANNING', 'APPROVAL_REQUIRED', 'plan_needs_approval'),
        ('PLANNING', 'APPROVED', 'plan_auto_approved'),
        ('PLANNING', 'CANCELLED', 'cancel'),
        ('APPROVAL_REQUIRED', 'APPROVED', 'approve'),
        ('APPROVAL_REQUIRED', 'PLANNING', 'request_changes'),
        ('APPROVAL_REQUIRED', 'CANCELLED', 'reject'),
        ('APPROVED', 'EXECUTING', 'dispatch'),
        ('EXECUTING', 'VERIFYING', 'all_tasks_done'),
        ('EXECUTING', 'BLOCKED', 'block'),
        ('EXECUTING', 'PAUSED', 'pause'),
        ('EXECUTING', 'FAILED', 'unrecoverable'),
        ('EXECUTING', 'REPLANNING', 'task_failed_retryable'),
        ('BLOCKED', 'RESUMED', 'unblock'),
        ('PAUSED', 'RESUMED', 'resume'),
        ('RESUMED', 'EXECUTING', 'redispatch'),
        ('RESUMED', 'UNDERSTANDING', 'redispatch_before_plan'),
        ('FAILED', 'REPLANNING', 'replan'),
        ('REPLANNING', 'APPROVAL_REQUIRED', 'plan_needs_approval'),
        ('REPLANNING', 'APPROVED', 'plan_auto_approved'),
        ('REPLANNING', 'BLOCKED', 'replan_budget_exhausted'),
        ('VERIFYING', 'REVIEWING', 'verified'),
        ('VERIFYING', 'REPLANNING', 'verification_failed'),
        ('VERIFYING', 'BLOCKED', 'awaiting_human_acceptance'),
        ('REVIEWING', 'COMPLETED', 'accepted'),
        ('REVIEWING', 'REPLANNING', 'changes_requested'),
        ('CREATED', 'CANCELLED', 'cancel'),
        ('BLOCKED', 'CANCELLED', 'cancel'),
        ('PAUSED', 'CANCELLED', 'cancel'),
        ('FAILED', 'CANCELLED', 'cancel'),
        ('COMPLETED', _E, None),
        ('CANCELLED', _E, None),
    ),
    # One row is one immutable PlanVersion (p8-design-gate D1, D2). DRAFT is
    # transient: a version is inserted and takes `ready` in the same
    # transaction. PROPOSED = structurally valid and ready for the POLICY stage,
    # never approved or executable; `approved` and `rejected` are P9's.
    'plan': (
        (_S, 'DRAFT', None),
        ('DRAFT', 'PROPOSED', 'ready'),
        ('PROPOSED', 'APPROVED', 'approved'),
        ('PROPOSED', 'REJECTED', 'rejected'),
        ('PROPOSED', 'SUPERSEDED', 'superseded'),
        ('APPROVED', 'SUPERSEDED', 'superseded'),
        ('SUPERSEDED', _E, None),
        ('REJECTED', _E, None),
    ),
    'task': (
        (_S, 'PENDING', None),
        ('PENDING', 'READY', 'deps_satisfied'),
        ('PENDING', 'SKIPPED', 'skip'),
        ('READY', 'ROUTING', 'dispatch'),
        ('ROUTING', 'RUNNING', 'routed'),
        ('ROUTING', 'BLOCKED', 'no_eligible_resource'),
        ('ROUTING', 'AWAITING_APPROVAL', 'route_needs_approval'),
        ('RUNNING', 'AWAITING_APPROVAL', 'action_needs_approval'),
        ('AWAITING_APPROVAL', 'READY', 'approved'),
        ('AWAITING_APPROVAL', 'BLOCKED', 'rejected'),
        ('RUNNING', 'PAUSED', 'pause'),
        ('PAUSED', 'READY', 'resume'),
        ('RUNNING', 'VERIFYING', 'execution_succeeded'),
        ('RUNNING', 'READY', 'execution_failed_retry'),
        ('RUNNING', 'FAILED', 'execution_failed_final'),
        ('RUNNING', 'BLOCKED', 'merge_conflict'),
        ('VERIFYING', 'SUCCEEDED', 'checks_passed'),
        ('VERIFYING', 'READY', 'checks_failed_retry'),
        ('VERIFYING', 'FAILED', 'checks_failed_final'),
        ('BLOCKED', 'READY', 'unblock'),
        ('PENDING', 'CANCELLED', 'cancel'),
        ('READY', 'CANCELLED', 'cancel'),
        ('BLOCKED', 'CANCELLED', 'cancel'),
        ('PAUSED', 'CANCELLED', 'cancel'),
        ('SUCCEEDED', _E, None),
        ('FAILED', _E, None),
        ('SKIPPED', _E, None),
        ('CANCELLED', _E, None),
    ),
    'execution': (
        (_S, 'INTENT', None),
        ('INTENT', 'STARTING', 'spawn'),
        ('INTENT', 'ABANDONED', 'spawn_failed'),
        ('INTENT', 'LOST', 'spawn_unconfirmed'),
        ('STARTING', 'RUNNING', 'first_output'),
        ('STARTING', 'LOST', 'start_timeout'),
        ('RUNNING', 'AWAITING_APPROVAL', 'hook_asked'),
        ('AWAITING_APPROVAL', 'STARTING', 'resume_approved'),
        ('AWAITING_APPROVAL', 'ENDED_REJECTED', 'rejected'),
        ('RUNNING', 'PAUSING', 'pause_requested'),
        ('PAUSING', 'PAUSED', 'halted_at_boundary'),
        ('PAUSING', 'STOPPING', 'pause_timeout'),
        ('PAUSED', 'STARTING', 'resume'),
        ('RUNNING', 'HANDING_OFF', 'pressure_or_account_change'),
        ('HANDING_OFF', 'ENDED_HANDOFF', 'checkpoint_written'),
        ('RUNNING', 'STOPPING', 'stop'),
        ('STOPPING', 'ENDED_KILLED', 'process_gone'),
        ('RUNNING', 'ENDED_OK', 'exited_success'),
        ('RUNNING', 'ENDED_ERROR', 'exited_error'),
        ('RUNNING', 'LOST', 'heartbeat_missing'),
        ('LOST', 'RUNNING', 'adopted'),
        ('LOST', 'ENDED_KILLED', 'reconciled_kill'),
        ('ABANDONED', _E, None),
        ('ENDED_OK', _E, None),
        ('ENDED_ERROR', _E, None),
        ('ENDED_KILLED', _E, None),
        ('ENDED_HANDOFF', _E, None),
        ('ENDED_REJECTED', _E, None),
    ),
    'approval': (
        (_S, 'PENDING', None),
        ('PENDING', 'APPROVED', 'approve'),
        ('PENDING', 'REJECTED', 'reject'),
        ('PENDING', 'EXPIRED', 'ttl_elapsed'),
        ('PENDING', 'SUPERSEDED', 'plan_replaced'),
        ('APPROVED', 'CONSUMED', 'action_executed'),
        ('APPROVED', 'EXPIRED', 'ttl_elapsed'),
        ('APPROVED', 'SUPERSEDED', 'plan_replaced'),
        ('REJECTED', _E, None),
        ('EXPIRED', _E, None),
        ('SUPERSEDED', _E, None),
        ('CONSUMED', _E, None),
    ),
    'verification': (
        (_S, 'PENDING', None),
        ('PENDING', 'RUNNING', 'start'),
        ('RUNNING', 'PASSED', 'all_checks_pass'),
        ('RUNNING', 'FAILED', 'a_check_fails'),
        ('RUNNING', 'ERROR', 'verifier_crashed'),
        ('PENDING', 'AWAITING_HUMAN', 'generic_verifier'),
        ('AWAITING_HUMAN', 'PASSED', 'user_accepts'),
        ('AWAITING_HUMAN', 'FAILED', 'user_rejects'),
        ('ERROR', 'PENDING', 'retry'),
        ('PASSED', _E, None),
        ('FAILED', _E, None),
    ),
    'review': (
        (_S, 'PENDING', None),
        ('PENDING', 'IN_REVIEW', 'start'),
        ('IN_REVIEW', 'ACCEPTED', 'verdict_accept'),
        ('IN_REVIEW', 'CHANGES_REQUESTED', 'verdict_changes'),
        ('IN_REVIEW', 'REJECTED', 'verdict_reject'),
        ('PENDING', 'IN_REVIEW', 'user_reviews'),
        ('ACCEPTED', _E, None),
        ('CHANGES_REQUESTED', _E, None),
        ('REJECTED', _E, None),
    ),
    'automation': (
        (_S, 'DRAFT', None),
        ('DRAFT', 'PENDING_APPROVAL', 'enable_requested'),
        ('PENDING_APPROVAL', 'ENABLED', 'approve'),
        ('PENDING_APPROVAL', 'DRAFT', 'reject'),
        ('DRAFT', 'ENABLED', 'enable_within_policy'),
        ('ENABLED', 'DISABLED', 'disable'),
        ('DISABLED', 'ENABLED', 'enable_within_policy'),
        ('ENABLED', 'SUSPENDED', 'loop_guard_tripped'),
        ('SUSPENDED', 'ENABLED', 'user_reenables'),
        ('ENABLED', 'ARCHIVED', 'archive'),
        ('DISABLED', 'ARCHIVED', 'archive'),
        ('ARCHIVED', _E, None),
    ),
    'automation_run': (
        (_S, 'CLAIMED', None),
        ('CLAIMED', 'SKIPPED', 'condition_false'),
        ('CLAIMED', 'SKIPPED', 'rate_limited'),
        ('CLAIMED', 'ESCALATED', 'depth_exceeded'),
        ('CLAIMED', 'POLICY_CHECK', 'conditions_met'),
        ('POLICY_CHECK', 'SKIPPED', 'denied'),
        ('POLICY_CHECK', 'ESCALATED', 'asks'),
        ('POLICY_CHECK', 'MISSION_CREATED', 'allowed'),
        ('MISSION_CREATED', 'SUCCEEDED', 'mission_completed'),
        ('MISSION_CREATED', 'FAILED', 'mission_failed_or_cancelled'),
        ('SKIPPED', _E, None),
        ('ESCALATED', _E, None),
        ('SUCCEEDED', _E, None),
        ('FAILED', _E, None),
    ),
    'account_health': (
        (_S, 'UNVERIFIED', None),
        ('UNVERIFIED', 'AVAILABLE', 'auth_ok'),
        ('UNVERIFIED', 'UNAUTHENTICATED', 'auth_failed'),
        ('AVAILABLE', 'CONSTRAINED', 'near_ceiling'),
        ('CONSTRAINED', 'AVAILABLE', 'usage_dropped'),
        ('AVAILABLE', 'LIMITED', 'window_exhausted'),
        ('CONSTRAINED', 'LIMITED', 'window_exhausted'),
        ('LIMITED', 'AVAILABLE', 'reset_time_passed'),
        ('AVAILABLE', 'DEGRADED', 'error_storm'),
        ('CONSTRAINED', 'DEGRADED', 'error_storm'),
        ('DEGRADED', 'AVAILABLE', 'probe_ok'),
        ('DEGRADED', 'OPEN', 'errors_persist'),
        ('OPEN', 'DEGRADED', 'cooldown_elapsed'),
        ('AVAILABLE', 'UNAUTHENTICATED', 'auth_failed'),
        ('UNAUTHENTICATED', 'UNVERIFIED', 'relogin'),
        ('AVAILABLE', 'DISABLED', 'user_disables'),
        ('DISABLED', 'UNVERIFIED', 'user_enables'),
    ),
    'repository_inspection': (
        (_S, 'SCHEDULED', None),
        ('SCHEDULED', 'RUNNING', 'start'),
        ('RUNNING', 'COMPLETED', 'inspected'),
        ('RUNNING', 'FAILED', 'error'),
        ('FAILED', 'SCHEDULED', 'retry'),
        ('COMPLETED', _E, None),
    ),
    # Repository.architecture_state
    'architecture': (
        (_S, 'UNKNOWN', None),
        ('UNKNOWN', 'CONSISTENT', 'first_inspection'),
        ('UNKNOWN', 'DRIFTED', 'first_inspection_drift'),
        ('CONSISTENT', 'STALE', 'revision_moved'),
        ('DRIFTED', 'STALE', 'revision_moved'),
        ('CONSISTENT', 'STALE', 'constraints_changed'),
        ('DRIFTED', 'STALE', 'constraints_changed'),
        ('STALE', 'CONSISTENT', 'reinspected_no_drift'),
        ('STALE', 'DRIFTED', 'reinspected_drift'),
        ('DRIFTED', 'CONSISTENT', 'architecture_updated'),
        ('DRIFTED', 'CONSISTENT', 'drift_accepted_as_change'),
        ('DRIFTED', 'DRIFTED', 'drift_rejected_mission_created'),
    ),
    'knowledge_item': (
        (_S, 'CANDIDATE', None),
        ('CANDIDATE', 'CONFIRMED', 'confirm'),
        ('CANDIDATE', 'RETRACTED', 'reject'),
        ('CONFIRMED', 'SUPERSEDED', 'superseded'),
        ('CONFIRMED', 'RETRACTED', 'retract'),
        ('CONFIRMED', 'EXPIRED', 'validity_ended'),
        ('EXPIRED', 'CONFIRMED', 'revalidated'),
        ('SUPERSEDED', _E, None),
        ('RETRACTED', _E, None),
    ),
    'device': (
        (_S, 'PAIRING', None),
        ('PAIRING', 'ACTIVE', 'code_redeemed'),
        ('PAIRING', _E, 'code_expired'),      # the pairing row simply ends
        ('ACTIVE', 'REVOKED', 'revoke'),
        ('REVOKED', _E, None),
    ),
    'execution_node': (
        (_S, 'ONLINE', None),
        ('ONLINE', 'GRACE', 'heartbeat_missed'),
        ('GRACE', 'ONLINE', 'heartbeat'),
        ('GRACE', 'OFFLINE', 'grace_elapsed'),
        ('OFFLINE', 'ONLINE', 'reconnect'),
        ('ONLINE', 'RETIRED', 'retire'),
        ('OFFLINE', 'RETIRED', 'retire'),
    ),
    # Task.integration_state: a second lifecycle of a task, not an entity
    # (domain-model §7.3); the column arrives with the merge-back in P13
    'integration': (
        (_S, 'PENDING', None),
        ('PENDING', 'MERGING', 'task_verified'),
        ('MERGING', 'MERGED', 'fast_forward_or_clean'),
        ('MERGING', 'CONFLICT', 'conflict'),
        ('CONFLICT', 'PENDING', 'conflict_task_done'),
        ('CONFLICT', 'ABANDONED', 'user_abandons'),
        ('MERGED', _E, None),
        ('ABANDONED', _E, None),
    ),
}

#: Triggers whose edge is guarded (state-machines §2 guard table, §5 approve).
#: Each is a pure function of the entity plus a read-only snapshot in guards.py.
_GUARDED = {
    'mission': {'plan_auto_approved', 'plan_needs_approval', 'all_tasks_done', 'verified',
                'awaiting_human_acceptance', 'replan_budget_exhausted',
                'task_failed_retryable', 'unrecoverable', 'verification_failed',
                'redispatch', 'accepted',
                # P9: blocked only by a recorded denial (p9-design-gate D11)
                'plan_denied'},
    # a plan version is ready only as far as Core's validator allows (P8)
    'plan': {'ready'},
    'approval': {'approve'},
    # an assessment is taken only as far as the findings it records allow
    'architecture': {'first_inspection', 'first_inspection_drift', 'reinspected_no_drift',
                     'reinspected_drift'},
}

TABLE = tuple(
    (m, frm, to, trig, trig if trig in _GUARDED.get(m, ()) else None)
    for m in MACHINES for frm, to, trig in _EDGES[m])

#: States of entities whose lifecycle state-machines.md does not diagram. They
#: are validated as sets; their edges are not declared yet (see the P1 report).
STATE_SETS = {
    'session': ('OPEN', 'CLOSED', 'LOST'),
    'harness': ('AVAILABLE', 'MISSING', 'MISCONFIGURED'),
}


def edges(machine):
    """(from, to, trigger, guard) rows of one machine, pseudo-states included."""
    if machine not in _EDGES:
        raise KeyError(machine)
    return [row[1:] for row in TABLE if row[0] == machine]


def states(machine):
    """Every real state of a machine (or a STATE_SETS entry), in first-seen order."""
    if machine in STATE_SETS:
        return STATE_SETS[machine]
    seen = []
    for frm, to, _t, _g in edges(machine):
        for s in (frm, to):
            if s != START and s not in seen:
                seen.append(s)
    return tuple(seen)


def initial(machine):
    """The state a new row of this machine starts in."""
    if machine in STATE_SETS:
        return STATE_SETS[machine][0]
    (first,) = [to for frm, to, _t, _g in edges(machine) if frm == START]
    return first


def terminal(machine):
    """States that end the machine (`X --> [*]` with no trigger)."""
    return frozenset(frm for frm, to, t, _g in edges(machine) if to == END and t is None)


def targets(machine, from_state):
    """{trigger: to_state} available from *from_state*."""
    return {t: to for frm, to, t, _g in edges(machine)
            if frm == from_state and t is not None}
