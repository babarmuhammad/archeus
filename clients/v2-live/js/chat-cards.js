// Chat messages and cards (S4). Every card is drawn from its stored data and, where it shows live state (plan, approval), from the simulation.
// A card's own buttons call the engine; the command that made the card decided nothing. SIMULATED is stated on every reply.
import { h } from './dom.js';
import { glyph } from './icons.js';
import * as store from './store.js';
import { fmt } from '../chat-engine.js';
import { COMMANDS, CLASSES, nameIn, otherName, descOf, labelOf, find } from '../slash.js';
import { clockLabel } from '../sim.js';
import { present } from '../core-words.js';

export const lang = () => store.get('lang');
export const L = (en, it, v) => fmt({ en, it: it == null ? en : it, v: v || {} }, lang());
export const C = (c) => fmt(c, lang());
const pname = (sim, id) => { const p = sim.state.projects.find((x) => x.id === id); return p ? p.name : id; };
const btn = (label, on, cls, attrs) => h('button', Object.assign({ class: 'btn ' + (cls || ''), type: 'button', onclick: on }, attrs || {}), label);
const kv = (...rows) => h('dl', { class: 'kv ckv' }, ...rows.filter(Boolean).flatMap(([a, b]) => [h('dt', null, a), h('dd', null, b)]));
const KICK = { '◆': 'needs_you', '✓': 'done', '✕': 'blocked', '■': 'blocked' };
const kicker = (mark, text, role) => h('p', { class: 'kick', 'data-role': role || null }, h('span', { class: 'g', 'aria-hidden': 'true' }, glyph(KICK[mark])), h('span', null, text));
const SIMLINE = () => L('This is a simulated decision: nothing is run, sent or spent.', 'Decisione simulata: nulla viene eseguito, inviato o speso.');
const CLSNAME = { READ: ['READ', 'LETTURA'], CREATE: ['CREATE', 'CREA'], PROPOSE: ['PROPOSE', 'PROPONI'], NAVIGATE: ['NAVIGATE', 'NAVIGA'] };
export const clsLabel = (c) => CLSNAME[c][lang() === 'it' ? 1 : 0];
export const clsChip = (c) => h('span', { class: 'cat cls', 'data-cls': c }, clsLabel(c));

export function destLabel(sim, m) {
  if (m.dest === 'general') return L('General · not project memory', 'Generale · non è memoria di progetto');
  if (m.dest === 'command' && m.cmd) return '/' + m.cmd + ' · ' + clsLabel(m.cls);
  return L('Work · {p}', 'Lavoro · {p}', { p: pname(sim, m.project || 'archeus') });
}

// ----- one card. ctx.act is not used: the engine decides what a button does (act(id, what, data)) -----
export function cardNode(ctx, m, act, sample) {
  const c = m.card, sim = ctx.sim, st = sim.state;
  if (!c) return null;
  const off = !!sample;
  const A = (what, data) => () => { if (!off) act(m.id, what, data); };
  const B = (label, what, cls, data) => btn(label, A(what, data), cls, off ? { 'aria-disabled': 'true' } : null);
  const done = (text) => h('p', { class: 'cdone' }, text);
  const mis = c.mission ? st.missions[c.mission] : null;
  const mtitle = mis ? mis.title : (c.sample || '');
  if (c.kind === 'link') return h('div', { class: 'actions', style: 'margin-top:8px' }, h('a', { class: 'btn', href: c.href }, L(c.text, c.text === 'Open the review' ? 'Apri la revisione' : c.text)));
  if (c.kind === 'proposal') return c.state !== 'open' ? h('p', { class: 'sp-text' }, c.text + ' · ' + (c.state === 'done' ? L('Confirmed', 'Confermato') : L('Dismissed', 'Scartato'))) : h('div', { class: 'ccard', 'data-kind': 'proposal' }, h('p', null, c.text), h('div', { class: 'actions' }, btn(L('Confirm', 'Conferma'), () => ctx.act('card', m.id + '|confirm'), 'primary'), btn(L('Dismiss', 'Scarta'), () => ctx.act('card', m.id + '|dismiss'))));
  const box = (kind, kids, state) => h('div', { class: 'ccard', 'data-kind': kind, 'data-state': state || c.state || null, 'data-sample': off ? 'true' : null }, ...kids);

  if (c.kind === 'help') {
    if (c.arg) { const x = find(String(c.arg).replace(/^\//, '')); if (x) return box('help', [kicker('?', L('Usage', 'Uso')), h('p', { class: 'mono' }, '/' + nameIn(x, lang()) + (labelOf(x, lang()) ? ' <' + labelOf(x, lang()) + '>' : '')), h('p', null, descOf(x, lang())), h('p', { class: 'sp-text' }, clsLabel(x.cls))]); }
    return box('help', [kicker('?', L('Commands by class', 'Comandi per classe')), ...CLASSES.map((k) => h('div', { class: 'hgrp' }, clsChip(k), h('p', { class: 'mono hnames' }, COMMANDS.filter((x) => x.cls === k && !x.unavailable).map((x) => '/' + nameIn(x, lang())).join('  ')))),
      h('p', { class: 'sp-text' }, L('Type / for the list with descriptions. //text sends a slash as plain text. READ and NAVIGATE are not recorded.', 'Scrivi / per l\'elenco con le descrizioni. //testo invia uno slash come testo semplice. READ e NAVIGATE non vengono registrati.'))]);
  }
  if (c.kind === 'status') return box('status', [kicker('●', L('Status, as of {t}', 'Stato, alle {t}', { t: clockLabel(c.at) })), kv([L('Core', 'Core'), L('Reachable (simulated)', 'Raggiungibile (simulato)')], [L('Emergency stop', 'Arresto di emergenza'), c.estop ? L('Engaged: nothing new starts', 'Attivo: non parte nulla di nuovo') : L('Not engaged', 'Non attivo')], [L('Running', 'In corso'), String(c.running)], [L('Waiting for you', 'Aspettano te'), String(c.waiting)], [L('Stopped', 'Fermi'), String(c.stopped)], [L('Accepting new work', 'Accetta nuovo lavoro'), h('span', { class: 'unk' }, L('Unknown', 'Sconosciuto'))]), h('p', { class: 'sp-text' }, L('Unknown is shown when the status read does not carry the field, never a guess.', 'Sconosciuto appare quando la lettura non porta il campo, mai un\'ipotesi.'))]);
  if (c.kind === 'usage') return box('usage', [kicker('◌', L('Usage', 'Utilizzo')), h('div', null, ...c.rows.map((r) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, r), h('span', { class: 'b unk' }, L('Unknown', 'Sconosciuto'))))), h('p', { class: 'sp-text' }, L('Unknown is never shown as 0. Numbers come only from the existing usage reader, once T-154 exists. No token is ever shown.', 'Sconosciuto non è mai mostrato come 0. I numeri verranno solo dal lettore di utilizzo esistente, quando esisterà T-154. Nessun token è mai mostrato.'))]);
  if (c.kind === 'list') return box('list', [h('ul', { class: 'clist' }, ...c.items.map((i) => h('li', null, h('a', { class: 'crow', href: i.href }, h('span', { class: 'cl' }, i.label), h('span', { class: 'cm' }, i.meta))))), c.more ? h('p', { class: 'sp-text' }, L('+{n} more', '+{n} altri', { n: c.more })) : null]);
  if (c.kind === 'why') return box('why', [kicker('◇', L('Route decision {id}', 'Decisione di instradamento {id}', { id: c.id })), kv([L('Served model and billed cost', 'Modello servito e costo fatturato'), h('span', { class: 'unk' }, L('Unknown', 'Sconosciuto'))], [L('Account', 'Account'), L('Selected by Core', 'Scelto dal Core')])]);
  if (c.kind === 'plan') {
    const p = Object.values(st.plans).filter((x) => x.mission === c.mission).sort((a, b) => b.version - a.version)[0], ts = mis ? mis.tasks.map((id) => st.tasks[id]) : [];
    return box('plan', [kicker('≡', p ? L('Plan v{v} · {s}', 'Piano v{v} · {s}', { v: p.version, s: present('plan', p.state).label }) : L('No plan yet', 'Ancora nessun piano')), h('p', { class: 'ctitle' }, mtitle),
      ts.length ? h('ol', { class: 'cplan' }, ...ts.map((t) => h('li', null, h('span', null, t.title), h('span', { class: 'cm' }, present('task', t.state).label)))) : h('p', { class: 'sp-text' }, L('The plan is made after the mission starts.', 'Il piano si fa dopo l\'avvio della missione.')),
      h('div', { class: 'actions' }, h('a', { class: 'btn', href: off ? '#/chat' : '#/work/' + c.mission, onclick: () => { if (!off) ctx.ui.tab = 'plan'; } }, L('Open plan', 'Apri il piano')), mis && mis.approval ? h('a', { class: 'btn primary', href: off ? '#/chat' : '#/attention/' + mis.approval }, L('Open decision', 'Apri la decisione')) : null)]);
  }
  if (c.kind === 'created') return box('created', [kicker('+', L('Created · {w}', 'Creato · {w}', { w: c.what })), h('p', { class: 'ctitle' }, c.title), kv([L('Id', 'Id'), c.id], [L('Project', 'Progetto'), c.project]), h('div', { class: 'actions' }, h('a', { class: 'btn', href: c.href }, L('Show', 'Mostra')))]);
  if (c.kind === 'start') {
    const t = { t: mtitle, p: mis ? pname(sim, mis.project) : '' };
    if (c.step === 'done') return box('start', [kicker('◇', L('Started', 'Avviata')), done(L('“{t}” started. Planning is under way; the plan waits for your approval before anything executes.', '“{t}” avviata. La pianificazione è in corso; il piano aspetta la tua approvazione prima che si esegua qualcosa.', t)), h('p', { class: 'sp-text' }, SIMLINE())]);
    if (c.step === 'kept') return box('start', [kicker('○', L('Kept as mission', 'Tenuta come missione')), done(L('“{t}” is kept. Not started. Archeus will not ask again.', '“{t}” è tenuta. Non avviata. Archeus non lo chiederà di nuovo.', t))]);
    if (c.step === 'stale') return box('start', [kicker('○', L('No longer applies', 'Non si applica più')), done(c.note)]);
    const review = c.step === 'review';
    return box('start', [kicker('◆', L('Proposed · nothing has started', 'Proposta · non è partito nulla'), 'needs_you'), h('p', { class: 'ctitle' }, review ? L('Start and plan “{t}”?', 'Avviare e pianificare “{t}”?', t) : L('Starting “{t}” needs your approval', 'Avviare “{t}” richiede la tua approvazione', t)),
      review ? kv([L('What', 'Cosa'), L('Start “{t}” in {p} and ask the planner for a plan.', 'Avviare “{t}” in {p} e chiedere un piano al pianificatore.', t)], [L('Why', 'Perché'), L('You created it from chat. Chat creation never starts work by itself.', 'L\'hai creata dalla chat. La creazione da chat non avvia mai il lavoro da sola.')], [L('Core consequence', 'Conseguenza per il Core'), L('Planning runs on an account Core selects. Account and cost: Unknown. The plan then waits for your approval; nothing executes before it.', 'La pianificazione gira su un account scelto dal Core. Account e costo: Sconosciuti. Il piano poi aspetta la tua approvazione; nulla si esegue prima.')]) : h('p', { class: 'sp-text' }, L('Review it first, or keep it as a mission. Keeping leaves it idle and asks no more.', 'Rivedila prima, oppure tienila come missione. Tenerla la lascia ferma e non chiede altro.')),
      h('div', { class: 'actions' }, review ? [B(L('Start and plan', 'Avvia e pianifica'), 'start', 'primary'), B(L('Back', 'Indietro'), 'back')] : [B(L('Review proposal', 'Rivedi la proposta'), 'review', 'primary'), B(L('Keep as mission', 'Tieni come missione'), 'keep')])]);
  }
  if (c.kind === 'confirm') {
    const ts = c.targets.map((id) => st.missions[id]).filter(Boolean), name = ts.map((x) => x.title).join(', ');
    const V = { stop: [L('Stop', 'Ferma'), L('Ends its running execution. Work already recorded stays recorded. This cannot be undone from chat.', 'Termina la sua esecuzione in corso. Il lavoro già registrato resta registrato. Dalla chat non si può disfare.')],
      estop: [L('Emergency stop', 'Arresto d\'emergenza'), L('Stops every running execution, not only their scheduling, and blocks new dispatch until you re-arm in Settings (a step-up). This cannot be undone from chat.', 'Ferma ogni esecuzione in corso, non solo la loro pianificazione, e blocca ogni nuovo avvio finché non riarmi in Impostazioni (conferma rafforzata). Dalla chat non si può disfare.')],
      cancel: [L('Cancel', 'Annulla'), L('Cancels the mission. It cannot undo effects an earlier run may have had.', 'Annulla la missione. Non può disfare gli effetti che un\'esecuzione precedente può aver avuto.')],
      pause: [L('Pause', 'Pausa'), L('Halts the work at a safe boundary. You can resume it.', 'Ferma il lavoro a un confine sicuro. Puoi riprenderlo.')],
      resume: [L('Resume', 'Riprendi'), L('A new dispatch may spend usage. Account and cost: Unknown.', 'Un nuovo avvio può consumare quota. Account e costo: Sconosciuti.')] }[c.action];
    if (c.step === 'done') return box('confirm', [kicker('✓', V[0]), done(L('Done for {n}: {t}.', 'Fatto per {n}: {t}.', { n: c.n || ts.length, t: name })), h('p', { class: 'sp-text' }, SIMLINE())]);
    if (c.step === 'dismissed') return box('confirm', [kicker('○', L('Dismissed', 'Scartata')), done(L('Nothing was done.', 'Non è stato fatto nulla.'))]);
    if (c.step === 'stale') return box('confirm', [kicker('○', L('No longer applies', 'Non si applica più')), done(c.note)]);
    const two = ['stop', 'estop', 'cancel'].includes(c.action), second = c.step === 'confirm';
    return box('confirm', [kicker('◆', L('Proposed · nothing has happened', 'Proposta · non è successo nulla'), 'needs_you'), h('p', { class: 'ctitle' }, second ? L('Confirm: {a} {t} now?', 'Conferma: {a} {t} adesso?', { a: V[0].toLowerCase(), t: name }) : L('{a} {t}?', '{a} {t}?', { a: V[0], t: name })),
      h('p', { class: 'sp-text' }, V[1]), two ? h('p', { class: 'sp-text step' }, second ? L('Step 2 of 2', 'Passo 2 di 2') : L('Step 1 of 2', 'Passo 1 di 2')) : null,
      h('div', { class: 'actions' }, second ? [B(L('Yes, {a}', 'Sì, {a}', { a: V[0].toLowerCase() }), 'yes', 'danger'), B(L('Back', 'Indietro'), 'back')] : [B(two ? L('{a} mission', '{a} missione', { a: V[0] }) : V[0], two ? 'step2' : 'yes', two ? 'danger' : 'primary'), B(L('Cancel', 'Annulla'), 'dismiss')])]);
  }
  if (c.kind === 'approval') {
    const a = st.approvals[c.approval], am = a ? st.missions[a.mission] : null;
    if (!a) return box('approval', [done(L('This decision no longer exists.', 'Questa decisione non esiste più.'))]);
    if (c.step === 'stale') return box('approval', [kicker('○', L('No longer waiting', 'Non è più in attesa')), done(c.note)]);
    if (a.state !== 'PENDING') return box('approval', [kicker(a.state === 'REJECTED' ? '✕' : '✓', present('approval', a.state).label), done(L('Decided by {w}. {s}', 'Deciso da {w}. {s}', { w: a.decided_by === 'user_device' ? L('you', 'te') : L('Core', 'il Core'), s: '' })), h('p', { class: 'sp-text' }, SIMLINE())]);
    const step = c.step === 'stepup';
    return box('approval', [kicker('◆', a.kind === 'plan' ? L('Approve this plan?', 'Approvare questo piano?') : L('Allow this action?', 'Consentire questa azione?'), 'needs_you'), h('p', { class: 'ctitle' }, am ? am.title : ''),
      kv([L('What', 'Cosa'), a.presented.what], [L('Why it asks', 'Perché lo chiede'), a.presented.why], [L('What Core does next', 'Cosa fa il Core dopo'), a.presented.consequence], [L('Bound to', 'Legata a'), L('action hash {h} · plan version {v}', 'hash dell\'azione {h} · versione del piano {v}', { h: (a.id + '9f3c').slice(0, 8), v: am ? am.plan_version || 1 : 1 })]),
      step ? h('p', { class: 'cstep' }, L('Step-up needed: confirm it is you before this is {w}. (Simulated step-up.)', 'Serve la conferma d\'identità: conferma che sei tu prima che sia {w}. (Conferma simulata.)', { w: c.pick === 'approve' ? L('approved', 'approvata') : L('rejected', 'rifiutata') })) : h('p', { class: 'sp-text' }, L('Only this card’s own button decides. A message or a bare “yes” never does.', 'Decide solo il pulsante di questa scheda. Un messaggio o un semplice “sì” non decide mai.')),
      h('div', { class: 'actions' }, step ? [B(c.pick === 'approve' ? L('Confirm approval', 'Conferma l\'approvazione') : L('Confirm rejection', 'Conferma il rifiuto'), 'confirm', c.pick === 'approve' ? 'primary' : 'danger'), B(L('Back', 'Indietro'), 'back')] : [B(L('Approve', 'Approva'), 'approve', 'primary'), B(L('Reject', 'Rifiuta'), 'reject', 'danger'), h('a', { class: 'btn', href: off ? '#/chat' : '#/attention/' + a.id }, L('Open decision', 'Apri la decisione'))]), h('p', { class: 'sp-text' }, SIMLINE())]);
  }
  if (c.kind === 'remember') {
    const scopeName = c.scope === 'all' ? L('all projects', 'tutti i progetti') : c.scope ? pname(sim, c.scope) : '';
    if (c.step === 'done') return box('remember', [kicker('✓', L('Remembered', 'Ricordato')), done(L('Remembered for {s}: “{t}” (item {i}).', 'Ricordato per {s}: “{t}” (voce {i}).', { s: scopeName, t: c.excerpt, i: c.item })), h('p', { class: 'sp-text' }, SIMLINE())]);
    if (c.step === 'dismissed') return box('remember', [kicker('○', L('Not remembered', 'Non ricordato')), done(L('Nothing was written.', 'Non è stato scritto nulla.'))]);
    const ta = h('textarea', { class: 'cta', rows: 2, 'aria-label': L('What to remember', 'Cosa ricordare'), maxlength: 300, readonly: off ? true : null, oninput: (e) => { if (!off) c.excerpt = e.target.value; } }); ta.value = c.excerpt || '';
    const sel = h('select', { 'aria-label': L('Remember in', 'Ricorda in'), 'aria-disabled': off ? 'true' : null, onchange: (e) => { if (!off) { c.scope = e.target.value; act(m.id, 'scope', { scope: e.target.value }); } } },
      h('option', { value: '' }, L('Choose where…', 'Scegli dove…')), ...st.projects.map((p) => h('option', { value: p.id }, p.name)), h('option', { value: 'all' }, L('All projects', 'Tutti i progetti')));
    sel.value = c.scope || '';
    return box('remember', [kicker('◆', scopeName ? L('Remember in {s}?', 'Ricordare in {s}?', { s: scopeName }) : L('Remember in…', 'Ricorda in…'), 'needs_you'),
      h('label', { class: 'cfield' }, h('span', null, L('What to remember', 'Cosa ricordare')), ta), h('label', { class: 'cfield' }, h('span', null, L('Remember in', 'Ricorda in')), sel),
      h('p', { class: 'sp-text' }, L('Nothing is written until you confirm. There is no silent global memory. Conversation retention: Unknown.', 'Non si scrive nulla finché non confermi. Non esiste memoria globale implicita. Conservazione della conversazione: Sconosciuta.')),
      h('div', { class: 'actions' }, B(L('Remember', 'Ricorda'), 'save', 'primary', { excerpt: null }), B(L('Cancel', 'Annulla'), 'dismiss'))]);
  }
  if (c.kind === 'general') return box('general', [h('p', { class: 'gtag' }, L('General · not project memory', 'Generale · non è memoria di progetto')),
    h('p', { class: 'sp-text' }, L('No star, no link, no activity for a general answer. “Not project memory” does not mean “not stored”.', 'Nessuna stella, nessun collegamento, nessuna attività per una risposta generale. “Non è memoria di progetto” non vuol dire “non archiviato”.')),
    h('p', { class: 'sp-text' }, L('Account selected by Core · Usage: Unknown · Conversation retention: Unknown', 'Account scelto dal Core · Utilizzo: Sconosciuto · Conservazione della conversazione: Sconosciuta')),
    c.state === 'open' ? h('div', { class: 'actions' }, B(L('Remember in…', 'Ricorda in…'), 'remember')) : null]);
  if (c.kind === 'choice') {
    if (c.state === 'done') return box('choice', [done(c.step === 'general' ? L('Answered in General.', 'Risposto in Generale.') : L('Sent as work.', 'Inviato come lavoro.'))]);
    return box('choice', [kicker('?', L('Answer this, or create work?', 'Rispondo a questo, o creo del lavoro?')), h('p', { class: 'quote' }, c.text), h('p', { class: 'sp-text' }, L('Nothing was created and nothing was sent anywhere yet.', 'Non è stato creato nulla e non è stato inviato nulla.')),
      h('div', { class: 'actions' }, B(L('Answer in General', 'Rispondi in Generale'), 'general', 'primary'), B(L('Create work', 'Crea lavoro'), 'work'))]);
  }
  if (c.kind === 'pick') return box('pick', [kicker('?', L('Pick one. Nothing was sent.', 'Scegline una. Non è stato inviato nulla.')), c.state === 'done' ? done(L('Picked.', 'Scelta.')) : h('ol', { class: 'cpick' }, ...c.options.map((o, i) => h('li', null, h('button', { class: 'btn crow', type: 'button', 'aria-disabled': off ? 'true' : null, onclick: A('pick', { id: o.id }) }, h('span', { class: 'cl' }, (i + 1) + '. ' + o.label), h('span', { class: 'cm' }, o.meta))))), c.more ? h('p', { class: 'sp-text' }, L('+{n} more', '+{n} altri', { n: c.more })) : null]);
  if (c.kind === 'refusal') return box('refusal', [kicker('■', L('Not from chat', 'Non dalla chat'), 'blocked'), c.href ? h('div', { class: 'actions' }, h('a', { class: 'btn', href: c.href }, c.href === '#/attention' ? L('Open Attention', 'Apri Attenzione') : c.href === '#/security' ? L('Open Security', 'Apri Sicurezza') : L('Open Work', 'Apri Lavoro'))) : null]);
  return null;
}

// ----- one message -----
export function msgNode(ctx, m, act, retry) {
  const sim = ctx.sim, you = m.from === 'you', gen = m.dest === 'general';
  const body = m.c && !you ? C(m.c) : m.text;
  const status = you && !m.local ? (m.status === 'submitted' ? h('p', { class: 'mstat' }, L('Submitted.', 'Inviato.')) : m.status === 'failed' ? h('p', { class: 'mstat bad' }, L('Not sent. Send again?', 'Non inviato. Rimandare?'), ' ', btn(L('Send again', 'Rimanda'), () => retry(m.id), 'quiet')) : null) : null;
  return h('article', { class: 'msg ' + (you ? 'you' : 'archeus') + (gen ? ' general' : ''), 'data-key': 'msg-' + m.id, 'data-dest': m.dest || null },
    h('p', { class: 'who' }, h('span', null, (you ? L('You', 'Tu') : 'Archeus') + ' · ' + clockLabel(m.at)), m.dest ? h('span', { class: 'dest' }, destLabel(sim, m)) : null, !you && m.c ? h('span', { class: 'sim-tag' }, L('SIMULATED', 'SIMULATO')) : null),
    h('p', { class: 'mbody' }, body), status, cardNode(ctx, m, act, false),
    !you && m.local ? h('p', { class: 'sp-text lc' }, L('Local view: READ and NAVIGATE answers are not recorded.', 'Vista locale: le risposte READ e NAVIGATE non vengono registrate.')) : null);
}
