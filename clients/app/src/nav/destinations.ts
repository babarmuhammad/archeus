// THE navigation table (p16-design-gate §4.2): one flat declaration; the
// sidebar, the rail, the phone tab bar, the shortcuts, the command bar and the
// tests all read it. Pure.

export interface Destination {
  id: 'now' | 'work' | 'world' | 'attention' | 'control';
  label: string;
  /** keyboard shortcut with Ctrl (Windows/Linux) or ⌘ (macOS) */
  key: string;
  /** on a phone: a bottom tab, or the header menu */
  phone: 'tab' | 'menu';
  blurb: string;
}

export const DESTINATIONS: Destination[] = [
  { id: 'now', label: 'Now', key: '1', phone: 'tab', blurb: 'What changed, what is happening, and the conversation' },
  { id: 'work', label: 'Work', key: '2', phone: 'tab', blurb: 'Every mission, grouped by what it waits on' },
  { id: 'world', label: 'World', key: '3', phone: 'tab', blurb: 'Projects, repositories and what Archeus knows' },
  { id: 'attention', label: 'Attention', key: 'j', phone: 'tab', blurb: 'Everything that waits on you' },
  { id: 'control', label: 'Control', key: ',', phone: 'menu', blurb: 'Autonomy, automations, resources, sessions and clients' },
];

export const CONTROL_SECTIONS = [
  { id: 'autonomy', label: 'Autonomy' },
  { id: 'automations', label: 'Automations' },
  { id: 'resources', label: 'Resources' },
  { id: 'sessions', label: 'Sessions' },
  { id: 'devices', label: 'Clients' },
  { id: 'about', label: 'About' },
] as const;

/** The inspector tabs per object kind, in their fixed order (§6.1). */
export const INSPECTOR_TABS: Record<string, string[]> = {
  mission: ['outcome', 'plan', 'now', 'evidence', 'why', 'timeline', 'relations'],
  execution: ['output', 'checkpoints', 'relations'],
  session: ['brief', 'lineage', 'relations'],
  knowledge_item: ['detail', 'relations'],
  automation_run: ['explanation', 'relations'],
  approval: ['detail'],
  plan: ['detail', 'relations'],
  verification: ['detail', 'relations'],
  route_decision: ['detail'],
  policy_decision: ['detail'],
  context_package: ['detail'],
  project: ['detail'],
  repository: ['detail'],
};

export const TAB_LABEL: Record<string, string> = {
  outcome: 'Outcome', plan: 'Plan', now: 'Now', evidence: 'Evidence', why: 'Why',
  timeline: 'Timeline', relations: 'Relations', output: 'Output', checkpoints: 'Checkpoints',
  brief: 'Brief', lineage: 'Lineage', detail: 'Detail', explanation: 'Explanation',
};

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
