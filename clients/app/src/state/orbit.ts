// The mark's orbit as Archeus's presence (ADR-0027 §2, rulebook §8, §21 A-07).
// The node's state is read, never animated: hollow while this client is not
// connected, attention while something needs the user, active while an attempt
// is running, neutral otherwise — the order of rulebook §7.1, where attention
// outranks active work. The travel is the only motion: one turn round the
// orbit per batch of `execution.*` frames, at most once per 5 s, never for an
// event already presented, and under reduced motion none at all. The favicon
// shows the same state, still.
import { MOTIONS } from './motion.ts';
import { present } from './present.ts';
import type { Timeline } from './timeline.ts';
import { pulseSubject, type PulseFrame } from './rowpulse.ts';

export type Presence = 'idle' | 'active' | 'attention' | 'disconnected';

export const ORBIT_EVERY_MS = MOTIONS['presence-orbit'].min_interval_ms;

export function presence(connected: boolean, needsYou: number, live: Live[]): Presence {
  if (!connected) return 'disconnected';
  if (needsYou > 0) return 'attention';
  return running(live).length ? 'active' : 'idle';
}

type Live = { kind?: string; state: string | null };

/** The live attempts that are running now: the halo's own class. An own call
 * in flight is live work but never an attempt, so it never animates (G8). */
export const running = <T extends Live>(live: T[]): T[] => live.filter((x) => x.kind !== 'own_call' && present('execution', x.state ?? '').cls === 'active');

/** The strip's "running": missions, Archeus's unit, with an attempt running now. */
export const runningMissions = (live: (Live & { mission_id: string | null })[]): number => new Set(running(live).map((x) => x.mission_id)).size;

/** The ids the live map lights: attempts only. An own call is never a map node (G8). */
export const attemptIds = <T extends Live & { id: string }>(live: T[]): string[] => live.filter((x) => x.kind !== 'own_call').map((x) => x.id);

export class Orbit {
  private seq = 0;
  private last = -Infinity;
  private listeners = new Set<() => void>();
  private timeline: Timeline;
  private host: { now: () => number; reduced: () => boolean };

  constructor(timeline: Timeline, host: { now: () => number; reduced: () => boolean }) {
    this.timeline = timeline;
    this.host = host;
  }

  frame(f: PulseFrame) {
    if (!pulseSubject(f)) return;
    const now = this.host.now();
    if (now - this.last < ORBIT_EVERY_MS) return;
    if (!this.timeline.start('presence-orbit', 'shell', f.id, now, this.host.reduced())) return;
    this.last = now;
    this.seq = f.id!;
    this.listeners.forEach((l) => l());
  }

  /** The seq of the newest turn (0: none). */
  current(): number {
    return this.seq;
  }

  subscribe(l: () => void): () => void {
    this.listeners.add(l);
    return () => void this.listeners.delete(l);
  }
}

// the mark's figure (www/components/site/Mark.tsx, the credited artwork re-cut
// as one monochrome glyph): the letter, its orbit, and the node on it
export const MARK = {
  letter: ['M16 3.6 L7.6 27.8 L4.8 27.8 Z', 'M16 3.6 L27.7 27.8 L23.5 27.8 Z', 'M8.6 21 Q16 28.2 23.4 21 Q16 23.6 8.6 21 Z'],
  tilt: -18,
  cx: 16,
  cy: 16.5,
  rx: 13.2,
  ry: 5.4,
  at: -42, // the node's place on the orbit, degrees
  r: 1.7,
} as const;

/** The favicon: the mark on the dark tile, its node in the presence's colour.
 * *dark* is the dark theme's token table. */
export function favicon(p: Presence, dark: Record<string, string>): string {
  const { letter, tilt, cx, cy, rx, ry, at, r } = MARK;
  const a = (at * Math.PI) / 180;
  const x = (cx + rx * Math.cos(a)).toFixed(2);
  const y = (cy + ry * Math.sin(a)).toFixed(2);
  const ink = dark.text;
  const node =
    p === 'disconnected'
      ? `<circle cx="${x}" cy="${y}" r="${r}" fill="${dark.bg}" stroke="${ink}" stroke-width="0.8"/>`
      : `<circle cx="${x}" cy="${y}" r="${r}" fill="${p === 'active' ? dark['state.active'] : p === 'attention' ? dark['state.attention'] : ink}"/>`;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="${dark.bg}"/>` +
    `<g fill="${ink}">${letter.map((d) => `<path d="${d}"/>`).join('')}</g>` +
    `<g transform="rotate(${tilt} ${cx} ${cy})"><ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="none" stroke="${ink}" stroke-width="1.35" opacity="0.55"/>${node}</g></svg>`;
  return 'data:image/svg+xml,' + encodeURIComponent(svg);
}
