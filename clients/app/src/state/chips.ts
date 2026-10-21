// The activity chip (ADR-0024 §6, rulebook §21 A-17; p21-design-gate D6): an
// `execution.hook` frame says only that an execution's agent asked Core about a
// tool call (ADR-0009). The execution is read again from Core, and the current
// action Core recorded when it judged that call (its class and a label, never raw
// input) becomes a chip on the mission's row, when that row is on screen.
// A chip lives ttl_ms (ttl_error_ms when Core refused or held the call). A row
// shows at most `cap` at once. A further chip waits in that row's queue, first in
// first out, and shows when a chip leaves, if its execution is still live then:
// Core is asked again at that moment, and work that has ended is dropped. The
// queue holds QUEUE_MAX per row; beyond that the oldest waiting chip is dropped.
// Nothing replays: a frame at or below the newest one heard, or an action already
// chipped, adds none. Under reduced motion the chip appears and leaves without its fade.
import { MOTIONS } from './motion.ts';
import type { Timeline } from './timeline.ts';

const M = MOTIONS['activity-chip'];
export const CHIP_TTL_MS = M.ttl_ms;
export const CHIP_TTL_ERROR_MS = M.ttl_error_ms;
export const CHIPS_PER_ROW = M.cap;
/** Chips waiting per row, beyond the CHIPS_PER_ROW shown. */
export const QUEUE_MAX = 6;
/** Mirrors `LIVE` in archeus/core/application/executions.py: the states that can still act. */
const LIVE = ['INTENT', 'STARTING', 'RUNNING', 'AWAITING_APPROVAL', 'PAUSING', 'PAUSED',
  'STOPPING', 'LOST', 'HANDING_OFF'];
/** A read Core does not answer in this long drops its chip, not the queue behind it. */
const READ_MS = 2000;
/** The dedupe marks kept: one per execution, the oldest forgotten first. */
const CHIPPED_MAX = 256;

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
  read: (execution: string) => Promise<{ mission_id: string; state?: string; current_action?: Current | null } | null>;
  readMs?: number;
}

export interface Chip {
  seq: number; // the frame it presents
  execution: string;
  text: string;
  ttl: number;
  still: boolean; // no fade (reduced motion)
  announce: boolean; // refused or held: also said to assistive technology
}

type Waiting = Omit<Chip, 'still'>;

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
  const t = [VERB[a.action_class] ?? a.action_class, a.label].filter(Boolean).join(' ');
  return a.decision in NOT_RUN ? `${NOT_RUN[a.decision]}: ${t}` : t;
}

/** The newest refused or held chip on a row: what assistive technology is told. */
export function announcement(list: readonly Chip[]): Chip | undefined {
  return [...list].reverse().find((c) => c.announce);
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
  private waiting = new Map<string, Waiting[]>(); // mission → its queue, oldest first
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

  /** Resolves once every frame and promotion heard so far is handled. */
  idle(): Promise<void> {
    return this.queue;
  }

  private async handle(f: ChipFrame) {
    const x = hookSubject(f);
    if (!x || f.id! <= this.heard) return;
    this.heard = f.id!;
    if (!this.shown.size) return;
    const e = await this.read(x);
    const a = e?.current_action;
    const row = e ? this.rows.get(e.mission_id) : undefined;
    if (!e || !a || !row || a.seq <= (this.chipped.get(x) ?? -Infinity)) return;
    this.chipped.set(x, a.seq);
    if (this.chipped.size > CHIPPED_MAX) this.chipped.delete(this.chipped.keys().next().value!);
    const ttl = a.decision === 'allow' ? CHIP_TTL_MS : CHIP_TTL_ERROR_MS;
    const chip: Waiting = { seq: f.id!, execution: x, text: chipText(a), ttl, announce: a.decision in NOT_RUN };
    if (row.length < CHIPS_PER_ROW) {
      this.present(e.mission_id, chip);
      return;
    }
    const w = this.waiting.get(e.mission_id) ?? [];
    if (w.length >= QUEUE_MAX) w.shift();
    w.push(chip);
    this.waiting.set(e.mission_id, w);
  }

  private present(mission: string, c: Waiting) {
    const fade = this.timeline.start('activity-chip', 'mission:' + mission, c.seq, this.host.now(), this.host.reduced());
    this.rows.set(mission, [...(this.rows.get(mission) ?? NONE), { ...c, still: !fade }]);
    this.listeners.forEach((l) => l());
  }

  /** Shows the queue's oldest chips while the row has room, each only if its execution is still live. */
  private async promote(mission: string) {
    const w = this.waiting.get(mission);
    if (!w) return;
    while (w.length && this.rows.has(mission) && this.rows.get(mission)!.length < CHIPS_PER_ROW) {
      const c = w.shift()!;
      const e = await this.read(c.execution);
      if (!this.rows.has(mission)) break; // the row left while Core answered
      if (!e || !LIVE.includes(e.state ?? '')) continue; // ended, or Core silent: never shown
      this.present(mission, c);
    }
    if (!w.length && this.waiting.get(mission) === w) this.waiting.delete(mission);
  }

  /** A read that Core does not answer in time yields null. */
  private async read(x: string) {
    let t: ReturnType<typeof setTimeout> | undefined;
    const late = new Promise<null>((r) => {
      t = setTimeout(() => r(null), this.host.readMs ?? READ_MS);
    });
    try {
      return await Promise.race([this.host.read(x).catch(() => null), late]);
    } finally {
      clearTimeout(t);
    }
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
      this.waiting.delete(mission);
    };
  }

  /** The chips on *mission*'s row, oldest first (the same array until they change). */
  chips(mission: string): readonly Chip[] {
    return this.rows.get(mission) ?? NONE;
  }

  /** The chip of *seq* on *mission*'s row has left (its time is up): the queue's next one may show. */
  dismiss(mission: string, seq: number) {
    const row = this.rows.get(mission);
    if (!row?.some((c) => c.seq === seq)) return;
    this.rows.set(mission, row.filter((c) => c.seq !== seq));
    this.listeners.forEach((l) => l());
    if (this.waiting.has(mission)) {
      this.queue = this.queue.then(() => this.promote(mission)).catch(() => undefined);
    }
  }

  subscribe(l: () => void): () => void {
    this.listeners.add(l);
    return () => void this.listeners.delete(l);
  }
}
