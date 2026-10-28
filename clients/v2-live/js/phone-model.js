// Phone logic, pure so it can be tested: what counts as a phone, the keyboard from the visual viewport, the bottom bar slots, the Stop two-step,
// the Places sheet and the Overview project list. The DOM side is js/viewport.js (measuring) and the slices that draw the bar and the sheets.
import { railProjects, RAIL_GROUPS } from './rail-model.js';
import { search } from './palette-model.js';

// ---------- one definition of "phone" ----------
export const PHONE_W = 600;
// A phone held sideways is wider than PHONE_W but still a phone: short window, coarse pointer. viewport.js turns this into the matchMedia query.
export const LANDSCAPE_QUERY = '(max-height: 499px) and (max-width: 949px) and (pointer: coarse)';
export const phoneBox = ({ frameW, landscape }) => frameW < PHONE_W || !!landscape;

// A keyboard is up when the visual viewport lost more than a browser bar's worth of height at the bottom while a field has focus, and the page is not pinch-zoomed.
export const KB_MIN = 120;
export function keyboard({ innerH, vvH, vvTop = 0, scale = 1, editing }) {
  const bottom = Math.max(0, Math.round(innerH - vvH - vvTop));
  return { bottom, open: !!editing && scale <= 1.01 && bottom >= KB_MIN };
}

// ---------- bottom bar ----------
export const badgeText = (n) => (n > 99 ? '99+' : String(n));

// The slots, left to right, defined once: changing the bar is changing this list. `routes` are the pages a slot stands for; a page no slot names belongs to Places.
export const BAR = [
  { id: 'overview', icon: 'now', label: 'Overview', kind: 'route', routes: ['now'] },
  { id: 'work', icon: 'work', label: 'Work', kind: 'route', routes: ['work'], badge: 'attention' },
  { id: 'tell', icon: 'chat', label: 'Tell', kind: 'action', primary: true },
  { id: 'places', icon: 'places', label: 'Places', kind: 'action' },
  { id: 'stop', icon: 'estop', label: 'Stop', kind: 'action', danger: true },
];

// state: { route, attention, engaged, placesOpen, tellOpen, safetyOpen }. Exactly one slot is current: an open sheet wins, then the slot that names the route, then Places.
export function slots({ route, attention = 0, engaged = false, placesOpen = false, tellOpen = false, safetyOpen = false }) {
  const open = safetyOpen ? 'stop' : placesOpen ? 'places' : tellOpen ? 'tell' : null;
  const named = BAR.find((s) => s.routes && s.routes.includes(route));
  const current = open || (named ? named.id : route === 'chat' ? 'tell' : 'places');
  return BAR.map((s) => {
    const badge = s.badge === 'attention' && attention > 0 ? badgeText(attention) : null;
    const label = s.id === 'stop' && engaged ? 'Re-arm' : s.label;
    const aria = s.id === 'stop' ? (engaged ? 'Re-arm new work' : 'Emergency stop all missions')
      : badge ? s.label + ', ' + attention + ' need you'
      : s.id === 'tell' ? 'Tell Archeus' : s.label;
    return { id: s.id, icon: s.icon, label, aria, badge, kind: s.kind, primary: !!s.primary, danger: !!s.danger, current: s.id === current, expanded: s.kind === 'action' && s.id !== 'stop' ? open === s.id : undefined };
  });
}

// ---------- Stop: two steps, the second named and away from the first tap ----------
export const STOP_MS = 5000;
export const STOP_IDLE = Object.freeze({ phase: 'idle', at: 0, action: null, label: '' });

// idle -tap-> armed -confirm-> done -> idle. An armed Stop disarms after STOP_MS or on cancel; a second tap on Stop only restarts the timer, it never confirms.
// ctx: { running, engaged, now }. The caller fires `state.action` ('estop' or 'rearm') when it sees phase 'done', then steps 'tick' to return to idle.
export function stopStep(s, ev, { running = 0, engaged = false, now = 0 } = {}) {
  if (ev === 'tap') return { phase: 'armed', at: now, ...(engaged ? { action: 'rearm', label: 'Re-arm new work' } : { action: 'estop', label: 'Stop all ' + running + (running === 1 ? ' mission' : ' missions') }) };
  if (s.phase === 'armed' && ev === 'confirm') return { ...s, phase: 'done' };
  if (s.phase === 'armed' && ev === 'tick' && now - s.at < STOP_MS) return s;
  return STOP_IDLE;
}

// The confirm sits on the opposite half of the screen from the tap, so one reflex tap can never land on it.
export const confirmSide = (tapX, width) => (tapX > width / 2 ? 'start' : 'end');

// ---------- Places sheet ----------
const TERMINAL = { id: 'terminal', label: 'Terminal view', icon: 'terminal' };
export const placeLabel = (r) => (r.id === 'now' ? 'Overview' : r.label);

// routes: [{ id, label, icon }] (the app's ROUTES). Without a query: the desktop groups (Work, Govern, Configure), the top `cap` projects by attention, how many more there are.
// With a query: the pages and projects that match, best first, searching every project (the same ranking as the command palette).
export function places({ routes, projects, stateOf, selected = null, attention = 0, query = '', cap = 5 }) {
  const byId = Object.fromEntries([...routes, TERMINAL].map((r) => [r.id, r]));
  const page = (id) => ({ id, label: placeLabel(byId[id]), icon: byId[id].icon, href: '#/' + id, badge: id === 'work' && attention > 0 ? badgeText(attention) : null });
  const q = query.trim();
  if (q) {
    const items = [...RAIL_GROUPS.flatMap(([, ids]) => ids).map((id) => ({ id, group: 'Pages', label: placeLabel(byId[id]) })), ...projects.map((p) => ({ id: p.id, group: 'Projects', label: p.name }))];
    const hits = search(items, q);
    return { query: q, groups: [], pages: hits.filter((i) => i.group === 'Pages').map((i) => page(i.id)), projects: hits.filter((i) => i.group === 'Projects').map((i) => projects.find((p) => p.id === i.id)), more: 0, total: projects.length };
  }
  const { shown, more } = railProjects(projects, stateOf, selected, cap);
  return { query: '', groups: RAIL_GROUPS.map(([label, ids]) => ({ label, items: ids.map(page) })), pages: [], projects: shown, more, total: projects.length };
}

// ---------- Overview project list ----------
export const OVERVIEW_CAP = 5;
export const OVERVIEW_SEARCH_ABOVE = 12;

// The rows under the state sentence: attention-ranked, at most `cap`, with "All N" for the rest; a search field only above OVERVIEW_SEARCH_ABOVE projects.
export function overviewProjects({ projects, stateOf, query = '', cap = OVERVIEW_CAP }) {
  const searchable = projects.length > OVERVIEW_SEARCH_ABOVE, q = searchable ? query.trim() : '';
  if (q) {
    const hits = search(projects.map((p) => ({ id: p.id, group: 'Projects', label: p.name })), q, [], { max: projects.length });
    return { searchable, rows: hits.slice(0, cap).map((i) => projects.find((p) => p.id === i.id)), more: Math.max(0, hits.length - cap), total: projects.length, matches: hits.length };
  }
  const { shown, more } = railProjects(projects, stateOf, null, cap);
  return { searchable, rows: shown, more, total: projects.length, matches: projects.length };
}
