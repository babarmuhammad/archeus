const TAU = Math.PI * 2;
const GOLDEN = 2.399963229728653;
export const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
export const INSET = Object.freeze({top: 16, right: 16, bottom: 60, left: 16});
export const unit = (width, height) => clamp(Math.sqrt(width * height) / 900, .9, 1.6);
export const coreCentre = (width, height, inset = INSET) => ({x: width / 2, y: (inset.top + height - inset.bottom) / 2});
export const coreRadius = u => 40 * u;
export const coreReach = width => (width < 480 ? 1.25 : 1.75);
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
export const crystalRadius = (u, width) => (width < 480 ? 25 : 62) * u;
export const bodyRadius = (n, u, width) => (n.kind === 'Project' ? (width < 480 ? 17 : 34) : n.kind === 'Execution' ? (width < 480 ? 17 : 38) : (width < 480 ? 13 : 26)) * u;
export const hullPadding = (members, u) => Math.max(17 * u + 7, Math.max(...members.map(n => n.radius)) + 10);
export const wordmarkSize = u => Math.round(11 * u + 1);
// Convex polygons: the vector that moves `a` clear of `b` along the axis of least penetration (plus `margin`), or null when they are already apart.
export function overlapDepth(a, b, margin = 0) {
  let best = Infinity, push = null;
  for (const poly of [a, b]) for (let i = 0; i < poly.length; i++) {
    const p = poly[i], q = poly[(i + 1) % poly.length], len = Math.hypot(q.x - p.x, q.y - p.y) || 1, nx = (q.y - p.y) / len, ny = -(q.x - p.x) / len;
    let a0 = Infinity, a1 = -Infinity, b0 = Infinity, b1 = -Infinity;
    for (const v of a) { const d = v.x * nx + v.y * ny; if (d < a0) a0 = d; if (d > a1) a1 = d; }
    for (const v of b) { const d = v.x * nx + v.y * ny; if (d < b0) b0 = d; if (d > b1) b1 = d; }
    const toward = a1 - b0 + margin, away = b1 - a0 + margin;
    if (toward <= 0 || away <= 0) return null;
    const depth = Math.min(toward, away);
    if (depth < best) { best = depth; const sign = toward < away ? -1 : 1; push = {x: nx * depth * sign, y: ny * depth * sign}; }
  }
  return push;
}
export const rectPolygon = (x0, y0, x1, y1) => [{x: x0, y: y0}, {x: x1, y: y0}, {x: x1, y: y1}, {x: x0, y: y1}];
// What a hull must stay clear of: the core star and the wordmark and running count under it.
export function coreObstacles(width, height, u, inset = INSET) {
  const c = coreCentre(width, height, inset), R = coreRadius(u), ws = wordmarkSize(u), S = R * coreReach(width) + 4 * u;
  return [Array.from({length: 12}, (_, i) => ({x: c.x + S * Math.cos(i * TAU / 12 + .26), y: c.y + S * Math.sin(i * TAU / 12 + .26)})),
    rectPolygon(c.x - 6.5 * ws, c.y + R * .6, c.x + 6.5 * ws, c.y + R * coreReach(width) + (width < 480 ? 2.8 : 4.6) * ws)];
}
export function layout(graph, width, height, seed = 'archeus', inset = INSET) {
  const u = unit(width, height), core = coreCentre(width, height, inset);
  const keys = [...new Set(graph.nodes.map(n => n.project || 'unassigned'))].sort();
  if (!keys.length) return [];
  const weight = n => isCrystal(n) ? Math.max(CRYSTAL_WEIGHT, Number(n.weight) || 1) : Number(n.weight) || 1;
  const groups = keys.map(key => graph.nodes.filter(n => (n.project || 'unassigned') === key)
    .map(n => { const w = weight(n); return {...n, radius: isCrystal(n) ? crystalRadius(u, width) : ['Mission', 'Project', 'Execution'].includes(n.kind) ? bodyRadius(n, u, width) : nodeRadius(w, u), rank: w}; })
    .sort((a, b) => (a.kind === 'Project' ? 0 : 1) - (b.kind === 'Project' ? 0 : 1) || b.rank - a.rank || String(a.id).localeCompare(String(b.id))));
  const left = Math.min(inset.left, width / 10), right = Math.min(inset.right, width / 10);
  const top = Math.min(inset.top, height / 3), bottom = Math.min(inset.bottom, height / 5);
  const halfX = Math.min(core.x - left, width - right - core.x), halfY = Math.min(core.y - top, height - bottom - core.y);
  const pad = 20 * u, keepOut = coreRadius(u) * coreReach(width) + 8 * u, P = keys.length;
  const reach = (s, group) => s * Math.sqrt(Math.max(0, group.length - 1)) + pad + 8 * u;
  const widest = Math.max(...groups.map(g => g.length));
  const ring = (s, angles) => {
    const rc = reach(s, {length: widest}), a = halfX - rc, b = halfY - rc;
    return {rc, a, b, points: angles.map(t => ({x: a * Math.cos(t), y: b * Math.sin(t)}))};
  };
  const fits = (s, angles) => {
    const {rc, a, b, points} = ring(s, angles);
    if (a <= 0 || b <= 0 || points.some(p => Math.hypot(p.x, p.y - 12 * u) < keepOut + rc * .8)) return false;
    for (let i = 0; i < P; i++) for (let j = i + 1; j < P; j++)
      if (Math.hypot(points[i].x - points[j].x, points[i].y - points[j].y) < (reach(s, groups[i]) + reach(s, groups[j])) * .82) return false;
    return true;
  };
  const lowest = 14 * u, highest = 66 * u;
  let best = {spacing: lowest, angles: keys.map((_, i) => -Math.PI / 2 + i * TAU / P), score: -1};
  for (let k = 0; k < 12; k++) {
    const turn = -Math.PI / 2 + k * (P === 1 ? TAU : TAU / P) / 12, angles = keys.map((_, i) => turn + i * TAU / P);
    let lo = lowest, hi = highest, spacing = lowest;
    if (fits(hi, angles)) spacing = hi;
    else if (fits(lo, angles)) { for (let i = 0; i < 22; i++) { const mid = (lo + hi) / 2; if (fits(mid, angles)) lo = mid; else hi = mid; } spacing = lo; }
    else continue;
    if (spacing > best.score + 1e-6) best = {spacing, angles, score: spacing};
  }
  const place = spacing => {
    const {points: centres} = ring(spacing, best.angles), placed = groups.map(() => []);
    groups.forEach((group, gi) => {
      const phase = randomSeed(`${seed}:${keys[gi]}`)() * TAU;
      group.forEach((node, i) => {
        const rng = randomSeed(`${seed}:${node.id}`);
        const a = phase + i * GOLDEN + (rng() - .5) * .5, d = spacing * Math.sqrt(i) * (.9 + rng() * .2);
        placed[gi].push({...node, x: core.x + centres[gi].x + Math.cos(a) * d, y: core.y + centres[gi].y + Math.sin(a) * d});
      });
    });
    const nodes = placed.flat();
    for (let step = 0; step < (placed.flat().length > 60 ? 4 : 8); step++) {
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const gap = a.radius + b.radius + 10 * u, dx = b.x - a.x, dy = b.y - a.y;
        if (Math.abs(dx) >= gap || Math.abs(dy) >= gap) continue;
        const d = Math.hypot(dx, dy) || .01;
        if (d >= gap) continue;
        const f = (gap - d) / d * .5, ux = dx || .01;
        a.x -= ux * f; a.y -= dy * f; b.x += ux * f; b.y += dy * f;
      }
      for (const n of nodes) {
        const dx = n.x - core.x, dy = n.y - core.y, d = Math.hypot(dx, dy);
        const need = keepOut + n.radius * .5;
        if (d < need) { n.x = core.x + (dx || 1) / (d || 1) * need; n.y = core.y + dy / (d || 1) * need; }
        n.x = clamp(n.x, left + n.radius, width - right - n.radius);
        n.y = clamp(n.y, top + n.radius, height - bottom - n.radius);
      }
    }
    return placed;
  };
  // Hulls are the real polygons: push whole clusters apart (and off the core mark and its wordmark) until none touch, keeping them in view.
  const obstacles = coreObstacles(width, height, u, inset), gap = 6 * u;
  const shift = (g, dx, dy) => { for (const n of g) { n.x += dx; n.y += dy; } };
  const hullOf = g => hullVertices(g, hullPadding(g, u));
  const settle = (placed, rounds) => {
    for (let round = 0; round < rounds; round++) {
      let moved = false;
      const hull = placed.map(hullOf);
      for (let i = 0; i < P; i++) for (let j = i + 1; j < P; j++) {
        const push = overlapDepth(hull[i], hull[j], gap);
        if (!push) continue;
        shift(placed[i], push.x / 2, push.y / 2); shift(placed[j], -push.x / 2, -push.y / 2);
        hull[i] = hullOf(placed[i]); hull[j] = hullOf(placed[j]); moved ||= Math.hypot(push.x, push.y) > 1;
      }
      for (let i = 0; i < P; i++) {
        for (const o of obstacles) { const push = overlapDepth(hull[i], o, gap); if (push) { shift(placed[i], push.x, push.y); hull[i] = hullOf(placed[i]); moved ||= Math.hypot(push.x, push.y) > 1; } }
        const xs = hull[i].map(v => v.x), ys = hull[i].map(v => v.y), g = placed[i];
        const lo = {x: Math.min(...xs) - 4, y: Math.min(...ys) - 4}, hi = {x: Math.max(...xs) + 4, y: Math.max(...ys) + 6};
        const nlo = {x: Math.min(...g.map(n => n.x - n.radius)) - left, y: Math.min(...g.map(n => n.y - n.radius)) - top};
        const nhi = {x: Math.max(...g.map(n => n.x + n.radius)) - (width - right), y: Math.max(...g.map(n => n.y + n.radius)) - (height - bottom)};
        const dx = Math.max(-lo.x, -nlo.x, 0) + Math.min(width - hi.x, -nhi.x, 0), dy = Math.max(-lo.y, -nlo.y, 0) + Math.min(height - hi.y, -nhi.y, 0);
        if (Math.abs(dx) > .01 || Math.abs(dy) > .01) { shift(g, dx, dy); moved ||= Math.hypot(dx, dy) > 1; }
      }
      if (!moved) break;
    }
    const hull = placed.map(hullOf);
    return hull.every((h, i) => hull.slice(i + 1).every(o => !overlapDepth(h, o, 0)) && obstacles.every(o => !overlapDepth(h, o, 0)));
  };
  let spacing = best.spacing, placed;
  // ponytail: past 60 nodes no layout fits the box, so hulls are not separated; a real packing solver if big graphs matter.
  const crowded = groups.reduce((s, g) => s + g.length, 0) > 60;
  for (let attempt = 0; attempt < (crowded ? 1 : 4); attempt++) { placed = place(spacing); if (crowded || settle(placed, 14) || spacing < lowest * .5) break; spacing *= .86; }
  return placed.flat().sort((a, b) => String(a.id).localeCompare(String(b.id)));
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
// The hull of the members grown by `padding`: each corner of the member hull becomes an octagon, so thin or collinear clusters get faceted ends, never spikes.
export function hullVertices(points, padding = 22) {
  if (!points.length) return [];
  const r = padding / Math.cos(Math.PI / 8);
  return convexHull(convexHull(points).flatMap(p => Array.from({length: 8}, (_, i) => ({x: p.x + Math.cos((i + .5) * TAU / 8) * r, y: p.y + Math.sin((i + .5) * TAU / 8) * r}))));
}
export function polygonPath(vertices, round = 0) {
  if (!vertices.length) return '';
  if (!round) return `M${vertices.map(p => `${p.x},${p.y}`).join('L')}Z`;
  const n = vertices.length;
  const corner = (v, to) => { const d = Math.hypot(to.x - v.x, to.y - v.y) || 1, t = Math.min(round / d, .4); return `${v.x + (to.x - v.x) * t},${v.y + (to.y - v.y) * t}`; };
  return vertices.map((v, i) => `${i ? 'L' : 'M'}${corner(v, vertices.at(i - 1))}Q${v.x},${v.y} ${corner(v, vertices[(i + 1) % n])}`).join('') + 'Z';
}
export const hullPath = (points, round = 6, padding = 22) => polygonPath(hullVertices(points, padding), round);
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
  const budget = width < 480 ? 5 : width < 1280 ? 13 : 30;
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
    const distances = mandatory ? [gap, gap + 10, gap + 24, gap + 44, gap + 70] : [gap, gap + 10, gap + 24];
    for (const text of variants) {
      const labelWidth = Math.min(width - 16, Math.max(width_(text), rich ? metaWidth : 0) + 4);
      const labelHeight = height2;
      const candidates = [];
      for (const d of distances) {
        candidates.push([n.x + d, n.y - labelHeight / 2], [n.x - d - labelWidth, n.y - labelHeight / 2],
          [n.x - labelWidth / 2, n.y - d - labelHeight], [n.x - labelWidth / 2, n.y + d]);
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
