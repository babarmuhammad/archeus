// The Work graph on a phone: its own full height view, not the desktop graph squeezed. At most GRAPH_NODES missions and decisions as large nodes (52 px, a state glyph inside) on a ring round the core,
// a label only where one fits without touching another label or a node (placeLabels), tap to select, drag to pan and pinch to zoom, Fit to come back. The list has everything the graph leaves out.
//   const g = createPhoneGraph({ onSelect(id) }); host.append(g.el); g.update({ nodes: [{ id, cls, state, title, word, project }], selected, label });
import { s } from './dom.js';
import { star } from './brand.js';
import { glyph } from './icons.js';
import { ringLayout, placeLabels, shortLabel, clampView } from './phone-lists-model.js';

export const NODE_R = 26;
const LABEL_SIZE = 13;
const FIT = { w: 92, h: 44 }; // the Fit button floats over the bottom right corner (work.css .wg-fit)

export function createPhoneGraph({ onSelect }) {
  const world = s('g', { class: 'wg-world' }), svg = s('svg', { class: 'wg-svg', role: 'group', focusable: 'false' }, world);
  const el = document.createElement('div');
  el.className = 'wg-box'; el.append(svg);
  let model = { nodes: [], selected: null, label: '' }, size = { w: 0, h: 0 }, view = { k: 1, x: 0, y: 0 }, sig = '';

  function draw() {
    const { w, h } = size;
    if (!w || !h) return;
    const nodes = model.nodes, pts = ringLayout(nodes.length, w, h, NODE_R), cx = w / 2, cy = h / 2;
    const items = nodes.map((n, i) => ({ id: n.id, ...pts[i], r: NODE_R, text: shortLabel(n.title), priority: n.id === model.selected ? 3 : n.cls === 'needs_you' ? 2 : 1 }));
    const labels = placeLabels(items, { x: 4, y: 4, w: w - 8, h: h - 8 }, { size: LABEL_SIZE, avoid: [{ x: w - FIT.w - 12, y: h - FIT.h - 12, w: FIT.w, h: FIT.h }] });
    const core = star(40); core.setAttribute('x', cx - 20); core.setAttribute('y', cy - 20); core.setAttribute('class', 'wg-core');
    world.replaceChildren(...items.map((p) => s('line', { class: 'wg-edge', x1: cx, y1: cy, x2: p.x, y2: p.y })), core, ...nodes.map((n, i) => {
      const p = pts[i], l = labels.get(n.id), glyphEl = glyph(n.cls, 24);
      glyphEl.setAttribute('x', -12); glyphEl.setAttribute('y', -12);
      return s('g', { class: 'wgn' + (n.id === model.selected ? ' wgn-on' : ''), 'data-id': n.id, 'data-state': n.state, transform: `translate(${p.x} ${p.y})`, role: 'button', tabindex: '0', 'aria-pressed': String(n.id === model.selected), 'aria-label': `${n.title}, ${n.word}${n.project ? ', ' + n.project : ''}` },
        s('circle', { class: 'wgn-sel', r: NODE_R + 6 }), s('circle', { class: 'wgn-body', r: NODE_R }), glyphEl,
        l ? s('text', { class: 'wgn-label', x: l.x - p.x, y: l.y - p.y, 'text-anchor': l.anchor, 'dominant-baseline': 'central', 'font-size': LABEL_SIZE }, shortLabel(n.title)) : null);
    }));
    world.setAttribute('transform', `translate(${view.x} ${view.y}) scale(${view.k})`);
  }
  const apply = () => { view = clampView(view, size.w, size.h); world.setAttribute('transform', `translate(${view.x} ${view.y}) scale(${view.k})`); };

  // one pointer pans, two pinch; a press that never moved is a tap on the node under it
  const ptrs = new Map();
  let tap = null, pinch = 0;
  const idAt = (e) => { const n = e.target.closest && e.target.closest('[data-id]'); return n ? n.dataset.id : null; };
  svg.addEventListener('pointerdown', (e) => { ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY }); tap = ptrs.size === 1 ? { id: idAt(e), x: e.clientX, y: e.clientY } : null; pinch = 0; });
  svg.addEventListener('pointermove', (e) => {
    const p = ptrs.get(e.pointerId);
    if (!p) return;
    const dx = e.clientX - p.x, dy = e.clientY - p.y;
    if (ptrs.size === 1 && (!tap || Math.hypot(e.clientX - tap.x, e.clientY - tap.y) > 8)) {
      tap = null; svg.setPointerCapture(e.pointerId);
      view = { ...view, x: view.x + dx, y: view.y + dy }; apply();
    } else if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()], before = Math.hypot(a.x - b.x, a.y - b.y);
      ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const [c, d] = [...ptrs.values()], now = Math.hypot(c.x - d.x, c.y - d.y);
      if (before && now) {
        const r = svg.getBoundingClientRect(), mx = (c.x + d.x) / 2 - r.left, my = (c.y + d.y) / 2 - r.top, k = Math.max(1, Math.min(3, view.k * now / before)), f = k / view.k;
        view = { k, x: mx - (mx - view.x) * f, y: my - (my - view.y) * f }; apply();
      }
      return;
    }
    ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
  });
  const up = (e) => {
    ptrs.delete(e.pointerId);
    if (e.type === 'pointerup' && tap && tap.id && idAt(e) === tap.id) onSelect(tap.id);
    tap = null;
  };
  svg.addEventListener('pointerup', up); svg.addEventListener('pointercancel', up);
  svg.addEventListener('keydown', (e) => { const id = idAt(e); if (id && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onSelect(id); } });
  svg.addEventListener('wheel', (e) => { e.preventDefault(); const r = svg.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, k = Math.max(1, Math.min(3, view.k * (e.deltaY < 0 ? 1.15 : 1 / 1.15))), f = k / view.k; view = { k, x: mx - (mx - view.x) * f, y: my - (my - view.y) * f }; apply(); }, { passive: false });

  const resize = () => {
    const w = Math.round(el.clientWidth), h = Math.round(el.clientHeight);
    if (!w || !h || (w === size.w && h === size.h)) return; // detached while the page redraws: keep the picture and its zoom
    size = { w, h }; svg.setAttribute('viewBox', `0 0 ${w} ${h}`); view = { k: 1, x: 0, y: 0 }; sig = ''; draw();
  };
  const watch = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize);
  if (watch) watch.observe(el);

  return {
    el,
    // The picture is redrawn only when something it shows changed, so a simulation tick never interrupts a drag.
    update(next) {
      model = next;
      svg.setAttribute('aria-label', next.label || '');
      const now = JSON.stringify([size, next.selected, next.nodes.map((n) => [n.id, n.cls, n.state, n.title, n.word, n.project])]);
      if (now !== sig) { sig = now; draw(); }
    },
    fit() { view = { k: 1, x: 0, y: 0 }; apply(); },
    destroy() { if (watch) watch.disconnect(); }
  };
}
