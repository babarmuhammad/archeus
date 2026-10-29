// The Replay mission chooser, as pure functions: filter, count, rank, group and cap. No DOM, no clock.
// A row is { id, title, project, projectName, branch, facet, cls, at, steps }; the facet comes from viewOfCls, the one rule Work counts by, so a number here is a number there.
import { WORK_VIEWS } from './page-model.js';

export const FACETS = WORK_VIEWS.filter(([v]) => v !== 'all'); // needs, running, blocked, done
export const CAP = 20;          // rows shown per section until "Show more"
export const TOP_PROJECTS = 7;  // project chips before "More projects"
export const RECENT_MAX = 5;
const ORDER = Object.fromEntries(FACETS.map(([v], i) => [v, i]));

// every word of the search must appear in the title, the project, the branch or the id
export function matches(row, q) {
  const words = String(q || '').toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = [row.title, row.projectName, row.branch, row.id].join(' ').toLowerCase();
  return words.every((w) => hay.includes(w));
}

// f: { q, project, facet, history }. `skip` leaves one part out, which is how a facet is counted: by what it would show if chosen.
const keep = (rows, f, skip) => rows.filter((r) => (skip === 'q' || matches(r, f.q)) && (skip === 'project' || !f.project || r.project === f.project)
  && (skip === 'facet' || !f.facet || f.facet === 'all' || r.facet === f.facet) && (!f.history || r.steps > 0));
export const filterRows = (rows, f) => keep(rows, f);

export function facetCounts(rows, f) {
  const own = keep(rows, f, 'facet'), n = { all: own.length };
  for (const [v] of FACETS) n[v] = 0;
  for (const r of own) n[r.facet]++;
  return n;
}

export function projectCounts(rows, f) {
  const own = keep(rows, f, 'project'), n = new Map();
  for (const r of own) n.set(r.project, (n.get(r.project) || 0) + 1);
  return { all: own.length, by: n };
}

// Projects by what they ask of the owner: most Needs you, then most Running, then most recent, then name. Ranked on all rows, so the chips do not shuffle as the filters change.
export function rankProjects(rows, projects) {
  const s = new Map(projects.map((p) => [p.id, { id: p.id, name: p.name, needs: 0, running: 0, at: 0, total: 0 }]));
  for (const r of rows) {
    const p = s.get(r.project); if (!p) continue;
    p.total++; p.at = Math.max(p.at, r.at || 0);
    if (r.facet === 'needs') p.needs++; else if (r.facet === 'running') p.running++;
  }
  return [...s.values()].sort((a, b) => b.needs - a.needs || b.running - a.running || b.at - a.at || a.name.localeCompare(b.name) || String(a.id).localeCompare(String(b.id)));
}

// Attention first (the facet order), then the most recent, then the title. The sections are the facets, so this is also the reading order.
export const sortRows = (rows) => [...rows].sort((a, b) => ORDER[a.facet] - ORDER[b.facet] || (b.at || 0) - (a.at || 0) || a.title.localeCompare(b.title) || String(a.id).localeCompare(String(b.id)));

// caps: { [facet]: extra rows the owner asked for }. A section shows CAP + its extra, and says how many it holds back.
export function sections(rows, f, caps = {}) {
  const sorted = sortRows(keep(rows, f)), out = [];
  for (const [v, title] of FACETS) {
    const own = sorted.filter((r) => r.facet === v);
    if (!own.length) continue;
    const take = CAP + (caps[v] || 0);
    out.push({ facet: v, title, total: own.length, rows: own.slice(0, take), more: Math.max(0, own.length - take) });
  }
  return out;
}

// The last few missions replayed, newest first, one entry each.
export const pushRecent = (list, id, max = RECENT_MAX) => [id, ...(Array.isArray(list) ? list : []).filter((x) => x !== id)].slice(0, max);
export function recentRows(rows, ids) {
  const by = new Map(rows.map((r) => [r.id, r]));
  return (Array.isArray(ids) ? ids : []).map((id) => by.get(id)).filter(Boolean).slice(0, RECENT_MAX);
}

// What is remembered is only a project and a state; both are dropped when they no longer exist.
export function remembered(saved, projects) {
  const s = saved && typeof saved === 'object' ? saved : {};
  return { project: projects.some((p) => p.id === s.project) ? s.project : null, facet: FACETS.some(([v]) => v === s.facet) ? s.facet : 'all' };
}

// The rows a reader can move through with the arrows, in order: recents, then each section's rows, then a "Show more" stop for a section that holds rows back.
export function stops(recents, secs) {
  const out = recents.map((r) => ({ type: 'row', row: r, recent: true }));
  for (const s of secs) { s.rows.forEach((r) => out.push({ type: 'row', row: r })); if (s.more) out.push({ type: 'more', facet: s.facet, n: Math.min(CAP, s.more) }); }
  return out;
}
