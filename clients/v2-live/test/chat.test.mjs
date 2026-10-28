import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createSim } from '../sim.js';
import { createChat, fmt } from '../chat-engine.js';
import { buildReplay } from "../replay-model.js";
import { parse, menuFor, COMMANDS, find, CLASSES, ordered, filter } from '../slash.js';

const mk = () => { const sim = createSim({ strict: true }); let t = 1e6; const chat = createChat(sim, { now: () => t }); return { sim, chat, tick: (ms) => { t += ms; } }; };
const send = (c, text, o) => { const r = c.send(text, o); if (r.run) r.run(); return r; };
const last = (sim) => sim.state.messages.at(-1);

test('registry: 34 commands, one Italian alias each, every class present, unavailable /account', () => {
  assert.equal(COMMANDS.length, 34);
  CLASSES.forEach((k) => assert.ok(COMMANDS.some((c) => c.cls === k)));
  COMMANDS.forEach((c) => { assert.ok(c.alias && c.desc[0] && c.desc[1], c.name); assert.equal(find(c.alias).name, c.name); });
  assert.equal(parse('/account x').kind, 'unavailable');
});

test('parse: // escape, unknown, never, usage, argument step, ? help', () => {
  assert.deepEqual(parse('//idea x'), { kind: 'text', text: '/idea x' });
  assert.equal(parse('/xyz').kind, 'unknown');
  assert.equal(parse('/project').kind, 'never');
  assert.equal(parse('/status now').kind, 'usage');
  assert.equal(parse('/mission').kind, 'arg');
  assert.equal(parse('/theme pink').kind, 'usage');
  assert.equal(parse('?').cmd.name, 'help');
  assert.equal(parse('hello'), null);
  assert.equal(parse('/avvia fix').cmd.name, 'start');
});

test('menu order: recents, then READ, CREATE, PROPOSE, NAVIGATE; typing filters by name, alias and description', () => {
  const o = ordered(['stop', 'idea']).map((c) => c.name);
  assert.deepEqual(o.slice(0, 2), ['stop', 'idea']);
  const rest = o.slice(2).map((n) => find(n).cls);
  assert.deepEqual([...rest].sort((a, b) => CLASSES.indexOf(a) - CLASSES.indexOf(b)), rest);
  assert.equal(filter('stat', [], 'en')[0].name, 'status');
  assert.equal(filter('riprendi', [], 'it')[0].name, 'resume');
  assert.ok(filter('emergency', [], 'en').some((c) => c.name === 'estop'));
  assert.equal(menuFor('//x', [], 'en').mode, 'off');
  assert.equal(menuFor('/start ', [], 'en').mode, 'arg');
  assert.equal(menuFor('/start @no', [], 'en').mode, 'mention');
  assert.equal(menuFor('/status ', [], 'en').mode, 'off');
});

test('READ writes nothing recorded: the echo is local, the simulation log does not grow', () => {
  const { sim, chat } = mk(); const n = sim.state.messages.length, ev = sim.state.events.length;
  ['/status', '/projects', '/missions', '/ideas', '/needs', '/usage'].forEach((t) => send(chat, t));
  assert.equal(sim.state.messages.length, n); assert.equal(sim.state.events.length, ev);
  assert.ok(chat.thread().length >= 12);
  const u = chat.thread().find((m) => m.card && m.card.kind === 'usage');
  assert.match(fmt(u.c, 'en'), /Unknown/); assert.equal(u.card.rows.length, 3);
});

test('CREATE: /mission makes one mission that is NOT started; Start needs its card; Keep leaves it idle', () => {
  const { sim, chat } = mk(); const n = Object.keys(sim.state.missions).length;
  send(chat, '/mission Audit export labels');
  assert.equal(Object.keys(sim.state.missions).length, n + 1);
  const id = last(sim).card.mission; assert.equal(sim.state.missions[id].state, 'CREATED');
  assert.equal(last(sim).card.kind, 'start');
  assert.match(fmt(last(sim).c, 'en'), /Not started/);
  sim.advance(120000); assert.equal(sim.state.missions[id].state, 'CREATED', 'nothing starts by itself');
  const cid = last(sim).id;
  assert.equal(chat.card(cid, 'review').ok, true);
  assert.equal(last(sim).card.step, 'review');
  assert.equal(chat.card(cid, 'start').ok, true);
  assert.equal(sim.state.missions[id].state, 'UNDERSTANDING');
  assert.equal(chat.card(cid, 'start').ok, false, 'a card answers once');
  const b = mk(); send(b.chat, '/mission Keep me'); const id2 = last(b.sim).card.mission;
  b.chat.card(last(b.sim).id, 'keep'); b.sim.advance(300000);
  assert.equal(b.sim.state.missions[id2].state, 'CREATED');
});

test('CREATE: @project mention, /idea, /feedback', () => {
  const { sim, chat } = mk();
  send(chat, '/mission Tidy export @Notes'); const id = last(sim).card.mission;
  assert.equal(sim.state.missions[id].project, 'notes'); assert.equal(sim.state.missions[id].title, 'Tidy export');
  send(chat, '/idea quick widget'); assert.ok(sim.state.ideas.some((i) => i.title === 'quick widget')); assert.match(fmt(last(sim).c, 'en'), /not a commitment/);
  send(chat, '/feedback labels unclear'); assert.ok(sim.state.knowledge.some((k) => k.text === 'labels unclear' && k.state === 'CANDIDATE'));
  send(chat, '/mission x @Nowhere'); assert.match(fmt(last(sim).c, 'en'), /No project/);
});

test('PROPOSE: /stop and /cancel are two steps; nothing changes until the confirm', () => {
  const { sim, chat } = mk();
  send(chat, '/stop fix date'); const id = last(sim).id;
  const card = () => sim.state.messages.find((x) => x.id === id).card;
  assert.equal(sim.state.missions['m-date'].state, 'EXECUTING');
  assert.equal(chat.card(id, 'yes').ok, false, 'not before step two');
  chat.card(id, 'step2'); assert.equal(card().step, 'confirm'); assert.equal(sim.state.missions['m-date'].state, 'EXECUTING');
  assert.equal(chat.card(id, 'yes').ok, true);
  assert.equal(sim.state.missions['m-date'].state, 'BLOCKED');
  assert.equal(sim.state.executions['x-date-1'].state, 'ENDED_KILLED');
  send(chat, '/cancel export'); const c = last(sim); chat.card(c.id, 'step2'); chat.card(c.id, 'yes');
  assert.equal(sim.state.missions['m-export'].state, 'CANCELLED');
  send(chat, '/resume voice'); chat.card(last(sim).id, 'yes'); sim.advance(10000);
  assert.ok(['RESUMED', 'EXECUTING'].includes(sim.state.missions['m-voice'].state));
});

test('PROPOSE: /estop stops running executions only after both steps; Dismiss does nothing', () => {
  const { sim, chat, tick } = mk();
  send(chat, '/estop'); chat.card(last(sim).id, 'dismiss'); assert.equal(sim.state.missions['m-date'].state, 'EXECUTING');
  tick(3000); send(chat, '/estop'); const id2 = last(sim).id; chat.card(id2, 'step2'); chat.card(id2, 'yes');
  assert.equal(Object.values(sim.state.missions).filter((m) => m.state === 'EXECUTING').length, 0);
  tick(3000); send(chat, '/estop'); assert.match(fmt(last(sim).c, 'en'), /already engaged/); assert.equal(last(sim).card.href, '#/settings');
  assert.equal(sim.state.estop.engaged, true);
});

test('PROPOSE: /approve opens the card and decides nothing; the card needs a step-up; an approval id works', () => {
  const { sim, chat } = mk();
  const ap = sim.state.missions['m-search'].approval;
  send(chat, '/approve search'); const m = last(sim);
  assert.equal(m.card.kind, 'approval'); assert.equal(sim.state.approvals[ap].state, 'PENDING');
  chat.card(m.id, 'approve'); assert.equal(sim.state.approvals[ap].state, 'PENDING', 'step-up first');
  chat.card(m.id, 'confirm'); assert.equal(sim.state.approvals[ap].state, 'APPROVED');
  send(chat, '/reject ' + ap); assert.match(fmt(last(sim).c, 'en'), /already approved/);
});

test('refusals: bare approve, bulk delete, shell, policy; never commands send nothing', () => {
  const { sim, chat } = mk();
  for (const t of ['approve', 'delete all missions', 'run the migration shell command', 'change the policy limit']) {
    send(chat, t); assert.equal(last(sim).card.kind, 'refusal', t);
  }
  assert.match(fmt(sim.state.messages.at(-1).c, 'en'), /can’t do that from chat; open Work/);
  const m = sim.state.messages.length;
  assert.equal(chat.send('/project').ok, false); assert.equal(chat.send('/xyz').ok, false); assert.equal(sim.state.messages.length, m);
  assert.equal(chat.send('sk-abcdefghij1234').ok, false); assert.equal(chat.send('/mission').arg.name, 'mission');
});

test('general vs project: destination is explicit, a general answer is not project memory, Remember needs a destination and a confirm', () => {
  const { sim, chat } = mk(); const k0 = sim.state.knowledge.length, mi = Object.keys(sim.state.missions).length;
  send(chat, 'Explain a checkpoint', { dest: 'general' });
  const g = last(sim); assert.equal(g.card.kind, 'general'); assert.equal(g.dest, 'general');
  assert.equal(sim.state.knowledge.length, k0); assert.equal(Object.keys(sim.state.missions).length, mi);
  chat.card(g.id, 'remember'); const r = last(sim); assert.equal(r.card.kind, 'remember'); assert.equal(r.card.scope, '');
  assert.equal(chat.card(r.id, 'save').ok, false, 'no implicit destination');
  assert.equal(sim.state.knowledge.length, k0);
  assert.equal(chat.card(r.id, 'save', { scope: 'notes', excerpt: 'Checkpoint = handover point' }).ok, true);
  const k = sim.state.knowledge.at(-1); assert.equal(k.project, 'notes'); assert.equal(k.state, 'CONFIRMED');
  send(chat, '/remember all projects use UTC'); const r2 = last(sim); assert.equal(r2.card.scope, 'archeus');
  chat.card(r2.id, 'save', { scope: 'all' }); assert.equal(sim.state.knowledge.at(-1).project, null);
});

test('ambiguous text asks, it never guesses: "Answer this, or create work?"', () => {
  const { sim, chat } = mk(); const mi = Object.keys(sim.state.missions).length;
  send(chat, 'What is a checkpoint');
  assert.equal(last(sim).card.kind, 'choice'); assert.equal(Object.keys(sim.state.missions).length, mi);
  chat.card(last(sim).id, 'general'); assert.equal(last(sim).card.kind, 'general');
  send(chat, 'Create a mission to export backups and start it');
  assert.match(fmt(last(sim).c, 'en'), /Mission created\. Starting it needs your approval/);
  assert.equal(sim.state.missions[last(sim).card.mission].state, 'CREATED');
  send(chat, 'Create a project called Atlas');
  assert.ok(sim.state.projects.some((p) => p.name === 'Atlas'));
});

test('names: ambiguous matches ask with a list, unknown names list the closest, nothing sent', () => {
  const { chat } = mk();
  send(chat, '/open t'); const m = chat.thread().at(-1);
  assert.ok(m.card && m.card.kind === 'pick' && m.card.options.length <= 5);
  send(chat, '/open zzzz'); assert.match(fmt(chat.thread().at(-1).c, 'en'), /No project or mission named “zzzz”/);
});

test('send failure and retry: Not sent, same key, recorded once', () => {
  const { sim, chat } = mk(); const n = sim.state.messages.length;
  const r = chat.send('/idea fail once', { fail: true });
  assert.equal(r.failed, true); assert.equal(last(sim).status, 'failed'); assert.equal(sim.state.ideas.some((i) => i.title === 'fail once'), false);
  const key = last(sim).key; const re = chat.retry(last(sim).id); re.run(); re.run();
  assert.equal(sim.state.ideas.filter((i) => i.title === 'fail once').length, 1);
  assert.equal(sim.state.messages.length, n + 2); assert.equal(sim.state.messages.find((m) => m.key === key).status, 'sent');
});

test('the same text within 2 s asks first; force sends', () => {
  const { chat, tick } = mk();
  assert.equal(send(chat, '/idea twice').ok, true);
  tick(1000); const d = chat.send('/idea twice'); assert.equal(d.ok, false); assert.equal(d.dup.secs, 1);
  tick(1500); assert.equal(chat.send('/idea twice').ok, true);
  assert.equal(chat.send('/idea twice', { force: true }).ok, true);
});

test('/clear hides earlier messages but keeps the history; /theme returns a preference', () => {
  const { sim, chat } = mk(); const n = sim.state.messages.length;
  send(chat, '/clear'); assert.equal(chat.thread().length, 0); assert.equal(sim.state.messages.length, n);
  send(chat, 'hello'); assert.ok(chat.thread().length >= 1 && chat.thread().length < n + 4);
  const r = chat.send('/theme dark'); assert.ok(r.ok);
});

test('Italian copy: every reply carries both languages', () => {
  const { sim, chat } = mk();
  for (const t of ['/mission Prova', '/estop', '/status', '/idea x', '/pause fix', 'approve']) send(chat, t);
  [...sim.state.messages, ...chat.local()].filter((m) => m.from === 'archeus' && m.c).forEach((m) => { assert.ok(m.c && m.c.it && m.c.it !== m.c.en, m.text); });
});

test('// escape: the text is sent as ordinary text, the idea handler and the intent guesser do not run', () => {
  const { sim, chat } = mk(); const n = sim.state.ideas.length;
  send(chat, '//idea x'); assert.equal(sim.state.ideas.length, n);
  assert.equal(sim.state.messages.at(-2).text, '/idea x'); assert.match(fmt(last(sim).c, 'en'), /Sent as ordinary text/);
});

test('a reply carries the project it answers, so a slow reply is not filed under the project sent after it', () => {
  const { sim, chat } = mk();
  const a = chat.send('what is a mission', { project: 'archeus' }), b = chat.send('what is an idea', { project: 'notes' });
  b.run(); a.run();
  assert.deepEqual(sim.state.messages.slice(-2).map((m) => [m.from, m.project]), [['archeus', 'notes'], ['archeus', 'archeus']]);
});

// ---------- queue (Enter) and steer (Cmd/Ctrl+Enter) while a mission runs ----------
const untilLeft = (sim, id, from) => { for (let i = 0; i < 400 && sim.state.missions[id].state === from; i++) sim.advance(10000); };

test('queue: waits for the end of the step, then is answered; one message per send', () => {
  const { sim, chat } = mk(), base = sim.state.messages.filter((x) => x.from === 'archeus').length;
  const r = chat.send('Check the date again', { project: 'archeus', mode: 'queue' });
  assert.ok(r.queued && r.mission === 'm-date' && !r.run);
  const m = sim.state.messages.find((x) => x.id === r.id);
  assert.deepEqual([m.status, m.target], ['queued', 'm-date']);
  assert.equal(chat.queued('archeus').length, 1);
  assert.equal(sim.state.messages.at(-1).id, r.id, 'no reply yet');
  untilLeft(sim, 'm-date', 'EXECUTING');
  assert.equal(m.status, 'sent');
  assert.equal(chat.queued().length, 0);
  assert.equal(sim.state.messages.filter((x) => x.from === 'archeus').length, base + 1);
});

test('queue: a removed message is never sent', () => {
  const { sim, chat } = mk(), base = sim.state.messages.filter((x) => x.from === 'archeus').length;
  const r = chat.send('Check the date again', { project: 'archeus', mode: 'queue' });
  assert.equal(chat.unqueue(r.id), true);
  assert.equal(chat.unqueue(r.id), false);
  untilLeft(sim, 'm-date', 'EXECUTING');
  assert.equal(sim.state.messages.find((x) => x.id === r.id).status, 'withdrawn');
  assert.equal(sim.state.messages.filter((x) => x.from === 'archeus').length, base);
});

test('steer: steering until Core acknowledges, a request and an acknowledgement event, both said to be simulated', () => {
  const { sim, chat } = mk();
  const r = chat.send('Skip the slow test', { project: 'archeus', mode: 'steer' });
  const m = sim.state.messages.find((x) => x.id === r.id);
  assert.ok(r.steering);
  assert.equal(m.status, 'steering');
  const req = sim.state.events.find((e) => e.type === 'mission.steer_requested');
  assert.deepEqual([req.mission, req.actor], ['m-date', 'device']);
  sim.advance(31000);
  assert.equal(m.status, 'sent');
  const ack = sim.state.events.find((e) => e.type === 'mission.steer_acknowledged');
  assert.equal(ack.actor, 'system');
  assert.match(fmt(sim.state.messages.at(-1).c, 'en'), /^SIMULATED .*nothing changed course/);
  const steps = buildReplay(sim, 'm-date').steps.filter((s) => /^STEER_/.test(s.state));
  assert.deepEqual(steps.map((s) => [s.state, s.category]), [['STEER_REQUESTED', 'INTENDED'], ['STEER_ACKNOWLEDGED', 'RECORDED']]);
  assert.ok(steps.every((s) => /not prove|not that/.test(s.why)));
});

test('queue and steer: with nothing running, or for a command, both just send', () => {
  const { sim, chat } = mk();
  const a = chat.send('Check the notes', { project: 'notes', mode: 'queue' }), b = chat.send('/status', { project: 'archeus', mode: 'steer', force: true });
  assert.ok(a.run && !a.queued && sim.state.messages.find((x) => x.id === a.id).status === 'submitted');
  assert.ok(!b.steering && !sim.state.events.some((e) => e.type === 'mission.steer_requested'));
});

test('pins and recents: canonical names, pin order, recents capped at 8 and deduped, only valid commands survive', async () => {
  const { clean, togglePin, pushRecent, RECENT_CAP } = await import('../slash.js');
  assert.deepEqual(clean(['stato', 'status', 'nope', 'account', 7, 'aiuto']), ['status', 'help'], 'aliases become the English name, repeats, unknown names and /account drop out');
  assert.deepEqual(clean('not a list'), []);
  let pins = []; pins = togglePin(pins, 'stop'); pins = togglePin(pins, 'idea'); pins = togglePin(pins, 'status');
  assert.deepEqual(pins, ['stop', 'idea', 'status'], 'pin order is kept');
  assert.deepEqual(togglePin(pins, 'idea'), ['stop', 'status'], 'toggling again unpins');
  let r = []; for (const n of ['a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 'a8', 'a9']) r = pushRecent(r, n);
  assert.equal(r.length, RECENT_CAP); assert.equal(RECENT_CAP, 8); assert.deepEqual(r.slice(0, 2), ['a9', 'a8']);
  assert.deepEqual(pushRecent(['status', 'idea', 'stop'], 'idea'), ['idea', 'status', 'stop'], 'a repeat moves to the front once');
});

test('menu with no query: Pinned, then the last five Recent without repeating a pin, then the rest by class', () => {
  const g = menuFor('/', ['needs', 'status', 'idea', 'stop', 'plan', 'why', 'help'], 'en', ['status', 'digest']).groups;
  assert.deepEqual(g.map((x) => x.key), ['pinned', 'recent', 'READ', 'CREATE', 'PROPOSE', 'NAVIGATE']);
  assert.deepEqual(g[0].items.map((c) => c.name), ['status', 'digest']);
  assert.deepEqual(g[1].items.map((c) => c.name), ['needs', 'idea', 'stop', 'plan'], 'five recents, minus the pinned /status');
  const flat = g.flatMap((x) => x.items).map((c) => c.name);
  assert.equal(new Set(flat).size, flat.length, 'no command twice');
  assert.equal(flat.length, COMMANDS.length);
  assert.deepEqual(menuFor('/', [], 'en', []).groups.map((x) => x.key), ['READ', 'CREATE', 'PROPOSE', 'NAVIGATE'], 'no pins and no recents: no empty headings');
  assert.equal(menuFor('/st', [], 'en', []).groups, null, 'typing drops the headings');
});

test('ranking with a query: exact or prefix first, then pinned, then recent, then the others; Italian aliases match too', () => {
  const names = (q, rec, pins, lang = 'en') => filter(q, rec, lang, pins).map((c) => c.name);
  const plain = names('st', [], []);
  assert.deepEqual(plain.slice(0, 3), ['status', 'start', 'stop'], 'prefix matches first, class then alphabetical');
  assert.equal(names('st', [], ['stop'])[0], 'stop', 'a pinned prefix match leads the prefix matches');
  const contain = names('e', [], []), pinnedContain = names('e', [], ['review']), prefixCount = contain.filter((n) => n.startsWith('e') || find(n).alias.startsWith('e')).length;
  assert.equal(pinnedContain.indexOf('review'), prefixCount, 'pinned beats the others but never a prefix match');
  const recentContain = names('e', ['pause'], []);
  assert.equal(recentContain.indexOf('pause'), prefixCount, 'recent beats the others but never a prefix match');
  const both = names('e', ['pause'], ['review']);
  assert.ok(both.indexOf('review') < both.indexOf('pause'), 'pinned before recent');
  assert.equal(names('stato', [], [], 'it')[0], 'status', 'the Italian alias matches');
});

test('the slash menu shows one language: the chat never prints the other name of a command', async () => {
  const { readFileSync } = await import('node:fs');
  const src = readFileSync(new URL('../js/chat.js', import.meta.url), 'utf8');
  assert.ok(!/otherName\(/.test(src), 'no row prints the alias in the other language');
  assert.ok(!/a\.cmd\.name\b/.test(src), 'the destination line prints the active language name');
});
