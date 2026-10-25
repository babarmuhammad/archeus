// How a row LOOKS (p16-design-gate §6). Every function here maps fields Core
// returned to text and glyphs; none decides what a state means, whether an
// action is allowed, where work runs or whether it is done — those are the
// rows' (P9–P15). Pure: the node tests and the mutation suite run it directly.
import { CLASSES, ID_KINDS, LABELS, PRESENTATION, TRIGGERS } from './presentation.ts';

/** Whether the state machine has *trigger* from *state* at all — what a button
 * may be offered for. Whether it may fire now is Core's (guards, P9). */
export const offers = (machine: string, state: string, ...trigger: string[]) =>
  trigger.some((t) => TRIGGERS[machine]?.[state]?.includes(t) ?? false);

/** Whether *state* ends its machine: no trigger leaves it (a mission's
 * COMPLETED and CANCELLED). Core still refuses whatever it refuses. */
export const ended = (machine: string, state: string) => !TRIGGERS[machine]?.[state]?.length;

const STOPPED: Record<string, string> = {
  user: 'stopped by you',
  estop: 'stopped by the emergency stop',
  ceiling: 'stopped: the account reached its ceiling',
  limit: 'stopped: the account reached its usage limit',
  breaker: 'stopped: the account kept failing and was taken out of use',
  pause_timeout: 'stopped: it did not pause in time',
  cancel: 'stopped: its mission was cancelled',
  binding: 'stopped: what it was bound to changed',
  disarmed: 'stopped: Archeus was disarmed',
  workspace: 'stopped: its workspace could not be made',
  path_too_long: 'stopped: its workspace path is too long for Git; use a shorter Archeus folder',
  spawn: 'stopped: its agent CLI could not start a process; Archeus tries again',
};
const FAILED: Record<string, string> = {
  resource: 'the account or its provider failed',
  auth: "the account's sign-in failed",
  limit: 'the account reached its usage limit',
  task: 'the work itself failed',
};

/** Why an attempt ended badly, in words, from the fields Core recorded
 * (rulebook Appendix B: "✕ red + plain reason; raw code under Details");
 * null for an attempt that did not fail. */
export function endReason(x: { state: string; exit_reason?: unknown; stop_reason?: unknown; failure?: unknown }): string | null {
  if (present('execution', x.state).cls !== 'failed') return null;
  const s = (v: unknown) => (typeof v === 'string' ? v : '');
  switch (s(x.exit_reason)) {
    case 'killed':
      return STOPPED[s(x.stop_reason)] ?? 'stopped';
    case 'lost':
      return 'Archeus lost its process';
    case 'rejected':
      return 'an approval it needed was rejected';
    case 'abandoned':
      return 'it never started';
    default:
      return `it ended with an error: ${FAILED[s(x.failure)] ?? 'the process exited with an error'}`;
  }
}

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

// ── plain language: a value as words, an identifier behind Details (R1, rulebook §15) ──

const MENTION = new RegExp(`\\b(${Object.keys(ID_KINDS).join('|')})_[0-9A-HJKMNP-TV-Z]{26}\\b`, 'g');

export type Piece = string | { kind: string; id: string };

/** Core's own sentences sometimes name an object by its id ("plan v1 approved
 * (approval apr_…)"). Split such a sentence into its words and the objects it
 * names, so each is shown as that object and never as its id; the kind word
 * the sentence already put before the id is not said twice. */
export function mentions(text: string): Piece[] {
  const out: Piece[] = [];
  let last = 0;
  for (const m of text.matchAll(MENTION)) {
    const kind = ID_KINDS[m[1]];
    let before = text.slice(last, m.index);
    const word = kind.replace(/_/g, ' ') + ' ';
    if (before.toLowerCase().endsWith(word)) before = before.slice(0, -word.length);
    if (before) out.push(before);
    out.push({ kind, id: m[0] });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** A field name as words: `as_of_seq` → `As of seq`. */
export const words = (k: string) => (k.charAt(0).toUpperCase() + k.slice(1)).replace(/_/g, ' ');

/** Fields that hold an identifier, a digest or a git revision: they belong in
 * Details, never in the default view. Read by NAME, so a value that merely
 * looks like an id is not guessed at. */
const TECH = /(^|_)(id|ids|digest|hash|sha|sha256)$|^(revision|last_revision|evaluated_against|policy_version|instance|home_ref|integration_branch|integration_head)$/;

const scalar = (v: unknown) => v === null || ['string', 'number', 'boolean', 'undefined'].includes(typeof v);

/** Split a row Core returned into what a person reads and its identifiers,
 * each labelled by where it sits (`Subject · id`). Nothing is dropped: every
 * technical scalar comes back as a Details row. */
export function technical(v: unknown, at = ''): [unknown, [string, string][]] {
  const label = (k: string) => (at ? `${at} · ${words(k).toLowerCase()}` : words(k));
  if (Array.isArray(v)) {
    const tech: [string, string][] = [];
    const clean = v.map((x, i) => {
      const [c, t] = technical(x, `${at || 'Item'} ${i + 1}`);
      tech.push(...t);
      return c;
    });
    return [clean, tech];
  }
  if (v && typeof v === 'object') {
    const out: Record<string, unknown> = {};
    const tech: [string, string][] = [];
    for (const [k, x] of Object.entries(v)) {
      if (TECH.test(k) && (scalar(x) || (Array.isArray(x) && x.every(scalar)))) {
        if (x !== null && x !== undefined && x !== '' && !(Array.isArray(x) && !x.length)) tech.push([label(k), Array.isArray(x) ? x.join(', ') : String(x)]);
      } else {
        const [c, t] = technical(x, label(k));
        out[k] = c;
        tech.push(...t);
      }
    }
    return [out, tech];
  }
  return [v, []];
}

/** A value on one line: scalars as themselves, lists joined, objects as
 * `Key value` pairs — never JSON. */
export function inline(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  if (Array.isArray(v)) return v.length ? v.map(inline).join(', ') : '—';
  if (typeof v === 'object') return Object.entries(v).map(([k, x]) => `${words(k)} ${inline(x)}`).join(' · ') || '—';
  return String(v);
}

type Test = string | number | boolean | null | { glob?: string; not_glob?: string };

const test = (k: string, t: Test) =>
  t && typeof t === 'object'
    ? 'glob' in t
      ? `${words(k).toLowerCase()} matches ${t.glob}`
      : `${words(k).toLowerCase()} does not match ${t.not_glob}`
    : `${words(k).toLowerCase()} is ${String(t)}`;

/** An automation trigger (p14 §L: `{kind: 'event', type, where}`) in words. */
export function triggerText(t: { type?: unknown; where?: Record<string, Test> | null }): string {
  const where = Object.entries(t.where ?? {}).map(([k, v]) => test(k, v));
  return `When a ${String(t.type ?? 'recorded')} event happens${where.length ? `, where ${where.join(' and ')}` : ''}`;
}

/** What an automation asks for (`{title, objective, success_criteria}`) in words. */
export function templateText(t: { title?: unknown; objective?: unknown; success_criteria?: unknown[] }): string {
  const n = (t.success_criteria ?? []).length;
  return `Start a mission “${String(t.title ?? '')}”: ${String(t.objective ?? '')}${n ? ` (${n} success ${n === 1 ? 'criterion' : 'criteria'})` : ''}`;
}

/** Why a run fired (`{type, where: {key: {test, value}}}`) in words. */
export function firedText(w: { type?: unknown; where?: Record<string, { test: Test; value: unknown }> | null }): string {
  const seen = Object.entries(w.where ?? {}).map(([k, x]) => `${words(k).toLowerCase()} was ${inline(x.value)}`);
  return `It fired on a ${String(w.type ?? 'recorded')} event${seen.length ? `: ${seen.join(', ')}` : ''}.`;
}

/** An account's newest usage reading (`{windows, resets_at, observed_at, source}`)
 * in words; a window not reported is not shown as 0. */
export function usageText(u: { windows?: Record<string, number | null>; resets_at?: Record<string, string>; observed_at?: number | null; source?: string } | null, now = Date.now()): string {
  if (!u) return 'not observed';
  const w = Object.entries(u.windows ?? {}).map(([k, pct]) => {
    const at = u.resets_at?.[k];
    return `${words(k).toLowerCase()} ${pct === null || pct === undefined ? 'unknown' : `${pct}%`}${at ? ` (resets ${ago(at, now)})` : ''}`;
  });
  const seen = typeof u.observed_at === 'number' ? `, observed ${ago(new Date(u.observed_at * 1000).toISOString(), now)}` : '';
  return `${w.join(' · ') || 'no window reported'}${seen}${u.source ? ` from ${u.source}` : ''}`;
}

/** Today's consumption of an account (ADR-0048 §3, G12): a figure not fully
 * reported is a lower bound, and nothing reported is unknown — never 0. Work
 * still in flight has not written its usage yet, so it is unknown while it runs. */
export function consumptionText(l: { tokens_today: number; cost_today: number; running: number; complete: { tokens: boolean; cost: boolean } }): string {
  const busy = l.running;
  const one = (n: number, done: boolean, say: (n: number) => string, what: string) =>
    done && !busy ? say(n) : n ? `at least ${say(n)}` : `${what} unknown${busy ? ` (${busy} running)` : ''}`;
  return `${one(l.tokens_today, l.complete.tokens, (n) => `${n.toLocaleString('en-US')} tokens`, 'tokens')} · ${one(l.cost_today, l.complete.cost, (n) => `$${n.toFixed(2)}`, 'cost')}`;
}

/** What runs on an account now (ADR-0043 §3, G8): its live work, by name. */
export function consumersText(c: { kind: string; task_key?: string | null; attempt?: number | null; purpose?: string | null }[]): string {
  if (!c.length) return 'nothing';
  return c.map((x) => (x.kind === 'own_call' ? `an own call for the ${(x.purpose ?? '').split('_').join(' ')}` : `${x.task_key} attempt ${x.attempt}`)).join('; ');
}

/** The header's count of live work: attempts are "running"; own calls are
 * counted apart, because they never animate (G8). */
export function liveCountText(live: { kind?: string }[]): string {
  const attempts = live.filter((x) => x.kind !== 'own_call').length;
  const own = live.length - attempts;
  return `${attempts} running${own ? ` · ${own} own call${own === 1 ? '' : 's'} in flight` : ''}`;
}

/** The offline header's line: the live count, then whether the emergency stop is engaged. */
export function headerLine(s: { live: { kind?: string }[]; armed: boolean }): string {
  return `${liveCountText(s.live)}${s.armed ? '' : ' · Emergency stop engaged'}`;
}

// ── the emergency stop in Control → About (P20 F7, F8) ──

/** How a press ended, for a caller that says it itself (ActionButton's
 * `report`): Core's answer; a refusal (4xx: nothing was done); a failure inside
 * Core (5xx); or no answer at all (whether Core acted is not known). */
export type Outcome =
  | { ok: true; out: unknown }
  | { ok: false; kind: 'refused' | 'failed' | 'network'; why: string };

/** Why a step-up Core will ask for cannot be answered from here yet (P9's
 * approvals, D10's re-arm): this client has no PIN, or fewer than its six
 * digits are typed. An empty proof is a wrong one and counts toward the
 * revocation (T-098). */
export function stepUpBlocked(capability: string | undefined, pin: string): string | null {
  if (capability === 'none') return 'This client has no PIN: it cannot satisfy a step-up.';
  return capability === 'pin' && pin.length < 6 ? 'Enter this client’s PIN first.' : null;
}

/** Core's armed state in words; *armed* undefined is "Core cannot be reached",
 * never a guess from an older read. */
export function armedText(armed: boolean | undefined): string {
  if (armed === undefined)
    return 'Core cannot be reached, so whether it is armed is not known here. The tray’s Emergency stop and “archeus estop” work without Core.';
  return armed ? 'Armed: Archeus accepts new work.' : 'Emergency stop engaged: Archeus refuses new work until you re-arm.';
}

/** One status line for what Core answered to an emergency stop or a re-arm, in
 * the tray's words, and the armed state it describes (`when`; undefined when
 * no answer came). A line never claims more than Core said. */
export function estopSaid(act: 'estop' | 'rearm', o: Outcome): { text: string; alert: boolean; when?: boolean } {
  if (o.ok) {
    const out = (o.out ?? {}) as { stopped?: unknown[]; armed?: boolean };
    if (act === 'estop')
      return { text: `Emergency stop: ${out.stopped?.length ?? 0} execution(s) stopped; Core is disarmed until re-armed.`, alert: false, when: out.armed };
    return out.armed
      ? { text: 'Re-armed: Core accepts new work again.', alert: false, when: true }
      : { text: 'Core answered, but it is still disarmed.', alert: true, when: false };
  }
  const what = act === 'estop' ? 'nothing is confirmed stopped' : 'it stays disarmed';
  if (o.kind === 'network')
    return { text: act === 'estop'
      ? 'Core did not answer, so nothing is confirmed stopped. The tray’s Emergency stop and “archeus estop” stop without Core.'
      : 'Core did not answer, so the re-arm is not confirmed.', alert: true };
  if (o.kind === 'failed')
    return { text: `The ${act === 'estop' ? 'emergency stop' : 're-arm'} failed inside Core, so ${what}: ${o.why}`, alert: true, when: act === 'rearm' ? false : true };
  return { text: act === 'estop'
    ? `Core refused the emergency stop, so nothing was stopped: ${o.why}`
    : `Core refused the re-arm, so it stays disarmed: ${o.why}`, alert: true, when: act === 'rearm' ? false : true };
}

/** P20 (ADR-0049): what became of one item an execution's settings sources load. */
const INVENTORY_STATUS: Record<string, string> = {
  excluded: 'excluded',
  opted_in: 'opted in',
  not_excludable: 'loaded, not excludable',
  recorded_only: 'loaded, recorded only (fallback)',
  not_found: 'opted in, not found',
  builtin: "loaded, built into the CLI (outside Archeus's controls)",
};
const INVENTORY_TYPE: Record<string, string> = {
  hook: 'hook',
  permission: 'permission rule',
  plugin: 'plugin',
  skill: 'skill',
  mcp_server: 'MCP server',
  claude_md: 'CLAUDE.md',
  managed_settings: 'managed settings',
  unreadable: 'unreadable file',
};

type InventoryLike = {
  unavailable?: string;
  observed?: boolean;
  truncated?: boolean;
  flags?: {
    setting_sources?: string[];
    mcp_servers?: { name: string }[];
    disable_slash_commands?: boolean;
    plugin_dirs?: { name: string; path?: string | null }[];
  };
  items?: { source: string; type: string; name: string; status: string }[];
};

/** [label, text] rows of an execution's recorded inventory (ADR-0049): the
 * flags it was spawned with, then every item and what became of it. Words
 * only; what was excluded is Core's record, never decided here. */
export function inventoryLines(inv: InventoryLike | null | undefined): [string, string][] {
  if (!inv) return [['Inherited settings', 'not recorded for this execution']];
  if (inv.unavailable) return [['Inherited settings', inv.unavailable]];
  const f = inv.flags ?? {};
  const names = (xs: string[]) => xs.join(', ') || 'none';
  const rows: [string, string][] = [
    ['Settings sources loaded', names(f.setting_sources ?? [])],
    ['MCP servers', 'only the opted in: ' + names((f.mcp_servers ?? []).map((s) => s.name))],
    ['Skills', f.disable_slash_commands ? 'disabled' : 'enabled: a skill is opted in'],
    ['Plugins for this session', names((f.plugin_dirs ?? []).filter((d) => d.path).map((d) => d.name))],
    ['Observed on a real run', inv.observed ? 'yes' : 'no: predicted before the spawn, by the rule PV-19 observed'],
  ];
  for (const i of inv.items ?? [])
    rows.push([`${INVENTORY_TYPE[i.type] ?? i.type} (${i.source})`, `${i.name}: ${INVENTORY_STATUS[i.status] ?? i.status}`]);
  if (inv.truncated) rows.push(['More', 'the record was cut; not every item is listed']);
  return rows;
}
