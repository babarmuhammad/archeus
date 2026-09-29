// The accessible mirror's rows (p18-design-gate A11): one per LOADED node, in
// the read's order, each with its edges in the shared words. Built from the
// same object the canvas draws: never a second source. A pinned node (view
// state, A13) says so; a project's counts and a route decision's recorded
// selection facts are its `detail`, the words the canvas draws (A3). Pure.
import { attrsText, countsText, lookOf } from './encoding.ts';
import { keyOf, type Model } from './model.ts';
import { edgeWords } from './relations.ts';

export function mirrorRows(model: Model, pinned: ReadonlySet<string> = new Set()) {
  return model.nodes.map((n) => {
    const k = keyOf(n);
    const look = lookOf(n.kind, n.endpoint, n.type);
    const edges = model.edges
      .filter((e) => keyOf(e.from) === k || keyOf(e.to) === k)
      .map((e) => {
        const holder = keyOf(e.from) === k;
        const other = model.byKey.get(keyOf(holder ? e.to : e.from));
        const text =
          `${edgeWords(e.field, holder, e.rel)} ${other ? other.label : (holder ? e.to : e.from).id}` +
          (e.tier ? ` (${e.tier.toLowerCase()})` : '') +
          (e.inactive ? ' — no longer current' : '') +
          (e.count && e.count > 1 ? ` ×${e.count}` : '');
        return { id: e.id, text };
      });
    const detail = n.kind === 'project' ? countsText(n.counts) : n.kind === 'route_decision' ? attrsText(n.attrs) : '';
    return { k, n, look, edges, pinned: pinned.has(k), detail };
  });
}
