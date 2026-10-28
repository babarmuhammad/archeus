const TAU = Math.PI * 2;
export const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
export const INSET = Object.freeze({top: 16, right: 16, bottom: 60, left: 16});
export const unit = (width, height) => clamp(Math.sqrt(width * height) / 900, .9, 1.6);
export const coreCentre = (width, height, inset = INSET) => ({x: width / 2, y: (inset.top + height - inset.bottom) / 2});
export const CALM_CORE = 2.1;
export const coreRadius = (u, calm, width = 1000) => 52 * u * (calm ? (width < 600 ? 1.2 : CALM_CORE) : 1);
export const coreReach = (width, calm) => (calm ? 1.1 : width < 480 ? 1.25 : 1.75);
export function randomSeed(seed) {
  let n = 2166136261;
  for (const c of String(seed)) n = Math.imul(n ^ c.charCodeAt(0), 16777619);
  return () => {
    n += 0x6D2B79F5;
    let t = Math.imul(n ^ n >>> 15, 1 | n);
    t ^= t + Math.imul(t ^ t >>> 7, 61 | t);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
// Ambient motion parameters of one node or relation, seeded by its id: a drift of 1.5 to 3 px along a fixed direction, 9 to 17 s per swing, started at its own phase.
export function driftOf(seed, id) {
  const r = randomSeed(`drift|${seed}|${id}`), amp = 1.5 + r() * 1.5, angle = r() * Math.PI * 2, period = 9000 + r() * 8000, phase = r();
  return {dx: +(Math.cos(angle) * amp).toFixed(2), dy: +(Math.sin(angle) * amp).toFixed(2), period: Math.round(period), delay: -Math.round(phase * period)};
}
export function stateKey(state) {
  const key = String(state || 'idle').toLowerCase().replace(/[ _]/g, '-');
  return ({waiting: 'needs-you', attention: 'needs-you', active: 'running', completed: 'done'})[key] || key;
}
export const isCrystal = n => n.kind === 'Mission' && ['running', 'needs-you'].includes(stateKey(n.state));
// Open space: only the top few running or needs-you missions are drawn as big crystals, the rest shrink to minor nodes.
export const CRYSTAL_BUDGET = 3;
export const crystalIds = nodes => new Set(nodes.filter(isCrystal).sort((a, b) => (stateKey(b.state) === 'needs-you') - (stateKey(a.state) === 'needs-you') || String(a.id).localeCompare(String(b.id))).slice(0, CRYSTAL_BUDGET).map(n => n.id));
export const wordmarkSize = (u, calm) => Math.round((12.5 * u + 2) * (calm ? 1.35 : 1));
// What the layout keeps clear of: the core star (a circle) and the wordmark with its tagline under it (a box).
export function coreKeepOut(width, height, u, inset = INSET, calm = false, scale = 1) {
  const c = coreCentre(width, height, inset), R = coreRadius(u, calm, width) * scale, ws = wordmarkSize(u, calm), reach = coreReach(width, calm);
  return {x: c.x, y: c.y, radius: R * reach + 8 * u,
    box: {x: c.x - 6.5 * ws, y: c.y + R * .6, width: 13 * ws, height: R * reach + (width < 480 || !(calm || taglineOn(scale)) ? 2.8 : 4.6) * ws - R * .6}};
}
// Moves a node off the core circle and the wordmark box (to the nearest free side), then back inside the area.
function keepClear(n, keep, {left, right, top, bottom, width, height}) {
  const dx = n.x - keep.x, dy = n.y - keep.y, d = Math.hypot(dx, dy) || .01, need = keep.radius + n.radius * .5;
  if (d < need) { n.x = keep.x + dx / d * need; n.y = keep.y + dy / d * need; }
  if (coversNode(keep.box, n, 6)) {
    const r = n.radius + 6, bx = keep.box, fits = ([x, y]) => x >= left + n.radius && x <= width - right - n.radius && y >= top + n.radius && y <= height - bottom - n.radius;
    const options = [[n.x, bx.y - r], [n.x, bx.y + bx.height + r], [bx.x - r, n.y], [bx.x + bx.width + r, n.y]].sort((p, q) => (fits(q) - fits(p)) || Math.hypot(p[0] - n.x, p[1] - n.y) - Math.hypot(q[0] - n.x, q[1] - n.y));
    [n.x, n.y] = options[0];
  }
  n.x = clamp(n.x, left + n.radius, width - right - n.radius);
  n.y = clamp(n.y, top + n.radius, height - bottom - n.radius);
}
export function layoutPhone(graph, width, height) {
  const priority = n => stateKey(n.state) === 'needs-you' ? 3 : stateKey(n.state) === 'running' ? 2 : 1;
  const missions = graph.nodes.filter(n => n.kind === 'Mission').sort((a, b) => priority(b) - priority(a) || String(a.id).localeCompare(String(b.id)));
  const lead = missions[0];
  const others = missions.filter(n => n !== lead && stateKey(n.state) !== 'needs-you');
  const projects = graph.nodes.filter(n => n.kind === 'Project').sort((a, b) => String(a.id).localeCompare(String(b.id)));
  const nodes = [...(lead ? [lead] : []), ...others, ...projects].slice(0, 4);
  const slots = [[.2, .78], [.82, .43], [.16, .16], [.82, .13]];
  return nodes.map((n, i) => ({...n, phone: true, x: width * slots[i][0], y: height * slots[i][1], radius: i === 0 && stateKey(n.state) === 'needs-you' ? 26 : 9, rank: priority(n)}));
}
// Project clusters (the Network view). Each project is a hub on a staggered lattice of cells round the core, its missions orbit it as satellites and their
// executions and decisions sit beside them. The cell size is the density level: the largest that holds every project, so the slots of a level never move when a project is added.
// Cells nearest the core come first and are given to the projects the owner has to look at first (the caller freezes that order). Satellites keep the slot they were first given.
export const coreScaleFor = count => (count <= 8 ? .8 : count <= 16 ? .7 : .5);
export const taglineOn = scale => scale >= .7;
// Cell and radii per level, roomy to tight. lines: hub label lines (2 name and last action, 1 name, 0 the code only); cap: satellites shown; only: attention, running and blocked ones only.
export const CELLS = Object.freeze([
  {w: 340, h: 232, hub: 30, sat: 20, kid: 11, lines: 2, cap: 18}, {w: 300, h: 208, hub: 28, sat: 18, kid: 10, lines: 2, cap: 14},
  {w: 250, h: 176, hub: 26, sat: 16, kid: 9, lines: 2, cap: 12}, {w: 206, h: 148, hub: 24, sat: 14, kid: 8, lines: 2, cap: 10},
  {w: 164, h: 120, hub: 22, sat: 12, kid: 7, lines: 1, cap: 8}, {w: 128, h: 96, hub: 19, sat: 10, kid: 0, lines: 1, cap: 6, only: true},
  {w: 100, h: 80, hub: 17, sat: 8, kid: 0, lines: 1, cap: 4, only: true}, {w: 80, h: 66, hub: 15, sat: 7, kid: 0, lines: 0, cap: 3, only: true},
  {w: 64, h: 54, hub: 13, sat: 0, kid: 0, lines: 0, cap: 0, only: true}, {w: 48, h: 44, hub: 10, sat: 0, kid: 0, lines: 0, cap: 0, only: true}]);
const CELL_PAD = 6, GAP = 5, TAG = [13, 34, 40];
export const satRank = n => ({'needs-you': 0, running: 1, blocked: 2, paused: 3, thinking: 3, idle: 4, done: 5})[stateKey(n.state)] ?? 4;
const byRank = (a, b) => satRank(a) - satRank(b) || String(a.id).localeCompare(String(b.id));
const inside = (x, y, r, box) => x - r >= box.x && x + r <= box.x + box.width && y - r >= box.y && y + r <= box.y + box.height;
// The cells of one level: the best of four lattice phases (rows and columns on or between the core's lines), minus what touches the core, its wordmark, the inset or a reserved box.
function cellsOf(level, width, height, inset, keep, core, avoid) {
  const {w, h} = CELLS[level], x0 = Math.min(inset.left, width / 10), x1 = width - Math.min(inset.right, width / 10), y0 = Math.min(inset.top, height * .42), y1 = height - Math.min(inset.bottom, height * .26);
  const halfX = Math.max(1, Math.min(core.x - x0, x1 - core.x)), halfY = Math.max(1, Math.min(core.y - y0, y1 - core.y));
  let best = [];
  for (const [rows, cols] of [[0, 0], [.5, 0], [0, .5], [.5, .5]]) {
    const found = [];
    for (let j = -Math.ceil(height / h); j <= Math.ceil(height / h); j++) for (let i = -Math.ceil(width / w); i <= Math.ceil(width / w); i++) {
      const cx = core.x + (i + cols + (j & 1 ? .5 : 0)) * w, cy = core.y + (j + rows) * h, box = {x: cx - w / 2, y: cy - h / 2, width: w, height: h};
      if (box.x < x0 || box.y < y0 || box.x + w > x1 || box.y + h > y1 || coversNode(box, {x: keep.x, y: keep.y, radius: keep.radius}, 0) || overlaps(box, keep.box) || avoid.some(a => overlaps(box, a))) continue;
      found.push({x: box.x, y: box.y, w, h, d: Math.round(Math.hypot((cx - core.x) / halfX, (cy - core.y) / halfY) * 12), a: ((Math.atan2(cy - core.y, cx - core.x) - Math.PI) % TAU + TAU) % TAU});
    }
    if (found.length > best.length) best = found;
  }
  return best.sort((p, q) => p.d - q.d || p.a - q.a).map(({d, a, ...cell}) => cell);
}
export function plan(count, width, height, inset = INSET, avoid = []) {
  const u = unit(width, height), scale = coreScaleFor(count), keep = coreKeepOut(width, height, u, inset, false, scale), core = coreCentre(width, height, inset);
  let level = 0, cells = cellsOf(0, width, height, inset, keep, core, avoid);
  while (cells.length < count && level < CELLS.length - 1) cells = cellsOf(++level, width, height, inset, keep, core, avoid);
  // A window too small for any cell still gets one, so every project has somewhere to be.
  if (!cells.length) cells = [{x: inset.left, y: inset.top, w: Math.max(1, width - inset.left - inset.right), h: Math.max(1, height - inset.top - inset.bottom)}];
  return {scale, keep, core, level, cells, ...CELLS[level]};
}
export function layout(graph, width, height, inset = INSET, {slots, memory, avoid = []} = {}) {
  if (!graph.nodes.length) return {nodes: [], scale: 1, level: 0, memory: new Map()};
  const keyOf = n => n.project || 'unassigned', byId = new Map(graph.nodes.map(n => [n.id, n]));
  const order = [...new Set(graph.nodes.map(keyOf))].sort((a, b) => (slots?.get(a) ?? 1e9) - (slots?.get(b) ?? 1e9) || String(a).localeCompare(String(b)));
  const P = plan(order.length, width, height, inset, avoid), {core} = P, gap = P.sat >= 12 ? GAP : 2, stamp = `${P.level}|${P.scale}|${width}x${height}`;
  const parentOf = new Map();
  for (const e of graph.edges || []) { const from = byId.get(e.from); if (from && from.kind !== 'Project' && byId.has(e.to) && !parentOf.has(e.to)) parentOf.set(e.to, e.from); }
  const out = [], kept = new Map();
  order.forEach((key, slot) => {
    const cell = P.cells[slot] || P.cells[P.cells.length - 1], mine = graph.nodes.filter(n => keyOf(n) === key), hub = mine.find(n => n.kind === 'Project');
    const sats = mine.filter(n => n !== hub && !parentOf.has(n.id)).sort(byRank), kids = new Map();
    for (const n of mine) if (parentOf.has(n.id)) { if (!kids.has(parentOf.get(n.id))) kids.set(parentOf.get(n.id), []); kids.get(parentOf.get(n.id)).push(n); }
    const content = {x: cell.x + CELL_PAD, y: cell.y + CELL_PAD, width: cell.w - 2 * CELL_PAD, height: cell.h - 2 * CELL_PAD}, hubR = hub ? P.hub : 0, lines = hub ? P.lines : 0;
    const tagH = hub ? TAG[lines] : 0, block = 2 * hubR + (tagH ? 4 + tagH : 0), tagW = Math.min(content.width, P.level <= 1 ? 200 : 220);
    // In the roomy levels the hub leans towards the core as far as its label allows (the label stays inside the cell), so a few projects sit close to it and their satellites open outward.
    const lean = P.level <= 2 && tagH ? Math.sign(core.x - (cell.x + cell.w / 2)) * (content.width - tagW) / 2 : 0, hx = cell.x + cell.w / 2 + lean, hy = cell.y + cell.h / 2 - block / 2 + hubR;
    const tag = tagH ? {x: hx - tagW / 2, y: hy + hubR + 4, width: tagW, height: tagH} : null;
    const outward = Math.atan2(hy - core.y, hx - core.x), spin = a => Math.abs(((a - outward + 3 * Math.PI) % TAU) - Math.PI);
    const clear = (x, y, r) => inside(x, y, r, content) && !(tag && coversNode(tag, {x, y, radius: r}, gap)) && !avoid.some(a => coversNode(a, {x, y, radius: r}, 0)) && Math.hypot(x - hx, y - hy) >= hubR + r + gap;
    const cand = [];
    for (let k = 0; k < 4 && P.sat; k++) {
      const ro = hubR + P.sat + gap + (P.sat >= 12 ? 3 : 0) + k * (2 * P.sat + gap), ring = [];
      for (let a = 0; a < 36; a++) ring.push(a * TAU / 36 - Math.PI);
      for (const a of ring.sort((p, q) => spin(p) - spin(q) || p - q)) { const x = hx + Math.cos(a) * ro, y = hy + Math.sin(a) * ro; if (clear(x, y, P.sat)) cand.push([x, y]); }
    }
    const taken = [], free = (x, y, r) => clear(x, y, r) && taken.every(o => Math.hypot(x - o.x, y - o.y) >= r + o.r + gap);
    const placed = new Map(), recall = id => { const m = memory?.get(id); return m && m.key === stamp ? [hx + m.dx, hy + m.dy] : null; };
    const put = (n, x, y, r) => { placed.set(n.id, {x, y, r}); taken.push({x, y, r}); };
    const shown = sats.filter(n => !P.only || satRank(n) <= 2).slice(0, P.cap);
    for (const n of shown) { const at = recall(n.id); if (at && free(at[0], at[1], P.sat)) put(n, at[0], at[1], P.sat); }
    if (P.kid) for (const n of shown) if (placed.has(n.id) && kids.has(n.id)) for (const k of kids.get(n.id).slice(0, 4)) { const at = recall(k.id); if (at && free(at[0], at[1], P.kid)) put(k, at[0], at[1], P.kid); }
    for (const n of shown) if (!placed.has(n.id)) { const at = cand.find(([x, y]) => free(x, y, P.sat)); if (at) put(n, at[0], at[1], P.sat); }
    if (P.kid) for (const n of shown) {
      const m = placed.get(n.id);
      if (!m || !kids.has(n.id)) continue;
      const away = Math.atan2(m.y - hy, m.x - hx);
      for (const k of kids.get(n.id).sort(byRank).slice(0, 4)) {
        if (placed.has(k.id)) continue;
        const spot = [0, 1, 2].flatMap(i => [0, 35, -35, 70, -70, 105, -105, 140, -140, 180].map(d => { const a = away + d * Math.PI / 180, dist = m.r + P.kid + 4 + i * (2 * P.kid + 4); return [m.x + Math.cos(a) * dist, m.y + Math.sin(a) * dist]; })).find(([x, y]) => free(x, y, P.kid));
        if (spot) put(k, spot[0], spot[1], P.kid);
      }
    }
    const quiet = sats.filter(n => !placed.has(n.id)).length;
    if (hub) out.push({...hub, x: hx, y: hy, radius: hubR, rank: 8, hub: true, cluster: key, quiet, tag, lines});
    for (const [id, p] of placed) { out.push({...byId.get(id), x: p.x, y: p.y, radius: p.r, rank: 1, cluster: key}); kept.set(id, {dx: p.x - hx, dy: p.y - hy, key: stamp}); }
  });
  return {nodes: out.sort((a, b) => String(a.id).localeCompare(String(b.id))), scale: P.scale, level: P.level, memory: kept};
}
// Calm (concept 07): only the projects, as large pointy-top hexagon panels round the core, each one listing its own items.
// Up to four sit at the corners; more spread along an ellipse that skips the wordmark below the core. The radius shrinks until no two panels or the core keep-out touch.
export function layoutCalm(graph, width, height, seed = 'archeus', inset = INSET) {
  const u = unit(width, height), core = coreCentre(width, height, inset), keep = coreKeepOut(width, height, u, inset, true);
  const projects = graph.nodes.filter(n => n.kind === 'Project').sort((a, b) => String(a.id).localeCompare(String(b.id))), P = projects.length;
  // Five-panel slots must fit above the full reserved bottom band.
  const left = Math.min(inset.left, width / 10), right = Math.min(inset.right, width / 10), top = Math.min(inset.top, height / 3), bottom = P === 5 ? inset.bottom : Math.min(inset.bottom, height / 5);
  const halfX = Math.min(core.x - left, width - right - core.x), halfY = Math.min(core.y - top, height - bottom - core.y), area = {left, right, top, bottom, width, height};
  const slots = [[-.62, -.5], [.5, -.55], [.74, .45], [-.74, .45]];
  const at = P <= 4 ? slots.slice(0, P) : P === 5 ? [[-.62, -.5], [.5, -.55], [.74, .18], [.5, .6], [-.7, .5]] : Array.from({length: P}, (_, i) => { const t = Math.PI / 2 + .6 + i * (2 * Math.PI - 1.2) / (P - 1); return [Math.cos(t) * .72, Math.sin(t) * .72]; });
  const spots = at.map(([fx, fy]) => ({x: core.x + fx * halfX, y: core.y + fy * halfY}));
  let R = Math.min(120 * u, halfX * .3, halfY * .5);
  if (P === 5 && width < 600) R = Math.min(R, 24); // Leave room beside the wordmark after keepClear.
  for (const [i, s] of spots.entries()) {
    R = Math.min(R, Math.hypot(s.x - core.x, s.y - core.y) - keep.radius - 4, Math.min(s.x - left, width - right - s.x, s.y - top, height - bottom - s.y));
    for (const t of spots.slice(i + 1)) R = Math.min(R, Math.hypot(s.x - t.x, s.y - t.y) / 2 - 5);
  }
  let out = [];
  for (let pass = 0; pass < 4; pass++) {
    R = Math.max(20, R);
    out = projects.map((n, i) => { const o = {...n, radius: R, rank: 8, ...spots[i]}; keepClear(o, keep, area); return o; });
    const gap = Math.min(Infinity, ...out.flatMap((a, i) => out.slice(i + 1).map(b => Math.hypot(a.x - b.x, a.y - b.y) / 2 - 2)));
    if (gap >= R) break;
    R = gap;
  }
  return out;
}
// Work graph (concepts 04 and 08): the missions and the decisions they ask for, grouped by what they wait on, round a small core.
// Groups run clockwise from the upper left: needs you, running, blocked, the rest, done. A node whose parent is in the graph (a decision) sits just outside its mission.
export const workGroup = n => { const s = stateKey(n.state); return s === 'needs-you' ? 0 : s === 'running' ? 1 : s === 'blocked' ? 2 : s === 'done' ? 4 : 3; };
export function workCore(width, height, inset = INSET) {
  const c = coreCentre(width, height, inset), R = clamp(Math.min(width * .08, (height - inset.top - inset.bottom) * .12), 12, 40);
  return {x: c.x, y: c.y, radius: R, keep: R * 1.7 + 4};
}
export function layoutWork(graph, width, height, seed = 'archeus', inset = INSET) {
  if (!graph.nodes.length) return [];
  const core = workCore(width, height, inset), {left, right, top, bottom} = inset, innerH = height - top - bottom, parentOf = new Map();
  for (const e of graph.edges || []) if (!parentOf.has(e.to)) parentOf.set(e.to, e.from);
  const order = (a, b) => workGroup(a) - workGroup(b) || String(a.id).localeCompare(String(b.id));
  const nodes = graph.nodes.map(n => ({...n, rank: 1})).sort(order), byId = new Map(nodes.map(n => [n.id, n]));
  const isKid = n => parentOf.has(n.id) && byId.has(parentOf.get(n.id)), prime = nodes.filter(n => !isKid(n)), kids = nodes.filter(isKid);
  const big = crystalIds(prime), rng = randomSeed(`${seed}:work`), P = prime.length, jitter = prime.map(() => rng() - .5);
  let scale = 1;
  for (let pass = 0; pass < 10; pass++, scale *= .88) {
    const crystal = clamp(innerH * .17, 22, 62) * scale, plain = clamp(innerH * .06, 10, 18) * scale;
    for (const n of nodes) n.radius = isKid(n) ? plain * .8 : big.has(n.id) ? crystal : plain;
    const halfX = (width - left - right) / 2, halfY = innerH / 2;
    prime.forEach((n, i) => {
      const a = -Math.PI * .75 + (i + .5) * TAU / P + jitter[i] * .12, k = i % 2 ? .66 : .86;
      n.x = core.x + Math.cos(a) * (halfX - n.radius) * k; n.y = core.y + Math.sin(a) * (halfY - n.radius) * k;
    });
    kids.forEach(n => {
      const p = byId.get(parentOf.get(n.id)), nth = kids.filter(k => parentOf.get(k.id) === p.id).indexOf(n), away = Math.atan2(p.y - core.y, p.x - core.x) + (nth - .5) * .9, d = p.radius + n.radius + 14;
      n.x = p.x + Math.cos(away) * d; n.y = p.y + Math.sin(away) * d;
    });
    for (let step = 0; step < 90; step++) {
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j], need = a.radius + b.radius + 12, dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || .01;
        if (d >= need) continue;
        const f = (need - d) / d * .5; a.x -= dx * f; a.y -= dy * f; b.x += dx * f; b.y += dy * f;
      }
      for (const n of nodes) {
        const dx = n.x - core.x, dy = n.y - core.y, d = Math.hypot(dx, dy) || .01, need = core.keep + n.radius;
        if (d < need) { n.x = core.x + dx / d * need; n.y = core.y + dy / d * need; }
        n.x = clamp(n.x, left + n.radius, width - right - n.radius); n.y = clamp(n.y, top + n.radius, height - bottom - n.radius);
      }
    }
    if (!nodes.some((a, i) => Math.hypot(a.x - core.x, a.y - core.y) < core.keep + a.radius - .5 || nodes.slice(i + 1).some(b => Math.hypot(a.x - b.x, a.y - b.y) < a.radius + b.radius - .5))) break;
  }
  return nodes;
}
export function convexHull(points) {
  const sorted = [...new Map(points.map(p => [`${p.x}:${p.y}`, {x: p.x, y: p.y}])).values()]
    .sort((a, b) => a.x - b.x || a.y - b.y);
  if (sorted.length < 3) return sorted;
  const cross = (a, b, c) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  const half = list => {
    const out = [];
    for (const p of list) {
      while (out.length > 1 && cross(out.at(-2), out.at(-1), p) <= 0) out.pop();
      out.push(p);
    }
    return out.slice(0, -1);
  };
  return [...half(sorted), ...half([...sorted].reverse())];
}
export const overlaps = (a, b, pad = 0) => a.x < b.x + b.width + pad && a.x + a.width + pad > b.x && a.y < b.y + b.height + pad && a.y + a.height + pad > b.y;
export function coversNode(box, node, pad = 3) {
  const r = node.radius + pad;
  if (node.x + r < box.x || node.x - r > box.x + box.width || node.y + r < box.y || node.y - r > box.y + box.height) return false;
  const x = clamp(node.x, box.x, box.x + box.width), y = clamp(node.y, box.y, box.y + box.height);
  return Math.hypot(x - node.x, y - node.y) < node.radius + pad;
}
export function placeLabels(nodes, width, height, {selected, measure = s => [...s].length * 7.5, obstacles = [], size = 12, rich = width >= 1280, metaOf, measureMeta, budget: limit, all = false, only, sub = false} = {}) {
  const result = [], occupied = [...obstacles], widths = new Map(), metas = new Map();
  const width_ = text => widths.get(text) ?? (widths.set(text, measure(text)), widths.get(text));
  const large = nodes.filter(n => n.radius > 24), small = nodes.filter(n => n.radius <= 24);
  const reach = Math.max(0, ...small.map(n => n.radius)) + 4, cell = 64, grid = new Map();
  for (const p of small) { const key = `${Math.floor(p.x / cell)},${Math.floor(p.y / cell)}`; if (!grid.has(key)) grid.set(key, []); grid.get(key).push(p); }
  const touchesNode = box => {
    if (large.some(p => coversNode(box, p))) return true;
    for (let gx = Math.floor((box.x - reach) / cell); gx <= Math.floor((box.x + box.width + reach) / cell); gx++)
      for (let gy = Math.floor((box.y - reach) / cell); gy <= Math.floor((box.y + box.height + reach) / cell); gy++)
        for (const p of grid.get(`${gx},${gy}`) || []) if (coversNode(box, p)) return true;
    return false;
  };
  const keys = new Map(nodes.map(n => [n, stateKey(n.state)]));
  const priority = n => n.id === selected ? 10000 : keys.get(n) === 'needs-you' ? 5000 : keys.get(n) === 'running' ? 1000 : Number(n.weight) || 1;
  const rank = new Map(nodes.map(n => [n, priority(n)]));
  const sorted = [...nodes].sort((a, b) => rank.get(b) - rank.get(a) || String(a.id).localeCompare(String(b.id)));
  const budget = limit ?? (width < 480 ? 4 : width < 1280 ? 7 : 9);
  const metaSize = size * .68, lineHeight = size * 1.3, height2 = rich ? lineHeight + metaSize * 1.5 + size * .95 : sub ? lineHeight + size * 1.1 : lineHeight;
  for (const n of sorted) {
    if (only && !only.has(n.id)) continue;
    const mandatory = all || n.id === selected || keys.get(n) === 'needs-you';
    if (!mandatory && result.length >= budget) continue;
    const full = String(n.label || n.id);
    const metaText = metaOf ? metaOf(n) : `${n.kind || 'Node'} · ${n.state || 'Idle'}`.toUpperCase();
    if (!metas.has(metaText)) metas.set(metaText, measureMeta ? measureMeta(metaText) : measure(metaText) * .75 + metaText.length * metaSize * .16);
    const metaWidth = metas.get(metaText);
    const variants = [full];
    if (mandatory) for (const cut of [18, 11]) if ([...full].length > cut) variants.push(`${[...full].slice(0, cut - 1).join('').trimEnd()}…`);
    const gap = n.radius + 8;
    const distances = mandatory ? [gap, gap + 10, gap + 24, gap + 44, gap + 70, gap + 100, gap + 140] : [gap, gap + 10, gap + 24];
    for (const text of variants) {
      const labelWidth = Math.min(width - 16, Math.max(width_(text), rich ? metaWidth : 0) + 4);
      const labelHeight = height2;
      const candidates = [];
      for (const d of distances) {
        candidates.push([n.x + d, n.y - labelHeight / 2], [n.x - d - labelWidth, n.y - labelHeight / 2],
          [n.x - labelWidth / 2, n.y - d - labelHeight], [n.x - labelWidth / 2, n.y + d]);
        if (mandatory) { const k = d * .75; candidates.push([n.x + k, n.y + k], [n.x - k - labelWidth, n.y + k], [n.x + k, n.y - k - labelHeight], [n.x - k - labelWidth, n.y - k - labelHeight]); }
      }
      const found = candidates.find(([x, y]) => {
        const box = {x, y, width: labelWidth, height: labelHeight};
        return !(x < 8 || y < 8 || x + box.width > width - 8 || y + box.height > height - 8)
          && !occupied.some(b => overlaps(box, b, 4)) && !touchesNode(box);
      });
      if (found) {
        const box = {id: n.id, x: found[0], y: found[1], width: labelWidth, height: labelHeight, text, rich, sub, mandatory, size};
        result.push(box); occupied.push(box); break;
      }
    }
  }
  return result;
}
export function nearestNeighbour(nodes, id, direction) {
  const from = nodes.find(n => n.id === id);
  if (!from) return null;
  const [ux, uy] = ({ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]})[direction] || [0, 0];
  let best = null, score = Infinity;
  for (const n of nodes) {
    const dx = n.x - from.x, dy = n.y - from.y, forward = dx * ux + dy * uy;
    if (n.id === id || forward <= 0) continue;
    const value = Math.hypot(dx, dy) * (1 + Math.abs(dx * uy - dy * ux) / forward);
    if (value < score) { score = value; best = n.id; }
  }
  return best;
}

export const projectsLegendBox = (width, height) => ({x: 16, y: height - 126, width: Math.min(290, width - 32), height: 110});
const projectsInset = inset => ({...inset, bottom: Math.max(inset.bottom, 142)});
export const projectsCore = (width, height, inset = INSET) => width < 600
  ? {x: width / 2, y: inset.top + 36} : coreCentre(width, height, projectsInset(inset));
export function projectsKeepOut(width, height, inset = INSET) {
  const core = projectsCore(width, height, inset);
  return width < 600 ? {...core, radius: 32, box: {x: core.x - 100, y: core.y + 20, width: 200, height: 48}}
    : coreKeepOut(width, height, Math.min(unit(width, height), (height - 142) / 400), projectsInset(inset));
}
export function layoutProjects(graph, width, height, seed = 'archeus', inset = INSET) {
  const byId = (a, b) => String(a.id).localeCompare(String(b.id));
  const projects = graph.nodes.filter(n => n.kind === 'Project').sort(byId), ideas = graph.nodes.filter(n => n.kind === 'Idea').sort(byId);
  const known = new Set(projects.map(p => p.id));
  const items = projects.flatMap(p => [p, ...ideas.filter(n => n.project === p.id)]).concat(ideas.filter(n => !known.has(n.project)));
  const phone = width < 600, keep = projectsKeepOut(width, height, inset), rows = phone ? items.length : Math.ceil(items.length / 2);
  const plateWidth = phone ? width - inset.left - inset.right - 16 : Math.min(260, (width - inset.left - inset.right - keep.box.width - 56) / 2);
  const available = height - inset.top - projectsInset(inset).bottom - (phone ? 120 : 0);
  const plateHeight = Math.min(64, Math.max(44, available / Math.max(1, rows) - 12)), pitch = Math.max(available / Math.max(1, rows), plateHeight + 12);
  return items.map((n, i) => ({...n, width: plateWidth, height: plateHeight, radius: 22,
    x: phone ? width / 2 + 8 : i % 2 ? width - inset.right - plateWidth / 2 : inset.left + plateWidth / 2,
    y: inset.top + (phone ? 120 : 0) + (Math.floor(i / (phone ? 1 : 2)) + .5) * pitch}));
}
