// The chat surfaces (S4): the full Chat page, the bar docked on Now, and the phone chat sheet. One composer per place, cached across renders so
// typing, focus and the caret survive a redraw. The slash menu is a combobox: focus stays in the field, the menu never takes it.
import { h, clear } from './dom.js';
import { icon } from './icons.js';
import * as store from './store.js';
import { createChat } from '../chat-engine.js';
import * as SL from '../slash.js';
import { clockLabel } from '../sim.js';
import { head, dnote, panel } from './views.js';
import { L, C, lang, msgNode, cardNode, clsChip, clsLabel } from './chat-cards.js';

const RKEY = 'archeus-v2-live-recents';
const loadRecents = () => { try { const r = JSON.parse(localStorage.getItem(RKEY)); return Array.isArray(r) ? r.slice(0, 5) : []; } catch (e) { return []; } };
const saveRecents = (r) => { try { localStorage.setItem(RKEY, JSON.stringify(r)); } catch (e) { /* blocked storage: the menu simply has no recents */ } };

export function S4(ctx) {
  const ui = ctx.ui;
  if (!ui.s4) {
    const eng = createChat(ctx.sim, {});
    eng.onChange = () => ctx.render();
    ui.s4 = { eng, dest: 'work', project: 'archeus', recents: loadRecents(), comps: {}, sheet: false, exp: false, kb: false, slow: false, fail: false, touched: false, pinned: true, unread: 0, notice: null, seen: 0 };
  }
  return ui.s4;
}
const phoneNow = () => { const a = document.getElementById('app'); return !!a && a.clientWidth < 600; };
const hoverDevice = () => !!(window.matchMedia && window.matchMedia('(hover: hover)').matches);

// ---------- what a card button or a retry does ----------
function actions(ctx) {
  const s = S4(ctx);
  return {
    act(id, what, data) { const r = s.eng.card(id, what, data); if (!r.ok) ctx.toast(L('Not done: {r}', 'Non fatto: {r}', { r: r.reason })); ctx.render(); if (r.nav) ctx.nav(r.nav); return r; },
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
  s.touched = true; if (phoneNow()) s.sheet = true;
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
    ...list.map((m) => msgNode(ctx, m, A.act, A.retry)),
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
  const scope = h('select', { class: 'cscope', 'aria-label': 'Destination', onchange: (e) => { const v = e.target.value; if (v === 'general') s.dest = 'general'; else { s.dest = 'work'; s.project = v.slice(5); } fillDest(); } });
  const slashBtn = h('button', { class: 'btn cslash', type: 'button', 'aria-label': 'Commands', onclick: () => { input.value = '/'; ctx.ui.draft = '/'; input.focus(); onInput(); } }, '/');
  const send = h('button', { class: 'btn primary csend', type: 'button', onclick: () => submit() }, '');
  const stop = h('button', { class: 'btn danger cstop', type: 'button', onclick: () => stopNow(ctx) }, '');
  const maxRows = () => { const hgt = (document.getElementById('app') || {}).clientHeight || 800; return where === 'sheet' ? (hgt < 700 ? 2 : 3) : hgt < 760 ? 3 : 5; };
  const root = h('div', { class: 'composer2', 'data-where': where }, notice, argline, list, live, h('div', { class: 'crow2' }, scope, input, slashBtn, send, where === 'sheet' ? null : stop), dest);

  function fillDest() {
    const a = SL.parse(input.value || '');
    const pn = (ctx.sim.state.projects.find((p) => p.id === s.project) || { name: s.project }).name;
    dest.textContent = a && a.kind === 'command' ? L('Destination: Command · /{n} · {c}', 'Destinazione: Comando · /{n} · {c}', { n: a.cmd.name, c: clsLabel(a.cmd.cls) })
      : s.dest === 'general' ? L('Destination: General · not project memory. Nothing here is saved to a project.', 'Destinazione: Generale · non è memoria di progetto. Qui non si salva nulla in un progetto.')
        : L('Destination: Work · {p}. Replies and records stay in this project.', 'Destinazione: Lavoro · {p}. Risposte e record restano in questo progetto.', { p: pn });
    scope.value = s.dest === 'general' ? 'general' : 'work:' + s.project;
  }
  function refresh() {
    input.placeholder = L('Tell Archeus what to do…', 'Dì ad Archeus cosa fare…'); input.setAttribute('aria-label', L('Message to Archeus', 'Messaggio ad Archeus'));
    scope.setAttribute('aria-label', L('Destination', 'Destinazione')); slashBtn.setAttribute('aria-label', L('Commands', 'Comandi'));
    send.textContent = L('Send', 'Invia'); stop.textContent = L('Stop', 'Ferma'); stop.setAttribute('aria-label', L('Stop: propose an emergency stop', 'Ferma: proponi un arresto d\'emergenza'));
    clear(scope).append(...ctx.sim.state.projects.map((p) => h('option', { value: 'work:' + p.id }, L('Work · {p}', 'Lavoro · {p}', { p: p.name }))), h('option', { value: 'general' }, L('General · not project memory', 'Generale · non è memoria di progetto')));
    if (document.activeElement !== input && input.value !== (ctx.ui.draft || '')) input.value = ctx.ui.draft || '';
    fillDest(); draw();
  }

  // ----- the combobox -----
  function rowsFor() {
    const mf = SL.menuFor(input.value, s.recents, lang());
    M.mode = mf.mode; M.cut = mf.cut || 0;
    if (mf.mode === 'commands') { const all = mf.items, lim = M.expanded ? all.length : maxRows(); return { rows: all.slice(0, lim).map((c) => ({ kind: 'cmd', c })).concat(all.length > lim ? [{ kind: 'more', n: all.length - lim }] : []), mf }; }
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
    while (M.active < rows.length && rows[M.active].kind === 'cmd' && rows[M.active].c.unavailable) M.active++;
    M.open = rows.length > 0;
    clear(list).hidden = !M.open;
    list.dataset.mode = M.mode;
    rows.forEach((r, i) => {
      const o = h('div', { class: 'srow', role: 'option', id: id + '-o' + i, 'aria-selected': i === M.active ? 'true' : 'false', 'aria-disabled': r.c && r.c.unavailable ? 'true' : null, onmousedown: (e) => e.preventDefault(), onclick: () => { M.active = i; choose(); input.focus(); } });
      if (r.kind === 'cmd') o.append(h('span', { class: 'sn' }, '/' + SL.nameIn(r.c, lang()), h('span', { class: 'sa' }, ' ' + (SL.otherName(r.c, lang()) !== SL.nameIn(r.c, lang()) ? '/' + SL.otherName(r.c, lang()) : ''), SL.labelOf(r.c, lang()) ? ' <' + SL.labelOf(r.c, lang()) + '>' : '')), clsChip(r.c.cls), h('span', { class: 'sd' }, r.c.unavailable ? SL.descOf(r.c, lang()) + ' · ' + r.c.unavailable[lang() === 'it' ? 1 : 0] : SL.descOf(r.c, lang())));
      else if (r.kind === 'more') o.append(h('span', { class: 'sn more' }, L('+{n} more', '+{n} altri', { n: r.n })));
      else o.append(h('span', { class: 'sn' }, '@' + r.label), h('span', { class: 'sd' }, r.meta));
      list.append(o);
    });
    const arg = mf.mode === 'arg' ? mf.cmd : null;
    argline.hidden = !arg;
    if (arg) argline.textContent = (SL.labelOf(arg, lang()) || arg.name) + (mf.empty ? ': ____' : '') + ' · ' + L('Enter sends, Esc cancels', 'Invio invia, Esc annulla');
    input.setAttribute('aria-expanded', M.open ? 'true' : 'false');
    if (M.open) input.setAttribute('aria-activedescendant', id + '-o' + M.active); else input.removeAttribute('aria-activedescendant');
    announce();
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
    if (M.open && e.key === 'ArrowDown') { e.preventDefault(); M.active = (M.active + 1) % n; while (M.rows[M.active].kind === 'cmd' && M.rows[M.active].c.unavailable) M.active = (M.active + 1) % n; draw(); }
    else if (M.open && e.key === 'ArrowUp') { e.preventDefault(); M.active = (M.active + n - 1) % n; while (M.rows[M.active].kind === 'cmd' && M.rows[M.active].c.unavailable) M.active = (M.active + n - 1) % n; draw(); }
    else if (M.open && e.key === 'Tab' && !e.shiftKey) { const r = M.rows[M.active]; if (r && r.kind === 'cmd' && !r.c.unavailable) { e.preventDefault(); input.value = '/' + SL.nameIn(r.c, lang()) + ' '; ctx.ui.draft = input.value; M.expanded = false; draw(); fillDest(); } else if (r && r.kind === 'ref') { e.preventDefault(); choose(); } }
    else if (e.key === 'Enter') { e.preventDefault(); if (M.open) choose(); else submit(); }
    else if (e.key === 'Escape') { if (M.open) { e.preventDefault(); e.stopPropagation(); M.open = false; clear(list).hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); } else if (!argline.hidden) { argline.hidden = true; e.stopPropagation(); } }
  });

  // ----- sending -----
  function showNotice(r) {
    clear(notice); notice.hidden = false;
    if (r.dup) { notice.append(h('span', null, L('You sent this {n} s ago. Send again?', 'Hai inviato questo {n} s fa. Rimandare?', { n: r.dup.secs })), h('span', { class: 'actions' }, h('button', { class: 'btn', type: 'button', onclick: () => { notice.hidden = true; submit(true); } }, L('Send again', 'Rimanda')), h('button', { class: 'btn quiet', type: 'button', onclick: () => { notice.hidden = true; } }, L('Cancel', 'Annulla')))); return; }
    if (r.notice) { notice.append(h('span', null, C(r.notice))); if (r.href) notice.append(h('a', { class: 'btn', href: r.href }, L('Open', 'Apri'))); return; }
    notice.hidden = true;
  }
  function run(text, force) {
    const o = { dest: s.dest, project: s.project, force: !!force, fail: s.fail };
    const slow = s.slow; s.fail = false; s.slow = false;
    const r = s.eng.send(text, o);
    if (!r.ok) { if (r.menu) { input.value = '/'; draw(); return r; } if (r.arg) { M.mode = 'arg'; draw(); return r; } showNotice(r); return r; }
    s.touched = true; s.pinned = true;
    if (text === input.value) { input.value = ''; ctx.ui.draft = ''; }
    notice.hidden = true; M.open = false;
    if (r.cmd) { s.recents = [r.cmd].concat(s.recents.filter((x) => x !== r.cmd)).slice(0, 5); saveRecents(s.recents); }
    if (r.run) setTimeout(() => settle(ctx, s.eng.finish(r.id)), slow ? 3000 : 500);
    else if (r.done) setTimeout(() => settle(ctx, r.out), 0);
    ctx.render();
    return r;
  }
  function submit(force) { return run(input.value, force); }

  const comp = { root, input, refresh, run, draw, setText(t) { input.value = t; ctx.ui.draft = t; fillDest(); draw(); input.focus(); } };
  s.comps[where] = comp; refresh();
  return root;
}

// ---------- the Chat page ----------
import { spineInspector } from './spine.js';
import { spineOf, isOpenMission } from '../spine-model.js';
import { present } from '../core-words.js';
import { translate } from './i18n.js';

function chatPageEntries(s, st) {
  let project = 'archeus', mission = null, general = false;
  return s.eng.thread().map((m) => {
    const own = m.from !== 'you' && m.project !== undefined;
    if (m.from === 'you') { project = m.project || 'archeus'; general = m.dest === 'general'; mission = s.eng.originOf(m).mission; }
    const ref = m.card?.mission || st.approvals[m.card?.approval]?.mission || (own ? m.mission : mission);
    return { m, project: m.project || project, mission: ref, general: m.general || m.dest === 'general' || (m.from !== 'you' && !own && general) };
  });
}

export function viewChat(ctx) {
  const s = S4(ctx), st = ctx.sim.state;
  const P = s.page || (s.page = { search: '', commands: '', seen: new Set(), read: new Set(), open: {}, pins: [], sheet: null, switched: false, scroll: 0, bottom: true });
  if (P.messages && P.messages !== st.messages) { P.pins = []; P.seen.clear(); P.read.clear(); P.mission = null; P.lastYou = null; P.bottom = true; }
  P.messages = st.messages;
  const comp = composer(ctx, 'page'), A = actions(ctx), entries = chatPageEntries(s, st);
  const lastYou = entries.filter((e) => e.m.from === 'you').at(-1)?.m.id;
  if (P.lastYou && P.lastYou !== lastYou) P.mission = null;
  P.lastYou = lastYou;
  const oldCards = new Map([...document.querySelectorAll('.chatpage .msg')].map((el) => [el.dataset.key, el.querySelector('.ccard')?.getBoundingClientRect().height]));
  const scrollers = ':is(.cp-rail, .cp-context, .cp-sheet, .cp-commands)', scrollKey = (el) => el.className + (el.closest('.cp-sheet') ? '/sheet' : '');
  const oldScroll = new Map([...document.querySelectorAll('.chatpage ' + scrollers)].map((el) => [scrollKey(el), el.scrollTop]));
  const project = st.projects.find((p) => p.id === s.project);
  const focused = s.dest !== 'general' && st.missions[P.mission]?.project === s.project ? st.missions[P.mission] : null;
  const title = s.dest === 'general' ? L('General', 'Generale') : focused?.title || project?.name || s.project;
  const visible = entries.filter((e) => s.dest === 'general' ? e.general : !e.general && e.project === s.project && (!focused || e.mission === focused.id));
  if (P.bottom) visible.forEach((e) => P.read.add(e.m.id));
  const select = (dest, id, mid) => {
    s.dest = dest; if (id) s.project = id;
    P.mission = mid || null; P.sheet = null; P.switched = true; P.scroll = 0; P.bottom = true;
    ctx.render(); s.comps.page.input.focus({ preventScroll: true });
  };
  const pending = Object.values(st.approvals).filter((a) => a.state === 'PENDING');
  function destinations(sheet = false) {
    const rows = h('div', { class: 'cp-destinations' });
    const search = h('input', { type: 'search', class: 'cp-search', placeholder: 'Search conversations', 'aria-label': 'Search conversations', 'data-key': sheet ? 'cp-sheet-search' : 'cp-search', value: P.search });
    const draw = () => {
      clear(rows); let count = 0;
      const row = (label, dest, id, mid) => {
        if (P.search && !label.toLocaleLowerCase().includes(P.search.toLocaleLowerCase())) return;
        count++;
        const active = dest === s.dest && (dest === 'general' || id === s.project && (mid || null) === (focused?.id || null));
        const need = dest !== 'general' && pending.some((a) => mid ? a.mission === mid : a.project === id);
        const unread = entries.filter((e) => e.m.from === 'archeus' && !P.read.has(e.m.id) && (dest === 'general' ? e.general : !e.general && e.project === id && (!mid || e.mission === mid))).length;
        rows.append(h('button', { class: 'cp-destination', type: 'button', 'aria-current': active ? 'true' : null, 'data-key': 'cp-dest-' + (mid || id || dest) + (sheet ? '-sheet' : ''), onclick: () => select(dest, id, mid) },
          h('span', { class: 'cp-name' }, label), need ? h('span', { class: 'cp-needs' }, L('Needs you', 'Richiede te')) : null,
          unread ? h('span', { class: 'cp-unread', 'aria-label': L('{n} unread', '{n} non letti', { n: unread }) }, String(unread)) : null));
      };
      row(L('General', 'Generale'), 'general');
      const needs = (p) => pending.some((a) => a.project === p.id), many = st.projects.length > 8 && !P.search;
      rows.append(h('h3', null, 'Projects')); [...st.projects].sort((a, b) => needs(b) - needs(a)).forEach((p) => row(p.name, 'work', p.id));
      rows.append(h('h3', null, 'Missions'));
      st.projects.forEach((p) => {
        if (many && p.id !== s.project) return;
        const missions = Object.values(st.missions).filter((m) => m.project === p.id);
        if (!missions.some((m) => !P.search || m.title.toLocaleLowerCase().includes(P.search.toLocaleLowerCase()))) return;
        rows.append(h('p', { class: 'cp-group' }, p.name)); missions.forEach((m) => row(m.title, 'work', p.id, m.id));
      });
      if (many) rows.append(h('p', { class: 'sp-text' }, 'Missions of the other projects: search by title.'));
      if (!count) rows.append(h('p', { class: 'sp-text' }, 'No conversations match'));
      translate(rows);
    };
    search.addEventListener('input', () => { P.search = search.value; draw(); }); draw();
    return h('div', { class: 'cp-rail-content' }, h('h2', null, 'Conversations'), search, rows);
  }
  function context(sheet = false) {
    const active = focused || (s.dest !== 'general' && Object.values(st.missions).find((m) => m.project === s.project && isOpenMission(m)));
    const missionSpine = active ? spineInspector(active.state, active.held_from) : null;
    if (active) {
      const sp = spineOf(active.state, active.held_from);
      missionSpine.querySelectorAll('li').forEach((row, i) => {
        const mark = sp.marks[i];
        const word = mark.kind === 'passed' ? 'Completed' : mark.kind === 'ahead' ? 'Waiting' : mark.kind === 'unknown' ? 'Position unknown' : mark.kind === 'none' ? 'Cancelled' : present('mission', active.state).label;
        row.append(h('span', { class: 'cp-phase-word' }, word));
      });
    }
    const commands = h('div', { class: 'cp-commands' });
    const search = h('input', { type: 'search', class: 'cp-search', placeholder: 'Search commands', 'aria-label': 'Search commands', 'data-key': sheet ? 'cp-cmd-sheet' : 'cp-cmd', value: P.commands });
    const draw = () => {
      clear(commands);
      const hit = SL.COMMANDS.filter((c) => !c.unavailable && ('/' + c.name + ' /' + c.alias + ' ' + SL.descOf(c, lang())).toLocaleLowerCase().includes(P.commands.toLocaleLowerCase()));
      hit.forEach((c) => commands.append(h('button', { class: 'cp-command', type: 'button', onclick: () => { P.sheet = null; ctx.render(); s.comps.page.setText('/' + SL.nameIn(c, lang()) + (c.arg === 'none' ? '' : ' ')); } },
        h('span', { class: 'mono' }, '/' + SL.nameIn(c, lang())), clsChip(c.cls), h('span', { class: 'cp-command-desc' }, SL.descOf(c, lang())))));
      if (!hit.length) commands.append(h('p', { class: 'sp-text' }, 'No commands match'));
      translate(commands);
    };
    search.addEventListener('input', () => { P.commands = search.value; draw(); }); draw();
    const pins = P.pins.map((id) => entries.find((e) => e.m.id === id)).filter((e) => e && !e.general && e.project === s.project);
    return h('div', { class: 'cp-context-content' },
      h('section', null, h('h2', null, 'Current state'), h('p', { class: 'cp-context-title' }, title), h('p', { class: 'sp-text' }, s.dest === 'general' ? L('General · not project memory', 'Generale · non è memoria di progetto') : project?.note || ''), st.estop.engaged ? h('p', { class: 'cp-needs' }, L('Emergency stop engaged', 'Arresto di emergenza attivo')) : null),
      h('section', null, h('h2', null, 'Active mission'), active ? [h('a', { class: 'cp-link', href: '#/work/' + active.id }, active.title), missionSpine] : h('p', { class: 'sp-text' }, 'No active mission')),
      h('section', null, h('h2', null, 'Pinned decisions'), pins.length && s.dest !== 'general' ? pins.map((e) => h('button', { class: 'cp-command', type: 'button', onclick: () => { P.sheet = null; P.mission = null; ctx.render(); const el = document.querySelector('[data-key="msg-' + e.m.id + '"]'); el?.scrollIntoView({ block: 'center', behavior: 'instant' }); el?.focus({ preventScroll: true }); } }, L('Open decision', 'Apri la decisione'), h('span', { class: 'cp-command-desc' }, e.m.c ? C(e.m.c) : e.m.text))) : h('p', { class: 'sp-text' }, 'No pinned decisions')),
      h('details', { class: 'cp-disclosure cp-cmdref', open: !!P.open.commands, ontoggle: (e) => { P.open.commands = e.currentTarget.open; } }, h('summary', { 'data-key': sheet ? 'cp-cmdref-sheet' : 'cp-cmdref' }, 'Command reference'), h('div', { class: 'cp-cmdref-body' }, search, commands)));
  }
  const log = h('div', { class: 'msgs cp-thread', role: 'log', 'aria-live': 'polite', 'aria-label': L('Conversation', 'Conversazione'), tabindex: '0' });
  if (s.eng.hidden()) log.append(h('p', { class: 'cut' }, L('Earlier messages hidden on this screen. History kept.', 'Messaggi precedenti nascosti su questo schermo. La cronologia resta.')));
  visible.forEach(({ m }) => {
    const node = msgNode(ctx, m, A.act, A.retry); node.tabIndex = -1;
    if (!P.switched && P.seen.size && !P.seen.has(m.id)) node.classList.add('cp-arrive');
    if (m.card && ['approval', 'confirm', 'plan'].includes(m.card.kind)) node.append(h('button', { class: 'btn quiet cp-pin', type: 'button', 'aria-pressed': P.pins.includes(m.id) ? 'true' : 'false', onclick: () => { P.pins = P.pins.includes(m.id) ? P.pins.filter((id) => id !== m.id) : P.pins.concat(m.id); ctx.render(); } }, P.pins.includes(m.id) ? L('Unpin decision', 'Rimuovi decisione dai fissati') : L('Pin decision', 'Fissa decisione')));
    log.append(node);
  });
  if (!visible.length) log.append(h('div', { class: 'cp-empty' }, h('h2', null, 'No messages here yet'), h('p', null, focused ? 'Mission focus shows linked messages. Replies go to the project.' : L('Ask a question, capture an idea, or describe work.', "Fai una domanda, cattura un’idea o descrivi un lavoro.")), h('button', { class: 'btn', type: 'button', onclick: () => s.comps.page.setText(focused ? '/plan ' + focused.id : '/status') }, L('Draft a command', 'Prepara un comando'))));
  if (visible.some((e) => e.m.status === 'submitted')) log.append(h('p', { class: 'cp-working', role: 'status' }, 'Archeus is working', h('span', { class: 'cp-dots', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'))));
  const newer = h('button', { class: 'btn newreply', type: 'button', hidden: P.bottom || !visible.some((e) => !P.seen.has(e.m.id)), onclick: () => { P.bottom = true; log.scrollTop = log.scrollHeight; newer.hidden = true; visible.forEach((e) => P.read.add(e.m.id)); } }, L('New reply', 'Nuova risposta'));
  log.addEventListener('scroll', () => { P.scroll = log.scrollTop; P.bottom = log.scrollHeight - log.scrollTop - log.clientHeight < 24; if (P.bottom) { newer.hidden = true; visible.forEach((e) => P.read.add(e.m.id)); } });
  const disclosure = (label, ...children) => h('details', { class: 'cp-disclosure', open: !!P.open[label], ontoggle: (e) => { P.open[label] = e.currentTarget.open; } }, h('summary', null, label), h('div', { class: 'cp-disclosure-body' }, ...children));
  const openSheet = (name) => { P.sheet = name; ctx.render(); };
  const page = h('div', { class: 'chatpage', 'data-quiet': store.reducedMotion() ? 'true' : 'false' }, head(ctx, L('Chat', 'Chat')),
    h('div', { class: 'view chatview' }, h('div', { class: 'chatgrid' },
      h('aside', { class: 'cp-rail', 'aria-label': 'Conversations' }, destinations()),
      h('section', { class: 'convo', 'aria-label': L('Conversation', 'Conversazione') },
        h('header', { class: 'cp-thread-head' }, h('div', null, h('h2', null, title), h('p', { class: 'sp-text' }, focused ? 'Mission focus · Replies go to the project' : s.dest === 'general' ? L('General · not project memory', 'Generale · non è memoria di progetto') : L('Work · {p}', 'Lavoro · {p}', { p: project?.name || s.project }))),
          h('div', { class: 'actions' }, h('button', { class: 'btn cp-switch', type: 'button', 'data-key': 'cp-switch', 'aria-haspopup': 'dialog', onclick: () => openSheet('destinations') }, 'Conversations'), h('button', { class: 'btn cp-context-toggle', type: 'button', 'data-key': 'cp-context', 'aria-haspopup': 'dialog', onclick: () => openSheet('context') }, 'Context'))),
        h('div', { class: 'logwrap' }, log, newer), comp,
        h('div', { class: 'cp-footer' }, disclosure('Privacy and storage', h('p', { class: 'sp-text' }, L('Retention: Unknown. “Not project memory” does not mean “not stored”. Account selected by Core. Usage: Unknown.', 'Conservazione: Sconosciuta. “Non è memoria di progetto” non vuol dire “non archiviato”. Account scelto dal Core. Utilizzo: Sconosciuto.'))),
          disclosure('Simulation fixtures', h('div', { class: 'actions' }, ...[['slow', L('Slow reply (3 s)', 'Risposta lenta (3 s)')], ['fail', L('Failed send', 'Invio fallito')]].map(([key, label]) => h('button', { class: 'btn quiet', type: 'button', 'aria-pressed': s[key] ? 'true' : 'false', onclick: () => { s[key] = !s[key]; ctx.render(); } }, label)))))),
      h('aside', { class: 'cp-context', 'aria-label': 'Context' }, context()))));
  if (P.sheet) {
    const which = P.sheet;
    const close = () => { P.sheet = null; ctx.render(); document.querySelector('[data-key="' + (which === 'context' ? 'cp-context' : 'cp-switch') + '"]')?.focus(); };
    const dialog = h('dialog', { class: 'cp-sheet', 'aria-label': which === 'context' ? 'Context' : 'Conversations', oncancel: (e) => { e.preventDefault(); close(); } },
      h('header', null, h('h2', null, which === 'context' ? 'Context' : 'Conversations'), h('button', { class: 'btn', type: 'button', onclick: close }, L('Close', 'Chiudi'))), which === 'context' ? context(true) : destinations(true));
    page.append(dialog); ctx.mounts.push(() => { if (!dialog.open) dialog.showModal(); });
  }
  ctx.mounts.push(() => {
    if (!store.reducedMotion()) log.querySelectorAll('.msg').forEach((el) => {
      const before = oldCards.get(el.dataset.key), card = el.querySelector('.ccard'), after = card?.getBoundingClientRect().height;
      if (before && after && Math.abs(before - after) > 1) card.animate([{ height: before + 'px', overflow: 'hidden' }, { height: after + 'px', overflow: 'hidden' }], { duration: 180, easing: 'ease-out' });
    });
    oldCards.clear();
    page.querySelectorAll(scrollers).forEach((el) => { el.scrollTop = oldScroll.get(scrollKey(el)) || 0; });
    log.scrollTop = P.bottom ? log.scrollHeight : P.scroll;
    visible.forEach((e) => P.seen.add(e.m.id));
    if (P.switched) { P.switched = false; if (!store.reducedMotion()) log.animate([{ opacity: .35 }, { opacity: 1 }], { duration: 140, easing: 'ease-out' }); }
  });
  // Page-only listener; the cached composer's original listener still owns destination changes.
  comp.querySelector('.cscope').onchange = () => { P.mission = null; P.switched = true; P.bottom = true; ctx.render(); };
  return page;
}
// ---------- the bar docked on Now, and the phone sheet ----------
export const openTell = (ctx) => { const s = S4(ctx); if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); s.sheet = true; s.focusSheet = true; ctx.render(); };
// On the phone the dock is gone: Tell (bottom bar) opens the chat sheet from any page but Chat, which has its own composer.
export function mountDock(ctx, dock, app) {
  const s = S4(ctx), phone = phoneNow(), on = ctx.route.name === 'now' && !phone;
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
