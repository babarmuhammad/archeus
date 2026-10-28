// The one bottom sheet. A detent is a resting height (peek, half, full) of the space above the keyboard; the handle drags between them and is also a button, so a drag
// always has a keyboard and screen reader twin. Esc, the scrim, Close and the system Back all close it. Existing sheets are moved onto this one slice by slice.
//   const s = openSheet({ id: 'places', title: 'Places', detents: ['half', 'full'], initial: 'half', content: node, footer: node, modal: true, onClose })
//   s.setDetent('full'); s.close(); s.el  (the dialog element)
// modal (default true): scrim, the page behind inert, focus trapped, aria-modal. modal: false is modeless (page stays usable) until the sheet reaches full.
import { h, trapTab } from './dom.js';
import { icon } from './icons.js';
import { translate, tr } from './i18n.js';
import { reducedMotion } from './store.js';
import { heights, snap, velocity, follow, step, stepLabel, isModal } from './sheet-model.js';

const stack = [];
// One popstate listener for every sheet: Back closes the top sheet that owns a history entry. A back() the sheet made itself (closing by its own button) is swallowed,
// or it would close the sheet underneath.
let ownBack = 0;
addEventListener('popstate', () => {
  if (ownBack) { ownBack--; return; }
  const top = [...stack].reverse().find((x) => x.entry);
  if (top) top.close(false);
});
let seq = 0;

// Everything outside the sheet's own branch goes inert, and comes back when the sheet closes.
function inertRest(wrap) {
  const done = [];
  for (let node = wrap; node !== document.body; node = node.parentElement) {
    [...node.parentElement.children].forEach((el) => { if (el !== node && !el.inert && !el.matches('.toast, .apbar')) { el.inert = true; done.push(el); } });
  }
  return () => done.forEach((el) => { el.inert = false; });
}

// history: false for a sheet whose address is the route (an inspector at #/work/a-1): it adds no history entry, so Back is the route's and onClose(fromUi) navigates.
// fixed: { peek: 180 } pins a detent to pixels instead of a share (the Tell sheet's peek is just the composer).
export function openSheet({ id, title, detents = ['half', 'full'], initial, content, onClose, footer, modal = true, host = document.getElementById('app'), history: own = true, fixed }) {
  const uid = 'sheet-' + (id || ++seq), many = detents.length > 1, opener = document.activeElement;
  let detent = detents.includes(initial) ? initial : detents[0], closed = false, drag = null, release = null, ownEntry = false;

  const grip = h(many ? 'button' : 'div', many ? { class: 'sheet-grip', type: 'button', 'data-key': uid + '-grip', 'aria-label': stepLabel(detent, detents) } : { class: 'sheet-grip', 'aria-hidden': 'true' });
  const heading = h('h2', { id: uid + '-t', tabindex: '-1' }, title);
  const el = h('section', { class: 'sheet', role: 'dialog', 'aria-labelledby': uid + '-t', 'data-detent': detent },
    grip,
    h('div', { class: 'sheet-head' }, heading, h('button', { class: 'sheet-close', type: 'button', 'data-key': uid + '-x', 'aria-label': 'Close', onclick: () => close() }, icon('close', 20))),
    h('div', { class: 'sheet-body' }, content),
    footer ? h('div', { class: 'sheet-foot' }, footer) : null);
  const wrap = h('div', { class: 'sheet-wrap', 'data-sheet': uid, 'data-enter': '' }, h('div', { class: 'sheet-scrim', 'aria-hidden': 'true', onclick: () => close() }), el);

  const sizes = () => heights(detents, wrap.clientHeight, fixed);
  const setPx = (v) => { el.style.setProperty('--sheet-h', v + 'px'); host.style.setProperty('--toast-b', 'calc(' + Math.round(v) + 'px + var(--vv-bottom) + 8px)'); };
  const modalNow = () => isModal(detent, modal);
  let unInert = null;
  function syncModal() {
    const m = modalNow();
    wrap.toggleAttribute('data-modal', m);
    if (m) el.setAttribute('aria-modal', 'true'); else el.removeAttribute('aria-modal');
    if (m && !unInert) unInert = inertRest(wrap); else if (!m && unInert) { unInert(); unInert = null; }
  }
  function setDetent(name) {
    if (closed || !detents.includes(name)) return;
    detent = name; el.dataset.detent = name;
    const d = sizes().find((x) => x.name === name); setPx(d ? d.px : 0);
    if (many) grip.setAttribute('aria-label', tr(stepLabel(name, detents)));
    syncModal();
  }

  const end = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const d = drag; drag = null; delete el.dataset.drag;
    if (!d.moved) return;
    d.moved = false; release = true; setTimeout(() => { release = null; }, 50);
    const to = snap({ height: el.offsetHeight, velocity: velocity(d.samples), detents: sizes() });
    if (to === 'close') close(); else setDetent(to);
  };
  grip.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    drag = { id: e.pointerId, y0: e.clientY, h0: el.offsetHeight, samples: [{ t: e.timeStamp, y: e.clientY }], moved: false };
    grip.setPointerCapture(e.pointerId);
  });
  grip.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const dy = e.clientY - drag.y0;
    if (!drag.moved && Math.abs(dy) < 4) return;
    drag.moved = true; el.dataset.drag = '';
    drag.samples.push({ t: e.timeStamp, y: e.clientY }); if (drag.samples.length > 8) drag.samples.shift();
    setPx(follow(drag.h0, dy, sizes().at(-1).px));
  });
  grip.addEventListener('pointerup', end);
  grip.addEventListener('pointercancel', end);
  if (many) {
    grip.addEventListener('click', () => { if (!release) setDetent(step(detent, detents)); });
    grip.addEventListener('keydown', (e) => { if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); setDetent(step(detent, detents, e.key === 'ArrowUp' ? 1 : -1)); } });
  }

  const onKey = (e) => {
    if (stack.at(-1) !== api || e.defaultPrevented) return;
    if (e.key === 'Escape') { e.preventDefault(); close(); } else if (modalNow()) trapTab(e, el);
  };
  const watch = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => { if (!drag && !closed) setDetent(detent); });

  function close(fromUi = true) {
    if (closed) return;
    closed = true; stack.splice(stack.indexOf(api), 1);
    document.removeEventListener('keydown', onKey); if (watch) watch.disconnect();
    if (unInert) unInert();
    host.style.removeProperty('--toast-b');
    if (ownEntry && fromUi && history.state && history.state.sheet === uid) { ownBack++; history.back(); }
    const key = opener && opener.dataset && opener.dataset.key, back = opener && opener.isConnected ? opener : key && document.querySelector('[data-key="' + key + '"]');
    wrap.inert = true;
    if (back) back.focus({ preventScroll: true });
    if (onClose) onClose(fromUi);
    if (reducedMotion()) wrap.remove(); else { wrap.dataset.leaving = ''; setTimeout(() => wrap.remove(), 160); }
  }

  const api = { el, setDetent, close, entry: own };
  host.append(wrap); translate(wrap);
  el.dataset.drag = ''; setDetent(detent); void el.offsetHeight; delete el.dataset.drag; // the first height is set, not animated
  stack.push(api);
  document.addEventListener('keydown', onKey); if (watch) watch.observe(wrap);
  if (own) { history.pushState({ sheet: uid }, ''); ownEntry = true; }
  const first = el.querySelector('[autofocus]') || heading; first.focus({ preventScroll: true });
  return api;
}
