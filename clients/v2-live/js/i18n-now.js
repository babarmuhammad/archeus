// Italian for the Overview scene: exact strings in IT_NOW, [regex, fn] rules in RULES_NOW. Merged by i18n.js. Written by the builder, not native-checked: see IT-REVIEW.md.
export const IT_NOW = {
  'Worktree': 'Worktree', 'Worktrees': 'Worktree', 'linked': 'collegato', 'task': 'attività', 'Missing': 'Mancante', 'Merged': 'Unito', 'Abandoned': 'Abbandonato', 'Last activity': 'Ultima attività', 'No mission': 'Nessuna missione', 'Attempt': 'Tentativo',
  'Open work': 'Apri il lavoro', 'Open mission': 'Apri la missione', 'No missions yet': 'Ancora nessuna missione', 'Agent execution': 'Esecuzione agente', 'No items yet': 'Ancora nessuna voce', 'items': 'voci', 'Today': 'Oggi', 'Known projects': 'Progetti noti', 'Tell': 'Dimmi', 'Today and known projects': 'Oggi e progetti noti', 'Understand · Plan · Do': 'Capisci · Pianifica · Fai',
  'Your projects. In context.': 'I tuoi progetti. Nel contesto.',
  'Nothing running. Tell Archeus what to do.': 'Niente in corso. Dì ad Archeus cosa fare.',
  'Archeus is quiet. Tell it what to do next, or open a project.': 'Archeus è a riposo. Digli cosa fare, oppure apri un progetto.',
  'Live constellation of your work. Missions, projects and ideas in context, moving forward together.': 'Costellazione viva del tuo lavoro. Missioni, progetti e idee nel loro contesto, che avanzano insieme.',
  'All projects': 'Tutti i progetti', 'Open work': 'Apri il lavoro', 'Show missions': 'Mostra le missioni', 'Open mission': 'Apri la missione', 'Overview view': 'Vista della panoramica', 'Territories: one cell per project': 'Territori: una cella per progetto', 'Rings: a lane per state': 'Anelli: una corsia per stato', 'Network: missions around each project': 'Rete: le missioni attorno a ogni progetto',
  'No missions yet': 'Ancora nessuna missione', 'Archeus': 'Archeus', 'Archeus has not completed a mission today.': 'Oggi Archeus non ha ancora completato nessuna missione.',
  'completed': 'ha completato', 'is verifying': 'sta verificando', 'is reviewing': 'sta rivedendo', 'started': 'ha avviato', 'asks you to approve': 'ti chiede di approvare', 'is blocked on': 'è bloccato su', 'has stopped': 'ha fermato', 'paused': 'ha messo in pausa'
};
export const RULES_NOW = [[/^(\d+) items?$/, (m) => m[1] + ' voci'],
  [/^\+(\d+) worktrees?$/, (m) => '+' + m[1] + ' worktree'], [/^(\d+) worktrees?$/, (m) => m[1] + ' worktree'],
  [/^Archeus completed (\d+) missions? today:$/, (m) => 'Oggi Archeus ha completato ' + (m[1] === '1' ? 'una missione' : m[1] + ' missioni') + ':'], [/^\+(\d+) more projects$/, (m) => '+' + m[1] + (m[1] === '1' ? ' altro progetto' : ' altri progetti')],
  [/^(\d+) missions?$/, (m) => m[1] + (m[1] === '1' ? ' missione' : ' missioni')], [/^(\d+) ideas? captured$/, (m) => m[1] + (m[1] === '1' ? ' idea raccolta' : ' idee raccolte')], [/^(\d+) ideas? captured, no missions yet$/, (m) => m[1] + (m[1] === '1' ? ' idea raccolta, ancora nessuna missione' : ' idee raccolte, ancora nessuna missione')],
  [/^(\d+) projects?\. (\d+) need you\.$/, (m) => m[1] + (m[1] === '1' ? ' progetto. ' : ' progetti. ') + (m[2] === '0' ? 'Nessuno ti serve.' : m[2] === '1' ? 'Ne serve uno a te.' : 'Ne servono ' + m[2] + ' a te.')], [/^\+(\d+) quiet$/, (m) => '+' + m[1] + ' inattive'], [/^(\d+) verified$/, (m) => m[1] + (m[1] === '1' ? ' verificata' : ' verificate')]];
