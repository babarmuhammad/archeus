// Semantic zoom for the Network view (pure, no DOM). Zooming in makes the projects near the view centre more detailed while the rest stay compact:
//   level 0  overview: hub, code, state, counts (what the density level of the layout shows); worktrees fold into a count on the hub
//   level 1  every mission of the project as a satellite with its title; worktrees are sub-hubs and their missions hang off them
//   level 2  per mission its tasks, attempts, verification and approval as small marks; ideas as marks of their own
//   level 3  the focused mission's events as a small timeline ring
// Glyphs keep their size on screen: a level is laid out for the camera scale it starts at (REF), so zooming in spreads the marks apart instead of only magnifying them.
// A worktree is never a project: it is a sub-hub between its project's hub and the missions that work in it.
import {satRank, coversNode} from './geometry.js';
const TAU = Math.PI * 2;

export const REF = Object.freeze([1, 1.6, 3.2, 6.4]);
export const UP = REF;                       // the camera scale at which a level begins
export const HYST = 1.15;                    // a level is kept until the scale falls 15 % under its start
export const BUDGET = 300;                   // detailed nodes drawn at once, whatever the project count
export const MAX_K = 8, MIN_K = .5;
const PX = Object.freeze({hub: 26, mission: 17, worktree: 13, kid: 6.5, kidOrbit: 34, idea: 7, event: 4, gap: 6});
const CAP = Object.freeze({missions: [0, 80, 60, 60], worktrees: [0, 12, 12, 12], ideas: [0, 6, 10, 10], kids: [0, 2, 6, 6], rings: 6, events: 16});
// The radius each kind of node is drawn at; the art is then scaled to the laid out radius, so a small mark is the same picture as a big one.
export const DRAW = Object.freeze({Project: 26, Mission: 18, Worktree: 14, Execution: 11, Task: 11, Verification: 11, Decision: 11, Idea: 11, Event: 6});
const EDGE = Object.freeze({Execution: 'runs', Decision: 'asks', Idea: 'contains', Mission: 'contains', Worktree: 'contains'});

// The level the camera scale asks for, with hysteresis around every threshold so a wheel or pinch hovering at one does not flicker.
export function levelFor(k, prev = 0) {
  let level = prev;
  while (level < 3 && k >= UP[level + 1]) level++;
  while (level > 0 && k < UP[level] / HYST) level--;
  return level;
}
// Nodes a project costs at a level (an estimate before the data is read; expandCluster stops at the limit it is given).
export function costOf(missions, ideas, level, worktrees = 0) {
  if (level <= 0) return 0;
  const shown = Math.min(missions, CAP.missions[level]);
  return 1 + shown * (level >= 2 ? 1 + 3 : 1) + Math.min(ideas, CAP.ideas[level]) + Math.min(worktrees, CAP.worktrees[level]);
}
// Which projects expand and how far. hubs: [{id, x, y, missions, ideas, worktrees}] on screen; the nearest to `centre` gets the deepest level, the others down to level 2,
// and projects are added by distance until the node budget is spent. A project that is open stays open a little farther out (hysteresis).
export function expansion({k, prevGlobal = 0, prev = new Map(), hubs, centre, radius, budget = BUDGET}) {
  const global = levelFor(k, prevGlobal), levels = new Map();
  if (global === 0) return {global, levels};
  const order = hubs.map(h => ({...h, d: Math.hypot(h.x - centre.x, h.y - centre.y)})).sort((a, b) => a.d - b.d || String(a.id).localeCompare(String(b.id)));
  let left = budget, first = true;
  for (const h of order) {
    if (h.d > radius * (prev.get(h.id) ? 1.25 : 1)) break;
    let level = Math.min(global, first ? 3 : 2);
    while (level > 0 && costOf(h.missions, h.ideas, level, h.worktrees) > left) level--;
    if (level > 0) { levels.set(h.id, level); left -= costOf(h.missions, h.ideas, level, h.worktrees); first = false; }
  }
  return {global, levels};
}
export const sameLevels = (a, b) => a.size === b.size && [...a].every(([id, level]) => b.get(id) === level);
// The mission whose timeline opens: the nearest to the centre, kept until another is clearly (20 px) nearer.
export function pickFocus(prevId, candidates) {
  if (!candidates.length) return null;
  const best = candidates.reduce((a, b) => (b.d < a.d ? b : a)), kept = candidates.find(c => c.id === prevId);
  return kept && kept.d <= best.d + 20 ? kept.id : best.id;
}
// Projects whose hub lies inside the grown cluster (plus a margin) give way to it: they fade instead of crossing it.
export function receding(hubs, open, margin = 60) {
  const out = new Set();
  for (const o of open) for (const h of hubs) if (h.id !== o.id && Math.hypot(h.x - o.x, h.y - o.y) < o.extent + margin) out.add(h.id);
  return out;
}

// The laid-out cluster of one project at one level. Inputs: hub {x, y, tag:{width}, outward}, missions (graph nodes; a mission with `worktree` hangs off that worktree),
// worktrees (Worktree nodes of the project), kids Map(missionId -> nodes), ideas, events, blocked(x, y, r) -> true where a node may not stand (the core, the zoom column,
// other hubs), limit (nodes). Returns {nodes, edges, quiet, wtQuiet, extent, hub} in world units; edges run hub - worktree - mission and mission - its marks, nothing else.
export function expandCluster({level, key, hub, missions, worktrees = [], kids = new Map(), ideas = [], events = [], focusId = null, blocked = () => false, limit = BUDGET}) {
  const s = 1 / REF[Math.min(level, 2)], px = v => v * s, hubR = px(PX.hub), mr = px(PX.mission), wr = px(PX.worktree), kr = px(PX.kid), gap = px(PX.gap);
  const fp = level >= 2 ? px(PX.kidOrbit) : mr, tagW = hub.tag?.width ?? 200, tagH = 40;
  const tagBox = {x: hub.x - px(tagW) / 2, y: hub.y + hubR + px(4), width: px(tagW), height: px(tagH)};
  const outward = hub.outward ?? 0, spin = a => Math.abs(((a - outward + 3 * Math.PI) % TAU) - Math.PI);
  const nodes = [], edges = [], taken = [], slots = [], placedIdea = new Set();
  const hubNode = {x: hub.x, y: hub.y, radius: hubR, art: DRAW.Project, lines: 2, tag: {x: hub.x - px(tagW) / 2, y: tagBox.y, width: tagW, height: tagH}};
  const room = () => nodes.length < limit;
  const clear = (x, y, r, list) => !blocked(x, y, r) && !coversNode(tagBox, {x, y, radius: r}, gap) && Math.hypot(x - hub.x, y - hub.y) >= hubR + r + gap && [list, taken].every(l => l.every(o => Math.hypot(x - o.x, y - o.y) >= r + o.r + gap));
  const add = (src, x, y, r, parent, kind = src.kind) => {
    nodes.push({...src, kind, x, y, radius: r, art: DRAW[kind], cluster: key, rank: 1, detail: true, parent});
    taken.push({x, y, r}); edges.push({from: parent, to: src.id, kind: EDGE[kind] || 'part'});
  };
  // Candidate places for something of radius `reserve` round the hub: rings outward, the side away from the core first.
  const spots = reserve => {
    const out = [];
    for (let ring = 0; ring < CAP.rings; ring++) {
      const ro = hubR + reserve + gap + ring * (2 * reserve + gap), count = Math.max(6, Math.floor(TAU * ro / (2 * reserve + gap)));
      Array.from({length: count}, (_, i) => -Math.PI + (i + (ring % 2 ? .5 : 0)) * TAU / count).sort((p, q) => spin(p) - spin(q) || p - q).forEach(a => out.push([hub.x + Math.cos(a) * ro, hub.y + Math.sin(a) * ro]));
    }
    return out;
  };
  // Ideas first: small marks on the side facing the core.
  const ideaR = px(PX.idea), inward = outward + Math.PI;
  ideas.slice(0, CAP.ideas[level]).forEach(idea => {
    if (!room()) return;
    for (const row of [0, 1]) for (const d of [0, 1, -1, 2, -2, 3, -3].map(v => v * .5)) {
      const a = inward + d + row * .25, dist = hubR + ideaR + px(5) + row * (2 * ideaR + px(2)), x = hub.x + Math.cos(a) * dist, y = hub.y + Math.sin(a) * dist;
      if (!placedIdea.has(idea.id) && clear(x, y, ideaR, taken)) { placedIdea.add(idea.id); add(idea, x, y, ideaR, key, 'Idea'); return; }
    }
  });
  const ranked = [...missions].sort((a, b) => satRank(a) - satRank(b) || String(a.id).localeCompare(String(b.id))).slice(0, CAP.missions[level]);
  const wts = worktrees.slice(0, CAP.worktrees[level]), has = new Set(wts.map(w => w.id)), free = ranked.filter(m => !has.has(m.worktree));
  const around = (cx, cy, away, near, r, list, rows = 2) => [...Array(rows).keys()].flatMap(row => [0, 40, -40, 80, -80, 120, -120, 160, 180].map(d => {
    const a = away + d * Math.PI / 180, dist = near + r + row * (2 * r + gap);
    return [cx + Math.cos(a) * dist, cy + Math.sin(a) * dist];
  })).find(([x, y]) => clear(x, y, r, list));
  // Worktrees: sub-hubs on the first rings, each with the missions that work in it hanging round it, away from the hub.
  for (const w of wts) {
    if (!room()) break;
    const mine = ranked.filter(m => m.worktree === w.id), reserve = wr + gap + (mine.length ? fp * Math.min(3, 1 + Math.sqrt(mine.length) * 1.3) : 0);
    const at = spots(reserve).find(([x, y]) => clear(x, y, reserve, slots));
    if (!at) { free.push(...mine); continue; }
    add(w, at[0], at[1], wr, key); slots.push({x: at[0], y: at[1], r: wr + gap});
    const away = Math.atan2(at[1] - hub.y, at[0] - hub.x);
    for (const m of mine) {
      const spot = room() && around(at[0], at[1], away, wr + gap, fp, slots, 3);
      if (spot) { slots.push({x: spot[0], y: spot[1], r: fp}); add(m, spot[0], spot[1], mr, w.id); } else free.push(m);
    }
  }
  // The missions of no worktree sit on rings round the hub, as before.
  let next = 0;
  for (const [x, y] of spots(fp)) {
    if (next >= free.length || !room()) break;
    if (clear(x, y, fp, slots)) { slots.push({x, y, r: fp}); add(free[next++], x, y, mr, key); }
  }
  const placed = nodes.filter(n => n.kind === 'Mission');
  for (const m of placed) {
    if (level < 1 || !room()) break;
    const away = Math.atan2(m.y - hub.y, m.x - hub.x);
    if (level >= 3 && m.id === focusId) {
      // The timeline ring: the mission's events clockwise from the top.
      const list = events.slice(-CAP.events), rt = mr + px(14), er = px(PX.event);
      list.forEach((ev, i) => { if (room()) { const a = -Math.PI / 2 + (list.length > 1 ? i * (TAU * .83) / (list.length - 1) : 0); add(ev, m.x + Math.cos(a) * rt, m.y + Math.sin(a) * rt, er, m.id, 'Event'); } });
      continue;
    }
    const mine = (kids.get(m.id) || []).slice().sort((a, b) => satRank(a) - satRank(b) || String(a.id).localeCompare(String(b.id))).slice(0, CAP.kids[level]);
    for (const kid of mine) {
      const spot = room() && around(m.x, m.y, away, mr + px(3), kr, taken);
      if (spot) add(kid, spot[0], spot[1], kr, m.id);
    }
  }
  const extent = Math.max(hubR, ...nodes.map(n => Math.hypot(n.x - hub.x, n.y - hub.y) + n.radius));
  const shownWt = nodes.filter(n => n.kind === 'Worktree').length;
  return {nodes, edges, quiet: missions.length - placed.length, wtQuiet: worktrees.length - shownWt, extent, hub: hubNode};
}

export const OVERVIEW_MAX = UP[1] / HYST - .05;           // Fit frames the overview and stays under the first level of detail
