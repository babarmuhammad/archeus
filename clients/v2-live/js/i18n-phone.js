// Italian for the phone slice: add exact strings to IT_PHONE and [regex, fn] rules to RULES_PHONE. Merged by i18n.js.
export const IT_PHONE = {
  'Places': 'Luoghi', 'Re-arm': 'Riarma', 'Expand': 'Espandi', 'Collapse': 'Comprimi', 'Search': 'Cerca',
  'SIMULATED, prototype tools': 'SIMULATO, strumenti del prototipo',
  'Not stopped. Archeus accepts new work.': 'Non fermato. Archeus accetta nuovo lavoro.',
  'Stopped. New work is blocked until you re-arm.': 'Fermato. Il nuovo lavoro è bloccato finché non riarmi.',
  'Every running mission stops. New work is blocked until you re-arm.': 'Ogni missione in corso si ferma. Il nuovo lavoro è bloccato finché non riarmi.',
  'New work can start again.': 'Il nuovo lavoro può ripartire.', 'Re-arm new work?': 'Riarmare il nuovo lavoro?',
  'Show everything': 'Mostra tutto', 'Nothing here.': 'Niente qui.', 'Tap a node to see the mission.': 'Tocca un nodo per vedere la missione.',
  'Work graph: missions and decisions as nodes round the core. The list has the same content.': 'Grafo del lavoro: missioni e decisioni come nodi attorno al Core. L’elenco ha lo stesso contenuto.',
  'One page for Work and Attention: missions and decisions grouped by what they wait on, as a list and as a graph. The spine shows where each mission is (A13); an obligation is a 12 % amber tint with its state in words (B09).': 'Una sola pagina per Lavoro e Attenzione: missioni e decisioni raggruppate per ciò che attendono, come elenco e come grafo. La spina mostra a che punto è ogni missione (A13); un obbligo è una tinta ambra al 12 % con lo stato a parole (B09).'
};
export const RULES_PHONE = [
  [/^Stop all 1 mission\?$/, () => 'Fermare la missione in corso?'], [/^Stop all (\d+) missions\?$/, (m) => 'Fermare tutte le ' + m[1] + ' missioni?'],
  [/^(\d+) running, (\d+) paused$/, (m) => m[1] + ' in corso, ' + m[2] + ' in pausa'],
  [/^\+(\d+) more in the list$/, (m) => '+' + m[1] + ' altri nell’elenco'], [/^All (\d+) in Work$/, (m) => 'Tutti i ' + m[1] + ' in Lavoro'], [/^Show (\d+) more$/, (m) => 'Mostra altri ' + m[1]],
  [/^(Project filter|More states): (.+)$/, (m) => (m[1] === 'More states' ? 'Altri stati' : 'Filtro progetto') + ': ' + ({ 'All projects': 'Tutti i progetti', More: 'Altro' }[m[2]] || m[2])],
  [/^Work, (\d+) need you$/, (m) => 'Lavoro, ' + m[1] + (m[1] === '1' ? ' richiede la tua attenzione' : ' richiedono la tua attenzione')]
];
