// Layout (p18-design-gate A7; the legacy renderer's G4 mechanisms, ported):
// children seeded radially around their parent in key order, top-level
// clusters placed on a ring, grid-bucketed repulsion and collision, a spring
// to the parent — a FIXED number of iterations, run once, then static.
// Deterministic: a seeded PRNG from the focus key, no Math.random, no clock.
// Nodes already placed keep their positions (a refresh never makes the graph
// jump); only new nodes settle. Pure.

export interface Point {
  x: number;
  y: number;
}

export const ITERATIONS = 120;

/** mulberry32: a tiny deterministic PRNG. */
export function prng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export interface LayoutInput {
  keys: readonly string[]; // visible nodes, in the server's order
  parentOf: (k: string) => string | null; // nearest VISIBLE ancestor
  radius: (k: string) => number;
  links: readonly [string, string][]; // drawn edges
  seed: string; // the focus key
  prev?: ReadonlyMap<string, Point>; // positions to keep
  pinned?: ReadonlySet<string>;
}

export function layout(inp: LayoutInput): Map<string, Point> {
  const rnd = prng(hash(inp.seed));
  const pos = new Map<string, Point>();
  const fixed = new Set<string>();
  for (const k of inp.keys) {
    const p = inp.prev?.get(k);
    if (p) {
      pos.set(k, { x: p.x, y: p.y });
      fixed.add(k);
    }
  }
  for (const k of inp.pinned ?? []) if (pos.has(k)) fixed.add(k);
  // top level on a ring, sized by population (the legacy zones)
  const tops = inp.keys.filter((k) => !inp.parentOf(k));
  const kids = new Map<string, string[]>();
  for (const k of inp.keys) {
    const p = inp.parentOf(k);
    if (p) kids.set(p, [...(kids.get(p) ?? []), k]);
  }
  const ringR = tops.length <= 1 ? 0 : Math.max(160, tops.length * 36);
  tops.forEach((k, i) => {
    if (pos.has(k)) return;
    const a = (2 * Math.PI * i) / tops.length;
    pos.set(k, { x: Math.cos(a) * ringR, y: Math.sin(a) * ringR });
  });
  // children radially around their parent, breadth first, in key order
  const queue = [...tops];
  while (queue.length) {
    const p = queue.shift()!;
    const cs = kids.get(p) ?? [];
    const pp = pos.get(p)!;
    const phase = rnd() * Math.PI * 2;
    cs.forEach((c, i) => {
      if (!pos.has(c)) {
        const a = phase + (2 * Math.PI * i) / cs.length;
        const r = 70 + Math.min(220, cs.length * 7);
        pos.set(c, { x: pp.x + Math.cos(a) * r, y: pp.y + Math.sin(a) * r });
      }
      queue.push(c);
    });
  }
  const moving = inp.keys.filter((k) => !fixed.has(k));
  if (!moving.length) return pos;
  const vel = new Map<string, Point>(inp.keys.map((k) => [k, { x: 0, y: 0 }]));
  const all = inp.keys.map((k) => ({ k, p: pos.get(k)!, r: inp.radius(k) }));
  const CELL = 120;
  for (let it = 0; it < ITERATIONS; it++) {
    const grid = new Map<string, typeof all>();
    for (const n of all) {
      const g = `${Math.floor(n.p.x / CELL)}|${Math.floor(n.p.y / CELL)}`;
      const b = grid.get(g);
      if (b) b.push(n);
      else grid.set(g, [n]);
    }
    for (const n of all) {
      if (fixed.has(n.k)) continue;
      const v = vel.get(n.k)!;
      const cx = Math.floor(n.p.x / CELL);
      const cy = Math.floor(n.p.y / CELL);
      for (let gx = cx - 1; gx <= cx + 1; gx++)
        for (let gy = cy - 1; gy <= cy + 1; gy++)
          for (const o of grid.get(`${gx}|${gy}`) ?? []) {
            if (o === n) continue;
            const dx = n.p.x - o.p.x;
            const dy = n.p.y - o.p.y;
            const d2 = dx * dx + dy * dy + 0.01;
            if (d2 > CELL * CELL) continue;
            const d = Math.sqrt(d2);
            const f = ((n.r + o.r + 24) * 90) / d2;
            v.x += (dx / d) * f;
            v.y += (dy / d) * f;
          }
    }
    for (const [a, b] of inp.links) {
      const pa = pos.get(a);
      const pb = pos.get(b);
      if (!pa || !pb) continue;
      const dx = pb.x - pa.x;
      const dy = pb.y - pa.y;
      const d = Math.sqrt(dx * dx + dy * dy) + 0.01;
      const f = (d - 90) * 0.01;
      if (!fixed.has(a)) {
        vel.get(a)!.x += (dx / d) * f;
        vel.get(a)!.y += (dy / d) * f;
      }
      if (!fixed.has(b)) {
        vel.get(b)!.x -= (dx / d) * f;
        vel.get(b)!.y -= (dy / d) * f;
      }
    }
    for (const n of all) {
      if (fixed.has(n.k)) continue;
      const v = vel.get(n.k)!;
      n.p.x += Math.max(-40, Math.min(40, v.x));
      n.p.y += Math.max(-40, Math.min(40, v.y));
      v.x *= 0.7;
      v.y *= 0.7;
    }
  }
  return pos;
}

/** A two-finger pinch (A12): the scale follows the fingers' distance *d1*
 * against *d0* when the pinch began, and the world point under their midpoint
 * *mid* (screen offset from the canvas centre) stays where it is. */
export function pinchCamera(start: { x: number; y: number; k: number }, d0: number, d1: number, mid: Point): { x: number; y: number; k: number } {
  const k = Math.max(0.1, Math.min(4, start.k * (d1 / Math.max(1, d0))));
  const wx = start.x + mid.x / start.k;
  const wy = start.y + mid.y / start.k;
  return { x: wx - mid.x / k, y: wy - mid.y / k, k };
}

/** The camera that shows every point: centre and scale for a w×h viewport. */
export function fit(points: Iterable<Point>, w: number, h: number, pad = 40): { x: number; y: number; k: number } {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const p of points) {
    x0 = Math.min(x0, p.x);
    y0 = Math.min(y0, p.y);
    x1 = Math.max(x1, p.x);
    y1 = Math.max(y1, p.y);
  }
  if (!Number.isFinite(x0)) return { x: 0, y: 0, k: 1 };
  const k = Math.min(2, Math.max(0.1, Math.min((w - pad * 2) / Math.max(1, x1 - x0), (h - pad * 2) / Math.max(1, y1 - y0))));
  return { x: (x0 + x1) / 2, y: (y0 + y1) / 2, k };
}
