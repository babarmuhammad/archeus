// The execution pulse on rows (ADR-0024 §6, rulebook §21 A-02, the DOM form of
// the graph's pulse): an `execution.*` frame says only WHICH execution moved
// (ADR-0009). Its mission is read again from Core, and the pulse is one CSS
// opacity step on that mission's row, when Core's read says the execution is
// live and the row is on screen — at most one per row per min_interval_ms.
// Nothing replays: the timeline refuses a seq it has presented, and a row
// shows only a pulse that began while it was on screen. Under reduced motion,
// or while frames run slow, no pulse starts but the event counts as presented.
import { MOTIONS } from './motion.ts';
import { present } from './present.ts';
import type { Timeline } from './timeline.ts';

export const ROW_PULSE_EVERY_MS = MOTIONS['row-pulse'].min_interval_ms;

export interface PulseFrame {
  id?: number;
  event: string;
  data?: unknown;
}

export interface PulseHost {
  now: () => number;
  reduced: () => boolean;
  degraded: () => boolean; // frames run slow (Loop.degraded)
  read: (execution: string) => Promise<{ mission_id: string; state: string }>;
}

/** The execution a frame names, when the frame could pulse a row. */
export function pulseSubject(f: PulseFrame): string | null {
  const subject = (f.data as { subject?: { kind?: string; id?: string } } | undefined)?.subject;
  if (f.id === undefined || !f.event.startsWith('execution.') || subject?.kind !== 'execution' || !subject.id) return null;
  return subject.id;
}

export class RowPulses {
  private shown = new Map<string, number>(); // mission → rows of it on screen
  private last = new Map<string, number>(); // mission → presentation time of its last pulse
  private seqs = new Map<string, number>(); // mission → seq of its newest pulse
  private listeners = new Set<() => void>();
  private queue: Promise<void> = Promise.resolve();
  private timeline: Timeline;
  private host: PulseHost;

  constructor(timeline: Timeline, host: PulseHost) {
    this.timeline = timeline;
    this.host = host;
  }

  /** Frames are handled one after another, so a slow read never lets an
   * older event overtake a newer one. */
  frame(f: PulseFrame): Promise<void> {
    this.queue = this.queue.then(() => this.handle(f)).catch(() => undefined);
    return this.queue;
  }

  private async handle(f: PulseFrame) {
    const x = pulseSubject(f);
    if (!x || !this.shown.size) return;
    if (this.quiet()) {
      this.timeline.start('row-pulse', '', f.id, this.host.now(), true);
      return;
    }
    const e = await this.host.read(x);
    if (!this.shown.has(e.mission_id) || present('execution', e.state).cls !== 'active') return;
    const now = this.host.now();
    if (now - (this.last.get(e.mission_id) ?? -Infinity) < ROW_PULSE_EVERY_MS) return;
    if (!this.timeline.start('row-pulse', 'mission:' + e.mission_id, f.id, now, this.quiet())) return;
    this.last.set(e.mission_id, now);
    this.seqs.set(e.mission_id, f.id!);
    this.listeners.forEach((l) => l());
  }

  private quiet() {
    return this.host.reduced() || this.host.degraded();
  }

  /** A row of *mission* came on screen; the returned function takes it off. */
  show(mission: string): () => void {
    this.shown.set(mission, (this.shown.get(mission) ?? 0) + 1);
    return () => {
      const n = (this.shown.get(mission) ?? 1) - 1;
      if (n) this.shown.set(mission, n);
      else this.shown.delete(mission);
    };
  }

  /** The seq of *mission*'s newest pulse (0: none). */
  seq(mission: string): number {
    return this.seqs.get(mission) ?? 0;
  }

  subscribe(l: () => void): () => void {
    this.listeners.add(l);
    return () => void this.listeners.delete(l);
  }
}
