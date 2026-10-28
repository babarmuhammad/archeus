// Italian for the phone slice: add exact strings to IT_PHONE and [regex, fn] rules to RULES_PHONE. Merged by i18n.js.
export const IT_PHONE = {
  'Places': 'Luoghi', 'Re-arm': 'Riarma', 'Expand': 'Espandi', 'Collapse': 'Comprimi', 'Search': 'Cerca',
  'SIMULATED, prototype tools': 'SIMULATO, strumenti del prototipo',
  'Not stopped. Archeus accepts new work.': 'Non fermato. Archeus accetta nuovo lavoro.',
  'Stopped. New work is blocked until you re-arm.': 'Fermato. Il nuovo lavoro è bloccato finché non riarmi.',
  'Every running mission stops. New work is blocked until you re-arm.': 'Ogni missione in corso si ferma. Il nuovo lavoro è bloccato finché non riarmi.',
  'New work can start again.': 'Il nuovo lavoro può ripartire.', 'Re-arm new work?': 'Riarmare il nuovo lavoro?'
};
export const RULES_PHONE = [
  [/^Stop all 1 mission\?$/, () => 'Fermare la missione in corso?'], [/^Stop all (\d+) missions\?$/, (m) => 'Fermare tutte le ' + m[1] + ' missioni?'],
  [/^(\d+) running, (\d+) paused$/, (m) => m[1] + ' in corso, ' + m[2] + ' in pausa'],
  [/^Work, (\d+) need you$/, (m) => 'Lavoro, ' + m[1] + (m[1] === '1' ? ' ti serve' : ' ti servono')]
];
