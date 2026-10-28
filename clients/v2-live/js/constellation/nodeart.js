import {randomSeed, convexHull, stateKey} from './geometry.js';

// Node art as SVG path strings: open wireframe polyhedra (silhouette plus a triangulated hairline mesh), the execution triangle and the core star. Hairlines only, no fills but the ground.
const pt = ([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`;
const seg = (a, b) => `M${pt(a)}L${pt(b)}`;
// 24-unit line icons, drawn at 28 px inside the opaque centre disk.
export const ICONS = {
  folder: 'M3 6h7l2 3h9v12H3ZM3 6V4h7l2 2',
  'doc-search': 'M13 21H4V3h11l5 5v4M14 3v6h6M7 8h3M7 12h4M7 16h3M19 19l3 3M20 16a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  doc: 'M5 2h10l5 5v15H5ZM14 2v6h6M8 12h9M8 16h9M8 19h6',
  notes: 'M4 2h16v20H4ZM7 7h10M7 11h10M7 15h10M7 19h6',
  code: 'M8 7 3 12l5 5M16 7l5 5-5 5M14 5l-4 14',
  branch: 'M6 3v12M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM18 9a9 9 0 0 1-9 9',
  bulb: 'M9 20h6M10 23h4M8 16c0-3-3-3-3-7a7 7 0 0 1 14 0c0 4-3 4-3 7v1H8Z',
  check: 'M4 12l5 5 11-12',
  shield: 'M12 2l9 5v9l-9 6-9-6V7ZM7 12l4 4 6-7',
  terminal: 'M3 4h18v16H3ZM7 9l3 3-3 3M13 15h4',
  chart: 'M5 20V10M10 20V4M15 20v-8M20 20V8'
};
const GOLDEN = 2.399963229728653;
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
// Seeded points on an ellipsoid are all hull vertices, so the convex hull is a triangulated polyhedron with 3V-6 edges.
// ponytail: O(V^4) face search; V is at most about 32 and the result is cached per node id.
const hulls = new Map();
export function hull3(id, count) {
  const key = `${id}:${count}`;
  if (hulls.has(key)) return hulls.get(key);
  const rng = randomSeed(`crystal:${id}`), axis = [.8 + rng() * .2, .8 + rng() * .2, .8 + rng() * .2];
  const pts = Array.from({length: count}, (_, i) => {
    const y = 1 - 2 * (i + .5) / count, rr = Math.sqrt(1 - y * y), t = i * GOLDEN + (rng() - .5) * .8;
    return [rr * Math.cos(t) * axis[0], y * axis[1], rr * Math.sin(t) * axis[2]];
  });
  const edges = new Set();
  for (let i = 0; i < count; i++) for (let j = i + 1; j < count; j++) for (let k = j + 1; k < count; k++) {
    const nrm = cross(sub(pts[j], pts[i]), sub(pts[k], pts[i]));
    let lo = false, hi = false;
    for (let m = 0; m < count && !(lo && hi); m++) { if (m === i || m === j || m === k) continue; const d = dot(nrm, sub(pts[m], pts[i])); if (d > 1e-9) hi = true; else if (d < -1e-9) lo = true; }
    if (lo && hi) continue;
    edges.add(`${i}-${j}`); edges.add(`${j}-${k}`); edges.add(`${i}-${k}`);
  }
  const out = {pts, edges: [...edges].map(e => e.split('-').map(Number))};
  hulls.set(key, out);
  return out;
}
// A wireframe crystal: seeded hull, one fixed rotation per node, perspective projection fitted into radius r.
// Edges and vertices come back in depth bands (front brightest, back dimmest) as path strings; the outline is the silhouette.
export function crystal(id, r) {
  const rng = randomSeed(`spin:${id}`), [ax, ay, az] = [rng() * Math.PI * 2, rng() * Math.PI * 2, rng() * Math.PI * 2];
  const [cx, sx, cy, sy, cz, sz] = [Math.cos(ax), Math.sin(ax), Math.cos(ay), Math.sin(ay), Math.cos(az), Math.sin(az)];
  const pick = randomSeed(`crystal:${id}`)(), {pts, edges} = hull3(id, r > 40 ? 24 + Math.floor(pick * 8) : 10 + Math.floor(pick * 3));
  const cam = 3.4, turned = pts.map(([x, y, z]) => {
    [y, z] = [y * cx - z * sx, y * sx + z * cx]; [x, z] = [x * cy + z * sy, -x * sy + z * cy]; [x, y] = [x * cz - y * sz, x * sz + y * cz];
    const k = cam / (cam - z);
    return {x: x * k, y: y * k, z};
  });
  const fit = r / Math.max(...turned.map(p => Math.hypot(p.x, p.y))), v = turned.map(p => ({x: p.x * fit, y: p.y * fit, z: p.z}));
  const bands = ['', '', ''], band = z => (z > .3 ? 2 : z > -.3 ? 1 : 0), dots = ['', ''];
  for (const [a, b] of edges) bands[band((v[a].z + v[b].z) / 2)] += seg([v[a].x, v[a].y], [v[b].x, v[b].y]);
  for (const p of v) dots[p.z >= 0 ? 1 : 0] += `M${pt([p.x, p.y])}h0`;
  return {back: bands[0], mid: bands[1], front: bands[2], dotsBack: dots[0], dotsFront: dots[1], outline: `M${convexHull(v).map(p => pt([p.x, p.y])).join('L')}Z`, edgeCount: edges.length, vertexCount: pts.length};
}
export function triangle(id, r) {
  const rng = randomSeed(`tri:${id}`), v = [[0, -r * 1.1], [r * 1.05, r * .75], [-r * 1.05, r * .75]], c = [(rng() - .5) * r * .1, r * .1];
  const mid = v.map((p, i) => { const q = v[(i + 1) % 3]; return [(p[0] + q[0]) / 2 + (rng() - .5) * r * .08, (p[1] + q[1]) / 2 + (rng() - .5) * r * .08]; });
  return {outline: `M${v.map(pt).join('L')}Z`, mesh: v.map((p, i) => seg(p, c) + seg(mid[i], mid[(i + 1) % 3]) + seg(p, mid[(i + 1) % 3])).join(''), dots: v.map(p => `M${pt(p)}h0`).join('')};
}
const esc = t => String(t).replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`), fx = v => +v.toFixed(2);
const STATES = ['needs-you', 'running', 'done', 'blocked', 'idle', 'paused', 'thinking'];
// One node as SVG markup: the wireframe (crystal, or the triangle for an execution), a plate and a line icon, and the state mark (amber diamond, red cross).
// The map and the mission graph both draw their nodes with this, so state is only ever line colour.
export function bodyMarkup(n, ic) {
  const state = stateKey(n.state), cls = STATES.includes(state) ? state : 'idle', r = n.radius, big = r > 40;
  if (n.phone) return `<g class="am-star am-state-${cls}" data-node-id="${esc(n.id)}"><circle r="${r}" class="am-attention-ring"/><circle r="${state === 'needs-you' ? 7 : 3}" class="am-body"/></g>`;
  const tiny = r < 12, plate = big ? 17 : Math.max(8, r * .42), scale = big ? 28 / 24 : plate * 1.5 / 24, k = Math.min(1, r / 16), a = fx(7 * k), b = fx(8 * k);
  const mark = state === 'needs-you' ? `<path d="M${fx(-r * .9)},${fx(-r * .78)}l${a},-${b}l${a},${b}l-${a},${b}Z" class="am-diamond"/>` : state === 'blocked' ? `<path d="M${fx(r * .72)},${fx(-r * .8)}l${a},${a}m0,-${a}l-${a},${a}" class="am-glyph"/>` : '';
  const wire = n.kind === 'Execution' ? (t => `<path d="${t.outline}" class="am-fill"/><path d="${t.mesh}" class="am-e1"/><path d="${t.outline}" class="am-e2"/><path d="${t.dots}" class="am-d1"/>`)(triangle(n.id, r))
    : (c => `<path d="${c.outline}" class="am-fill"/><path d="${c.back}" class="am-e0"/><path d="${c.mid}" class="am-e1"/><path d="${c.front}" class="am-e2"/><path d="${c.dotsBack}" class="am-d0"/><path d="${c.dotsFront}" class="am-d1"/>`)(crystal(n.id, r));
  return `<g class="am-star am-state-${cls}" data-node-id="${esc(n.id)}">${wire}${tiny ? '' : `<circle r="${fx(plate)}" class="am-mark-plate"/><g transform="translate(${fx(-12 * scale)} ${fx(-12 * scale + (n.kind === 'Execution' ? r * .2 : 0))}) scale(${fx(scale)})"><path d="${ICONS[ic]}" class="am-icon"/></g>`}${mark}</g>`;
}
// A project mark: one thin ring, no letters, no chip. In the Overview rings (n.lane) the ring wears its state colour (the lane's) and carries the diamond (needs you) or the cross (blocked);
// in the Network view it stays neutral (identity is the place) and only the diamond marks what needs you. A worktree is never a project: up to two tiny hollow squares trail the ring.
// Everything is drawn at the design radius n.radius, so the markup is the same picture at any size; a detailed mark is scaled by the caller.
export function ringMarkMarkup(n) {
  const r = n.radius, state = stateKey(n.state), flag = state === 'needs-you' ? 'diamond' : state === 'blocked' ? 'cross' : '', lane = Boolean(n.lane), k = Math.min(1, Math.max(.45, r / 16)), a = fx(6 * k), b = fx(7 * k);
  const mark = flag === 'diamond' ? `<path class="am-diamond" d="M${fx(r * .72)},${fx(-r * .95)}l${a},-${b}l${a},${b}l-${a},${b}Z"/>` : flag === 'cross' && lane ? `<path class="am-glyph" d="M${fx(r * .72)},${fx(-r * .95)}l${a},${a}m0,-${a}l-${a},${a}"/>` : '';
  const wt = Math.min(2, n.worktrees || 0), q = Math.max(2.5, r * .17), sq = Array.from({length: wt}, (_, i) => `M${fx(-r - q * 2.4 - i * q * 3)},${fx(-q)}h${fx(q * 2)}v${fx(q * 2)}h${fx(-q * 2)}Z`).join('');
  return `<g class="am-star am-hub am-state-${lane ? (['needs-you', 'blocked', 'running', 'paused', 'done'].includes(state) ? state : 'idle') : 'core'}" data-node-id="${esc(n.id)}"><circle r="${r}" class="am-hub-disc"/>${mark}${sq ? `<path class="am-vertex" d="${sq}"${n.tangent ? ` transform="rotate(${fx(n.tangent * 180 / Math.PI)})"` : ''}/>` : ''}</g>`;
}
// A worktree sub-hub: one ring round a branch glyph, smaller than a project hub. Its owner (linked or task) and state are words beside it, never colour alone; a missing one carries the cross.
export function worktreeMarkup(n) {
  const r = n.radius, state = stateKey(n.state), cls = STATES.includes(state) ? state : 'idle', k = r * 1.15 / 24, a = fx(r * .35);
  const cross = state === 'blocked' ? `<path d="M${fx(r * .62)},${fx(-r * .85)}l${a},${a}m0,-${a}l-${a},${a}" class="am-glyph"/>` : '';
  return `<g class="am-star am-worktree am-state-${cls}" data-node-id="${esc(n.id)}"><circle r="${r}" class="am-hub-disc"/><g transform="translate(${fx(-12 * k)} ${fx(-12 * k)}) scale(${fx(k)})"><path d="${ICONS.branch}" class="am-icon"/></g>${cross}</g>`;
}
// The core mark (owner choice 2026-10-28, concept R2-A5 M3, the thread driven merge): four cross arms with end dots, four diagonal spokes, an eight point star of fine string art
// between them, one partial outer arc and a centre ring. State is drawn by threads and arcs only: a heavier sector with a blue arc and dot (working), one amber thread ending in a
// diamond (needs you), a dashed arc, slack threads and a red cross (stopped). L = R * reach is the star radius; angles run clockwise from 12 o'clock; nothing but the
// amber diamond goes beyond 1.12 L, so the keep zone, the wordmark and every layout are unchanged. Strokes are non-scaling (see map.css); no halo, gradient or filter.
const rad = deg => deg * Math.PI / 180, polar = (r, deg) => [r * Math.sin(rad(deg)), -r * Math.cos(rad(deg))];
export function arcPath(r, from, to) {
  const sweep = ((to - from) % 360 + 360) % 360, [a, b] = [polar(r, from), polar(r, to)];
  return `M${pt(a)}A${fx(r)},${fx(r)} 0 ${sweep > 180 ? 1 : 0} 1 ${pt(b)}`;
}
// What the core says, most urgent first: stopped, then needs you, then working, then calm. Working and needs you draw together (different marks); stopped replaces them.
export const coreState = ({stopped, needsYou, running} = {}) => (stopped ? 'stopped' : needsYou ? 'needs-you' : running ? 'working' : 'calm');
// Size tiers by the star radius in screen pixels, with a 4 px hysteresis so a pinch never flickers: full (a mark 160 px or more), standard (the 96 px mark), mini (48), micro (24).
export const CORE_TIERS = Object.freeze(['full', 'standard', 'mini', 'micro']);
const TIER_AT = Object.freeze([71, 36, 18]);
export function coreTier(Lpx, prev) {
  const raw = TIER_AT.findIndex(min => Lpx >= min), i = raw < 0 ? 3 : raw, was = CORE_TIERS.indexOf(prev);
  if (was < 0 || was === i) return CORE_TIERS[i];
  // Keep the old tier until the radius is 4 px past the boundary between the two.
  const edge = TIER_AT[Math.min(i, was)];
  return Math.abs(Lpx - edge) < 4 ? CORE_TIERS[was] : CORE_TIERS[i];
}
const ARMS = [[0, 1.12], [90, 1.10], [180, 1.12], [270, 1.14]], DIAG = [45, 135, 225, 315], TIPS = [.60, .50];
// String art between neighbouring radial lines of the star: point i/n out along one line joins point 1 - i/n out along the next (or the one after).
function web(L, n, skip) {
  const tip = j => (j % 2 ? TIPS[1] : TIPS[0]) * L;
  let d = '';
  for (let j = 0; j < 8; j++) for (let i = 1; i < n; i++) d += seg(polar(tip(j) * i / n, j * 45), polar(tip(j + skip) * (1 - i / n), (j + skip) * 45));
  return d;
}
const cache = new Map();
// The paths of the core, as [{c: class, d | r}] in drawing order. opts: tier, stopped, needsYou, running. At most 19 elements in any state (calm 9, working 14, working and needs you 16, stopped 10).
export function corePaths(R, reach = 1.75, {tier = 'full', stopped = false, needsYou = false, running = false} = {}) {
  const L = R * reach, key = `${fx(L)}|${tier}|${stopped}`;
  let base = cache.get(key);
  if (!base) {
    if (cache.size > 48) cache.clear();
    const slack = stopped ? .82 : 1, big = tier === 'full', mid = tier === 'standard', micro = tier === 'micro';
    const arm = ARMS.map(([a, r]) => `M0,0L${pt(polar(r * L * slack, a))}`).join(''), diag = DIAG.map(a => `M0,0L${pt(polar(.76 * L * (stopped ? .7 : 1), a))}`).join('');
    const out = [];
    if (!micro) {
      const dense = stopped ? '' : web(L, big ? 14 : mid ? 10 : 6, 1), loose = big || stopped ? web(L, 10, 2) : '';
      if (dense) out.push({c: 'am-core-chords', d: dense});
      if (loose) out.push({c: 'am-core-chords am-core-loose', d: loose});
    }
    out.push({c: 'am-core-thread', d: arm + diag});
    out.push({c: 'am-core-dot', d: ARMS.map(([a, r]) => `M${pt(polar(r * L * slack, a))}h0`).join('')});
    out.push({c: 'am-core-dot am-core-dot-s', d: DIAG.map(a => `M${pt(polar(.76 * L * (stopped ? .7 : 1), a))}h0`).join('')});
    out.push({c: `am-core-arc${stopped ? ' am-core-arc-stopped' : ''}`, d: arcPath(.94 * L, 150, 355)});
    if (tier === 'full' || tier === 'standard') out.push({t: 'circle', c: 'am-core-ring', r: fx(Math.max(3.5, .06 * L))});
    if (!stopped) out.push({t: 'circle', c: 'am-core-centre', r: fx(Math.max(2, .028 * L))});
    base = out; cache.set(key, base);
  }
  const out = [...base];
  if (stopped) { out.push({c: 'am-core-cross', d: `M${pt([-.1 * L, -.1 * L])}L${pt([.1 * L, .1 * L])}M${pt([.1 * L, -.1 * L])}L${pt([-.1 * L, .1 * L])}`}); return out; }
  if (running) {
    out.push({c: 'am-core-sector', d: `M0,0L${pt(polar(1.12 * L, 0))}M0,0L${pt(polar(.94 * L, 45))}M0,0L${pt(polar(1.10 * L, 90))}`}, {c: 'am-core-state-arc', d: arcPath(.94 * L, 0, 90)}, {c: 'am-core-state-dot', d: `M${pt(polar(.94 * L, 45))}h0`},
      {t: 'circle', c: 'am-ring am-state-running am-core-pulse', r: fx(.7 * L)}, {c: 'am-travel am-core-travel', d: 'M0,0h0', x1: fx(polar(.94 * L, 45)[0]), y1: fx(polar(.94 * L, 45)[1])});
  }
  if (needsYou) {
    const a = running ? 315 : 45, h = Math.max(4, .07 * L), [x, y] = polar(1.04 * L, a);
    out.push({c: 'am-core-needs', d: `M0,0L${pt(polar(1.0 * L, a))}`}, {c: 'am-diamond am-core-diamond', d: `M${pt([x, y - h])}L${pt([x + h * .75, y])}L${pt([x, y + h])}L${pt([x - h * .75, y])}Z`});
  }
  return out;
}
export const coreMarkup = (R, reach, opts) => corePaths(R, reach, opts).map(p => (p.t === 'circle' ? `<circle class="${p.c}" r="${p.r}"/>` : `<path class="${p.c}" d="${p.d}"${p.x1 !== undefined ? ` style="--x0:0px;--y0:0px;--x1:${p.x1}px;--y1:${p.y1}px"` : ''}/>`)).join('');

export function projectPlateMarkup(n, t = x => x) {
  const x = -n.width / 2, y = -n.height / 2;
  const count = Math.max(5, Math.floor((n.width - 58) / 9));
  const label = [...String(n.label || n.id)];
  const title = label.length > count ? label.slice(0, count - 1).join('') + '…' : label.join('');
  const meta = n.kind === 'Idea' ? t('Captured') : t(`${n.missionCount} ${n.missionCount === 1 ? 'mission' : 'missions'}`);
  return `<g class="am-project-plate"><title>${esc(n.label || n.id)}</title><rect x="${x}" y="${y}" width="${n.width}" height="${n.height}"/><g transform="translate(${x + 12} -12)"><path class="am-icon" d="${ICONS[n.kind === 'Idea' ? 'bulb' : 'folder']}"/></g><circle class="projects-status" cx="${n.width / 2 - 9}" cy="${y + 9}" r="3"/><text class="am-plate-title" x="${x + 48}" y="-1">${esc(title)}</text><text class="am-plate-meta" x="${x + 48}" y="17">${esc(meta)}</text></g>`;
}
