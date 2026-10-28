// Replay and Recovery (T-148, S4): the read model, DOM-free, built from the simulation's rows and events. SIMULATED: no Core.
// Rules kept: categories come from one vocabulary (130 states), a state with no entry answers UNKNOWN, a settlement is read from the recorded edge and the event
// actor (never a new record), evidence carries its real strength, an unsupported item says NOT RECORDED, retention depth is stated, nothing is autoplayed or re-run.
import { VOCAB } from './replay-vocab-data.js';
import { tp } from './chat-engine.js';
import { clockLabel } from './sim.js';

export { VOCAB };
export const CATS = ['INTENDED', 'AUTHORIZED', 'RECORDED', 'MAY-HAVE-TAKEN-EFFECT', 'UNCERTAIN', 'SUSPENDED', 'RECONCILED', 'NONE', 'UNKNOWN'];
export const CAT_DEF = {
  INTENDED: tp('Planned or requested work only. Nothing was dispatched, decided or stored yet.', 'Solo lavoro pianificato o richiesto. Ancora nulla avviato, deciso o archiviato.'),
  AUTHORIZED: tp('The state is an approval or a policy decision.', 'Lo stato è un\'approvazione o una decisione di policy.'),
  RECORDED: tp('A settled outcome with a durable row; the change and its event commit together.', 'Un esito chiuso con una riga durevole; il cambiamento e il suo evento vengono salvati insieme.'),
  'MAY-HAVE-TAKEN-EFFECT': tp('Something was dispatched or is alive and its outcome is not known yet.', 'Qualcosa è stato avviato o è attivo e il suo esito non è ancora noto.'),
  UNCERTAIN: tp('The outcome is unknown or a response was lost. Core cannot tell what happened.', 'L\'esito è sconosciuto o una risposta è andata persa. Il Core non sa dire cosa sia successo.'),
  SUSPENDED: tp('Work stopped and waits for a person.', 'Il lavoro si è fermato e aspetta una persona.'),
  RECONCILED: tp('A restart sweep or an operator settled it, read from the recorded edge.', 'Un controllo al riavvio o un operatore l\'ha chiuso, letto dal passaggio registrato.'),
  NONE: tp('Nothing was ever dispatched and nothing is pending.', 'Non è mai stato avviato nulla e nulla è in sospeso.'),
  UNKNOWN: tp('What this state means for a timeline is not declared. It is never guessed.', 'Cosa significa questo stato per una cronologia non è dichiarato. Non si indovina mai.')
};
export const STRENGTH = {
  RECORDED: tp('Recorded', 'Registrato'), REPORTED: tp('Reported, not proof', 'Riferito, non una prova'), SUMMARY: tp('Summary, not complete', 'Riepilogo, non completo'),
  NOT_RECORDED: tp('NOT RECORDED', 'NON REGISTRATO'), UNKNOWN: tp('UNKNOWN', 'SCONOSCIUTO'), SIM: tp('Simulated here', 'Simulato qui')
};

const MAP = {};
Object.entries(VOCAB).forEach(([m, rows]) => rows.forEach(([s, c, why]) => { MAP[m + '.' + s] = { c, why }; }));
export const category = (machine, state) => (MAP[machine + '.' + state] ? MAP[machine + '.' + state].c : 'UNKNOWN');
export const whyOf = (machine, state) => (MAP[machine + '.' + state] ? MAP[machine + '.' + state].why : '');
export const vocabCounts = () => { const n = {}; let t = 0; Object.values(VOCAB).forEach((rows) => rows.forEach((r) => { n[r[1]] = (n[r[1]] || 0) + 1; t++; })); return { n, total: t, machines: Object.keys(VOCAB).length }; };

// A settlement is read from the recorded edge (T-148 R3). Anything else keeps its plain category; a RECONCILED state with no retained edge is UNKNOWN.
const SETTLEMENT = { execution: ['reconciled_kill', 'adopted'], integration: ['user_abandons'], execution_node: ['retire'], knowledge_item: ['confirm', 'reject', 'retract'] };
export function classify(machine, state, ev, pruned) {
  let answer = category(machine, state), reason = answer === 'UNKNOWN' ? 'state_meaning_undeclared' : 'durable_row', by = 'unknown', byWhy = pruned ? 'retained_event_prefix_pruned' : 'no_retained_transition';
  if (ev && ev.payload && ev.payload.to === state) {
    byWhy = 'transition_does_not_reconcile';
    if ((SETTLEMENT[machine] || []).includes(ev.payload.trigger)) { answer = 'RECONCILED'; reason = 'recorded_settlement_edge'; by = ev.actor === 'system' ? 'core' : ev.actor === 'device' ? 'device' : 'unknown'; byWhy = by === 'unknown' ? 'unreadable_event_actor' : 'event_actor'; } else if (answer === 'RECONCILED') { answer = 'RECORDED'; reason = 'recorded_non_reconciliation_edge'; }
  } else if (answer === 'RECONCILED') { answer = 'UNKNOWN'; reason = byWhy; }
  if (machine === 'execution' && state === 'LOST') { by = 'unknown'; byWhy = 'unsettled_lost_awaiting_core_sweep'; }
  return { answer, reason, by, byWhy };
}

// Checkpoint fixtures (summaries: a checkpoint lists at most 30 items and is never the whole change set).
const CHECKPOINTS = { 'x-date-1': { files: ['M src/dates.py', 'M tests/test_dates.py'], shape: 'summary' } };
const E = (label, value, strength) => ({ label, value, strength });
const word = (r) => r;

function evidence(sim, ev) {
  const st = sim.state, p = ev.payload || {}, out = [], k = ev.subject.kind, id = ev.subject.id, to = p.to;
  const m = st.missions[ev.mission];
  const row = k === 'mission' ? st.missions[id] : k === 'plan' ? st.plans[id] : k === 'task' ? st.tasks[id] : k === 'execution' ? st.executions[id] : k === 'approval' ? st.approvals[id] : k === 'verification' ? st.verifications[id] : k === 'review' ? st.reviews[id] : null;
  out.push(E(tp('Record', 'Record'), k + ' ' + id, 'RECORDED'));
  if (ev.type === 'mission.created') out.push(E(tp('Starting state', 'Stato iniziale'), tp('Mission.integration_head is not modelled here', 'Mission.integration_head non è modellato qui'), 'UNKNOWN'));
  if (k === 'plan') out.push(E(tp('Plan version', 'Versione del piano'), String(row ? row.version : p.version || ''), 'RECORDED'));
  if (k === 'plan' && to === 'APPROVED') out.push(E(tp('Authority', 'Autorità'), p.trigger === 'approved' ? tp('A recorded policy decision or an approval; the row names it', 'Una decisione di policy registrata o un\'approvazione; la riga la nomina') : '', 'SIM'));
  if (ev.type === 'approval.requested' || k === 'approval') {
    out.push(E(tp('Action hash', 'Hash dell\'azione'), tp('The approval is bound to one action and one version', 'L\'approvazione è legata a una sola azione e a una sola versione'), 'RECORDED'));
    if (row && row.decided_by) out.push(E(tp('Decided by', 'Deciso da'), row.decided_by, 'RECORDED'));
    if (row && row.state === 'PENDING') out.push(E(tp('Decision', 'Decisione'), tp('Waits on a person', 'Aspetta una persona'), 'RECORDED'));
  }
  if (k === 'task') out.push(E(tp('Scope', 'Ambito'), tp('Frozen at dispatch: objective, expected output, boundaries, acceptance', 'Congelato all\'avvio: obiettivo, risultato atteso, confini, accettazione'), 'RECORDED'));
  if (k === 'execution') {
    if (to === 'RUNNING') out.push(E(tp('Process', 'Processo'), tp('execution.started: the process exists (pid, create time)', 'execution.started: il processo esiste (pid, ora di creazione)'), 'RECORDED'));
    if (to === 'STARTING') out.push(E(tp('Spawning marker', 'Marcatore di avvio'), tp('The marker may exist with no pid recorded yet', 'Il marcatore può esistere senza un pid ancora registrato'), 'RECORDED'));
    if (to === 'ENDED_OK' || to === 'ENDED_ERROR') {
      out.push(E(tp('Exit', 'Uscita'), 'exit_code ' + (p.exit_code == null ? '?' : p.exit_code), 'REPORTED'));
      const cp = CHECKPOINTS[id];
      out.push(cp ? E(tp('Files changed', 'File modificati'), cp.files.join(', ') + ' (at most 30 items, summary)', 'SUMMARY') : E(tp('Files changed', 'File modificati'), tp('No checkpoint for this execution', 'Nessun checkpoint per questa esecuzione'), 'NOT_RECORDED'));
    }
    if (to === 'LOST') { out.push(E(tp('exit_reason', 'exit_reason'), 'lost · charged: true', 'RECORDED'), E(tp('What a process may have done', 'Cosa può aver fatto un processo'), tp('A process may have run and done anything', 'Un processo può aver girato e fatto qualsiasi cosa'), 'UNKNOWN')); }
    if (p.trigger === 'adopted') out.push(E(tp('Settlement', 'Chiusura'), tp('The process was alive by identity; Core adopted it at its sweep', 'Il processo era vivo per identità; il Core l\'ha adottato nel suo controllo'), 'RECORDED'));
    if (p.trigger === 'reconciled_kill') out.push(E(tp('Settlement', 'Chiusura'), tp('Core’s sweep ended a LOST execution', 'Il controllo del Core ha chiuso un\'esecuzione PERSA'), 'RECORDED'));
    if (to === 'AWAITING_APPROVAL') out.push(E(tp('Boundary', 'Confine'), tp('The process halted at its boundary and waits for a decision', 'Il processo si è fermato al suo confine e aspetta una decisione'), 'RECORDED'));
  }
  if (k === 'verification') {
    (row ? row.checks : []).forEach((c) => out.push(E(c.name, c.result, 'RECORDED')));
    if (row) out.push(E(tp('Starting state', 'Stato iniziale'), 'Verification.base_revision ' + row.base_revision, 'RECORDED'));
    if (to === 'FAILED') out.push(E(tp('Verdict', 'Verdetto'), tp('A failed verification is a recorded verdict, not an error', 'Una verifica fallita è un verdetto registrato, non un errore'), 'RECORDED'));
    if (to === 'ERROR') out.push(E(tp('Verdict', 'Verdetto'), tp('An ERROR is not a verdict', 'Un ERRORE non è un verdetto'), 'UNKNOWN'));
  }
  if (k === 'review' && row && row.state !== 'PENDING') out.push(E(tp('Verdict', 'Verdetto'), word(row.state), 'RECORDED'));
  const cat = ev.type.endsWith('state_changed') ? category(k, to) : null;
  if (cat === 'MAY-HAVE-TAKEN-EFFECT' || cat === 'UNCERTAIN') out.push(E(tp('External effect of this step', 'Effetto esterno di questo passo'), tp('No external-effect record exists', 'Non esiste alcun record di effetto esterno'), 'NOT_RECORDED'));
  void m;
  return out;
}

// A steer is the owner's request (INTENDED) and Core's acknowledgement (RECORDED). Neither row says the mission changed course.
const STEER_WHY = {
  'mission.steer_requested': 'A steer is a request to be taken at the next safe boundary. This is a simulation; a real Core would record the request, not that the mission changed course.',
  'mission.steer_acknowledged': 'Core acknowledged the steer. The acknowledgement is recorded; it does not prove the mission changed course, and the boundary it took effect at is not modelled here.'
};
export function buildReplay(sim, missionId) {
  const st = sim.state, m = st.missions[missionId];
  if (!m) return null;
  const evs = st.events.filter((e) => e.mission === missionId && /state_changed$|created$|requested$|acknowledged$/.test(e.type) && !/^(message|task\.created)/.test(e.type));
  const last = {}; evs.forEach((e) => { if (e.type.endsWith('state_changed')) last[e.subject.kind + ':' + e.subject.id] = e; });
  const steps = evs.map((e, i) => {
    const k = e.subject.kind, to = e.payload && e.payload.to, isState = e.type.endsWith('state_changed');
    const cl = isState ? classify(k, to, e, st.pruned) : { answer: e.type === 'approval.requested' ? 'SUSPENDED' : e.type.endsWith('created') || e.type === 'mission.steer_requested' ? 'INTENDED' : e.type === 'mission.steer_acknowledged' ? 'RECORDED' : 'UNKNOWN', reason: 'durable_row', by: 'unknown', byWhy: 'transition_does_not_reconcile' };
    return {
      n: i + 1, seq: e.seq, at: e.at, time: clockLabel(e.at), machine: k, id: e.subject.id, state: to || e.type.split('.')[1].toUpperCase(), from: e.payload && e.payload.from || null,
      trigger: e.payload && e.payload.trigger || null, category: cl.answer, reason: cl.reason, why: isState ? whyOf(k, to) : STEER_WHY[e.type] || '', settled_by: cl.by, settled_why: cl.byWhy,
      actor: e.actor === 'device' ? 'device' : e.actor === 'system' ? 'core' : 'unknown', evidence: evidence(sim, e)
    };
  });
  const rows = [];
  const own = (id) => st.tasks[id];
  rows.push(['mission', m]);
  Object.values(st.plans).filter((x) => x.mission === m.id).forEach((x) => rows.push(['plan', x]));
  m.tasks.map(own).forEach((x) => rows.push(['task', x]));
  Object.values(st.executions).filter((x) => x.mission === m.id).forEach((x) => rows.push(['execution', x]));
  Object.values(st.approvals).filter((x) => x.mission === m.id).forEach((x) => rows.push(['approval', x]));
  Object.values(st.verifications).filter((x) => x.mission === m.id).forEach((x) => rows.push(['verification', x]));
  Object.values(st.reviews).filter((x) => x.mission === m.id).forEach((x) => rows.push(['review', x]));
  const records = rows.map(([k, r]) => Object.assign({ machine: k, id: r.id, state: r.state }, classify(k, r.state, last[k + ':' + r.id], st.pruned)));
  const vs = Object.values(st.verifications).filter((x) => x.mission === m.id);
  const first = st.events.length ? st.events[0].at : null;
  const counts = {}; steps.forEach((s) => { counts[s.category] = (counts[s.category] || 0) + 1; });
  return {
    mission: m, steps, records, counts,
    starting_state: [
      { source: 'Mission.integration_head', answer: 'UNKNOWN', reason: 'starting_state_not_recorded', note: tp('Not modelled in this simulation; Core answers UNKNOWN when it is not bound.', 'Non modellato in questa simulazione; il Core risponde SCONOSCIUTO quando non è legato.') },
      ...vs.map((v) => ({ source: 'Verification.base_revision', answer: 'RECORDED', reason: 'existing_commit_binding', value: v.base_revision, note: tp('The commit the checks ran on ({id}).', 'Il commit su cui hanno girato i controlli ({id}).', { id: v.id }) })),
      { source: 'Execution.seed_revision', answer: 'UNKNOWN', reason: 'starting_state_not_recorded', note: tp('Only a seeded, isolated attempt carries one. There is no per-attempt starting digest.', 'Solo un tentativo isolato con seme ne ha una. Non esiste un digest iniziale per tentativo.') }
    ],
    history: { answer: st.pruned ? 'UNKNOWN' : 'RECORDED', reason: st.pruned ? 'retained_event_prefix_pruned' : 'retained_range_only', oldest_retained_at: first, event_days: 180, open_mission_extension: false },
    external_effects: { answer: 'UNKNOWN', reason: 'external_effects_not_recorded' }
  };
}

// The five example rows of the strategy (STRATEGY-assessment 84-93), each answered with its real strength. A strategy example, not this mission.
export const FIVE_ROWS = [
  { t: '09:00', title: tp('Task initiated', 'Attività avviata'), says: tp('Scope, authority and starting state captured', 'Ambito, autorità e stato iniziale registrati'), parts: [
    ['RECORDED', tp('Scope: the frozen dispatch contract of the task', 'Ambito: il contratto di avvio congelato dell\'attività')],
    ['RECORDED', tp('Authority: the policy decision and the approval row', 'Autorità: la decisione di policy e la riga di approvazione')],
    ['UNKNOWN', tp('Starting state: only from three commit bindings, otherwise UNKNOWN. There is no per-attempt digest.', 'Stato iniziale: solo da tre legami a commit, altrimenti SCONOSCIUTO. Non esiste un digest per tentativo.')]] },
  { t: '09:12', title: tp('Files changed', 'File modificati'), says: tp('Changes and resulting artifacts linked to the task', 'Modifiche e artefatti collegati all\'attività'), parts: [
    ['SUMMARY', tp('A checkpoint lists at most 30 items. It is a summary, never the whole change set.', 'Un checkpoint elenca al massimo 30 voci. È un riepilogo, mai l\'intero insieme di modifiche.')],
    ['RECORDED', tp('Artifacts (patch, test result) with their task', 'Artefatti (patch, risultato dei test) con la loro attività')],
    ['NOT_RECORDED', tp('A complete file ledger per task', 'Un registro completo dei file per attività')]] },
  { t: '09:18', title: tp('Tests passed', 'Test superati'), says: tp('Validation evidence recorded', 'Prove di validazione registrate'), parts: [
    ['RECORDED', tp('Each check: name, kind, result, output hash. The strongest row of the five.', 'Ogni controllo: nome, tipo, risultato, hash dell\'output. La riga più solida delle cinque.')],
    ['UNKNOWN', tp('An ERROR verification or an unknown criterion is not a pass', 'Una verifica in ERRORE o un criterio sconosciuto non è un successo')]] },
  { t: '09:24', title: tp('External response lost', 'Risposta esterna persa'), says: tp('Actual side effect classified as uncertain', 'Effetto reale classificato come incerto'), parts: [
    ['RECORDED', tp('For a process: the execution is LOST, charged, a process may have run', 'Per un processo: l\'esecuzione è PERSA, addebitata, un processo può aver girato')],
    ['NOT_RECORDED', tp('As an external effect: there is no Effect record, so it stays UNKNOWN', 'Come effetto esterno: non esiste un record Effect, quindi resta SCONOSCIUTO')]] },
  { t: '09:25', title: tp('Workflow suspended', 'Flusso sospeso'), says: tp('No unsafe retry; operator reconciliation required', 'Nessun nuovo tentativo non sicuro; serve la riconciliazione di un operatore'), parts: [
    ['RECORDED', tp('Suspension: the task, execution or approval waits for a person', 'Sospensione: l\'attività, l\'esecuzione o l\'approvazione aspetta una persona')],
    ['RECORDED', tp('No unsafe retry: a spawning marker is never spawned again; a retry is a new execution id', 'Nessun nuovo tentativo non sicuro: un marcatore di avvio non riparte mai; un nuovo tentativo è una nuova esecuzione')],
    ['NOT_RECORDED', tp('An operator’s own reconciliation: today Core is the reconciler, nothing records who settled an external effect', 'La riconciliazione di un operatore: oggi il riconciliatore è il Core, nulla registra chi ha chiuso un effetto esterno')]] }
];

export const GAPS = [
  tp('External effects or responses', 'Effetti o risposte esterni'), tp('A per-attempt starting digest', 'Un digest iniziale per tentativo'), tp('Operator reconciliation', 'La riconciliazione di un operatore'),
  tp('Complete retained history (events are kept 180 days)', 'La cronologia completa (gli eventi si conservano 180 giorni)'), tp('The private reasoning and tool transcript', 'Il ragionamento privato e la trascrizione degli strumenti'),
  tp('Intermediate file snapshots', 'Copie intermedie dei file'), tp('Actual cost, or served and billed provenance', 'Costo reale, o provenienza servita e fatturata'), tp('Confinement proof', 'Prova di confinamento')
];

// Recovery: what Archeus would do and what it will not do. Every option only creates an approval card; none re-runs anything.
export const NEVER = [
  tp('Spawn the same execution again. A retry is a new execution id.', 'Riavviare la stessa esecuzione. Un nuovo tentativo è una nuova esecuzione.'),
  tp('Claim that an external effect can be undone.', 'Affermare che un effetto esterno si possa annullare.'),
  tp('Settle an external effect as an operator. Core’s sweep settles processes only.', 'Chiudere un effetto esterno come operatore. Il controllo del Core chiude solo i processi.'),
  tp('Run or play anything on its own. Replay never autoplays and never re-runs.', 'Eseguire o riprodurre qualcosa da solo. Il Replay non parte mai da solo e non riesegue nulla.'),
  tp('Change the recorded evidence. Approving a card changes a receipt, never the history.', 'Cambiare le prove registrate. Approvare una scheda cambia una ricevuta, mai la cronologia.')
];
export function recovery(sim, missionId) {
  const st = sim.state, m = st.missions[missionId];
  const lost = Object.values(st.executions).find((x) => x.mission === m.id && x.state === 'LOST');
  const pend = Object.values(st.approvals).find((a) => a.mission === m.id && a.state === 'PENDING');
  const resume = m.state === 'PAUSED' ? { act: 'resume', ok: true } : m.state === 'BLOCKED' ? { act: 'unblock', ok: true } : { ok: false, why: lost ? tp('Core reconciles a LOST execution at its own sweep. An operator cannot force it.', 'Il Core riconcilia un\'esecuzione PERSA nel suo controllo. Un operatore non può forzarlo.') : tp('Nothing is paused or blocked.', 'Niente è in pausa o bloccato.') };
  const retry = m.state === 'FAILED' ? { act: 'replan', ok: true } : { ok: false, why: pend ? tp('A plan already waits for your decision.', 'Un piano aspetta già la tua decisione.') : tp('Only a failed mission is replanned.', 'Si ripianifica solo una missione fallita.') };
  return [
    Object.assign({ id: 'resume', title: tp('Resume', 'Riprendi'), would: [tp('Open an approval card for the resume', 'Aprire una scheda di approvazione per la ripresa'), tp('After you approve: continue from the checkpoint through a new dispatch', 'Dopo la tua approvazione: proseguire dal checkpoint con un nuovo avvio')], wont: [tp('Reuse the old execution or its spawning marker', 'Riusare la vecchia esecuzione o il suo marcatore di avvio')] }, resume),
    Object.assign({ id: 'retry', title: tp('Retry with changes', 'Riprova con modifiche'), would: [tp('Draft the changed instructions for you to edit', 'Preparare le istruzioni modificate perché tu le modifichi'), tp('Ask for a new plan version; a new execution id exists only after you approve it', 'Chiedere una nuova versione del piano; una nuova esecuzione esiste solo dopo la tua approvazione')], wont: [tp('Promise the earlier attempt left no external effect', 'Promettere che il tentativo precedente non abbia lasciato effetti esterni')] }, retry),
    { id: 'ask', title: tp('Ask the owner', 'Chiedi al proprietario'), ok: true, act: 'ask', would: [tp('Draft an unsent question you can edit', 'Preparare una domanda non inviata che puoi modificare'), tp('Send it to the conversation only after you approve', 'Inviarla alla conversazione solo dopo la tua approvazione')], wont: [tp('Guess an answer or decide for you', 'Indovinare una risposta o decidere al posto tuo')] }
  ];
}
