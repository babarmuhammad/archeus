/* T-153 slash commands, prototype. Registry, parser and menu filter only: no DOM, no Core call.
   app.js runs the commands on the fixtures. Classes: READ, CREATE, PROPOSE (cards only), NAVIGATE. */
(function (root) {
  var CLASSES = ['READ', 'CREATE', 'PROPOSE', 'NAVIGATE'];
  var SECRET = /(sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{12,}|Bearer\s+\S{8,})/;

  // args: none | opt | req. label: the argument step line. choices: allowed values, if fixed.
  var COMMANDS = [
    { name: 'help', alias: ['aiuto'], cls: 'NAVIGATE', args: 'opt', label: 'Command (optional)', en: 'List the commands, or the usage of one' },
    { name: 'status', alias: ['stato'], cls: 'READ', args: 'none', en: 'Core, emergency state, running and waiting work' },
    { name: 'usage', alias: ['usa'], cls: 'READ', args: 'opt', label: 'Account (optional)', en: 'Usage per account. Unknown until the usage card (T-154)' },
    { name: 'projects', alias: ['progetti'], cls: 'READ', args: 'none', en: 'List projects and their open missions' },
    { name: 'missions', alias: ['missioni'], cls: 'READ', args: 'opt', label: 'Project (optional)', en: 'List missions, optionally of one project' },
    { name: 'needs', alias: ['attesa'], cls: 'READ', args: 'none', en: 'Decisions waiting for you. Nothing is decided here' },
    { name: 'digest', alias: ['riepilogo'], cls: 'READ', args: 'none', en: 'Since you left' },
    { name: 'ideas', alias: ['idee'], cls: 'READ', args: 'none', en: 'List ideas' },
    { name: 'plan', alias: ['piano'], cls: 'READ', args: 'req', label: 'Mission', en: 'Open the plan of a mission' },
    { name: 'why', alias: ['perche'], cls: 'READ', args: 'req', label: 'Decision id', en: 'Explain one route decision' },
    { name: 'search', alias: ['cerca'], cls: 'READ', args: 'req', label: 'Text to find', en: 'Search projects and missions' },
    { name: 'trace', alias: ['traccia'], cls: 'NAVIGATE', args: 'req', label: 'Mission', en: 'Open the trace of a mission' },
    { name: 'replay', alias: ['rigioca'], cls: 'NAVIGATE', args: 'opt', label: 'Mission (optional)', en: 'Open the replay at a mission, or the latest' },
    { name: 'open', alias: ['apri'], cls: 'NAVIGATE', args: 'req', label: 'Name or id', en: 'Open a project or a mission' },
    { name: 'focus', alias: ['vai'], cls: 'NAVIGATE', args: 'req', label: 'Project', en: 'Move the view to a project' },
    { name: 'clear', alias: ['pulisci'], cls: 'NAVIGATE', args: 'none', en: 'Hide earlier messages on this screen. History is kept' },
    { name: 'theme', alias: ['tema'], cls: 'NAVIGATE', args: 'req', label: 'system, light, dark or contrast', choices: ['system', 'light', 'dark', 'contrast'], en: 'Set the colour theme on this device' },
    { name: 'motion', alias: ['movimento'], cls: 'NAVIGATE', args: 'req', label: 'full, quiet or reduced', choices: ['full', 'quiet', 'reduced'], en: 'Set motion on this device' },
    { name: 'mission', alias: ['missione'], cls: 'CREATE', args: 'req', label: 'Mission in one line', en: 'Create a mission in chat. Start is asked next' },
    { name: 'idea', alias: [], cls: 'CREATE', args: 'req', label: 'Idea in one line', en: 'Capture an idea. It is not a commitment' },
    { name: 'feedback', alias: [], cls: 'CREATE', args: 'req', label: 'Feedback', en: 'Save feedback as a candidate' },
    { name: 'remember', alias: ['ricorda'], cls: 'CREATE', args: 'req', label: 'What to remember', en: 'Remember a fact, after a confirm card names the scope' },
    { name: 'tell', alias: ['scrivi'], cls: 'CREATE', args: 'req', label: 'Message', en: 'Send the text as a plain message' },
    { name: 'general', alias: ['generale'], cls: 'CREATE', args: 'req', label: 'Question', en: 'Ask in the general thread, outside project memory' },
    { name: 'start', alias: ['avvia'], cls: 'PROPOSE', args: 'req', label: 'Mission', en: 'Propose starting a mission. A card asks first' },
    { name: 'stop', alias: ['ferma'], cls: 'PROPOSE', args: 'opt', label: 'Mission (optional)', en: 'Propose a stop. Two-step confirm' },
    { name: 'estop', alias: ['arresto'], cls: 'PROPOSE', args: 'none', en: 'Propose an emergency stop. Two-step confirm' },
    { name: 'pause', alias: ['pausa'], cls: 'PROPOSE', args: 'req', label: 'Mission or all', en: 'Propose a pause. All needs a card' },
    { name: 'resume', alias: ['riprendi'], cls: 'PROPOSE', args: 'req', label: 'Mission', en: 'Propose a resume' },
    { name: 'cancel', alias: ['annulla'], cls: 'PROPOSE', args: 'req', label: 'Mission', en: 'Propose a cancel. Irreversible, two-step' },
    { name: 'review', alias: ['rivedi'], cls: 'PROPOSE', args: 'opt', label: 'Mission (optional)', en: 'Open the decision. The command decides nothing' },
    { name: 'approve', alias: ['approva'], cls: 'PROPOSE', args: 'req', label: 'Mission', en: 'Open the approval card. The command decides nothing' },
    { name: 'reject', alias: ['rifiuta'], cls: 'PROPOSE', args: 'req', label: 'Mission', en: 'Open the rejection card. The command decides nothing' },
    { name: 'account', alias: [], cls: 'PROPOSE', args: 'req', label: 'Account', en: 'Propose a change to an account', unavailable: 'Needs an admin device. Not on this device.' }
  ];

  function find(name) {
    var n = String(name).toLowerCase();
    return COMMANDS.filter(function (c) { return c.name === n || c.alias.indexOf(n) >= 0; })[0] || null;
  }

  // Parse the composer text. null = plain chat text (sent as it is today).
  function parse(text) {
    var t = String(text).trim();
    if (t === '?') return { kind: 'command', cmd: find('help'), args: '' };
    if (t.indexOf('//') === 0 || t.indexOf('\\/') === 0) return { kind: 'text', text: t.slice(1) };
    if (t.charAt(0) !== '/') return null;
    var m = /^\/(\S*)\s*([\s\S]*)$/.exec(t), typed = m[1], args = m[2].trim();
    if (typed === '?') typed = 'help';
    if (!typed) return { kind: 'menu' };
    var cmd = find(typed);
    if (!cmd) return { kind: 'unknown', message: 'Unknown command /' + m[1] + '. Type / for the list, or //' + m[1] + ' to send the text as a message.' };
    if (args && SECRET.test(args)) return { kind: 'secret', message: 'This looks like a secret, so it was not sent.' };
    if (cmd.unavailable) return { kind: 'unavailable', cmd: cmd, message: cmd.unavailable };
    if (cmd.args === 'none' && args) return { kind: 'usage', message: '/' + cmd.name + ' takes no arguments. Usage: /' + cmd.name };
    if (cmd.args === 'req' && !args) return { kind: 'arg', cmd: cmd };
    if (cmd.choices && args && cmd.choices.indexOf(args.toLowerCase()) < 0) return { kind: 'usage', message: 'Usage: /' + cmd.name + ' ' + cmd.choices.join('|') };
    return { kind: 'command', cmd: cmd, args: args };
  }

  function lev(a, b) {
    var prev = [], cur, i, j;
    for (j = 0; j <= b.length; j++) prev[j] = j;
    for (i = 1; i <= a.length; i++) {
      cur = [i];
      for (j = 1; j <= b.length; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a.charAt(i - 1) === b.charAt(j - 1) ? 0 : 1));
      prev = cur;
    }
    return prev[b.length];
  }

  function subsequence(q, s) {
    var k = 0;
    for (var i = 0; i < s.length && k < q.length; i++) if (s.charAt(i) === q.charAt(k)) k++;
    return k === q.length;
  }

  // 0 name or alias starts with q, 1 contains q, 2 fuzzy name, 3 description word, -1 no match.
  function tier(c, q) {
    var names = [c.name].concat(c.alias);
    if (names.some(function (n) { return n === q; })) return 0;
    if (names.some(function (n) { return n.indexOf(q) === 0; })) return 1;
    if (names.some(function (n) { return n.indexOf(q) > 0; })) return 2;
    var max = c.name.length >= 4 && c.name.length <= 7 ? 1 : 2;
    if (q.length >= 3 && (lev(q, c.name.slice(0, q.length)) <= max || subsequence(q, c.name))) return 3;
    if (c.en.toLowerCase().indexOf(q) >= 0) return 4;
    return -1;
  }

  // Default order: recent names first (this device), then class order, alphabetical inside a class.
  function ordered(recent) {
    var out = [];
    (recent || []).forEach(function (n) { var c = find(n); if (c && out.indexOf(c) < 0) out.push(c); });
    CLASSES.forEach(function (k) {
      COMMANDS.filter(function (c) { return c.cls === k; }).sort(function (a, b) { return a.name < b.name ? -1 : 1; })
        .forEach(function (c) { if (out.indexOf(c) < 0) out.push(c); });
    });
    return out;
  }

  function filter(query, recent) {
    var q = String(query || '').trim().toLowerCase(), base = ordered(recent);
    if (!q) return base;
    var hits = [];
    base.forEach(function (c, i) { var t = tier(c, q); if (t >= 0) hits.push({ c: c, t: t, i: i }); });
    hits.sort(function (a, b) { return a.t - b.t || a.i - b.i; });
    return hits.map(function (h) { return h.c; });
  }

  var api = { COMMANDS: COMMANDS, CLASSES: CLASSES, find: find, parse: parse, filter: filter, lev: lev };
  root.ArchSlash = api;
})(typeof window !== 'undefined' ? window : globalThis);
