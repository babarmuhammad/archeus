// Replay vocabulary: every state of every machine with its Replay category. Generated from archeus/core/application/replay.py (T-148, c86e8fd)
// for the categories and from .collab/REPLAY-coverage.md Part A for the reasons. execution.ENDED_REJECTED is RECORDED (owner clarification 2026-10-25).
// A state with no entry answers UNKNOWN, never a guess. Data only.
export const VOCAB = {
 "idea": [
  [
   "CAPTURED",
   "INTENDED",
   "start state; idea.created = \"an idea was captured\" (events.py:31)"
  ],
  [
   "UNDERSTOOD",
   "INTENDED",
   "clarify 55 — a question answered, nothing dispatched"
  ],
  [
   "SCHEDULED",
   "INTENDED",
   "schedule 56/65 — a time is set, no run exists"
  ],
  [
   "PARKED",
   "INTENDED",
   "park 57, revive 71 — intent held idle"
  ],
  [
   "EXPLORED",
   "INTENDED",
   "explore 58"
  ],
  [
   "PLANNED",
   "INTENDED",
   "plan 59/63/64 — a plan version is asked for"
  ],
  [
   "VALIDATED",
   "INTENDED",
   "validate 60"
  ],
  [
   "DISCARDED",
   "INTENDED",
   "discard 61; revive 72 keeps the intent re-usable"
  ],
  [
   "CONCEPT",
   "INTENDED",
   "conceptualise 62"
  ],
  [
   "IMPLEMENTING",
   "INTENDED",
   "promote 66 — a flag on planned work; the run is the mission machine's state"
  ],
  [
   "COMPLETED",
   "RECORDED",
   "mission_completed 68, committed with its idea.state_changed (writer.py:213)"
  ],
  [
   "LEARNED",
   "RECORDED",
   "learn 70 — the learning step is recorded with the move"
  ]
 ],
 "mission": [
  [
   "CREATED",
   "INTENDED",
   "mission.created \"a mission row was created\" (events.py:22)"
  ],
  [
   "UNDERSTANDING",
   "INTENDED",
   "start 79 — requirements being read"
  ],
  [
   "CONTEXT_GATHERING",
   "INTENDED",
   "understood 80 — context being assembled"
  ],
  [
   "REASONING",
   "INTENDED",
   "context_ready 82"
  ],
  [
   "PLANNING",
   "INTENDED",
   "reasoned 83"
  ],
  [
   "REPLANNING",
   "INTENDED",
   "task_failed_retryable 98 — a new plan version is asked for"
  ],
  [
   "RESUMED",
   "INTENDED",
   "unblock 99 / resume 100; redispatch 101 comes later"
  ],
  [
   "BLOCKED",
   "SUSPENDED",
   "needs_clarification 81, awaiting_human_acceptance 109 — waits on a person (unblock 99); also reached by plan_denied 86 and replan_budget_exhausted 106"
  ],
  [
   "APPROVAL_REQUIRED",
   "SUSPENDED",
   "plan_needs_approval 87 → approval.requested (events.py:71, notify True); approve 90"
  ],
  [
   "PAUSED",
   "SUSPENDED",
   "pause 96 (a Pause all: pause_batch.created events.py:27); resume 100 is the user's"
  ],
  [
   "REVIEWING",
   "SUSPENDED",
   "verified 107 → a verdict is awaited (accepted 110, changes_requested 111)"
  ],
  [
   "APPROVED",
   "AUTHORIZED",
   "approve 90 / plan_auto_approved 88 are guarded edges (_GUARDED states.py:371-377: \"approved only by a real authorisation\")"
  ],
  [
   "CANCELLED",
   "RECORDED",
   "cancel 89/112-115 commits a reason with the move"
  ],
  [
   "FAILED",
   "RECORDED",
   "unrecoverable 97, guarded 371 — a settled failure with its reason"
  ],
  [
   "COMPLETED",
   "RECORDED",
   "accepted 110 (guarded 371) with the Review's findings (entities.py:1246-1255)"
  ],
  [
   "EXECUTING",
   "MAY-HAVE-TAKEN-EFFECT",
   "dispatch 93 — executions run; their effects are not yet verified"
  ],
  [
   "VERIFYING",
   "MAY-HAVE-TAKEN-EFFECT",
   "all_tasks_done 94 (guarded, 371) — work is done, the verdict is not in"
  ]
 ],
 "plan": [
  [
   "DRAFT",
   "INTENDED",
   "transient: \"a version is inserted and takes ready in the same transaction\" (states.py:120-122)"
  ],
  [
   "PROPOSED",
   "INTENDED",
   "\"structurally valid and ready for the POLICY stage, never approved or executable\" (states.py:121-122)"
  ],
  [
   "APPROVED",
   "AUTHORIZED",
   "approved 126 — P9's authorisation (comment 122; PolicyDecision row entities.py:1766-1782)"
  ],
  [
   "REJECTED",
   "AUTHORIZED",
   "rejected 127 — \"blocked only by a recorded denial\" (states.py:375-377)"
  ],
  [
   "SUPERSEDED",
   "RECORDED",
   "superseded 128, plan.state_changed (events.py:34)"
  ]
 ],
 "task": [
  [
   "PENDING",
   "INTENDED",
   "start; task.created \"a task of a plan was created\" (events.py:36)"
  ],
  [
   "READY",
   "INTENDED",
   "deps_satisfied 135"
  ],
  [
   "SKIPPED",
   "NONE",
   "skip 136 — never dispatched, nothing pending, no evidence"
  ],
  [
   "ROUTING",
   "MAY-HAVE-TAKEN-EFFECT",
   "dispatch 137 — the router is asked and may have made its own calls (route.decided events.py:116, archeus_call.ended 118)"
  ],
  [
   "RUNNING",
   "MAY-HAVE-TAKEN-EFFECT",
   "routed 138 — an execution is live; its effects are not verified"
  ],
  [
   "VERIFYING",
   "MAY-HAVE-TAKEN-EFFECT",
   "execution_succeeded 146 — the run ended, the checks have not reported"
  ],
  [
   "BLOCKED",
   "SUSPENDED",
   "no_eligible_resource 139, merge_conflict 149, rejected 143 — unblock 153 is someone else's action"
  ],
  [
   "AWAITING_APPROVAL",
   "SUSPENDED",
   "route_needs_approval 140 / action_needs_approval 141; approval.requested (events.py:71)"
  ],
  [
   "PAUSED",
   "SUSPENDED",
   "pause 144, resume 145"
  ],
  [
   "FAILED",
   "RECORDED",
   "execution_failed_final 148 with failure_class, \"set with that move\" (entities.py:930)"
  ],
  [
   "SUCCEEDED",
   "RECORDED",
   "checks_passed 150 — the Verification rows behind it are durable (entities.py:1191-1193)"
  ],
  [
   "CANCELLED",
   "RECORDED",
   "cancel 154-157 commits the reason with the move"
  ]
 ],
 "execution": [
  [
   "INTENT",
   "INTENDED",
   "execution.intent = \"an execution was committed before spawn\" (events.py:38)"
  ],
  [
   "STARTING",
   "MAY-HAVE-TAKEN-EFFECT",
   "spawn 165 — the marker may exist with no pid recorded (\"a marker without ended belongs to reconciliation\", base.py:15-16)"
  ],
  [
   "RUNNING",
   "MAY-HAVE-TAKEN-EFFECT",
   "first_output 168 — the process exists (execution.started \"its process exists (pid, create_time)\", events.py:40)"
  ],
  [
   "PAUSING",
   "MAY-HAVE-TAKEN-EFFECT",
   "pause_requested 173 — the process is alive until halted_at_boundary 174 or pause_timeout 175"
  ],
  [
   "HANDING_OFF",
   "MAY-HAVE-TAKEN-EFFECT",
   "pressure_or_account_change 177 / user_handoff 181 — running up to the checkpoint"
  ],
  [
   "STOPPING",
   "MAY-HAVE-TAKEN-EFFECT",
   "stop 184/185/189/190 — the kill is not yet confirmed (process_gone 195 completes it)"
  ],
  [
   "ABANDONED",
   "NONE",
   "spawn_failed 166 only; boot's INTENT branch refuses it with reason='no process was started' (_reconcile_one, manager.py:875-897)"
  ],
  [
   "LOST",
   "UNCERTAIN",
   "spawn_unconfirmed 167, start_timeout 169, heartbeat_missing 198; \"charged (a process may have run and done anything)\" (executions.py:472-474)"
  ],
  [
   "AWAITING_APPROVAL",
   "SUSPENDED",
   "hook_asked 170 — the process halts at its boundary (execution.halted events.py:47) pending a decision"
  ],
  [
   "PAUSED",
   "SUSPENDED",
   "halted_at_boundary 174; resume 176 is the user's, discarded 193 ends it"
  ],
  [
   "ENDED_HANDOFF",
   "RECORDED",
   "checkpoint_written 178 — checkpoint.created (events.py:66) over an immutable Checkpoint"
  ],
  [
   "ENDED_OK",
   "RECORDED",
   "exited_success 182 — execution.ended \"the process exited (payload: exit_reason)\" (events.py:42)"
  ],
  [
   "ENDED_ERROR",
   "RECORDED",
   "exited_error 183 with exit_reason/exit_code (entities.py:985-986)"
  ],
  [
   "ENDED_REJECTED",
   "RECORDED",
   "Owner clarification 2026-10-25: a durable terminal row with a recorded rejection."
  ],
  [
   "ENDED_KILLED",
   "RECONCILED",
   "reached from LOST by reconciled_kill 200 — the restart sweep's verdict (executions.lost executions.py:471-486; Engine.reconcile_orphans engine.py:282)"
  ]
 ],
 "session": [
  [
   "OPEN",
   "UNKNOWN",
   "the machine only says a provider conversation is known (comment states.py:208-210); what it produced rides on session.observed (events.py:62) — no code says what OPEN evidences"
  ],
  [
   "CLOSED",
   "RECORDED",
   "close 212 with session.state_changed (events.py:54)"
  ],
  [
   "LOST",
   "UNCERTAIN",
   "vanished 214 — the provider side is gone; only reappeared 215 settles it"
  ]
 ],
 "approval": [
  [
   "PENDING",
   "SUSPENDED",
   "approval.requested \"an action or plan needs a decision\", notify True (events.py:71)"
  ],
  [
   "APPROVED",
   "AUTHORIZED",
   "approve is a guarded edge (_GUARDED['approval'] states.py:380); decided_by/decided_at (entities.py:1826)"
  ],
  [
   "REJECTED",
   "AUTHORIZED",
   "reject 220 — \"blocked only by a recorded denial\" (states.py:375-377)"
  ],
  [
   "EXPIRED",
   "UNCERTAIN",
   "ttl_elapsed 221/224 by the policy worker's sweep (p9-design-gate.md:660) — nobody answered"
  ],
  [
   "SUPERSEDED",
   "RECORDED",
   "plan_replaced 222 in the transaction that supersedes the version (state-machines.md:477)"
  ],
  [
   "CONSUMED",
   "RECORDED",
   "action_executed 223 — \"consumption recorded\" (domain-model.md:620)"
  ]
 ],
 "verification": [
  [
   "PENDING",
   "INTENDED",
   "verification.created \"a task or criterion is checked\" (events.py:80)"
  ],
  [
   "RUNNING",
   "MAY-HAVE-TAKEN-EFFECT",
   "start 233 — the verifier is dispatched; checks not yet recorded"
  ],
  [
   "PASSED",
   "RECORDED",
   "all_checks_pass 234 — checks {name, kind, result, output_sha256…} (entities.py:1190-1191)"
  ],
  [
   "FAILED",
   "RECORDED",
   "a_check_fails 235"
  ],
  [
   "ERROR",
   "UNCERTAIN",
   "verifier_crashed 236; listed among \"What remains uncertain? AWAITING_HUMAN, ERROR, unknown criteria…\" (p13-design-gate.md:971)"
  ],
  [
   "AWAITING_HUMAN",
   "SUSPENDED",
   "generic_verifier 237; user_accepts 238 / user_rejects 239, decided_by/note (entities.py:1201-1202)"
  ]
 ],
 "review": [
  [
   "PENDING",
   "SUSPENDED",
   "review.requested \"a mission result awaits review\" (events.py:82); start 246 / user_reviews 250"
  ],
  [
   "IN_REVIEW",
   "UNKNOWN",
   "a verdict is not yet recorded and the table declares no partial-verdict state (246-249); whether anything external was touched is not stated"
  ],
  [
   "ACCEPTED",
   "RECORDED",
   "verdict_accept 247 with requirements_met[] etc. (entities.py:1249-1253)"
  ],
  [
   "CHANGES_REQUESTED",
   "RECORDED",
   "verdict_changes 248"
  ],
  [
   "REJECTED",
   "RECORDED",
   "verdict_reject 249"
  ]
 ],
 "automation": [
  [
   "DRAFT",
   "INTENDED",
   "automation.created (events.py:87 region) — written, not live"
  ],
  [
   "PENDING_APPROVAL",
   "SUSPENDED",
   "enable_requested 257 → approve 258 / reject 259; the row was written by automation.created (events.py:86)"
  ],
  [
   "SUSPENDED",
   "SUSPENDED",
   "loop_guard_tripped 263; only user_reenables 264 releases it"
  ],
  [
   "ENABLED",
   "AUTHORIZED",
   "approve 258 or enable_within_policy 260 — a policy/user decision made it live"
  ],
  [
   "DISABLED",
   "RECORDED",
   "disable 261 committed with its reason"
  ],
  [
   "ARCHIVED",
   "RECORDED",
   "archive 265 (an operator action, terminal 267)"
  ]
 ],
 "automation_run": [
  [
   "CLAIMED",
   "INTENDED",
   "automation_run.created \"an automation claimed an event\" (events.py:90)"
  ],
  [
   "POLICY_CHECK",
   "INTENDED",
   "conditions_met 274 — the evaluation has not decided yet"
  ],
  [
   "SKIPPED",
   "NONE",
   "condition_false 271 / rate_limited 272 / denied 275 — nothing was ever dispatched"
  ],
  [
   "ESCALATED",
   "SUSPENDED",
   "depth_exceeded 273 / asks 276 — it asks instead of acting"
  ],
  [
   "MISSION_CREATED",
   "AUTHORIZED",
   "allowed 277 — a recorded policy ALLOW created the mission"
  ],
  [
   "SUCCEEDED",
   "RECORDED",
   "mission_completed 278"
  ],
  [
   "FAILED",
   "RECORDED",
   "mission_failed_or_cancelled 279"
  ]
 ],
 "account_health": [
  [
   "UNVERIFIED",
   "UNKNOWN",
   "the start state before auth_ok 287 / auth_failed 288; the table says nothing more about what it evidences"
  ],
  [
   "AVAILABLE",
   "RECORDED",
   "auth_ok 287 — a probe result with account_health.state_changed (events.py:130)"
  ],
  [
   "UNAUTHENTICATED",
   "RECORDED",
   "auth_failed 288/299"
  ],
  [
   "CONSTRAINED",
   "RECORDED",
   "near_ceiling 289 from an observed window (usage.observed events.py:137)"
  ],
  [
   "LIMITED",
   "RECORDED",
   "window_exhausted 291/292; reset_time_passed 293"
  ],
  [
   "DEGRADED",
   "RECORDED",
   "error_storm 294; probe_ok 296"
  ],
  [
   "OPEN",
   "RECORDED",
   "errors_persist 297 — a breaker verdict, cooldown_elapsed 298"
  ],
  [
   "DISABLED",
   "RECORDED",
   "user_disables 301 — an operator action"
  ]
 ],
 "repository_inspection": [
  [
   "SCHEDULED",
   "INTENDED",
   "start 306 queued it"
  ],
  [
   "RUNNING",
   "UNKNOWN",
   "a read is in flight; the state itself stores no evidence and the table says nothing about partial results (306-309)"
  ],
  [
   "COMPLETED",
   "RECORDED",
   "inspected 307 — the findings live on the row (RepositoryInspection, entities.py:305)"
  ],
  [
   "FAILED",
   "RECORDED",
   "error 308; retry 309"
  ]
 ],
 "architecture": [
  [
   "UNKNOWN",
   "UNKNOWN",
   "the start state: no assessment exists yet (314-316)"
  ],
  [
   "CONSISTENT",
   "RECORDED",
   "first_inspection 315 — a guarded assessment edge (_GUARDED['architecture'] 382-383)"
  ],
  [
   "DRIFTED",
   "RECORDED",
   "first_inspection_drift 316; drift verdicts are recorded findings (323-325)"
  ],
  [
   "STALE",
   "RECORDED",
   "revision_moved 317 — the assessed revision no longer matches (project.changed events.py:99)"
  ]
 ],
 "knowledge_item": [
  [
   "CANDIDATE",
   "RECORDED",
   "knowledge_item.created \"a knowledge item was recorded\" (events.py:106); knowledge_item.purged keeps the tombstone's provenance (events.py:109)"
  ],
  [
   "SUPERSEDED",
   "RECORDED",
   "superseded 331 — \"supersession chain never broken\" (domain-model.md:617)"
  ],
  [
   "EXPIRED",
   "RECORDED",
   "validity_ended 333; revalidated 334"
  ],
  [
   "CONFIRMED",
   "RECONCILED",
   "confirm 329 — an operator settles a candidate"
  ],
  [
   "RETRACTED",
   "RECONCILED",
   "reject 330 / retract 332 — an operator's verdict; \"RETRACTED keeps the row\" (domain-model.md:617)"
  ]
 ],
 "device": [
  [
   "PAIRING",
   "INTENDED",
   "a launch code is minted for a slot (entities.py:196-198)"
  ],
  [
   "ACTIVE",
   "AUTHORIZED",
   "code_redeemed 340 grants the client its slot"
  ],
  [
   "REVOKED",
   "AUTHORIZED",
   "revoke 342 — an authorisation decision; \"Revocation closes the device's live SSE streams in the same request\" (state-machines.md:714)"
  ]
 ],
 "execution_node": [
  [
   "ONLINE",
   "RECORDED",
   "heartbeat 348 is an observed fact with node.state_changed (events.py:140)"
  ],
  [
   "OFFLINE",
   "RECORDED",
   "grace_elapsed 349 — a declared timeout verdict; reconnect 350"
  ],
  [
   "GRACE",
   "UNCERTAIN",
   "heartbeat_missed 347 — \"on grace elapsed its RUNNING executions become LOST and are reconciled on wake\" (state-machines.md:714-716)"
  ],
  [
   "RETIRED",
   "RECONCILED",
   "retire 351/352 — an operator settles the node's history"
  ]
 ],
 "integration": [
  [
   "PENDING",
   "INTENDED",
   "task_verified 358 queues the merge"
  ],
  [
   "MERGING",
   "MAY-HAVE-TAKEN-EFFECT",
   "the merge into the mission branch may already have happened; MERGED 359 or CONFLICT 360 decides"
  ],
  [
   "MERGED",
   "RECORDED",
   "fast_forward_or_clean 359 with merged_revision (entities.py:934); guarded task_verified (states.py:384-385)"
  ],
  [
   "CONFLICT",
   "SUSPENDED",
   "conflict 360; conflict_task_done 361 or user_abandons 362 are someone else's actions (Task.conflicts entities.py:935)"
  ],
  [
   "ABANDONED",
   "RECONCILED",
   "user_abandons 362 — an operator closed the question"
  ]
 ],
 "harness": [
  [
   "AVAILABLE",
   "RECORDED",
   "harness.state_changed \"a harness appeared, vanished or broke\" (events.py:139)"
  ],
  [
   "MISSING",
   "RECORDED",
   "same registry; the observation is the record"
  ],
  [
   "MISCONFIGURED",
   "RECORDED",
   "same registry"
  ]
 ]
};
