// DOM helpers shared by the phone pages: a scrolling row with faded edges (no scrollbar), and a two line lede with a More button.
import { h } from './dom.js';
import { edgeOf, centerLeft } from './phone-pages-model.js';

const CURRENT = '[aria-current="page"], [aria-current="true"], [aria-selected="true"], [aria-pressed="true"]';

// Makes `el` (chips or tabs in one row) fade the edge that has more behind it, and brings the current item to the middle once it has a width.
export function edgeRow(el) {
  let placed = false;
  const sync = () => { el.dataset.edge = edgeOf({ left: el.scrollLeft, client: el.clientWidth, scroll: el.scrollWidth }); };
  el.addEventListener('scroll', sync, { passive: true });
  if (typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(() => {
      const cur = el.querySelector(CURRENT);
      if (!placed && cur && el.clientWidth) { placed = true; el.scrollLeft = centerLeft({ offset: cur.offsetLeft, width: cur.offsetWidth, client: el.clientWidth, scroll: el.scrollWidth }); }
      sync();
    }).observe(el);
  }
  return el;
}

// The lede under a page's state sentence: two lines, and a 44 px More beside them when the text is longer than that.
export function lede(text) {
  const p = h('p', { class: 'ax-lede-t' }, text);
  const more = h('button', { class: 'ax-more', type: 'button', hidden: true, 'aria-expanded': 'false', onclick: () => { const open = row.dataset.open !== 'true'; row.dataset.open = String(open); more.textContent = open ? 'Less' : 'More'; more.setAttribute('aria-expanded', String(open)); } }, 'More');
  const row = h('div', { class: 'ax-lede-row' }, p, more);
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => { if (row.dataset.open !== 'true') more.hidden = p.scrollHeight <= p.clientHeight + 1; }).observe(p);
  return row;
}

// A sheet closes by stepping history back, which would undo a navigation started in the same tick, so `go` waits for that step.
export function closeThen(sheet, go) {
  if (history.state && history.state.sheet) { addEventListener('popstate', () => go(), { once: true }); sheet.close(); } else { sheet.close(); go(); }
}
