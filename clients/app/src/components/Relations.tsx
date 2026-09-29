// The Relations tab (p16-design-gate §20.5): an object's authoritative edges
// as a navigable list, grouped by relationship — the accessible form of the
// graph, and the only form P16 draws. Each row says which field it was read
// from; a superseded or ended neighbour is shown distinct, never as current.
import { useState } from 'react';
import { TIER_STYLE, type Edge } from '../graph/relations';
import { objectHref } from '../nav/destinations';
import { Empty, RefLabel } from './ui';

export function Relations({ edges }: { edges: Edge[] }) {
  const rels = [...new Set(edges.map((e) => e.rel.replace(/ v\d+$/, ' (version)')))];
  const [only, setOnly] = useState<string | null>(null);
  if (!edges.length) return <Empty>No recorded relationships.</Empty>;
  const shown = only ? edges.filter((e) => e.rel.replace(/ v\d+$/, ' (version)') === only) : edges;
  return (
    <div className="relations">
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
          <li key={i} data-inactive={e.inactive ? '' : undefined}>
            <span className="rel">{e.rel}</span>
            {e.tier ? (
              <span className="tier" data-style={TIER_STYLE[e.tier]}>
                <span className="swatch" aria-hidden="true" />
                {e.tier.toLowerCase()}
              </span>
            ) : null}
            <a href={objectHref(e.to.kind, e.to.id)}>
              <RefLabel kind={e.to.kind} id={e.to.id} />
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
