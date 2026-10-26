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
    input.placeholder = L('Tell Archeus what you need…', 'Dimmi cosa ti serve…'); input.setAttribute('aria-label', L('Message to Archeus', 'Messaggio ad Archeus'));
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
const EXAMPLES = [
  ['/status', 'work'], ['/needs', 'work'], ['/mission Audit export labels @Notes', 'work'], ['/stop fix date', 'work'], ['/estop', 'work'], ['/approve search', 'work'],
  ['/remember Reports use UTC', 'work'], ['Create a mission to export backups and start it', 'work'], ['Explain a checkpoint', 'general'], ['Create a project called Atlas', 'work'], ['/replay fix date', 'work'], ['delete all missions', 'work']
];
export function viewChat(ctx) {
  const s = S4(ctx), sim = ctx.sim, st = sim.state;
  const comp = composer(ctx, 'page');
  const log = threadNode(ctx);
  const nr = newReply(log);
  const convo = h('section', { class: 'panel convo', 'aria-label': L('Conversation', 'Conversazione') },
    h('h2', null, h('span', { class: 'gt' }, 'Conversation'), h('span', { class: 'n' }, s.dest === 'general' ? L('General · not project memory', 'Generale · non è memoria di progetto') : L('Work · {p}', 'Lavoro · {p}', { p: (st.projects.find((p) => p.id === s.project) || {}).name }))),
    h('div', { class: 'logwrap' }, log, nr), comp,
    h('p', { class: 'note truth' }, L('Retention: Unknown. “Not project memory” does not mean “not stored”. Account selected by Core. Usage: Unknown.', 'Conservazione: Sconosciuta. “Non è memoria di progetto” non vuol dire “non archiviato”. Account scelto dal Core. Utilizzo: Sconosciuto.')));
  const ex = EXAMPLES.map(([t, d]) => h('button', { class: 'chip ex', type: 'button', onclick: () => { s.dest = d === 'general' ? 'general' : 'work'; comp.setText(t); } }, t));
  const sample = (k) => ({ id: 'g-' + k, from: 'archeus', at: st.clock, dest: 'work', c: null, card: null });
  const gal = (card) => { const m = Object.assign(sample(card.kind), { card }); return cardNode(ctx, m, () => {}, true); };
  const mSearch = st.missions['m-search'], apSearch = mSearch && mSearch.approval;
  const side = h('div', { class: 'side' },
    panel(L('How this chat works', 'Come funziona questa chat'), null, h('div', { class: 'body' }, h('dl', { class: 'kv ckv' },
      h('dt', null, L('Work', 'Lavoro')), h('dd', null, L('Replies and records stay in the project you chose. Effects are cards you confirm.', 'Risposte e record restano nel progetto scelto. Gli effetti sono schede che confermi.')),
      h('dt', null, L('General', 'Generale')), h('dd', null, L('Not project memory. “Remember in…” asks where, and writes only after you confirm.', 'Non è memoria di progetto. “Ricorda in…” chiede dove, e scrive solo dopo la tua conferma.')),
      h('dt', null, L('Commands', 'Comandi')), h('dd', null, L('READ and NAVIGATE answer here and are not recorded. CREATE records one thing. PROPOSE only makes a card.', 'READ e NAVIGATE rispondono qui e non vengono registrati. CREATE registra una cosa. PROPOSE crea solo una scheda.')),
      h('dt', null, L('Refused', 'Rifiutato')), h('dd', null, L('Bulk approvals, shell commands, policy, credentials, deleting: “I can’t do that from chat; open Work.”', 'Approvazioni in blocco, comandi shell, policy, credenziali, eliminazioni: “Non posso farlo dalla chat; apri Lavoro.”')),
      h('dt', null, L('Retention', 'Conservazione')), h('dd', null, h('span', { class: 'unk' }, L('Unknown', 'Sconosciuta')))))),
    panel(L('Try it', 'Provalo'), ex.length, h('div', { class: 'body' }, h('p', { class: 'sp-text', style: 'padding:0 0 8px' }, L('A button fills the field; nothing is sent until you press Send.', 'Un pulsante riempie il campo; non si invia nulla finché non premi Invia.')), h('div', { class: 'chips' }, ...ex))),
    panel(L('Card gallery', 'Galleria delle schede'), 4, h('div', { class: 'body gallery' }, h('p', { class: 'sp-text', style: 'padding:0' }, L('Examples with their buttons off. The same cards appear in the conversation, where they work.', 'Esempi con i pulsanti spenti. Le stesse schede compaiono nella conversazione, dove funzionano.')),
      h('h3', { class: 'gh' }, L('Plan card', 'Scheda del piano')), gal({ kind: 'plan', mission: 'm-search' }),
      h('h3', { class: 'gh' }, L('Start card', 'Scheda di avvio')), gal({ kind: 'start', mission: 'm-sample', sample: 'Audit export labels', step: 'ask', state: 'open' }),
      h('h3', { class: 'gh' }, L('Approval card', 'Scheda di approvazione')), apSearch ? gal({ kind: 'approval', approval: apSearch, step: 'ask', state: 'open' }) : h('p', { class: 'sp-text' }, L('No decision is waiting now.', 'Nessuna decisione è in attesa adesso.')),
      h('h3', { class: 'gh' }, L('Status card', 'Scheda di stato')), gal(Object.assign({ kind: 'status', at: st.clock }, (() => { const n = sim.counts(); return { running: n.running, waiting: n.need, stopped: n.stopped }; })())))),
    panel(L('Edge cases', 'Casi limite'), null, h('div', { class: 'body' }, h('p', { class: 'sp-text', style: 'padding:0 0 8px' }, L('One-shot fixtures for the next send. A failed send is retried with the same key and recorded once. Sending the same text twice within 2 s asks first.', 'Casi di prova per il prossimo invio. Un invio fallito si ritenta con la stessa chiave e si registra una volta. Inviare lo stesso testo due volte entro 2 s chiede prima.')),
      h('div', { class: 'chips' }, h('button', { class: 'chip', type: 'button', 'aria-pressed': s.slow ? 'true' : 'false', onclick: () => { s.slow = !s.slow; ctx.render(); } }, L('Slow reply (3 s)', 'Risposta lenta (3 s)')), h('button', { class: 'chip', type: 'button', 'aria-pressed': s.fail ? 'true' : 'false', onclick: () => { s.fail = !s.fail; ctx.render(); } }, L('Failed send', 'Invio fallito'))))));
  return h('div', { class: 'chatpage' }, head(ctx, L('Chat', 'Chat')),
    h('div', { class: 'view chatview' },
      dnote('A16', 'Chat reads and creates; effects are cards you confirm (F07). A new mission waits for your approval here, unlike V1 today (F03).'),
      dnote('A17', 'Slash commands with Italian aliases: READ and CREATE act at once, PROPOSE only makes a card (F11 to F15). A secret-looking text is refused.'),
      h('div', { class: 'chatgrid' }, convo, side)));
}

// ---------- the bar docked on Now, and the phone sheet ----------
export function mountDock(ctx, dock, app) {
  const s = S4(ctx), on = ctx.route.name === 'now';
  const phone = phoneNow();
  if (!phone && s.sheet) s.sheet = false;
  app.dataset.dock = on ? '1' : '';
  dock.hidden = !on; clear(dock);
  const old = app.querySelector('.chatsheet'); if (old) old.remove();
  const oldS = app.querySelector('.cscrim'); if (oldS) oldS.remove();
  if (!on) return;
  if (phone) {
    const pn = s.dest === 'general' ? L('General', 'Generale') : (ctx.sim.state.projects.find((p) => p.id === s.project) || {}).name;
    const open = () => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); s.sheet = true; s.focusSheet = true; ctx.render(); };
    dock.append(h('div', { class: 'tellbar' }, h('span', { class: 'tscope' }, pn), h('button', { class: 'tellfield', type: 'button', 'data-key': 'tell-open', onclick: open, 'aria-label': L('Tell Archeus what you need…', 'Dimmi cosa ti serve…') }, ctx.ui.draft ? ctx.ui.draft : L('Tell Archeus what you need…', 'Dimmi cosa ti serve…')),
      h('button', { class: 'btn danger cstop', type: 'button', onclick: () => stopNow(ctx) }, L('Stop', 'Ferma'))));
    if (s.sheet) buildSheet(ctx, app);
    return;
  }
  const comp = composer(ctx, 'dock');
  const strip = s.touched ? h('div', { class: 'dstrip' }, threadNode(ctx, { last: true, cls: 'last' }), h('a', { class: 'btn quiet openconv', href: '#/chat' }, L('Open conversation', 'Apri la conversazione'))) : h('p', { class: 'intro dintro' }, L('Ask a question, capture an idea, or describe work.', 'Fai una domanda, cattura un\'idea o descrivi un lavoro.'));
  dock.append(h('div', { class: 'dockin' }, strip, comp));
}
function buildSheet(ctx, app) {
  const s = S4(ctx), comp = composer(ctx, 'sheet');
  const back = () => { s.sheet = false; s.kb = false; ctx.render(); const b = document.querySelector('[data-key="tell-open"]'); if (b) b.focus(); };
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
