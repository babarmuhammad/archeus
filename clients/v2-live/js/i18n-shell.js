// Italian for the shell slice: add exact strings to IT_SHELL and [regex, fn] rules to RULES_SHELL. Merged by i18n.js.
export const IT_SHELL = {
  'Emergency stop all missions': 'Arresto di emergenza di tutte le missioni', 'Re-arm new work': 'Riarma il nuovo lavoro',
  'Overview': 'Panoramica', 'Projects': 'Progetti', 'Tell': 'Dimmi', 'Stop': 'Ferma', 'Tools': 'Strumenti', 'Prototype tools': 'Strumenti del prototipo',
  'Not stopped': 'Non fermato', 'Stopped': 'Fermato', 'accepts new work': 'accetta nuovo lavoro', 'new work blocked': 'nuovo lavoro bloccato',
  'decision waiting': 'decisione in attesa', 'work running': 'lavoro in corso', 'all verified': 'tutto verificato', 'nothing running': 'niente in corso',
  'Decision notes on the Overview': 'Note sulle decisioni in Panoramica',
  'Back to the app': 'Torna all’app', 'Show': 'Mostra', 'Hide': 'Nascondi',
  'Live work moves the map slowly: nodes drift, markers travel along active links and the core mark breathes. Reduced motion stops all of it.': 'Il lavoro in corso muove piano la mappa: i nodi si spostano appena, i segnalini viaggiano lungo i collegamenti attivi e il simbolo del Core respira. Il movimento ridotto ferma tutto.',
  'Simulated clock': 'Orologio simulato', '. One real second is ten simulated seconds at x1. Same seed, same story.': '. Un secondo reale sono dieci secondi simulati a x1. Stesso seme, stessa storia.',
  'V2 Live is a prototype that simulates the Archeus app on every device. Nothing here is connected to a Core: the projects, missions, approvals, usage numbers and replies are fixtures and a scripted clock.': 'V2 Live è un prototipo che simula l’app Archeus su ogni dispositivo. Nulla qui è collegato a un Core: i progetti, le missioni, le approvazioni, i numeri di utilizzo e le risposte sono dati di prova e un orologio scritto.',
  'Six looks: Dark and Light, each standard and high contrast, plus System and forced colours. Reduced motion is Quiet (A05).': 'Sei aspetti: Scuro e Chiaro, ciascuno standard e ad alto contrasto, più Sistema e colori forzati. Il movimento ridotto è Quieto (A05).',
  'Everything on screen is simulated and says so; no Core is connected.': 'Tutto ciò che è sullo schermo è simulato e lo dice; nessun Core è collegato.'
};
export const RULES_SHELL = [
  [/^All (\d+) projects$/, (m) => 'Tutti i ' + m[1] + ' progetti'],
  [/^(\d+) extensions$/, (m) => m[1] + ' estensioni'], [/^(\d+) off$/, (m) => m[1] + ' spente'], [/^1 needs you$/, () => '1 ti serve']
];
