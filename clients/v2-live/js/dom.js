// Tiny element builder. Text is always set as text, never as markup.
const SVGNS = 'http://www.w3.org/2000/svg';

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  fill(el, attrs, kids);
  return el;
}

export function s(tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  fill(el, attrs, kids);
  return el;
}

function fill(el, attrs, kids) {
  for (const k in attrs || {}) {
    const v = attrs[k];
    if (v == null || v === false) continue;
    if (k === 'class') el.setAttribute('class', v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of kids.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
}

export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };

export function trapTab(e, root) {
  if (e.key !== 'Tab') return;
  const controls = [...root.querySelectorAll('a[href], button, input, select, textarea, [tabindex="0"]')].filter((el) => !el.disabled && el.getClientRects().length);
  const first = controls[0], last = controls[controls.length - 1];
  if (e.shiftKey ? document.activeElement === first || !root.contains(document.activeElement) : document.activeElement === last || !root.contains(document.activeElement)) {
    e.preventDefault();
    const next = e.shiftKey ? last : first;
    if (next) next.focus();
  }
}
