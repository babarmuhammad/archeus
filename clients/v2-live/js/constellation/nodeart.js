import {randomSeed} from './geometry.js';

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
export function polyhedron(id, r) {
  const rng = randomSeed(`poly:${id}`), n = r > 40 ? 5 + Math.floor(rng() * 3) : 6, full = r > 40;
  const ring = (k, rad, jit, turn) => Array.from({length: k}, (_, i) => { const a = -Math.PI / 2 + turn + i * Math.PI * 2 / k + (rng() - .5) * jit, d = rad * (1 - jit * .5 + rng() * jit); return [d * Math.cos(a), d * Math.sin(a)]; });
  const outer = ring(n, r, .22, 0), mid = ring(n, r * .6, .3, Math.PI / n), inner = full ? ring(Math.max(3, n - 2), r * .3, .4, .4) : [];
  let mesh = '';
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    mesh += seg(outer[i], mid[i]) + seg(outer[j], mid[i]) + seg(mid[i], mid[j]);
    if (full) mesh += seg(outer[i], outer[(i + 2) % n]) + seg(mid[i], inner[i % inner.length]) + seg(mid[j], inner[i % inner.length]);
  }
  if (full) inner.forEach((p, i) => { mesh += seg(p, inner[(i + 1) % inner.length]); });
  const dots = [...outer, ...(full ? mid : [])];
  return {outline: `M${outer.map(pt).join('L')}Z`, mesh, dots: dots.map(p => `M${pt(p)}h0`).join('')};
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
