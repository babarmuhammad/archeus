// The activity chip (ADR-0024 §6, rulebook §21 A-17; p21-design-gate D6): an
// `execution.hook` frame says only that an execution's agent asked Core about a
// tool call (ADR-0009). The execution is read again from Core, and the current
// action Core recorded when it judged that call — its class and a label, never
// raw input — becomes a chip on the mission's row, when that row is on screen.
// A chip lives ttl_ms (ttl_error_ms when Core refused or held the call), at most
// `cap` on a row: a further chip is dropped, not queued. Nothing replays: a
// frame at or below the newest one heard, or an action already chipped, adds
// none. Under reduced motion the chip appears and leaves without its fade.
import { MOTIONS } from './motion.ts';
import type { Timeline } from './timeline.ts';

const M = MOTIONS['activity-chip'];
export const CHIP_TTL_MS = M.ttl_ms;
export const CHIP_TTL_ERROR_MS = M.ttl_error_ms;
export const CHIPS_PER_ROW = M.cap;

export interface ChipFrame {
  id?: number;
  event: string;
  data?: unknown;
}

export interface Current {
  action_class: string;
  label: string;
  decision: string;
  seq: number;
}

export interface ChipHost {
  now: () => number;
  reduced: () => boolean;
  read: (execution: string) => Promise<{ mission_id: string; current_action?: Current | null }>;
}

export interface Chip {
  seq: number; // the frame it presents
  text: string;
  ttl: number;
  still: boolean; // no fade (reduced motion)
}

const VERB: Record<string, string> = {
  read: 'reading',
  write_repo: 'editing',
  exec: 'running',
  web: 'fetching',
  git_commit: 'committing',
  git_push: 'pushing',
  deploy: 'deploying',
  external_comm: 'sending to',
  destructive: 'deleting',
  install: 'installing',
  spend: 'spending',
  personal_data: 'personal data',
  credential: 'credential',
};
const NOT_RUN: Record<string, string> = { deny: 'refused', halt: 'held' };

/** The chip's words: what the agent asked, and whether Core let it. */
export function chipText(a: Current): string {
  const t = `${VERB[a.action_class] ?? a.action_class} ${a.label}`;
  return a.decision in NOT_RUN ? `${NOT_RUN[a.decision]}: ${t}` : t;
}

/** The execution a frame says asked about a tool call, or null. */
export function hookSubject(f: ChipFrame): string | null {
  const s = (f.data as { subject?: { kind?: string; id?: string } } | undefined)?.subject;
  return f.id !== undefined && f.event === 'execution.hook' && s?.kind === 'execution' && s.id ? s.id : null;
}

const NONE: readonly Chip[] = [];

export class Chips {
  private rows = new Map<string, readonly Chip[]>(); // mission with a row on screen → its chips
  private shown = new Map<string, number>(); // mission → rows of it on screen
  private chipped = new Map<string, number>(); // execution → seq of its newest chipped action
  private heard = -Infinity;
  private listeners = new Set<() => void>();
  private queue: Promise<void> = Promise.resolve();
  private timeline: Timeline;
  private host: ChipHost;

  constructor(timeline: Timeline, host: ChipHost) {
    this.timeline = timeline;
    this.host = host;
  }

  /** Frames are handled in order, so a slow read never lets an older action
   * overtake a newer one. */
  frame(f: ChipFrame): Promise<void> {
    this.queue = this.queue.then(() => this.handle(f)).catch(() => undefined);
    return this.queue;
  }

  private async handle(f: ChipFrame) {
    const x = hookSubject(f);
    if (!x || f.id! <= this.heard) return;
    this.heard = f.id!;
    if (!this.shown.size) return;
    const e = await this.host.read(x);
    const a = e.current_action;
    const row = this.rows.get(e.mission_id);
    if (!a || !row || a.seq <= (this.chipped.get(x) ?? -Infinity)) return;
    this.chipped.set(x, a.seq);
    if (row.length >= CHIPS_PER_ROW) return;
    const fade = this.timeline.start('activity-chip', 'mission:' + e.mission_id, f.id, this.host.now(), this.host.reduced());
    const ttl = a.decision === 'allow' ? CHIP_TTL_MS : CHIP_TTL_ERROR_MS;
    this.rows.set(e.mission_id, [...row, { seq: f.id!, text: chipText(a), ttl, still: !fade }]);
    this.listeners.forEach((l) => l());
  }

  /** A row of *mission* came on screen; the returned function takes it off. */
  show(mission: string): () => void {
    this.shown.set(mission, (this.shown.get(mission) ?? 0) + 1);
    if (!this.rows.has(mission)) this.rows.set(mission, NONE);
    return () => {
      const n = (this.shown.get(mission) ?? 1) - 1;
      if (n) return void this.shown.set(mission, n);
      this.shown.delete(mission);
      this.rows.delete(mission);
    };
  }

  /** The chips on *mission*'s row, oldest first (the same array until they change). */
  chips(mission: string): readonly Chip[] {
    return this.rows.get(mission) ?? NONE;
  }

  /** The chip of *seq* on *mission*'s row has left (its time is up). */
  dismiss(mission: string, seq: number) {
    const row = this.rows.get(mission);
    if (!row?.some((c) => c.seq === seq)) return;
    this.rows.set(mission, row.filter((c) => c.seq !== seq));
    this.listeners.forEach((l) => l());
  }

  subscribe(l: () => void): () => void {
    this.listeners.add(l);
    return () => void this.listeners.delete(l);
  }
}
