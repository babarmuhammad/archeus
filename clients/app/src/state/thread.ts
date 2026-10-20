// The thread's T1 form (ADR-0026 §1, design system §2, rulebook §20-§21
// A-05): a new Archeus message whose `Message.links` — Core's record of the
// world objects it touched — name an object whose row is on screen draws one
// line from the message to that row, once, in at most 600 ms, and is gone;
// what stays on the row is its T2 rule, which the digest decides (R5). The
// frame says only which message arrived (ADR-0009); the links are read from
// the message itself. Pure: the node tests run it directly.

export interface Ref {
  kind: string;
  id: string;
}

/** The objects a message's links name, in order, each once; an entry that is
 * not a {ref: {kind, id}} is not guessed into one. */
export function linksOf(links: readonly unknown[]): Ref[] {
  const out: Ref[] = [];
  for (const l of links) {
    const r = (l as { ref?: { kind?: unknown; id?: unknown } } | null)?.ref;
    if (typeof r?.kind !== 'string' || typeof r.id !== 'string') continue;
    if (!out.some((x) => x.kind === r.kind && x.id === r.id)) out.push({ kind: r.kind, id: r.id });
  }
  return out;
}

/** The message a stream frame says arrived, when it has a seq. */
export function messageHeard(f: { id?: number; event: string; data?: unknown }): string | null {
  const s = (f.data as { subject?: { kind?: string; id?: string } } | undefined)?.subject;
  return f.id !== undefined && f.event === 'message.created' && s?.kind === 'message' && s.id ? s.id : null;
}

/** The first linked object whose row is on screen: where the line goes. */
export const targetOf = (links: readonly Ref[], onScreen: (r: Ref) => boolean): Ref | null => links.find(onScreen) ?? null;

/** The polite announcement (rulebook §20). */
export const threadWords = (names: readonly string[]) => `Archeus updated ${names.join(', ')}`;

export interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** The line from the message to the row: it leaves the message on the side
 * facing the row and ends on the row's side facing the message, at their
 * vertical middles. Where it starts, how long it is and its angle. */
export function lineBetween(from: Box, to: Box): { x: number; y: number; length: number; angle: number } {
  const rightward = (to.left + to.right) / 2 > (from.left + from.right) / 2;
  const x = rightward ? from.right : from.left;
  const y = (from.top + from.bottom) / 2;
  const ex = rightward ? to.left : to.right;
  const ey = (to.top + to.bottom) / 2;
  return { x, y, length: Math.hypot(ex - x, ey - y), angle: Math.atan2(ey - y, ex - x) };
}
