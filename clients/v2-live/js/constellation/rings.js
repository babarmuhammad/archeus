// The Overview rings (owner direction 2026-10-28, concepts R2-C): concentric lanes round the core, one family of lanes per state, from the core outward
// needs you, blocked, running, paused, done. A project sits on the lane of its worst state and a lane exists only if it has members. When a state has more
// members than its lane holds, another lane of the same state is added just outside it, before the next state starts; a lane is never fatter or denser.
// Pure, no DOM. A lane is an ellipse centred on the core; its capacity is its perimeter over the mark pitch of the size tier.
import {clamp, unit, coreCentre, coreKeepOut, coreScaleFor, coversNode, INSET} from './geometry.js';

export const LANES = Object.freeze(['needs-you', 'blocked', 'running', 'paused', 'done']);
// Size tiers by project count: pitch between marks along a lane, the gap between lanes (on the short axis, so marks of two lanes never touch), the mark radius range.
export const TIERS = Object.freeze([
  {name: 'named', max: 12, pitch: 96, gap: 52, rmin: 10, rmax: 26, base: 10, k: 2.2},
  {name: 'mixed', max: 40, pitch: 64, gap: 40, rmin: 7, rmax: 18, base: 7, k: 1.4},
  {name: 'dense', max: Infinity, pitch: 28, gap: 20, rmin: 3, rmax: 9, base: 3, k: .8}]);
export const tierOf = count => TIERS.find(t => count <= t.max);
// The lane a project sits on: the worst of its missions' states (counts of ALL its missions) and its attention items. Planning, approved, quiet and empty are paused.
export function laneOf(counts = {}, attention = 0) {
  if (attention > 0 || counts['needs-you'] > 0) return 'needs-you';
  if (counts.blocked > 0) return 'blocked';
  if (counts.running > 0) return 'running';
  const total = Object.values(counts).reduce((t, n) => t + n, 0);
  return total > 0 && counts.done === total ? 'done' : 'paused';
}
export const markRadius = (missions, tier) => clamp(tier.base + tier.k * Math.sqrt(Math.max(0, missions)), tier.rmin, tier.rmax);
export const perimeter = (rx, ry) => { const h = ((rx - ry) / (rx + ry)) ** 2; return Math.PI * (rx + ry) * (1 + 3 * h / (10 + Math.sqrt(4 - 3 * h))); };
// n points spread evenly by arc length along the ellipse, the first at angle `start` (degrees, clockwise from 12 o'clock). Returns [{x, y, deg, tangent}] relative to the centre.
export function pointsOn(rx, ry, n, start = 0) {
  const S = 720, at = t => [rx * Math.sin(t), -ry * Math.cos(t)], cum = [0];
  for (let i = 1; i <= S; i++) { const [x0, y0] = at((i - 1) * 2 * Math.PI / S), [x1, y1] = at(i * 2 * Math.PI / S); cum.push(cum[i - 1] + Math.hypot(x1 - x0, y1 - y0)); }
  const total = cum[S], t0 = start * Math.PI / 180, first = (() => { let i = Math.round(t0 / (2 * Math.PI) * S) % S; return cum[i]; })(), out = [];
  for (let k = 0; k < n; k++) {
    const want = (first + k * total / n) % total;
    let lo = 0, hi = S;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (cum[mid] <= want) lo = mid; else hi = mid; }
    const t = (lo + (want - cum[lo]) / ((cum[hi] - cum[lo]) || 1)) * 2 * Math.PI / S, [x, y] = at(t);
    out.push({x, y, deg: ((t * 180 / Math.PI) % 360 + 360) % 360, tangent: Math.atan2(ry * Math.sin(t), rx * Math.cos(t))});
  }
  return out;
}
const SCALES = [1, .85, .72, .62, .52];
// The order a lane's slots fill in: bit-reversed, so the first members sit opposite each other and a part-filled lane is balanced round the core instead of bunched (Van der Corput).
const spread = n => Array.from({length: n}, (_, i) => i).sort((p, q) => rev(p, n) - rev(q, n));
const rev = (i, n) => { let r = 0, bits = Math.max(1, Math.ceil(Math.log2(n))); for (let b = 0; b < bits; b++) r = (r << 1) | ((i >> b) & 1); return r; };

const byId = (a, b) => String(a.id).localeCompare(String(b.id));
// projects: [{id, lane, missions, worktrees, ...}]. memory: Map(id -> {state, v}) kept between calls so a mark keeps its place: v is the index inside its state's lanes (lane 0 first), a
// new project takes the lowest free one and nothing already placed moves. avoid: boxes no mark may touch (the zoom column). Returns {nodes, lanes, order, tier, scale, memory, core, keep}.
export function layoutRings(projects, width, height, inset = INSET, {memory = new Map(), avoid = []} = {}) {
  const count = projects.length, tier = tierOf(Math.max(1, count)), u = unit(width, height), core = coreCentre(width, height, inset), keep = coreKeepOut(width, height, u, inset, false, coreScaleFor(count));
  const empty = {nodes: [], lanes: [], order: [], tier, scale: 1, memory: new Map(), core, keep};
  if (!count) return empty;
  const x0 = Math.min(inset.left, width / 10), x1 = width - Math.min(inset.right, width / 10), y0 = Math.min(inset.top, height * .42), y1 = height - Math.min(inset.bottom, height * .26);
  const halfX = Math.max(1, Math.min(core.x - x0, x1 - core.x)), halfY = Math.max(1, Math.min(core.y - y0, y1 - core.y)), aspect = clamp((y1 - y0) / (x1 - x0), .55, .8);
  // Each state's members take their remembered index, the rest the lowest free one.
  const next = new Map(), groups = new Map(LANES.map(l => [l, []]));
  for (const p of [...projects].sort(byId)) groups.get(LANES.includes(p.lane) ? p.lane : 'paused').push(p);
  for (const [state, list] of groups) {
    const used = new Set(list.map(p => memory.get(p.id)).filter(m => m && m.state === state).map(m => m.v));
    for (const p of list) {
      const m = memory.get(p.id);
      if (m && m.state === state) { next.set(p.id, {state, v: m.v}); continue; }
      let v = 0; while (used.has(v)) v++;
      used.add(v); next.set(p.id, {state, v});
    }
  }
  let plan = null;
  for (const s of SCALES) {
    plan = planAt(s);
    if (plan.fits) break;
  }
  return {...plan, tier, memory: next, core, keep};
  function planAt(s) {
    const T = tier, pitch = T.pitch * s, gap = T.gap * s, rMax = Math.max(...projects.map(p => markRadius(p.missions, T) * s)), blocked = (x, y, r) => coversNode(keep.box, {x, y, radius: r}, 4) || avoid.some(b => coversNode(b, {x, y, radius: r}, 0)) || x - r < x0 || x + r > x1 || y - r < y0 || y + r > y1;
    // The first lane passes just outside the core's keep zone and below its wordmark, so no lane crosses a word.
    const first = Math.max(keep.radius + rMax * .6, keep.box.y + keep.box.height - core.y + 6), nodes = [], lanes = [];
    let j = 0;
    for (const state of LANES) {
      const list = groups.get(state);
      if (!list.length) continue;
      const top = Math.max(...list.map(p => next.get(p.id).v)), slots = [];
      // Lanes of this state until the highest index fits. A lane's usable slots are the ones clear of the wordmark box, the controls and the edges.
      for (let n = 0; slots.length <= top && n < 40; n++, j++) {
        const ry = first + j * gap, rx = ry / aspect, cap = Math.max(1, Math.floor(perimeter(rx, ry) / pitch)), pts = pointsOn(rx, ry, cap, 40 * j + 25);
        const clear = pts.filter(q => !blocked(core.x + q.x, core.y + q.y, rMax)), usable = clear.length ? clear : pts;
        lanes.push({state, n, index: j, rx, ry, capacity: usable.length, slots: cap, members: []});
        for (const i of spread(usable.length)) slots.push({...usable[i], lane: lanes.length - 1});
      }
      for (const p of list) {
        const sl = slots[next.get(p.id).v] || slots[slots.length - 1], lane = lanes[sl.lane];
        lane.members.push(p.id);
        nodes.push({...p, id: p.id, x: core.x + sl.x, y: core.y + sl.y, radius: markRadius(p.missions, T) * s, state, lane: true, laneNo: lane.n, laneIndex: lane.index, angle: sl.deg, tangent: sl.tangent});
      }
    }
    const last = lanes[lanes.length - 1], fits = !last || (last.rx + rMax <= halfX + .5 && last.ry + rMax <= halfY + .5);
    // The attention order: needs you lane 1 clockwise from 12 o'clock, lane 2, blocked, running, paused, done.
    const order = [...nodes].sort((a, b) => LANES.indexOf(a.state) - LANES.indexOf(b.state) || a.laneNo - b.laneNo || a.angle - b.angle || byId(a, b)).map(n => n.id);
    return {nodes: nodes.sort(byId), lanes, order, scale: s, fits};
  }
}

// What the model says about a project beyond its drawn marks: the missions by state (all of them, not only the placed ones) and the recent activity.
export const stateCounts = states => states.reduce((c, s) => { c[s] = (c[s] || 0) + 1; return c; }, {});
// Events per project inside the window (default 30 minutes of simulated time): the activity weight. One pass over the log.
export function activityByProject(events, now, windowMs = 30 * 60e3) {
  const out = new Map();
  for (let i = events.length - 1; i >= 0; i--) { const e = events[i]; if (now - e.at > windowMs) break; if (e.project && e.type !== 'clock') out.set(e.project, (out.get(e.project) || 0) + 1); }
  return out;
}
// Arrow keys on the rings (the keyboard path): left and right walk the attention order, up and down step to the nearest mark of the inner or the outer lane (empty lanes are skipped).
export function ringStep({nodes, order}, id, key) {
  const i = order.indexOf(id), me = nodes.find(n => n.id === id);
  if (i < 0 || !me) return null;
  if (key === 'ArrowRight' || key === 'ArrowLeft') return order[(i + (key === 'ArrowRight' ? 1 : -1) + order.length) % order.length];
  const dir = key === 'ArrowDown' ? 1 : key === 'ArrowUp' ? -1 : 0;
  if (!dir) return null;
  const lanes = [...new Set(nodes.map(n => n.laneIndex))].sort((a, b) => a - b), at = lanes.indexOf(me.laneIndex), to = lanes[at + dir];
  if (to === undefined) return null;
  const turn = d => Math.abs(((d % 360) + 540) % 360 - 180);
  return nodes.filter(n => n.laneIndex === to).sort((a, b) => turn(a.angle - me.angle) - turn(b.angle - me.angle))[0]?.id ?? null;
}
