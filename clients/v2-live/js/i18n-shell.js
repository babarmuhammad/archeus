// Italian for the shell slice: add exact strings to IT_SHELL and [regex, fn] rules to RULES_SHELL. Merged by i18n.js.
export const IT_SHELL = {
  'Emergency stop all missions': 'Arresto di emergenza di tutte le missioni', 'Re-arm new work': 'Riarma il nuovo lavoro',
  'Overview': 'Panoramica', 'Projects': 'Progetti', 'Tell': 'Dimmi', 'Stop': 'Ferma', 'Tools': 'Strumenti', 'Prototype tools': 'Strumenti del prototipo',
  'Not stopped': 'Non fermato', 'Stopped': 'Fermato', 'accepts new work': 'accetta nuovo lavoro', 'new work blocked': 'nuovo lavoro bloccato',
  'decision waiting': 'decisione in attesa', 'work running': 'lavoro in corso', 'all verified': 'tutto verificato', 'nothing running': 'niente in corso',
  'Decision notes on the Overview': 'Note sulle decisioni in Panoramica',
  'Nothing needs you': 'Niente ti serve', 'Last seen': 'Visto l’ultima volta', 'Search extensions': 'Cerca estensioni', 'Search extensions…': 'Cerca estensioni…',
  'No extension matches.': 'Nessuna estensione corrisponde.', 'Nothing is listed here.': 'Qui non c’è ancora nulla.', 'Extension types': 'Tipi di estensione', 'Open review': 'Apri la revisione',
  'Undo': 'Annulla', 'Clear search': 'Cancella la ricerca',
  'Settings sections': 'Sezioni delle impostazioni', 'Safety': 'Sicurezza', 'Prototype': 'Prototipo', 'About': 'Informazioni',
  'Govern': 'Governa', 'Configure': 'Configura', 'Search or run a command': 'Cerca o esegui un comando', 'Search pages, actions and projects': 'Cerca pagine, azioni e progetti',
  'Command palette': 'Comandi rapidi', 'Results': 'Risultati', 'Pages': 'Pagine', 'Actions': 'Azioni', 'Nothing matches. Try a page, an action or a project name.': 'Nessun risultato. Prova il nome di una pagina, di un’azione o di un progetto.',
  'move': 'muovi', 'run': 'esegui', 'close': 'chiudi', 'Stop all': 'Ferma tutto', 'Tell Archeus': 'Dì ad Archeus', 'Settings: Safety': 'Impostazioni: Sicurezza', 'Settings: Appearance': 'Impostazioni: Aspetto',
  'Settings: Prototype': 'Impostazioni: Prototipo', 'Language: Italiano': 'Lingua: Italiano', 'Language: English': 'Lingua: English', 'Stale': 'Non aggiornato',
  'Ctrl+K or Cmd+K': 'Ctrl+K o Cmd+K', 'Search pages, actions and projects, and run them': 'Cerca pagine, azioni e progetti ed eseguili',
  'Back to the app': 'Torna all’app', 'Show': 'Mostra', 'Hide': 'Nascondi',
  'Live work moves the map slowly: nodes drift, markers travel along active links and the core mark breathes. Reduced motion stops all of it.': 'Il lavoro in corso muove piano la mappa: i nodi si spostano appena, i segnalini viaggiano lungo i collegamenti attivi e il simbolo del Core respira. Il movimento ridotto ferma tutto.',
  'Simulated projects': 'Progetti simulati', 'Number of simulated projects': 'Numero di progetti simulati', '3 (the default story)': '3 (la storia predefinita)', 'Reloads the prototype with that many projects and the same mission mix, to see how every page scales.': 'Ricarica il prototipo con quel numero di progetti e la stessa miscela di missioni, per vedere come scala ogni pagina.',
  'Simulated clock': 'Orologio simulato', '. One real second is ten simulated seconds at x1. Same seed, same story.': '. Un secondo reale sono dieci secondi simulati a x1. Stesso seme, stessa storia.',
  'V2 Live is a prototype that simulates the Archeus app on every device. Nothing here is connected to a Core: the projects, missions, approvals, usage numbers and replies are fixtures and a scripted clock.': 'V2 Live è un prototipo che simula l’app Archeus su ogni dispositivo. Nulla qui è collegato a un Core: i progetti, le missioni, le approvazioni, i numeri di utilizzo e le risposte sono dati di prova e un orologio scritto.',
  'Six looks: Dark and Light, each standard and high contrast, plus System and forced colours. Reduced motion is Quiet (A05).': 'Sei aspetti: Scuro e Chiaro, ciascuno standard e ad alto contrasto, più Sistema e colori forzati. Il movimento ridotto è Quieto (A05).',
  'Everything on screen is simulated and says so; no Core is connected.': 'Tutto ciò che è sullo schermo è simulato e lo dice; nessun Core è collegato.'
};
export const RULES_SHELL = [
  [/^All (\d+) projects$/, (m) => 'Tutti i ' + m[1] + ' progetti'],
  [/^(\d+) extensions$/, (m) => m[1] + ' estensioni'], [/^(\d+) off$/, (m) => m[1] + ' spente'], [/^1 needs you$/, () => '1 ti serve'], [/^(\d+) need you$/, (m) => m[1] + ' ti servono'],
  [/^Today (\d\d:\d\d)$/, (m) => 'Oggi ' + m[1]], [/^Yesterday (\d\d:\d\d)$/, (m) => 'Ieri ' + m[1]], [/^Earlier (\d\d:\d\d)$/, (m) => 'Prima ' + m[1]],
  [/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\d\d:\d\d)$/, (m) => ({ Mon: 'Lun', Tue: 'Mar', Wed: 'Mer', Thu: 'Gio', Fri: 'Ven', Sat: 'Sab', Sun: 'Dom' })[m[1]] + ' ' + m[2]]
];
