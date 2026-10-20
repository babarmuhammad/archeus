// The accessible mirror's rows (p18-design-gate A11): one per LOADED node, in
// the read's order, each with its edges in the shared words. Built from the
// same object the canvas draws: never a second source. A pinned node (view
// state, A13) says so; a project's counts and a route decision's recorded
// selection facts are its `detail`, the words the canvas draws (A3); a node
// the canvas haloes is `live` — the halo's text equivalent (ADR-0024 §6); and a
// live execution's attempt-of relation, the edge its pulse and travelling
// marker run along, says "live now" — their text equivalent. R3's marks say
// themselves in words too (rulebook §20): the hull as "in project Atlas",
// depth as "2 steps from <focus>", and the impact view as "affected". Pure.
import { attrsText, countsText, lookOf } from './encoding.ts';
import { ancestors, keyOf, type Model } from './model.ts';
import { edgeWords, TIER_WORD } from './relations.ts';

/** Where the view stands: the focused node, the drawn hop distance of each
 * node from it, and — while the impact view is on — what it affects. */
export interface Around {
  focus: string;
  steps: ReadonlyMap<string, number>;
  affected?: ReadonlyMap<string, number> | null;
}

const stepsWord = (n: number) => `${n} ${n === 1 ? 'step' : 'steps'}`;

export function mirrorRows(model: Model, pinned: ReadonlySet<string> = new Set(), halo: ReadonlySet<string> = new Set(), around?: Around) {
  const focus = around && model.byKey.get(around.focus)?.label;
  return model.nodes.map((n) => {
    const k = keyOf(n);
    const look = lookOf(n.kind, n.endpoint, n.type);
    const edges = model.edges
      .filter((e) => keyOf(e.from) === k || keyOf(e.to) === k)
      .map((e) => {
        const holder = keyOf(e.from) === k;
        const live = e.field === 'executions.task_id' && halo.has(keyOf(e.from));
        const other = model.byKey.get(keyOf(holder ? e.to : e.from));
        const text =
          `${edgeWords(e.field, holder, e.rel)} ${other ? other.label : (holder ? e.to : e.from).id}` +
          (e.tier && e.tier in TIER_WORD ? ` (${TIER_WORD[e.tier as keyof typeof TIER_WORD]})` : '') +
          (e.inactive ? ' — no longer current' : '') +
          (e.count && e.count > 1 ? ` ×${e.count}` : '') +
          (live ? ' — live now' : '');
        return { id: e.id, text, live };
      });
    const detail = n.kind === 'project' ? countsText(n.counts) : n.kind === 'route_decision' ? attrsText(n.attrs) : '';
    const project = ancestors(model, k).map((a) => model.byKey.get(a)!).find((a) => a.kind === 'project');
    const d = around && k !== around.focus ? around.steps.get(k) : undefined;
    const hit = around?.affected?.get(k);
    const notes = [
      ...(project ? [`in project ${project.label}`] : []),
      ...(d ? [`${stepsWord(d)} from ${focus}`] : []),
      ...(hit ? [`affected, ${stepsWord(hit)} from ${focus} over recorded relations`] : []),
    ];
    return { k, n, look, edges, live: halo.has(k), pinned: pinned.has(k), detail, notes };
  });
}
