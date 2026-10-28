// The V2 Live chat brain (S4). DOM-free, no Core. It reads the simulation, writes its records through sim.chat (every record has an event),
// and only ever PROPOSES effects: an effect runs when the owner confirms the card (T-153 P5, CHAT-control-catalogue "reads and creates, not effects").
// Truth rules kept here: READ and NAVIGATE are not recorded (a local echo); CREATE and PROPOSE are recorded; "Not started" is said only when true;
// general answers are not project memory; retention is Unknown; a bare approve is declined; model-like text is never parsed for commands.
import { parse, find, nameIn, looksSecret } from './slash.js';
import { present } from './core-words.js';

export const tp = (en, it, v) => ({ en, it, v: v || {} });
export const fmt = (c, lang) => String((lang === 'it' ? c.it : c.en)).replace(/\{(\w+)\}/g, (_, k) => (c.v[k] == null ? '' : c.v[k]));

const norm = (s) => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
const words = (s) => norm(s).split(/[^a-z0-9]+/).filter(Boolean);
const lev = (a, b) => { let p = Array.from({ length: b.length + 1 }, (_, j) => j); for (let i = 1; i <= a.length; i++) { const c = [i]; for (let j = 1; j <= b.length; j++) c[j] = Math.min(p[j] + 1, c[j - 1] + 1, p[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)); p = c; } return p[b.length]; };

// Fixture route decisions for /why (SIMULATED: no Core, no router).
const WHY = {
  'rd-1': ['Core elected the work account for “Fix date test” because the personal account was near its ceiling.', 'Il Core ha scelto l\'account di lavoro per “Fix date test” perché quello personale era vicino al limite.'],
  'rd-2': ['Core elected Sonnet 5.5 for the plan of “Search provenance”: the plan needs the large tier.', 'Il Core ha scelto Sonnet 5.5 per il piano di “Search provenance”: il piano richiede il livello grande.'],
  'rd-3': ['Core held the dispatch of “Voice notes prototype” because you paused it. A pause is yours to release.', 'Il Core ha trattenuto l\'avvio di “Voice notes prototype” perché l\'hai messa in pausa. Una pausa la rilasci tu.']
};
const GENERAL = [
  [/replay|recover|reconcil|checkpoint/i, tp('A Replay shows what was intended, what you authorized, what was durably recorded, what may have taken effect and where the state is uncertain. Recovery proposes new work; it never claims an external effect can be undone.', 'Un Replay mostra cosa era previsto, cosa hai autorizzato, cosa è stato registrato in modo durevole, cosa può aver avuto effetto e dove lo stato è incerto. Il recupero propone nuovo lavoro; non afferma mai che un effetto esterno si possa annullare.')],
  [/approv|decid/i, tp('An approval is bound to one action and one version. Changing the plan or the target makes an earlier confirmation stale. A bare “yes” never approves.', 'Un\'approvazione è legata a una sola azione e a una sola versione. Cambiare il piano o il bersaglio rende vecchia la conferma precedente. Un semplice “sì” non approva mai.')],
  [/pause|stop/i, tp('Pause halts work at a safe boundary and can be resumed. Stop ends the running execution and cannot be undone from chat. Emergency stop pauses everything that runs.', 'La pausa ferma il lavoro a un confine sicuro e si può riprendere. L\'arresto termina l\'esecuzione in corso e non si disfa dalla chat. L\'arresto d\'emergenza mette in pausa tutto ciò che gira.')],
  [/mission|project|idea/i, tp('A project holds missions; a mission is one piece of work with a plan, tasks and runs; an idea is a note that is not a commitment.', 'Un progetto contiene missioni; una missione è un lavoro con un piano, attività ed esecuzioni; un\'idea è una nota che non è un impegno.')]
];
const GENERAL_DEFAULT = tp('This is not about a project, so it stays in the general thread. This prototype answers with fixed text; a real build answers through the official CLI on the account Core selects. Nothing here reaches project memory unless you remember it.', 'Non riguarda un progetto, quindi resta nel thread generale. Questo prototipo risponde con testo fisso; una versione reale risponde tramite la CLI ufficiale sull\'account scelto dal Core. Niente qui entra nella memoria dei progetti se non lo ricordi tu.');
const WORKWORD = /\b(create|add|make|new|start|run|remember|plan|idea|project|mission|draft|promote)\b/i;
const QUESTION = /^(what|why|how|who|when|where|which|is|are|does|do|can|cosa|perch[eé]|come|chi|quando|dove|quale|[eè])\b/i;

export function createChat(sim, env = {}) {
  const now = env.now || (() => Date.now());
  const S = () => sim.state;
  let local = [], ln = 0, last = { text: '', at: -1e9 }, kn = 0, hide = null, done = new Set();
  const api = { onChange: null, local: () => local };
  const changed = () => { if (api.onChange) api.onChange(); };
  const word = (m) => present('mission', m.state).label;
  const pname = (id) => { const p = S().projects.find((x) => x.id === id); return p ? p.name : id; };

  // ---------- messages: recorded ones live in the simulation, READ and NAVIGATE echoes stay local (T-153 P3) ----------
  function post(from, c, extra, recorded) {
    const m = Object.assign({ from, text: fmt(c, 'en'), c, at: S().clock }, extra || {});
    if (recorded) { const ex = Object.assign({}, m); delete ex.from; delete ex.at; delete ex.text; return sim.chat.post(from, m.text, ex); }
    m.id = 'l-' + (++ln); m.ref = S().messages.length; m.local = true; local.push(m); changed(); return m;
  }
  const originOf = (m) => ({ project: m.project, mission: Object.values(S().missions).find((x) => m.args && (x.id === m.args || x.title.toLowerCase() === m.args.toLowerCase()))?.id || null });
  const get = (id) => (String(id).startsWith('l-') ? local.find((x) => x.id === id) : S().messages.find((x) => x.id === id));
  function patch(id, fields) {
    const m = get(id); if (!m) return null;
    if (m.local) { Object.assign(m, fields); changed(); return m; }
    return sim.chat.patch(id, fields);
  }
  function thread() {
    const out = [], gone = (m, i) => hide && (m.local ? i < hide.n : false);
    local.forEach((m, j) => { if (m.ref === 0 && !gone(m, j)) out.push(m); });
    S().messages.forEach((m, i) => {
      if (!hide || i >= hide.ref) out.push(m);
      local.forEach((l, j) => { if (l.ref === i + 1 && !gone(l, j)) out.push(l); });
    });
    return out;
  }
  const reset = () => { local = []; ln = 0; hide = null; done = new Set(); last = { text: '', at: -1e9 }; };
  sim.subscribe((e) => { if (e.type === 'sim.reset') reset(); });

  // ---------- queue and steer ----------
  // While a mission runs, plain text sent with mode 'queue' waits for the end of the step; mode 'steer' asks to be taken at the next safe boundary and
  // stays 'steering' until Core acknowledges. With nothing running both just send. The state lives on the recorded message (status, target).
  const running = (project) => Object.values(S().missions).filter((x) => x.state === 'EXECUTING' && (!project || x.project === project));
  api.running = running;
  api.queued = (project) => S().messages.filter((x) => x.status === 'queued' && (!project || x.project === project));
  api.unqueue = (id) => { const m = get(id); if (!m || m.status !== 'queued') return false; patch(id, { status: 'withdrawn' }); return true; };
  sim.subscribe((e) => {
    if (e.type === 'mission.state_changed' && e.payload.from === 'EXECUTING') api.queued().filter((m) => m.target === e.mission).forEach((m) => { patch(m.id, { status: 'submitted' }); api.finish(m.id); });
    if (e.type === 'mission.steer_acknowledged') {
      const m = get(e.payload.message), x = S().missions[e.mission];
      if (m && m.status === 'steering' && x) {
        patch(m.id, { status: 'sent' });
        post('archeus', tp('SIMULATED · Core acknowledged the steer for “{t}”. A real Core would record the request and the safe boundary where it took effect; here nothing changed course.', 'SIMULATO · Il Core ha confermato la richiesta di guida per “{t}”. Un Core reale registrerebbe la richiesta e il confine sicuro in cui ha avuto effetto; qui nulla ha cambiato rotta.', { t: x.title }), { dest: 'work', project: x.project, mission: x.id }, true);
      }
    }
  });

  // ---------- resolving a name: exact, word prefix, substring, fuzzy (T-153 section 2). Never a silent first pick ----------
  function resolve(q0, kinds) {
    const q = norm(String(q0).replace(/^@/, '').replace(/^"|"$/g, ''));
    const pool = [];
    if (kinds.includes('mission')) Object.values(S().missions).forEach((m) => pool.push({ kind: 'mission', id: m.id, name: m.title, meta: word(m) }));
    if (kinds.includes('project')) S().projects.forEach((p) => pool.push({ kind: 'project', id: p.id, name: p.name, meta: tp('project', 'progetto').en }));
    if (!q) return { none: true, closest: [] };
    const tiers = [
      (x) => norm(x.name) === q || x.id === q || x.id === 'm-' + q,
      (x) => words(x.name).some((w) => w.startsWith(q)) || norm(x.name).startsWith(q),
      (x) => norm(x.name).includes(q),
      (x) => { const n = norm(x.name), max = q.length >= 4 && q.length <= 7 ? 1 : q.length > 7 ? 2 : 0; return max > 0 && (lev(q, n) <= max || words(x.name).some((w) => lev(q, w) <= max)); }
    ];
    for (const t of tiers) {
      const hit = pool.filter(t);
      if (hit.length === 1) return { one: hit[0] };
      if (hit.length > 1) { const ex = hit.filter((x) => norm(x.name) === q || x.id === q); if (ex.length === 1) return { one: ex[0] }; return { many: hit.slice(0, 5), more: Math.max(0, hit.length - 5) }; }
    }
    return { none: true, closest: pool.map((x) => ({ x, d: lev(q, norm(x.name).slice(0, Math.max(q.length, 3))) })).sort((a, b) => a.d - b.d).slice(0, 3).map((o) => o.x.name) };
  }
  const refReply = (r, q) => (r.none
    ? { c: tp('No project or mission named “{q}”. Closest: {list}.', 'Nessun progetto o missione di nome “{q}”. Più simili: {list}.', { q, list: r.closest.join(', ') || '-' }) }
    : { c: tp('More than one matches “{q}”. Pick one; nothing was sent.', 'Più di una corrisponde a “{q}”. Scegline una; non è stato inviato nulla.', { q }), card: { kind: 'pick', options: r.many.map((x) => ({ id: x.id, label: x.name, meta: x.meta })), more: r.more, state: 'open' } });

  const lines = (items, more) => ({ kind: 'list', items, more: more || 0 });
  const missionRows = (ms) => ms.map((m) => ({ label: m.title, meta: word(m) + ' · ' + pname(m.project), href: '#/work/' + m.id }));
  const BASED = tp('Based on available Core context.', 'In base al contesto disponibile del Core.');

  // ---------- what one command answers ----------
  function readCmd(name, args) {
    const st = S(), ms = Object.values(st.missions);
    if (name === 'help') return { c: tp('The commands, by class. READ and NAVIGATE answer, CREATE writes one record, PROPOSE only makes a card you confirm.', 'I comandi, per classe. READ e NAVIGATE rispondono, CREATE scrive un record, PROPOSE crea solo una scheda che confermi tu.'), card: { kind: 'help', arg: args } };
    if (name === 'status') { const n = sim.counts(); return { c: BASED, card: { kind: 'status', running: n.running, waiting: n.need, stopped: n.stopped, estop: st.estop.engaged, at: st.clock } }; }
    if (name === 'usage') return { c: tp('Usage is Unknown. The read is not built yet (T-154); Archeus shows no number it cannot source.', 'L\'utilizzo è Sconosciuto. La lettura non esiste ancora (T-154); Archeus non mostra numeri che non può documentare.'), card: { kind: 'usage', rows: st.accounts.filter((a) => !args || norm(a.label).includes(norm(args))).map((a) => a.label) } };
    if (name === 'projects') return { c: BASED, card: lines(st.projects.map((p) => ({ label: p.name, meta: ms.filter((m) => m.project === p.id && !['COMPLETED', 'CANCELLED'].includes(m.state)).length + ' open', href: '#/now' }))) };
    if (name === 'missions') {
      let list = ms, p = null;
      if (args) { const r = resolve(args, ['project']); if (!r.one) return refReply(r, args); p = r.one; list = ms.filter((m) => m.project === p.id); }
      return { c: BASED, card: lines(missionRows(list.slice(0, 10)), Math.max(0, list.length - 10)) };
    }
    if (name === 'needs') { const a = sim.attention().filter((x) => x.kind !== 'knowledge'); return { c: a.length ? tp('{n} wait for you. Nothing is decided here; each row opens its card.', '{n} aspettano te. Qui non si decide nulla; ogni riga apre la sua scheda.', { n: a.length }) : tp('Nothing waits for you.', 'Niente aspetta te.'), card: a.length ? lines(a.map((x) => ({ label: x.reason, meta: x.group, href: x.kind === 'approval' ? '#/work/' + x.ref : '#/work' }))) : null }; }
    if (name === 'digest') {
      const since = st.clock - 3600000, ev = st.events.filter((e) => e.at >= since);
      const n = (re) => ev.filter((e) => re.test(e.type)).length;
      return { c: tp('Since you left (the last simulated hour).', 'Da quando sei andato via (l\'ultima ora simulata).'), card: lines([{ label: n(/^mission\.state_changed$/) + ' mission state changes', meta: '', href: '#/work' }, { label: n(/^approval\.requested$/) + ' approvals requested', meta: '', href: '#/work' }, { label: n(/^idea\.created$/) + ' ideas captured', meta: '', href: '#/work' }]) };
    }
    if (name === 'ideas') return { c: BASED, card: lines(st.ideas.map((i) => ({ label: i.title, meta: present('idea', i.state).label + ' · ' + pname(i.project), href: '#/work' }))) };
    if (name === 'search') {
      const q = norm(args), hit = [];
      ms.filter((m) => norm(m.title).includes(q)).forEach((m) => hit.push({ label: m.title, meta: 'mission · ' + word(m), href: '#/work/' + m.id }));
      st.projects.filter((p) => norm(p.name).includes(q)).forEach((p) => hit.push({ label: p.name, meta: 'project', href: '#/now' }));
      st.ideas.filter((i) => norm(i.title).includes(q)).forEach((i) => hit.push({ label: i.title, meta: 'idea', href: '#/work' }));
      return hit.length ? { c: tp('{n} found for “{q}”. A row opens the object.', '{n} trovati per “{q}”. Una riga apre l\'oggetto.', { n: hit.length, q: args }), card: lines(hit.slice(0, 8), Math.max(0, hit.length - 8)) } : { c: tp('Nothing found for “{q}”.', 'Niente trovato per “{q}”.', { q: args }) };
    }
    if (name === 'why') {
      const w = WHY[norm(args)];
      return w ? { c: tp(w[0], w[1]), card: { kind: 'why', id: norm(args) } } : { c: tp('No route decision “{q}”. Closest: rd-1, rd-2, rd-3.', 'Nessuna decisione di instradamento “{q}”. Più vicine: rd-1, rd-2, rd-3.', { q: args }) };
    }
    if (name === 'plan') { const r = resolve(args, ['mission']); if (!r.one) return refReply(r, args); return { c: tp('The plan of “{t}”.', 'Il piano di “{t}”.', { t: r.one.name }), card: { kind: 'plan', mission: r.one.id } }; }
    if (name === 'trace' || name === 'open' || name === 'replay' || name === 'focus') {
      if (name === 'replay' && !args) { const m = ms.slice().sort((a, b) => b.updated_at - a.updated_at)[0]; return { c: tp('Opening the Replay of “{t}”, the latest.', 'Apro il Replay di “{t}”, l\'ultima.', { t: m.title }), nav: '#/replay/' + m.id }; }
      const r = resolve(args, name === 'focus' ? ['project'] : name === 'open' ? ['mission', 'project'] : ['mission']); if (!r.one) return refReply(r, args);
      const x = r.one;
      if (name === 'focus' || x.kind === 'project') return { c: tp('Focusing the map on {t}.', 'Porto la mappa su {t}.', { t: x.name }), nav: '#/now' };
      if (name === 'replay') return { c: tp('Opening the Replay of “{t}”.', 'Apro il Replay di “{t}”.', { t: x.name }), nav: '#/replay/' + x.id };
      if (name === 'trace') return { c: tp('Opening the trace of “{t}”.', 'Apro la traccia di “{t}”.', { t: x.name }), nav: '#/work/' + x.id, tab: 'timeline' };
      return { c: tp('Opening “{t}”.', 'Apro “{t}”.', { t: x.name }), nav: '#/work/' + x.id };
    }
    if (name === 'clear') { hide = { ref: st.messages.length, n: local.length }; return { c: null, cleared: true }; }
    if (name === 'theme') return { c: tp('Theme set to {v} on this device.', 'Tema impostato su {v} su questo dispositivo.', { v: args }), pref: ['theme', args.toLowerCase()] };
    if (name === 'motion') return { c: tp('Motion set to {v} on this device. The facts stay the same.', 'Movimento impostato su {v} su questo dispositivo. I fatti restano gli stessi.', { v: args }), pref: ['motion', args.toLowerCase() === 'full' ? 'full' : 'reduced'] };
    return null;
  }

  function mentionProject(args) {
    const m = /(?:^|\s)@("[^"]+"|\S+)/.exec(args);
    if (!m) return { text: args, project: null };
    const r = resolve(m[1], ['project']);
    return { text: args.replace(m[0], ' ').replace(/\s+/g, ' ').trim(), project: r.one ? r.one.id : null, bad: r.one ? null : m[1] };
  }
  const startCard = (id) => ({ kind: 'start', mission: id, step: 'ask', state: 'open' });

  function createCmd(name, args, o) {
    if (name === 'mission') {
      const { text, project, bad } = mentionProject(args);
      if (bad) return { c: tp('No project “{q}”. Nothing was created.', 'Nessun progetto “{q}”. Non è stato creato nulla.', { q: bad }) };
      const m = sim.chat.createMission(text || args, project || o.project || 'archeus');
      return { c: tp('Created “{t}” in {p}. Not started. Starting it needs your approval.', 'Creata “{t}” in {p}. Non avviata. Per avviarla serve la tua approvazione.', { t: m.title, p: pname(m.project) }), card: startCard(m.id), created: { kind: 'mission', id: m.id } };
    }
    if (name === 'idea') { const i = sim.chat.createIdea(args, o.project === 'archeus' ? 'archeus' : 'ideas'); return { c: tp('Idea captured. It is not a commitment.', 'Idea catturata. Non è un impegno.'), card: { kind: 'created', what: 'idea', title: i.title, id: i.id, project: pname(i.project), href: '#/work' }, created: { kind: 'idea', id: i.id } }; }
    if (name === 'feedback') { const k = sim.chat.addKnowledge({ project: o.project || 'archeus', text: args, source: 'feedback' }); return { c: tp('Feedback saved as a candidate.', 'Feedback salvato come candidato.'), card: { kind: 'created', what: 'feedback', title: k.text, id: k.id, project: pname(k.project), href: '#/work' }, created: { kind: 'knowledge_item', id: k.id } }; }
    if (name === 'remember') return { c: tp('Nothing is written until you confirm where to remember it.', 'Non si scrive nulla finché non confermi dove ricordarlo.'), card: { kind: 'remember', excerpt: args, scope: o.dest === 'general' ? '' : (o.project || 'archeus'), step: 'ask', state: 'open' } };
    return null;
  }

  function general(q) {
    const hit = GENERAL.find(([re]) => re.test(q));
    return { c: hit ? hit[1] : GENERAL_DEFAULT, card: { kind: 'general', question: q, state: 'open' }, general: true };
  }

  const MISSION_NEED = { pause: ['EXECUTING', 'running'], resume: ['PAUSED', 'paused'], stop: ['EXECUTING', 'running'] };
  function proposeCmd(name, args) {
    const st = S();
    if (name === 'estop' || (name === 'pause' && norm(args) === 'all')) {
      const run = Object.values(st.missions).filter((m) => m.state === 'EXECUTING');
      if (name === 'estop' && st.estop.engaged) return { c: tp('The emergency stop is already engaged. Nothing new starts until you re-arm it in Settings; that needs a step-up and is not done from chat.', 'L\'arresto d\'emergenza è già attivo. Non parte nulla di nuovo finché non lo riarmi in Impostazioni; serve una conferma rafforzata e non si fa dalla chat.'), card: { kind: 'link', text: 'Open Settings', href: '#/settings' } };
      if (!run.length && name !== 'estop') return { c: tp('Nothing is running, so there is nothing to pause.', 'Niente è in esecuzione, quindi non c\'è nulla da mettere in pausa.') };
      return { c: name === 'estop' ? tp('Emergency stop is a proposal. Nothing has happened.', 'L\'arresto d\'emergenza è una proposta. Non è successo nulla.') : tp('Pausing everything that runs is a proposal. Nothing has happened.', 'Mettere in pausa tutto ciò che gira è una proposta. Non è successo nulla.'), card: { kind: 'confirm', action: name === 'estop' ? 'estop' : 'pause', targets: run.map((m) => m.id), step: 'ask', state: 'open' } };
    }
    if ((name === 'approve' || name === 'reject') && st.approvals[norm(args)]) {
      const a = st.approvals[norm(args)], mm = st.missions[a.mission];
      return a.state === 'PENDING' ? { c: tp('Approval {id} is open for “{t}”. The command decides nothing; only the card’s own button does.', 'L’approvazione {id} è aperta per “{t}”. Il comando non decide nulla; decide solo il pulsante della scheda.', { id: a.id, t: mm.title }), card: { kind: 'approval', approval: a.id, step: 'ask', state: 'open' } } : { c: tp('Approval {id} is already {w}.', 'L’approvazione {id} è già {w}.', { id: a.id, w: a.state.toLowerCase() }) };
    }
    const r = resolve(args, ['mission']); if (!r.one) return refReply(r, args);
    const m = st.missions[r.one.id], t = { t: m.title };
    if (name === 'review') return m.state === 'REVIEWING' ? { c: tp('“{t}” waits for your review. The command decides nothing.', '“{t}” aspetta la tua revisione. Il comando non decide nulla.', t), card: { kind: 'link', text: 'Open the review', href: '#/work/' + m.id } } : { c: tp('“{t}” has no review waiting.', '“{t}” non ha revisioni in attesa.', t) };
    if (name === 'approve' || name === 'reject') {
      const a = Object.values(st.approvals).find((x) => x.mission === m.id && x.state === 'PENDING');
      return a ? { c: tp('A decision waits on “{t}”. The command decides nothing; only the card’s own button does.', 'Una decisione aspetta su “{t}”. Il comando non decide nulla; decide solo il pulsante della scheda.', t), card: { kind: 'approval', approval: a.id, step: 'ask', state: 'open' } } : { c: tp('“{t}” has no decision waiting.', '“{t}” non ha decisioni in attesa.', t) };
    }
    if (name === 'start') return m.state === 'CREATED' ? { c: tp('Starting “{t}” is a proposal. Nothing has started.', 'Avviare “{t}” è una proposta. Non è partito nulla.', t), card: startCard(m.id) } : { c: tp('“{t}” is {w}, so /start does not apply.', '“{t}” è {w}, quindi /start non si applica.', { t: m.title, w: word(m).toLowerCase() }) };
    if (name === 'cancel') return edge(m.state, 'CANCELLED', 'cancel') ? { c: tp('Cancelling “{t}” is a proposal and cannot be undone. Nothing has happened.', 'Annullare “{t}” è una proposta e non si può disfare. Non è successo nulla.', t), card: { kind: 'confirm', action: 'cancel', targets: [m.id], step: 'ask', state: 'open' } } : { c: tp('“{t}” is {w} and cannot be cancelled here.', '“{t}” è {w} e non si può annullare da qui.', { t: m.title, w: word(m).toLowerCase() }) };
    const need = MISSION_NEED[name];
    if (need && m.state !== need[0]) return { c: tp('“{t}” is {w}, so /{n} does not apply.', '“{t}” è {w}, quindi /{n} non si applica.', { t: m.title, w: word(m).toLowerCase(), n: name }) };
    return { c: tp('{v} “{t}” is a proposal. Nothing has happened.', '“{t}”: {v} è una proposta. Non è successo nulla.', { v: name[0].toUpperCase() + name.slice(1), t: m.title }), card: { kind: 'confirm', action: name, targets: [m.id], step: 'ask', state: 'open' } };
  }
  const edge = (s, to, trig) => sim.edgeOk('mission', s, to, trig);

  // ---------- plain text: scripted, deterministic, honest about what is faked ----------
  const REFUSE = [
    [/^(approve|reject|yes|ok|okay|si|sì|approva|rifiuta|confirm|confirmed)[.!]*$/i, tp('A bare word never approves. Open the decision card; only its own button decides, bound to its hash.', 'Una parola da sola non approva mai. Apri la scheda della decisione; decide solo il suo pulsante, legato al suo hash.'), '#/work'],
    [/\b(delete|remove|archive|wipe)\b.*\b(all|every)\b|\b(delete|archive)\b.*\bmissions?\b/i, tp('I can’t do that from chat; open Work. Deleting or archiving needs a card.', 'Non posso farlo dalla chat; apri Lavoro. Eliminare o archiviare richiede una scheda.'), '#/work'],
    [/\b(run|execute|exec)\b.*\b(command|shell|script|bash|powershell)\b|\bsudo\b|\brm -rf\b/i, tp('I can’t do that from chat; open Work. A command, shell or script never runs from here.', 'Non posso farlo dalla chat; apri Lavoro. Un comando, una shell o uno script non girano mai da qui.'), '#/work'],
    [/\b(change|set|edit|update)\b.*\b(policy|permissions?|limit|budget|hook|token|password)\b|\b(token|password|credential)s?\b/i, tp('I can’t do that from chat; open Work. Policy, limits and credentials are never changed from here.', 'Non posso farlo dalla chat; apri Lavoro. Policy, limiti e credenziali non si cambiano mai da qui.'), '#/security']
  ];
  function plainWork(text, o) {
    const ref = REFUSE.find(([re]) => re.test(text));
    if (ref) return { c: ref[1], card: { kind: 'refusal', href: ref[2], state: 'open' } };
    if (/^remember\b/i.test(text)) return createCmd('remember', text.replace(/^remember\s*/i, ''), o);
    const proj = /\b(create|add|new|make)\b.*\bproject\b\s*(?:called|named)?\s*["“]?([\w][\w \-]{1,30})/i.exec(text);
    if (proj && !/\bmission\b/i.test(text)) {
      const p = sim.chat.createProject(proj[2].trim().replace(/\s+(and|to)\b.*$/i, ''));
      return { c: tp('SIMULATED · Project “{t}” created in this demo. Core chat creation is not connected. It is a record only; folders, clones and access are proposals.', 'SIMULATO · Progetto “{t}” creato in questa demo. La creazione da chat nel Core non è collegata. È solo un record; cartelle, cloni e accessi sono proposte.', { t: p.name }), card: { kind: 'created', what: 'project', title: p.name, id: p.id, project: p.name, href: '#/now' }, created: { kind: 'project', id: p.id } };
    }
    if (/\bidea\b/i.test(text) && !/\bmission\b/i.test(text)) return createCmd('idea', text.replace(/^.*?\bidea\b[:\s,-]*/i, '').replace(/^(for|about|to|that)\s+/i, '') || text, o);
    const mis = /\b(create|add|make|new|draft|open)\b.*\bmission\b(?:\s+(?:to|for|called|named|:))?\s*(.*)$/i.exec(text) || /^mission\s+(.+)$/i.exec(text);
    if (mis) {
      let t = (mis[2] || mis[1] || '').replace(/\s+and\s+(start|run|plan)\b.*$/i, '').replace(/^[“"]|[”"]$/g, '').trim();
      t = t ? t[0].toUpperCase() + t.slice(1) : 'New mission';
      const r = createCmd('mission', t, o), startToo = /\b(start|run|plan)\b/i.test(text);
      r.c = startToo ? tp('Mission created. Starting it needs your approval.', 'Missione creata. Per avviarla serve la tua approvazione.') : r.c;
      return r;
    }
    if (/\b(needs? me|what.*(running|waiting)|status|today|cosa.*(attesa|corso)|stato)\b/i.test(text)) return readCmd('status', '');
    if (QUESTION.test(text) && !WORKWORD.test(text)) return { c: tp('Answer this, or create work?', 'Rispondo a questo, o creo del lavoro?'), card: { kind: 'choice', text, state: 'open' } };
    return { c: tp('I heard you. Name the project, mission, idea or proposal you want. Nothing was created or executed.', 'Ti ho sentito. Dimmi il progetto, la missione, l\'idea o la proposta che vuoi. Non è stato creato né eseguito nulla.') };
  }
  function plainGeneral(text) {
    if (REFUSE.slice(0, 1).concat(REFUSE.slice(2)).some(([re]) => re.test(text)) || (WORKWORD.test(text) && /\b(create|add|start|make|run|plan|remember)\b/i.test(text))) return { c: tp('Answer this, or create work?', 'Rispondo a questo, o creo del lavoro?'), card: { kind: 'choice', text, state: 'open', from: 'general' } };
    return general(text);
  }

  function answer(msg) {
    const o = { dest: msg.dest, project: msg.project };
    if (msg.cmd) {
      const c = find(msg.cmd);
      if (c.name === 'general') return general(msg.args);
      if (c.cls === 'CREATE') return createCmd(c.name, msg.args, o);
      if (c.cls === 'PROPOSE') return proposeCmd(c.name, msg.args);
      return readCmd(c.name, msg.args);
    }
    if (msg.escaped) return { c: tp('Sent as ordinary text: {t}. No slash handler ran.', 'Inviato come testo normale: {t}. Nessun comando slash è partito.', { t: msg.text }) };
    return msg.dest === 'general' ? plainGeneral(msg.text) : plainWork(msg.text, o);
  }

  // ---------- sending ----------
  api.send = (input, o = {}) => {
    const t0 = String(input || '').trim();
    if (!t0) return { ok: false, notice: tp('Write a message first.', 'Scrivi prima un messaggio.') };
    if (looksSecret(t0)) return { ok: false, keep: true, notice: tp('This looks like a secret, so it was not sent.', 'Sembra un segreto, quindi non è stato inviato.') };
    const p = parse(t0);
    if (p && p.kind === 'menu') return { ok: false, menu: true };
    if (p && p.kind === 'unknown') return { ok: false, keep: true, notice: tp('Unknown command /{n}. Type / for the list, or //{n} to send the text as a message.', 'Comando /{n} sconosciuto. Scrivi / per l\'elenco, oppure //{n} per inviare il testo come messaggio.', { n: p.name }) };
    if (p && (p.kind === 'never' || p.kind === 'usage' || p.kind === 'unavailable')) return { ok: false, keep: true, notice: tp(p.say[0], p.say[1]), href: p.href || null };
    if (p && p.kind === 'arg') return { ok: false, keep: true, arg: p.cmd };
    const tm = now();
    if (!o.force && !o.retry && last.text === t0 && tm - last.at < 2000) return { ok: false, keep: true, dup: { secs: Math.max(1, Math.round((tm - last.at) / 1000)), text: t0 } };
    last = { text: t0, at: tm };
    let escaped = false, cmd = p && p.kind === 'command' ? p.cmd : null, args = p && p.kind === 'command' ? p.args : '', text = t0, dest = o.dest === 'general' ? 'general' : 'work';
    if (p && p.kind === 'text') { text = p.text; escaped = true; }
    if (cmd && cmd.name === 'tell') { text = args; cmd = null; args = ''; }
    if (cmd && cmd.name === 'general') dest = 'general';
    const recorded = !cmd || cmd.cls === 'CREATE' || cmd.cls === 'PROPOSE';
    const key = o.key || 'k-' + (++kn);
    const target = !cmd && dest === 'work' && o.mode && !o.fail ? (o.mission && running().find((x) => x.id === o.mission)) || running(o.project || 'archeus')[0] : null;
    const extra = { dest: cmd && cmd.name !== 'general' ? 'command' : dest, project: o.project || 'archeus', cmd: cmd ? cmd.name : null, cls: cmd ? cmd.cls : null, args, key, escaped, status: o.fail ? 'failed' : target ? (o.mode === 'steer' ? 'steering' : 'queued') : 'submitted' };
    if (target) extra.target = target.id;
    const m = post('you', tp(t0, t0), extra, recorded);
    m.text = escaped ? text : t0;
    if (cmd) m.c = tp(t0, t0);
    if (o.fail) return { ok: true, id: m.id, failed: true, cmd: cmd && cmd.name };
    if (target) { if (o.mode === 'steer') sim.chat.steer(target.id, m.id); return { ok: true, id: m.id, [o.mode === 'steer' ? 'steering' : 'queued']: true, mission: target.id }; }
    const run = () => api.finish(m.id);
    if (!recorded) { const out = run(); return { ok: true, id: m.id, cmd: cmd.name, done: true, out }; }
    return { ok: true, id: m.id, cmd: cmd && cmd.name, run };
  };
  // send and answer in one step, for a surface without a pending-reply animation (the terminal, sim.say). A duplicate within 2 s is allowed here.
  api.say = (input, o = {}) => {
    const r = api.send(input, Object.assign({ force: true }, o));
    if (!r.ok) return { ok: false, keep: !!r.keep, href: r.href || null, reason: r.notice ? fmt(r.notice, 'en') : r.arg ? '/' + r.arg.name + ' needs an argument: ' + r.arg.label[0] + '.' : r.menu ? 'Type a command after /. Try /help.' : 'Not sent.' };
    return Object.assign({ ok: true, id: r.id }, r.out || (r.run && r.run()) || {});
  };
  api.finish = (id) => {
    const m = get(id); if (!m || m.status === 'sent' || m.status === 'failed' || done.has(m.key)) return null;
    done.add(m.key);
    const r = answer(m) || { c: tp('Nothing to do.', 'Niente da fare.') };
    if (r.card && r.card.kind === 'pick') r.card.origin = id;
    patch(id, { status: 'sent' });
    const recorded = !m.local;
    let reply = null;
    if (r.c) reply = post('archeus', r.c, { dest: m.dest, card: r.card || null, general: !!r.general, ...originOf(m) }, recorded);
    return Object.assign({ reply }, r);
  };
  // a failed send is retried with the same key, so it cannot be recorded twice
  api.retry = (id) => { const m = get(id); if (!m || m.status !== 'failed') return null; patch(id, { status: 'submitted' }); return { id, run: () => api.finish(id) }; };

  // ---------- what a card's own button does ----------
  function cardOf(id) { const m = get(id); return m && m.card ? m : null; }
  const setCard = (id, fields) => { const m = get(id); patch(id, { card: Object.assign({}, m.card, fields) }); };
  const stale = (id, reason) => { setCard(id, { step: 'stale', note: reason }); return { ok: false, reason }; };

  api.card = (id, what, data = {}) => {
    const m = cardOf(id); if (!m) return { ok: false, reason: 'No such card' };
    const c = m.card, k = c.kind;
    if (c.state && c.state !== 'open' && what !== 'remember') return { ok: false, reason: 'This card is already answered' };
    if (what === 'dismiss') { setCard(id, { state: 'dismissed', step: 'dismissed' }); return { ok: true }; }
    if (k === 'start') {
      const mi = S().missions[c.mission];
      if (what === 'review') { setCard(id, { step: 'review' }); return { ok: true }; }
      if (what === 'back') { setCard(id, { step: 'ask' }); return { ok: true }; }
      if (what === 'keep') { setCard(id, { step: 'kept', state: 'kept' }); return { ok: true }; }
      if (what === 'start') {
        if (!mi || mi.state !== 'CREATED') return stale(id, 'This mission is no longer waiting to start');
        const r = sim.act('start', mi.id); if (!r.ok) return r;
        setCard(id, { step: 'done', state: 'done' }); return { ok: true };
      }
    }
    if (k === 'confirm') {
      if (what === 'step2') { setCard(id, { step: 'confirm' }); return { ok: true }; }
      if (what === 'back') { setCard(id, { step: 'ask' }); return { ok: true }; }
      if (what === 'yes') {
        const kind = c.action === 'estop' ? 'stop' : c.action;
        if (['stop', 'estop', 'cancel'].includes(c.action) && c.step !== 'confirm') return { ok: false, reason: 'Confirm first' };
        let okn = 0, why = '';
        if (c.action === 'estop') { const r = sim.act('estop'); if (r.ok) okn = r.n || 1; else why = r.reason; }
        else c.targets.forEach((t) => { const r = sim.act(kind, t); if (r.ok) okn++; else why = r.reason; });
        if (!okn) return stale(id, why || 'It no longer applies');
        setCard(id, { step: 'done', state: 'done', n: okn }); return { ok: true };
      }
    }
    if (k === 'approval') {
      const a = S().approvals[c.approval];
      if (what === 'back') { setCard(id, { step: 'ask' }); return { ok: true }; }
      if (what === 'approve' || what === 'reject') { if (!a || a.state !== 'PENDING') return stale(id, 'This decision is no longer waiting'); setCard(id, { step: 'stepup', pick: what }); return { ok: true }; }
      if (what === 'confirm') {
        if (c.step !== 'stepup') return { ok: false, reason: 'Step-up first' };
        if (!a || a.state !== 'PENDING') return stale(id, 'This decision is no longer waiting');
        const r = sim.act(c.pick, a.id); if (!r.ok) return r;
        setCard(id, { step: 'done', state: 'done' }); return { ok: true };
      }
    }
    if (k === 'remember') {
      if (what === 'scope') { setCard(id, { scope: data.scope }); return { ok: true }; }
      if (what === 'excerpt') { setCard(id, { excerpt: data.excerpt }); return { ok: true }; }
      if (what === 'save') {
        const text = String(data.excerpt != null ? data.excerpt : c.excerpt).trim(), scope = data.scope != null ? data.scope : c.scope;
        if (!text) return { ok: false, reason: 'Write what to remember' };
        if (looksSecret(text)) return { ok: false, reason: 'This looks like a secret, so it was not saved.' };
        if (!scope) return { ok: false, reason: 'Choose where to remember it first' };
        const kn2 = sim.chat.addKnowledge({ project: scope === 'all' ? null : scope, text, state: 'CONFIRMED', source: 'chat' });
        setCard(id, { step: 'done', state: 'done', excerpt: text, scope, item: kn2.id }); return { ok: true, item: kn2.id };
      }
    }
    if (k === 'choice') {
      if (what === 'general' || what === 'work') {
        setCard(id, { state: 'done', step: what });
        const r = what === 'general' ? general(c.text) : (() => { const x = plainWork(c.text, { dest: 'work' }); if (x.card && x.card.kind === 'choice') return { c: tp('I heard you. Name the project, mission, idea or proposal you want. Nothing was created or executed.', 'Ti ho sentito. Dimmi il progetto, la missione, l\'idea o la proposta che vuoi. Non è stato creato né eseguito nulla.') }; return x; })();
        post('archeus', r.c, { dest: what, card: r.card || null, general: !!r.general, project: m.project, mission: m.mission }, true); return { ok: true };
      }
    }
    if (k === 'pick' && what === 'pick') {
      const orig = get(c.origin);
      setCard(id, { state: 'done', step: 'picked', picked: data.id });
      if (!orig) return { ok: true };
      const r = answer(Object.assign({}, orig, { args: data.id })); if (r) post('archeus', r.c, { dest: 'command', card: r.card || null, ...originOf(Object.assign({}, orig, { args: data.id })) }, !(orig.local));
      return { ok: true, nav: r && r.nav };
    }
    if (k === 'general' && what === 'remember') {
      post('archeus', tp('Where should this be remembered? Nothing is written until you confirm.', 'Dove va ricordato? Non si scrive nulla finché non confermi.'), { dest: 'general', card: { kind: 'remember', excerpt: c.question, scope: '', step: 'ask', state: 'open' }, project: m.project, mission: m.mission }, true);
      return { ok: true };
    }
    return { ok: false, reason: 'Unknown card action' };
  };
  api.resolve = resolve;
  api.hidden = () => !!hide;
  api.thread = thread;
  api.reset = reset;
  api.post = post;
  api.answer = answer;
  api.originOf = originOf;
  api.nameIn = nameIn;
  return api;
}
