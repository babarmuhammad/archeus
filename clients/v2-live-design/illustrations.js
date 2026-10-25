import { s } from './dom.js';

const drawings = {
  missions: 'M24 52L60 22 104 32 136 66 94 94 48 88Z M24 52L94 94M60 22L94 94M48 88L104 32',
  clear: 'M24 60L58 28 112 32 138 66 92 94 42 90Z M58 28L92 94M24 60L138 66M66 60l10 10 22-24',
  offline: 'M24 74L56 40 76 54M94 60L118 40 140 70M32 20L128 108 M40 84L62 72M104 80L124 90',
  error: 'M80 18L138 100H22Z M80 46V70M80 82V84 M22 100L12 108M138 100L148 108',
  first: 'M80 14L90 48 124 58 90 68 80 102 70 68 36 58 70 48Z M20 26L36 58 18 88M140 26L124 58 144 94'
};

export function illustration(name, label) {
  const svg = s('svg', { class: 'ds-illustration', width: 160, height: 120, viewBox: '0 0 160 120', fill: 'none', stroke: 'currentColor', 'stroke-width': 1, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', role: label ? 'img' : null, 'aria-label': label || null, 'aria-hidden': label ? null : 'true', focusable: 'false' }, s('path', { d: drawings[name] || drawings.missions }));
  for (const [cx, cy] of [[24, 52], [60, 22], [104, 32], [136, 66], [94, 94], [48, 88]]) svg.append(s('circle', { cx, cy, r: 1.6, fill: 'currentColor', stroke: 'none', opacity: '.5' }));
  return svg;
}
