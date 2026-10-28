// Italian for the insp slice: add exact strings to IT_INSP and [regex, fn] rules to RULES_INSP. Merged by i18n.js.
// Written by the builder, not checked by a native speaker: see IT-REVIEW.md.
export const IT_INSP = {
  'Started': 'Avviata',
  'Station details': 'Dettagli delle fasi',
  'Understanding': 'Comprensione', 'Planning': 'In pianificazione', 'Approval': 'Approvazione',
  'Executing': 'Esecuzione', 'Verifying': 'Verifica', 'Reviewing': 'Revisione',
  'Projects scene': 'Scena dei progetti',
  'Select a project to see its phases, missions and ideas.': 'Seleziona un progetto per vedere fasi, missioni e idee.',
  'No projects yet.': 'Ancora nessun progetto.', 'No missions yet.': 'Ancora nessuna missione.',
  'No project ideas yet.': 'Ancora nessuna idea per questo progetto.', 'Project ideas': 'Idee del progetto',
  'Phases': 'Fasi', 'Recorded relation': 'Relazione registrata', 'Suggested relation': 'Relazione suggerita',
  'Active': 'Attiva', 'Waiting': 'In attesa', 'Verified': 'Verificata', 'Completed': 'Completata',
  'Nothing running in this project.': 'Niente in esecuzione in questo progetto.',
  'Work needs you in this project.': 'Il lavoro in questo progetto richiede la tua attenzione.',
  'Work is active in this project.': 'Il lavoro in questo progetto è attivo.',
  'Every mission is completed.': 'Tutte le missioni sono completate.',
  'Capture an idea': 'Cattura un’idea', 'Idea title': 'Titolo dell’idea', 'Capture': 'Cattura', 'Promote': 'Promuovi',
  'Phase summary across missions': 'Riepilogo delle fasi delle missioni',
  'Advance along the idea path': 'Avanza nel percorso dell’idea',
  'No launch settings recorded.': 'Nessuna impostazione di avvio registrata.',
  'Overview': 'Panoramica', 'Back': 'Indietro', 'Breadcrumb': 'Percorso', 'Mission graph': 'Grafo della missione', 'Mission steps': 'Passi della missione',
  'Current phase': 'Fase attuale', 'Agent': 'Agente', 'Current task': 'Compito attuale', 'Latest record': 'Ultima registrazione', 'Activity log': 'Registro attività',
  'Plan steps': 'Passi del piano', 'Not recorded.': 'Non registrato.', 'Nothing recorded yet.': 'Ancora nulla di registrato.', 'Nothing has been decided yet.': 'Non è ancora stato deciso nulla.',
  'ORCHESTRATES': 'ORCHESTRA', 'EXECUTES': 'ESEGUE', 'RESULTS IN': 'PORTA A', 'USES': 'USA', 'PRODUCES': 'PRODUCE', 'VERIFIES': 'VERIFICA', 'Results': 'Risultati',
  'MISSION': 'MISSIONE', 'EXECUTION': 'ESECUZIONE', 'VERIFICATION': 'VERIFICA', 'REVIEW': 'REVISIONE', 'TASK': 'ATTIVITÀ', 'OUTPUT': 'RISULTATO', 'ARCHEUS': 'ARCHEUS',
  'What you approve': 'Cosa approvi', 'Why Archeus asks': 'Perché Archeus lo chiede', 'Phase': 'Fase',
};
export const RULES_INSP = [[/^Branch: (.+)$/, (m) => 'Ramo: ' + m[1]], [/^(\d+) missions?$/, m => m[1] + (m[1] === '1' ? ' missione' : ' missioni')]];
