// Italian for the insp slice: add exact strings to IT_INSP and [regex, fn] rules to RULES_INSP. Merged by i18n.js.
// Written by the builder, not checked by a native speaker: see IT-REVIEW.md.
export const IT_INSP = {
  'Overview': 'Panoramica', 'Back': 'Indietro', 'Breadcrumb': 'Percorso', 'Mission graph': 'Grafo della missione', 'Mission steps': 'Passi della missione',
  'Current phase': 'Fase attuale', 'Agent': 'Agente', 'Current task': 'Compito attuale', 'Latest record': 'Ultima registrazione', 'Activity log': 'Registro attività',
  'Plan steps': 'Passi del piano', 'Not recorded.': 'Non registrato.', 'Nothing recorded yet.': 'Ancora nulla di registrato.', 'Nothing has been decided yet.': 'Non è ancora stato deciso nulla.',
  'ORCHESTRATES': 'ORCHESTRA', 'EXECUTES': 'ESEGUE', 'RESULTS IN': 'PORTA A', 'USES': 'USA', 'PRODUCES': 'PRODUCE', 'VERIFIES': 'VERIFICA', 'Results': 'Risultati',
  'MISSION': 'MISSIONE', 'EXECUTION': 'ESECUZIONE', 'VERIFICATION': 'VERIFICA', 'REVIEW': 'REVISIONE', 'TASK': 'ATTIVITÀ', 'OUTPUT': 'RISULTATO', 'ARCHEUS': 'ARCHEUS',
  'What you approve': 'Cosa approvi', 'Why Archeus asks': 'Perché Archeus lo chiede', 'Phase': 'Fase',
};
export const RULES_INSP = [[/^Branch: (.+)$/, (m) => 'Ramo: ' + m[1]]];
