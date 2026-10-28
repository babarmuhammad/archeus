// Phone lists, as pure functions: the Work chips and sections, the phone graph (what is drawn, where, which labels fit) and the Projects groups with their caps. No DOM.
// The desktop pages keep their own layout; the phone gets these so a hundred projects or ninety-seven missions are never a wall.
import { WORK_VIEWS, graphPick, viewOfCls } from '../page-model.js';

export const SECTION_CAP = 20;   // rows per section until "Show 20 more"
export const GRAPH_NODES = 9;    // what the phone graph draws; the list has the rest
export const PROJECT_STEP = 20;  // projects per group until "Show 20 more"
const LABEL = Object.fromEntries(WORK_VIEWS);

// ---------- Work: the chip row ----------
// Needs you, Running and All always; a view that lives behind "More states" (Blocked, Done) takes a fourth chip while it is the one shown, so the row never hides the filter.
export function workChips(counts, view) {
  const chip = (id) => ({ id, label: LABEL[id], n: counts[id] || 0, on: view === id });
  const extra = view === 'blocked' || view === 'done' ? [chip(view)] : [];
  return { chips: [...['needs', 'running', 'all'].map(chip), ...extra], more: ['blocked', 'done'].map(chip) };
}

// ---------- Work: sections ----------
export const SECTIONS = [['needs', 'Needs you'], ['running', 'Running'], ['blocked', 'Blocked'], ['done', 'Quiet']];
// rows: { id, cls, at }, already filtered. `pages[key]` counts the "Show more" taps. Needs you lists the longest waiting first, the rest the newest first.
export function workSections(rows, pages = {}, cap = SECTION_CAP) {
  return SECTIONS.map(([key, label]) => {
    const own = rows.filter((r) => viewOfCls(r.cls) === key).sort((a, b) => (key === 'needs' ? a.at - b.at : b.at - a.at) || String(a.id).localeCompare(String(b.id)));
    const shown = Math.min(own.length, cap * (1 + (pages[key] || 0)));
    return { key, label, count: own.length, rows: own.slice(0, shown), left: own.length - shown, next: Math.min(cap, own.length - shown) };
  }).filter((s) => s.count);
}

// Projects for the picker sheet: what asks most of the owner first. entries: { project, cls }.
export function rankProjects(entries, projects) {
  const n = new Map(projects.map((p) => [p.id, { needs: 0, all: 0 }]));
  for (const e of entries) { const c = n.get(e.project); if (c) { c.all++; if (viewOfCls(e.cls) === 'needs') c.needs++; } }
  return projects.map((p) => ({ p, ...n.get(p.id) })).sort((a, b) => b.needs - a.needs || b.all - a.all || a.p.name.localeCompare(b.p.name) || String(a.p.id).localeCompare(String(b.p.id)));
}

// ---------- the phone graph ----------
// Drawn: the entries the filter keeps, in rank order, at most GRAPH_NODES; with no filter the most urgent ones. `more` is what only the list shows.
export function phoneGraphPick(entries, shown, filtered, rank, prev = []) {
  const pool = filtered ? shown : entries, picked = graphPick(pool, pool, GRAPH_NODES, rank, prev);
  return { picked, more: pool.length - picked.length };
}

// n nodes on an ellipse round the core, the first at the top and then clockwise; a few nodes stay close to the core instead of reaching the edge.
export function ringLayout(n, w, h, node) {
  const cx = w / 2, cy = h / 2, fit = n < 5 ? .62 + n * .08 : 1, rx = Math.max(0, (w / 2 - node - 8) * fit), ry = Math.max(0, (h / 2 - node - 28) * fit);
  return Array.from({ length: n }, (_, i) => { const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(n, 1); return { x: Math.round(cx + rx * Math.cos(a)), y: Math.round(cy + ry * Math.sin(a)) }; });
}

// A label is one line of at most `max` characters (the full title is in the peek card and in the node's name). Width is an upper estimate so the box always holds the text.
export const LABEL_MAX = 18;
export const shortLabel = (t, max = LABEL_MAX) => (t.length > max ? t.slice(0, max - 1).trimEnd() + '…' : t);
export const labelWidth = (text, size) => Math.ceil(text.length * size * .62);

const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const hitsNode = (r, n, pad) => { const x = Math.max(r.x, Math.min(n.x, r.x + r.w)), y = Math.max(r.y, Math.min(n.y, r.y + r.h)); return (x - n.x) ** 2 + (y - n.y) ** 2 < (n.r + pad) ** 2; };

// Which nodes get a label and where. items: { id, x, y, r, text, priority } (higher first). Each label tries below, above, beside its node, then below and above lined up with the node's edge, and takes the first
// spot that is inside the box, off every node, off `avoid` (rectangles such as a floating button) and off the labels already placed; a label with no free spot is left out (the node still has its name for a screen
// reader). Returns Map id -> { x, y, w, h, anchor }: x is where the text starts, ends or is centred, y its middle.
export function placeLabels(items, box, { size = 13, gap = 6, avoid = [] } = {}) {
  const placed = new Map(), taken = [...avoid], lh = Math.round(size * 1.3);
  for (const it of [...items].sort((a, b) => b.priority - a.priority || String(a.id).localeCompare(String(b.id)))) {
    const w = labelWidth(it.text, size), h = lh, below = it.y + it.r + gap, above = it.y - it.r - gap - h;
    const spots = [
      { x: it.x - w / 2, y: below, anchor: 'middle' }, { x: it.x - w / 2, y: above, anchor: 'middle' },
      { x: it.x + it.r + gap, y: it.y - h / 2, anchor: 'start' }, { x: it.x - it.r - gap - w, y: it.y - h / 2, anchor: 'end' },
      { x: it.x - it.r, y: below, anchor: 'start' }, { x: it.x + it.r - w, y: below, anchor: 'end' }, { x: it.x - it.r, y: above, anchor: 'start' }, { x: it.x + it.r - w, y: above, anchor: 'end' }
    ];
    const ok = spots.find((s) => { const r = { x: s.x, y: s.y, w, h }; return r.x >= box.x && r.y >= box.y && r.x + w <= box.x + box.w && r.y + h <= box.y + box.h && !items.some((n) => hitsNode(r, n, 2)) && !taken.some((t) => hit(r, t)); });
    if (!ok) continue;
    taken.push({ x: ok.x, y: ok.y, w, h });
    placed.set(it.id, { x: ok.anchor === 'middle' ? it.x : ok.anchor === 'start' ? ok.x : ok.x + w, y: ok.y + h / 2, w, h, anchor: ok.anchor });
  }
  return placed;
}

// Pan and zoom: never smaller than the fitted view, so a label never drops under its size; the content cannot be dragged away from the box.
export const ZOOM = { min: 1, max: 3 };
export const clampView = (v, w, h) => { const k = Math.max(ZOOM.min, Math.min(ZOOM.max, v.k)); return { k, x: Math.max(w - w * k, Math.min(0, v.x)), y: Math.max(h - h * k, Math.min(0, v.y)) }; };

// ---------- Projects ----------
// groups: [{ key, label }]; each project says which group it is in. The first `step` of a group are listed, `pages[key]` taps of "Show 20 more" add more.
// The quiet group starts folded when there are many projects, and a search leaves every group open.
export function projectGroups(list, groupOf, groups, { pages = {}, step = PROJECT_STEP, many = false, searching = false } = {}) {
  return groups.map(({ key, label }) => {
    const own = list.filter((p) => groupOf(p) === key), shown = Math.min(own.length, step * (1 + (pages[key] || 0)));
    return { key, label, count: own.length, rows: own.slice(0, shown), left: own.length - shown, next: Math.min(step, own.length - shown), fold: key === 'quiet' && many && !searching };
  }).filter((g) => g.count);
}
