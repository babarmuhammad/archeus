// The Relations tab (p16-design-gate §20.5): an object's authoritative edges
// as a navigable list, grouped by relationship — the accessible form of the
// graph. Core's graph route focused on the object is the one source
// (p19-design-gate B1). Each row says which field it was read from; a
// superseded or ended neighbour is shown distinct, never as current; a row
// whose neighbour the digest names carries the thread's rule (T2, B2).
import { useState } from 'react';
import type { WorldGraph } from '../api/generated';
import { useRead } from '../data/cache';
import { edgeRows, relationsPath, TIER_STYLE, TIER_WORD, type Edge } from '../graph/relations';
import { objectHref } from '../nav/destinations';
import { Changed, Empty, Loadable, RefLabel, thread, useChanged } from './ui';
import { useWide } from '../graph/wide';

/** P18 (p18-design-gate A4): the same relationships as a graph, one link away.
 * Hidden below 600 px, where this list is the view (A12). */
export function GraphLink({ kind, id }: { kind: string; id: string }) {
  if (!useWide()) return null;
  return (
    <a className="graph-toggle" href={`#/world/graph/${kind}/${encodeURIComponent(id)}`}>
      Show as a graph
    </a>
  );
}

export function Relations({ of }: { of: { kind: string; id: string } }) {
  const s = useRead<WorldGraph>(relationsPath(of.kind, of.id));
  return (
    <Loadable snap={s} what="Relationships">
      {(g) => <RelationList edges={edgeRows(g.edges, of)} of={of} />}
    </Loadable>
  );
}

function RelationList({ edges, of }: { edges: Edge[]; of: { kind: string; id: string } }) {
  const changed = useChanged();
  const rels = [...new Set(edges.map((e) => e.rel))];
  const [only, setOnly] = useState<string | null>(null);
  const link = <GraphLink kind={of.kind} id={of.id} />;
  if (!edges.length)
    return (
      <>
        {link}
        <Empty>No recorded relationships.</Empty>
      </>
    );
  const shown = only ? edges.filter((e) => e.rel === only) : edges;
  return (
    <div className="relations">
      {link}
      {rels.length > 1 ? (
        <div className="chips" role="group" aria-label="Filter by relationship">
          <button type="button" className={only ? 'chip' : 'chip on'} aria-pressed={!only} onClick={() => setOnly(null)}>
            All
          </button>
          {rels.map((r) => (
            <button key={r} type="button" className={only === r ? 'chip on' : 'chip'} aria-pressed={only === r} onClick={() => setOnly(r)}>
              {r}
            </button>
          ))}
        </div>
      ) : null}
      <ul className="rel-list">
        {shown.map((e, i) => (
          <li key={i} data-ref={`${e.to.kind}:${e.to.id}`} data-inactive={e.inactive ? '' : undefined} {...thread(changed(e.to.kind, e.to.id))}>
            <span className="rel">{e.rel}</span>
            {e.tier ? (
              <span className="tier" data-style={TIER_STYLE[e.tier]}>
                <span className="swatch" aria-hidden="true" />
                {TIER_WORD[e.tier]}
              </span>
            ) : null}
            <a href={objectHref(e.to.kind, e.to.id)}>
              <RefLabel kind={e.to.kind} id={e.to.id} />
              <Changed on={changed(e.to.kind, e.to.id)} />
            </a>
            {e.inactive ? <span className="inactive-mark">no longer current</span> : null}
            <span className="field" title="the field this relationship is read from">
              {e.field}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
