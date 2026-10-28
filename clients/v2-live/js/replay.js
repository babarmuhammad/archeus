// Replay and Recovery (S4): what Core recorded, step by step, from rows and events. Nothing here plays by itself or re-runs anything.
// Recovery options only create an approval card; approving changes a receipt and the simulation through its ordinary actions, never the evidence.
import { h } from './dom.js';
import { translate } from './i18n.js';
import * as store from './store.js';
import { picker } from './picker.js';
import { glyph, icon } from './icons.js';
import { head, dnote, panel, empty, word, badge } from './views.js';
import { present } from '../core-words.js';
import { replayQuery, replayHref, openStep, compactRows, whatChanged, isBadStep, RP_SECTIONS, RP_DETAILS } from '../page-model.js';
import { L, C } from './chat-cards.js';
import { tp } from '../chat-engine.js';
import { clockLabel } from '../sim.js';
import { spineInspector } from './spine.js';
import { openSheet } from './sheet.js';
import { isPhone } from './viewport.js';
import { edgeRow, closeThen } from './phone-pages.js';
import { eventLine } from './phone-pages-model.js';
import { CATS, CAT_DEF, STRENGTH, VOCAB, buildReplay, recovery, FIVE_ROWS, GAPS, NEVER, vocabCounts, whyOf } from '../replay-model.js';

const GLYPH = { INTENDED: '○', AUTHORIZED: '◇', RECORDED: '●', 'MAY-HAVE-TAKEN-EFFECT': '◐', UNCERTAIN: '?', SUSPENDED: '‖', RECONCILED: '✓', NONE: '–', UNKNOWN: '?' };
const catChip = (c) => h('span', { class: 'cat rc', 'data-cat': c }, h('span', { class: 'g', 'aria-hidden': 'true' }, GLYPH[c]), c);
const strChip = (k) => h('span', { class: 'str', 'data-str': k }, C(STRENGTH[k]));
const reasonText = (r) => r.replace(/_/g, ' ');
const nm = (x) => (typeof x === 'object' && x && x.en ? C(x) : x);

addEventListener('hashchange', () => { if (evSheet && !/^#\/replay/.test(location.hash)) evSheet.close(); });
let spyOff = null, evSheet = null; // evSheet: the phone's evidence sheet, kept across redraws so a step change does not close it
function rpState(ctx) { const u = ctx.ui; if (!u.rp) u.rp = { filter: null, rec: null, receipt: null, machine: 'execution', mission: null }; return u.rp; }

export function viewReplay(ctx) {
  const sim = ctx.sim, st = sim.state, rp = rpState(ctx);
  const ms = Object.values(st.missions);
  const m = st.missions[ctx.route.id] || st.missions['m-date'] || ms[0];
  if (!m) return h('div', { class: 'rp-page' }, head(ctx, L('Replay', 'Replay')), h('div', { class: 'view replayview' }, empty('No missions to replay yet.')));
  if (rp.mission !== m.id) { rp.mission = m.id; rp.rec = null; rp.receipt = null; rp.filter = null; rp.evidenceOpen = false; rp.tlTop = 0; rp.cursorPos = null; rp.lastSel = null; rp.evidenceN = null; rp.evidenceTrigger = null; ctx.ui.replaySel = null; }
  const phone = isPhone(), r = buildReplay(sim, m.id);
  const shown = r.steps.filter((x) => !rp.filter || x.category === rp.filter);
  const qq = ctx.route.q || {}, rq = replayQuery(qq);
  if (qq.mode) rp.mode = rq.mode; if (qq.detail) rp.detail = rq.detail; // the view modes come from the address, and stay for the next mission
  const mode = rp.mode || 'timeline', detail = rp.detail || 'normal', cur = { mode, detail }, sec = rq.section || 'events'; // sec: the section on show on a phone
  if (!phone && rq.section && rp.sectionSeen !== m.id + rq.section) { rp.sectionSeen = m.id + rq.section; rp.jump = rq.section; }
  // Open on the step that explains why the mission needs you; a mission that moved on opens on its last step.
  const needs = ['needs_you', 'blocked', 'failed', 'reviewing'].includes(present('mission', m.state).cls);
  const selN = ctx.ui.replaySel == null ? openStep(r.steps, needs) ?? r.steps.length : ctx.ui.replaySel;           // 1-based step number
  let row = shown.find((x) => x.n === selN) || shown[shown.length - 1];
  // A step change updates the page in place (select, below). Only a drafted proposal or a receipt, which belong to the old step, force a rebuild.
  const pick = (n, evidence = true, fade = true) => {
    if (!rp.rec && !rp.receipt) { select(n, evidence, fade); return; }
    ctx.ui.replaySel = n; rp.rec = null; rp.receipt = null; rp.evidenceOpen = evidence; rp.evidenceTrigger = document.activeElement?.dataset?.key; ctx.render();
  };
  let idx = row ? shown.findIndex((x) => x.n === row.n) : -1;
  const move = (d) => { const t = shown[Math.max(0, Math.min(shown.length - 1, (idx < 0 ? 0 : idx) + d))]; if (t) pick(t.n, rp.evidenceOpen); };

  const rows = mode === 'compact' ? compactRows(shown) : shown.map((x) => ({ machine: x.machine, n: 1, first: x, last: x, step: x, bad: isBadStep(x) }));
  const rowIdx = row ? rows.findIndex((g) => row.n >= g.first.n && row.n <= g.last.n) : -1;
  const why = (x) => (detail === 'thinking' ? h('span', { class: 'rp-why' }, x.why || reasonText(x.reason)) : detail === 'verbose' ? h('span', { class: 'rp-why mono' }, [x.trigger ? 'trigger ' + x.trigger : null, 'by ' + (x.actor || 'unknown'), 'seq ' + x.seq].filter(Boolean).join(' · ')) : null);
  const phoneEvent = (g, x) => h('span', { class: 'rp-event-copy' },
    h('b', null, g.n > 1 ? g.machine + ' ' + g.first.state.replace(/_/g, ' ') + ' to ' + g.last.state.replace(/_/g, ' ') : eventLine(x, detail).title),
    h('span', { class: 'rp-sub' }, catChip(x.category), h('span', { class: 'rp-sum' }, g.n > 1 ? g.n + ' steps' : eventLine(x, detail).summary)));
  const timeline = h('div', { class: 'rp-events', role: 'group', 'aria-label': 'Recorded events', 'data-mode': mode },
    ...rows.map((g, i) => { const x = g.step; return h('button', {
      class: 'rp-event', type: 'button', id: 'rs-' + x.n,
      'aria-pressed': i === rowIdx ? 'true' : 'false',
      'data-cat': x.category, 'data-key': 'tl-' + x.n, onclick: () => pick(x.n),
      onkeydown: (e) => {
        if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
        e.preventDefault();
        const t = (e.key === 'Home' ? rows[0] : e.key === 'End' ? rows[rows.length - 1] : rows[Math.max(0, Math.min(rows.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]).step;
        pick(t.n, rp.evidenceOpen); document.getElementById('rs-' + t.n)?.focus({ preventScroll: true });
      }
    }, h('span', { class: 'rp-time' }, g.n > 1 && g.first.time !== g.last.time ? g.first.time + ' to ' + g.last.time : x.time), phone ? phoneEvent(g, x) : h('span', { class: 'rp-event-copy' },
      h('b', null, g.n > 1 ? g.machine + ' ' + g.first.state.replace(/_/g, ' ') + ' to ' + g.last.state.replace(/_/g, ' ') : x.machine + ' ' + x.state.replace(/_/g, ' ')), catChip(x.category), g.n > 1 ? h('span', { class: 'rp-steps' }, g.n + ' steps') : null,
      h('span', { class: 'rp-source' }, x.id), why(x)), phone ? null : h('span', { class: 'rp-number', 'aria-hidden': 'true' }, String(x.n))); }),
    !shown.length ? empty(r.steps.length ? 'No events in this category.' : L('No recorded steps for this mission.', 'Nessun passo registrato per questa missione.')) : null);
  const evBtns = [...timeline.querySelectorAll('.rp-event')];
  timeline.addEventListener('scroll', () => { rp.tlTop = timeline.scrollTop; });
  // Bring a row into view only when it is out of view; a step change glides there, a first paint does not.
  const reveal = (el, glide) => {
    if (!el) return;
    if (phone) { el.scrollIntoView({ block: 'nearest', behavior: glide && !store.reducedMotion() ? 'smooth' : 'auto' }); return; }
    const top = el.offsetTop, bottom = top + el.offsetHeight, at = timeline.scrollTop;
    const to = top < at ? top : bottom > at + timeline.clientHeight ? bottom - timeline.clientHeight : null;
    if (to != null) timeline.scrollTo({ top: to, behavior: glide && !store.reducedMotion() ? 'smooth' : 'auto' });
  };
  ctx.mounts.push(() => {
    if (!phone) { timeline.scrollTop = rp.tlTop || 0; if (row && rp.lastSel !== row.n) reveal(document.getElementById('rs-' + row.n)); }
    rp.lastSel = row ? row.n : null;
  });
  const seg = (label, opts, on, hrefOf, key) => h('nav', { class: 'seg', 'aria-label': label }, ...opts.map(([id, l]) => h('a', { class: 'seg-opt', href: hrefOf(id), 'aria-current': on === id ? 'true' : null, 'data-key': key + id }, h('span', { class: 'gt' }, l))));
  const modes = h('div', { class: 'rp-modes' },
    seg('View', [['timeline', 'Timeline'], ['compact', 'Compact']], mode, (id) => replayHref(m.id, { mode: id, detail }), 'rp-mode-'),
    seg('Detail', RP_DETAILS, detail, (id) => replayHref(m.id, { mode, detail: id }), 'rp-detail-'));
  const filters = edgeRow(h('div', { class: 'chips rp-filters', role: 'group', 'aria-label': L('Filter by category', 'Filtra per categoria') },
    h('button', { class: 'chip', type: 'button', 'data-key': 'rp-all', 'aria-pressed': !rp.filter ? 'true' : 'false', onclick: () => { rp.filter = null; rp.tlTop = 0; ctx.render(); } }, L('All', 'Tutte') + ' ' + r.steps.length),
    ...CATS.filter((c) => r.counts[c] || rp.filter === c).map((c) => h('button', { class: 'chip', type: 'button', 'data-cat': c, 'data-key': 'rp-filter-' + c, 'aria-pressed': rp.filter === c ? 'true' : 'false', onclick: () => { rp.filter = rp.filter === c ? null : c; rp.tlTop = 0; ctx.render(); } },
      h('span', { class: 'g', 'aria-hidden': 'true' }, GLYPH[c]), ' ' + c + ' ', h('span', { class: 'rp-count' }, String(r.counts[c] || 0))))));
  const openView = (e) => {
    const body = h('div', { class: 'rp-viewsheet' }, ...[['Layout', [['timeline', 'Timeline'], ['compact', 'Compact']], mode, (id) => replayHref(m.id, { mode: id, detail })], ['Detail', RP_DETAILS, detail, (id) => replayHref(m.id, { mode, detail: id })]].map(([label, opts, on, hrefOf]) =>
      h('div', { class: 'rp-viewgroup' }, h('h3', { class: 'rp-bh' }, label), h('div', { class: 'chips', role: 'group', 'aria-label': label }, ...opts.map(([id, l]) => h('button', { class: 'chip', type: 'button', 'aria-pressed': on === id ? 'true' : 'false', 'data-key': 'rp-view-' + id, onclick: () => closeThen(s, () => ctx.nav(hrefOf(id))) }, l))))));
    const s = openSheet({ id: 'rp-view', title: L('View', 'Vista'), detents: ['peek'], content: body });
  };
  const viewBtn = h('button', { class: 'btn rp-view', type: 'button', 'data-key': 'rp-view', onclick: openView }, L('View', 'Vista'));

  // Steps are discrete, so they sit evenly on the track (a time scale piles ten events into the last second); a real pause between two steps is drawn as a break with its length.
  const N = shown.length, fx = (i) => (N > 1 ? i / (N - 1) : .5);
  const pauses = shown.map((x, i) => (i ? x.at - shown[i - 1].at : 0)), med = pauses.slice(1).sort((p, q) => p - q)[Math.floor((N - 1) / 2)] || 0;
  const mainW = (document.querySelector('.main-col') || {}).clientWidth || innerWidth, dense = (mainW - 40 - 96) / Math.max(1, N - 1) < 30;
  const dur = (ms) => (ms >= 3600000 ? Math.round(ms / 3600000) + ' h' : ms >= 60000 ? Math.round(ms / 60000) + ' min' : Math.round(ms / 1000) + ' s');
  const left = (f) => 'left:calc(14px + ' + f + ' * (100% - 28px))';
  const nodes = shown.map((x, i) => h('span', { class: 'rp-node', 'data-cat': x.category, 'data-dense': dense ? 'true' : null, 'data-sel': i === idx ? 'true' : null, style: left(fx(i)) }, dense ? '' : GLYPH[x.category]));
  const breaks = dense ? [] : shown.flatMap((x, i) => (i && pauses[i] >= Math.max(60000, med * 5) ? [h('span', { class: 'rp-break', style: left((fx(i) + fx(i - 1)) / 2) }, '+' + dur(pauses[i]))] : []));
  const elapsed = h('span', { class: 'rp-elapsed' }), flag = h('span', { class: 'rp-flag' }, row ? row.time : '');
  const plot = h('div', { class: 'rp-plot', 'aria-hidden': 'true' }, h('span', { class: 'rp-rail' }), elapsed, ...breaks, ...nodes, flag);
  const at = (f) => 14 + f * Math.max(0, plot.clientWidth - 28);
  let lastI = -1;
  const setIdx = (i, instant) => {
    const f = fx(i), x = at(f), w = plot.clientWidth;
    if (instant) flag.style.transition = elapsed.style.transition = 'none';
    flag.style.transform = 'translateX(' + Math.max(26, Math.min(w - 26, x)) + 'px)'; elapsed.style.transform = 'scaleX(' + (w ? (x - 14) / (w - 28) : 0) + ')';
    if (instant) { flag.getBoundingClientRect(); flag.style.transition = elapsed.style.transition = ''; }
    // Only the nodes between the old and the new step change state.
    const a = shown[i] && lastI >= 0 ? Math.min(lastI, i) : 0, z = shown[i] && lastI >= 0 ? Math.max(lastI, i) : nodes.length - 1;
    for (let k = a; k <= z; k++) { const n = nodes[k]; if (!n) continue; const sel = k === i ? 'true' : 'false', done = k < i ? 'true' : 'false'; if (n.dataset.sel !== sel) n.dataset.sel = sel; if (n.dataset.done !== done) n.dataset.done = done; }
    lastI = i;
    if (shown[i] && flag.textContent !== shown[i].time) flag.textContent = shown[i].time;
  };
  const nearest = (clientX) => { const bx = plot.getBoundingClientRect(), f = Math.max(0, Math.min(1, (clientX - bx.left - 14) / Math.max(1, bx.width - 28))); return Math.max(0, Math.min(N - 1, Math.round(f * (N - 1)))); };
  const scrub = h('input', { type: 'range', min: 0, max: Math.max(0, shown.length - 1), value: Math.max(0, idx), 'data-key': 'rp-cursor', class: 'vh',
    'aria-label': L('Step cursor. Arrows step, Home and End jump', 'Cursore dei passi. Le frecce spostano, Home e Fine saltano'),
    'aria-valuetext': row ? row.time + ' ' + row.machine + ' ' + row.state : '', disabled: shown.length ? null : true,
    oninput: (e) => {
      const i = Number(e.target.value), next = shown[i];
      if (next) { setIdx(i); e.target.setAttribute('aria-valuetext', next.time + ' ' + next.machine + ' ' + next.state); }
    }, onchange: (e) => { const next = shown[Number(e.target.value)]; if (next) pick(next.n, rp.evidenceOpen); } });
  const earlier = h('button', { class: 'rp-step', type: 'button', 'data-key': 'rp-earlier', 'aria-label': L('Earlier event', 'Evento precedente'), title: L('Earlier', 'Prima'), disabled: idx <= 0 ? true : null, onclick: () => move(-1) }, icon('chevronl', 20));
  const later = h('button', { class: 'rp-step', type: 'button', 'data-key': 'rp-later', 'aria-label': L('Later event', 'Evento successivo'), title: L('Later', 'Dopo'), disabled: idx < 0 || idx >= shown.length - 1 ? true : null, onclick: () => move(1) }, icon('chevron', 20));
  let drag = null, hot = -1;
  const track = h('div', { class: 'rp-track' }, plot, scrub, h('div', { class: 'rp-axis', 'aria-hidden': 'true' }, h('span', null, shown[0] ? shown[0].time : ''), h('span', null, N ? shown[N - 1].time : '')));
  const heat = (i) => { if (hot === i) return; if (nodes[hot]) nodes[hot].dataset.hot = 'false'; hot = i; if (nodes[i]) nodes[i].dataset.hot = 'true'; };
  // While dragging, the flag glides and the detail panel follows, once per frame and without a fade; the release only commits.
  let frame = 0, want = null;
  const preview = (i) => {
    if (!shown[i]) return;
    setIdx(i); scrub.value = String(i); scrub.setAttribute('aria-valuetext', shown[i].time + ' ' + shown[i].machine + ' ' + shown[i].state);
    want = shown[i]; if (!frame) frame = requestAnimationFrame(() => { frame = 0; paintStep(want, false); });
  };
  track.addEventListener('pointerdown', (e) => { if (!N || e.button > 0) return; track.setPointerCapture(e.pointerId); drag = nearest(e.clientX); preview(drag); });
  track.addEventListener('pointermove', (e) => {
    if (drag !== null) { drag = nearest(e.clientX); preview(drag); return; }
    if (e.pointerType === 'mouse' && N) heat(nearest(e.clientX));
  });
  track.addEventListener('pointerleave', () => heat(-1));
  track.addEventListener('pointerup', () => { const i = drag; drag = null; if (i !== null && shown[i]) pick(shown[i].n, rp.evidenceOpen, false); });
  track.addEventListener('pointercancel', () => { drag = null; cancelAnimationFrame(frame); frame = 0; setIdx(Math.max(0, idx)); scrub.value = String(Math.max(0, idx)); paintStep(row, false); });
  const wc = whatChanged(r.steps);
  const changed = wc ? h('p', { class: 'rp-changed', 'data-key': 'rp-changed' }, h('span', null, wc.count + ' steps recorded'), h('span', null, wc.from === wc.to ? wc.from : wc.from + ' to ' + wc.to), h('span', null, 'Last: ' + wc.last.machine + ' ' + wc.last.state.replace(/_/g, ' ')), wc.bad ? h('span', { class: 'rp-bad' }, wc.bad + (wc.bad === 1 ? ' step needs a look' : ' steps need a look')) : null) : null;
  const posText = (x) => (x ? x.n + ' / ' + r.steps.length + ' · ' + x.time : '0 / ' + r.steps.length), position = h('span', { class: 'rp-position', role: 'status' }, posText(row));
  const phoneState = h('p', { class: 'rp-state' }, badge('mission', m.state), h('span', { class: 'rp-state-t' }, r.steps.length + ' ' + L('events', 'eventi') + (wc && wc.bad ? ' · ' + wc.bad + ' ' + L('need a look', 'da guardare') : '')));
  const scrubBar = phone ? h('div', { class: 'rp-scrub' }, earlier, h('div', { class: 'rp-mid' }, position, track), later) : null;
  const overview = phone ? null : h('section', { class: 'rp-overview', 'aria-label': 'Timeline overview' },
    h('div', { class: 'rp-heading' }, h('div', null, h('h2', null, m.title), h('p', { class: 'rp-intro' }, 'Read-only history. Select an event to inspect what Core recorded.')),
      position, h('a', { class: 'btn', href: '#/work/' + m.id }, L('Mission', 'Missione'))),
    changed,
    h('div', { class: 'rp-stations' }, spineInspector(m.state, m.held_from)),
    h('div', { class: 'rp-cursor-tools' }, earlier, track, later),
    h('button', { class: 'btn rp-inspect', type: 'button', 'data-key': 'rp-inspect', disabled: !row, onclick: () => pick(row.n) }, 'Inspect selected event'),
    r.history.answer === 'UNKNOWN' ? h('p', { class: 'note' }, L('Older steps were pruned from the event log, so anything before them is UNKNOWN, not “nothing happened”.', 'I passi più vecchi sono stati eliminati dal registro eventi, quindi ciò che li precede è SCONOSCIUTO, non “non è successo nulla”.')) : null);
  ctx.mounts.push(() => {
    setIdx(rp.cursorIdx ?? Math.max(0, idx), true);
    setIdx(Math.max(0, idx));
    rp.cursorIdx = Math.max(0, idx);
  });

  const stepBody = (row) => (row ? h('div', { class: 'body' },
    h('p', { class: 'ctitle' }, row.machine + ' ' + row.state.replace(/_/g, ' ')),
    h('dl', { class: 'kv' },
      h('dt', null, L('Time', 'Ora')), h('dd', null, row.time), h('dt', null, L('Category', 'Categoria')), h('dd', null, catChip(row.category), h('span', { class: 'sp-text cdef' }, C(CAT_DEF[row.category]))),
      h('dt', null, L('Why this category', 'Perché questa categoria')), h('dd', null, row.why || reasonText(row.reason)),
      h('dt', null, L('Trigger', 'Causa')), h('dd', null, row.trigger || L('none recorded', 'nessuna registrata')),
      h('dt', null, L('Recorded by', 'Registrato da')), h('dd', null, row.actor === 'device' ? L('you (device)', 'te (dispositivo)') : row.actor === 'core' ? L('Core', 'Core') : L('unknown', 'sconosciuto')),
      h('dt', null, L('Settled by', 'Chiuso da')), h('dd', null, row.settled_by === 'unknown' ? h('span', { class: 'unk' }, L('unknown', 'sconosciuto')) : row.settled_by, h('span', { class: 'sp-text cdef' }, L('Read only, from the recorded edge and its event actor ({r}). Not a new record.', 'Sola lettura, dal passaggio registrato e dal suo attore ({r}). Non è un nuovo record.', { r: reasonText(row.settled_why) })))),
    h('h3', { class: 'rp-bh' }, 'Source record'),
    h('p', { class: 'rp-record mono' }, row.machine + ' · ' + row.id + ' · seq ' + row.seq),
    h('h3', { class: 'rp-bh' }, L('Evidence', 'Prove')),
    h('ul', { class: 'evid' }, ...row.evidence.map((e) => h('li', null, h('span', { class: 'el' }, nm(e.label)), h('span', { class: 'ev' }, nm(e.value)), strChip(e.strength)))),
    h('p', { class: 'sp-text' }, L('A report is never the completion signal. A decision is never proof that it happened.', 'Un rapporto non è mai il segnale di completamento. Una decisione non è mai la prova che sia avvenuta.'))) : empty(L('Nothing selected.', 'Niente di selezionato.')));
  let bodyEl = stepBody(row), painted = row ? row.n : null, target = row, fading = null;
  const stepPanel = panel(L('Selected step', 'Passo selezionato'), null, bodyEl);
  // Swap only the detail content. A step change cross-fades (100 ms out, 140 ms in, opacity only); a drag preview swaps at once. Reduced motion: instant.
  function paintStep(x, fade) {
    target = x;
    if (fading) { if (fade) return; fading.onfinish = null; fading.cancel(); fading = null; }
    if ((x ? x.n : null) === painted) return;
    const draw = () => { painted = target ? target.n : null; const next = stepBody(target); bodyEl.replaceWith(next); bodyEl = next; translate(next); return next; };
    if (!fade || store.reducedMotion() || !bodyEl.animate) { draw(); return; }
    fading = bodyEl.animate({ opacity: [1, 0] }, { duration: 100, easing: 'ease-out' });
    fading.onfinish = () => { fading = null; draw().animate({ opacity: [0, 1] }, { duration: 140, easing: 'ease-out' }); };
  }

  // ----- recovery: cards that propose, never run -----
  const opts = recovery(sim, m.id);
  const propose = (o) => { rp.rec = { id: o.id, step: row ? row.n : null, text: o.id === 'retry' ? '' : o.id === 'ask' ? L('How should we proceed with “{t}”? The outcome of its last attempt is uncertain.', 'Come procediamo con “{t}”? L\'esito dell\'ultimo tentativo è incerto.', { t: m.title }) : '' }; rp.receipt = null; ctx.render(); };
  const approve = () => {
    const o = opts.find((x) => x.id === rp.rec.id), t = rp.rec.text.trim();
    if (rp.rec.step !== (row && row.n)) { rp.rec = null; ctx.render(); return; }
    if (o.id !== 'resume' && !t) { ctx.toast(L('Not done: add the changed instructions or the question first', 'Non fatto: aggiungi prima le istruzioni modificate o la domanda')); return; }
    if (o.id === 'ask') { sim.chat.post('archeus', t, { c: tp(t, t), dest: 'work', card: { kind: 'link', text: 'Open Replay', href: '#/replay/' + m.id } }); rp.receipt = L('Approved: the question for you was added to the conversation. Evidence unchanged.', 'Approvata: la domanda per te è stata aggiunta alla conversazione. Prove invariate.'); } else {
      const rr = ctx.act(o.act, m.id); rp.receipt = rr.ok ? L('Approved: {n}. The simulation moves on through its own steps; the evidence above is unchanged.', 'Approvata: {n}. La simulazione prosegue con i suoi passi; le prove qui sopra restano invariate.', { n: C(o.title).toLowerCase() }) : L('Not done: {r}', 'Non fatto: {r}', { r: rr.reason }); }
    rp.rec = null; ctx.render();
  };
  // Options that propose, never run. The one that fits the mission now comes first and holds the single primary action; the rest that apply follow; the ones that do not apply take one line each.
  const okOpts = opts.filter((o) => o.ok), recId = (okOpts.find((o) => o.id !== 'ask') || okOpts[0] || {}).id;
  const live = [...okOpts.filter((o) => o.id === recId), ...okOpts.filter((o) => o.id !== recId)], off = opts.filter((o) => !o.ok);
  const optRow = (o) => {
    const rec = o.id === recId;
    return h('article', { class: 'rcv rp-opt', 'data-kind': 'recovery', 'data-ok': 'true', 'data-rec': rec ? 'true' : null },
      h('div', { class: 'rp-opt-head' },
        h('div', { class: 'rp-opt-t' }, h('p', { class: 'ctitle' }, C(o.title), rec ? h('span', { class: 'rp-rec-tag' }, L('Recommended', 'Consigliata')) : null), h('p', { class: 'sp-text' }, C(o.would[0]))),
        h('button', { class: 'btn' + (rec ? ' primary' : ''), type: 'button', onclick: () => propose(o) }, L('Draft a proposal', 'Prepara una proposta'))),
      h('details', { class: 'rp-opt-more' }, h('summary', null, L('What Archeus would and will not do', 'Cosa farebbe e cosa non farà Archeus')),
        h('div', { class: 'wl' }, h('div', null, h('h4', null, L('Archeus would', 'Archeus farebbe')), h('ul', null, ...o.would.map((w) => h('li', null, C(w))))), h('div', null, h('h4', null, L('Archeus will not', 'Archeus non farà')), h('ul', null, ...o.wont.map((w) => h('li', null, C(w))))))));
  };
  const offRow = (o) => h('p', { class: 'rcv rp-off', 'data-kind': 'recovery', 'data-ok': 'false' }, h('b', null, C(o.title)), h('span', null, C(o.why)));
  const pc = rp.rec && rp.rec.step === (row && row.n) ? (() => { const o = opts.find((x) => x.id === rp.rec.id); const ta = h('textarea', { class: 'cta', rows: 3, 'aria-label': o.id === 'ask' ? L('Question for you (unsent)', 'Domanda per te (non inviata)') : L('Changed instructions', 'Istruzioni modificate'), oninput: (e) => { rp.rec.text = e.target.value; } }); ta.value = rp.rec.text;
    return h('div', { class: 'ccard', 'data-kind': 'proposal' }, h('p', { class: 'kick', 'data-role': 'needs_you' }, h('span', { class: 'g', 'aria-hidden': 'true' }, glyph('needs_you')), h('span', null, L('Proposed · nothing has happened', 'Proposta · non è successo nulla'))),
      h('p', { class: 'ctitle' }, C(o.title)), h('p', { class: 'sp-text' }, L('Bound to {t}, step {n}. Nothing will run or be sent until you approve. A retry is a new execution id.', 'Legata a {t}, passo {n}. Non girerà né sarà inviato nulla finché non approvi. Un nuovo tentativo è una nuova esecuzione.', { t: m.title, n: rp.rec.step })),
      o.id === 'resume' ? null : h('label', { class: 'cfield' }, h('span', null, o.id === 'ask' ? L('Question for you (unsent)', 'Domanda per te (non inviata)') : L('Changed instructions', 'Istruzioni modificate')), ta),
      h('div', { class: 'actions' }, h('button', { class: 'btn primary', type: 'button', onclick: approve }, L('Approve proposal', 'Approva la proposta')), h('button', { class: 'btn', type: 'button', onclick: () => { rp.rec = null; ctx.render(); } }, L('Cancel', 'Annulla'))), h('p', { class: 'sp-text' }, L('This is a simulated decision: nothing is run, sent or spent.', 'Decisione simulata: nulla viene eseguito, inviato o speso.'))); })() : null;
  const rail = h('aside', { class: 'rp-rec-side', 'aria-label': L('Where it stands', 'Dove siamo') },
    h('h3', { class: 'rp-bh' }, L('Where it stands', 'Dove siamo')),
    h('p', { class: 'rp-rec-state' }, badge('mission', m.state), m.reason ? h('span', null, m.reason) : null),
    pc, rp.receipt ? h('p', { class: 'receipt', role: 'status' }, rp.receipt) : null,
    !pc && !rp.receipt ? h('p', { class: 'sp-text' }, L('Choose an option to draft a proposal. Nothing runs until you approve it.', 'Scegli un\'opzione per preparare una proposta. Non gira nulla finché non la approvi.')) : null);
  const recPanel = h('section', { class: 'panel rp-rec' }, h('h2', null, h('span', { class: 'gt' }, L('Recovery proposals', 'Proposte di recupero')), h('span', { class: 'cat rp-sim' }, L('SIMULATED', 'SIMULATO'))),
    h('p', { class: 'lede' }, L('Options depend on where the mission is now. Each one makes an approval card; none re-runs, resumes or reconciles by itself.', 'Le opzioni dipendono da dove si trova ora la missione. Ognuna crea una scheda di approvazione; nessuna riesegue, riprende o riconcilia da sola.')),
    h('div', { class: 'rp-rec-grid' }, h('div', { class: 'rp-opts' }, ...live.map(optRow), off.length ? h('div', { class: 'rp-offs' }, h('h3', { class: 'rp-bh' }, L('Not available now', 'Non disponibili ora')), ...off.map(offRow)) : null), rail));

  // ----- the side: starting state, retention, the five rows, categories, records, vocabulary, gaps -----
  const block = (title, n, ...kids) => h('section', { class: 'rp-block' }, h('h3', { class: 'rp-bh' }, h('span', { class: 'gt' }, title), n != null ? h('span', { class: 'n' }, String(n)) : null), ...kids);
  const fold = (cls, key, open, set, title, meta, ...kids) => h('details', { class: 'rp-fold ' + cls, open, ontoggle: (e) => set(e.currentTarget.open) }, h('summary', { 'data-key': key }, h('span', { class: 'gt' }, title), meta ? h('span', { class: 'n' }, meta) : null), ...kids);
  const startPanel = block(L('Starting state', 'Stato iniziale'), null, h('div', { class: 'rp-lines' }, ...r.starting_state.map((b) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, h('span', { class: 'mono' }, b.source), h('span', { class: 'sp-text', style: 'display:block;padding:2px 0 0' }, C(b.note))), h('span', { class: 'b' }, b.answer === 'RECORDED' ? h('span', null, catChip('RECORDED'), ' ', b.value) : catChip('UNKNOWN')))),
    h('p', { class: 'sp-text' }, L('From three commit bindings, otherwise UNKNOWN. There is no per-attempt starting digest.', 'Da tre legami a commit, altrimenti SCONOSCIUTO. Non esiste un digest iniziale per tentativo.'))));
  const histPanel = block(L('Retention depth', 'Profondità di conservazione'), null, h('div', { class: 'rp-lines' }, h('dl', { class: 'kv' },
    h('dt', null, L('This read', 'Questa lettura')), h('dd', null, catChip(r.history.answer), ' ', reasonText(r.history.reason)),
    h('dt', null, L('Oldest retained event', 'Evento più vecchio conservato')), h('dd', null, r.history.oldest_retained_at == null ? L('none', 'nessuno') : clockLabel(r.history.oldest_retained_at)),
    h('dt', null, L('Events kept', 'Eventi conservati')), h('dd', null, L('{n} days', '{n} giorni', { n: r.history.event_days })),
    h('dt', null, L('Open-mission extension', 'Estensione per missioni aperte')), h('dd', null, L('not built: “kept until the mission closes + 30 days” does not exist yet', 'non costruita: “conservato fino alla chiusura + 30 giorni” non esiste ancora'))),
    h('p', { class: 'sp-text' }, L('Steps are read from rows, not the event log. A range past retention answers UNKNOWN with a reason, never “nothing happened”.', 'I passi si leggono dalle righe, non dal registro eventi. Un periodo oltre la conservazione risponde SCONOSCIUTO con un motivo, mai “non è successo nulla”.')),
    h('p', { class: 'sp-text' }, L('External effects: UNKNOWN. No Effect record exists.', 'Effetti esterni: SCONOSCIUTO. Non esiste un record Effect.'))));
  const five = fold('rp-five', 'rp-five', rp.fiveOpen, (v) => { rp.fiveOpen = v; }, L('Five example rows', 'Cinque righe di esempio'), '5', h('p', { class: 'lede' }, L('The strategy’s example day, each row answered with what Core records today. An example, not this mission.', 'La giornata d\'esempio della strategia, ogni riga con ciò che il Core registra oggi. Un esempio, non questa missione.')),
    h('div', { class: 'body fiverows' }, ...FIVE_ROWS.map((f) => h('article', { class: 'five' }, h('p', { class: 'ctitle' }, h('span', { class: 'mono' }, f.t), ' ', C(f.title)), h('p', { class: 'sp-text q' }, '“' + C(f.says) + '”'), h('ul', { class: 'evid' }, ...f.parts.map(([s, t]) => h('li', null, h('span', { class: 'ev', style: 'grid-column:1/3' }, C(t)), strChip(s))))))));
  const legend = block(L('Categories', 'Categorie'), CATS.length, h('div', { class: 'rp-cats' }, ...CATS.map((c) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, catChip(c)), h('span', { class: 'b cd' }, C(CAT_DEF[c]))))));
  // What Archeus will not do belongs to Reference: short guarantees, a lead sentence and the detail under it.
  const never = h('div', { class: 'rp-never-block' }, block(L('What Archeus will not do, ever', 'Cosa Archeus non farà, mai'), null, h('ul', { class: 'rp-never' }, ...NEVER.map((n) => { const [lead, ...rest] = C(n).split(/(?<=\.) /); return h('li', null, h('span', { class: 'rp-never-i', 'aria-hidden': 'true' }, icon('close', 16)), h('span', null, h('b', null, lead), rest.length ? h('span', { class: 'sp-text' }, rest.join(' ')) : null)); }))));
  const recs = h('details', { class: 'rp-fold recs', open: rp.recordsOpen, ontoggle: (e) => { rp.recordsOpen = e.currentTarget.open; } }, h('summary', { 'data-key': 'rp-records' }, h('span', { class: 'gt' }, L('Records now', 'Record attuali')), h('span', { class: 'n' }, String(r.records.length))), h('div', { class: 'body' }, ...r.records.map((x) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, h('span', { class: 'mono' }, x.machine + ' ' + x.id), h('span', { class: 'sp-text', style: 'display:block;padding:2px 0 0' }, x.state.replace(/_/g, ' ') + ' · ' + reasonText(x.reason))), catChip(x.answer)))));
  const vc = vocabCounts(), machines = Object.keys(VOCAB);
  const vsel = picker({ key: 'rp-machine', label: L('Machine', 'Macchina'), value: rp.machine, items: machines.map((x) => ({ value: x, label: x + ' (' + VOCAB[x].length + ')' })), onPick: (v) => { rp.machine = v; ctx.render(); } });
  const vocab = h('details', { class: 'rp-fold vocab', open: rp.vocabOpen, ontoggle: (e) => { rp.vocabOpen = e.currentTarget.open; } }, h('summary', { 'data-key': 'rp-vocab' }, h('span', { class: 'gt' }, L('The vocabulary', 'Il vocabolario')), h('span', { class: 'n' }, vc.total + ' ' + L('states', 'stati') + ' · ' + vc.machines + ' ' + L('machines', 'macchine'))),
    h('div', { class: 'body' }, h('p', { class: 'sp-text', style: 'padding:0 0 8px' }, L('One table in Core covers every state of every machine; a state with no entry answers UNKNOWN. execution.ENDED_REJECTED is RECORDED (owner clarification, 2026-10-25). Source notes stay in English.', 'Una sola tabella nel Core copre ogni stato di ogni macchina; uno stato senza voce risponde SCONOSCIUTO. execution.ENDED_REJECTED è REGISTRATO (chiarimento del proprietario, 2026-10-25). Le note sulle fonti restano in inglese.')),
      h('div', { class: 'sel-wrap', style: 'padding:0 0 8px' }, h('label', null, L('Machine', 'Macchina')), vsel),
      h('div', { class: 'vlist' }, ...VOCAB[rp.machine].map(([s, c]) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, h('span', { class: 'mono' }, s), h('span', { class: 'sp-text', style: 'display:block;padding:2px 0 0' }, whyOf(rp.machine, s).slice(0, 160))), catChip(c)))),
      h('p', { class: 'sp-text' }, Object.entries(vc.n).map(([k, v]) => k + ' ' + v).join(' · '))));
  const gaps = block(L('Not recorded', 'Non registrato'), GAPS.length, h('div', { class: 'rp-lines' }, h('ul', { class: 'gaps' }, ...GAPS.map((g) => h('li', null, h('span', null, C(g)), strChip('NOT_RECORDED'))))), h('p', { class: 'note' }, L('Not every external effect can be reversed.', 'Non ogni effetto esterno si può annullare.')));
  const fwd = h('button', { class: 'btn', type: 'button', onclick: () => { sim.advance(10 * 60 * 1000); ctx.toast(L('The simulation moved 10 minutes forward. Replay shows its new steps.', 'La simulazione è avanzata di 10 minuti. Il Replay mostra i suoi nuovi passi.')); ctx.render(); } }, L('Advance the simulation 10 minutes', 'Avanza la simulazione di 10 minuti'));

  // The two Decision notes, merged and folded: they explain the page, they do not belong in the way of it.
  const how = fold('rp-how', 'rp-how', rp.howOpen, (v) => { rp.howOpen = v; }, L('How Replay reads Core', 'Come il Replay legge il Core'), null,
    h('div', { class: 'body' }, dnote('A19', 'Replay answers from what Core recorded: nine categories, a reason when it cannot tell, nothing that can be re-run (G03, G11).'), dnote('G10', 'Recovery choices create explicit approval cards only; approving changes a receipt, never the evidence. No autoplay (G09).')));
  stepPanel.classList.add('rp-evidence');
  const side = h('div', { class: 'rp-side', id: 'rp-evidence' }, stepPanel, recs, gaps);
  const events = phone ? h('div', { class: 'rp-pane', id: 'rp-events' }, scrubBar, h('div', { class: 'rp-filterbar' }, filters, viewBtn), timeline, r.history.answer === 'UNKNOWN' ? h('p', { class: 'note' }, L('Older steps were pruned from the event log, so anything before them is UNKNOWN, not “nothing happened”.', 'I passi più vecchi sono stati eliminati dal registro eventi, quindi ciò che li precede è SCONOSCIUTO, non “non è successo nulla”.')) : null) : panel('Recorded events', shown.length, modes, filters, timeline);
  if (!phone) events.id = 'rp-events';
  const reading = h('div', { class: 'rp-reading' }, events, side);
  recPanel.id = 'rp-recovery';
  const referenceBody = h('div', { class: 'rp-reference-grid' }, h('div', { class: 'rp-ref-top' }, legend, h('div', { class: 'rp-ref-col' }, startPanel, histPanel)), never, five, vocab, how, h('div', { class: 'actions' }, fwd));
  const reference = phone ? h('section', { class: 'rp-reference panel', 'aria-label': 'Reference and limits' }, referenceBody) : h('details', { class: 'rp-reference panel', open: rp.referenceOpen, ontoggle: (e) => { rp.referenceOpen = e.currentTarget.open; } }, h('summary', { 'data-key': 'rp-reference' }, 'Reference and limits'), referenceBody);
  reference.id = 'rp-reference';
  // The phone's evidence sheet: opened by a row tap, only while the Events section is showing. A redraw hands the open sheet the new panel.
  function syncSheet() {
    const want = phone && rp.evidenceOpen && row && sec === 'events';
    if (evSheet && !want) { const o = evSheet; evSheet = null; o.close(); return; }
    if (!want) return;
    if (evSheet) { evSheet.el.querySelector('.sheet-body').replaceChildren(stepPanel); return; }
    evSheet = openSheet({ id: 'rp-evidence', title: L('Selected step', 'Passo selezionato'), detents: ['peek', 'full'], initial: 'peek', modal: false, content: stepPanel, onClose: () => { if (evSheet) { evSheet = null; rp.evidenceOpen = false; } } });
    requestAnimationFrame(() => reveal(document.getElementById('rs-' + row.n), true)); // the sheet now covers the foot of the list
  }
  ctx.mounts.push(syncSheet);
  // The step change, in place: selection state by attribute, the scrubber glides, the panel cross-fades. Nothing is rebuilt, so scroll, focus and hover survive.
  function select(n, evidence, fade) {
    const i = shown.findIndex((x) => x.n === n);
    if (i < 0) return;
    ctx.ui.replaySel = n; rp.evidenceOpen = evidence; rp.evidenceTrigger = document.activeElement?.dataset?.key;
    row = shown[i]; idx = i; rp.cursorIdx = i; rp.lastSel = n;
    const ri = rows.findIndex((g) => n >= g.first.n && n <= g.last.n);
    evBtns.forEach((b, k) => { const on = k === ri ? 'true' : 'false'; if (b.getAttribute('aria-pressed') !== on) b.setAttribute('aria-pressed', on); });
    reveal(evBtns[ri], true);
    cancelAnimationFrame(frame); frame = 0;
    setIdx(i); scrub.value = String(i); scrub.setAttribute('aria-valuetext', row.time + ' ' + row.machine + ' ' + row.state);
    position.textContent = posText(row);
    const offE = i <= 0, offL = i >= N - 1;
    if (offE && !offL && document.activeElement === earlier) later.focus({ preventScroll: true });
    if (offL && !offE && document.activeElement === later) earlier.focus({ preventScroll: true });
    earlier.disabled = offE; later.disabled = offL;
    paintStep(row, fade);
    syncSheet();
  }
  // The section nav is part of the address (?section=recovery); a click scrolls to the section, and scrolling lights the section in view.
  const nav = h('nav', { class: 'rp-nav', 'aria-label': 'Sections' }, ...RP_SECTIONS.map(([id, label]) => h('a', { class: 'rp-nav-a', href: replayHref(m.id, { mode, detail, section: id }), 'data-section': id, 'data-key': 'rp-nav-' + id, 'aria-current': phone && id === sec ? 'page' : null, onclick: () => { rp.pin = id; rp.jump = id; if (id === 'reference') rp.referenceOpen = true; } }, label)));
  if (!phone) ctx.mounts.push(() => {
    const at = (id) => document.getElementById('rp-' + id);
    if (rp.jump) { const el = at(rp.jump); if (el) { if (rp.jump === 'reference') el.open = true; requestAnimationFrame(() => el.scrollIntoView({ block: 'start' })); } rp.jump = null; }
    let sc = nav.parentElement; while (sc && !/(auto|scroll)/.test(getComputedStyle(sc).overflowY)) sc = sc.parentElement;
    if (spyOff) spyOff();
    if (!sc) return;
    let raf = 0;
    const spy = () => { raf = 0; const line = nav.getBoundingClientRect().bottom + 24; let on = RP_SECTIONS[0][0]; const top0 = at('events') ? at('events').getBoundingClientRect().top : 0; for (const [id] of RP_SECTIONS) { const el = at(id); if (!el || !el.getClientRects().length) continue; const t = el.getBoundingClientRect().top; if (id === 'evidence' && Math.abs(t - top0) < 8 && rp.pin !== 'evidence') continue; /* side by side with Events: lit only when chosen */ if (t <= line) on = id; } if (sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 4) on = RP_SECTIONS[RP_SECTIONS.length - 1][0]; if (rp.pin && at(rp.pin) && at(rp.pin).getClientRects().length && at(rp.pin).getBoundingClientRect().top < sc.clientHeight) on = rp.pin; /* a chosen section stays lit until the reader scrolls by hand */ nav.querySelectorAll('a').forEach((a) => { if (a.dataset.section === on) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current'); }); };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(spy); };
    const drop = () => { rp.pin = null; }; sc.addEventListener('scroll', onScroll, { passive: true }); for (const t of ['wheel', 'touchmove', 'keydown']) sc.addEventListener(t, drop, { passive: true });
    spyOff = () => { sc.removeEventListener('scroll', onScroll); for (const t of ['wheel', 'touchmove', 'keydown']) sc.removeEventListener(t, drop); spyOff = null; }; spy();
  });
  const missionPick = picker({ key: 'rp-mission', label: L('Mission', 'Missione'), cls: 'pick', value: m.id, items: ms.map((x) => ({ value: x.id, label: x.title })), onPick: (v) => ctx.nav(replayHref(v, cur)) });
  if (phone) {
    const hd = head(ctx, L('Replay', 'Replay')); hd.querySelector('h1').classList.add('vh');
    const pane = { events, evidence: h('div', { class: 'rp-pane', id: 'rp-evidence' }, stepPanel, recs, gaps), recovery: recPanel, reference }[sec];
    return h('div', { class: 'rp-page', 'data-phone': 'true' }, hd, h('div', { class: 'view replayview' },
      h('div', { class: 'rp-phead' }, missionPick, h('a', { class: 'btn rp-mission', href: '#/work/' + m.id, 'aria-label': L('Open the mission', 'Apri la missione') }, L('Mission', 'Missione'))), phoneState, nav, pane));
  }
  return h('div', { class: 'rp-page' }, head(ctx, L('Replay', 'Replay'), missionPick), h('div', { class: 'view replayview' },
    overview, nav, reading, recPanel, reference));
}
