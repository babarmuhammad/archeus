// The one motion layer (spec: .collab/v2live-motion-spec.md). Every animation that is not a plain css hover or press transition goes through here:
// Web Animations on transform and opacity (tint: a background colour, paint only), finite, interruptible, nothing on layout, nothing under Reduced motion.
// Durations and curves are the css tokens (--dur-1..4, --ease-out, --ease-move); the pure decisions (what moved, which way a route travels) live in motion-model.js.
//
// The shell re-renders the whole page on every simulation event, so rows are matched by key across renders: capture(roots) before, play(snap, roots) after.
// A page opts a row in with one attribute: data-mk="<stable key>" (or it already carries data-key or matches ROWS). Chat and Usage rows do that after their merge.
import { reducedMotion } from './store.js';
import { plan, direction, staggerDelay, keyOf, ticks } from './motion-model.js';

const root = document.documentElement;
const ROWS = '.mrow, .card.band, .rp-event, .pcell, .pidea, .ax-xrow, .us-row, .hl-row, .ln-row, .sec-row, .ax-acct, .ax-model, .ax-idea, .msg, .proj-item[data-proj], .safety, .stop-btn, [data-mk]';
const NUMS = [['.n', (el) => (el.parentElement.querySelector(':scope > .gt') || {}).textContent], ['.ctr b', (el) => (el.nextElementSibling || {}).textContent]];
// A popover, a sheet or a dialog that the shell draws and removes. in: how it arrives (css owns the ones with a keyframe of their own); out: how its last copy leaves.
const OVERLAYS = [
  { sel: '.safety-pop', into: '.app', enter: { s: .98, origin: '0 0', dur: 1 }, exit: null },
  { sel: '.pl-wrap', into: '.app', enter: null, exit: { y: 24, dur: 2 } },
  { sel: '.chatdock.tell:not([hidden])', into: '.app', clone: true, enter: { y: 8, s: .98, origin: '50% 100%', dur: 1 }, exit: { y: 8, s: .98, dur: 1 } }
];

let tok = null;
const T = () => {
  if (tok) return tok;
  const cs = getComputedStyle(root), n = (v, d) => parseFloat(cs.getPropertyValue(v)) || d, e = (v, d) => cs.getPropertyValue(v).trim() || d;
  return (tok = { 1: n('--dur-1', 100), 2: n('--dur-2', 160), 3: n('--dur-3', 200), 4: n('--dur-4', 240), out: e('--ease-out', 'cubic-bezier(.23, 1, .32, 1)'), move: e('--ease-move', 'cubic-bezier(.65, 0, .35, 1)') });
};
export const on = () => !reducedMotion() && typeof Element.prototype.animate === 'function';

const running = new WeakMap();
// One animation per element and kind: starting it again replaces the one in flight, so a rapid change retargets instead of queueing.
function run(el, kind, frames, o) {
  if (!on() || !el.isConnected) return null;
  const prev = running.get(el);
  if (prev && prev[kind]) prev[kind].cancel();
  const a = el.animate(frames, { fill: 'backwards', easing: T().out, ...o });
  const slot = prev || {};
  slot[kind] = a; running.set(el, slot);
  const done = () => { if (slot[kind] === a) delete slot[kind]; };
  a.onfinish = done; a.oncancel = done;
  return a;
}
// Individual transform properties (translate, scale) compose with an element's own transform instead of replacing it, so a centred dock or a rotated chevron keeps its place.
const from = ({ x = 0, y = 0, s = 1 }) => ({ opacity: 0, translate: `${x}px ${y}px`, scale: s });
const REST = { translate: 'none', scale: 'none' };

// Something new on screen: opacity and a short move (6 px for rows), from its origin when it has one.
export function enter(el, { x = 0, y = 6, s = 1, origin, dur = 2, delay = 0, ease } = {}) {
  if (origin) el.style.transformOrigin = origin;
  return run(el, 'enter', [from({ x, y, s }), { opacity: 1, ...REST }], { duration: T()[dur] || dur, delay, easing: ease || T().out });
}

// A single 180 ms tint on a changed cell: a flat translucent fill that fades to the cell's own background. Paint only, never on a full redraw.
export function tint(el, color) {
  const edge = getComputedStyle(el).getPropertyValue('--edge').trim();
  const c = color || `color-mix(in srgb, ${edge || 'var(--text)'} 16%, transparent)`;
  return run(el, 'tint', [{ backgroundColor: c }], { duration: T()[2], easing: T().out });
}

// A number that changed: the new one rises into place instead of swapping.
export function tick(el) { return run(el, 'tick', [{ opacity: 0, translate: '0 40%' }, { opacity: 1, translate: 'none' }], { duration: T()[2] }); }

// ---------- ghosts: a leaving thing stays for one short exit ----------
const COPY = ['display', 'flexDirection', 'backgroundColor', 'color', 'borderTop', 'borderRight', 'borderBottom', 'borderLeft', 'borderRadius', 'overflow', 'zIndex'];
function boxOf(el, into) {
  const r = el.getBoundingClientRect(), a = into.getBoundingClientRect(), k = a.width / (into.offsetWidth || a.width) || 1, cs = getComputedStyle(el);
  return { x: (r.left - a.left) / k, y: (r.top - a.top) / k, w: r.width / k, h: r.height / k, css: COPY.map((p) => [p, cs[p]]) };
}
function hush(node) {
  node.inert = true; node.setAttribute('aria-hidden', 'true');
  for (const e of [node, ...node.querySelectorAll('[data-key], [id], [data-mk]')]) { e.removeAttribute('data-key'); e.removeAttribute('data-mk'); e.removeAttribute('id'); }
}
// `node` (the old element, or a clone) is put back inside `into` at the box it had, then fades and leaves. exit: { x, y, s, dur }.
function ghost(node, box, into, { x = 0, y = 0, s = 1, dur = 2 } = {}) {
  if (!on()) return;
  hush(node);
  node.classList.add('m-ghost');
  Object.assign(node.style, { position: 'absolute', left: box.x + 'px', top: box.y + 'px', width: box.w + 'px', height: box.h + 'px', margin: '0', transform: 'none', pointerEvents: 'none' });
  for (const [p, v] of box.css) node.style[p] = v;
  into.append(node);
  const a = node.animate([{ opacity: 1, ...REST }, { opacity: 0, translate: `${x}px ${y}px`, scale: s }], { duration: T()[dur], easing: T().out, fill: 'forwards' });
  a.onfinish = a.oncancel = () => node.remove();
}
// A box the user closes (the Details sheet): clone it before it is hidden, leave the clone beside it.
export function exitClone(el, o) {
  if (!on() || !el.offsetParent) return;
  const into = el.parentElement;
  ghost(el.cloneNode(true), boxOf(el, into), into, o);
}

// ---------- re-render continuity: rows glide, new rows enter, gone rows leave, a changed row tints ----------
const rowsOf = (roots) => {
  const out = new Map(), dup = new Map();
  for (const r of roots) for (const el of r.querySelectorAll(ROWS)) {
    if (el.parentElement.closest(ROWS)) continue;
    let key = keyOf(el);
    if (!key) continue;
    const rect = el.getBoundingClientRect();
    if (!rect.width) continue;
    const n = dup.get(key) || 0; dup.set(key, n + 1); if (n) key += '#' + n;
    out.set(key, { el, rect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom }, sig: el.matches('.msg') ? '' : (el.dataset.state || '') + '|' + el.textContent });
  }
  return out;
};
const numsOf = (roots) => {
  const out = new Map();
  for (const r of roots) for (const [sel, label] of NUMS) for (const el of r.querySelectorAll(sel)) { const l = label(el); if (l) out.set(sel + '|' + l, { el, text: el.textContent }); }
  return out;
};
const shape = () => { const a = document.getElementById('app'); return [a.clientWidth, a.clientHeight, root.dataset.theme, root.lang].join('|'); };

export function capture(roots, extra = {}) {
  if (!on()) return null;
  const app = document.getElementById('app');
  return { rows: rowsOf(roots), nums: numsOf(roots), shape: shape(), overlays: OVERLAYS.map((d) => { const el = app.querySelector(d.sel); return el ? { d, el: d.clone ? el.cloneNode(true) : el, box: boxOf(el, app.querySelector(d.into) || app) } : { d, el: null }; }), ...extra };
}

export function play(prev, roots) {
  if (!prev || !on() || prev.shape !== shape()) return;
  const app = document.getElementById('app'), next = rowsOf(roots);
  const view = { top: 0, bottom: innerHeight, left: 0, right: innerWidth };
  const ops = plan(prev.rows, next, { view });
  // leaving rows: the old node goes back beside its nearest surviving neighbour (same parent styles), out of flow, so the rest glide into the gap
  const order = [...prev.rows.keys()];
  const leaves = ops.filter((o) => o.op === 'leave').map((o) => o.key);
  for (const key of leaves) {
    const old = prev.rows.get(key), i = order.indexOf(key);
    let anchor = null, before = false;
    for (let j = i - 1; j >= 0 && !anchor; j--) if (next.has(order[j])) anchor = next.get(order[j]).el;
    for (let j = i + 1; j < order.length && !anchor; j++) if (next.has(order[j])) { anchor = next.get(order[j]).el; before = true; }
    if (!anchor || anchor.parentElement.className !== old.el.parentElement.className) continue;
    const g = old.el, r = old.rect, k = (anchor.getBoundingClientRect().width / (anchor.offsetWidth || 1)) || 1;
    hush(g); g.classList.add('m-ghost');
    Object.assign(g.style, { position: 'absolute', width: (r.right - r.left) / k + 'px', margin: '0', pointerEvents: 'none' });
    (before ? anchor.before(g) : anchor.after(g));
    const now = g.getBoundingClientRect();
    const dx = (r.left - now.left) / k, dy = (r.top - now.top) / k;
    const a = g.animate([{ opacity: 1, translate: `${dx}px ${dy}px` }, { opacity: 0, translate: `${dx}px ${dy - 6}px` }], { duration: T()[1], easing: T().out, fill: 'forwards' });
    a.onfinish = a.oncancel = () => g.remove();
  }
  for (const o of ops) {
    const el = next.get(o.key) && next.get(o.key).el;
    if (!el) continue;
    if (o.op === 'move') {
      const k = (el.getBoundingClientRect().width / (el.offsetWidth || 1)) || 1;
      run(el, 'move', [{ translate: `${o.dx / k}px ${o.dy / k}px` }, { translate: 'none' }], { duration: T()[3], easing: T().move });
    } else if (o.op === 'enter') enter(el, { dur: 2 });
    else if (o.op === 'tint') tint(el);
  }
  for (const [k, n] of numsOf(roots)) { const p = prev.nums.get(k); if (p && ticks(p.text, n.text)) tick(n.el); }
  for (const p of prev.overlays) {
    const el = app.querySelector(p.d.sel);
    if (el && !p.el && p.d.enter) enter(el, { y: 0, ...p.d.enter });
    else if (!el && p.el && p.d.exit) ghost(p.el, p.box, app.querySelector(p.d.into) || app, p.d.exit);
  }
}

// The same, around a plain DOM change: flip(page, () => reorder()).
export function flip(container, mutate) { const s = capture([container]); mutate(); play(s, [container]); }

// ---------- the inspector: a column on a wide window, a sheet on a narrow one ----------
export function inspectorIn(el, width) {
  if (width < 600) return enter(el, { y: 24, dur: 3 });
  return enter(el, { x: width < 1024 ? 32 : 12, y: 0, dur: 3 });
}
export function inspectorOut(oldContent, box, width) {
  if (!on() || !oldContent) return;
  const app = document.getElementById('app'), g = document.createElement('div');
  g.className = 'inspector'; g.append(oldContent);
  ghost(g, box, app, width < 600 ? { y: 24, dur: 2 } : { x: width < 1024 ? 32 : 12, dur: 2 });
}
export const boxOfInspector = (el) => (on() && el.offsetParent ? boxOf(el, document.getElementById('app')) : null);

// ---------- routes ----------
let armed = false, viaVT = false;
export const arm = () => { armed = true; };
export const canRoute = () => armed && on() && document.visibilityState === 'visible';
const stage = (el) => el && el.getClientRects().length;

// A directional cross-fade between pages: View Transitions where the browser has them (css/motion.css names the page snapshot), otherwise just the arrival.
export function route(from, to, update) {
  const dir = direction(from, to);
  if (typeof document.startViewTransition !== 'function' || from === 'terminal' || to === 'terminal') { viaVT = false; update(dir); return; }
  root.dataset.vt = dir > 0 ? 'fwd' : 'back'; viaVT = true;
  const t = document.startViewTransition(() => update(dir));
  const clearVt = () => { delete root.dataset.vt; };
  t.finished.then(clearVt, clearVt);
}

// The page head and the first blocks of content come in one after the other (4 steps at most, 40 ms apart). Only after a route change, never on a live update.
export function arrive(page, dir) {
  if (!on()) return;
  const head = page.querySelector('.page-head, .ax-top, .now-hero');
  const view = page.querySelector('.view');
  let kids = view ? [...view.children] : [];
  if (kids.length === 1) kids = [...kids[0].children];
  const items = [head, ...kids.filter((k) => k !== head && !k.matches('.now-scene, .dnote, dialog') && stage(k))].filter(Boolean).slice(0, 4);
  items.forEach((el, i) => enter(el, { y: 6, dur: 2, delay: staggerDelay(i) }));
  if (!viaVT && page.firstElementChild) run(page.firstElementChild, 'route', [{ translate: `${dir * 12}px 0` }, { translate: 'none' }], { duration: T()[3], easing: T().out });
  viaVT = false;
}

// ---------- the rail's current mark slides between items ----------
let mark = null, markTop = null;
export function railMark(rail, instant) {
  if (!mark) { mark = document.createElement('span'); mark.className = 'rail-mark'; mark.setAttribute('aria-hidden', 'true'); rail.append(mark); rail.dataset.mark = '1'; }
  const cur = rail.querySelector('.nav-item[aria-current="page"]');
  if (!cur || !cur.offsetParent) { mark.hidden = true; markTop = null; return; }
  mark.hidden = false;
  mark.dataset.still = instant || markTop === null || !on() ? '1' : '';
  mark.style.height = cur.offsetHeight + 'px';
  mark.style.transform = `translateY(${cur.offsetTop}px)`;
  markTop = cur.offsetTop;
}

// ---------- tabs: the underline slides to the selected tab, also across the re-render that rebuilds the tab list ----------
const tabPos = new Map();
export function tabs(roots) {
  for (const r of roots) for (const list of r.querySelectorAll('.tabs')) {
    const sel = list.querySelector('[aria-selected="true"]');
    if (!sel || !sel.offsetWidth) continue;
    const id = (list.getAttribute('aria-label') || '') + '|' + (list.closest('.inspector') ? 'i' : 'p');
    list.dataset.mark = '1';
    let m = list.querySelector('.tab-mark');
    if (!m) { m = document.createElement('span'); m.className = 'tab-mark'; m.setAttribute('aria-hidden', 'true'); list.append(m); }
    const x = sel.offsetLeft, was = tabPos.get(id), slide = was != null && was !== x && on();
    m.style.width = sel.offsetWidth + 'px';
    m.dataset.still = '1';
    m.style.transform = `translateX(${slide ? was : x}px)`;
    if (slide) { m.getBoundingClientRect(); delete m.dataset.still; m.style.transform = `translateX(${x}px)`; }
    tabPos.set(id, x);
  }
}
