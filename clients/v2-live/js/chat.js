// The chat surfaces (S4): the full Chat page, the bar docked on Now, and the phone chat sheet. One composer per place, cached across renders so
// typing, focus and the caret survive a redraw. The slash menu is a combobox: focus stays in the field, the menu never takes it.
import { h, clear } from './dom.js';
import { picker, popButton } from './picker.js';
import { icon, glyph } from './icons.js';
import * as store from './store.js';
import { isPhone } from './viewport.js';
import { createChat } from '../chat-engine.js';
import * as SL from '../slash.js';
import { clockLabel } from '../sim.js';
import { hrefFor } from './ax.js';
import { spineOf, isOpenMission } from '../spine-model.js';
import { present } from '../core-words.js';
import { L, C, lang, msgNode, cardNode, clsChip, clsLabel } from './chat-cards.js';

export function S4(ctx) {
  const ui = ctx.ui;
  if (!ui.s4) {
    const eng = createChat(ctx.sim, {});
    eng.onChange = () => ctx.render();
    ui.s4 = { eng, dest: 'work', project: 'archeus', recents: SL.clean(store.get('slashrecent')), cpins: SL.clean(store.get('slashpins')), comps: {}, sheet: false, exp: false, kb: false, slow: false, fail: false, touched: false, pinned: true, unread: 0, notice: null, seen: 0 };
  }
  return ui.s4;
}
// From this main-area width the Chat page shows a side pane (Receipts and Context) beside the thread instead of tabs over it.
const WIDE = 1100, wideNow = () => (document.querySelector('.main-col')?.clientWidth || 0) >= WIDE;
const hoverDevice = () => !!(window.matchMedia && window.matchMedia('(hover: hover)').matches);

// ---------- what a card button or a retry does ----------
function actions(ctx) {
  const s = S4(ctx);
  return {
    act(id, what, data) { const r = s.eng.card(id, what, data); if (!r.ok) ctx.toast(L('Not done: {r}', 'Non fatto: {r}', { r: r.reason })); ctx.render(); if (r.nav) ctx.nav(r.nav); return r; },
    unqueue(id) { s.eng.unqueue(id); ctx.render(); },
    retry(id) { const r = s.eng.retry(id); if (r) setTimeout(() => { settle(ctx, s.eng.finish(id)); }, 500); ctx.render(); }
  };
}
function settle(ctx, f) {
  if (!f) return;
  if (f.pref) { const [k, v] = f.pref; store.set(k, k === 'theme' && v === 'contrast' ? (store.get('theme').startsWith('light') ? 'light-hc' : 'dark-hc') : v); }
  if (f.nav) { const s = S4(ctx); if (s.sheet) { s.sheet = false; } if (f.tab) ctx.ui.tab = f.tab; ctx.nav(f.nav); return; }
  ctx.render();
}

// Stop is a distinct, stable control: it only proposes the emergency stop; the card asks twice.
export function stopNow(ctx) {
  const s = S4(ctx), r = s.eng.send('/estop', { dest: 'work', project: s.project, force: true });
  s.touched = true; if (isPhone()) s.sheet = true;
  if (r.run) setTimeout(() => settle(ctx, s.eng.finish(r.id)), 500);
  ctx.render();
}

// ---------- the thread (shared by the page, the dock strip and the sheet) ----------
export function threadNode(ctx, opts = {}) {
  const s = S4(ctx), A = actions(ctx);
  let list = s.eng.thread();
  if (opts.last) { const out = []; for (let i = list.length - 1; i >= 0 && out.length < 2; i--) { out.unshift(list[i]); if (list[i].from === 'you') break; } list = out; }
  const log = h('div', { class: 'msgs ' + (opts.cls || ''), role: 'log', 'aria-live': 'polite', 'aria-label': L('Conversation', 'Conversazione'), tabindex: opts.last ? null : '0' },
    s.eng.hidden() ? h('p', { class: 'cut' }, L('Earlier messages hidden on this screen. History kept.', 'Messaggi precedenti nascosti su questo schermo. La cronologia resta.')) : null,
    ...list.map((m) => msgNode(ctx, m, A.act, A.retry, A.unqueue)),
    !list.length ? h('p', { class: 'intro' }, L('Ask a question, capture an idea, or describe work.', 'Fai una domanda, cattura un\'idea o descrivi un lavoro.')) : null);
  if (!opts.last) {
    log.addEventListener('scroll', () => { s.pinned = log.scrollHeight - log.scrollTop - log.clientHeight < 24; if (s.pinned) { s.unread = 0; const b = log.parentElement && log.parentElement.querySelector('.newreply'); if (b) b.hidden = true; } });
    ctx.mounts.push(() => {
      const n = s.eng.thread().length;
      if (s.pinned || n <= s.seen) log.scrollTop = log.scrollHeight; else { s.unread += n - s.seen; const b = log.parentElement && log.parentElement.querySelector('.newreply'); if (b) { b.hidden = false; } }
      s.seen = n;
    });
  }
  return log;
}
const newReply = (log) => h('button', { class: 'btn newreply', type: 'button', hidden: true, onclick: (e) => { log.scrollTop = log.scrollHeight; e.currentTarget.hidden = true; } }, L('New reply', 'Nuova risposta'));

// ---------- the scope picker: General or a project. It is the conversation list: projects that wait for you come first, a long list is searchable ----------
const scopeValue = (s) => (s.dest === 'general' ? 'general' : 'work:' + s.project);
function scopeItems(ctx) {
  const st = ctx.sim.state, need = new Set(Object.values(st.approvals).filter((a) => a.state === 'PENDING').map((a) => a.project));
  const row = (p, group) => ({ value: 'work:' + p.id, label: p.name, group });
  return [{ value: 'general', label: L('General', 'Generale'), meta: L('Not project memory', 'Non è memoria di progetto') }].concat(
    st.projects.filter((p) => need.has(p.id)).map((p) => row(p, L('Needs you', 'Richiede te'))), st.projects.filter((p) => !need.has(p.id)).map((p) => row(p, L('Projects', 'Progetti'))));
}
function scopePicker(ctx, key, o) {
  const s = S4(ctx);
  return picker({ key, label: L('Destination', 'Destinazione'), prefix: o.prefix, cls: o.cls, up: o.up, value: scopeValue(s), items: scopeItems(ctx),
    onPick: (v) => { if (v === 'general') s.dest = 'general'; else { s.dest = 'work'; s.project = v.slice(5); } if (s.onScope) s.onScope(); ctx.render(); } });
}

// ---------- the composer: destination, field, slash combobox ----------
let uid = 0;
export function composer(ctx, where) {
  const s = S4(ctx);
  if (s.comps[where]) { s.comps[where].refresh(); return s.comps[where].root; }
  const id = 'cmp' + (++uid);
  const M = { open: false, rows: [], active: 0, expanded: false, mode: 'off', cut: 0 };
  const input = h('input', { type: 'text', class: 'cinput', role: 'combobox', autocomplete: 'off', maxlength: 300, 'aria-autocomplete': 'list', 'aria-expanded': 'false', 'aria-controls': id + '-list', 'data-key': 'chat-in-' + where, id: id + '-in' });
  const list = h('div', { class: 'slash', role: 'listbox', id: id + '-list', hidden: true });
  const argline = h('p', { class: 'argline', hidden: true });
  const notice = h('div', { class: 'cnote', role: 'status', hidden: true });
  const live = h('p', { class: 'vh', role: 'status', 'aria-live': 'polite' });
  const dest = h('p', { class: 'cdest' });
  const shint = h('p', { class: 'shint', hidden: true });
  const hint = h('p', { class: 'chint', 'aria-live': 'polite', hidden: true });
  const foot = h('div', { class: 'cfoot' }, dest, where === 'dock' ? null : hint);
  const scope = scopePicker(ctx, 'chat-scope-' + where, { cls: 'cscope', prefix: L('To', 'A'), up: true });
  const slashBtn = h('button', { class: 'btn cslash', type: 'button', 'aria-label': 'Commands', onclick: () => { input.value = '/'; ctx.ui.draft = '/'; input.focus(); onInput(); } }, '/');
  const send = h('button', { class: 'btn primary csend', type: 'button', onclick: () => submit() }, '');
  const stop = h('button', { class: 'btn danger cstop', type: 'button', onclick: () => stopNow(ctx) }, '');
  const maxRows = () => { const hgt = (document.getElementById('app') || {}).clientHeight || 800; return where === 'sheet' ? (hgt < 700 ? 2 : 3) : hgt < 760 ? 3 : 5; };
  const root = h('div', { class: 'composer2', 'data-where': where }, notice, argline, list, shint, live, h('div', { class: 'crow2' }, scope, input, where === 'dock' ? hint : null, slashBtn, send, where === 'sheet' ? null : stop), foot);

  function fillDest() {
    const a = SL.parse(input.value || '');
    const pn = (ctx.sim.state.projects.find((p) => p.id === s.project) || { name: s.project }).name;
    dest.textContent = a && a.kind === 'command' ? L('Command · /{n} · {c}', 'Comando · /{n} · {c}', { n: SL.nameIn(a.cmd, lang()), c: clsLabel(a.cmd.cls) })
      : s.dest === 'general' ? L('Nothing here is saved to a project.', 'Qui non si salva nulla in un progetto.')
        : L('Replies and records stay in {p}.', 'Risposte e record restano in {p}.', { p: pn });
    scope.update({ value: scopeValue(s), items: scopeItems(ctx), prefix: L('To', 'A'), label: L('Destination', 'Destinazione') });
  }
  // While a mission runs in this scope: the two keys, and how many messages wait for the step. Hidden otherwise.
  const mod = /Mac|iPhone|iPad/.test(navigator.platform || '') ? '⌘' : 'Ctrl+';
  function drawHint() {
    const live = s.dest === 'work' && s.eng.running(s.project).length, n = s.dest === 'work' ? s.eng.queued(s.project).length : 0;
    hint.hidden = !live && !n;
    hint.textContent = [live ? L('Enter queue · {k}Enter steer', 'Invio accoda · {k}Invio guida', { k: mod }) : '', n ? L('{n} queued', '{n} in coda', { n }) : ''].filter(Boolean).join(' · ');
  }
  function refresh() {
    input.placeholder = L('Tell Archeus what to do…', 'Dì ad Archeus cosa fare…'); input.setAttribute('aria-label', L('Message to Archeus', 'Messaggio ad Archeus'));
    slashBtn.setAttribute('aria-label', L('Commands', 'Comandi')); slashBtn.title = L('Commands (type /)', 'Comandi (scrivi /)'); send.title = L('Send (Enter)', 'Invia (Invio)');
    drawHint();
    send.textContent = L('Send', 'Invia'); stop.textContent = L('Stop', 'Ferma'); stop.setAttribute('aria-label', L('Stop: propose an emergency stop', 'Ferma: proponi un arresto d\'emergenza'));
    if (document.activeElement !== input && input.value !== (ctx.ui.draft || '')) input.value = ctx.ui.draft || '';
    fillDest(); draw();
  }

  // ----- the combobox -----
  // A pinned command is never folded behind "+N more"; the headings (Pinned, Recent, then the classes) only show with an empty query.
  function cmdRows(mf) {
    const lim = M.expanded ? Infinity : maxRows(), pin = new Set(s.cpins), rows = [];
    let shown = 0;
    (mf.groups || [{ key: '', items: mf.items }]).forEach((g) => {
      const vis = g.items.filter((c) => (shown < lim || pin.has(c.name)) && ++shown);
      if (!vis.length) return;
      if (g.key) rows.push({ kind: 'head', label: g.key === 'pinned' ? L('Pinned', 'Fissati') : g.key === 'recent' ? L('Recent', 'Recenti') : clsLabel(g.key) });
      vis.forEach((c) => rows.push({ kind: 'cmd', c }));
    });
    return mf.items.length > shown ? rows.concat([{ kind: 'more', n: mf.items.length - shown }]) : rows;
  }
  const sel = (r) => r.kind !== 'head' && !(r.c && r.c.unavailable);
  function rowsFor() {
    const mf = SL.menuFor(input.value, s.recents, lang(), s.cpins);
    M.mode = mf.mode; M.cut = mf.cut || 0;
    if (mf.mode === 'commands') return { rows: cmdRows(mf), mf };
    if (mf.mode === 'mention') {
      const q = mf.q.toLowerCase(), st = ctx.sim.state;
      const pool = st.projects.map((p) => ({ kind: 'ref', label: p.name, meta: L('project', 'progetto') })).concat(Object.values(st.missions).map((m) => ({ kind: 'ref', label: m.title, meta: L('mission', 'missione') })));
      const hit = pool.filter((x) => !q || x.label.toLowerCase().includes(q));
      return { rows: hit.some((x) => x.label.toLowerCase() === q) ? [] : hit.slice(0, 6), mf };
    }
    return { rows: [], mf };
  }
  function draw() {
    const { rows, mf } = rowsFor();
    M.rows = rows; if (M.active >= rows.length) M.active = 0;
    if (M.keep) { const k = rows.findIndex((r) => r.c === M.keep); if (k >= 0) M.active = k; M.keep = null; }
    while (M.active < rows.length && !sel(rows[M.active])) M.active++;
    M.open = rows.length > 0;
    const top = list.scrollTop;
    clear(list).hidden = !M.open;
    list.dataset.mode = M.mode;
    rows.forEach((r, i) => {
      if (r.kind === 'head') { list.append(h('div', { class: 'sgh', role: 'presentation' }, r.label)); return; }
      const o = h('div', { class: 'srow', role: 'option', id: id + '-o' + i, 'aria-selected': i === M.active ? 'true' : 'false', 'aria-disabled': r.c && r.c.unavailable ? 'true' : null, onmousedown: (e) => e.preventDefault(), onclick: () => { M.active = i; choose(); input.focus(); } });
      if (r.kind === 'cmd') o.append(h('span', { class: 'sn' }, '/' + SL.nameIn(r.c, lang()), h('span', { class: 'sa' }, SL.labelOf(r.c, lang()) ? ' <' + SL.labelOf(r.c, lang()) + '>' : '')), clsChip(r.c.cls), h('span', { class: 'sd' }, r.c.unavailable ? SL.descOf(r.c, lang()) + ' · ' + r.c.unavailable[lang() === 'it' ? 1 : 0] : SL.descOf(r.c, lang())), r.c.unavailable ? null : pinButton(r.c));
      else if (r.kind === 'more') o.append(h('span', { class: 'sn more' }, L('+{n} more', '+{n} altri', { n: r.n })));
      else o.append(h('span', { class: 'sn' }, '@' + r.label), h('span', { class: 'sd' }, r.meta));
      list.append(o);
    });
    const arg = mf.mode === 'arg' ? mf.cmd : null;
    argline.hidden = !arg;
    if (arg) argline.textContent = (SL.labelOf(arg, lang()) || arg.name) + (mf.empty ? ': ____' : '') + ' · ' + L('Enter sends, Esc cancels', 'Invio invia, Esc annulla');
    list.scrollTop = top;
    const cur = list.children[M.active];
    if (M.open && cur) { // the active row stays inside the scrolling list, with its heading when it is the first of a group
      const lead = cur.previousElementSibling, t = lead && lead.classList.contains('sgh') ? lead.offsetTop : cur.offsetTop, b = cur.offsetTop + cur.offsetHeight;
      if (t < list.scrollTop) list.scrollTop = t; else if (b > list.scrollTop + list.clientHeight) list.scrollTop = b - list.clientHeight;
    }
    shint.hidden = !(M.open && M.mode === 'commands' && where !== 'sheet' && hoverDevice());
    shint.textContent = shint.hidden ? '' : L('Alt+P pins or unpins the highlighted command', 'Alt+P fissa o rimuove il comando evidenziato');
    input.setAttribute('aria-expanded', M.open ? 'true' : 'false');
    if (M.open) input.setAttribute('aria-activedescendant', id + '-o' + M.active); else input.removeAttribute('aria-activedescendant');
    announce();
  }
  function pinButton(c) {
    const on = s.cpins.includes(c.name), nm = '/' + SL.nameIn(c, lang()), label = on ? L('Unpin {c}', 'Rimuovi {c} dai fissati', { c: nm }) : L('Pin {c}', 'Fissa {c}', { c: nm });
    return h('button', { class: 'spin', type: 'button', tabindex: '-1', 'aria-pressed': on ? 'true' : 'false', 'aria-label': label, title: label, onmousedown: (e) => e.preventDefault(),
      onclick: (e) => { e.stopPropagation(); togglePin(c); input.focus(); } }, icon('pin', 18));
  }
  function togglePin(c) {
    s.cpins = SL.togglePin(s.cpins, c.name); store.set('slashpins', s.cpins); M.keep = c; draw();
    lastSay = live.textContent = s.cpins.includes(c.name) ? L('Pinned {c}', 'Fissato {c}', { c: '/' + SL.nameIn(c, lang()) }) : L('Unpinned {c}', 'Rimosso {c} dai fissati', { c: '/' + SL.nameIn(c, lang()) });
  }
  let lastSay = '';
  function announce() {
    let say = '';
    if (M.open) { const r = M.rows[M.active]; say = r && r.kind === 'cmd' ? L('{n} commands. {c}: {d}, {k}', '{n} comandi. {c}: {d}, {k}', { n: M.rows.filter((x) => x.kind === 'cmd').length, c: SL.nameIn(r.c, lang()), d: SL.descOf(r.c, lang()), k: clsLabel(r.c.cls) }) : r && r.kind === 'more' ? L('{n} more commands', '{n} altri comandi', { n: r.n }) : r ? r.label : ''; }
    if (say !== lastSay) { lastSay = say; live.textContent = say; }
  }
  function choose() {
    const r = M.rows[M.active]; if (!r) return false;
    if (r.kind === 'more') { M.expanded = true; draw(); return true; }
    if (r.kind === 'ref') { const t = input.value, name = /\s/.test(r.label) ? '@"' + r.label + '"' : '@' + r.label; input.value = t.slice(0, M.cut) + name + ' '; ctx.ui.draft = input.value; draw(); return true; }
    if (r.c.unavailable) return true;
    const n = SL.nameIn(r.c, lang());
    if (r.c.arg === 'req') { input.value = '/' + n + ' '; ctx.ui.draft = input.value; M.expanded = false; draw(); fillDest(); return true; }
    input.value = '/' + n; ctx.ui.draft = input.value; M.open = false; submit(); return true;
  }
  function onInput() { ctx.ui.draft = input.value; M.active = 0; M.expanded = false; notice.hidden = true; fillDest(); draw(); }
  input.addEventListener('input', onInput);
  input.addEventListener('focus', () => { if (where === 'sheet' && hoverDevice()) { s.kb = true; const sh = root.closest('.chatsheet'); if (sh) sh.dataset.kb = '1'; } });
  input.addEventListener('keydown', (e) => {
    if (e.isComposing || e.keyCode === 229) return;
    const n = M.rows.length;
    const walk = (d, steps) => { for (let k = 0; k < steps; k++) { let j = M.active; do j += d; while (j >= 0 && j < n && !sel(M.rows[j])); if (j < 0 || j >= n) break; M.active = j; } draw(); };
    if (M.open && e.altKey && e.code === 'KeyP') { const r = M.rows[M.active]; e.preventDefault(); if (r && r.kind === 'cmd' && !r.c.unavailable) togglePin(r.c); }
    else if (M.open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); const d = e.key === 'ArrowDown' ? 1 : n - 1; do M.active = (M.active + d) % n; while (!sel(M.rows[M.active])); draw(); }
    else if (M.open && (e.key === 'PageDown' || e.key === 'PageUp')) { e.preventDefault(); walk(e.key === 'PageDown' ? 1 : -1, 5); }
    else if (M.open && (e.key === 'Home' || e.key === 'End')) { e.preventDefault(); M.active = e.key === 'Home' ? -1 : n; walk(e.key === 'Home' ? 1 : -1, 1); }
    else if (M.open && e.key === 'Tab' && !e.shiftKey) { const r = M.rows[M.active]; if (r && r.kind === 'cmd' && !r.c.unavailable) { e.preventDefault(); input.value = '/' + SL.nameIn(r.c, lang()) + ' '; ctx.ui.draft = input.value; M.expanded = false; draw(); fillDest(); } else if (r && r.kind === 'ref') { e.preventDefault(); choose(); } }
    else if (e.key === 'Enter') { e.preventDefault(); if (M.open) choose(); else submit(false, e.metaKey || e.ctrlKey ? 'steer' : 'queue'); }
    else if (e.key === 'Escape') { if (M.open) { e.preventDefault(); e.stopPropagation(); M.open = false; clear(list).hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); } else if (!argline.hidden) { argline.hidden = true; e.stopPropagation(); } }
  });

  // ----- sending -----
  function showNotice(r) {
    clear(notice); notice.hidden = false;
    if (r.dup) { notice.append(h('span', null, L('You sent this {n} s ago. Send again?', 'Hai inviato questo {n} s fa. Rimandare?', { n: r.dup.secs })), h('span', { class: 'actions' }, h('button', { class: 'btn', type: 'button', onclick: () => { notice.hidden = true; submit(true); } }, L('Send again', 'Rimanda')), h('button', { class: 'btn quiet', type: 'button', onclick: () => { notice.hidden = true; } }, L('Cancel', 'Annulla')))); return; }
    if (r.notice) { notice.append(h('span', null, C(r.notice))); if (r.href) notice.append(h('a', { class: 'btn', href: r.href }, L('Open', 'Apri'))); return; }
    notice.hidden = true;
  }
  function run(text, force, mode) {
    const o = { dest: s.dest, project: s.project, force: !!force, fail: s.fail, mode: mode || 'queue', mission: where === 'page' && s.page ? s.page.mission : null };
    const slow = s.slow; s.fail = false; s.slow = false;
    const r = s.eng.send(text, o);
    if (!r.ok) { if (r.menu) { input.value = '/'; draw(); return r; } if (r.arg) { M.mode = 'arg'; draw(); return r; } showNotice(r); return r; }
    s.touched = true; s.pinned = true;
    if (r.queued || r.steering) live.textContent = r.queued ? L('Queued. It is handled after the current step.', 'In coda. Viene gestito dopo il passo corrente.') : L('Steering. Waiting for Core to acknowledge; this is simulated.', 'Guida in corso. In attesa che il Core confermi; è simulato.');
    if (text === input.value) { input.value = ''; ctx.ui.draft = ''; }
    notice.hidden = true; M.open = false;
    if (r.cmd && !r.failed) { s.recents = SL.pushRecent(s.recents, r.cmd); store.set('slashrecent', s.recents); }
    if (r.run) setTimeout(() => settle(ctx, s.eng.finish(r.id)), slow ? 3000 : 500);
    else if (r.done) setTimeout(() => settle(ctx, r.out), 0);
    ctx.render();
    return r;
  }
  function submit(force, mode) { return run(input.value, force, mode); }

  const comp = { root, input, refresh, run, draw, setText(t) { input.value = t; ctx.ui.draft = t; fillDest(); draw(); input.focus(); } };
  s.comps[where] = comp; refresh();
  return root;
}

// ---------- the Chat page ----------
// One thread. Scope (General or a project) is chosen in the composer or the bar above the thread: that picker is the history. The bar holds the
// mission filter, the mission's state in one line, a link to what waits for you, and a menu for privacy and the simulation switches.
function chatPageEntries(s, st) {
  let project = 'archeus', mission = null, general = false;
  return s.eng.thread().map((m) => {
    const own = m.from !== 'you' && m.project !== undefined;
    if (m.from === 'you') { project = m.project || 'archeus'; general = m.dest === 'general'; mission = s.eng.originOf(m).mission; }
    const ref = m.card?.mission || st.approvals[m.card?.approval]?.mission || (own ? m.mission : mission);
    return { m, project: m.project || project, mission: ref, general: m.general || m.dest === 'general' || (m.from !== 'you' && !own && general) };
  });
}

const missionItems = (st, project, pending) => {
  const need = new Set(pending.map((a) => a.mission)), all = Object.values(st.missions).filter((m) => m.project === project);
  const row = (m, group) => ({ value: m.id, label: m.title, meta: present('mission', m.state).label, group });
  return [{ value: '', label: L('All missions', 'Tutte le missioni') }].concat(
    all.filter((m) => need.has(m.id)).map((m) => row(m, L('Needs you', 'Richiede te'))),
    all.filter((m) => !need.has(m.id) && isOpenMission(m)).map((m) => row(m, L('Open', 'Aperte'))),
    all.filter((m) => !need.has(m.id) && !isOpenMission(m)).map((m) => row(m, L('Closed', 'Chiuse'))));
};

const spineDots = (m) => { const sp = spineOf(m.state, m.held_from); return h('span', { class: 'cb-spine', role: 'img', 'aria-label': sp.text }, ...sp.marks.map((k) => h('i', { 'data-k': k.kind, 'data-c': k.cls || null }))); };
const spineLine = (m) => { const sp = spineOf(m.state, m.held_from); return h('span', { class: 'cb-state' }, spineDots(m), h('span', null, present('mission', m.state).label + (sp.station ? L(' · step {n} of 6', ' · passo {n} di 6', { n: sp.station }) : ''))); };
// Relative time on the simulation clock; the exact time is the tooltip.
const ago = (ms) => { const m = Math.floor(ms / 60000); return m < 1 ? L('just now', 'adesso') : m < 60 ? L('{n} min ago', '{n} min fa', { n: m }) : L('{n} h ago', '{n} h fa', { n: Math.floor(m / 60) }); };
const stamp = (st, at) => h('time', { class: 'cp-tm', title: clockLabel(at, true) }, ago(st.clock - at));
const STEPS = /^mission\.(state_changed|steer_requested|steer_acknowledged)$/;
const STEER = { 'mission.steer_requested': () => L('Steer asked (simulated)', 'Guida richiesta (simulata)'), 'mission.steer_acknowledged': () => L('Steer acknowledged (simulated)', 'Guida confermata (simulata)') };
const TABS = [['chat', 'Conversation', 'Conversazione'], ['receipts', 'Receipts', 'Ricevute'], ['context', 'Context', 'Contesto']];

export function viewChat(ctx) {
  const s = S4(ctx), st = ctx.sim.state;
  const P = s.page || (s.page = { seen: new Set(), mission: null, switched: false, scroll: 0, bottom: true, tab: 'chat', all: false });
  if (P.messages && P.messages !== st.messages) { P.seen.clear(); P.mission = null; P.lastYou = null; P.bottom = true; }
  P.messages = st.messages;
  s.onScope = () => { P.mission = null; P.switched = true; P.scroll = 0; P.bottom = true; };
  const comp = composer(ctx, 'page'), A = actions(ctx), entries = chatPageEntries(s, st), general = s.dest === 'general';
  const lastYou = entries.filter((e) => e.m.from === 'you').at(-1)?.m.id;
  if (P.lastYou && P.lastYou !== lastYou) P.mission = null;
  P.lastYou = lastYou;
  const oldCards = new Map([...document.querySelectorAll('.chatpage .msg')].map((el) => [el.dataset.key, el.querySelector('.ccard')?.getBoundingClientRect().height]));
  const project = st.projects.find((p) => p.id === s.project);
  const focused = !general && st.missions[P.mission]?.project === s.project ? st.missions[P.mission] : null;
  const visible = entries.filter((e) => general ? e.general : !e.general && e.project === s.project && (!focused || e.mission === focused.id));
  const pending = Object.values(st.approvals).filter((a) => a.state === 'PENDING'), here = general ? [] : pending.filter((a) => a.project === s.project);
  const open = general ? [] : Object.values(st.missions).filter((m) => m.project === s.project && isOpenMission(m));

  // ----- the bar above the thread -----
  const scopeHead = scopePicker(ctx, 'chat-scope-head', { cls: 'cb-scope' });
  const missionPick = general ? null : picker({ key: 'chat-mission', label: L('Mission', 'Missione'), cls: 'cb-mission', value: focused ? focused.id : '', items: missionItems(st, s.project, pending), text: focused ? focused.title : L('All missions', 'Tutte le missioni'),
    onPick: (v) => { P.mission = v || null; P.switched = true; P.bottom = true; ctx.render(); } });
  const summary = general ? L('Not project memory', 'Non è memoria di progetto')
    : focused ? null : open.length ? L('{n} open', '{n} aperte', { n: open.length }) : L('Nothing open', 'Niente di aperto');
  const more = popButton({ key: 'chat-more', label: L('More', 'Altro'), glyph: 'more', cls: 'cb-more', end: true, title: L('More', 'Altro'), build: (pop) => {
    const fix = (key, label) => {
      const on = h('span', { class: 'fx-on' }, s[key] ? icon('check', 16) : null);
      const b = h('button', { class: 'btn quiet', type: 'button', 'aria-pressed': s[key] ? 'true' : 'false', onclick: () => { s[key] = !s[key]; b.setAttribute('aria-pressed', s[key] ? 'true' : 'false'); clear(on).append(...(s[key] ? [icon('check', 16)] : [])); } }, on, label);
      return b;
    };
    pop.classList.add('cb-menu');
    const first = fix('slow', L('Slow reply (3 s)', 'Risposta lenta (3 s)'));
    pop.append(h('h3', { class: 'pk-gh' }, L('Privacy and storage', 'Privacy e conservazione')),
      h('p', { class: 'cb-note' }, L('Retention: Unknown. “Not project memory” does not mean “not stored”. Account selected by Core. Usage: Unknown.', 'Conservazione: Sconosciuta. “Non è memoria di progetto” non vuol dire “non archiviato”. Account scelto dal Core. Utilizzo: Sconosciuto.')),
      h('h3', { class: 'pk-gh' }, L('Simulation fixtures', 'Scenari di simulazione')), h('div', { class: 'cb-fix' }, first, fix('fail', L('Failed send', 'Invio fallito'))));
    return first;
  } });
  const tab = P.tab;
  const bar = h('header', { class: 'cb' }, h('h1', { class: 'vh' }, L('Chat', 'Chat')), scopeHead, missionPick,
    focused ? spineLine(focused) : summary ? h('span', { class: 'cb-sum' }, summary) : null,
    h('span', { class: 'cb-gap' }),
    here.length ? h('a', { class: 'btn cb-need', href: '#/work/' + here[0].id, 'data-key': 'chat-needs' }, glyph('needs_you'), L('Needs you · {n}', 'Richiede te · {n}', { n: here.length })) : null, more);
  const wide = P.wide = wideNow(), cur = wide && tab === 'chat' ? 'receipts' : tab;
  const tabStrip = (list) => h('div', { class: 'cb-tabs', role: 'tablist', 'aria-label': L('Chat sections', 'Sezioni della chat') }, ...list.map(([id, en, it]) => h('button', { class: 'cb-tab', type: 'button', role: 'tab', id: 'cbt-' + id, 'aria-selected': cur === id ? 'true' : 'false', 'aria-controls': 'cbp', tabindex: cur === id ? '0' : '-1', 'data-key': 'chat-tab-' + id,
    onclick: () => { P.tab = id; ctx.render(); },
    onkeydown: (e) => { const i = list.findIndex((x) => x[0] === id), n = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: list.length - 1 }[e.key]; if (n == null) return; e.preventDefault(); P.tab = list[(n + list.length) % list.length][0]; ctx.render(); } }, L(en, it))));

  // ----- the thread -----
  const log = h('div', { class: 'msgs cp-thread', role: 'log', 'aria-live': 'polite', 'aria-label': L('Conversation', 'Conversazione'), tabindex: '0' });
  if (s.eng.hidden()) log.append(h('p', { class: 'cut' }, L('Earlier messages hidden on this screen. History kept.', 'Messaggi precedenti nascosti su questo schermo. La cronologia resta.')));
  visible.forEach(({ m }) => {
    const node = msgNode(ctx, m, A.act, A.retry, A.unqueue); node.tabIndex = -1;
    if (!P.switched && P.seen.size && !P.seen.has(m.id)) node.classList.add('cp-arrive');
    log.append(node);
  });
  if (visible.length) log.classList.add('cp-pin'); else log.append(emptyNode());
  if (visible.some((e) => e.m.status === 'submitted')) log.append(h('p', { class: 'cp-working', role: 'status' }, L('Archeus is working', 'Archeus sta lavorando'), h('span', { class: 'cp-dots', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'))));
  const newer = h('button', { class: 'btn newreply', type: 'button', hidden: P.bottom || !visible.some((e) => !P.seen.has(e.m.id)), onclick: () => { P.bottom = true; log.scrollTop = log.scrollHeight; newer.hidden = true; } }, L('New reply', 'Nuova risposta'));
  log.addEventListener('scroll', () => { P.scroll = log.scrollTop; P.bottom = log.scrollHeight - log.scrollTop - log.clientHeight < 24; if (P.bottom) newer.hidden = true; });

  // What the empty thread offers: ways to start, what waits for you, what Archeus did last.
  function emptyNode() {
    const say = (t) => () => s.comps.page.setText(t);
    const cmd = (n, tail) => '/' + SL.nameIn(SL.find(n), lang()) + (tail || '');
    const starters = general ? [[L('Explain a checkpoint', 'Spiega un checkpoint'), L('Explain a checkpoint', 'Spiega un checkpoint')], [L('What can you do?', 'Cosa sai fare?'), cmd('help')]]
      : [[L('What needs me?', 'Cosa aspetta me?'), cmd('needs')], [L('Status', 'Stato'), cmd('status')], [L('Start a mission…', 'Avvia una missione…'), cmd('mission', ' ')], [L('Capture an idea…', 'Cattura un\'idea…'), cmd('idea', ' ')]];
    const seen = new Set(), last = general ? [] : st.events.filter((e) => e.project === s.project && e.type === 'mission.state_changed' && st.missions[e.subject.id] && (!focused || e.subject.id === focused.id)).reverse().filter((e) => !seen.has(e.subject.id) && seen.add(e.subject.id)).slice(0, 4);
    const waits = focused ? here.filter((a) => a.mission === focused.id) : here;
    return h('div', { class: 'cp-empty' },
      h('h2', null, general ? L('Ask anything.', 'Chiedi pure.') : L('Nothing said in {p} yet.', 'Ancora nulla detto in {p}.', { p: focused ? focused.title : project?.name || s.project })),
      h('p', { class: 'cp-sub' }, general ? L('Ask a question. No mission starts from General.', 'Fai una domanda. Da Generale non parte nessuna missione.') : L('Ask, or hand Archeus work. Replies and receipts appear here.', 'Chiedi, o affida un lavoro ad Archeus. Risposte e ricevute compaiono qui.')),
      h('div', { class: 'cp-starts' }, ...starters.map(([label, text]) => h('button', { class: 'btn cp-start', type: 'button', onclick: say(text) }, label))),
      waits.length ? h('section', { class: 'cp-sec' }, h('h3', { class: 'pk-gh' }, L('Waiting for you', 'Aspettano te')), ...waits.map((a) => h('a', { class: 'cp-line', 'data-need': '', href: '#/work/' + a.id }, glyph('needs_you'), h('span', { class: 'cp-lt' }, st.missions[a.mission]?.title || a.id), h('span', { class: 'cp-lw' }, a.kind === 'plan' ? L('Approve this plan?', 'Approvare questo piano?') : L('Allow this action?', 'Consentire questa azione?'))))) : null,
      last.length ? h('section', { class: 'cp-sec' }, h('h3', { class: 'pk-gh' }, L('Last receipts', 'Ultime ricevute')), ...last.map((e) => h('a', { class: 'cp-line', href: hrefFor('mission', e.subject.id) }, stamp(st, e.at), h('span', { class: 'cp-lt' }, st.missions[e.subject.id].title), h('span', { class: 'cp-lw' }, present('mission', e.payload.to).label)))) : null);
  }

  // Receipts: what Archeus did here, newest first, each a line you can open.
  function receiptsNode() {
    if (general) return h('div', { class: 'cp-empty' }, h('h2', null, L('General keeps no receipts.', 'Generale non tiene ricevute.')), h('p', { class: 'cp-sub' }, L('Answers here do not touch a project. Pick a project to see what Archeus did in it.', 'Le risposte qui non toccano nessun progetto. Scegli un progetto per vedere cosa ha fatto Archeus.')));
    const evs = st.events.filter((e) => e.project === s.project && STEPS.test(e.type) && st.missions[e.subject.id] && (!focused || e.subject.id === focused.id)).reverse();
    const shown = P.all ? evs : evs.slice(0, 30), waits = focused ? here.filter((a) => a.mission === focused.id) : here;
    return h('div', { class: 'cp-scroll' },
      waits.length ? h('section', { class: 'cp-sec' }, h('h3', { class: 'pk-gh' }, L('Waiting for you', 'Aspettano te')), ...waits.map((a) => h('a', { class: 'cp-line', 'data-need': '', href: '#/work/' + a.id }, glyph('needs_you'), h('span', { class: 'cp-lt' }, st.missions[a.mission]?.title || a.id), h('span', { class: 'cp-lw' }, a.kind === 'plan' ? L('Approve this plan?', 'Approvare questo piano?') : L('Allow this action?', 'Consentire questa azione?'))))) : null,
      open.length ? h('section', { class: 'cp-sec' }, h('h3', { class: 'pk-gh' }, L('Open missions', 'Missioni aperte')), ...open.filter((m) => !focused || m.id === focused.id).map((m) => h('a', { class: 'cp-line', href: hrefFor('mission', m.id) }, spineDots(m), h('span', { class: 'cp-lt' }, m.title), h('span', { class: 'cp-lw' }, present('mission', m.state).label)))) : null,
      h('section', { class: 'cp-sec' }, h('h3', { class: 'pk-gh' }, L('Done by Archeus', 'Fatto da Archeus')),
        ...(shown.length ? shown.map((e) => h('a', { class: 'cp-line', href: hrefFor('mission', e.subject.id) }, stamp(st, e.at), h('span', { class: 'cp-lt' }, st.missions[e.subject.id].title), h('span', { class: 'cp-lw' }, e.payload.to ? present('mission', e.payload.to).label : STEER[e.type]())))
          : [h('p', { class: 'cp-sub' }, L('Archeus has not acted here yet.', 'Archeus non ha ancora agito qui.'))]),
        evs.length > shown.length ? h('button', { class: 'btn quiet cp-more', type: 'button', onclick: () => { P.all = true; ctx.render(); } }, L('Show {n} earlier', 'Mostra {n} precedenti', { n: evs.length - shown.length })) : null));
  }
  // Context: the project's missions and the command reference (what the old right column held, one click away).
  function contextNode() {
    const list = h('div', { class: 'cp-cmds' }), q = h('input', { type: 'search', class: 'cp-q', placeholder: L('Search commands', 'Cerca comandi'), 'aria-label': L('Search commands', 'Cerca comandi'), 'data-key': 'chat-cmd-q', autocomplete: 'off' });
    const draw = () => {
      clear(list); const n = q.value.trim().toLowerCase();
      const hit = SL.COMMANDS.filter((c) => !c.unavailable && (!n || ('/' + c.name + ' /' + c.alias + ' ' + SL.descOf(c, lang())).toLowerCase().includes(n)));
      hit.forEach((c) => list.append(h('button', { class: 'cp-cmd', type: 'button', onclick: () => { P.tab = 'chat'; ctx.render(); s.comps.page.setText('/' + SL.nameIn(c, lang()) + (c.arg === 'none' ? '' : ' ')); } },
        h('span', { class: 'mono' }, '/' + SL.nameIn(c, lang())), clsChip(c.cls), h('span', { class: 'cp-cd' }, SL.descOf(c, lang())))));
      if (!hit.length) list.append(h('p', { class: 'cp-sub' }, L('No command matches.', 'Nessun comando corrispondente.')));
    };
    q.addEventListener('input', draw); draw();
    const ms = general ? [] : Object.values(st.missions).filter((m) => m.project === s.project).sort((a, b) => isOpenMission(b) - isOpenMission(a));
    return h('div', { class: 'cp-scroll' },
      general ? null : h('section', { class: 'cp-sec' }, h('h3', { class: 'pk-gh' }, project?.name || s.project), project?.note ? h('p', { class: 'cp-sub' }, project.note) : null,
        ...(ms.length ? ms.map((m) => h('a', { class: 'cp-line', href: hrefFor('mission', m.id) }, spineDots(m), h('span', { class: 'cp-lt' }, m.title), h('span', { class: 'cp-lw' }, present('mission', m.state).label))) : [h('p', { class: 'cp-sub' }, L('No missions yet.', 'Ancora nessuna missione.'))])),
      h('section', { class: 'cp-sec' }, h('h3', { class: 'pk-gh' }, L('Commands', 'Comandi')), q, list));
  }

  const thread = [h('div', { class: 'logwrap' }, log, newer), comp];
  const side = () => cur === 'context' ? contextNode() : receiptsNode();
  const page = h('div', { class: 'chatpage', 'data-quiet': store.reducedMotion() ? 'true' : 'false', 'data-wide': wide ? 'true' : 'false' },
    wide ? h('section', { class: 'convo', 'aria-label': L('Conversation', 'Conversazione') }, bar, ...thread)
      : h('section', { class: 'convo', 'aria-label': L('Conversation', 'Conversazione') }, bar, tabStrip(TABS), h('div', { class: 'cp-panel', id: 'cbp', role: 'tabpanel', 'aria-labelledby': 'cbt-' + tab }, tab === 'chat' ? thread : side())),
    wide ? h('aside', { class: 'cside', 'aria-label': L('Activity', 'Attività') }, tabStrip(TABS.slice(1)), h('div', { class: 'cp-panel', id: 'cbp', role: 'tabpanel', 'aria-labelledby': 'cbt-' + cur }, side())) : null);
  ctx.mounts.push(() => {
    if (!store.reducedMotion()) log.querySelectorAll('.msg').forEach((el) => {
      const before = oldCards.get(el.dataset.key), card = el.querySelector('.ccard'), after = card?.getBoundingClientRect().height;
      if (before && after && Math.abs(before - after) > 1) card.animate([{ height: before + 'px', overflow: 'hidden' }, { height: after + 'px', overflow: 'hidden' }], { duration: 180, easing: 'ease-out' });
    });
    oldCards.clear();
    if (wideNow() !== wide) return ctx.render();
    if (wide || tab === 'chat') log.scrollTop = P.bottom ? log.scrollHeight : P.scroll;
    visible.forEach((e) => P.seen.add(e.m.id));
    if (P.switched) { P.switched = false; if (!store.reducedMotion()) log.animate([{ opacity: .35 }, { opacity: 1 }], { duration: 140, easing: 'ease-out' }); }
  });
  return page;
}
// ---------- the bar docked on Now, and the phone sheet ----------
export const openTell = (ctx) => { const s = S4(ctx); if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); s.sheet = true; s.focusSheet = true; ctx.render(); };
// On the phone the dock is gone: Tell (bottom bar) opens the chat sheet from any page but Chat, which has its own composer.
export function mountDock(ctx, dock, app) {
  const s = S4(ctx), phone = isPhone(), on = ctx.route.name === 'now' && !phone;
  if (!phone && s.sheet) s.sheet = false;
  app.dataset.dock = on ? '1' : '';
  dock.hidden = !on; clear(dock);
  const old = app.querySelector('.chatsheet'); if (old) old.remove();
  const oldS = app.querySelector('.cscrim'); if (oldS) oldS.remove();
  if (phone) { if (s.sheet && ctx.route.name !== 'chat') buildSheet(ctx, app); else s.sheet = false; return; }
  if (!on) return;
  dock.append(dockNode(ctx));
}
// The composer with the last exchange above it: on the Overview it sits in the scene, on other pages it is the Tell overlay.
export function dockNode(ctx) {
  const s = S4(ctx), comp = composer(ctx, 'dock');
  const strip = s.touched ? h('div', { class: 'dstrip' }, threadNode(ctx, { last: true, cls: 'last' }), h('a', { class: 'btn quiet openconv', href: '#/chat' }, L('Open conversation', 'Apri la conversazione'))) : h('p', { class: 'intro dintro' }, L('Ask a question, capture an idea, or describe work.', 'Fai una domanda, cattura un\'idea o descrivi un lavoro.'));
  return h('div', { class: 'dockin' }, strip, comp);
}
function buildSheet(ctx, app) {
  const s = S4(ctx), comp = composer(ctx, 'sheet');
  const back = () => { s.sheet = false; s.kb = false; ctx.render(); const b = document.querySelector('[data-key="bb-tell"]'); if (b) b.focus(); };
  const log = threadNode(ctx), nr = newReply(log);
  const sheet = h('section', { class: 'chatsheet', role: 'dialog', 'aria-label': L('Chat with Archeus', 'Chat con Archeus'), 'data-exp': s.exp ? '1' : '0', 'data-kb': s.kb ? '1' : '0' },
    h('div', { class: 'cs-main' }, h('div', { class: 'grab', 'aria-hidden': 'true' }),
      h('div', { class: 'cs-head' }, h('button', { class: 'btn quiet', type: 'button', onclick: back }, icon('chevron', 18), L('Back', 'Indietro')), h('h2', null, L('Chat', 'Chat')),
        h('button', { class: 'btn quiet', type: 'button', 'aria-pressed': s.exp ? 'true' : 'false', onclick: () => { s.exp = !s.exp; ctx.render(); } }, s.exp ? L('Collapse', 'Riduci') : L('Expand', 'Espandi'))),
      h('div', { class: 'logwrap' }, log, nr), comp),
    h('div', { class: 'kbsim', 'aria-hidden': s.kb ? null : 'true' }, h('p', { class: 'kbnote' }, L('Simulated keyboard', 'Tastiera simulata')), h('div', { class: 'kbkeys', 'aria-hidden': 'true' }, ...'qwertyuiop asdfghjkl zxcvbnm'.split(' ').map((r) => h('div', { class: 'kbrow' }, ...r.split('').map((k) => h('span', { class: 'kbk' }, k))))),
      h('button', { class: 'btn quiet', type: 'button', onclick: () => { s.kb = false; sheet.dataset.kb = '0'; } }, L('Hide keyboard', 'Nascondi la tastiera'))));
  sheet.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); back(); } });
  app.append(h('div', { class: 'cscrim', onclick: back }), sheet);
  if (window.visualViewport && !hoverDevice()) { const vv = window.visualViewport, f = () => sheet.style.setProperty('--kbh-real', Math.max(0, window.innerHeight - vv.height - vv.offsetTop) + 'px'); vv.addEventListener('resize', f); f(); }
  ctx.mounts.push(() => { if (s.focusSheet) { s.focusSheet = false; const i = sheet.querySelector('input.cinput'); if (i) i.focus({ preventScroll: true }); } });
}
void clockLabel;
