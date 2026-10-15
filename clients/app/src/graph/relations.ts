// The graph capability's list form (p16-design-gate §20): the authoritative
// relationships of one object. Core's graph route assembles every edge, from
// the field that records it (p19-design-gate B1); this module only says them
// in words, from where one stands, and the spatial view says the same words
// (EDGE_WORDS). Pure: tested and mutated directly.
import { paths } from '../api/generated.ts';
import { EDGE_WORDS } from './edgeWords.ts';

export { EDGE_WORDS };

export interface Edge {
  rel: string; // what the relationship is, in words
  to: { kind: string; id: string };
  field: string; // the column or body field it was read from
  tier?: 'EXTRACTED' | 'INFERRED' | 'AMBIGUOUS';
  inactive?: boolean; // superseded / ended: shown distinct, never as current
}

/** An edge's words from where one stands: at the row holding its field
 * (`holder`), or at the row it names. A `Relation` row says its own `rel`. */
export function edgeWords(field: string, holder: boolean, rel?: string | null): string {
  if (field.startsWith('relations.')) return holder ? String(rel) : `${String(rel)} (from)`;
  const w = EDGE_WORDS[field];
  return w ? w[holder ? 0 : 1] : field;
}

type Ref = { kind: string; id: string };

/** An edge as `/v1/world/graph` returns it: held by `from`. */
export interface RouteEdge {
  from: Ref;
  to: Ref;
  field: string;
  rel?: unknown;
  tier?: unknown;
  inactive?: unknown;
  structural?: unknown;
}

/** The read a Relations list is drawn from: one hop around the object, every
 * edge (depth is always sent: the route walks two hops for most kinds). */
export const relationsPath = (kind: string, id: string) =>
  paths.worldGraph({ focus: `${kind}:${id}`, depth: 1, limit: 1000 });

/** The Relations list of *of*, from Core's graph read focused on it: every
 * edge incident to it, said from its end. Containment (`structural`) is the
 * graph's alone (p19-design-gate B1, X3). */
export function edgeRows(edges: readonly RouteEdge[], of: Ref): Edge[] {
  const at = (r: Ref) => r.kind === of.kind && r.id === of.id;
  const out: Edge[] = [];
  for (const e of edges) {
    if (e.structural) continue;
    const holder = at(e.from);
    if (!holder && !at(e.to)) continue;
    const row: Edge = { rel: edgeWords(e.field, holder, e.rel as string | null), to: holder ? e.to : e.from, field: e.field };
    if (e.tier) row.tier = e.tier as Edge['tier'];
    if (e.inactive) row.inactive = true;
    out.push(row);
  }
  return out;
}

/** The line style that encodes a relation's confidence tier (research §22). */
export const TIER_STYLE: Record<NonNullable<Edge['tier']>, string> = {
  EXTRACTED: 'solid',
  INFERRED: 'dashed',
  AMBIGUOUS: 'dotted',
};

/** What a person reads for a tier (ADR-0025 §1, rulebook §25): the list, the
 * mirror and the legend say these words, never the enum. An edge read from a
 * column has no tier and is recorded. */
export const TIER_WORD: Record<NonNullable<Edge['tier']>, string> = {
  EXTRACTED: 'recorded',
  INFERRED: 'suggested by Archeus',
  AMBIGUOUS: 'unclear',
};

export type Tier = keyof typeof TIER_WORD;

/** An edge's tier as drawn: a column edge (no tier) is recorded; a tier Core
 * does not define is none — never guessed. */
export function tierOf(e: { tier?: string | null }): Tier | null {
  if (!e.tier) return 'EXTRACTED';
  return e.tier in TIER_WORD ? (e.tier as Tier) : null;
}
