// Italian for the work slice: add exact strings to IT_WORK and [regex, fn] rules to RULES_WORK. Merged by i18n.js.
// 2026-10-27: the Work page that also holds what Attention showed. 2026-10-28: saved views, detail pane, Replay modes and sections, project tabs and sort, the Attention strip.
// Not natively checked; listed in IT-REVIEW.md.
export const IT_WORK = {
  'All projects': 'Tutti i progetti',
  'Work graph': 'Grafo del lavoro',
  'No worktrees besides the main tree.': 'Nessun worktree oltre all\'albero principale.', 'All worktrees': 'Tutti i worktree', 'Filter by worktree': 'Filtra per worktree', 'Open project': 'Apri il progetto', 'Linked and task worktrees of this project': 'Worktree collegati e di attività di questo progetto',
  'Merge or drop its branch, then remove the folder yourself: Archeus never removes a linked worktree.': 'Unisci o scarta il suo ramo, poi rimuovi tu la cartella: Archeus non rimuove mai un worktree collegato.',
  'Archeus made it for a task. Finish or abandon the mission and Archeus removes it.': 'Lo ha creato Archeus per un\'attività. Concludi o abbandona la missione e Archeus lo rimuove.',
  'The folder is gone. Restore it or drop the branch: Archeus does not reset or recreate a linked worktree.': 'La cartella non c\'è più. Ripristinala o scarta il ramo: Archeus non reimposta né ricrea un worktree collegato.',
  'The folder is gone. Abandon the mission, or restore the folder.': 'La cartella non c\'è più. Abbandona la missione oppure ripristina la cartella.',
  'Nothing matches this filter.': 'Nessun risultato per questo filtro.', 'Clear filter': 'Azzera il filtro', 'Filter by state': 'Filtra per stato',
  'Work graph: missions and decisions grouped by what they wait on. The list below has the same content.': 'Grafo del lavoro: missioni e decisioni raggruppate per ciò che attendono. L\'elenco qui sotto ha lo stesso contenuto.',
  'One page for Work and Attention: missions and decisions grouped by what they wait on, as a list with a detail pane and as a graph. The spine shows where each mission is (A13); an obligation is a 12 % amber tint with its state in words (B09).': 'Una sola pagina per Lavoro e Attenzione: missioni e decisioni raggruppate per ciò che attendono, come elenco con un pannello di dettaglio e come grafo. La spina mostra a che punto è ogni missione (A13); un obbligo è una tinta ambra al 12 % con lo stato a parole (B09).',
  'Saved views': 'Viste salvate', 'Layout': 'Disposizione', 'List': 'Elenco', 'Graph': 'Grafo', 'Find a project': 'Cerca un progetto',
  'g:All': 'Tutto', 'g:Running': 'In corso', 'Selected work': 'Lavoro selezionato', 'What Archeus did': 'Cosa ha fatto Archeus',
  'Select a row to see what Archeus did.': 'Scegli una riga per vedere cosa ha fatto Archeus.',
  'awaiting input': 'in attesa di te', 'active': 'attivo', 'pending': 'in sospeso', 'error': 'errore', 'complete': 'completo', 'stale': 'fermo',
  'Nothing is stuck.': 'Niente è bloccato.', 'Nothing has finished yet.': 'Non è ancora finito nulla.', 'No work yet.': 'Ancora nessun lavoro.',
  'See what is running': 'Vedi cosa è in corso', 'Tell Archeus what to do': 'Dì ad Archeus cosa fare', 'now': 'ora',
  // Replay: view modes, detail levels, sections
  'Sections': 'Sezioni', 'View': 'Vista', 'Detail': 'Dettaglio', 'Compact': 'Compatta', 'Normal': 'Normale', 'g:Thinking': 'Ragionamento', 'Verbose': 'Dettagliata',
  'Events': 'Eventi', 'Recovery': 'Recupero', 'Reference': 'Riferimenti',
  // Projects: sort, tabs
  'Sort projects': 'Ordina i progetti', 'Name': 'Nome', 'Activity': 'Attività', 'Showing the latest 30 changes.': 'Mostro gli ultimi 30 cambiamenti.',
  // Overview: the Attention strip
  'Projects that need you': 'Progetti che hanno bisogno di te'
};
const n = (m, one, many) => (m === '1' ? one : many);
export const RULES_WORK = [
  [/^(\d+) missions and decisions$/, (m) => m[1] + ' missioni e decisioni'],
  [/^Showing (\d+) of (\d+)$/, (m) => 'Mostro ' + m[1] + ' di ' + m[2]],
  [/^(\d+)m ago$/, (m) => m[1] + ' min fa'], [/^(\d+)h ago$/, (m) => m[1] + ' h fa'], [/^(\d+)d ago$/, (m) => m[1] + ' g fa'],
  [/^No work in (.+) yet\.$/, (m) => 'Ancora nessun lavoro in ' + m[1] + '.'],
  [/^Pausing “(.+)”\.$/, (m) => 'Messa in pausa: “' + m[1] + '”.'],
  [/^(\d+) steps recorded$/, (m) => m[1] + ' passi registrati'],
  [/^(\d\d:\d\d) to (\d\d:\d\d)$/, (m) => m[1] + ' a ' + m[2]],
  [/^Last: (.+)$/, (m) => 'Ultimo: ' + m[1]],
  [/^(\d+) steps? needs? a look$/, (m) => m[1] + n(m[1], ' passo da guardare', ' passi da guardare')],
  [/^(\d+) steps$/, (m) => m[1] + ' passi'],
  [/^trigger (.+)$/, (m) => 'causa ' + m[1]], [/^by (.+)$/, (m) => 'da ' + m[1]],
  [/^(\w+) ([A-Z_ ]+) to ([A-Z_ ]+)$/, (m) => m[1] + ' ' + m[2] + ' a ' + m[3]],
  [/^(\d+) of (\d+) projects?$/, (m) => m[1] + ' di ' + m[2] + ' progetti'],
  [/^\+(\d+) more$/, (m) => '+' + m[1] + ' ' + n(m[1], 'altro', 'altri')]
];
