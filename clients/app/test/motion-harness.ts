// The deterministic motion harness (ADR-0029 §1): a frozen presentation clock,
// a frame queue that only runs when a test says so, a recording canvas and
// renderAt(t). Every visual slice tests its motion with these instead of a
// timing system of its own: no wall clock, no real requestAnimationFrame, no
// sleep. Not a test file itself (the suite runs test/*.test.ts).
import type { LoopHost } from '../src/graph/loop.ts';
import { draw, type DrawStats, type Scene } from '../src/graph/render.ts';
import type { Timeline } from '../src/state/timeline.ts';

export type FakeHost = LoopHost & {
  /** run queued frames (and the frames they queue) until none is left; how many ran */
  run: () => number;
  /** advance the frozen clock */
  tick: (ms: number) => void;
  /** frames queued and not run */
  pending: () => number;
  /** every requestAnimationFrame ever asked for: the idle gate reads it */
  asked: () => number;
};

/** A loop host on a frozen clock at 0: frames run only in run(), at now(). */
export function fakeHost(over: Partial<LoopHost> = {}): FakeHost {
  const q: ((t: number) => void)[] = [];
  let now = 0;
  let asked = 0;
  return {
    raf: (cb) => (asked++, q.push(cb)),
    caf: (id) => void (q[id - 1] = () => undefined),
    now: () => now,
    hidden: () => false,
    focused: () => true,
    reduced: () => false,
    ...over,
    run() {
      let n = 0;
      while (q.length && n < 1000) {
        q.shift()!(now);
        n++;
      }
      return n;
    },
    tick(ms) {
      now += ms;
    },
    pending: () => q.length,
    asked: () => asked,
  };
}

/** A 2D context that records every call: equal op lists are equal pictures. */
export function recorder() {
  const ops: string[] = [];
  const state: Record<string, unknown> = {};
  const ctx = new Proxy(state, {
    get(t, p: string) {
      if (p in t) return t[p];
      return (...a: unknown[]) => {
        ops.push(`${p}(${a.map((x) => (typeof x === 'number' ? Math.round(x * 100) / 100 : JSON.stringify(x))).join(',')})`);
      };
    },
    set(t, p: string, v) {
      t[p] = v;
      if (p === 'fillStyle' || p === 'strokeStyle' || p === 'globalAlpha') ops.push(`${p}=${String(v)}`);
      return true;
    },
  }) as unknown as CanvasRenderingContext2D;
  return { ctx, ops };
}

/** The graph's picture at presentation time *t*: the scene with every
 * registered canvas motion read from *tl* at t. Pure: the same scene, timeline
 * and t give the same ops. A slice adding a canvas motion adds its read here. */
export function renderAt(scene: Scene, tl: Timeline, t: number): { ops: string[]; stats: DrawStats } {
  const { ctx, ops } = recorder();
  const stats = draw(ctx, { ...scene, pulse: tl.progress('execution-pulse', t), marker: tl.progress('travelling-marker', t) });
  return { ops, stats };
}
