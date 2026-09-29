// How a row LOOKS (p16-design-gate §6). Every function here maps fields Core
// returned to text and glyphs; none decides what a state means, whether an
// action is allowed, where work runs or whether it is done — those are the
// rows' (P9–P15). Pure: the node tests and the mutation suite run it directly.
import { CLASSES, LABELS, PRESENTATION, TRIGGERS } from './presentation.ts';

/** Whether the state machine has *trigger* from *state* at all — what a button
 * may be offered for. Whether it may fire now is Core's (guards, P9). */
export const offers = (machine: string, state: string, ...trigger: string[]) =>
  trigger.some((t) => TRIGGERS[machine]?.[state]?.includes(t) ?? false);

export interface Look {
  cls: string;
  glyph: string;
  role: string;
  label: string;
}

/** The presentation of *state* of *machine*; an unknown state is shown as
 * itself, neutral, rather than guessed into a class. */
export function present(machine: string, state: string): Look {
  const cls = PRESENTATION[machine]?.[state];
  if (!cls) return { cls: 'neutral', glyph: '?', role: 'text-2', label: state };
  const c = CLASSES[cls];
  return { cls, glyph: c.glyph, role: c.role, label: LABELS[machine]?.[state] ?? state };
}

/** What a state badge renders: the glyph is decoration (hidden from assistive
 * technology), the label is the information — never a glyph alone (§17). */
export function badge(machine: string, state: string): { glyph: string; label: string; role: string; cls: string } {
  const l = present(machine, state);
  return { glyph: l.glyph, label: l.label || state, role: l.role, cls: l.cls };
}

/** A mission is Done only when COMPLETED — verified and reviewed (P13). */
export const isDone = (machine: string, state: string) => present(machine, state).cls === 'done';

// ── presence (P15 §5): transport observation, never a person ──

export type PresenceState = 'connected' | 'recent' | 'absent' | 'revoked';

export function presenceLabel(p: { state: PresenceState; connections: number }): string {
  switch (p.state) {
    case 'connected':
      return `connected (${p.connections} ${p.connections === 1 ? 'stream' : 'streams'})`;
    case 'recent':
      return 'seen in the last minute';
    case 'absent':
      return 'not connected';
    case 'revoked':
      return 'revoked';
  }
}

// ── resources: harness, model and account are three things (§6.4) ──

export interface ResourceField {
  key: 'harness' | 'model' | 'account' | 'effort';
  label: string;
  value: string;
}

/** The resource fields of an execution, route decision or session — each one
 * labelled on its own, never merged into one "model" string. A missing value
 * is shown as missing, not borrowed from another field. */
export function resourceLine(r: {
  harness_id?: unknown;
  model?: unknown;
  account_id?: unknown;
  effort?: unknown;
}): ResourceField[] {
  const v = (x: unknown) => (typeof x === 'string' && x ? x : '—');
  const out: ResourceField[] = [
    { key: 'harness', label: 'Harness', value: v(r.harness_id) },
    { key: 'model', label: 'Model', value: v(r.model) },
    { key: 'account', label: 'Account', value: v(r.account_id) },
  ];
  if (typeof r.effort === 'string' && r.effort) out.push({ key: 'effort', label: 'Effort', value: r.effort });
  return out;
}

// ── the mission status line (§6.1): derived from rows only ──

export interface StatusInputs {
  state: string;
  planning_blocked?: Record<string, unknown> | null;
  pending_approval?: { kind: string; expires_at?: string } | null;
  plan_version?: number | null;
  tasks?: { key: string; title: string; state: string }[];
}

export function statusLine(m: StatusInputs): string {
  const tasks = m.tasks ?? [];
  if (m.state === 'APPROVAL_REQUIRED' && m.pending_approval) {
    return m.pending_approval.kind === 'plan'
      ? `Waiting: approve plan v${m.plan_version ?? '?'}`
      : `Waiting: approve a ${m.pending_approval.kind} step`;
  }
  const pb = m.planning_blocked;
  if (pb && typeof pb === 'object') {
    const qs = (pb.questions as string[] | undefined) ?? [];
    if (pb.kind === 'policy') return 'Blocked: the policy denies this plan';
    if (qs.length) return `Waiting: ${qs[0]}`;
    return `Waiting: planning needs your answer (${String(pb.kind)})`;
  }
  const running = tasks.filter((t) => t.state === 'RUNNING' || t.state === 'ROUTING');
  if (m.state === 'EXECUTING' && running.length) {
    const done = tasks.filter((t) => t.state === 'SUCCEEDED' || t.state === 'SKIPPED').length;
    return `${running[0].title} · ${done} of ${tasks.length} tasks done`;
  }
  return ''; // nothing beyond what the state badge already says
}

// ── why is this in the state it is in? (§6.3) ──

export interface Why {
  text: string;
  source: string; // which row said so
}

/** The recorded reasons for a mission's state, most specific first; when no
 * row explains it, it says so instead of guessing. */
export function explainState(x: {
  mission: { state: string; planning_blocked?: Record<string, unknown> | null };
  approval?: { kind: string; state: string; expires_at?: string; eligible?: boolean; eligible_why?: string | null } | null;
  policy?: { decision: string; reason: string } | null;
  route?: { result?: string | null; explanation?: string; unblock_at?: string | null } | null;
  execution?: { state: string; stop_reason?: string | null; exit_reason?: string | null } | null;
  verification?: { state: string; checks?: { name: string; result: string }[] } | null;
  review?: { state: string; verdict?: string | null } | null;
}): Why[] {
  const out: Why[] = [];
  // a settled mission is explained by its own state, not by what ran after it
  if (x.mission.state === 'COMPLETED')
    return [{ text: 'Completed: its result was verified, and a review accepted it.', source: 'mission.state' }];
  if (x.mission.state === 'CANCELLED') return [{ text: 'Cancelled.', source: 'mission.state' }];
  const pb = x.mission.planning_blocked;
  if (pb) {
    const qs = (pb.questions as string[] | undefined) ?? [];
    out.push({
      text: pb.kind === 'policy' ? 'The policy denies this plan.' : qs.length ? `Planning asks: ${qs.join('; ')}` : `Planning is blocked (${String(pb.kind)}).`,
      source: 'mission.planning_blocked',
    });
  }
  if (x.approval && x.approval.state === 'PENDING') {
    const until = x.approval.expires_at ? ` until ${x.approval.expires_at}` : '';
    out.push({ text: `A ${x.approval.kind} approval waits for you${until}.`, source: 'approval' });
    if (x.approval.eligible === false && x.approval.eligible_why)
      out.push({ text: `It cannot be decided now: ${x.approval.eligible_why}.`, source: 'approval.eligible_why' });
  }
  if (x.policy && x.policy.decision === 'DENY') out.push({ text: `Policy: ${x.policy.reason}`, source: 'policy_decision' });
  if (x.route && (x.route.result === 'blocked' || x.route.result === 'ask')) {
    const when = x.route.unblock_at ? ` (retry after ${x.route.unblock_at})` : '';
    out.push({ text: `Routing: ${x.route.explanation ?? x.route.result}${when}`, source: 'route_decision' });
  }
  if (x.execution) {
    const r = x.execution.stop_reason || x.execution.exit_reason;
    if (r) out.push({ text: `The last execution ${present('execution', x.execution.state).label.toLowerCase()}: ${r}.`, source: 'execution' });
  }
  if (x.verification && x.verification.state !== 'PASSED') {
    const failed = (x.verification.checks ?? []).filter((c) => c.result !== 'pass').map((c) => c.name);
    out.push({
      text: `Verification: ${present('verification', x.verification.state).label}${failed.length ? ` (${failed.join(', ')})` : ''}.`,
      source: 'verification',
    });
  }
  if (x.review && x.review.state !== 'ACCEPTED' && x.review.verdict)
    out.push({ text: `Review verdict: ${x.review.verdict}.`, source: 'review' });
  if (!out.length) out.push({ text: 'No recorded reason.', source: 'none' });
  return out;
}

// ── time, for display only ──

export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—';
  const s = Math.round((now - Date.parse(iso)) / 1000);
  if (Number.isNaN(s)) return '—';
  if (s < 0) return `in ${fmt(-s)}`;
  return s < 45 ? 'just now' : `${fmt(s)} ago`;
}

function fmt(s: number): string {
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `${Math.round(s / 3600)} h`;
  return `${Math.round(s / 86400)} d`;
}
