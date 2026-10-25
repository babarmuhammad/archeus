import { s } from './dom.js';
import { starParts } from './brand.js';

const JITTER = [1, .94, 1.05, .97, 1.02, .92, 1.04];

// A faceted node: irregular polygon outline plus the chords that triangulate it, the concept's polyhedron nodes. Returns an svg <g>.
export function facet(cx, cy, r, n = 7, rot = 0) {
  const v = Array.from({ length: n }, (_, i) => {
    const a = (rot + (360 / n) * i) * Math.PI / 180, k = r * JITTER[i % JITTER.length];
    return [+(cx + k * Math.sin(a)).toFixed(1), +(cy - k * Math.cos(a)).toFixed(1)];
  });
  const mid = (a, b) => ((v[a][0] + v[b][0]) / 2).toFixed(1) + ' ' + ((v[a][1] + v[b][1]) / 2).toFixed(1);
  const chords = n === 3 ? 'M' + mid(0, 1) + 'L' + mid(1, 2) + 'L' + mid(2, 0) + 'Z'
    : v.flatMap((p, i) => [2, 3].map((d) => 'M' + p.join(' ') + 'L' + v[(i + d) % n].join(' '))).join('');
  const g = s('g', { fill: 'none', stroke: 'currentColor', 'stroke-width': 1, 'stroke-linejoin': 'round' });
  g.append(s('path', { d: chords, opacity: '.4' }), s('path', { d: 'M' + v.map((p) => p.join(' ')).join('L') + 'Z' }));
  for (const [x, y] of v) g.append(s('circle', { cx: x, cy: y, r: 1.6, fill: 'currentColor', stroke: 'none' }));
  return g;
}

const dots = (pairs) => pairs.map(([cx, cy]) => s('circle', { cx, cy, r: 1.6, fill: 'currentColor', stroke: 'none', opacity: '.5' }));
const web = (d) => s('path', { d, opacity: '.3' });

const drawings = {
  missions: () => [web('M12 30L80 60 148 24M12 96L80 60 150 92'), facet(80, 60, 34, 7, 8), s('circle', { cx: 80, cy: 60, r: 9 }), s('circle', { cx: 80, cy: 60, r: 2, fill: 'currentColor' }), ...dots([[12, 30], [148, 24], [12, 96], [150, 92]])],
  clear: () => [web('M10 70L46 60M114 60L152 36'), facet(80, 60, 34, 6, 0), s('path', { d: 'M65 61l10 10 20-22', stroke: 'var(--done)', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }), ...dots([[10, 70], [152, 36]])],
  offline: () => [web('M10 40L46 54M114 70L150 84'), s('g', { 'stroke-dasharray': '3 5', opacity: '.6' }, s('circle', { cx: 80, cy: 60, r: 46 })), facet(80, 60, 30, 6, 30), s('path', { d: 'M52 100L108 20', 'stroke-width': 2, stroke: 'var(--paused)', 'stroke-linecap': 'round' }), ...dots([[10, 40], [150, 84]])],
  error: () => [web('M10 96L50 84M110 84L152 100'), facet(80, 62, 38, 3, 0), s('path', { d: 'M80 48V68M80 79V80', stroke: 'var(--blocked)', 'stroke-width': 2.4, 'stroke-linecap': 'round' }), ...dots([[10, 96], [152, 100]])],
  first: () => [web('M10 20L80 60 150 30M20 100L80 60 142 96'), s('g', { transform: 'translate(36 16) scale(.92)' }, ...starParts()), ...dots([[10, 20], [150, 30], [20, 100], [142, 96]])]
};

export function illustration(name, label) {
  return s('svg', { class: 'ds-illustration', width: 160, height: 120, viewBox: '0 0 160 120', fill: 'none', stroke: 'currentColor', 'stroke-width': 1, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', role: label ? 'img' : null, 'aria-label': label || null, 'aria-hidden': label ? null : 'true', focusable: 'false' }, ...(drawings[name] || drawings.missions)());
}
