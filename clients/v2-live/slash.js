// T-153 slash commands: registry, parser, menu filter. DOM-free, no Core. English names are canonical, each command has one Italian alias.
// Classes: READ and NAVIGATE answer, CREATE writes one record, PROPOSE only makes a card, NEVER is not in the menu and is refused.
// Copy: [English, Italian]. Source: .collab/T-153-slash-commands-spec.md (sections 2 to 4), clients/v2-prototype/slash.js (lead, rewritten).

export const CLASSES = ['READ', 'CREATE', 'PROPOSE', 'NAVIGATE'];
const SECRET = /(sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{12,}|Bearer\s+\S{8,})/;
export const looksSecret = (t) => SECRET.test(String(t));

// arg: none | opt | req. argKind: mission | project | text | choice | account. label: the argument step line.
export const COMMANDS = [
  { name: 'help', alias: 'aiuto', cls: 'NAVIGATE', arg: 'opt', argKind: 'text', label: ['Command (optional)', 'Comando (facoltativo)'], desc: ['List the commands, or the usage of one', 'Elenca i comandi, o come si usa uno'] },
  { name: 'status', alias: 'stato', cls: 'READ', arg: 'none', desc: ['Core, emergency state, running and waiting work', 'Core, stato di emergenza, lavoro in corso e in attesa'] },
  { name: 'usage', alias: 'usa', cls: 'READ', arg: 'opt', argKind: 'text', label: ['Account (optional)', 'Account (facoltativo)'], desc: ['Usage per account. Unknown until the usage read exists', 'Utilizzo per account. Sconosciuto finché la lettura non esiste'] },
  { name: 'projects', alias: 'progetti', cls: 'READ', arg: 'none', desc: ['The projects and their open missions', 'I progetti e le loro missioni aperte'] },
  { name: 'missions', alias: 'missioni', cls: 'READ', arg: 'opt', argKind: 'project', label: ['Project (optional)', 'Progetto (facoltativo)'], desc: ['The missions, optionally of one project', 'Le missioni, eventualmente di un progetto'] },
  { name: 'needs', alias: 'attesa', cls: 'READ', arg: 'none', desc: ['What waits for you. Nothing is decided here', 'Cosa aspetta te. Qui non si decide nulla'] },
  { name: 'digest', alias: 'riepilogo', cls: 'READ', arg: 'none', desc: ['What changed since you left', 'Cosa è cambiato da quando sei andato via'] },
  { name: 'ideas', alias: 'idee', cls: 'READ', arg: 'none', desc: ['The ideas', 'Le idee'] },
  { name: 'plan', alias: 'piano', cls: 'READ', arg: 'req', argKind: 'mission', label: ['Mission', 'Missione'], desc: ['Open the plan of a mission', 'Apri il piano di una missione'] },
  { name: 'why', alias: 'perche', cls: 'READ', arg: 'req', argKind: 'text', label: ['Decision id (for example rd-1)', 'Id della decisione (per esempio rd-1)'], desc: ['Explain one route decision', 'Spiega una decisione di instradamento'] },
  { name: 'search', alias: 'cerca', cls: 'READ', arg: 'req', argKind: 'text', label: ['Text to find', 'Testo da cercare'], desc: ['Search projects, missions and ideas', 'Cerca progetti, missioni e idee'] },
  { name: 'trace', alias: 'traccia', cls: 'NAVIGATE', arg: 'req', argKind: 'mission', label: ['Mission', 'Missione'], desc: ['Open the trace of a mission', 'Apri la traccia di una missione'] },
  { name: 'replay', alias: 'rigioca', cls: 'NAVIGATE', arg: 'opt', argKind: 'mission', label: ['Mission (optional)', 'Missione (facoltativa)'], desc: ['Open the Replay at a mission, or the latest', 'Apri il Replay di una missione, o dell\'ultima'] },
  { name: 'open', alias: 'apri', cls: 'NAVIGATE', arg: 'req', argKind: 'mission', label: ['Name or id', 'Nome o id'], desc: ['Open a project or a mission', 'Apri un progetto o una missione'] },
  { name: 'focus', alias: 'vai', cls: 'NAVIGATE', arg: 'req', argKind: 'project', label: ['Project', 'Progetto'], desc: ['Move the map to a project', 'Sposta la mappa su un progetto'] },
  { name: 'clear', alias: 'pulisci', cls: 'NAVIGATE', arg: 'none', desc: ['Hide earlier messages on this screen. History is kept', 'Nascondi i messaggi precedenti su questo schermo. La cronologia resta'] },
  { name: 'theme', alias: 'tema', cls: 'NAVIGATE', arg: 'req', argKind: 'choice', choices: ['system', 'light', 'dark', 'contrast'], label: ['system, light, dark or contrast', 'system, light, dark o contrast'], desc: ['Set the colour theme on this device', 'Imposta il tema dei colori su questo dispositivo'] },
  { name: 'motion', alias: 'movimento', cls: 'NAVIGATE', arg: 'req', argKind: 'choice', choices: ['full', 'quiet', 'reduced'], label: ['full, quiet or reduced', 'full, quiet o reduced'], desc: ['Set motion on this device', 'Imposta il movimento su questo dispositivo'] },
  { name: 'mission', alias: 'missione', cls: 'CREATE', arg: 'req', argKind: 'text', label: ['Mission in one line', 'Missione in una riga'], desc: ['Create a mission. A Start card asks next', 'Crea una missione. Poi una scheda chiede l\'avvio'] },
  { name: 'idea', alias: 'idea', cls: 'CREATE', arg: 'req', argKind: 'text', label: ['Idea in one line', 'Idea in una riga'], desc: ['Capture an idea. It is not a commitment', 'Cattura un\'idea. Non è un impegno'] },
  { name: 'feedback', alias: 'feedback', cls: 'CREATE', arg: 'req', argKind: 'text', label: ['Feedback', 'Feedback'], desc: ['Save feedback as a candidate', 'Salva un feedback come candidato'] },
  { name: 'remember', alias: 'ricorda', cls: 'CREATE', arg: 'req', argKind: 'text', label: ['What to remember', 'Cosa ricordare'], desc: ['Remember a fact, after a card names where', 'Ricorda un fatto, dopo una scheda che dice dove'] },
  { name: 'tell', alias: 'scrivi', cls: 'CREATE', arg: 'req', argKind: 'text', label: ['Message', 'Messaggio'], desc: ['Send the text as a plain message', 'Invia il testo come messaggio semplice'] },
  { name: 'general', alias: 'generale', cls: 'CREATE', arg: 'req', argKind: 'text', label: ['Question', 'Domanda'], desc: ['Ask in the general thread, outside project memory', 'Chiedi nel thread generale, fuori dalla memoria dei progetti'] },
  { name: 'start', alias: 'avvia', cls: 'PROPOSE', arg: 'req', argKind: 'mission', label: ['Mission', 'Missione'], desc: ['Propose starting a mission. A card asks first', 'Proponi di avviare una missione. Prima chiede una scheda'] },
  { name: 'stop', alias: 'ferma', cls: 'PROPOSE', arg: 'req', argKind: 'mission', label: ['Mission', 'Missione'], desc: ['Propose a stop. Two-step confirm', 'Proponi un arresto. Conferma in due passi'] },
  { name: 'estop', alias: 'arresto', cls: 'PROPOSE', arg: 'none', desc: ['Propose an emergency stop. Two-step confirm', 'Proponi un arresto d\'emergenza. Conferma in due passi'] },
  { name: 'pause', alias: 'pausa', cls: 'PROPOSE', arg: 'req', argKind: 'mission', label: ['Mission', 'Missione'], desc: ['Propose a pause. A card asks first', 'Proponi una pausa. Prima chiede una scheda'] },
  { name: 'resume', alias: 'riprendi', cls: 'PROPOSE', arg: 'req', argKind: 'mission', label: ['Mission', 'Missione'], desc: ['Propose a resume. A card asks first', 'Proponi di riprendere. Prima chiede una scheda'] },
  { name: 'cancel', alias: 'annulla', cls: 'PROPOSE', arg: 'req', argKind: 'mission', label: ['Mission', 'Missione'], desc: ['Propose a cancel. Cannot be undone, two-step', 'Proponi di annullare. Non si può disfare, due passi'] },
  { name: 'review', alias: 'rivedi', cls: 'PROPOSE', arg: 'req', argKind: 'mission', label: ['Mission', 'Missione'], desc: ['Open the review. The command decides nothing', 'Apri la revisione. Il comando non decide nulla'] },
  { name: 'approve', alias: 'approva', cls: 'PROPOSE', arg: 'req', argKind: 'mission', label: ['Mission', 'Missione'], desc: ['Open the approval card. The command decides nothing', 'Apri la scheda di approvazione. Il comando non decide nulla'] },
  { name: 'reject', alias: 'rifiuta', cls: 'PROPOSE', arg: 'req', argKind: 'mission', label: ['Mission', 'Missione'], desc: ['Open the approval card to reject. Decides nothing', 'Apri la scheda per rifiutare. Non decide nulla'] },
  { name: 'account', alias: 'account', cls: 'PROPOSE', arg: 'req', argKind: 'account', label: ['Account', 'Account'], desc: ['Propose a change to an account', 'Proponi una modifica a un account'], unavailable: ['Needs an admin device. Not on this device.', 'Serve un dispositivo amministratore. Non su questo dispositivo.'] }
];

// Typed, these are not commands and not in the menu (T-153 section 3.3). Value: [what to say, where to go (hash or null)].
export const NEVER = {
  project: [['/project is not available from chat. Create projects in Control on an admin device.', '/project non è disponibile dalla chat. Crea i progetti in Controllo su un dispositivo amministratore.'], null],
  delete: [['/delete is not available from chat. Nothing is deleted without a card; open Work.', '/delete non è disponibile dalla chat. Niente si elimina senza una scheda; apri Lavoro.'], '#/work'],
  archive: [['/archive is not available from chat. Open Work.', '/archive non è disponibile dalla chat. Apri Lavoro.'], '#/work'],
  run: [['/run is not available from chat. A command, shell or script never runs from here; open Work.', '/run non è disponibile dalla chat. Da qui non gira mai un comando, una shell o uno script; apri Lavoro.'], '#/work'],
  exec: [['/exec is not available from chat. Nothing runs from here; open Work.', '/exec non è disponibile dalla chat. Da qui non gira nulla; apri Lavoro.'], '#/work'],
  shell: [['/shell is not available from chat. Nothing runs from here.', '/shell non è disponibile dalla chat. Da qui non gira nulla.'], null],
  policy: [['/policy is not available from chat. Policy is changed in Control by an owner device.', '/policy non è disponibile dalla chat. La policy si cambia in Controllo da un dispositivo del proprietario.'], '#/security'],
  login: [['/login is not available from chat. Archeus never handles credentials.', '/login non è disponibile dalla chat. Archeus non gestisce mai credenziali.'], '#/accounts'],
  token: [['/token is not available from chat. Archeus never handles tokens.', '/token non è disponibile dalla chat. Archeus non gestisce mai token.'], '#/accounts'],
  pair: [['/pair is not available from chat. Pairing a device is done in Control.', '/pair non è disponibile dalla chat. L\'abbinamento di un dispositivo si fa in Controllo.'], '#/accounts'],
  push: [['/push is not available from chat. Nothing leaves Archeus from here.', '/push non è disponibile dalla chat. Da qui non esce nulla da Archeus.'], null]
};

export const find = (name) => { const n = String(name).toLowerCase(); return COMMANDS.find((c) => c.name === n || c.alias === n) || null; };
export const nameIn = (c, lang) => (lang === 'it' ? c.alias : c.name);
export const otherName = (c, lang) => (lang === 'it' ? c.name : c.alias);
const LANG = (lang) => (lang === 'it' ? 1 : 0);
export const descOf = (c, lang) => c.desc[LANG(lang)];
export const labelOf = (c, lang) => (c.label ? c.label[LANG(lang)] : '');

// Parse the composer text. null = plain chat text. kinds: text (// escape), menu, unknown, never, secret, usage, arg (needs an argument), unavailable, command.
export function parse(text) {
  const t = String(text).trim();
  if (t === '?') return { kind: 'command', cmd: find('help'), args: '' };
  if (t.startsWith('//') || t.startsWith('\\/')) return { kind: 'text', text: t.slice(1) };
  if (t.charAt(0) !== '/') return null;
  const m = /^\/(\S*)\s*([\s\S]*)$/.exec(t), typed = m[1] === '?' ? 'help' : m[1], args = m[2].trim();
  if (!typed) return { kind: 'menu' };
  const cmd = find(typed);
  if (!cmd) return NEVER[typed.toLowerCase()] ? { kind: 'never', name: typed.toLowerCase(), say: NEVER[typed.toLowerCase()][0], href: NEVER[typed.toLowerCase()][1] } : { kind: 'unknown', name: m[1] };
  if (cmd.unavailable) return { kind: 'unavailable', cmd, say: cmd.unavailable };
  if (cmd.arg === 'none' && args) return { kind: 'usage', cmd, say: ['/' + cmd.name + ' takes no arguments. Usage: /' + cmd.name, '/' + cmd.alias + ' non vuole argomenti. Uso: /' + cmd.alias] };
  if (cmd.arg === 'req' && !args) return { kind: 'arg', cmd };
  if (cmd.choices && args && !cmd.choices.includes(args.toLowerCase())) return { kind: 'usage', cmd, say: ['Usage: /' + cmd.name + ' ' + cmd.choices.join('|'), 'Uso: /' + cmd.alias + ' ' + cmd.choices.join('|')] };
  return { kind: 'command', cmd, args };
}

export function lev(a, b) {
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    prev = cur;
  }
  return prev[b.length];
}
const subseq = (q, s) => { let k = 0; for (let i = 0; i < s.length && k < q.length; i++) if (s[i] === q[k]) k++; return k === q.length; };

// 0 exact, 1 prefix, 2 contains, 3 fuzzy, 4 description word, -1 none.
function tier(c, q, lang) {
  const names = [c.name, c.alias];
  if (names.includes(q)) return 0;
  if (names.some((n) => n.startsWith(q))) return 1;
  if (names.some((n) => n.includes(q))) return 2;
  const max = c.name.length >= 4 && c.name.length <= 7 ? 1 : 2;
  if (q.length >= 3 && (lev(q, c.name.slice(0, q.length)) <= max || subseq(q, c.name))) return 3;
  if (c.desc[LANG(lang)].toLowerCase().includes(q) || c.desc[0].toLowerCase().includes(q)) return 4;
  return -1;
}

// Default order: recent names first (this device, names only), then READ, CREATE, PROPOSE, NAVIGATE, alphabetical inside a class.
export function ordered(recent) {
  const out = [];
  (recent || []).forEach((n) => { const c = find(n); if (c && !out.includes(c)) out.push(c); });
  CLASSES.forEach((k) => COMMANDS.filter((c) => c.cls === k).sort((a, b) => (a.name < b.name ? -1 : 1)).forEach((c) => { if (!out.includes(c)) out.push(c); }));
  return out;
}
export function filter(query, recent, lang) {
  const q = String(query || '').trim().toLowerCase(), base = ordered(recent);
  if (!q) return base;
  return base.map((c, i) => ({ c, t: tier(c, q, lang), i })).filter((x) => x.t >= 0).sort((a, b) => a.t - b.t || a.i - b.i).map((x) => x.c);
}

// What the combobox shows for the composer text: { mode: 'off' | 'commands' | 'arg' | 'mention', ... }.
export function menuFor(text, recent, lang) {
  const t = String(text);
  if (t === '?') return { mode: 'commands', items: ordered(recent), q: '' };
  if (!t.startsWith('/') || t.startsWith('//')) return { mode: 'off' };
  const sp = t.search(/\s/);
  if (sp < 0) { const items = filter(t.slice(1), recent, lang); return { mode: 'commands', items, q: t.slice(1) }; }
  const cmd = find(t.slice(1, sp));
  if (!cmd || cmd.unavailable) return { mode: 'off' };
  const rest = t.slice(sp + 1), at = /(?:^|\s)@([^\s"]*)$/.exec(rest);
  if (at) return { mode: 'mention', cmd, q: at[1], cut: t.length - at[1].length - 1 };
  if (cmd.arg === 'none') return { mode: 'off' };
  return { mode: 'arg', cmd, empty: !rest.trim() };
}
