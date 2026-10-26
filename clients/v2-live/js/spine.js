// Draws the spine (ADR-0054) as vector SVG, one component, three sizes. Static: no animation. Figure is aria-hidden, the sentence is text.
import { h, s } from './dom.js';
import { spineOf, STATIONS } from '../spine-model.js';

// Owner decision: in narrow inspectors the stations show their short imperative names (the concepts' Understand, Plan, Approve, Run, Verify, Review); the full Core names stay for wide ones.
const SHORT = ['Understand', 'Plan', 'Approve', 'Run', 'Verify', 'Review'];

// One mark centred at (cx, cy) in a box of size `d`. Shape carries the meaning; colour only confirms it.
function mark(m, cx, cy, d) {
  const r = d / 2, sw = d >= 14 ? 2 : 1.5;
  if (m.kind === 'passed') {
    return s('g', null, s('circle', { class: 'disc', cx, cy, r }),
      s('path', { class: 'chk', 'stroke-width': Math.max(1, d * 0.14), d: 'M' + (cx - d * 0.23) + ' ' + cy + 'L' + (cx - d * 0.05) + ' ' + (cy + d * 0.19) + 'L' + (cx + d * 0.26) + ' ' + (cy - d * 0.2) }));
  }
  if (m.kind === 'ahead') return s('circle', { class: 'ring', cx, cy, r: r - sw / 2, 'stroke-width': sw });
  if (m.kind === 'unknown') return s('circle', { class: 'ring', cx, cy, r: r - sw / 2, 'stroke-width': sw, 'stroke-dasharray': '1.5 2' });
  if (m.kind === 'none') return s('line', { class: 'seg', x1: cx - r * 0.6, x2: cx + r * 0.6, y1: cy, y2: cy, 'stroke-width': sw });
  const c = m.cls, k = 'cur ' + c;
  if (c === 'needs_you') return s('polygon', { class: k, points: [cx, cy - r, cx + r, cy, cx, cy + r, cx - r, cy].join(' ') });
  if (c === 'approved') return s('polygon', { class: k + ' o', 'stroke-width': sw, points: [cx, cy - r + 1, cx + r - 1, cy, cx, cy + r - 1, cx - r + 1, cy].join(' ') });
  if (c === 'planning') return s('circle', { class: k + ' o', cx, cy, r: r - sw / 2, 'stroke-width': sw, 'stroke-dasharray': '2 1.6' });
  if (c === 'blocked') return s('rect', { class: k, x: cx - r * 0.8, y: cy - r * 0.8, width: d * 0.8, height: d * 0.8 });
  if (c === 'paused') return s('g', null, s('rect', { class: k, x: cx - r * 0.7, y: cy - r * 0.85, width: d * 0.28, height: d * 0.85 }), s('rect', { class: k, x: cx + r * 0.14, y: cy - r * 0.85, width: d * 0.28, height: d * 0.85 }));
  if (c === 'failed') return s('path', { class: k + ' o', 'stroke-width': sw + 0.5, 'stroke-linecap': 'round', d: 'M' + (cx - r * 0.7) + ' ' + (cy - r * 0.7) + 'L' + (cx + r * 0.7) + ' ' + (cy + r * 0.7) + 'M' + (cx + r * 0.7) + ' ' + (cy - r * 0.7) + 'L' + (cx - r * 0.7) + ' ' + (cy + r * 0.7) });
  return s('circle', { class: k, cx, cy, r });
}

function segment(kind, x1, x2, y, sw) {
  return s('line', { class: 'seg', x1, x2, y1: y, y2: y, 'stroke-width': sw, 'stroke-dasharray': kind === 'dashed' ? '3 2' : kind === 'dotted' ? '1 2' : null });
}

function strip(sp, d, pitch, pad) {
  const w = pad * 2 + pitch * 5 + d, hgt = d + 4, cy = hgt / 2;
  const svg = s('svg', { width: w, height: hgt, viewBox: '0 0 ' + w + ' ' + hgt, 'aria-hidden': 'true', focusable: 'false' });
  sp.segments.forEach((k, i) => { const x1 = pad + i * pitch + d + 1, x2 = pad + (i + 1) * pitch - 1; if (x2 > x1) svg.append(segment(k, x1 - 1, x2 + 1, cy, d >= 10 ? 1.5 : 1.25)); });
  sp.marks.forEach((m, i) => svg.append(mark(m, pad + i * pitch + d / 2, cy, d)));
  return svg;
}

const wrap = (size, sp, ...kids) => h('span', { class: 'spine', 'data-size': size, 'data-done': sp.done ? 'true' : 'false' }, ...kids, h('span', { class: 'vh' }, sp.text));

export function spineRow(state, held) {
  const sp = spineOf(state, held);
  if (!sp.marks.length) return wrap('row', sp);
  return wrap('row', sp, strip(sp, 8, 11.2, 0)); // six 8 px marks, 64 px wide, 12 px high
}

export function spineCard(state, held) {
  const sp = spineOf(state, held);
  if (!sp.marks.length) return h('span', { class: 'spine-card' }, sp.text);
  const cur = sp.station ? STATIONS[sp.station - 1] : '';
  return h('span', { class: 'spine-card' }, wrap('card', sp, strip(sp, 10, 22, 0)), h('span', { class: 'cap', 'aria-hidden': 'true' }, sp.unknown ? 'Position unknown' : sp.none ? sp.text.replace(/\.$/, '') : cur));
}

export function spineInspector(state, held, d = 16) {
  const sp = spineOf(state, held);
  if (!sp.marks.length) return h('p', null, sp.text);
  const ol = h('ol', { class: 'spine spine-insp', 'data-done': sp.done ? 'true' : 'false', 'aria-label': 'Mission steps' });
  sp.marks.forEach((m, i) => {
    const svg = s('svg', { width: d, height: d, viewBox: '0 0 ' + d + ' ' + d, 'aria-hidden': 'true', focusable: 'false' }, mark(m, d / 2, d / 2, d));
    const cur = m.kind === 'current' || (sp.station === i + 1 && !sp.unknown && !sp.done && m.kind !== 'ahead');
    ol.append(h('li', { 'aria-current': cur ? 'step' : null }, i > 0 ? h('span', { class: 'seg-l ' + sp.segments[i - 1], 'aria-hidden': 'true' }) : null, svg, h('span', { class: 'st-f' }, STATIONS[i]), h('span', { class: 'st-s' }, SHORT[i])));
  });
  return h('div', null, ol, h('p', { class: 'sp-text' }, sp.text));
}
