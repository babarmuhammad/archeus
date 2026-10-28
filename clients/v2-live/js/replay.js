// Replay and Recovery (S4): what Core recorded, step by step, from rows and events. Nothing here plays by itself or re-runs anything.
// Recovery options only create an approval card; approving changes a receipt and the simulation through its ordinary actions, never the evidence.
import { h } from './dom.js';
import { glyph } from './icons.js';
import { head, dnote, panel, empty } from './views.js';
import { L, C } from './chat-cards.js';
import { tp } from '../chat-engine.js';
import { clockLabel } from '../sim.js';
import { spineInspector } from './spine.js';
import { CATS, CAT_DEF, STRENGTH, VOCAB, buildReplay, recovery, FIVE_ROWS, GAPS, NEVER, vocabCounts, whyOf } from '../replay-model.js';

const GLYPH = { INTENDED: '○', AUTHORIZED: '◇', RECORDED: '●', 'MAY-HAVE-TAKEN-EFFECT': '◐', UNCERTAIN: '?', SUSPENDED: '‖', RECONCILED: '✓', NONE: '–', UNKNOWN: '?' };
const catChip = (c) => h('span', { class: 'cat rc', 'data-cat': c }, h('span', { class: 'g', 'aria-hidden': 'true' }, GLYPH[c]), c);
const strChip = (k) => h('span', { class: 'str', 'data-str': k }, C(STRENGTH[k]));
const reasonText = (r) => r.replace(/_/g, ' ');
const nm = (x) => (typeof x === 'object' && x && x.en ? C(x) : x);

function rpState(ctx) { const u = ctx.ui; if (!u.rp) u.rp = { filter: null, rec: null, receipt: null, machine: 'execution', mission: null }; return u.rp; }

export function viewReplay(ctx) {
  const sim = ctx.sim, st = sim.state, rp = rpState(ctx);
  const ms = Object.values(st.missions);
  const m = st.missions[ctx.route.id] || st.missions['m-date'] || ms[0];
  if (!m) return h('div', { class: 'rp-page' }, head(ctx, L('Replay', 'Replay')), h('div', { class: 'view replayview' }, empty('No missions to replay yet.')));
  if (rp.mission !== m.id) { rp.mission = m.id; rp.rec = null; rp.receipt = null; rp.filter = null; rp.evidenceOpen = false; rp.tlTop = 0; rp.cursorPos = null; rp.lastSel = null; rp.evidenceN = null; rp.evidenceTrigger = null; ctx.ui.replaySel = null; }
  const r = buildReplay(sim, m.id);
  const shown = r.steps.filter((x) => !rp.filter || x.category === rp.filter);
  const selN = ctx.ui.replaySel == null ? r.steps.length : ctx.ui.replaySel;           // 1-based step number
  const row = shown.find((x) => x.n === selN) || shown[shown.length - 1];
  const pick = (n, evidence = true) => { ctx.ui.replaySel = n; rp.rec = null; rp.receipt = null; rp.evidenceOpen = evidence; rp.evidenceTrigger = document.activeElement?.dataset?.key; ctx.render(); };
  const idx = row ? shown.findIndex((x) => x.n === row.n) : -1;
  const move = (d) => { const t = shown[Math.max(0, Math.min(shown.length - 1, (idx < 0 ? 0 : idx) + d))]; if (t) pick(t.n); };

  const entering = rp.enterMission !== m.id || rp.enterFilter !== rp.filter;
  rp.enterMission = m.id; rp.enterFilter = rp.filter;
  const timeline = h('div', { class: 'rp-events', role: 'group', 'aria-label': 'Recorded events' },
    ...shown.map((x, i) => h('button', {
      class: 'rp-event' + (entering ? ' rp-enter' : ''), type: 'button', id: 'rs-' + x.n,
      style: '--delay:' + Math.min(i * 20, 100) + 'ms', 'aria-pressed': row && x.n === row.n ? 'true' : 'false',
      'data-cat': x.category, 'data-key': 'tl-' + x.n, onclick: () => pick(x.n),
      onkeydown: (e) => {
        if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
        e.preventDefault();
        const i = shown.indexOf(x), t = e.key === 'Home' ? shown[0] : e.key === 'End' ? shown[shown.length - 1] : shown[Math.max(0, Math.min(shown.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))];
        pick(t.n, false); document.getElementById('rs-' + t.n)?.focus({ preventScroll: true });
      }
    }, h('span', { class: 'rp-time' }, x.time), h('span', { class: 'rp-event-copy' },
      h('b', null, x.machine + ' ' + x.state.replace(/_/g, ' ')), catChip(x.category),
      h('span', { class: 'rp-source' }, x.id)), h('span', { class: 'rp-number', 'aria-hidden': 'true' }, String(x.n)))),
    !shown.length ? empty(r.steps.length ? 'No events in this category.' : L('No recorded steps for this mission.', 'Nessun passo registrato per questa missione.')) : null);
  timeline.addEventListener('scroll', () => { rp.tlTop = timeline.scrollTop; });
  ctx.mounts.push(() => {
    timeline.scrollTop = rp.tlTop || 0;
    if (row && rp.lastSel !== row.n) {
      const el = document.getElementById('rs-' + row.n);
      if (el) {
        const top = el.offsetTop, bottom = top + el.offsetHeight;
        if (top < timeline.scrollTop) timeline.scrollTop = top;
        else if (bottom > timeline.scrollTop + timeline.clientHeight) timeline.scrollTop = bottom - timeline.clientHeight;
      }
    }
    rp.lastSel = row ? row.n : null;
  });
  const filters = h('div', { class: 'chips rp-filters', role: 'group', 'aria-label': L('Filter by category', 'Filtra per categoria') },
    h('button', { class: 'chip', type: 'button', 'data-key': 'rp-all', 'aria-pressed': !rp.filter ? 'true' : 'false', onclick: () => { rp.filter = null; rp.tlTop = 0; ctx.render(); } }, L('All', 'Tutte') + ' ' + r.steps.length),
    ...CATS.filter((c) => r.counts[c] || rp.filter === c).map((c) => h('button', { class: 'chip', type: 'button', 'data-cat': c, 'data-key': 'rp-filter-' + c, 'aria-pressed': rp.filter === c ? 'true' : 'false', onclick: () => { rp.filter = rp.filter === c ? null : c; rp.tlTop = 0; ctx.render(); } },
      h('span', { class: 'g', 'aria-hidden': 'true' }, GLYPH[c]), ' ' + c + ' ', h('span', { class: 'rp-count' }, String(r.counts[c] || 0)))));

  const firstAt = r.steps[0]?.at || 0, duration = (r.steps[r.steps.length - 1]?.at || firstAt) - firstAt;
  const position = (x) => duration ? (x.at - firstAt) / duration : (x.n - 1) / Math.max(1, r.steps.length - 1);
  // The plot is as wide as the right column (half the page when the page is wide); a mark nudged past the end shrinks the scale instead of piling on the last one.
  const mainW = (document.querySelector('.main-col') || {}).clientWidth || innerWidth, plotW = Math.max(220, (mainW > 900 ? (mainW - 80) / 2.05 : mainW - 40) - 24);
  const lanes = [-1, -1, -1, -1], gap = 14 / plotW;
  const laneFor = (at) => { let l = lanes.findIndex((last) => at - last > gap); if (l < 0) { l = lanes.indexOf(Math.min(...lanes)); at = lanes[l] + gap + .001; } lanes[l] = at; return { at, l }; };
  const marks = r.steps.map((x) => { const { at, l } = laneFor(position(x)); return { x, at, lane: l }; }), span = Math.max(1, ...marks.map((k) => k.at));
  const cursorPos = row ? position(row) / span : 0;
  const playhead = h('span', { class: 'rp-playhead', 'aria-hidden': 'true' });
  const plot = h('div', { class: 'rp-plot', 'aria-hidden': 'true' },
    ...marks.map(({ x, at, lane }) => h('span', { class: 'rp-tick', 'data-cat': x.category, 'data-dim': rp.filter && x.category !== rp.filter ? 'true' : null, style: 'left:calc(7px + ' + at / span + ' * (100% - 14px));top:' + (4 + lane * 18) + 'px' }, GLYPH[x.category])), playhead);
  const scrub = h('input', { type: 'range', min: 0, max: Math.max(0, shown.length - 1), value: Math.max(0, idx), 'data-key': 'rp-cursor',
    'aria-label': L('Step cursor. Arrows step, Home and End jump', 'Cursore dei passi. Le frecce spostano, Home e Fine saltano'),
    'aria-valuetext': row ? row.time + ' ' + row.machine + ' ' + row.state : '', disabled: shown.length ? null : true,
    oninput: (e) => {
      const next = shown[Number(e.target.value)];
      if (next) { playhead.style.transform = 'translateX(' + position(next) / span * plot.clientWidth + 'px)'; e.target.setAttribute('aria-valuetext', next.time + ' ' + next.machine + ' ' + next.state); }
    }, onchange: (e) => { const next = shown[Number(e.target.value)]; if (next) pick(next.n, false); } });
  const earlier = h('button', { class: 'btn', type: 'button', 'data-key': 'rp-earlier', disabled: idx <= 0 ? true : null, onclick: () => move(-1) }, L('Earlier', 'Prima'));
  const later = h('button', { class: 'btn', type: 'button', 'data-key': 'rp-later', disabled: idx < 0 || idx >= shown.length - 1 ? true : null, onclick: () => move(1) }, L('Later', 'Dopo'));
  const overview = h('section', { class: 'rp-overview', 'aria-label': 'Timeline overview' },
    h('div', { class: 'rp-heading' }, h('div', null, h('h2', null, m.title), h('p', { class: 'rp-intro' }, 'Read-only history. Select an event to inspect what Core recorded.')),
      h('span', { class: 'rp-position', role: 'status' }, row ? row.n + ' / ' + r.steps.length + ' · ' + row.time : '0 / ' + r.steps.length), h('a', { class: 'btn', href: '#/work/' + m.id }, L('Mission', 'Missione'))),
    h('div', { class: 'rp-stations' }, spineInspector(m.state, m.held_from)), plot,
    h('div', { class: 'rp-cursor-tools' }, earlier, scrub, later),
    h('button', { class: 'btn rp-inspect', type: 'button', 'data-key': 'rp-inspect', disabled: !row, onclick: () => pick(row.n) }, 'Inspect selected event'),
    r.history.answer === 'UNKNOWN' ? h('p', { class: 'note' }, L('Older steps were pruned from the event log, so anything before them is UNKNOWN, not “nothing happened”.', 'I passi più vecchi sono stati eliminati dal registro eventi, quindi ciò che li precede è SCONOSCIUTO, non “non è successo nulla”.')) : null);
  ctx.mounts.push(() => {
    const previous = rp.cursorPos ?? cursorPos;
    playhead.style.transition = 'none';
    playhead.style.transform = 'translateX(' + previous * plot.clientWidth + 'px)';
    playhead.getBoundingClientRect();
    playhead.style.transition = '';
    playhead.style.transform = 'translateX(' + cursorPos * plot.clientWidth + 'px)';
    rp.cursorPos = cursorPos;
  });

  const stepPanel = panel(L('Selected step', 'Passo selezionato'), null, row ? h('div', { class: 'body' },
    h('p', { class: 'ctitle' }, row.machine + ' ' + row.state.replace(/_/g, ' ')),
    h('dl', { class: 'kv' },
      h('dt', null, L('Time', 'Ora')), h('dd', null, row.time), h('dt', null, L('Category', 'Categoria')), h('dd', null, catChip(row.category), h('span', { class: 'sp-text cdef' }, C(CAT_DEF[row.category]))),
      h('dt', null, L('Why this category', 'Perché questa categoria')), h('dd', null, row.why || reasonText(row.reason)),
      h('dt', null, L('Trigger', 'Causa')), h('dd', null, row.trigger || L('none recorded', 'nessuna registrata')),
      h('dt', null, L('Recorded by', 'Registrato da')), h('dd', null, row.actor === 'device' ? L('you (device)', 'te (dispositivo)') : row.actor === 'core' ? L('Core', 'Core') : L('unknown', 'sconosciuto')),
      h('dt', null, L('Settled by', 'Chiuso da')), h('dd', null, row.settled_by === 'unknown' ? h('span', { class: 'unk' }, L('unknown', 'sconosciuto')) : row.settled_by, h('span', { class: 'sp-text cdef' }, L('Read only, from the recorded edge and its event actor ({r}). Not a new record.', 'Sola lettura, dal passaggio registrato e dal suo attore ({r}). Non è un nuovo record.', { r: reasonText(row.settled_why) })))),
    h('h3', { class: 'gh' }, 'Source record'),
    h('p', { class: 'rp-record mono' }, row.machine + ' · ' + row.id + ' · seq ' + row.seq),
    h('h3', { class: 'gh' }, L('Evidence', 'Prove')),
    h('ul', { class: 'evid' }, ...row.evidence.map((e) => h('li', null, h('span', { class: 'el' }, nm(e.label)), h('span', { class: 'ev' }, nm(e.value)), strChip(e.strength)))),
    h('p', { class: 'sp-text' }, L('A report is never the completion signal. A decision is never proof that it happened.', 'Un rapporto non è mai il segnale di completamento. Una decisione non è mai la prova che sia avvenuta.'))) : empty(L('Nothing selected.', 'Niente di selezionato.')));

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
  const optCard = (o) => h('article', { class: 'ccard rcv', 'data-kind': 'recovery', 'data-ok': o.ok ? 'true' : 'false' }, h('span', { class: 'cat rp-sim' }, L('SIMULATED', 'SIMULATO')), h('p', { class: 'ctitle' }, C(o.title)),
    h('div', { class: 'wl' }, h('div', null, h('h4', null, L('Archeus would', 'Archeus farebbe')), h('ul', null, ...o.would.map((w) => h('li', null, C(w))))), h('div', null, h('h4', null, L('Archeus will not', 'Archeus non farà')), h('ul', null, ...o.wont.map((w) => h('li', null, C(w)))))),
    o.ok ? h('div', { class: 'actions' }, h('button', { class: 'btn', type: 'button', onclick: () => propose(o) }, L('Draft a proposal', 'Prepara una proposta'))) : h('p', { class: 'sp-text why' }, C(o.why)));
  const pc = rp.rec && rp.rec.step === (row && row.n) ? (() => { const o = opts.find((x) => x.id === rp.rec.id); const ta = h('textarea', { class: 'cta', rows: 3, 'aria-label': o.id === 'ask' ? L('Question for you (unsent)', 'Domanda per te (non inviata)') : L('Changed instructions', 'Istruzioni modificate'), oninput: (e) => { rp.rec.text = e.target.value; } }); ta.value = rp.rec.text;
    return h('div', { class: 'ccard', 'data-kind': 'proposal' }, h('p', { class: 'kick', 'data-role': 'needs_you' }, h('span', { class: 'g', 'aria-hidden': 'true' }, glyph('needs_you')), h('span', null, L('Proposed · nothing has happened', 'Proposta · non è successo nulla'))),
      h('span', { class: 'cat rp-sim' }, L('SIMULATED', 'SIMULATO')), h('p', { class: 'ctitle' }, C(o.title)), h('p', { class: 'sp-text' }, L('Bound to {t}, step {n}. Nothing will run or be sent until you approve. A retry is a new execution id.', 'Legata a {t}, passo {n}. Non girerà né sarà inviato nulla finché non approvi. Un nuovo tentativo è una nuova esecuzione.', { t: m.title, n: rp.rec.step })),
      o.id === 'resume' ? null : h('label', { class: 'cfield' }, h('span', null, o.id === 'ask' ? L('Question for you (unsent)', 'Domanda per te (non inviata)') : L('Changed instructions', 'Istruzioni modificate')), ta),
      h('div', { class: 'actions' }, h('button', { class: 'btn primary', type: 'button', onclick: approve }, L('Approve proposal', 'Approva la proposta')), h('button', { class: 'btn', type: 'button', onclick: () => { rp.rec = null; ctx.render(); } }, L('Cancel', 'Annulla'))), h('p', { class: 'sp-text' }, L('This is a simulated decision: nothing is run, sent or spent.', 'Decisione simulata: nulla viene eseguito, inviato o speso.'))); })() : null;
  const recPanel = panel('Recovery proposals · SIMULATED', null, h('p', { class: 'lede' }, L('Options depend on where the mission is now. Each one makes an approval card; none re-runs, resumes or reconciles by itself.', 'Le opzioni dipendono da dove si trova ora la missione. Ognuna crea una scheda di approvazione; nessuna riesegue, riprende o riconcilia da sola.')),
    h('div', { class: 'body rcvs' }, ...opts.map(optCard), pc, rp.receipt ? h('p', { class: 'receipt', role: 'status' }, rp.receipt) : null,
      h('div', { class: 'never' }, h('h4', null, L('What Archeus will not do, ever', 'Cosa Archeus non farà, mai')), h('ul', null, ...NEVER.map((n) => h('li', null, C(n)))))));

  // ----- the side: starting state, retention, the five rows, categories, records, vocabulary, gaps -----
  const startPanel = panel(L('Starting state', 'Stato iniziale'), null, h('div', { class: 'body' }, ...r.starting_state.map((b) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, h('span', { class: 'mono' }, b.source), h('span', { class: 'sp-text', style: 'display:block;padding:2px 0 0' }, C(b.note))), h('span', { class: 'b' }, b.answer === 'RECORDED' ? h('span', null, catChip('RECORDED'), ' ', b.value) : catChip('UNKNOWN')))),
    h('p', { class: 'sp-text' }, L('From three commit bindings, otherwise UNKNOWN. There is no per-attempt starting digest.', 'Da tre legami a commit, altrimenti SCONOSCIUTO. Non esiste un digest iniziale per tentativo.'))));
  const histPanel = panel(L('Retention depth', 'Profondità di conservazione'), null, h('div', { class: 'body' }, h('dl', { class: 'kv' },
    h('dt', null, L('This read', 'Questa lettura')), h('dd', null, catChip(r.history.answer), ' ', reasonText(r.history.reason)),
    h('dt', null, L('Oldest retained event', 'Evento più vecchio conservato')), h('dd', null, r.history.oldest_retained_at == null ? L('none', 'nessuno') : clockLabel(r.history.oldest_retained_at)),
    h('dt', null, L('Events kept', 'Eventi conservati')), h('dd', null, L('{n} days', '{n} giorni', { n: r.history.event_days })),
    h('dt', null, L('Open-mission extension', 'Estensione per missioni aperte')), h('dd', null, L('not built: “kept until the mission closes + 30 days” does not exist yet', 'non costruita: “conservato fino alla chiusura + 30 giorni” non esiste ancora'))),
    h('p', { class: 'sp-text' }, L('Steps are read from rows, not the event log. A range past retention answers UNKNOWN with a reason, never “nothing happened”.', 'I passi si leggono dalle righe, non dal registro eventi. Un periodo oltre la conservazione risponde SCONOSCIUTO con un motivo, mai “non è successo nulla”.')),
    h('p', { class: 'sp-text' }, L('External effects: UNKNOWN. No Effect record exists.', 'Effetti esterni: SCONOSCIUTO. Non esiste un record Effect.'))));
  const five = panel(L('Five example rows', 'Cinque righe di esempio'), 5, h('p', { class: 'lede' }, L('The strategy’s example day, each row answered with what Core records today. An example, not this mission.', 'La giornata d\'esempio della strategia, ogni riga con ciò che il Core registra oggi. Un esempio, non questa missione.')),
    h('div', { class: 'body fiverows' }, ...FIVE_ROWS.map((f) => h('article', { class: 'five' }, h('p', { class: 'ctitle' }, h('span', { class: 'mono' }, f.t), ' ', C(f.title)), h('p', { class: 'sp-text q' }, '“' + C(f.says) + '”'), h('ul', { class: 'evid' }, ...f.parts.map(([s, t]) => h('li', null, h('span', { class: 'ev', style: 'grid-column:1/3' }, C(t)), strChip(s))))))));
  const legend = panel(L('Categories', 'Categorie'), CATS.length, h('div', { class: 'body' }, ...CATS.map((c) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, catChip(c)), h('span', { class: 'b cd' }, C(CAT_DEF[c]))))));
  const recs = h('details', { class: 'panel recs', open: rp.recordsOpen, ontoggle: (e) => { rp.recordsOpen = e.currentTarget.open; } }, h('summary', { 'data-key': 'rp-records' }, h('span', { class: 'gt' }, L('Records now', 'Record attuali')), h('span', { class: 'n' }, String(r.records.length))), h('div', { class: 'body' }, ...r.records.map((x) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, h('span', { class: 'mono' }, x.machine + ' ' + x.id), h('span', { class: 'sp-text', style: 'display:block;padding:2px 0 0' }, x.state.replace(/_/g, ' ') + ' · ' + reasonText(x.reason))), catChip(x.answer)))));
  const vc = vocabCounts(), machines = Object.keys(VOCAB);
  const vsel = h('select', { 'aria-label': L('Machine', 'Macchina'), 'data-key': 'rp-machine', onchange: (e) => { rp.machine = e.target.value; ctx.render(); } }, ...machines.map((x) => h('option', { value: x }, x + ' (' + VOCAB[x].length + ')'))); vsel.value = rp.machine;
  const vocab = h('details', { class: 'panel vocab', open: rp.vocabOpen, ontoggle: (e) => { rp.vocabOpen = e.currentTarget.open; } }, h('summary', { 'data-key': 'rp-vocab' }, h('span', { class: 'gt' }, L('The vocabulary', 'Il vocabolario')), h('span', { class: 'n' }, vc.total + ' ' + L('states', 'stati') + ' · ' + vc.machines + ' ' + L('machines', 'macchine'))),
    h('div', { class: 'body' }, h('p', { class: 'sp-text', style: 'padding:0 0 8px' }, L('One table in Core covers every state of every machine; a state with no entry answers UNKNOWN. execution.ENDED_REJECTED is RECORDED (owner clarification, 2026-10-25). Source notes stay in English.', 'Una sola tabella nel Core copre ogni stato di ogni macchina; uno stato senza voce risponde SCONOSCIUTO. execution.ENDED_REJECTED è REGISTRATO (chiarimento del proprietario, 2026-10-25). Le note sulle fonti restano in inglese.')),
      h('div', { class: 'sel-wrap', style: 'padding:0 0 8px' }, h('label', null, L('Machine', 'Macchina')), vsel),
      h('div', { class: 'vlist' }, ...VOCAB[rp.machine].map(([s, c]) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, h('span', { class: 'mono' }, s), h('span', { class: 'sp-text', style: 'display:block;padding:2px 0 0' }, whyOf(rp.machine, s).slice(0, 160))), catChip(c)))),
      h('p', { class: 'sp-text' }, Object.entries(vc.n).map(([k, v]) => k + ' ' + v).join(' · '))));
  const gaps = panel(L('Not recorded', 'Non registrato'), GAPS.length, h('div', { class: 'body' }, h('ul', { class: 'gaps' }, ...GAPS.map((g) => h('li', null, h('span', null, C(g)), strChip('NOT_RECORDED'))))), h('p', { class: 'note' }, L('Not every external effect can be reversed.', 'Non ogni effetto esterno si può annullare.')));
  const fwd = h('button', { class: 'btn', type: 'button', onclick: () => { sim.advance(10 * 60 * 1000); ctx.toast(L('The simulation moved 10 minutes forward. Replay shows its new steps.', 'La simulazione è avanzata di 10 minuti. Il Replay mostra i suoi nuovi passi.')); ctx.render(); } }, L('Advance the simulation 10 minutes', 'Avanza la simulazione di 10 minuti'));

  stepPanel.classList.add('rp-evidence');
  if (rp.evidenceN !== row?.n) stepPanel.classList.add('rp-evidence-enter');
  rp.evidenceN = row?.n;
  const closeEvidence = () => {
    rp.evidenceOpen = false; sheet.close(); ctx.render();
    const trigger = document.querySelector('[data-key="' + rp.evidenceTrigger + '"]');
    (trigger && !trigger.disabled ? trigger : document.getElementById('rs-' + row?.n))?.focus({ preventScroll: true });
  };
  const sheet = h('dialog', { class: 'rp-sheet', 'aria-label': L('Selected step', 'Passo selezionato'), oncancel: (e) => { e.preventDefault(); closeEvidence(); } },
    h('button', { class: 'btn rp-sheet-close', type: 'button', 'data-key': 'rp-close-evidence', onclick: closeEvidence }, 'Close evidence'));
  const side = h('div', { class: 'rp-side' }, overview, stepPanel);
  const reading = h('div', { class: 'rp-reading' }, panel('Recorded events', shown.length, filters, timeline), side);
  const reference = h('details', { class: 'rp-reference panel', open: rp.referenceOpen, ontoggle: (e) => { rp.referenceOpen = e.currentTarget.open; } }, h('summary', { 'data-key': 'rp-reference' }, 'Reference and limits'),
    h('div', { class: 'rp-reference-grid' }, startPanel, histPanel, legend, five, recs, vocab, gaps, h('div', { class: 'actions' }, fwd)));
  ctx.mounts.push(() => {
    const narrow = reading.clientWidth <= 600;
    if (narrow && rp.evidenceOpen && row) {
      if (!sheet.open) { sheet.append(stepPanel); sheet.showModal(); }
    } else if (sheet.open) { sheet.close(); side.append(stepPanel); }
  });
  const missionPick = h('select', { class: 'pick', 'aria-label': L('Mission', 'Missione'), 'data-key': 'rp-mission', onchange: (e) => ctx.nav('#/replay/' + e.target.value) }, ...ms.map((x) => h('option', { value: x.id }, x.title)));
  missionPick.value = m.id;
  return h('div', { class: 'rp-page' }, head(ctx, L('Replay', 'Replay'), missionPick), h('div', { class: 'view replayview' },
    reading, reference, recPanel, sheet,
    dnote('A19', 'Replay answers from what Core recorded: nine categories, a reason when it cannot tell, nothing that can be re-run (G03, G11).'),
    dnote('G10', 'Recovery choices create explicit approval cards only; approving changes a receipt, never the evidence. No autoplay (G09).')));
}
