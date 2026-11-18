// Which cached reads a stream frame makes stale (p16-design-gate §14.2).
// Frames carry identities only (ADR-0009): a frame never changes what is on
// screen, it only says which reads to repeat. A subject kind with no rule
// makes nothing stale — a view can be late, never wrong. Pure.
import { RULES } from './rules.ts';

/** Per subject kind, the read paths it can change: clients/app/tokens/invalidation.json,
 * generated into ./rules.ts (p17-design-gate A1). `{id}` is the subject's id, `*` one
 * path segment, a trailing `**` any rest (query included). */
export { RULES };

function compile(pattern: string, id: string): RegExp {
  const esc = (s: string) => s.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
  let rest = pattern;
  let tail = '(\\?.*)?';
  if (rest.endsWith('**')) {
    rest = rest.slice(0, -2);
    tail = '.*';
  }
  const body = rest
    .split('{id}')
    .map((part) => part.split('*').map(esc).join('[^/?]+'))
    .join(esc(id));
  return new RegExp('^' + body + tail + '$');
}

/** A predicate over cache keys (read paths) for one frame. */
export function staleBy(frame: { event: string; data?: unknown }): (path: string) => boolean {
  const subject = (frame.data as { subject?: { kind?: string; id?: string } } | undefined)?.subject;
  const rules = subject?.kind ? RULES[subject.kind] ?? [] : [];
  const rx = rules.map((p) => compile(p, subject?.id ?? ''));
  return (path) => rx.some((r) => r.test(path));
}
