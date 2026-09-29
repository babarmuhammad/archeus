// The graph capability's list form (p16-design-gate §20): the authoritative
// relationships of one object, each read from the field that records it. No
// edge is inferred: an edge whose field is empty is not emitted. P18's spatial
// view draws the same edges. Pure: tested and mutated directly.

export interface Edge {
  rel: string; // what the relationship is, in words
  to: { kind: string; id: string };
  field: string; // the column or body field it was read from
  tier?: 'EXTRACTED' | 'INFERRED' | 'AMBIGUOUS';
  inactive?: boolean; // superseded / ended: shown distinct, never as current
}

type Obj = Record<string, unknown>;

const s = (v: unknown) => (typeof v === 'string' && v ? v : null);

function edge(out: Edge[], rel: string, kind: string, id: unknown, field: string, extra: Partial<Edge> = {}) {
  const v = s(id);
  if (v) out.push({ rel, to: { kind, id: v }, field, ...extra });
}

export function missionEdges(
  m: Obj,
  plan?: { versions?: { id: string; plan_version: number; state: string }[] } | null,
  sessions: Obj[] = [],
): Edge[] {
  const out: Edge[] = [];
  edge(out, 'in project', 'project', m.project_id, 'missions.project_id');
  edge(out, 'context used', 'context_package', m.context_package_id, 'Mission.context_package_id');
  const origin = m.origin_ref as { kind?: string; id?: string } | undefined;
  if (origin?.kind) edge(out, 'started from', origin.kind, origin.id, 'Mission.origin_ref');
  for (const v of plan?.versions ?? [])
    edge(out, `plan v${String(v.plan_version)}`, 'plan', v.id, 'plans.mission_id', {
      inactive: v.state === 'SUPERSEDED' || v.state === 'REJECTED',
    });
  edge(out, 'waiting on approval', 'approval', m.pending_approval_id, 'approvals.mission_id');
  for (const x of sessions) edge(out, 'continued in session', 'session', x.id, 'sessions.mission_id');
  return out;
}

export function planEdges(p: Obj): Edge[] {
  const out: Edge[] = [];
  edge(out, 'of mission', 'mission', p.mission_id, 'plans.mission_id');
  edge(out, 'replaces', 'plan', p.supersedes_plan_id, 'plans.supersedes_plan_id');
  edge(out, 'context used', 'context_package', p.context_package_id, 'Plan.context_package_id');
  edge(out, 'planned by', 'route_decision', p.route_decision_id, 'Plan.route_decision_id');
  return out;
}

export function taskDependencies(t: Obj, byKey: Record<string, Obj>): Edge[] {
  const out: Edge[] = [];
  for (const k of (t.depends_on as string[] | undefined) ?? [])
    edge(out, 'after', 'task', byKey[k]?.id, 'Task.depends_on');
  return out;
}

export function executionEdges(e: Obj): Edge[] {
  const out: Edge[] = [];
  edge(out, 'attempt of task', 'task', e.task_id, 'executions.task_id');
  edge(out, 'of mission', 'mission', e.mission_id, 'executions.mission_id');
  // a hand-off: this execution continues the one it names (Execution.handoff_from)
  edge(out, 'continues', 'execution', e.handoff_from, 'Execution.handoff_from');
  edge(out, 'runs in session', 'session', e.session_id, 'Execution.session_id');
  edge(out, 'routed by', 'route_decision', e.route_decision_id, 'Execution.route_decision_id');
  edge(out, 'authorised by', 'policy_decision', e.policy_decision_id, 'Execution.policy_decision_id');
  return out;
}

export function verificationEdges(v: Obj): Edge[] {
  const out: Edge[] = [];
  const subject = v.subject as { kind?: string; id?: string } | undefined;
  if (subject?.kind) edge(out, 'verifies', subject.kind, subject.id, 'Verification.subject');
  edge(out, 'of plan', 'plan', v.plan_id, 'verifications.plan_id');
  edge(out, 'checked the work of', 'execution', v.execution_id, 'Verification.execution_id');
  return out;
}

export function sessionEdges(x: Obj, view?: { lineage?: Obj[]; targets?: Obj[] }): Edge[] {
  const out: Edge[] = [];
  edge(out, 'continues mission', 'mission', x.mission_id, 'sessions.mission_id');
  edge(out, 'handed off from', 'session', x.handoff_from_session_id, 'sessions.handoff_from_session_id');
  for (const t of view?.targets ?? []) edge(out, 'handed off to', 'session', t.id, 'sessions.handoff_from_session_id');
  edge(out, 'in project', 'project', x.project_id, 'sessions.project_id');
  return out;
}

export function knowledgeEdges(k: Obj): Edge[] {
  const out: Edge[] = [];
  const me = s(k.id);
  for (const r of (k.relations as Obj[] | undefined) ?? []) {
    const outgoing = r.src_kind === 'knowledge_item' && r.src_id === me;
    const tier = (r.confidence_tier as Edge['tier']) ?? 'EXTRACTED';
    if (outgoing) edge(out, String(r.rel), String(r.dst_kind), r.dst_id, 'relations.' + String(r.rel), { tier, inactive: !!r.valid_until });
    else edge(out, `${String(r.rel)} (from)`, String(r.src_kind), r.src_id, 'relations.' + String(r.rel), { tier, inactive: !!r.valid_until });
  }
  edge(out, 'replaces', 'knowledge_item', k.supersedes_id, 'KnowledgeItem.supersedes_id');
  edge(out, 'replaced by', 'knowledge_item', k.superseded_by_id, 'KnowledgeItem.superseded_by_id', { inactive: false });
  edge(out, 'produced by', 'route_decision', k.route_decision_id, 'KnowledgeItem.route_decision_id');
  return out;
}

export function runEdges(r: Obj): Edge[] {
  const out: Edge[] = [];
  edge(out, 'run of automation', 'automation', r.automation_id, 'automation_runs.automation_id');
  edge(out, 'created mission', 'mission', r.mission_id, 'automation_runs.mission_id');
  return out;
}

/** The line style that encodes a relation's confidence tier (research §22). */
export const TIER_STYLE: Record<NonNullable<Edge['tier']>, string> = {
  EXTRACTED: 'solid',
  INFERRED: 'dashed',
  AMBIGUOUS: 'dotted',
};
