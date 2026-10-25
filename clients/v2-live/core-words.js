/* Copied from clients/app/tokens/presentation.json and the generated LABELS in clients/app/src/state/presentation.ts
   (V1 Core state words). Data only; regenerate by copying again, never edit by hand. */
export const WORDS = {
 "classes": {
  "planning": {
   "glyph": "◌",
   "ascii": "~",
   "role": "state.thinking",
   "name": "Planning"
  },
  "proposed": {
   "glyph": "○",
   "ascii": "o",
   "role": "text-2",
   "name": "Proposed"
  },
  "needs_you": {
   "glyph": "◆",
   "ascii": "!",
   "role": "state.attention",
   "name": "Needs you"
  },
  "approved": {
   "glyph": "◇",
   "ascii": "^",
   "role": "text-2",
   "name": "Approved"
  },
  "active": {
   "glyph": "●",
   "ascii": "*",
   "role": "state.active",
   "name": "Active"
  },
  "verifying": {
   "glyph": "●",
   "ascii": "*",
   "role": "state.active",
   "name": "Verifying"
  },
  "reviewing": {
   "glyph": "●",
   "ascii": "*",
   "role": "state.active",
   "name": "Reviewing"
  },
  "blocked": {
   "glyph": "■",
   "ascii": "#",
   "role": "state.blocked",
   "name": "Blocked"
  },
  "paused": {
   "glyph": "‖",
   "ascii": "=",
   "role": "state.paused",
   "name": "Paused"
  },
  "failed": {
   "glyph": "✕",
   "ascii": "x",
   "role": "state.blocked",
   "name": "Failed"
  },
  "done": {
   "glyph": "✓",
   "ascii": "+",
   "role": "state.done",
   "name": "Done"
  },
  "neutral": {
   "glyph": "·",
   "ascii": ".",
   "role": "text-2",
   "name": "—"
  },
  "inactive": {
   "glyph": "–",
   "ascii": "-",
   "role": "text-2",
   "name": "Inactive"
  }
 },
 "machines": {
  "mission": {
   "CREATED": "planning",
   "UNDERSTANDING": "planning",
   "CONTEXT_GATHERING": "planning",
   "REASONING": "planning",
   "PLANNING": "planning",
   "REPLANNING": "planning",
   "APPROVAL_REQUIRED": "needs_you",
   "APPROVED": "approved",
   "EXECUTING": "active",
   "RESUMED": "active",
   "VERIFYING": "verifying",
   "REVIEWING": "reviewing",
   "BLOCKED": "blocked",
   "PAUSED": "paused",
   "FAILED": "failed",
   "COMPLETED": "done",
   "CANCELLED": "inactive"
  },
  "plan": {
   "DRAFT": "planning",
   "PROPOSED": "proposed",
   "APPROVED": "approved",
   "REJECTED": "inactive",
   "SUPERSEDED": "inactive"
  },
  "task": {
   "PENDING": "neutral",
   "READY": "neutral",
   "ROUTING": "active",
   "RUNNING": "active",
   "AWAITING_APPROVAL": "needs_you",
   "BLOCKED": "blocked",
   "PAUSED": "paused",
   "VERIFYING": "verifying",
   "SUCCEEDED": "done",
   "FAILED": "failed",
   "SKIPPED": "inactive",
   "CANCELLED": "inactive"
  },
  "execution": {
   "INTENT": "active",
   "STARTING": "active",
   "RUNNING": "active",
   "AWAITING_APPROVAL": "needs_you",
   "PAUSING": "paused",
   "PAUSED": "paused",
   "HANDING_OFF": "active",
   "STOPPING": "paused",
   "LOST": "blocked",
   "ENDED_OK": "neutral",
   "ENDED_HANDOFF": "neutral",
   "ENDED_ERROR": "failed",
   "ENDED_KILLED": "failed",
   "ENDED_REJECTED": "failed",
   "ABANDONED": "failed"
  },
  "approval": {
   "PENDING": "needs_you",
   "APPROVED": "approved",
   "CONSUMED": "inactive",
   "REJECTED": "inactive",
   "EXPIRED": "inactive",
   "SUPERSEDED": "inactive"
  },
  "verification": {
   "PENDING": "neutral",
   "RUNNING": "verifying",
   "PASSED": "done",
   "FAILED": "failed",
   "ERROR": "blocked",
   "AWAITING_HUMAN": "needs_you"
  },
  "review": {
   "PENDING": "neutral",
   "IN_REVIEW": "reviewing",
   "ACCEPTED": "done",
   "CHANGES_REQUESTED": "neutral",
   "REJECTED": "failed"
  },
  "session": {
   "OPEN": "neutral",
   "CLOSED": "inactive",
   "LOST": "blocked"
  },
  "automation": {
   "DRAFT": "neutral",
   "PENDING_APPROVAL": "needs_you",
   "ENABLED": "neutral",
   "DISABLED": "inactive",
   "SUSPENDED": "blocked",
   "ARCHIVED": "inactive"
  },
  "automation_run": {
   "CLAIMED": "neutral",
   "POLICY_CHECK": "neutral",
   "SKIPPED": "inactive",
   "ESCALATED": "needs_you",
   "MISSION_CREATED": "active",
   "SUCCEEDED": "done",
   "FAILED": "failed"
  },
  "account_health": {
   "UNVERIFIED": "neutral",
   "AVAILABLE": "neutral",
   "CONSTRAINED": "neutral",
   "LIMITED": "blocked",
   "DEGRADED": "blocked",
   "OPEN": "blocked",
   "UNAUTHENTICATED": "needs_you",
   "DISABLED": "inactive"
  },
  "architecture": {
   "UNKNOWN": "neutral",
   "CONSISTENT": "done",
   "STALE": "neutral",
   "DRIFTED": "needs_you"
  },
  "repository_inspection": {
   "SCHEDULED": "neutral",
   "RUNNING": "active",
   "COMPLETED": "done",
   "FAILED": "failed"
  },
  "knowledge_item": {
   "CANDIDATE": "needs_you",
   "CONFIRMED": "done",
   "SUPERSEDED": "inactive",
   "RETRACTED": "inactive",
   "EXPIRED": "inactive"
  },
  "idea": {
   "CAPTURED": "neutral",
   "UNDERSTOOD": "planning",
   "EXPLORED": "planning",
   "VALIDATED": "planning",
   "CONCEPT": "planning",
   "PLANNED": "planning",
   "SCHEDULED": "neutral",
   "IMPLEMENTING": "active",
   "COMPLETED": "done",
   "LEARNED": "done",
   "PARKED": "paused",
   "DISCARDED": "inactive"
  },
  "device": {
   "PAIRING": "neutral",
   "ACTIVE": "neutral",
   "REVOKED": "inactive"
  },
  "integration": {
   "PENDING": "neutral",
   "MERGING": "active",
   "MERGED": "done",
   "CONFLICT": "blocked",
   "ABANDONED": "inactive"
  },
  "execution_node": {
   "ONLINE": "neutral",
   "GRACE": "paused",
   "OFFLINE": "blocked",
   "RETIRED": "inactive"
  }
 },
 "labels": {
  "account_health": {
   "UNVERIFIED": "Unverified",
   "AVAILABLE": "Available",
   "CONSTRAINED": "Near its ceiling",
   "LIMITED": "Limited",
   "DEGRADED": "Degraded",
   "OPEN": "Circuit open",
   "UNAUTHENTICATED": "Unauthenticated",
   "DISABLED": "Disabled"
  },
  "approval": {
   "PENDING": "Pending",
   "APPROVED": "Approved",
   "CONSUMED": "Used",
   "REJECTED": "Rejected",
   "EXPIRED": "Expired",
   "SUPERSEDED": "Superseded"
  },
  "architecture": {
   "UNKNOWN": "Unknown",
   "CONSISTENT": "Consistent",
   "STALE": "Stale — re-inspecting",
   "DRIFTED": "Drifted"
  },
  "automation": {
   "DRAFT": "Draft",
   "PENDING_APPROVAL": "Pending approval",
   "ENABLED": "Enabled",
   "DISABLED": "Disabled",
   "SUSPENDED": "Suspended",
   "ARCHIVED": "Archived"
  },
  "automation_run": {
   "CLAIMED": "Claimed",
   "POLICY_CHECK": "Policy check",
   "SKIPPED": "Skipped",
   "ESCALATED": "Escalated",
   "MISSION_CREATED": "Mission created",
   "SUCCEEDED": "Succeeded",
   "FAILED": "Failed"
  },
  "device": {
   "PAIRING": "Pairing",
   "ACTIVE": "Active",
   "REVOKED": "Revoked"
  },
  "execution": {
   "INTENT": "Starting",
   "STARTING": "Starting",
   "RUNNING": "Running",
   "AWAITING_APPROVAL": "Awaiting approval",
   "PAUSING": "Pausing",
   "PAUSED": "Paused",
   "HANDING_OFF": "Handing off",
   "STOPPING": "Stopping",
   "LOST": "Lost — Core is reconciling",
   "ENDED_OK": "Exited ok — not verified",
   "ENDED_HANDOFF": "Handed off",
   "ENDED_ERROR": "Ended error",
   "ENDED_KILLED": "Killed",
   "ENDED_REJECTED": "Ended: approval rejected",
   "ABANDONED": "Abandoned"
  },
  "execution_node": {
   "ONLINE": "Online",
   "GRACE": "Grace",
   "OFFLINE": "Offline",
   "RETIRED": "Retired"
  },
  "idea": {
   "CAPTURED": "Captured",
   "UNDERSTOOD": "Understood",
   "EXPLORED": "Explored",
   "VALIDATED": "Validated",
   "CONCEPT": "Concept",
   "PLANNED": "Planned",
   "SCHEDULED": "Scheduled",
   "IMPLEMENTING": "Implementing",
   "COMPLETED": "Completed",
   "LEARNED": "Learned",
   "PARKED": "Parked",
   "DISCARDED": "Discarded"
  },
  "integration": {
   "PENDING": "Pending",
   "MERGING": "Merging",
   "MERGED": "Merged",
   "CONFLICT": "Conflict",
   "ABANDONED": "Abandoned"
  },
  "knowledge_item": {
   "CANDIDATE": "Candidate",
   "CONFIRMED": "Confirmed",
   "SUPERSEDED": "Superseded",
   "RETRACTED": "Retracted",
   "EXPIRED": "Expired"
  },
  "mission": {
   "CREATED": "Created",
   "UNDERSTANDING": "Understanding",
   "CONTEXT_GATHERING": "Context gathering",
   "REASONING": "Reasoning",
   "PLANNING": "Planning",
   "REPLANNING": "Replanning",
   "APPROVAL_REQUIRED": "Waiting for approval",
   "APPROVED": "Approved — not started",
   "EXECUTING": "Executing",
   "RESUMED": "Resuming",
   "VERIFYING": "Verifying",
   "REVIEWING": "Reviewing — verified, not accepted",
   "BLOCKED": "Blocked",
   "PAUSED": "Paused",
   "FAILED": "Failed",
   "COMPLETED": "Done — verified and reviewed",
   "CANCELLED": "Cancelled"
  },
  "plan": {
   "DRAFT": "Draft",
   "PROPOSED": "Proposed — validated, not approved",
   "APPROVED": "Approved",
   "REJECTED": "Rejected",
   "SUPERSEDED": "Superseded"
  },
  "repository_inspection": {
   "SCHEDULED": "Scheduled",
   "RUNNING": "Running",
   "COMPLETED": "Completed",
   "FAILED": "Failed"
  },
  "review": {
   "PENDING": "Pending",
   "IN_REVIEW": "In review",
   "ACCEPTED": "Accepted",
   "CHANGES_REQUESTED": "Changes requested",
   "REJECTED": "Rejected"
  },
  "session": {
   "OPEN": "Open",
   "CLOSED": "Closed",
   "LOST": "Lost — provider session not found"
  },
  "task": {
   "PENDING": "Pending",
   "READY": "Ready",
   "ROUTING": "Routing",
   "RUNNING": "Running",
   "AWAITING_APPROVAL": "Awaiting approval",
   "BLOCKED": "Blocked",
   "PAUSED": "Paused",
   "VERIFYING": "Verifying",
   "SUCCEEDED": "Succeeded",
   "FAILED": "Failed",
   "SKIPPED": "Skipped",
   "CANCELLED": "Cancelled"
  },
  "verification": {
   "PENDING": "Pending",
   "RUNNING": "Running",
   "PASSED": "Passed",
   "FAILED": "Failed",
   "ERROR": "Verifier error — not a failure of the work",
   "AWAITING_HUMAN": "Waiting for your acceptance"
  }
 }
};

export function present(machine, state) {
  const cls = WORDS.machines[machine] && WORDS.machines[machine][state];
  if (!cls) return { cls: 'neutral', glyph: '?', ascii: '?', role: 'text-2', label: state };
  const c = WORDS.classes[cls];
  const lab = WORDS.labels[machine] && WORDS.labels[machine][state];
  return { cls, glyph: c.glyph, ascii: c.ascii, role: c.role, label: lab || state.charAt(0) + state.slice(1).toLowerCase().replace(/_/g, ' ') };
}
