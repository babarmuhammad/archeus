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

export function coreMark(running = false, count = 1) {
  return h('div', { class: 'ds-core', 'data-live': String(running), 'data-core': 'idle' },
    s('svg', { class: 'core-breath', viewBox: '0 0 96 96', width: 96, height: 96, 'aria-hidden': 'true', focusable: 'false', fill: 'none', stroke: 'currentColor', 'stroke-width': 1, 'stroke-linejoin': 'round' }, ...starParts()),
    h('span', { class: 'ds-core-static' }, '◉ ', count + ' running'),
    h('span', { class: 'ds-sr' }, running ? count + ' running' : 'Nothing running'));
}

export function wordmark() {
  return h('span', { class: 'ds-wordmark', 'aria-label': 'Archeus V2' }, 'ARCHEUS ', h('span', null, 'V2'));
}

export function lockup() {
  return h('div', { class: 'ds-lockup' }, coreMark(), wordmark());
}

const STAR = '<path d="M32 5L34.4 29.6 59 32 34.4 34.4 32 59 29.6 34.4 5 32 29.6 29.6Z" fill="none" stroke="#EFE9DA" stroke-width="1.6" stroke-linejoin="round"/><path d="M32 32L44 20M32 32L44 44M32 32L20 44M32 32L20 20" stroke="#EFE9DA" stroke-width="1" opacity=".6"/><circle cx="32" cy="32" r="1.6" fill="#EFE9DA"/>';
export const faviconSVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#0C0811"/>' + STAR + '</svg>';
export const pwaIconSVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" fill="#0C0811"/><g transform="translate(96 96) scale(5)">' + STAR.replace(/stroke-width="1.6"/, 'stroke-width="1.3"') + '</g></svg>';
