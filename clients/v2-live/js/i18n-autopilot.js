// Italian for the Autopilot controls and notices: exact strings in IT_AP, [regex, fn] rules in RULES_AP. Merged by i18n.js. The chapter titles and captions carry their own Italian (autopilot-script.js).
export const IT_AP = {
  'Autopilot': 'Autopilot', 'Autopilot guided tour': 'Giro guidato Autopilot', 'Guided tour': 'Giro guidato', 'Autopilot controls': 'Controlli dell’Autopilot',
  'Previous chapter': 'Capitolo precedente', 'Next chapter': 'Capitolo successivo', 'Chapters': 'Capitoli',
  'Skipped a step: nothing to point at on this screen.': 'Passo saltato: su questa schermata non c’è nulla da indicare.',
  'Autopilot finished. Your settings are back as they were.': 'Autopilot terminato. Le tue impostazioni sono tornate come prima.',
  'Autopilot stopped because you used the app. Your settings are back as they were.': 'Autopilot fermato perché hai usato l’app. Le tue impostazioni sono tornate come prima.',
  'Autopilot stopped. Your settings are back as they were.': 'Autopilot fermato. Le tue impostazioni sono tornate come prima.'
};
export const RULES_AP = [[/^Chapter (\d+) of (\d+)$/, (m) => 'Capitolo ' + m[1] + ' di ' + m[2]]];
