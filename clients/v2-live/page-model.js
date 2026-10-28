// Pure logic for the Work, Replay and Projects pages: URL parsing, saved views, filters, counts, relative time, sort, replay modes. No DOM.
// Everything a page shows in its URL (#/work?view=running&project=notes, #/replay/m-date?mode=compact, #/projects/prj-notes/missions) is read and written here.

export const parseHash = (hash) => {
  const [path, query = ''] = String(hash || '').split('?'), m = /^#\/([a-z]+)(?:\/([\w-]+))?(?:\/([\w-]+))?/.exec(path) || [];
  return { name: m[1] || null, id: m[2] || null, sub: m[3] || null, q: Object.fromEntries(new URLSearchParams(query)) };
};
const href = (path, q) => { const s = new URLSearchParams(Object.entries(q).filter(([, v]) => v)).toString(); return '#/' + path + (s ? '?' + s : ''); };

// ---------- Work ----------
export const WORK_VIEWS = [['needs', 'Needs you'], ['running', 'Running'], ['blocked', 'Blocked'], ['done', 'Done'], ['all', 'All']];
const VIEW_OF = { needs_you: 'needs', reviewing: 'needs', blocked: 'blocked', failed: 'blocked', paused: 'blocked', done: 'done', inactive: 'done' };
export const viewOfCls = (cls) => VIEW_OF[cls] || 'running';

// The shared state vocabulary (pending, active, error, awaiting input, complete, stale) in our words.
const VOCAB = { needs_you: 'awaiting input', reviewing: 'awaiting input', active: 'active', verifying: 'active', planning: 'pending', proposed: 'pending', approved: 'pending', blocked: 'error', failed: 'error', paused: 'stale', done: 'complete', inactive: 'stale' };
export const vocabOf = (cls) => VOCAB[cls] || 'pending';

export const workQuery = (q, projectIds = []) => ({
  view: WORK_VIEWS.some(([v]) => v === q.view) ? q.view : 'all',
  project: projectIds.includes(q.project) ? q.project : null,
  as: q.as === 'graph' ? 'graph' : 'list'
});
export const workHref = ({ view, project, as } = {}) => href('work', { view: view === 'all' ? '' : view, project, as: as === 'graph' ? 'graph' : '' });

// items: { id, project, cls } for missions and for decisions alike.
export const filterWork = (items, { view = 'all', project = null } = {}) => items.filter((i) => (!project || i.project === project) && (view === 'all' || viewOfCls(i.cls) === view));
export const workCounts = (items, project = null) => {
  const own = project ? items.filter((i) => i.project === project) : items, n = { all: own.length };
  for (const [v] of WORK_VIEWS) if (v !== 'all') n[v] = own.filter((i) => viewOfCls(i.cls) === v).length;
  return n;
};
export const countLine = (shown, total) => (shown === total ? String(total) : shown + ' of ' + total);

// The entries the Work graph draws: those the filter keeps first, then the rest, at most cap, each group in rank order. The filter dims in the graph, it never removes: the rest only make way when there are more than cap.
// prev: the ids drawn last time. When they still all exist and already hold what the filter keeps, they are kept as they were, so a filter change is a highlight and not a new drawing.
export function graphPick(entries, shown, cap, rank = () => 0, prev = []) {
  const on = new Set(shown.map((e) => e.id)), by = (a, b) => rank(a) - rank(b), byId = new Map(entries.map((e) => [e.id, e]));
  if (prev.length && prev.every((id) => byId.has(id)) && [...shown].sort(by).slice(0, cap).every((e) => prev.includes(e.id))) return prev.map((id) => byId.get(id));
  return [...entries.filter((e) => on.has(e.id)).sort(by), ...entries.filter((e) => !on.has(e.id)).sort(by)].slice(0, cap);
}

// Relative time against the simulated clock: 'now', '3m ago', '2h ago', '4d ago'. The exact time goes in the title.
export function relTime(now, at) {
  const s = Math.max(0, Math.round((now - at) / 1000));
  return s < 45 ? 'now' : s < 3600 ? Math.round(s / 60) + 'm ago' : s < 86400 ? Math.round(s / 3600) + 'h ago' : Math.round(s / 86400) + 'd ago';
}

// ---------- Projects ----------
export const PROJECT_SORTS = [['attention', 'Attention'], ['recent', 'Recent'], ['name', 'Name']];
export const sortOf = (v) => (PROJECT_SORTS.some(([s]) => s === v) ? v : 'attention');
const byName = (a, b) => a.name.localeCompare(b.name) || String(a.id).localeCompare(String(b.id));
export function sortProjects(list, mode) {
  const cmp = {
    attention: (a, b) => (b.attention || 0) - (a.attention || 0) || (b.running || 0) - (a.running || 0) || (b.lastAt || 0) - (a.lastAt || 0) || byName(a, b),
    recent: (a, b) => (b.lastAt || 0) - (a.lastAt || 0) || byName(a, b),
    name: byName
  }[sortOf(mode)];
  return [...list].sort(cmp);
}
export const PROJECT_TABS = [['overview', 'Overview'], ['missions', 'Missions'], ['ideas', 'Ideas'], ['activity', 'Activity'], ['settings', 'Settings']];
export const projectTab = (sub) => (sub === 'details' ? 'settings' : PROJECT_TABS.some(([t]) => t === sub) ? sub : 'overview');
export const projectHref = (id, tab) => '#/projects/' + id + (tab && tab !== 'overview' ? '/' + tab : '');

// ---------- Replay ----------
export const RP_SECTIONS = [['events', 'Events'], ['evidence', 'Evidence'], ['recovery', 'Recovery'], ['reference', 'Reference']];
export const RP_DETAILS = [['normal', 'Normal'], ['thinking', 'Thinking'], ['verbose', 'Verbose']];
export const replayQuery = (q) => ({
  mode: q.mode === 'compact' ? 'compact' : 'timeline',
  detail: RP_DETAILS.some(([d]) => d === q.detail) ? q.detail : 'normal',
  section: RP_SECTIONS.some(([s]) => s === q.section) ? q.section : null
});
export const replayHref = (id, o) => href('replay/' + id, { mode: o.mode === 'compact' ? 'compact' : '', detail: o.detail === 'normal' ? '' : o.detail, section: o.section });

const BAD = /FAILED|ERROR|BLOCKED|LOST|REJECTED|AWAITING/;
export const isBadStep = (s) => BAD.test(s.state) || s.category === 'UNCERTAIN' || s.category === 'SUSPENDED';
// Open on the step that explains why the mission needs you; a mission that moved on opens on its last step.
export function openStep(steps, needsAttention) {
  if (!steps.length) return null;
  const bad = needsAttention ? steps.filter(isBadStep).pop() : null;
  return (bad || steps[steps.length - 1]).n;
}

// Compact mode: neighbouring steps of one machine become one row, represented by its last step.
export function compactRows(steps) {
  const rows = [];
  for (const s of steps) {
    const last = rows[rows.length - 1];
    if (last && last.machine === s.machine) { last.steps.push(s); last.step = s; } else rows.push({ machine: s.machine, steps: [s], step: s });
  }
  return rows.map((r) => ({ machine: r.machine, n: r.steps.length, first: r.steps[0], last: r.step, step: r.step, bad: r.steps.some(isBadStep) }));
}

// The line above the timeline: how much was recorded, over what time, and what the last step was.
export const whatChanged = (steps) => (steps.length ? { count: steps.length, from: steps[0].time, to: steps[steps.length - 1].time, last: steps[steps.length - 1], bad: steps.filter(isBadStep).length } : null);
