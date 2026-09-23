# Archeus V1 — State Machines

Status: **DECIDED**. Entities are defined in [domain-model.md](domain-model.md).

## 0. How state machines are implemented

- **One table.** `archeus/core/domain/states.py` declares every machine as a flat tuple of
  `(machine, from_state, to_state, trigger, guard_name)`. Diagrams in this document are
  documentation of that table; `tests/v1/unit/test_state_tables.py` parses the Mermaid blocks
  below and fails if a diagram edge is missing from the table or vice versa (the repo's
  "one declaration, everything derived" rule).
- **One mutator.** `transition(entity, to, *, actor, reason, cause)` validates the edge, runs the
  guard, bumps `version`, writes the row and appends the event in one transaction. Nothing else
  assigns `state`.
- **Guards are pure functions** of the entity plus a read-only snapshot. They never call a
  model or a process. A guard that needs a side effect is a bug; the side effect belongs in an
  outbox consumer reacting to the event.
- **Terminal states are terminal.** Retrying a FAILED execution creates a new Execution row;
  replanning a mission creates a new Plan version. History is never rewritten.
- **Human intervention** is modelled as triggers with `actor.kind == user_device` — the same
  edges an automation or the brain would use, so every path is audited the same way.
- Naming: states are UPPER_SNAKE; triggers are lower_snake verbs.

Policy decisions use exactly four values everywhere: `ALLOW`, `ASK`, `ALLOW_WITHIN_BOUNDARY`,
`DENY`.

---

## 1. Idea

```mermaid
stateDiagram-v2
    [*] --> CAPTURED
    CAPTURED --> UNDERSTOOD: clarify
    CAPTURED --> SCHEDULED: schedule
    CAPTURED --> PARKED: park
    UNDERSTOOD --> EXPLORED: explore
    UNDERSTOOD --> PLANNED: plan
    EXPLORED --> VALIDATED: validate
    EXPLORED --> DISCARDED: discard
    VALIDATED --> CONCEPT: conceptualise
    VALIDATED --> PLANNED: plan
    CONCEPT --> PLANNED: plan
    PLANNED --> SCHEDULED: schedule
    PLANNED --> IMPLEMENTING: promote
    SCHEDULED --> IMPLEMENTING: promote
    IMPLEMENTING --> COMPLETED: mission_completed
    IMPLEMENTING --> PLANNED: mission_cancelled
    COMPLETED --> LEARNED: learn
    PARKED --> CAPTURED: revive
    DISCARDED --> CAPTURED: revive
    LEARNED --> [*]
```

- `promote` creates a Mission (origin = idea) and links it; the idea's state then follows its
  mission (`mission_completed` / `mission_cancelled` are event-driven triggers).
- Stages may be skipped (spec §6): the diagram's shortcuts are the allowed skips; anything else
  is rejected. A reminder goes CAPTURED → SCHEDULED directly.
- `explore` runs research executions under the idea (they are tasks of a lightweight
  "exploration" mission with `kind=research`, which keeps routing/policy uniform).
- LEARNED is an **Idea** state only. Missions do not have a LEARNED state (see §2).

---

## 2. Mission

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> UNDERSTANDING: start
    UNDERSTANDING --> CONTEXT_GATHERING: understood
    UNDERSTANDING --> BLOCKED: needs_clarification
    CONTEXT_GATHERING --> REASONING: context_ready
    REASONING --> PLANNING: reasoned
    REASONING --> BLOCKED: challenge_raised
    PLANNING --> APPROVAL_REQUIRED: plan_needs_approval
    PLANNING --> APPROVED: plan_auto_approved
    PLANNING --> CANCELLED: cancel
    APPROVAL_REQUIRED --> APPROVED: approve
    APPROVAL_REQUIRED --> PLANNING: request_changes
    APPROVAL_REQUIRED --> CANCELLED: reject
    APPROVED --> EXECUTING: dispatch
    EXECUTING --> VERIFYING: all_tasks_done
    EXECUTING --> BLOCKED: block
    EXECUTING --> PAUSED: pause
    EXECUTING --> FAILED: unrecoverable
    EXECUTING --> REPLANNING: task_failed_retryable
    BLOCKED --> RESUMED: unblock
    PAUSED --> RESUMED: resume
    RESUMED --> EXECUTING: redispatch
    RESUMED --> UNDERSTANDING: redispatch_before_plan
    FAILED --> REPLANNING: replan
    REPLANNING --> APPROVAL_REQUIRED: plan_needs_approval
    REPLANNING --> APPROVED: plan_auto_approved
    REPLANNING --> BLOCKED: replan_budget_exhausted
    VERIFYING --> REVIEWING: verified
    VERIFYING --> REPLANNING: verification_failed
    VERIFYING --> BLOCKED: awaiting_human_acceptance
    REVIEWING --> COMPLETED: accepted
    REVIEWING --> REPLANNING: changes_requested
    CREATED --> CANCELLED: cancel
    BLOCKED --> CANCELLED: cancel
    PAUSED --> CANCELLED: cancel
    FAILED --> CANCELLED: cancel
    COMPLETED --> [*]
    CANCELLED --> [*]
```

| Guard / rule | Definition |
|---|---|
| `plan_auto_approved` | the policy engine evaluates every task's `action_classes` under the mission's scope chain and all are ALLOW or ALLOW_WITHIN_BOUNDARY, **and** the plan's estimated cost band is under the mission's auto-approve ceiling |
| `all_tasks_done` | every non-`human` task is SUCCEEDED or SKIPPED |
| `verified` | every mission-level success criterion with `check: automatic` has a PASSED verification |
| `awaiting_human_acceptance` | a criterion with `check: human` (GenericVerifier) is open; an Attention item is created. Mission shows `blocked_reason = "waiting for your acceptance"`, which the UI renders as *needs you*, not as failure |
| `replan_budget_exhausted` | `plan_version - 1 >= mission.max_replans` (default 2) |
| `task_failed_retryable` | a task FAILED after `max_attempts` and the failure class is not policy/credential/human |
| `unrecoverable` | policy DENY on a required action, missing capability with no resource, or user-declared failure |
| `pause` | cooperative: tasks move to PAUSED as their executions reach the next tool boundary; mission shows PAUSED immediately and "pausing N executions…" until they settle |

**Session rotation never changes mission state.** An execution handing off (Execution §4) keeps
its task RUNNING and its mission EXECUTING.

**Learning is not a state.** After COMPLETED, an outbox consumer runs the learning pass
(lessons, preferences, architecture updates) and sets `mission.learned_at`. A failed or skipped
learning pass never reopens a mission. This resolves the spec's `COMPLETED → LEARNED`.

---

## 3. Task

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> READY: deps_satisfied
    PENDING --> SKIPPED: skip
    READY --> ROUTING: dispatch
    ROUTING --> RUNNING: routed
    ROUTING --> BLOCKED: no_eligible_resource
    ROUTING --> AWAITING_APPROVAL: route_needs_approval
    RUNNING --> AWAITING_APPROVAL: action_needs_approval
    AWAITING_APPROVAL --> READY: approved
    AWAITING_APPROVAL --> BLOCKED: rejected
    RUNNING --> PAUSED: pause
    PAUSED --> READY: resume
    RUNNING --> VERIFYING: execution_succeeded
    RUNNING --> READY: execution_failed_retry
    RUNNING --> FAILED: execution_failed_final
    RUNNING --> BLOCKED: merge_conflict
    VERIFYING --> SUCCEEDED: checks_passed
    VERIFYING --> READY: checks_failed_retry
    VERIFYING --> FAILED: checks_failed_final
    BLOCKED --> READY: unblock
    PENDING --> CANCELLED: cancel
    READY --> CANCELLED: cancel
    BLOCKED --> CANCELLED: cancel
    PAUSED --> CANCELLED: cancel
    SUCCEEDED --> [*]
    FAILED --> [*]
    SKIPPED --> [*]
    CANCELLED --> [*]
```

- `approved` returns the task to READY; the resumed execution receives the one-shot allow bound
  to the approved action hash (execution-architecture §5).
- `execution_failed_retry`: attempt < `max_attempts`. A retry re-enters ROUTING, which may pick
  a different resource (affinity is kept unless the failure was resource-attributable).
- **The three-strikes rule (migration kit):** if the same failure signature (normalised error
  class + task kind) is seen three times across a mission, the task goes FAILED with
  `reason = rule_bug` and Attention gets a "this looks like a process problem" item instead of a
  fourth retry.
- `human` tasks skip ROUTING: READY → AWAITING_APPROVAL (the Attention item *is* the task).

---

## 4. Execution

```mermaid
stateDiagram-v2
    [*] --> INTENT
    INTENT --> STARTING: spawn
    INTENT --> ABANDONED: spawn_failed
    STARTING --> RUNNING: first_output
    STARTING --> LOST: start_timeout
    RUNNING --> AWAITING_APPROVAL: hook_asked
    AWAITING_APPROVAL --> STARTING: resume_approved
    AWAITING_APPROVAL --> ENDED_REJECTED: rejected
    RUNNING --> PAUSING: pause_requested
    PAUSING --> PAUSED: halted_at_boundary
    PAUSING --> STOPPING: pause_timeout
    PAUSED --> STARTING: resume
    RUNNING --> HANDING_OFF: pressure_or_account_change
    HANDING_OFF --> ENDED_HANDOFF: checkpoint_written
    RUNNING --> STOPPING: stop
    STOPPING --> ENDED_KILLED: process_gone
    RUNNING --> ENDED_OK: exited_success
    RUNNING --> ENDED_ERROR: exited_error
    RUNNING --> LOST: heartbeat_missing
    LOST --> RUNNING: adopted
    LOST --> ENDED_KILLED: reconciled_kill
    ABANDONED --> [*]
    ENDED_OK --> [*]
    ENDED_ERROR --> [*]
    ENDED_KILLED --> [*]
    ENDED_HANDOFF --> [*]
    ENDED_REJECTED --> [*]
```

- **INTENT is committed before spawn.** The row (with the planned argv, workdir and account)
  exists before any process does; the outbox consumer spawns and records `{pid, create_time}` in
  both the DB and the on-disk process registry (`~/.archeus/run/processes.jsonl`). A crash
  between commit and spawn leaves an INTENT row that boot reconciliation moves to ABANDONED.
- **Pause is cooperative** (Windows has no SIGSTOP; a headless agent cannot be frozen and
  thawed safely). `pause_requested` sets a flag the PreToolUse hook reads; at the next tool call
  the hook returns halt (`continue:false`). The adapter's `pause()` then records the provider
  session ref. `resume` starts a new process with `--resume` (same account). `pause_timeout`
  (default 120 s with no tool boundary) escalates to STOPPING and a checkpoint is derived.
- **ASK mid-execution:** hook denies the action with a reason and halts → `hook_asked` → an
  Approval row bound to the action hash. `resume_approved` resumes the provider session with a
  one-shot allow token for that hash.
- **HANDING_OFF → ENDED_HANDOFF** ends this execution; the Execution Manager creates the next
  Execution (attempt unchanged, `handoff_from` set) for the same task, fed by the checkpoint.
- **LOST** is decided by Core, never self-reported: no process-registry liveness *and* no output
  for `lost_after` (default 90 s), or node OFFLINE past grace. Reconciliation at boot either
  `adopted` (pid + create_time match a live process that is still writing its stream) or
  `reconciled_kill`.
- ENDED_OK does not mean the task succeeded — the task goes to VERIFYING.

---

## 5. Approval

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> APPROVED: approve
    PENDING --> REJECTED: reject
    PENDING --> EXPIRED: ttl_elapsed
    PENDING --> SUPERSEDED: plan_replaced
    APPROVED --> CONSUMED: action_executed
    APPROVED --> EXPIRED: ttl_elapsed
    APPROVED --> SUPERSEDED: plan_replaced
    REJECTED --> [*]
    EXPIRED --> [*]
    SUPERSEDED --> [*]
    CONSUMED --> [*]
```

- Guard on `approve`: actor is a `user_device` principal with scope `approve`; if `step_up`, the
  command carries a valid step-up proof; the command's `action_hash` equals the row's.
- `action_executed`: the policy engine, asked about an action whose hash matches an APPROVED
  approval, returns ALLOW once and consumes it. A second identical action needs a new approval
  (single-use; replay-safe).
- `plan_replaced`: a replan supersedes every approval tied to the old `plan_version`.
- Deciding commands are idempotent by `idempotency_key`: a repeated approve returns the existing
  decision.

---

## 6. Verification

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RUNNING: start
    RUNNING --> PASSED: all_checks_pass
    RUNNING --> FAILED: a_check_fails
    RUNNING --> ERROR: verifier_crashed
    PENDING --> AWAITING_HUMAN: generic_verifier
    AWAITING_HUMAN --> PASSED: user_accepts
    AWAITING_HUMAN --> FAILED: user_rejects
    ERROR --> PENDING: retry
    PASSED --> [*]
    FAILED --> [*]
```

ERROR (the verifier itself broke: missing test runner, timeout) is not FAILED (the work is
wrong). ERROR retries once, then becomes an Attention item; it never silently passes.

---

## 7. Review

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> IN_REVIEW: start
    IN_REVIEW --> ACCEPTED: verdict_accept
    IN_REVIEW --> CHANGES_REQUESTED: verdict_changes
    IN_REVIEW --> REJECTED: verdict_reject
    PENDING --> IN_REVIEW: user_reviews
    ACCEPTED --> [*]
    CHANGES_REQUESTED --> [*]
    REJECTED --> [*]
```

Review compares result vs intent, requirements, constraints and success criteria. The router
prefers a model/account different from the one that executed the work; when none is free the
review runs anyway with `independent = false`, and the mission's inspector shows it. The user
can always override a verdict (it is recorded as a second Review by `user`).

---

## 8. Automation and AutomationRun

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_APPROVAL: enable_requested
    PENDING_APPROVAL --> ENABLED: approve
    PENDING_APPROVAL --> DRAFT: reject
    DRAFT --> ENABLED: enable_within_policy
    ENABLED --> DISABLED: disable
    DISABLED --> ENABLED: enable_within_policy
    ENABLED --> SUSPENDED: loop_guard_tripped
    SUSPENDED --> ENABLED: user_reenables
    ENABLED --> ARCHIVED: archive
    DISABLED --> ARCHIVED: archive
    ARCHIVED --> [*]
```

```mermaid
stateDiagram-v2
    [*] --> CLAIMED
    CLAIMED --> SKIPPED: condition_false
    CLAIMED --> SKIPPED: rate_limited
    CLAIMED --> ESCALATED: depth_exceeded
    CLAIMED --> POLICY_CHECK: conditions_met
    POLICY_CHECK --> SKIPPED: denied
    POLICY_CHECK --> ESCALATED: asks
    POLICY_CHECK --> MISSION_CREATED: allowed
    MISSION_CREATED --> SUCCEEDED: mission_completed
    MISSION_CREATED --> FAILED: mission_failed_or_cancelled
    SKIPPED --> [*]
    ESCALATED --> [*]
    SUCCEEDED --> [*]
    FAILED --> [*]
```

- Enabling an automation whose template exercises any ASK/DENY action class needs approval
  (`enable_requested`); purely ALLOW templates enable directly.
- `depth_exceeded`: the triggering event's `cause_chain` contains ≥ `max_depth` automation runs
  → **escalate, never silently drop** (Munder Difflin's hop cap dropped messages; its docs said
  it escalated; we take the documented behaviour).
- `loop_guard_tripped`: the same automation escalated 3 times in 1 hour, or its rate limit was
  hit 3 windows in a row → SUSPENDED with an Attention item.
- Claiming uses the single writer: select-due + insert run + advance `next_run_at` happen in one
  transaction, so a schedule cannot fire twice (Vicoa's claim-and-advance, without needing
  `SKIP LOCKED` because only one writer exists).

---

## 9. Account health (resource availability + circuit breaker)

```mermaid
stateDiagram-v2
    [*] --> UNVERIFIED
    UNVERIFIED --> AVAILABLE: auth_ok
    UNVERIFIED --> UNAUTHENTICATED: auth_failed
    AVAILABLE --> CONSTRAINED: near_ceiling
    CONSTRAINED --> AVAILABLE: usage_dropped
    AVAILABLE --> LIMITED: window_exhausted
    CONSTRAINED --> LIMITED: window_exhausted
    LIMITED --> AVAILABLE: reset_time_passed
    AVAILABLE --> DEGRADED: error_storm
    CONSTRAINED --> DEGRADED: error_storm
    DEGRADED --> AVAILABLE: probe_ok
    DEGRADED --> OPEN: errors_persist
    OPEN --> DEGRADED: cooldown_elapsed
    AVAILABLE --> UNAUTHENTICATED: auth_failed
    UNAUTHENTICATED --> UNVERIFIED: relogin
    AVAILABLE --> DISABLED: user_disables
    DISABLED --> UNVERIFIED: user_enables
```

- `near_ceiling`: observed utilisation ≥ `allocation_pct − reserve_pct − 5` (router §4).
- `window_exhausted`: provider says so (`quota.is_limit_error` / `is_window_limit` on a failure,
  or usage ≥ 100%). `limited_until = resets_at`.
- DEGRADED/OPEN is a circuit breaker adapted from Munder Difflin's `breaker.ts`: move **at most
  one level per beat** (beat = 60 s), de-escalate on a successful probe. OPEN accounts are never
  routed to; DEGRADED accounts only receive work when no AVAILABLE candidate exists and policy
  permits fallback.
- The machine lives on Account; Harness has a simpler AVAILABLE/MISSING/MISCONFIGURED state set
  by discovery.

---

## 10. Repository inspection and architecture consistency

```mermaid
stateDiagram-v2
    [*] --> SCHEDULED
    SCHEDULED --> RUNNING: start
    RUNNING --> COMPLETED: inspected
    RUNNING --> FAILED: error
    FAILED --> SCHEDULED: retry
    COMPLETED --> [*]
```

```mermaid
stateDiagram-v2
    [*] --> UNKNOWN
    UNKNOWN --> CONSISTENT: first_inspection
    CONSISTENT --> STALE: revision_moved
    STALE --> CONSISTENT: reinspected_no_drift
    STALE --> DRIFTED: reinspected_drift
    DRIFTED --> CONSISTENT: architecture_updated
    DRIFTED --> CONSISTENT: drift_accepted_as_change
    DRIFTED --> DRIFTED: drift_rejected_mission_created
```

The second machine is `Repository.architecture_state`. `revision_moved`: HEAD SHA differs from
the last inspection's `revision` (checked cheaply from `.git/HEAD`, as `statusline` already
does). `reinspected_drift`: the new inspection's module graph or dependency set violates a
CONFIRMED ARCHITECTURE/DECISION item (context-and-knowledge §6). The drift proposal lands in
Attention with three actions: update the architecture knowledge, accept as intended change, or
create a mission to fix the code.

---

## 11. KnowledgeItem

```mermaid
stateDiagram-v2
    [*] --> CANDIDATE
    CANDIDATE --> CONFIRMED: confirm
    CANDIDATE --> RETRACTED: reject
    CONFIRMED --> SUPERSEDED: superseded
    CONFIRMED --> RETRACTED: retract
    CONFIRMED --> EXPIRED: validity_ended
    EXPIRED --> CONFIRMED: revalidated
    SUPERSEDED --> [*]
    RETRACTED --> [*]
```

- `confirm`: explicit user action, or automatic when `origin = explicit`, or when
  `confidence ≥ autoconfirm_threshold` and the type is FACT/ENTITY from an EXTRACTED source
  (today's `memory_lessons_autoapprove` generalised). PREFERENCE and STANDARD never
  auto-confirm from inferred sources.
- `superseded`: a newer CONFIRMED item with `supersedes_id = this` → sets `valid_until`,
  `superseded_by_id`. Superseded items are excluded from context by default and shown as history.
- Staleness is a flag (`stale = now > stale_after` or anchor revision moved), not a state; stale
  items are down-ranked and labelled in context packages rather than dropped.

---

## 12. Device and ExecutionNode

```mermaid
stateDiagram-v2
    [*] --> PAIRING
    PAIRING --> ACTIVE: code_redeemed
    PAIRING --> [*]: code_expired
    ACTIVE --> REVOKED: revoke
    REVOKED --> [*]
```

```mermaid
stateDiagram-v2
    [*] --> ONLINE
    ONLINE --> GRACE: heartbeat_missed
    GRACE --> ONLINE: heartbeat
    GRACE --> OFFLINE: grace_elapsed
    OFFLINE --> ONLINE: reconnect
    ONLINE --> RETIRED: retire
    OFFLINE --> RETIRED: retire
```

Revocation closes the device's live SSE streams in the same request. Host sleep: the local node
goes GRACE when the OS suspends (missed heartbeats); on grace elapsed its RUNNING executions
become LOST and are reconciled on wake.

---

## 13. Integration (merge-back of worktree results)

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> MERGING: task_verified
    MERGING --> MERGED: fast_forward_or_clean
    MERGING --> CONFLICT: conflict
    CONFLICT --> PENDING: conflict_task_done
    CONFLICT --> ABANDONED: user_abandons
    MERGED --> [*]
    ABANDONED --> [*]
```

Only Core merges (executions have no rights to the main branch). CONFLICT sets the owning task
BLOCKED and creates a follow-up `code_change` task "resolve conflict" in the same plan.
`git_commit` on the main branch and `git_push` are separate action classes evaluated by policy
at MERGING time.

---

## 14. Event handling (consumer cursors)

Each outbox consumer (spawner, notifier, automation matcher, learning pass, inspector scheduler,
SSE fan-out) owns a row in `consumer_cursors(name, last_seq)`. A consumer processes events in
`seq` order, performs its side effect idempotently (keyed by `(consumer, event_seq)` in
`consumer_effects`), then advances its cursor. A crash re-delivers from the cursor; the effects
table makes re-delivery harmless. This is Munder Difflin's `cursor.json` plus Vicoa's
wake-and-requery, on one SQLite file.
