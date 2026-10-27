// Italian for the Overview scene: exact strings in IT_NOW, [regex, fn] rules in RULES_NOW. Merged by i18n.js. Written by the builder, not native-checked: see IT-REVIEW.md.
export const IT_NOW = {
  'Agent execution': 'Esecuzione agente', 'No items yet': 'Ancora nessuna voce', 'items': 'voci', 'Today': 'Oggi', 'Known projects': 'Progetti noti', 'Tell': 'Dì', 'Today and known projects': 'Oggi e progetti noti', 'Understand · Plan · Do': 'Capisci · Pianifica · Fai',
  'Your projects. In context.': 'I tuoi progetti. Nel contesto.',
  'Nothing running. Tell Archeus what to do.': 'Niente in corso. Dì ad Archeus cosa fare.',
  'Archeus is quiet. Tell it what to do next, or open a project.': 'Archeus è a riposo. Digli cosa fare, oppure apri un progetto.',
  'Live constellation of your work. Missions, projects and ideas in context, moving forward together.': 'Costellazione viva del tuo lavoro. Missioni, progetti e idee nel loro contesto, che avanzano insieme.'
};
export const RULES_NOW = [[/^(\d+) items?$/, (m) => m[1] + ' voci'], [/^(\d+) verified$/, (m) => m[1] + (m[1] === '1' ? ' verificata' : ' verificate')]];
