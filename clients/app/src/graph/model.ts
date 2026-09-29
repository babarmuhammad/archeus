// The spatial view's model (p18-design-gate A7, A11, A13; the legacy
// renderer's mechanisms, G4, ported — not copied): which nodes are visible
// under the expanded set, edges lifted to the nearest visible ancestor,
// focus + context, search that expands ancestors, and a path over the edges
// already loaded. It only arranges what Core returned: no edge is created,
// none is inferred, nothing is read. Pure.

export interface Ref {
  kind: string;
  id: string;
}

export interface GNode {
  kind: string;
  id: string;
  label: string;
  parent?: Ref | null;
  machine?: string;
  state?: string;
  type?: string;
  counts?: Record<string, unknown>;
  attrs?: Record<string, unknown>;
  endpoint?: boolean;
  missing?: boolean;
}

export interface GEdge {
  id: string;
  from: Ref;
  to: Ref;
  field: string;
  rel?: string | null;
  tier?: string | null;
  inactive?: boolean;
  structural?: boolean;
  count?: number;
}

export interface Hidden {
  parent: Ref;
  kind: string;
  count: number;
}

export interface GraphData {
  nodes: GNode[];
  edges: GEdge[];
  hidden?: Hidden[];
  truncated?: boolean;
}

export interface Model {
  nodes: GNode[];
  byKey: Map<string, GNode>;
  parentOf: Map<string, string | null>; // nearest LOADED ancestor, null at the top
  children: Map<string, string[]>;
  edges: GEdge[];
}

/** One key per node. The import graph's edges name paths; its nodes are
 * directories and files — the same path is the same node (A5). */
export function keyOf(r: Ref): string {
  if (r.kind === 'path' || r.kind === 'directory' || r.kind === 'file') return 'path:' + r.id;
  return r.kind + ':' + r.id;
}

export function build(d: GraphData): Model {
  // what the cap cut becomes one "+N" stub per (parent, kind): drawn, listed,
  // and opened by re-focusing on the parent (A6) — never a node of the domain
  const stubs: GNode[] = (d.hidden ?? []).map((h) => ({
    kind: 'more',
    id: `${keyOf(h.parent)}:${h.kind}`,
    label: `+${h.count} more ${h.kind.replace(/_/g, ' ')}`,
    parent: h.parent,
    endpoint: true,
    counts: { hidden: h.count, of: h.kind },
  }));
  d = { ...d, nodes: [...d.nodes, ...stubs] };
  const byKey = new Map<string, GNode>();
  for (const n of d.nodes) byKey.set(keyOf(n), n);
  const parentOf = new Map<string, string | null>();
  const children = new Map<string, string[]>();
  for (const n of d.nodes) {
    const k = keyOf(n);
    const p = n.parent ? keyOf(n.parent) : null;
    const loaded = p && byKey.has(p) && p !== k ? p : null;
    parentOf.set(k, loaded);
    if (loaded) children.set(loaded, [...(children.get(loaded) ?? []), k]);
  }
  return { nodes: d.nodes, byKey, parentOf, children, edges: d.edges };
}

export function ancestors(m: Model, k: string): string[] {
  const out: string[] = [];
  let p = m.parentOf.get(k) ?? null;
  for (let guard = 0; p && guard < 64; guard++) {
    out.push(p);
    p = m.parentOf.get(p) ?? null;
  }
  return out;
}

/** A node is visible iff every loaded ancestor is expanded. */
export function visible(m: Model, expanded: ReadonlySet<string>): Set<string> {
  const out = new Set<string>();
  for (const n of m.nodes) {
    const k = keyOf(n);
    if (ancestors(m, k).every((a) => expanded.has(a))) out.add(k);
  }
  return out;
}

/** The nearest visible node standing for *k*: itself, or its first visible ancestor. */
export function lift(m: Model, vis: ReadonlySet<string>, k: string): string | null {
  if (vis.has(k)) return k;
  for (const a of ancestors(m, k)) if (vis.has(a)) return a;
  return null;
}

export interface Drawn {
  id: string; // the first real edge's id (stable)
  a: string;
  b: string;
  count: number; // how many real edges it stands for
  edges: GEdge[];
  tier?: string | null;
  inactive: boolean;
  structural: boolean;
}

/** Visible edges: every real edge lifted to its ends' nearest visible
 * ancestors, one line per pair, counting what it stands for (G4). An edge
 * whose ends lift to one node disappears inside it. */
export function lifted(m: Model, vis: ReadonlySet<string>, keep: (e: GEdge) => boolean = () => true): Drawn[] {
  const byPair = new Map<string, Drawn>();
  for (const e of m.edges) {
    if (!keep(e)) continue;
    const a = lift(m, vis, keyOf(e.from));
    const b = lift(m, vis, keyOf(e.to));
    if (!a || !b || a === b) continue;
    const pair = a < b ? `${a}|${b}` : `${b}|${a}`;
    const d = byPair.get(pair);
    const n = e.count ?? 1;
    if (!d) byPair.set(pair, { id: e.id, a, b, count: n, edges: [e], tier: e.tier, inactive: !!e.inactive, structural: !!e.structural });
    else {
      d.count += n;
      d.edges.push(e);
      d.inactive = d.inactive && !!e.inactive;
      d.structural = d.structural && !!e.structural;
      if (d.tier !== e.tier) d.tier = null; // a mixed bundle claims no tier
    }
  }
  return [...byPair.values()].sort((x, y) => (x.id < y.id ? -1 : x.id > y.id ? 1 : 0));
}

/** The edges at *k* in the order keyboard traversal visits them (A11): the
 * drawn edges' own order, so the same data always walks the same way. */
export function around(drawn: readonly Drawn[], k: string): { edge: Drawn; other: string }[] {
  return drawn.filter((d) => d.a === k || d.b === k).map((d) => ({ edge: d, other: d.a === k ? d.b : d.a }));
}

/** Focus + context (G4): the focused node and its neighbours stay; the rest dims. */
export function inFocus(drawn: readonly Drawn[], k: string | null): Set<string> | null {
  if (!k) return null;
  const out = new Set([k]);
  for (const x of around(drawn, k)) out.add(x.other);
  return out;
}

/** Toggle one node's children (expand/collapse by parent). */
export function toggle(expanded: ReadonlySet<string>, k: string): Set<string> {
  const next = new Set(expanded);
  if (next.has(k)) next.delete(k);
  else next.add(k);
  return next;
}

/** Everything with children, expanded: what a focused neighbourhood opens as. */
export function allExpanded(m: Model): Set<string> {
  return new Set(m.children.keys());
}

/** Search (A13): loaded nodes whose label matches, each made visible by
 * expanding its ancestors (G4). Never a request to Core. */
export function search(m: Model, expanded: ReadonlySet<string>, q: string): { hits: string[]; expanded: Set<string> } {
  const needle = q.trim().toLowerCase();
  const next = new Set(expanded);
  if (!needle) return { hits: [], expanded: next };
  const hits: string[] = [];
  for (const n of m.nodes) {
    if (n.kind === 'more' || !n.label.toLowerCase().includes(needle)) continue;
    const k = keyOf(n);
    hits.push(k);
    for (const a of ancestors(m, k)) next.add(a);
  }
  return { hits, expanded: next };
}

/** A path between two loaded nodes over loaded edges only (A13): breadth
 * first, deterministic; null when none — never a traversal Core is asked for. */
export function path(m: Model, from: string, to: string): string[] | null {
  if (!m.byKey.has(from) || !m.byKey.has(to)) return null;
  const adj = new Map<string, string[]>();
  for (const e of [...m.edges].sort((x, y) => (x.id < y.id ? -1 : 1))) {
    const a = keyOf(e.from);
    const b = keyOf(e.to);
    adj.set(a, [...(adj.get(a) ?? []), b]);
    adj.set(b, [...(adj.get(b) ?? []), a]);
  }
  const prev = new Map<string, string>([[from, from]]);
  const q = [from];
  while (q.length) {
    const x = q.shift()!;
    if (x === to) break;
    for (const y of adj.get(x) ?? []) {
      if (prev.has(y) || !m.byKey.has(y)) continue;
      prev.set(y, x);
      q.push(y);
    }
  }
  if (!prev.has(to)) return null;
  const out = [to];
  while (out[0] !== from) out.unshift(prev.get(out[0])!);
  return out;
}

/** The executions that are live right now, by Core's state (A8): their
 * presentation class is `active`. */
export function liveExecutions(m: Model, isActive: (machine: string, state: string) => boolean): Set<string> {
  const out = new Set<string>();
  for (const n of m.nodes)
    if (n.kind === 'execution' && n.machine && n.state && isActive(n.machine, n.state)) out.add(keyOf(n));
  return out;
}

/** The one edge a live execution's pulse travels: its `executions.task_id`
 * edge, as drawn (lifted) now. */
export function pulseEdge(drawn: readonly Drawn[], exec: string): Drawn | null {
  return drawn.find((d) => d.edges.some((e) => e.field === 'executions.task_id' && keyOf(e.from) === exec)) ?? null;
}

export const PULSE_MS = 240;
export const PULSE_EVERY_MS = 2000;

/** Whether a stream frame pulses an edge (A8), and which: an `execution.*`
 * frame about a loaded execution whose edge is live, at most once per
 * PULSE_EVERY_MS per edge, never under reduced motion. The frame says only
 * WHICH row moved; whether it is live is Core's state in the read. */
export function pulseFor(
  f: { event: string; data?: unknown },
  drawn: readonly Drawn[],
  live: ReadonlySet<string>,
  last: ReadonlyMap<string, number>,
  now: number,
  reduced: boolean,
): Drawn | null {
  const subject = (f.data as { subject?: Ref } | undefined)?.subject;
  if (reduced || !subject || subject.kind !== 'execution' || !f.event.startsWith('execution.')) return null;
  const d = pulseEdge(drawn, keyOf(subject));
  if (!d || !live.has(d.id)) return null;
  return now - (last.get(d.id) ?? -Infinity) < PULSE_EVERY_MS ? null : d;
}
