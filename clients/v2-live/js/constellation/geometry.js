const TAU = Math.PI * 2;
const GOLDEN = 2.399963229728653;
export const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
export const INSET = Object.freeze({top: 16, right: 16, bottom: 60, left: 16});
export const unit = (width, height) => clamp(Math.sqrt(width * height) / 900, .9, 1.6);
export const coreCentre = (width, height, inset = INSET) => ({x: width / 2, y: (inset.top + height - inset.bottom) / 2});
export const CALM_CORE = 2.1;
export const coreRadius = (u, calm, width = 1000) => 52 * u * (calm ? (width < 600 ? 1.2 : CALM_CORE) : 1);
export const coreReach = (width, calm) => (calm ? 1.1 : width < 480 ? 1.25 : 1.75);
export const nodeRadius = (weight, u = 1) => (3 + Math.sqrt(clamp(Number(weight) || 1, .25, 100)) * 2) * u;
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
export function stateKey(state) {
  const key = String(state || 'idle').toLowerCase().replace(/[ _]/g, '-');
  return ({waiting: 'needs-you', attention: 'needs-you', active: 'running', completed: 'done'})[key] || key;
}
export const isCrystal = n => n.kind === 'Mission' && ['running', 'needs-you'].includes(stateKey(n.state));
export const CRYSTAL_WEIGHT = 100;
export const crystalRadius = (u, width) => (width < 480 ? 25 * u : Math.min(60 * u, 92));
// Open space: only the top few running or needs-you missions are drawn as big crystals, the rest shrink to minor nodes.
export const CRYSTAL_BUDGET = 3;
export const crystalIds = nodes => new Set(nodes.filter(isCrystal).sort((a, b) => (stateKey(b.state) === 'needs-you') - (stateKey(a.state) === 'needs-you') || String(a.id).localeCompare(String(b.id))).slice(0, CRYSTAL_BUDGET).map(n => n.id));
export const bodyRadius = (n, u, width) => (n.kind === 'Project' ? (width < 480 ? 15 : 30) : n.kind === 'Execution' ? (width < 480 ? 17 : 38) : (width < 480 ? 11 : 15)) * u;
export const wordmarkSize = (u, calm) => Math.round((12.5 * u + 2) * (calm ? 1.35 : 1));
// What the layout keeps clear of: the core star (a circle) and the wordmark with its tagline under it (a box).
export function coreKeepOut(width, height, u, inset = INSET, calm = false) {
  const c = coreCentre(width, height, inset), R = coreRadius(u, calm, width), ws = wordmarkSize(u, calm), reach = coreReach(width, calm);
  return {x: c.x, y: c.y, radius: R * reach + 8 * u,
    box: {x: c.x - 6.5 * ws, y: c.y + R * .6, width: 13 * ws, height: R * reach + (width < 480 ? 2.8 : 4.6) * ws - R * .6}};
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
// Open composition: each project is a hub on a ring round the core, its children spiral out from it by rank, executions and decisions
// spiral round their mission, and a short relaxation pushes every pair apart. Nothing is drawn for a project but its own node.
export function layout(graph, width, height, seed = 'archeus', inset = INSET) {
  if (!graph.nodes.length) return [];
  const u = unit(width, height), core = coreCentre(width, height, inset), keep = coreKeepOut(width, height, u, inset);
  const big = crystalIds(graph.nodes), weight = n => big.has(n.id) ? Math.max(CRYSTAL_WEIGHT, Number(n.weight) || 1) : Number(n.weight) || 1;
  const nodes = graph.nodes.map(n => { const w = weight(n); return {...n, radius: big.has(n.id) ? crystalRadius(u, width) : ['Mission', 'Project', 'Execution'].includes(n.kind) ? bodyRadius(n, u, width) : nodeRadius(w, u), rank: w}; })
    .sort((a, b) => String(a.id).localeCompare(String(b.id)));
  const byId = new Map(nodes.map(n => [n.id, n])), keys = [...new Set(nodes.map(n => n.project || 'unassigned'))].sort(), P = keys.length;
  const left = Math.min(inset.left, width / 10), right = Math.min(inset.right, width / 10), top = Math.min(inset.top, height * .42), bottom = Math.min(inset.bottom, height * .26);
  const halfX = Math.min(core.x - left, width - right - core.x), halfY = Math.min(core.y - top, height - bottom - core.y);
  const parentOf = new Map();
  for (const e of graph.edges || []) if (byId.has(e.from) && byId.has(e.to) && byId.get(e.from).kind !== 'Project' && !parentOf.has(e.to)) parentOf.set(e.to, e.from);
  const order = (a, b) => (a.kind === 'Project' ? 0 : 1) - (b.kind === 'Project' ? 0 : 1) || b.rank - a.rank || String(a.id).localeCompare(String(b.id));
  const spiral = (list, cx, cy, r0, step, phase, rng) => list.forEach((n, i) => {
    const a = phase + i * GOLDEN + (rng() - .5) * .3, d = r0 + n.radius + step * Math.sqrt(i + .6) * (.9 + rng() * .2);
    n.x = cx + Math.cos(a) * d; n.y = cy + Math.sin(a) * d;
  });
  const kids = new Map();
  for (const n of nodes) if (parentOf.has(n.id)) { if (!kids.has(parentOf.get(n.id))) kids.set(parentOf.get(n.id), []); kids.get(parentOf.get(n.id)).push(n); }
  keys.forEach((key, pi) => {
    const rng = randomSeed(`${seed}:${key}`), theta = -Math.PI / 2 + Math.PI / P + pi * TAU / P + (P === 1 ? Math.PI / 2 : 0);
    let hx = core.x + Math.cos(theta) * halfX * .5; const hy = core.y + Math.sin(theta) * halfY * .45, hub = nodes.find(n => n.kind === 'Project' && (n.project || 'unassigned') === key);
    const group = nodes.filter(n => (n.project || 'unassigned') === key && n !== hub && !parentOf.has(n.id)).sort(order);
    if (hy > keep.box.y - 80 * u && Math.abs(hx - core.x) < keep.box.width / 2 + 90 * u) hx = core.x + (hx < core.x ? -1 : 1) * (keep.box.width / 2 + 90 * u);
    if (hub) { hub.x = hx; hub.y = hy; }
    spiral(group, hx, hy, hub ? hub.radius : 0, 92 * u, theta, rng);
  });
  for (const [pid, list] of kids) { const p = byId.get(pid), rng = randomSeed(`${seed}:${pid}`), away = Math.atan2(p.y - core.y, p.x - core.x); spiral(list.sort(order), p.x, p.y, p.radius, 30 * u, away, rng); }
  const area = {left, right, top, bottom, width, height}, anchor = nodes.map(n => ({x: n.x, y: n.y})), gap = 18 * u;
  for (let step = 0; step < (nodes.length > 60 ? 10 : 70); step++) {
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j], need = a.radius + b.radius + gap, dx = b.x - a.x, dy = b.y - a.y;
      if (Math.abs(dx) >= need || Math.abs(dy) >= need) continue;
      const d = Math.hypot(dx, dy) || .01;
      if (d >= need) continue;
      const f = (need - d) / d * .5, ux = dx || .01;
      a.x -= ux * f; a.y -= dy * f; b.x += ux * f; b.y += dy * f;
    }
    nodes.forEach((n, i) => {
      n.x += (anchor[i].x - n.x) * .02; n.y += (anchor[i].y - n.y) * .02;
      keepClear(n, keep, area);
    });
  }
  return nodes;
}
// A faint ambient field behind the scene: hollow dots on a jittered grid joined by hairlines. Pure: the same size and seed give the same field.
export function ambientField(width, height, seed = 'archeus', cell = 170) {
  const rng = randomSeed(`${seed}:ambient`), cols = Math.max(2, Math.round(width / cell)), rows = Math.max(2, Math.round(height / cell)), dots = [];
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) dots.push([(c + .2 + rng() * .6) * width / cols, (r + .2 + rng() * .6) * height / rows]);
  let d = '';
  const at = (c, r) => dots[r * cols + c];
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const p = at(c, r), links = [[c + 1, r], [c, r + 1], rng() < .45 ? [c + 1, r + 1] : null, rng() < .3 ? [c - 1, r + 1] : null];
    for (const l of links) if (l && l[0] >= 0 && l[0] < cols && l[1] < rows) { const q = at(l[0], l[1]); d += `M${p[0].toFixed(1)},${p[1].toFixed(1)}L${q[0].toFixed(1)},${q[1].toFixed(1)}`; }
  }
  return {d, dots};
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
export function placeLabels(nodes, width, height, {selected, measure = s => [...s].length * 7.5, obstacles = [], size = 12, rich = width >= 1280, metaOf, measureMeta} = {}) {
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
  const budget = width < 480 ? 4 : width < 1280 ? 7 : 9;
  const metaSize = size * .68, lineHeight = size * 1.3, height2 = rich ? lineHeight + metaSize * 1.5 + size * .95 : lineHeight;
  for (const n of sorted) {
    const mandatory = n.id === selected || keys.get(n) === 'needs-you';
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
        const box = {id: n.id, x: found[0], y: found[1], width: labelWidth, height: labelHeight, text, rich, mandatory, size};
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
