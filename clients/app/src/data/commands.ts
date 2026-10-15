// Sending a command (p16-design-gate §13.3). One idempotency key per USER
// ACTION, reused by every retry of that action, so Core applies it once; no
// command is queued, and nothing is shown as done until a re-read says so.
// What a refusal means is Core's — this only turns its answer into words. Pure
// but for the key generator, which is injectable for tests.

export interface Refusal {
  status: number;
  code: string;
  detail: Record<string, unknown>;
}

export const newKey = () =>
  (typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : String(Math.random()).slice(2) + Date.now().toString(36));

/** An action with its own key: `send` may be called again (a network retry,
 * a `503 busy`) and carries the same key every time. */
export function action<T>(send: (key: string) => Promise<T>, key: string = newKey()) {
  return { key, send: () => send(key) };
}

/** The request body of an approval decision: it echoes the `action_hash` the
 * card displayed (P9 X02), never the approval's id or a recomputed hash. */
export function decideBody(
  a: { action_hash: string; version: number },
  decision: 'approve' | 'reject' | 'request_changes',
  key: string,
  extra: { note?: string; step_up?: string } = {},
) {
  return { decision, action_hash: a.action_hash, expected_version: a.version, idempotency_key: key, ...extra };
}

/** Core's refusal in words, from its own code and detail. */
export function explain(r: Refusal): string {
  const d = r.detail ?? {};
  switch (r.code) {
    case 'scope_required':
      return `This client does not hold the “${String(d.scope)}” scope.`;
    case 'not_permitted':
      return `Not permitted: ${String(d.why ?? '')}`;
    case 'version_conflict':
      return 'This changed since you opened it. It has been read again — act on what is there now.';
    case 'guard_failed':
      return `Refused: ${String(d.reason ?? d.guard ?? 'a guard refused')}`;
    case 'invalid_transition':
      return `Not possible from ${String(d.from)}${d.trigger ? ` (${String(d.trigger)})` : ''}.`;
    case 'policy_denied':
      return `The policy denies it: ${String(d.reason ?? '')}`;
    case 'approval_not_eligible':
      return `This approval cannot be decided now: ${String(d.why ?? '')}`;
    case 'queued_intent_refused':
      return 'Archeus refused a command that was sent late. Nothing was changed.';
    case 'host_not_allowed':
      return 'Only from the computer running Archeus.';
    case 'core_starting':
      return 'Archeus is starting. Try again in a moment.';
    case 'busy':
      return 'Archeus is busy. It will be retried once.';
    case 'unauthenticated':
      return 'This client is signed out.';
    case 'invalid_request':
      return `Invalid: ${d.field ? String(d.field) + ' ' : ''}${String(d.why ?? '')}`;
    case 'not_found':
      return 'It no longer exists.';
    case 'refused':
      return `Refused: ${String(d.why ?? '')}`;
    case 'network':
      return 'Archeus could not be reached. Nothing was sent.';
    default:
      return `${r.status} ${r.code}`;
  }
}

/** The key for the user's next attempt at the same action: after a network
 * failure nobody knows whether Core applied it, so "try again" must reuse the
 * key (Core then answers the original result); after any answer it is new. */
export const keyAfter = (prev: string, outcome: 'ok' | 'refused' | 'network', fresh = newKey) =>
  outcome === 'network' ? prev : fresh();

/** Retry once, with the same key, only when Core asked for it. */
export const retryable = (r: Refusal) => r.code === 'busy' || r.code === 'core_starting';

// ── the motion preference (§18.4) ──

export type MotionPref = 'system' | 'reduced';

export const motionMode = (systemReduced: boolean, pref: MotionPref): 'full' | 'reduced' =>
  systemReduced || pref === 'reduced' ? 'reduced' : 'full';
