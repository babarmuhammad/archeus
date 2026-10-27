import {randomSeed, convexHull} from './geometry.js';

// Node art as SVG path strings: open wireframe polyhedra (silhouette plus a triangulated hairline mesh), the execution triangle and the core star. Hairlines only, no fills but the ground.
const pt = ([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`;
const seg = (a, b) => `M${pt(a)}L${pt(b)}`;
// 24-unit line icons, drawn at 28 px inside the opaque centre disk.
export const ICONS = {
  'doc-search': 'M13 21H4V3h11l5 5v4M14 3v6h6M7 8h3M7 12h4M7 16h3M19 19l3 3M20 16a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  doc: 'M5 2h10l5 5v15H5ZM14 2v6h6M8 12h9M8 16h9M8 19h6',
  notes: 'M4 2h16v20H4ZM7 7h10M7 11h10M7 15h10M7 19h6',
  code: 'M8 7 3 12l5 5M16 7l5 5-5 5M14 5l-4 14',
  bulb: 'M9 20h6M10 23h4M8 16c0-3-3-3-3-7a7 7 0 0 1 14 0c0 4-3 4-3 7v1H8Z',
  check: 'M4 12l5 5 11-12',
  shield: 'M12 2l9 5v9l-9 6-9-6V7ZM7 12l4 4 6-7'
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
// Crossing ivory threads: long axial spikes, diagonals and many thin chords between points on two rings.
export function coreStar(R, reach) {
  const L = R * reach, at = (k, rad) => { const a = k * Math.PI / 8 - Math.PI / 2; return [rad * Math.cos(a), rad * Math.sin(a)]; };
  const rng = randomSeed('core-star');
  let spikes = '', threads = '';
  for (let k = 0; k < 16; k++) { const axis = k % 4 === 0, diag = k % 2 === 0; spikes += seg([0, 0], at(k, axis ? L : diag ? L * .62 : L * .36)); }
  for (let i = 0; i < 26; i++) { const a = at(Math.floor(rng() * 16), R * (.35 + rng() * .65)), b = at(Math.floor(rng() * 16), R * (.35 + rng() * .65)); threads += seg(a, b); }
  const tips = [0, 4, 8, 12].map(k => `M${pt(at(k, L))}h0`).join('');
  return {spikes, threads, tips};
}
