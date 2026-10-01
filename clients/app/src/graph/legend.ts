// The graph's legend (ADR-0025 §2, rulebook §12 and §25, X-20): the encoding
// table read back as words — the shape of every kind in the loaded picture,
// the line of every confidence tier a loaded edge carries, and the two marks
// of live work. Nothing here is a second encoding: shapes come from
// `lookOf`, dashes from `dashOf`, words from `TIER_WORD`. A kind or tier row
// hides what it names in the drawing (view state, never sent); the mirror
// keeps listing everything loaded. Pure.
import { ENCODING, dashOf, lookOf, type Shape } from './encoding.ts';
import { keyOf, type GEdge, type GNode, type Model } from './model.ts';
import { TIER_WORD } from './relations.ts';

export type Tier = keyof typeof TIER_WORD;

export type LegendRow =
  | { key: string; group: 'kind'; shape: Shape; word: string }
  | { key: string; group: 'tier'; tier: Tier; dash: readonly number[]; word: string }
  | { key: 'halo' | 'marker'; group: 'live'; word: string };

const ENDPOINT_WORD = 'a reference with no record of its own, or “+N more”';
const ORDER = [...Object.keys(ENCODING).flatMap((k) => (k === 'knowledge_item' ? [k, 'decision'] : [k])), 'endpoint'];

/** The legend row a node is drawn under: its kind, a DECISION knowledge item
 * as the decision it records, and anything drawn as an endpoint as one. */
export function kindKey(n: GNode): string {
  const look = lookOf(n.kind, n.endpoint, n.type);
  if (look.shape === 'endpoint') return 'kind:endpoint';
  return 'kind:' + (look.shape === 'diamond' ? 'decision' : n.kind);
}

/** An edge's tier as drawn: a column edge (no tier) is recorded; a tier Core
 * does not define is none — never guessed. */
export function tierOf(e: GEdge): Tier | null {
  if (!e.tier) return 'EXTRACTED';
  return e.tier in TIER_WORD ? (e.tier as Tier) : null;
}

/** The rows, in the encoding's order: kinds present in the loaded picture,
 * tiers carried by a loaded edge (AMBIGUOUS only once Core writes one), then
 * the halo and the marker — or, under reduced motion, the static live edge
 * that stands in for the marker. */
export function legendRows(m: Model, reduced = false): LegendRow[] {
  const kinds = new Map<string, GNode>();
  for (const n of m.nodes) if (!kinds.has(kindKey(n))) kinds.set(kindKey(n), n);
  const rows: LegendRow[] = [];
  for (const k of ORDER) {
    const n = kinds.get('kind:' + k);
    if (!n) continue;
    const look = lookOf(n.kind, n.endpoint, n.type);
    rows.push({ key: 'kind:' + k, group: 'kind', shape: look.shape, word: look.shape === 'endpoint' ? ENDPOINT_WORD : look.noun });
  }
  const tiers = new Set(m.edges.map(tierOf));
  for (const t of Object.keys(TIER_WORD) as Tier[])
    if (tiers.has(t)) rows.push({ key: 'tier:' + t, group: 'tier', tier: t, dash: dashOf(t), word: TIER_WORD[t] });
  rows.push({ key: 'halo', group: 'live', word: 'live work now' });
  rows.push({ key: 'marker', group: 'live', word: reduced ? 'live now: the thicker line from an attempt to its task' : 'live now: output travelling from an attempt to its task' });
  return rows;
}

/** What the drawing shows once the unticked rows are hidden: the visible set
 * without the hidden kinds, and an edge filter that drops the hidden tiers and
 * every edge whose end is a hidden kind. */
export function applyLegend(m: Model, vis: ReadonlySet<string>, hidden: ReadonlySet<string>) {
  if (!hidden.size) return { vis: new Set(vis), keep: () => true };
  const shownKey = (k: string) => {
    const n = m.byKey.get(k);
    return !n || !hidden.has(kindKey(n));
  };
  const out = new Set([...vis].filter(shownKey));
  const keep = (e: GEdge) => {
    const t = tierOf(e);
    return !(t && hidden.has('tier:' + t)) && shownKey(keyOf(e.from)) && shownKey(keyOf(e.to));
  };
  return { vis: out, keep };
}
