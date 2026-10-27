// What the terminal shows for one chat reply: the answer, its card as plain lines, and the keys that act on the card. DOM free.
// The chat engine (chat-engine.js) does the work; this only reads its card and calls eng.card() with the same actions the chat page's buttons use.
import { fmt } from '../../chat-engine.js';
import { present } from '../../core-words.js';
import { COMMANDS, CLASSES, find, nameIn, labelOf } from '../../slash.js';

const VERB = { stop: ['Stop', 'Ferma'], estop: ['Emergency stop', 'Arresto d\'emergenza'], cancel: ['Cancel', 'Annulla'], pause: ['Pause', 'Pausa'], resume: ['Resume', 'Riprendi'] };

// Returns { lines: [text], keys: [{ k, label, hidden?, run() -> { say?, err?, href?, tab?, keep? } }] }.
export function replyOf(m, eng, sim, lang) {
  const it = lang === 'it', T = (en, ita) => (it ? ita : en), st = sim.state, c = m.card;
  const out = { lines: [m.c ? fmt(m.c, lang) : m.text], keys: [] };
  const L = (...x) => out.lines.push(...x);
  const key = (k, label, run, hidden) => out.keys.push({ k, label, run, hidden: !!hidden });
  const res = (r, say) => (r.ok ? { say } : { say: T('Not done: ', 'Non fatto: ') + r.reason, err: true });
  const act = (what, say, data) => () => res(eng.card(m.id, what, data), say);
  const step = (what, data) => () => { const r = eng.card(m.id, what, data); return r.ok ? { keep: true } : res(r); };
  const pname = (id) => { const p = st.projects.find((x) => x.id === id); return p ? p.name : id; };
  if (!c) return out;
  if (c.kind === 'link') key('enter', c.text, () => ({ href: c.href }));
  else if (c.kind === 'refusal') { if (c.href) key('enter', c.href === '#/security' ? T('Open Security', 'Apri Sicurezza') : T('Open Work', 'Apri Lavoro'), () => ({ href: c.href })); }
  else if (c.kind === 'status') L(T(`Running ${c.running}, waiting for you ${c.waiting}, stopped ${c.stopped}. Accepting new work: Unknown.`, `In corso ${c.running}, aspettano te ${c.waiting}, fermi ${c.stopped}. Accetta nuovo lavoro: Sconosciuto.`) + (c.estop ? T(' Emergency stop: engaged, nothing new starts.', " Arresto d'emergenza: attivo, non parte nulla di nuovo.") : ''));
  else if (c.kind === 'usage') { (c.rows || []).forEach((r) => L(r + ': ' + T('Unknown', 'Sconosciuto'))); L(T('Unknown is never shown as 0.', 'Sconosciuto non è mai mostrato come 0.')); }
  else if (c.kind === 'why') L(T(`Route decision ${c.id}. Served model and billed cost: Unknown. Account: selected by Core.`, `Decisione di instradamento ${c.id}. Modello servito e costo fatturato: Sconosciuti. Account: scelto dal Core.`));
  else if (c.kind === 'help') {
    const x = c.arg ? find(String(c.arg).replace(/^\//, '')) : null;
    if (x) L('/' + nameIn(x, lang) + (labelOf(x, lang) ? ' <' + labelOf(x, lang) + '>' : ''));
    else CLASSES.forEach((k) => L(k + '  ' + COMMANDS.filter((y) => y.cls === k && !y.unavailable).map((y) => '/' + nameIn(y, lang)).join(' ')));
  } else if (c.kind === 'list') {
    c.items.slice(0, 6).forEach((i, n) => { L(`${n + 1}. ${i.label}${i.meta ? '  ' + i.meta : ''}`); key(String(n + 1), i.label, () => ({ href: i.href }), true); });
    if (c.more) L(T(`+${c.more} more`, `+${c.more} altri`));
  } else if (c.kind === 'plan') {
    const mi = st.missions[c.mission], ts = mi ? mi.tasks.map((id) => st.tasks[id]).filter(Boolean) : [];
    ts.forEach((t) => L('- ' + t.title + '  ' + present('task', t.state).label));
    if (!ts.length) L(T('The plan is made after the mission starts.', 'Il piano si fa dopo l\'avvio della missione.'));
    key('enter', T('Open plan', 'Apri il piano'), () => ({ href: '#/work/' + c.mission, tab: 'plan' }));
  } else if (c.kind === 'created') { L(`${c.title}  (${c.id}, ${c.project})`); if (c.href) key('enter', T('Show', 'Mostra'), () => ({ href: c.href })); }
  else if (c.kind === 'start') {
    if (c.step === 'done') L(T('Started. Planning is under way; the plan waits for your approval before anything executes.', 'Avviata. La pianificazione è in corso; il piano aspetta la tua approvazione prima che si esegua qualcosa.'));
    else if (c.step === 'kept') L(T('Kept as a mission. Not started.', 'Tenuta come missione. Non avviata.'));
    else if (c.step === 'stale') L(c.note);
    else {
      L(T('Proposed. Nothing has started. Planning runs on an account Core selects; the plan then waits for your approval.', 'Proposta. Non è partito nulla. La pianificazione gira su un account scelto dal Core; il piano poi aspetta la tua approvazione.'));
      key('y', T('Start and plan', 'Avvia e pianifica'), () => { eng.card(m.id, 'review'); return res(eng.card(m.id, 'start'), T('Started (simulated).', 'Avviata (simulato).')); });
      key('n', T('Keep as mission', 'Tieni come missione'), act('keep', T('Kept. Not started.', 'Tenuta. Non avviata.')));
    }
  } else if (c.kind === 'confirm') {
    const names = c.targets.map((id) => (st.missions[id] || {}).title).filter(Boolean).join(', '), v = VERB[c.action][it ? 1 : 0], two = ['stop', 'estop', 'cancel'].includes(c.action);
    if (c.step === 'done') L(T(`Done for ${c.n || c.targets.length}: ${names}.`, `Fatto per ${c.n || c.targets.length}: ${names}.`));
    else if (c.step === 'dismissed') L(T('Nothing was done.', 'Non è stato fatto nulla.'));
    else if (c.step === 'stale') L(c.note);
    else if (c.step === 'confirm') {
      if (c.action === 'estop') L(T('New dispatch stays blocked until you re-arm (E on the terminal, or Settings).', 'Ogni nuovo avvio resta bloccato finché non riarmi (E nel terminale, o Impostazioni).'));
      L(T(`Confirm: ${v.toLowerCase()} ${names} now? Step 2 of 2. This cannot be undone from here.`, `Conferma: ${v.toLowerCase()} ${names} adesso? Passo 2 di 2. Da qui non si può disfare.`));
      key('y', T('Yes, ' + v.toLowerCase(), 'Sì, ' + v.toLowerCase()), act('yes', T('Done (simulated).', 'Fatto (simulato).')));
      key('n', T('Back', 'Indietro'), step('back'));
    } else {
      L(T(`${v} ${names}? Nothing has happened yet.${two ? ' Step 1 of 2.' : ''}`, `${v} ${names}? Non è successo ancora nulla.${two ? ' Passo 1 di 2.' : ''}`));
      key('y', T('Confirm', 'Conferma'), two ? step('step2') : act('yes', T('Confirmed (simulated).', 'Confermato (simulato).')));
      key('n', T('Dismiss', 'Scarta'), act('dismiss', T('Dismissed.', 'Scartata.')));
    }
  } else if (c.kind === 'approval') {
    const a = st.approvals[c.approval];
    if (!a) L(T('This decision no longer exists.', 'Questa decisione non esiste più.'));
    else if (c.step === 'stale') L(c.note);
    else if (a.state !== 'PENDING') L(present('approval', a.state).label);
    else {
      L(a.presented.what, T('Why it asks: ', 'Perché lo chiede: ') + a.presented.why, T('Only the decision screen decides; this message never does.', 'Decide solo la schermata della decisione; questo messaggio non decide mai.'));
      key('enter', T('Open the decision', 'Apri la decisione'), () => ({ href: '#/work/' + a.id }));
    }
  } else if (c.kind === 'remember') {
    if (c.step === 'done') L(T('Remembered: ', 'Ricordato: ') + c.excerpt);
    else if (c.step === 'dismissed') L(T('Nothing was written.', 'Non è stato scritto nulla.'));
    else if (c.scope) {
      L(T('Remember in ', 'Ricorda in ') + (c.scope === 'all' ? T('all projects', 'tutti i progetti') : pname(c.scope)) + ': ' + c.excerpt);
      key('y', T('Remember', 'Ricorda'), act('save', T('Remembered (simulated).', 'Ricordato (simulato).')));
      key('n', T('Cancel', 'Annulla'), act('dismiss', T('Nothing was written.', 'Non è stato scritto nulla.')));
    } else {
      L(T('Nothing is written until you choose where: ', 'Non si scrive nulla finché non scegli dove: ') + c.excerpt);
      const save = (scope) => () => { eng.card(m.id, 'scope', { scope }); return res(eng.card(m.id, 'save', { scope }), T('Remembered (simulated).', 'Ricordato (simulato).')); };
      st.projects.slice(0, 8).forEach((p, i) => key(String(i + 1), p.name, save(p.id)));
      key('a', T('All projects', 'Tutti i progetti'), save('all'));
      key('n', T('Cancel', 'Annulla'), act('dismiss', T('Nothing was written.', 'Non è stato scritto nulla.')));
    }
  } else if (c.kind === 'general') L(T('General answer, not project memory. "Not project memory" does not mean "not stored".', 'Risposta generale, non memoria di progetto. "Non è memoria di progetto" non vuol dire "non archiviato".'));
  else if (c.kind === 'choice') {
    if (c.state === 'open') {
      L(T('Nothing was created or sent yet.', 'Non è stato creato né inviato nulla.'));
      key('g', T('Answer in General', 'Rispondi in Generale'), act('general', T('Answered in General.', 'Risposto in Generale.')));
      key('w', T('Create work', 'Crea lavoro'), act('work', T('Sent as work.', 'Inviato come lavoro.')));
    }
  } else if (c.kind === 'pick' && c.state !== 'done') {
    c.options.forEach((o, n) => { L(`${n + 1}. ${o.label}  ${o.meta || ''}`.trimEnd()); key(String(n + 1), o.label, () => { const r = eng.card(m.id, 'pick', { id: o.id }); return r.ok ? { href: r.nav || null, say: T('Picked.', 'Scelta.') } : res(r); }, true); });
  }
  return out;
}
