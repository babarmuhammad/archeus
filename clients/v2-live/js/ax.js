// Small DOM pieces shared by the S3 inspectors and areas: pills, rings, bars, switches, links. Text is always set as text.
import { h, s } from './dom.js';
import { icon } from './icons.js';
import { LOW_LINE, METER_WORD, ROUTE_OF } from './areas-model.js';

// tone -> [glyph]; the colour never carries a state alone: every tone has a glyph and a word.
const GLYPH = { ok: '✓', attention: '◆', blocked: '■', paused: '‖', active: '●', thinking: '◌', unknown: '–' };
export const pill = (tone, word, extra) => h('span', { class: 'ax-pill' + (extra ? ' ' + extra : ''), 'data-tone': tone }, h('span', { class: 'g', 'aria-hidden': 'true' }, GLYPH[tone] || GLYPH.unknown), h('span', { class: 'w' }, word));

export const TONE_OF_METER = { ok: 'active', low: 'attention', critical: 'blocked', out: 'blocked', unknown: 'unknown' };
export const TONE_OF_STATE = { ok: 'ok', attention: 'attention', unknown: 'unknown', off: 'paused', open: 'blocked' };

export const eyebrow = (t) => h('p', { class: 'ax-eyebrow' }, t);
export const sec = (title, ...kids) => h('div', { class: 'ax-sec' }, title ? h('h3', null, title) : null, ...kids);
export const note = (t) => h('p', { class: 'ax-note' }, t);
export const kv = (rows) => h('dl', { class: 'kv' }, ...rows.filter(Boolean).flatMap(([k, v]) => [h('dt', null, k), h('dd', null, v)]));
export const link = (href, text, cls) => h('a', { class: cls || 'ax-link', href }, text);
export const hrefFor = (kind, id) => '#/' + (ROUTE_OF[kind] || 'work') + '/' + id;

// a related thing, as a row that opens its own inspector
export function entity(it, right) {
  return h('a', { class: 'ax-ent', href: hrefFor(it.kind, it.id) }, h('span', { class: 'e-main' }, h('span', { class: 'e-name' }, it.label), it.note ? h('span', { class: 'e-note' }, it.note) : null), right || null, h('span', { class: 'e-go', 'aria-hidden': 'true' }, icon('chevron', 18)));
}

export function sw(o) {
  return h('button', { class: 'ax-sw', type: 'button', role: 'switch', 'aria-checked': o.on ? 'true' : 'false', 'aria-label': o.label, 'data-key': o.key, disabled: o.disabled ? true : null, onclick: o.onclick },
    h('span', { class: 'track', 'aria-hidden': 'true' }, h('span', { class: 'knob' })), h('span', { class: 'sw-w' }, o.on ? 'On' : 'Off'));
}

// ---------- rings and bars: how much is LEFT, so the ring empties as it is used; a tick marks the 20% line ----------
const R = 42, C = 2 * Math.PI * R;
export function ringNode(o) {
  const unk = o.left == null, tone = TONE_OF_METER[o.key];
  const a = (LOW_LINE / 100) * 2 * Math.PI, tx = 50 + Math.sin(a) * (R - 6), ty = 50 - Math.cos(a) * (R - 6), tx2 = 50 + Math.sin(a) * (R + 6), ty2 = 50 - Math.cos(a) * (R + 6);
  const svg = s('svg', { class: 'ring-svg', viewBox: '0 0 100 100', 'aria-hidden': 'true', focusable: 'false' },
    s('circle', { class: 'trk' + (unk ? ' unk' : ''), cx: 50, cy: 50, r: R }),
    unk ? null : s('circle', { class: 'arc', cx: 50, cy: 50, r: R, 'stroke-dasharray': C.toFixed(2), 'stroke-dashoffset': (C * (1 - Math.min(100, o.left) / 100)).toFixed(2), transform: 'rotate(-90 50 50)' }),
    s('line', { class: 'line20', x1: tx.toFixed(2), y1: ty.toFixed(2), x2: tx2.toFixed(2), y2: ty2.toFixed(2) }));
  return h('div', { class: 'ax-ring', 'data-tone': tone, 'data-ax-ring': o.live || null, role: 'img', 'aria-label': o.label + ': ' + (unk ? 'unknown' : o.left + ' percent left. ' + METER_WORD[o.key]) },
    svg, h('div', { class: 'ring-c' }, h('span', { class: 'big' }, unk ? 'unknown' : Math.round(o.left) + '%'), h('span', { class: 'cap' }, unk ? 'no reading' : 'left')));
}
export function patchRing(el, left, key) {
  const unk = left == null; el.dataset.tone = TONE_OF_METER[key];
  const arc = el.querySelector('.arc'); if (arc && !unk) arc.setAttribute('stroke-dashoffset', (C * (1 - Math.min(100, left) / 100)).toFixed(2));
  const big = el.querySelector('.big'); if (big) big.textContent = unk ? 'unknown' : Math.round(left) + '%';
  el.setAttribute('aria-label', (el.getAttribute('aria-label') || '').split(':')[0] + ': ' + (unk ? 'unknown' : left + ' percent left. ' + METER_WORD[key]));
}

export function barNode(o) {
  const unk = o.left == null;
  return h('div', { class: 'ax-bar', 'data-tone': TONE_OF_METER[o.key], 'data-unk': unk ? 'true' : 'false', role: 'img', 'aria-label': o.label + ': ' + (unk ? 'unknown' : o.left + ' percent left') },
    h('i', { style: 'width:' + (unk ? 0 : Math.min(100, o.left)) + '%' }), h('b', { class: 'tick', style: 'left:' + LOW_LINE + '%' }));
}

export function spark(points, w, hgt) {
  w = w || 160; hgt = hgt || 36;
  const svg = s('svg', { class: 'ax-spark', viewBox: '0 0 ' + w + ' ' + hgt, preserveAspectRatio: 'none', 'aria-hidden': 'true', focusable: 'false' });
  if (points.length < 2) return svg;
  const t0 = points[0].t, t1 = points[points.length - 1].t || 1, span = Math.max(1, t1 - t0);
  const lo = Math.min(...points.map((p) => p.s)), hi = Math.max(lo + 8, ...points.map((p) => p.s));
  const xy = points.map((p) => [((p.t - t0) / span) * (w - 2) + 1, hgt - 3 - ((p.s - lo) / (hi - lo)) * (hgt - 8)]);
  const d = xy.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('');
  svg.append(s('path', { class: 'area', d: d + 'L' + xy[xy.length - 1][0].toFixed(1) + ' ' + hgt + 'L1 ' + hgt + 'Z' }), s('path', { class: 'ln', d }));
  return svg;
}

export function stat(tone, big, label, sub) {
  return h('div', { class: 'ax-stat', 'data-tone': tone }, h('span', { class: 'big' }, big), h('span', { class: 'lab' }, label), sub ? h('span', { class: 'sub' }, sub) : null);
}
