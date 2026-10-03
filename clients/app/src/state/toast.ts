// The completion toast (rulebook §17, §21 A-13; D-8, §46.1): work that ran at
// least 10 s finished while nothing on screen showed it. An `execution.ended`
// frame says only WHICH attempt ended (ADR-0009); the attempt is read again
// from Core, and only an attempt Core read as ENDED_OK, whose own started_at
// and ended_at are 10 s or more apart, and whose mission and attempt have no
// row or inspector on screen, gives a toast. A failure is never toasted: it
// shows where it happened (§17). One at a time — a newer completion replaces
// the toast showing — and nothing replays: the timeline refuses a seq it has
// presented. Under reduced motion the toast still appears, without its fade.
import { MOTIONS } from './motion.ts';
import type { Timeline } from './timeline.ts';

export const TOAST_AFTER_MS = 10_000;
export const TOAST_TTL_MS = MOTIONS.toast.ttl_ms ?? 4000;

export interface ToastFrame {
  id?: number;
  event: string;
  data?: unknown;
}

export interface Ended {
  id: string;
  mission_id: string;
  attempt: number;
  state: string;
  started_at?: unknown;
  ended_at?: unknown;
}

export interface ToastHost {
  now: () => number;
  reduced: () => boolean;
  read: (execution: string) => Promise<Ended>;
  title: (mission: string) => Promise<string | null>;
  onScreen: (mission: string, execution: string) => boolean;
}

export interface Toast {
  seq: number;
  mission: string;
  attempt: number;
  title: string | null;
  still: boolean; // no fade (reduced motion)
}

/** The attempt a frame says ended, or null. */
export function endedSubject(f: ToastFrame): string | null {
  const s = (f.data as { subject?: { kind?: string; id?: string } } | undefined)?.subject;
  return f.id !== undefined && f.event === 'execution.ended' && s?.kind === 'execution' && s.id ? s.id : null;
}

/** How long Core says the attempt ran, in ms, or null when it does not say. */
export function ranFor(e: Ended): number | null {
  const a = typeof e.started_at === 'string' ? Date.parse(e.started_at) : NaN;
  const b = typeof e.ended_at === 'string' ? Date.parse(e.ended_at) : NaN;
  return Number.isFinite(a) && Number.isFinite(b) ? b - a : null;
}

/** Whether Core's read of an ended attempt deserves a toast (D-8). */
export const deserves = (e: Ended) => e.state === 'ENDED_OK' && (ranFor(e) ?? 0) >= TOAST_AFTER_MS;

export class Toasts {
  private current: Toast | null = null;
  private seen = -Infinity;
  private listeners = new Set<() => void>();
  private queue: Promise<void> = Promise.resolve();
  private timeline: Timeline;
  private host: ToastHost;

  constructor(timeline: Timeline, host: ToastHost) {
    this.timeline = timeline;
    this.host = host;
  }

  /** Frames are handled in order, so a slow read never lets an older end
   * overtake a newer one. */
  frame(f: ToastFrame): Promise<void> {
    this.queue = this.queue.then(() => this.handle(f)).catch(() => undefined);
    return this.queue;
  }

  private async handle(f: ToastFrame) {
    const x = endedSubject(f);
    // no replay: an end at or below the newest one heard is never toasted
    if (!x || f.id! <= this.seen) return;
    this.seen = f.id!;
    const e = await this.host.read(x);
    if (!deserves(e) || this.host.onScreen(e.mission_id, e.id)) return;
    // the fade is the registered motion; under reduced motion the timeline
    // refuses it and the toast appears and leaves at once
    const fade = this.timeline.start('toast', 'shell', f.id, this.host.now(), this.host.reduced());
    this.current = { seq: f.id!, mission: e.mission_id, attempt: e.attempt, title: await this.host.title(e.mission_id), still: !fade };
    this.listeners.forEach((l) => l());
  }

  /** The toast showing, if any. */
  showing(): Toast | null {
    return this.current;
  }

  /** The toast of *seq* has left (its time is up). A newer one stays. */
  dismiss(seq: number) {
    if (this.current?.seq !== seq) return;
    this.current = null;
    this.listeners.forEach((l) => l());
  }

  subscribe(l: () => void): () => void {
    this.listeners.add(l);
    return () => void this.listeners.delete(l);
  }
}
