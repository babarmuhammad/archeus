// The Archeus mark and lockup as DOM. Static: the one allowed loop (the core breath) lives on the map's core, not here.
import { h, s } from './dom.js';

const rad = (deg) => deg * Math.PI / 180;
const pt = (r, deg) => [48 + r * Math.sin(rad(deg)), 48 - r * Math.cos(rad(deg))].map((v) => +v.toFixed(1));

// Four long concave spikes, four short diagonals and eight hairline rays of uneven length: the concept's core star, outline only.
const MAIN = 'M48 2L51.5 44.5 94 48 51.5 51.5 48 94 44.5 51.5 2 48 44.5 44.5Z';
const DIAG = 'M48 48L68 28M48 48L68 68M48 48L28 68M48 48L28 28';
const RAYS = [[22.5, 34], [67.5, 26], [112.5, 38], [157.5, 24], [202.5, 33], [247.5, 27], [292.5, 36], [337.5, 25]]
  .map(([a, r]) => 'M' + pt(7, a).join(' ') + 'L' + pt(r, a).join(' ')).join('');

export function starParts() {
  return [s('path', { d: RAYS, opacity: '.45' }), s('path', { d: DIAG, opacity: '.65' }), s('path', { d: MAIN }),
    s('circle', { cx: 48, cy: 48, r: 5.5, opacity: '.55' }), s('circle', { cx: 48, cy: 48, r: 1.8, fill: 'currentColor', stroke: 'none' })];
}

export const star = (size = 28) => s('svg', { class: 'star', viewBox: '0 0 96 96', width: size, height: size, 'aria-hidden': 'true', focusable: 'false', fill: 'none', stroke: 'currentColor', 'stroke-width': 1, 'stroke-linejoin': 'round' }, ...starParts());

export const wordmark = () => h('span', { class: 'wordmark' }, 'ARCHEUS ', h('span', null, 'V2'));

export const lockup = () => h('span', { class: 'lockup' }, star(26), wordmark());
