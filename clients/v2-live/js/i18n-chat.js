// Italian for the chat slice: add exact strings to IT_CHAT and [regex, fn] rules to RULES_CHAT. Merged by i18n.js.
// The chat surfaces build their own strings with L(en, it) (js/chat-cards.js); only the phase words shared with the inspectors live here.
export const IT_CHAT = {
  'Completed': 'Completato',
  'Waiting': 'In attesa',
  'Position unknown': 'Posizione sconosciuta',
  'Cancelled': 'Annullata',
  'Projects': 'Progetti',
  'Simulated keyboard': 'Tastiera simulata', 'Hide keyboard': 'Nascondi la tastiera',
  'Missions': 'Missioni',
  'A steer is a request to be taken at the next safe boundary. This is a simulation; a real Core would record the request, not that the mission changed course.': 'Una guida è una richiesta di essere presa al prossimo confine sicuro. Questa è una simulazione; un Core reale registrerebbe la richiesta, non che la missione abbia cambiato rotta.',
  'Core acknowledged the steer. The acknowledgement is recorded; it does not prove the mission changed course, and the boundary it took effect at is not modelled here.': 'Il Core ha confermato la guida. La conferma è registrata; non prova che la missione abbia cambiato rotta, e il confine in cui ha avuto effetto qui non è modellato.'
};
export const RULES_CHAT = [];
