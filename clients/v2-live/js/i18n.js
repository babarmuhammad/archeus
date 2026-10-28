// English is the source language; Italian is a display translation of the main surfaces (Now, Work, Attention, spine words,
// slash aliases, menus). The DOM is translated after each render by exact string, so views stay plain English text.
// Fixture content (mission titles, reasons, replies) stays English: it stands in for Core's own words.
import { get } from './store.js';
import { IT_AREAS, RULES_AREAS, setTr } from './i18n-areas.js';
import { IT_S6 } from './i18n-s6.js';
import { IT_SHELL, RULES_SHELL } from './i18n-shell.js';
import { IT_NOW, RULES_NOW } from './i18n-now.js';
import { IT_WORK, RULES_WORK } from './i18n-work.js';
import { IT_ATTN, RULES_ATTN } from './i18n-attn.js';
import { IT_INSP, RULES_INSP } from './i18n-insp.js';
import { IT_CHAT, RULES_CHAT } from './i18n-chat.js';
import { IT_PHONE, RULES_PHONE } from './i18n-phone.js';
import { IT_AP, RULES_AP } from './i18n-autopilot.js';

const IT = {
  'Timeline overview': 'Panoramica della cronologia',
  'Recorded events': 'Eventi registrati',
  'Source record': 'Record di origine',
  'Reference and limits': 'Riferimenti e limiti',
  'Close evidence': 'Chiudi le prove',
  'Inspect selected event': 'Esamina l’evento selezionato',
  'No events in this category.': 'Nessun evento in questa categoria.',
  'Read-only history. Select an event to inspect what Core recorded.': 'Cronologia in sola lettura. Seleziona un evento per esaminare ciò che il Core ha registrato.',
  'Recovery proposals · SIMULATED': 'Proposte di recupero · SIMULATO',
  // shell
  'Now': 'Adesso', 'Work': 'Lavoro', 'Attention': 'Attenzione', 'Replay': 'Replay', 'Chat': 'Chat', 'Settings': 'Impostazioni', 'More': 'Altro',
  'Security': 'Sicurezza', 'Health': 'Stato di salute', 'Accounts': 'Account', 'Terminal view': 'Vista terminale', 'Terminal': 'Terminale', 'All devices': 'Tutti i dispositivi',
  'Device': 'Dispositivo', 'Theme': 'Tema', 'Motion': 'Movimento', 'Quiet': 'Quieto', 'Sim': 'Sim', 'Paused': 'In pausa', 'Language': 'Lingua', 'Notes': 'Note',
  'Auto': 'Auto', 'Phone': 'Telefono', 'Tablet': 'Tablet', 'Desktop': 'Desktop',
  'Dark': 'Scuro', 'Light': 'Chiaro', 'Dark, high contrast': 'Scuro, alto contrasto', 'Light, high contrast': 'Chiaro, alto contrasto', 'System': 'Sistema', 'Forced colours (simulated)': 'Colori forzati (simulati)', 'Dark HC': 'Scuro AC', 'Light HC': 'Chiaro AC', 'Forced colours': 'Colori forzati',
  'Fills the window': 'Riempie la finestra', 'Text mode': 'Modalità testo',
  'SIMULATED': 'SIMULATO', 'no Core connected': 'nessun Core collegato',
  'Prototype controls': 'Controlli del prototipo', 'Device preview': 'Anteprima dispositivo', 'Reduced motion': 'Movimento ridotto', 'Simulation': 'Simulazione',
  'V2 Live prototype. Simulated. No Core is connected.': 'Prototipo V2 Live. Simulato. Nessun Core collegato.',
  'Main': 'Principale', 'Details': 'Dettagli', 'Expand or collapse the navigation': 'Apri o chiudi la navigazione',
  'A frame shows the real app at that width inside this page. If the window is narrower, the frame is scaled down to fit.': 'Un riquadro mostra l\'app vera a quella larghezza dentro la pagina. Se la finestra è più stretta, il riquadro viene ridotto.',
  'System follows the OS (including high contrast). Forced colours is a simulation; the real forced-colors mode is also honoured.': 'Sistema segue il sistema operativo (anche l\'alto contrasto). I colori forzati sono una simulazione; anche la vera modalità forced-colors è rispettata.',
  'Decision notes': 'Note sulle decisioni', 'Show which decision each choice implements': 'Mostra quale decisione attua ogni scelta',
  // page heads
  '(paused)': '(in pausa)',
  // Now
  'The sentence is built only from Core state words and counts.': 'La frase è costruita solo con parole di stato del Core e conteggi.',
  'Live map': 'Mappa viva', 'vector, redrawn at every size': 'vettoriale, ridisegnata a ogni dimensione', 'Happening now': 'In corso adesso', 'Upcoming': 'In arrivo',
  'Recent decisions and changes': 'Decisioni e cambiamenti recenti', 'Nothing is waiting for a decision.': 'Nessuna decisione in attesa.', 'Nothing is running.': 'Niente in esecuzione.',
  'Nothing is planned or approved.': 'Niente di pianificato o approvato.', 'Nothing has changed yet.': 'Non è cambiato ancora nulla.',
  'Project': 'Progetto', 'Mission': 'Missione', 'Execution': 'Esecuzione', 'Decision': 'Decisione', 'Centre: Core, ': 'Centro: Core, ', 'nothing running': 'niente in esecuzione',
  'Open decision': 'Apri la decisione', 'Open review': 'Apri la revisione', 'Open': 'Apri', 'Open Settings': 'Apri Impostazioni', 'Open Replay': 'Apri Replay', 'Open the terminal view': 'Apri la vista terminale',
  // Work
  'g:Needs you': 'Ti serve', 'g:Failed or cancelled': 'Fallite o annullate', 'g:Active': 'Attive', 'g:Planning': 'In pianificazione', 'g:Blocked': 'Bloccate', 'g:Paused': 'In pausa', 'g:Done': 'Fatte', 'Ideas': 'Idee', 'Blocked': 'Bloccata', 'Needs you': 'Richiede te',
  // Attention
  'Decide': 'Decidi', 'Review': 'Rivedi', 'Unblock': 'Sblocca', ' \u00b7 asks you to decide': ' \u00b7 ti chiede di decidere', ' \u00b7 results to accept': ' \u00b7 risultati da accettare', ' \u00b7 work that needs a person': ' \u00b7 lavoro che richiede una persona',
  'asks you to decide': 'ti chiede di decidere', 'results to accept': 'risultati da accettare', 'work that needs a person': 'lavoro che richiede una persona',
  'Nothing waits on you.': 'Niente aspetta te.', 'Remember': 'Ricorda', 'Not this': 'Non questo', 'Re-enable': 'Riattiva', 'Approve': 'Approva', 'Reject': 'Rifiuta', 'Candidate': 'Candidato', 'Automation': 'Automazione', 'Account': 'Account',
  // inspector and decision
  'Close': 'Chiudi', 'Close details': 'Chiudi i dettagli', 'Close decision': 'Chiudi la decisione', 'Outcome': 'Esito', 'Plan': 'Piano', 'Evidence': 'Prove', 'Timeline': 'Cronologia',
  'Where it is': 'A che punto è', 'Facts': 'Fatti', 'State': 'Stato', 'Branch': 'Ramo', 'Origin': 'Origine', 'Tasks': 'Attività', 'Why': 'Perché', 'Executions': 'Esecuzioni', 'Plan versions': 'Versioni del piano', 'Verification': 'Verifica',
  'Last recorded steps': 'Ultimi passi registrati', 'Mission steps': 'Passi della missione', 'No plan yet.': 'Ancora nessun piano.', 'No execution yet.': 'Ancora nessuna esecuzione.', 'Nothing has been verified yet.': 'Ancora nulla è stato verificato.',
  'Answer and unblock': 'Rispondi e sblocca', 'Cancel mission': 'Annulla la missione', 'Resume': 'Riprendi', 'Replan': 'Ripianifica', 'Accept': 'Accetta', 'Request changes': 'Chiedi modifiche', 'Pause': 'Pausa',
  'Approve this plan?': 'Approvare questo piano?', 'Allow this action?': 'Consentire questa azione?', 'What': 'Cosa', 'Why it asks': 'Perché lo chiede', 'What Core does next': 'Cosa fa il Core dopo', 'Where the mission is': 'A che punto è la missione',
  // spine
  'Understanding': 'Comprensione', 'Understand': 'Capisci', 'Run': 'Esegui', 'Verify': 'Verifica', 'Approval': 'Approvazione', 'Executing': 'Esecuzione', 'Verifying': 'Verifica', 'Reviewing': 'Revisione', 'Position unknown': 'Posizione sconosciuta',
  // mission/other state words
  'Created': 'Creata', 'Context gathering': 'Raccolta del contesto', 'Reasoning': 'Ragionamento', 'Replanning': 'Ripianificazione', 'Waiting for approval': 'In attesa di approvazione', 'Approved \u2014 not started': 'Approvata \u2014 non avviata',
  'Resuming': 'Ripresa', 'Reviewing \u2014 verified, not accepted': 'In revisione \u2014 verificata, non accettata', 'Failed': 'Fallita', 'Done \u2014 verified and reviewed': 'Fatta \u2014 verificata e rivista', 'Cancelled': 'Annullata',
  'Running': 'In esecuzione', 'Starting': 'Avvio', 'Awaiting approval': 'In attesa di approvazione', 'Lost \u2014 Core is reconciling': 'Persa \u2014 il Core sta riconciliando', 'Exited ok \u2014 not verified': 'Uscita ok \u2014 non verificata', 'Ended error': 'Finita con errore',
  'Pending': 'In sospeso', 'Approved': 'Approvata', 'Rejected': 'Rifiutata', 'Passed': 'Superata',
  // statuses of other machines used on the main surfaces
  'Planned': 'Pianificata', 'Parked': 'Parcheggiata', 'Explored': 'Esplorata', 'Scheduled': 'Programmata', 'Captured': 'Catturata',
  // Replay
  'Approve plan': 'Approva il piano', 'Allow action': 'Consenti l\'azione', 'Done': 'Fatta', 'Idle': 'Inattiva', 'Thinking': 'In pianificazione', 'Knowledge': 'Conoscenza', 'Idea': 'Idea', 'Node': 'Nodo', 'Kind': 'Tipo', 'Unassigned': 'Senza progetto',
  'Live map of your projects and missions. The list beside it has the same content.': 'Mappa viva dei tuoi progetti e delle tue missioni. L\'elenco accanto ha lo stesso contenuto.',
  'Constellation nodes. Select a row to focus its star.': 'Nodi della costellazione. Scegli una riga per portare il focus sulla sua stella.',
  'Map view': 'Vista della mappa', 'Zoom out': 'Riduci', 'Zoom in': 'Ingrandisci', 'Fit all nodes': 'Mostra tutti i nodi', 'Fit': 'Adatta',
  'Selected step': 'Passo selezionato', 'Categories': 'Categorie', 'Not recorded': 'Non registrato', 'Earlier': 'Prima', 'Later': 'Dopo', 'Step': 'Passo', 'Time': 'Ora', 'Category': 'Categoria', 'Trigger': 'Causa', 'Settled by': 'Chiuso da', 'Record': 'Registro',
  'What Core recorded, in order. Each step carries a Replay category and who settled it. Nothing here can be re-run.': 'Ciò che il Core ha registrato, in ordine. Ogni passo ha una categoria Replay e chi lo ha chiuso. Qui nulla può essere rieseguito.',
  'Older steps were pruned from the event log, so anything before them is UNKNOWN, not "nothing happened".': 'I passi più vecchi sono stati eliminati dal registro eventi, quindi ciò che li precede è SCONOSCIUTO, non "non è successo nulla".',
  'No recorded steps for this mission.': 'Nessun passo registrato per questa missione.', 'Nothing selected.': 'Niente di selezionato.',
  // Chat
  'Conversation': 'Conversazione', 'every reply is scripted and labelled': 'ogni risposta è scritta in anticipo ed etichettata', 'Send': 'Invia', 'Message to Archeus': 'Messaggio ad Archeus', 'Tell Archeus what you need...': 'Dì ad Archeus di cosa hai bisogno...',
  'You': 'Tu', 'Slash commands: type "/" for the list. READ and CREATE commands act at once; PROPOSE commands only make a card you confirm. Nothing you type leaves this page.': 'Comandi con slash: scrivi "/" per l\'elenco. I comandi READ e CREATE agiscono subito; i comandi PROPOSE fanno solo una scheda da confermare. Nulla di ciò che scrivi esce da questa pagina.',
  'Confirm': 'Conferma', 'Dismiss': 'Scarta', 'Confirmed': 'Confermato', 'Dismissed': 'Scartato', 'Commands': 'Comandi',
  // Settings and the new areas
  'Appearance': 'Aspetto', 'Motion ': 'Movimento ', 'Follow the system': 'Segui il sistema', 'Full': 'Pieno', 'Reduced (Quiet)': 'Ridotto (Quieto)',
  'Play': 'Avvia', 'Speed': 'Velocità', 'Trigger an approval': 'Genera una richiesta', 'Inject a failure': 'Inietta un guasto', 'Break the harness': 'Rompi l\'harness', 'Reset': 'Ripristina',
  'Accounts and usage': 'Account e utilizzo', '5 hour window': 'Finestra di 5 ore', 'Week': 'Settimana', 'Models and harnesses': 'Modelli e harness', 'Automations': 'Automazioni', 'Hooks, MCP servers and agents': 'Hook, server MCP e agenti', 'Clients': 'Client', 'About this prototype': 'Informazioni su questo prototipo',
  'unknown': 'sconosciuto',
  'Spawn breaker': 'Interruttore di avvio', 'Isolation and switches': 'Isolamento e interruttori', 'Checks': 'Controlli', 'Owner decisions': 'Decisioni del proprietario',
  'Not closed': 'Non chiuso', 'Built, switch off': 'Costruito, interruttore spento', 'Off': 'Spento', 'Built': 'Costruito', 'Closed': 'Chiuso', 'Open: cannot start': 'Aperto: non può avviare', 'ok': 'ok', 'attention': 'attenzione',
  'Everything here': 'Tutto qui', 'Go to': 'Vai a',
  // slash command descriptions (aliases are listed next to the name)
  'List the commands by class': 'Elenca i comandi per classe', 'What is running, waiting and stopped': 'Cosa è in corso, in attesa e fermo', 'Usage of the accounts (unknown until the read exists)': 'Utilizzo degli account (sconosciuto finché la lettura non esiste)', 'The projects': 'I progetti',
  'The missions, optionally of one project': 'Le missioni, eventualmente di un progetto', 'What waits for you': 'Cosa aspetta te', 'The ideas': 'Le idee', 'Open the Replay of a mission': 'Apri il Replay di una missione', 'Open a mission': 'Apri una missione',
  'Create a mission (it waits for your approval here)': 'Crea una missione (qui aspetta la tua approvazione)', 'Capture an idea': 'Cattura un\'idea', 'Propose pausing a mission': 'Proponi di mettere in pausa una missione', 'Propose resuming a mission': 'Proponi di riprendere una missione',
  'Propose cancelling a mission': 'Proponi di annullare una missione', 'Open the decision; it decides nothing': 'Apri la decisione; non decide nulla', 'Propose an emergency stop of every running mission': 'Proponi un arresto d’emergenza di ogni missione in corso'
};

const RULES = [
  [/^(\d+) needs? you$/, (m) => m[1] + (m[1] === '1' ? ' ti serve' : ' ti servono')], [/^(\d+) running$/, (m) => m[1] + ' in corso'], [/^(\d+) stopped$/, (m) => m[1] + (m[1] === '1' ? ' fermo' : ' fermi')],
  [/^Nothing needs you\.$/, () => 'Niente richiede la tua attenzione.'],
  [/^(\d+) more in Attention$/, (m) => m[1] + ' altri in Attenzione'],
  [/^(\d+) need you$/, (m) => m[1] + ' ti servono'],
  [/^(.+), step (\d) of 6\.$/, (m) => tr(m[1]) + ', passo ' + m[2] + ' di 6.'],
  [/^(.+) at step (\d) of 6 \((\w+)\)\.$/, (m) => tr(m[1]) + ' al passo ' + m[2] + ' di 6 (' + tr(m[3]) + ').'],
  [/^(.+), (\d) of 6 steps passed\.$/, (m) => tr(m[1]) + ', ' + m[2] + ' passi su 6 superati.'],
  [/^(.+), all 6 steps passed\.$/, (m) => tr(m[1]) + ', tutti i 6 passi superati.'], [/^(.+), not started\.$/, (m) => tr(m[1]) + ', non avviata.'],
  [/^(.+), position unknown\.$/, (m) => tr(m[1]) + ', posizione sconosciuta.'], [/^Cancelled\.$/, () => 'Annullata.'],
  [/^(.*)since (\d\d:\d\d)$/, (m) => m[1] + 'dalle ' + m[2]], [/^(.*)output (\d+) s ago$/, (m) => m[1] + 'output ' + m[2] + ' s fa'], [/^(.*)output (\d+) min ago$/, (m) => m[1] + 'output ' + m[2] + ' min fa'],
  [/^no output for (\d+) min$/, (m) => 'nessun output da ' + m[1] + ' min'], [/^Lost, Core is reconciling$/, () => 'Persa, il Core sta riconciliando'],
  [/^\(running, x([\d.]+)\)$/, (m) => '(in corso, x' + m[1] + ')'], [/^Expires (\d\d:\d\d)\. This is a simulated decision: nothing is run, sent or spent\.$/, (m) => 'Scade alle ' + m[1] + '. Decisione simulata: nulla viene eseguito, inviato o speso.'],
  [/^Decided: (.+)\.$/, (m) => 'Deciso: ' + tr(m[1]) + '.'], [/^Version (\d+)$/, (m) => 'Versione ' + m[1]],
  [/^(Approved|Rejected|Accepted|Changes requested|Unblocked|Resumed|Replanning|Cancelled|Pausing|Remembered|Not remembered|Enabled) \(simulated\)\.(.*)$/, (m) => ({ Approved: 'Approvata', Rejected: 'Rifiutata', Accepted: 'Accettata', 'Changes requested': 'Modifiche richieste', Unblocked: 'Sbloccata', Resumed: 'Ripresa', Replanning: 'Ripianificazione', Cancelled: 'Annullata', Pausing: 'In pausa', Remembered: 'Ricordato', 'Not remembered': 'Non ricordato', Enabled: 'Attivata' })[m[1]] + ' (simulato).' + (m[2] ? ' Nulla è stato eseguito.' : '')],
  [/^(\d+) nodes across (\d+) projects\. (\d+) need you\. .*$/, (m) => m[1] + ' nodi in ' + m[2] + ' progetti. ' + m[3] + ' ti servono. Usa Tab per scorrere le stelle, Invio per scegliere, le frecce per spostarti. La tabella equivalente segue i controlli della mappa.'],
  [/^(\d+) priority labels cannot fit\. .*$/, (m) => m[1] + ' etichette prioritarie non entrano. Le etichette complete sono nella tabella dei nodi.'],
  [/^(\d+) boxes$/, (m) => m[0]]
];

export function tr(s, ctx) {
  if (get('lang') !== 'it') return s;
  const lead = s.match(/^\s*/)[0], trail = s.match(/\s*$/)[0], core = s.trim();
  if (!core) return s;
  if (ctx && IT[ctx + core] != null) return lead + IT[ctx + core] + trail;
  if (IT[core] != null) return lead + IT[core] + trail;
  if (IT[s] != null) return IT[s];
  for (const [re, fn] of RULES) { const m = core.match(re); if (m) return lead + fn(m) + trail; }
  if (core.includes(' · ')) { const parts = core.split(' · '), out = parts.map((x) => tr(x)); if (out.some((x, k) => x !== parts[k])) return lead + out.join(' · ') + trail; }
  return s;
}

const ATTRS = ['aria-label', 'placeholder', 'title'];
export function translate(root) {
  if (get('lang') !== 'it' || !root) return;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  for (let n = w.currentNode; n; n = w.nextNode()) {
    if (n.nodeType === 3) {
      const p = n.parentElement; if (p && p.closest('pre')) continue; // the terminal view stays English
      const v = tr(n.nodeValue, p && p.classList.contains('gt') ? 'g:' : ''); if (v !== n.nodeValue) n.nodeValue = v;
    } else {
      for (const a of ATTRS) { const v = n.getAttribute(a); if (v) { const t = tr(v); if (t !== v) n.setAttribute(a, t); } }
    }
  }
}

// Italian command names are real aliases (T-153); the list is used by the chat menu and by sim.js
export const ALIASES = { help: 'aiuto', status: 'stato', usage: 'usa', projects: 'progetti', missions: 'missioni', needs: 'attesa', ideas: 'idee', replay: 'rigioca', open: 'apri', mission: 'missione', idea: 'idea', pause: 'pausa', resume: 'riprendi', cancel: 'annulla', approve: 'approva', estop: 'arresto' };

Object.assign(IT, IT_AREAS, IT_S6, IT_SHELL, IT_NOW, IT_WORK, IT_ATTN, IT_INSP, IT_CHAT, IT_PHONE, IT_AP, {
  'Pause, resume and emergency stop': 'Pausa, ripresa e arresto d’emergenza', 'Pause all': 'Metti tutto in pausa', 'Resume all': 'Riprendi tutto', 'Emergency stop': 'Arresto d’emergenza', 'Yes, stop everything': 'Sì, ferma tutto', 'Re-arm': 'Riarma', 'Yes, re-arm': 'Sì, riarma',
  'A vector constellation drawn from the simulation and redrawn at every size. Selecting a star opens it; the list beside it is the text mirror with the same content.': 'Una costellazione vettoriale disegnata dalla simulazione e ridisegnata a ogni dimensione. Selezionare una stella la apre; l’elenco accanto è lo specchio testuale con lo stesso contenuto.',
  'The shell, the map, the mission and decision views, chat, Replay and the terminal view are built on the simulation. A Core connection, real accounts and the native apps are not built.': 'La struttura, la mappa, le viste di missione e decisione, la chat, il Replay e la vista terminale sono costruiti sulla simulazione. La connessione a un Core, gli account reali e le app native non sono costruiti.',
  'The emergency stop is engaged: nothing new starts and no mission resumes until you re-arm. Re-arming needs a step-up (simulated here).': 'L’arresto d’emergenza è attivo: non parte nulla di nuovo e nessuna missione riprende finché non riarmi. Riarmare richiede una conferma rafforzata (simulata qui).',
  'Re-armed: new work can start again (simulated).': 'Riarmato: il nuovo lavoro può ripartire (simulato).', 'Show all projects': 'Mostra tutti i progetti', 'Project filter': 'Filtro progetto',
  'Pausing every running mission (simulated).': 'Metto in pausa ogni missione in corso (simulato).', 'Resuming every paused mission (simulated).': 'Riprendo ogni missione in pausa (simulato).', 'Emergency stop: every running mission stopped, new dispatch blocked until re-armed (simulated).': 'Arresto d’emergenza: ogni missione in corso è ferma, ogni nuovo avvio bloccato finché non riarmi (simulato).'
});
RULES.push(...RULES_AREAS, ...RULES_SHELL, ...RULES_NOW, ...RULES_WORK, ...RULES_ATTN, ...RULES_INSP, ...RULES_CHAT, ...RULES_PHONE, ...RULES_AP, [/^Project: (.+)$/, (m) => 'Progetto: ' + m[1]], [/^(\d+) running, (\d+) paused\. Pause all waits for each execution to reach a safe boundary\. Emergency stop ends every running execution; each mission then waits for you\.$/, (m) => m[1] + ' in corso, ' + m[2] + ' in pausa. Metti tutto in pausa aspetta che ogni esecuzione raggiunga un punto sicuro. L’arresto d’emergenza chiude ogni esecuzione in corso; ogni missione resta poi in attesa di te.']);
setTr(tr);
