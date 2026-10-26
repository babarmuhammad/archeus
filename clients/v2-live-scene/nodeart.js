const NS = 'http://www.w3.org/2000/svg';
export function s(tag, attrs, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, String(value));
  }
  for (const child of kids.flat(Infinity)) if (child != null) el.append(child.nodeType ? child : document.createTextNode(String(child)));
  return el;
}
export const icons = Object.freeze({
  'doc-search': 'M13 21H4V3h11l5 5v4M14 3v6h6M7 7h3M7 12h5M7 16h3M19 19l4 4M21 16a5 5 0 1 1-10 0 5 5 0 0 1 10 0',
  doc: 'M5 2h10l5 5v15H5ZM14 2v6h6M8 12h9M8 16h9M8 19h6',
  prompt: 'M3 3h18v18H3ZM7 8l4 4-4 4M13 16h4',
  'shield-check': 'M12 2l9 5v9l-9 6-9-6V7ZM7 12l4 4 6-7',
  bars: 'M4 21v-7M9 21V9M14 21V5M19 21V2',
  notes: 'M4 2h16v20H4ZM7 7h10M7 11h10M7 15h10M7 19h6',
  lightbulb: 'M9 20h6M10 23h4M8 16c0-3-3-3-3-7a7 7 0 0 1 14 0c0 4-3 4-3 7v1H8Z',
  cube: 'M12 2l10 5v10l-10 5-10-5V7ZM2 7l10 5 10-5M12 12v10M7 4.5l10 5',
  sliders: 'M2 5h4M10 5h12M2 12h12M18 12h4M2 19h6M12 19h10M6 3v4h4V3ZM14 10v4h4v-4ZM8 17v4h4v-4Z',
  home: 'M2 11L12 2l10 9M5 9v13h5v-8h4v8h5V9',
  'check-circle': 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0M7 12l4 4 6-8',
  'stop-square': 'M4 4h16v16H4Z'
});
export function icon(name = 'doc', size = 36) {
  return s('svg', {x: -size / 2, y: -size / 2, width: size, height: size, viewBox: '0 0 24 24', 'aria-hidden': 'true'},
    s('path', {d: icons[name] || icons.doc, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}));
}
export function randomSeed(seed) {
  let n = 2166136261;
  for (const c of String(seed)) n = Math.imul(n ^ c.charCodeAt(0), 16777619);
  return () => { n += 0x6D2B79F5; let t = Math.imul(n ^ n >>> 15, 1 | n); t ^= t + Math.imul(t ^ t >>> 7, 61 | t); return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
export function line(a, b, opacity = .5) {
  return s('path', {d: `M${a}L${b}`, fill: 'none', stroke: 'currentColor', 'stroke-width': .75, 'stroke-opacity': opacity, 'vector-effect': 'non-scaling-stroke'});
}
export function text(x, y, value, cls = 'title', anchor = 'start') {
  return s('text', {x, y, class: cls, 'text-anchor': anchor}, value);
}
export function missionPoly({seed = 'mission', sides = 7, state = 'idle', icon: glyph = 'doc', size = 210} = {}) {
  const rng = randomSeed(seed), n = Math.max(5, Math.min(12, Math.round(sides))), r = size / 2;
  const outer = Array.from({length: n}, (_, i) => { const a = i * Math.PI * 2 / n - Math.PI / 2, d = r * (.9 + rng() * .1); return [Math.cos(a) * d, Math.sin(a) * d]; });
  const inner = outer.map(([x, y]) => [x * .63 + (rng() - .5) * r * .14, y * .63 + (rng() - .5) * r * .14]);
  const centre = [(rng() - .5) * r * .2, (rng() - .5) * r * .2];
  const g = s('g', {class: `node-art state-${state}`});
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    g.append(line(outer[i], outer[j], .9), line(inner[i], inner[j], .45), line(outer[i], inner[i], .65), line(outer[i], inner[j], .42), line(inner[i], centre, .28));
    // Rear facets supply depth without a filled or luminous surface.
    g.append(line(outer[i], outer[(i + 2) % n], .2), line(inner[i], inner[(i + 3) % n], .23));
  }
  for (const [cx, cy] of outer) g.append(s('circle', {cx, cy, r: 2.2, fill: 'currentColor'}));
  g.append(s('circle', {r: size * .14, fill: 'var(--scene-bg, #0C0811)'}), icon(glyph, size * .23));
  return g;
}
export function projectPoly(options = {}) { return missionPoly({size: 145, sides: 6, icon: 'notes', ...options}); }
export function executionTriangle({size = 150, state = 'idle'} = {}) {
  const r = size / 2, p = [[0, -r], [r, r * .7], [-r, r * .7]], g = s('g', {class: `node-art state-${state}`});
  for (let i = 0; i < 3; i++) { g.append(line(p[i], p[(i + 1) % 3], .9), line(p[i], [0, r * .35], .4), line(p[i], p[(i + 1) % 3].map(v => v * .72), .22)); }
  g.append(icon('prompt', size * .27));
  for (const [cx, cy] of p) g.append(s('circle', {cx, cy, r: 2.5, fill: 'currentColor'}));
  return g;
}
export function core({scale = 1, t = (key, fallback) => fallback, tagline = 'Your projects. In context.'} = {}) {
  const root = s('g', {class: 'core', transform: `scale(${scale})`}), mark = s('g', {class: 'core-mark'});
  const p = Array.from({length: 8}, (_, i) => { const a = i * Math.PI / 4; return [Math.cos(a) * (i % 2 ? 78 : 112), Math.sin(a) * (i % 2 ? 78 : 112)]; });
  for (let i = 0; i < 8; i++) for (const step of [2, 3, 4]) mark.append(line(p[i], p[(i + step) % 8], step === 3 ? .68 : .4));
  mark.append(line([-142, 0], [142, 0], .85), line([0, -145], [0, 145], .85));
  root.append(mark, text(0, 178, t('brand.name', 'ARCHEUS'), 'wordmark', 'middle'), text(0, 204, t(tagline === 'UNDERSTAND · PLAN · DO' ? 'core.calmTagline' : 'core.tagline', tagline), 'subtitle', 'middle'));
  return root;
}
export function projectHexagon({title = 'Notes', items = [], t = (key, fallback) => fallback} = {}) {
  const p = [[0, -130], [125, -70], [125, 85], [0, 145], [-125, 85], [-125, -70]];
  const g = s('g', {class: 'project-panel'});
  g.append(s('polygon', {points: p.map(v => v.join(',')).join(' '), fill: 'var(--scene-bg, #0C0811)', stroke: 'currentColor', 'stroke-width': .8, 'vector-effect': 'non-scaling-stroke'}));
  for (const [cx, cy] of p) g.append(s('circle', {cx, cy, r: 1.8, fill: 'currentColor'}));
  g.append(text(-85, -48, t(`project.${title}`, title), 'panel-title'), line([-88, -29], [88, -29], .65));
  items.forEach((item, i) => { const y = 1 + i * 58; g.append(s('circle', {cx: -84, cy: y - 4, r: 5, class: item.state === 'done' ? 'done-dot' : 'idle-dot'}), text(-67, y, t(item.key || `item.${item.title}`, item.title), 'item-title'), text(-67, y + 21, t(`state.${item.state}`, item.state === 'done' ? 'Done' : 'Captured'), 'item-state')); });
  return g;
}
export function decisionMarker() { return s('g', {class: 'state-waiting', 'aria-hidden': 'true'}, s('path', {d: 'M0-11 9 0 0 11-9 0Z', fill: 'currentColor'}), s('path', {d: 'M0-4v5M0 4v1', stroke: 'var(--scene-bg, #0C0811)', 'stroke-width': 1.5})); }
export function reviewButton({t = (key, fallback) => fallback, onactivate, hitHeight = 44} = {}) {
  const g = s('g', {class: 'review action state-waiting', tabindex: 0, role: 'button', 'aria-label': t('review.label', 'Review plan')},
    s('rect', {x: -80, y: -hitHeight / 2, width: 160, height: hitHeight, rx: 5, fill: 'var(--scene-bg, #0C0811)', stroke: 'currentColor', 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke'}), text(-48, 6, t('review', 'Review'), 'button-label'), s('path', {d: 'M38 0h17m-6-6 6 6-6 6', fill: 'none', stroke: 'currentColor'}));
  if (onactivate) { g.addEventListener('click', onactivate); g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onactivate(e); } }); }
  return g;
}
