const TAU = Math.PI * 2;
const GOLDEN = 2.399963229728653;
export const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
export const INSET = Object.freeze({top: 16, right: 16, bottom: 60, left: 16});
export const unit = (width, height) => clamp(Math.sqrt(width * height) / 900, .9, 1.6);
export const coreCentre = (width, height) => ({x: width / 2, y: (INSET.top + height - INSET.bottom) / 2});
export const coreRadius = u => 40 * u;
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
export function layout(graph, width, height, seed = 'archeus') {
  const u = unit(width, height), core = coreCentre(width, height);
  const keys = [...new Set(graph.nodes.map(n => n.project || 'unassigned'))].sort();
  if (!keys.length) return [];
  const weight = n => isCrystal(n) ? Math.max(CRYSTAL_WEIGHT, Number(n.weight) || 1) : Number(n.weight) || 1;
  const groups = keys.map(key => graph.nodes.filter(n => (n.project || 'unassigned') === key)
    .map(n => ({...n, radius: nodeRadius(weight(n), u)}))
    .sort((a, b) => (a.kind === 'Project' ? 0 : 1) - (b.kind === 'Project' ? 0 : 1) || weight(b) - weight(a) || String(a.id).localeCompare(String(b.id))));
  const left = Math.min(INSET.left, width / 10), right = Math.min(INSET.right, width / 10);
  const top = Math.min(INSET.top, height / 10), bottom = Math.min(INSET.bottom, height / 5);
  const halfX = Math.min(core.x - left, width - right - core.x), halfY = Math.min(core.y - top, height - bottom - core.y);
  const pad = 20 * u, keepOut = coreRadius(u) + 16 * u, P = keys.length;
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
  const spacing = best.spacing, {points: centres} = ring(spacing, best.angles);
  const nodes = [];
  groups.forEach((group, gi) => {
    const phase = randomSeed(`${seed}:${keys[gi]}`)() * TAU;
    group.forEach((node, i) => {
      const rng = randomSeed(`${seed}:${node.id}`);
      const a = phase + i * GOLDEN + (rng() - .5) * .5, d = spacing * Math.sqrt(i) * (.9 + rng() * .2);
      nodes.push({...node, x: core.x + centres[gi].x + Math.cos(a) * d, y: core.y + centres[gi].y + Math.sin(a) * d});
    });
  });
  for (let step = 0; step < 4; step++) {
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
      if (d < keepOut) { n.x = core.x + (dx || 1) / (d || 1) * keepOut; n.y = core.y + dy / (d || 1) * keepOut; }
      n.x = clamp(n.x, left + n.radius, width - right - n.radius);
      n.y = clamp(n.y, top + n.radius, height - bottom - n.radius);
    }
  }
  return nodes.sort((a, b) => String(a.id).localeCompare(String(b.id)));
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
export function hullVertices(points, padding = 22) {
  if (!points.length) return [];
  const hull = convexHull(points);
  if (hull.length < 3) return convexHull(points.flatMap(p => Array.from({length: 6}, (_, i) => ({x: p.x + Math.cos(i * TAU / 6 + .5236) * padding, y: p.y + Math.sin(i * TAU / 6 + .5236) * padding}))));
  const area = hull.reduce((sum, p, i) => sum + p.x * hull[(i + 1) % hull.length].y - hull[(i + 1) % hull.length].x * p.y, 0);
  const side = area > 0 ? 1 : -1;
  const normal = (a, b) => { const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1; return [side * dy / d, -side * dx / d]; };
  return hull.map((v, i) => {
    const [x1, y1] = normal(hull.at(i - 1), v), [x2, y2] = normal(v, hull[(i + 1) % hull.length]);
    const k = padding / (1 + x1 * x2 + y1 * y2), mx = (x1 + x2) * k, my = (y1 + y2) * k, m = Math.hypot(mx, my), cap = Math.min(1, padding * 2.2 / (m || 1));
    return {x: v.x + mx * cap, y: v.y + my * cap};
  });
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
  const x = clamp(node.x, box.x, box.x + box.width), y = clamp(node.y, box.y, box.y + box.height);
  return Math.hypot(x - node.x, y - node.y) < node.radius + pad;
}
export function placeLabels(nodes, width, height, {selected, measure = s => [...s].length * 7.5, obstacles = [], size = 12, rich = width >= 1280, metaOf, measureMeta} = {}) {
  const result = [], occupied = [...obstacles], widths = new Map(), metas = new Map();
  const width_ = text => widths.get(text) ?? (widths.set(text, measure(text)), widths.get(text));
  const reach = Math.max(0, ...nodes.map(n => n.radius)) + 4, cell = 64, grid = new Map();
  for (const p of nodes) { const key = `${Math.floor(p.x / cell)},${Math.floor(p.y / cell)}`; if (!grid.has(key)) grid.set(key, []); grid.get(key).push(p); }
  const near = box => {
    const out = [];
    for (let gx = Math.floor((box.x - reach) / cell); gx <= Math.floor((box.x + box.width + reach) / cell); gx++)
      for (let gy = Math.floor((box.y - reach) / cell); gy <= Math.floor((box.y + box.height + reach) / cell); gy++) out.push(...(grid.get(`${gx},${gy}`) || []));
    return out;
  };
  const priority = n => n.id === selected ? 10000 : stateKey(n.state) === 'needs-you' ? 5000 : stateKey(n.state) === 'running' ? 1000 : Number(n.weight) || 1;
  const sorted = [...nodes].sort((a, b) => priority(b) - priority(a) || String(a.id).localeCompare(String(b.id)));
  const budget = width < 480 ? 5 : width < 1280 ? 13 : 30;
  const metaSize = size * .68, lineHeight = size * 1.3, height2 = rich ? lineHeight + metaSize * 1.5 : lineHeight;
  for (const n of sorted) {
    const mandatory = n.id === selected || stateKey(n.state) === 'needs-you';
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
          && !occupied.some(b => overlaps(box, b, 4)) && !near(box).some(p => coversNode(box, p));
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
