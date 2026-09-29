// THE navigation table (p16-design-gate §4.2): one flat declaration; the
// sidebar, the rail, the phone tab bar, the shortcuts, the command bar, the
// TUI and the tests all read it. Its rows are clients/app/tokens/navigation.json,
// generated into ./table.ts (p17-design-gate A1); this file adds the routes. Pure.
import { DESTINATIONS, type Destination } from './table.ts';

export { CONTROL_SECTIONS, DESTINATIONS, INSPECTOR_TABS, TAB_LABEL, type Destination } from './table.ts';

/** What a phone shows in its tab bar: never without Attention (§16). */
export const phoneTabs = () => DESTINATIONS.filter((d) => d.phone === 'tab');

// ── routes (hash-based, D7) ──

export type Route =
  | { view: Destination['id']; section?: string; project?: string }
  | { view: 'object'; kind: string; id: string; tab?: string; under: Destination['id'] };

/** The route a hash names; the two bootstrap fragments (`launch=`, `pair=`)
 * and anything unknown are Now. */
export function parse(hash: string, under: Destination['id'] = 'now'): Route {
  const h = hash.replace(/^#/, '');
  if (!h.startsWith('/')) return { view: 'now' };
  const [a, b, c, d] = h.slice(1).split('/').map(decodeURIComponent);
  if (a === 'o' && b && c) return { view: 'object', kind: b, id: c, tab: d || undefined, under };
  if ((a === 'world' || a === 'work') && b) return { view: a, project: b };
  if (a === 'control') return { view: 'control', section: b || 'autonomy' };
  const known = DESTINATIONS.find((x) => x.id === a);
  return known ? { view: known.id } : { view: 'now' };
}

export function href(r: Route): string {
  if (r.view === 'object') return `#/o/${r.kind}/${encodeURIComponent(r.id)}${r.tab ? '/' + r.tab : ''}`;
  if ((r.view === 'world' || r.view === 'work') && r.project) return `#/${r.view}/${encodeURIComponent(r.project)}`;
  if (r.view === 'control') return `#/control/${r.section ?? 'autonomy'}`;
  return `#/${r.view}`;
}

export const objectHref = (kind: string, id: string, tab?: string) =>
  href({ view: 'object', kind, id, tab, under: 'now' });
