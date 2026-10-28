// One popup and one picker for the whole app: a button that opens a listbox (or any small panel) in the top layer, so no scroller clips it.
// The picker follows the W3C APG listbox keys: arrows, Home/End, PageUp/PageDown, type-ahead, Enter and Space pick, Escape closes and returns focus.
// Above eight items it gains a search field (an editable combobox: focus stays in the field, the active row is aria-activedescendant).
import { h, clear, trapTab } from './dom.js';
import { icon } from './icons.js';
import * as store from './store.js';
import { translate } from './i18n.js';

const T = (en, it) => (store.get('lang') === 'it' ? it : en);
let cur = null; // the single open popup: { key, trigger, pop, close, place }
let uid = 0;

export const closePopup = (restore = true) => { if (cur) cur.close(restore); };

// Open a panel next to `trigger`. build(pop, close) fills it and returns the element to focus.
export function openPopup({ key, trigger, up, end, build, label, labelledby }) {
  closePopup(false);
  const pop = h('div', { class: 'pkpop', popover: 'manual', role: 'dialog', 'aria-label': label || null, 'aria-labelledby': labelledby || null });
  const state = { key, trigger, pop };
  const place = () => {
    const t = state.trigger;
    if (!t || !t.isConnected) return;
    const app = (document.getElementById('app') || document.body).getBoundingClientRect(), r = t.getBoundingClientRect();
    const w = Math.min(Math.max(r.width, 320), app.width - 16), below = innerHeight - r.bottom - 12, above = r.top - 12;
    const goUp = up ? above >= 220 || above > below : below < 220 && above > below;
    pop.style.width = w + 'px';
    pop.style.left = Math.min(Math.max((end ?? r.left + r.width / 2 > app.left + app.width * 0.6) ? r.right - w : r.left, app.left + 8), Math.max(app.left + 8, app.right - 8 - w)) + 'px';
    pop.style.maxHeight = Math.min(Math.max(168, goUp ? above : below), 460) + 'px';
    pop.style.top = goUp ? 'auto' : r.bottom + 6 + 'px';
    pop.style.bottom = goUp ? innerHeight - r.top + 6 + 'px' : 'auto';
    pop.dataset.up = goUp ? '1' : '0';
  };
  const away = (e) => { if (!pop.contains(e.target) && !(state.trigger && state.trigger.contains(e.target))) close(false); };
  const onScroll = (e) => { if (!pop.contains(e.target)) place(); };
  const onResize = () => close(false);
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); }
    else if (e.key === 'Tab' && pop.dataset.kind === 'list') close(true); // a listbox has one tab stop: Tab leaves it, from the trigger
    else trapTab(e, pop);
  };
  function close(restore) {
    document.removeEventListener('pointerdown', away, true);
    removeEventListener('resize', onResize); removeEventListener('hashchange', onResize);
    removeEventListener('scroll', onScroll, true);
    try { pop.hidePopover(); } catch (e) { /* already closed */ }
    pop.remove();
    if (cur === state) cur = null;
    const t = document.querySelector('[data-key="' + key + '"]') || state.trigger;
    if (t) { t.setAttribute('aria-expanded', 'false'); if (restore) t.focus({ preventScroll: true }); }
  }
  state.close = close; state.place = place;
  (document.querySelector('.app') || document.body).append(pop); // inside .app: the type and target tokens are defined there
  const first = build(pop, (r) => close(r !== false));
  translate(pop);
  pop.addEventListener('keydown', onKey);
  place(); pop.showPopover();
  trigger.setAttribute('aria-expanded', 'true');
  cur = state;
  document.addEventListener('pointerdown', away, true);
  addEventListener('resize', onResize); addEventListener('hashchange', onResize);
  addEventListener('scroll', onScroll, true);
  if (first) first.focus({ preventScroll: true });
  return state;
}

// A button that opens a panel built by build(pop, close). Re-created on a redraw, an open panel is re-attached to the new button.
export function popButton({ key, label, text, glyph, cls, up, end, build, title }) {
  const btn = h('button', { class: 'pk ' + (cls || ''), type: 'button', 'data-key': key, 'aria-haspopup': 'dialog', 'aria-expanded': cur && cur.key === key ? 'true' : 'false', 'aria-label': label, title: title || null,
    onclick: () => { if (cur && cur.key === key) closePopup(true); else openPopup({ key, trigger: btn, up, end, build, label }); } },
  glyph ? icon(glyph, 20) : null, text ? h('span', { class: 'pk-t' }, text) : null);
  if (cur && cur.key === key) cur.trigger = btn;
  return btn;
}

// items: [{ value, label, meta?, badge?, group? }] (a group's items are consecutive). Returns the trigger button; button.update({ items, value, text }) changes it in place.
export function picker(o) {
  const P = { searchAt: 8, ...o }, id = 'pk' + (++uid);
  const sel = () => P.items.find((i) => i.value === P.value);
  const btn = h('button', { class: 'pk ' + (P.cls || ''), type: 'button', 'data-key': P.key, 'aria-haspopup': 'listbox', 'aria-disabled': P.disabled ? 'true' : null, 'aria-expanded': cur && cur.key === P.key ? 'true' : 'false',
    onclick: () => { if (P.disabled) return; if (cur && cur.key === P.key) closePopup(true); else openPopup({ key: P.key, trigger: btn, up: P.up, label: P.label, build }); } });
  const paint = () => {
    clear(btn).append(...[P.prefix ? h('span', { class: 'pk-p' }, P.prefix) : '', h('span', { class: 'pk-t' }, P.text || (sel() ? sel().label : '')), h('span', { class: 'pk-v' }, icon('chevron', 16))].filter(Boolean));
    btn.setAttribute('aria-label', P.label + ': ' + (P.text || (sel() ? sel().label : '')));
  };
  btn.update = (n) => { Object.assign(P, n); paint(); };
  paint();
  if (cur && cur.key === P.key) cur.trigger = btn;

  function build(pop, close) {
    const searchable = P.items.length > P.searchAt, lid = id + '-list';
    const q = searchable ? h('input', { type: 'search', class: 'pk-q', role: 'combobox', 'aria-expanded': 'true', 'aria-controls': lid, 'aria-autocomplete': 'list', autocomplete: 'off', placeholder: T('Search', 'Cerca'), 'aria-label': T('Search', 'Cerca') + ' ' + P.label.toLowerCase() }) : null;
    const list = h('div', { class: 'pk-list', role: 'listbox', id: lid, 'aria-label': P.label, tabindex: searchable ? null : '0' });
    const focusEl = q || list;
    let rows = [], act = 0, typed = '', typedAt = 0;
    const setAct = (n, scroll = true) => {
      if (!rows.length) { focusEl.removeAttribute('aria-activedescendant'); return; }
      act = (n + rows.length) % rows.length;
      rows.forEach((r, i) => { if (i === act) r.el.setAttribute('data-act', ''); else r.el.removeAttribute('data-act'); });
      focusEl.setAttribute('aria-activedescendant', rows[act].el.id);
      if (scroll) rows[act].el.scrollIntoView({ block: 'nearest' });
    };
    const choose = (i) => { if (i.disabled) return; if (P.onPick) P.onPick(i.value); close(true); };
    const draw = () => {
      clear(list); rows = [];
      const needle = q ? q.value.trim().toLowerCase() : '';
      let gname, box = list;
      P.items.filter((i) => !needle || (i.label + ' ' + (i.meta || '')).toLowerCase().includes(needle)).forEach((i) => {
        if (i.group !== gname) {
          gname = i.group;
          if (gname) { const gid = id + '-g' + rows.length; box = h('div', { role: 'group', 'aria-labelledby': gid }, h('div', { class: 'pk-gh', id: gid }, gname)); list.append(box); } else box = list;
        }
        const on = i.value === P.value;
        const el = h('div', { class: 'pk-o', role: 'option', id: id + '-o' + rows.length, 'aria-selected': on ? 'true' : 'false', 'aria-disabled': i.disabled ? 'true' : null, 'data-value': i.value, onmousedown: (e) => e.preventDefault(), onclick: () => choose(i), onmousemove: () => { const n = rows.findIndex((r) => r.el === el); if (n !== act) setAct(n, false); } },
          h('span', { class: 'pk-l' }, i.label), i.meta ? h('span', { class: 'pk-m' }, i.meta) : null, i.badge ? h('span', { class: 'pk-b' }, i.badge) : null, h('span', { class: 'pk-c' }, on ? icon('check', 18) : null));
        box.append(el); rows.push({ el, i });
      });
      if (!rows.length) list.append(h('p', { class: 'pk-none' }, T('Nothing matches.', 'Nessun risultato.')));
      translate(list);
      const at = rows.findIndex((r) => r.i.value === P.value);
      setAct(needle ? 0 : at < 0 ? 0 : at);
    };
    pop.classList.add('pk-pop');
    pop.append(...[q ? h('div', { class: 'pk-qw' }, q) : '', list].filter(Boolean));
    pop.dataset.kind = 'list';
    draw();
    if (q) q.addEventListener('input', draw);
    focusEl.addEventListener('keydown', (e) => {
      const k = e.key;
      if (k === 'ArrowDown') { e.preventDefault(); setAct(act + 1); }
      else if (k === 'ArrowUp') { e.preventDefault(); setAct(act - 1); }
      else if (k === 'PageDown') { e.preventDefault(); setAct(Math.min(rows.length - 1, act + 8)); }
      else if (k === 'PageUp') { e.preventDefault(); setAct(Math.max(0, act - 8)); }
      else if ((k === 'Home' || k === 'End') && !q) { e.preventDefault(); setAct(k === 'Home' ? 0 : rows.length - 1); }
      else if (k === 'Enter' || (k === ' ' && !q)) { e.preventDefault(); if (rows[act]) choose(rows[act].i); }
      else if (!q && k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const now = Date.now(); typed = now - typedAt > 600 ? k.toLowerCase() : typed + k.toLowerCase(); typedAt = now;
        const from = typed.length === 1 ? act + 1 : act, n = rows.length;
        for (let d = 0; d < n; d++) { const r = rows[(from + d) % n]; if (r.i.label.toLowerCase().startsWith(typed)) { setAct((from + d) % n); break; } }
      }
    });
    return focusEl;
  }
  return btn;
}
