// The graph capability's list form (p16-design-gate §20): the authoritative
// relationships of one object, each read from the field that records it. No
// edge is inferred: an edge whose field is empty is not emitted. P18's spatial
// view draws the same edges, from the same words (EDGE_WORDS). Pure: tested
// and mutated directly.

export interface Edge {
  rel: string; // what the relationship is, in words
  to: { kind: string; id: string };
  field: string; // the column or body field it was read from
  tier?: 'EXTRACTED' | 'INFERRED' | 'AMBIGUOUS';
  inactive?: boolean; // superseded / ended: shown distinct, never as current
}

type Obj = Record<string, unknown>;

/** The one vocabulary of relationships (p18-design-gate A1): per field, the
 * words read at the row that holds the field, then at the row it names. The
 * Relations list and the spatial view both say these; Core's graph route
 * names the field and never the words. */
export const EDGE_WORDS: Readonly<Record<string, readonly [string, string]>> = {
  'missions.project_id': ['in project', 'mission'],
  'Mission.context_package_id': ['context used', 'context for mission'],
  'Mission.origin_ref': ['started from', 'started mission'],
  'plans.mission_id': ['of mission', 'plan'],
  'approvals.mission_id': ['waiting on approval', 'awaited by mission'],
  'plans.supersedes_plan_id': ['replaces', 'replaced by'],
  'Plan.context_package_id': ['context used', 'context for plan'],
  'Plan.route_decision_id': ['planned by', 'planned'],
  'Task.depends_on': ['after', 'before'],
  'tasks.plan_id': ['in plan', 'task'],
  'executions.task_id': ['attempt of task', 'attempt'],
  'executions.mission_id': ['of mission', 'execution'],
  'Execution.handoff_from': ['continues', 'continued by'],
  'Execution.session_id': ['runs in session', 'runs'],
  'Execution.route_decision_id': ['routed by', 'routed'],
  'Execution.policy_decision_id': ['authorised by', 'authorised'],
  'Verification.subject': ['verifies', 'verified by'],
  'verifications.plan_id': ['of plan', 'verification'],
  'Verification.execution_id': ['checked the work of', 'checked by'],
  'reviews.plan_id': ['reviews plan', 'review'],
  'sessions.mission_id': ['continues mission', 'continued in session'],
  'sessions.handoff_from_session_id': ['handed off from', 'handed off to'],
  'sessions.project_id': ['in project', 'session'],
  'KnowledgeItem.supersedes_id': ['replaces', 'replaced by'],
  'KnowledgeItem.superseded_by_id': ['replaced by', 'replaces'],
  'KnowledgeItem.route_decision_id': ['produced by', 'produced'],
  'knowledge_items.project_id': ['in project', 'knowledge'],
  'repositories.project_id': ['in project', 'repository'],
  'automation_runs.automation_id': ['run of automation', 'run'],
  'automation_runs.mission_id': ['created mission', 'created by run'],
};

/** An edge's words from where one stands: at the row holding its field
 * (`holder`), or at the row it names. A `Relation` row says its own `rel`. */
export function edgeWords(field: string, holder: boolean, rel?: string | null): string {
  if (field.startsWith('relations.')) return holder ? String(rel) : `${String(rel)} (from)`;
  const w = EDGE_WORDS[field];
  return w ? w[holder ? 0 : 1] : field;
}

const s = (v: unknown) => (typeof v === 'string' && v ? v : null);

function edge(out: Edge[], field: string, kind: string, id: unknown, extra: Partial<Edge> = {}, holder = true) {
  const v = s(id);
  if (v) out.push({ rel: edgeWords(field, holder), to: { kind, id: v }, field, ...extra });
}

export function missionEdges(
  m: Obj,
  plan?: { versions?: { id: string; plan_version: number; state: string }[] } | null,
  sessions: Obj[] = [],
): Edge[] {
  const out: Edge[] = [];
  edge(out, 'missions.project_id', 'project', m.project_id);
  edge(out, 'Mission.context_package_id', 'context_package', m.context_package_id);
  const origin = m.origin_ref as { kind?: string; id?: string } | undefined;
  if (origin?.kind) edge(out, 'Mission.origin_ref', origin.kind, origin.id);
  for (const v of plan?.versions ?? [])
    edge(out, 'plans.mission_id', 'plan', v.id, {
      rel: `${edgeWords('plans.mission_id', false)} v${String(v.plan_version)}`,
      inactive: v.state === 'SUPERSEDED' || v.state === 'REJECTED',
    }, false);
  edge(out, 'approvals.mission_id', 'approval', m.pending_approval_id);
  for (const x of sessions) edge(out, 'sessions.mission_id', 'session', x.id, {}, false);
  return out;
}

export function planEdges(p: Obj): Edge[] {
  const out: Edge[] = [];
  edge(out, 'plans.mission_id', 'mission', p.mission_id);
  edge(out, 'plans.supersedes_plan_id', 'plan', p.supersedes_plan_id);
  edge(out, 'Plan.context_package_id', 'context_package', p.context_package_id);
  edge(out, 'Plan.route_decision_id', 'route_decision', p.route_decision_id);
  return out;
}

export function taskDependencies(t: Obj, byKey: Record<string, Obj>): Edge[] {
  const out: Edge[] = [];
  for (const k of (t.depends_on as string[] | undefined) ?? []) edge(out, 'Task.depends_on', 'task', byKey[k]?.id);
  return out;
}

export function executionEdges(e: Obj): Edge[] {
  const out: Edge[] = [];
  edge(out, 'executions.task_id', 'task', e.task_id);
  edge(out, 'executions.mission_id', 'mission', e.mission_id);
  // a hand-off: this execution continues the one it names (Execution.handoff_from)
  edge(out, 'Execution.handoff_from', 'execution', e.handoff_from);
  edge(out, 'Execution.session_id', 'session', e.session_id);
  edge(out, 'Execution.route_decision_id', 'route_decision', e.route_decision_id);
  edge(out, 'Execution.policy_decision_id', 'policy_decision', e.policy_decision_id);
  return out;
}

export function verificationEdges(v: Obj): Edge[] {
  const out: Edge[] = [];
  const subject = v.subject as { kind?: string; id?: string } | undefined;
  if (subject?.kind) edge(out, 'Verification.subject', subject.kind, subject.id);
  edge(out, 'verifications.plan_id', 'plan', v.plan_id);
  edge(out, 'Verification.execution_id', 'execution', v.execution_id);
  return out;
}

export function sessionEdges(x: Obj, view?: { lineage?: Obj[]; targets?: Obj[] }): Edge[] {
  const out: Edge[] = [];
  edge(out, 'sessions.mission_id', 'mission', x.mission_id);
  edge(out, 'sessions.handoff_from_session_id', 'session', x.handoff_from_session_id);
  for (const t of view?.targets ?? []) edge(out, 'sessions.handoff_from_session_id', 'session', t.id, {}, false);
  edge(out, 'sessions.project_id', 'project', x.project_id);
  return out;
}

export function knowledgeEdges(k: Obj): Edge[] {
  const out: Edge[] = [];
  const me = s(k.id);
  for (const r of (k.relations as Obj[] | undefined) ?? []) {
    const outgoing = r.src_kind === 'knowledge_item' && r.src_id === me;
    const field = 'relations.' + String(r.rel);
    const extra = {
      rel: edgeWords(field, outgoing, String(r.rel)),
      tier: (r.confidence_tier as Edge['tier']) ?? 'EXTRACTED',
      inactive: !!r.valid_until,
    };
    if (outgoing) edge(out, field, String(r.dst_kind), r.dst_id, extra);
    else edge(out, field, String(r.src_kind), r.src_id, extra, false);
  }
  edge(out, 'KnowledgeItem.supersedes_id', 'knowledge_item', k.supersedes_id);
  edge(out, 'KnowledgeItem.superseded_by_id', 'knowledge_item', k.superseded_by_id, { inactive: false });
  edge(out, 'KnowledgeItem.route_decision_id', 'route_decision', k.route_decision_id);
  return out;
}

export function runEdges(r: Obj): Edge[] {
  const out: Edge[] = [];
  edge(out, 'automation_runs.automation_id', 'automation', r.automation_id);
  edge(out, 'automation_runs.mission_id', 'mission', r.mission_id);
  return out;
}

/** The line style that encodes a relation's confidence tier (research §22). */
export const TIER_STYLE: Record<NonNullable<Edge['tier']>, string> = {
  EXTRACTED: 'solid',
  INFERRED: 'dashed',
  AMBIGUOUS: 'dotted',
};
