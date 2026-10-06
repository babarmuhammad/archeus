// The read cache (p16-design-gate §14.1, D8): one entry per read path, fetched
// when a component first shows it, re-read only when a stream frame makes it
// stale (invalidation.ts) or the connection resyncs. It holds Core's answers
// and nothing else — no optimistic write, no derived state.
import { useEffect, useSyncExternalStore } from 'react';
import type { Send } from '../api/generated';
import { CoreError } from '../api/transport';
import { initial, next, type ConnState, type Signal } from './connection';

export interface Frame {
  event: string;
  data?: unknown;
}

export interface Snapshot<T> {
  data?: T;
  error?: CoreError;
  pending: boolean;
  gen: number; // the connection generation it was read in
  seq?: number; // the event head Core read it at (X-Archeus-Seq)
}

interface Entry {
  snap: Snapshot<unknown>;
  listeners: Set<() => void>;
  inflight: boolean;
  again: boolean;
}

const EMPTY: Snapshot<never> = { pending: true, gen: -1 };

class Store {
  private entries = new Map<string, Entry>();
  private send: Send | null = null;
  private stale: ((path: string) => boolean)[] = [];
  private timer: ReturnType<typeof setTimeout> | undefined;
  conn: ConnState = initial();
  private connListeners = new Set<() => void>();
  private frameListeners = new Set<(f: Frame) => void>();
  readonly seqs = new Map<string, number>();

  /** A stream frame arrived (after it invalidated what it makes stale). A
   * listener may only react to the frame's type and subject — never read its
   * payload as state (P14): the graph pulses a live execution's edge (P18 A8). */
  frame(f: Frame) {
    this.frameListeners.forEach((l) => l(f));
  }

  onFrame(l: (f: Frame) => void) {
    this.frameListeners.add(l);
    return () => void this.frameListeners.delete(l);
  }

  configure(send: Send) {
    this.send = send;
  }

  signal(sig: Signal) {
    const before = this.conn;
    this.conn = next(this.conn, sig);
    if (this.conn !== before) {
      this.connListeners.forEach((l) => l());
      if (this.conn.gen !== before.gen) this.invalidateAll();
      if (this.conn.conn === 'resynced') setTimeout(() => this.signal('settled'), 4000);
    }
  }

  subscribeConn = (l: () => void) => {
    this.connListeners.add(l);
    return () => this.connListeners.delete(l);
  };

  private entry(path: string): Entry {
    let e = this.entries.get(path);
    if (!e) {
      e = { snap: EMPTY, listeners: new Set(), inflight: false, again: false };
      this.entries.set(path, e);
    }
    return e;
  }

  snapshot(path: string): Snapshot<unknown> {
    return this.entries.get(path)?.snap ?? EMPTY;
  }

  subscribe(path: string, l: () => void) {
    const e = this.entry(path);
    e.listeners.add(l);
    if (e.snap === EMPTY || e.snap.gen < this.conn.gen) void this.fetch(path);
    return () => e.listeners.delete(l);
  }

  private set(path: string, snap: Snapshot<unknown>) {
    const e = this.entry(path);
    e.snap = snap;
    e.listeners.forEach((l) => l());
  }

  async fetch(path: string) {
    const e = this.entry(path);
    if (!this.send) return;
    if (e.inflight) {
      e.again = true; // a notice during a fetch collapses into one more fetch
      return;
    }
    e.inflight = true;
    if (!e.snap.pending) this.set(path, { ...e.snap, pending: true });
    try {
      do {
        e.again = false;
        const gen = this.conn.gen;
        try {
          const data = await this.send('GET', path);
          this.set(path, { data, pending: false, gen, seq: this.seqs.get(path) });
        } catch (err) {
          const error = err instanceof CoreError ? err : new CoreError(0, 'network', {});
          if (error.status === 401) this.signal('unauthorized');
          this.set(path, { ...e.snap, error, pending: false, gen });
        }
      } while (e.again);
    } finally {
      e.inflight = false;
    }
  }

  /** Mark reads stale; those on screen are re-read in one batch per 50 ms. */
  invalidate(pred: (path: string) => boolean) {
    this.stale.push(pred);
    if (this.timer === undefined)
      this.timer = setTimeout(() => {
        const preds = this.stale;
        this.stale = [];
        this.timer = undefined;
        for (const [path, e] of this.entries) {
          if (!preds.some((p) => p(path))) continue;
          if (e.listeners.size) void this.fetch(path);
          else this.entries.delete(path); // read again when next shown
        }
      }, 50);
  }

  invalidateAll() {
    this.invalidate(() => true);
  }
}

export const store = new Store();

/** The cached answer of GET *path* (null: nothing to read yet). */
export function useRead<T>(path: string | null): Snapshot<T> {
  const snap = useSyncExternalStore(
    (l) => (path ? store.subscribe(path, l) : () => undefined),
    () => (path ? store.snapshot(path) : EMPTY),
  );
  return snap as Snapshot<T>;
}

export function useConn(): ConnState {
  return useSyncExternalStore(store.subscribeConn, () => store.conn);
}

/** Re-read *path* every *ms* while shown — only for a clock-driven value Core
 * computes at read time (an approval's expiry), never instead of the stream. */
export function useRefresh(path: string | null, ms: number) {
  useEffect(() => {
    if (!path) return;
    const t = setInterval(() => void store.fetch(path), ms);
    return () => clearInterval(t);
  }, [path, ms]);
}
