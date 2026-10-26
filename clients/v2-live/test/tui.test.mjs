import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createSim } from '../sim.js';
import { present } from '../core-words.js';
import { spineText } from '../spine-model.js';
import { createTui, LOOKS } from '../js/tui/controller.js';
import { parse, complete } from '../js/tui/cmd.js';
import { Canvas, clip, lr, wrap, len } from '../js/tui/cells.js';

const mk = (adv = 400, o = {}) => { const sim = createSim(); sim.advance(adv * 1000); return { sim, t: createTui(sim, Object.assign({ lang: () => 'en' }, o)) }; };
const rowsOf = (t, cols, rows) => t.frame({ cols, rows }).lines.map((l) => l.s.map((x) => x[0]).join(''));
const textOf = (t, cols = 100, rows = 60) => rowsOf(t, cols, rows).join('\n');
const SCREEN_KEYS = ['1', '2', '3', 'a', 'r', '4', '4 tab', '4 tab tab', '4 tab tab tab', '4 tab tab tab tab', '4 tab tab tab tab tab', '4 tab tab tab tab tab tab', '2 j j j enter', 'a enter', '?', 'g', ':', '/'];
const SIZES = [[30, 20], [40, 24], [60, 30], [80, 30], [100, 36], [110, 36], [120, 40], [150, 40], [160, 44], [200, 50]];

test('every screen fits its columns at every width, in unicode and in ascii', () => {
  for (const ascii of [false, true]) for (const k of SCREEN_KEYS) for (const [cols, rows] of SIZES) {
    const { t } = mk(400, { prefs: { ascii } }); t.frame({ cols, rows }); t.keys(k);
    const f = t.frame({ cols, rows });
    assert.equal(f.lines.length, rows, k + ' rows');
    for (const l of f.lines) {
      const s = l.s.map((x) => x[0]).join('');
      assert.ok(s.length <= cols, k + ' ' + cols + ': ' + s.length + ' ' + s);
      if (ascii) assert.ok(/^[\x20-\x7e]*$/.test(s), 'ascii only: ' + k + ' ' + cols + ' ' + s);
    }
  }
});

test('every glyph is one BMP code unit and not a wide character', () => {
  const seen = new Set();
  for (const k of SCREEN_KEYS) for (const [cols, rows] of [[80, 30], [160, 44]]) { const { t } = mk(); t.frame({ cols, rows }); t.keys(k); textOf(t, cols, rows).split('').forEach((c) => seen.add(c)); }
  for (const c of seen) { const n = c.codePointAt(0); assert.ok(n < 0xd800 || n > 0xdfff, 'surrogate ' + n); assert.ok(!(n >= 0x1100 && n <= 0x115f) && !(n >= 0x2e80 && n <= 0xa4cf) && !(n >= 0xac00 && n <= 0xd7a3) && !(n >= 0xff00 && n <= 0xff60), 'wide ' + c); assert.ok(n < 0x300 || n > 0x36f, 'combining ' + c); }
});

test('the first line says SIMULATED and that no Core is connected, at every width from 40', () => {
  for (const [cols, rows] of SIZES.slice(1)) { const l = rowsOf(mk().t, cols, rows)[0]; assert.match(l, /SIMULATED/); assert.match(l, /no Core connected/); }
});

test('parity: the state line, counts and sentence are the app model\'s', () => {
  const { sim, t } = mk(); const text = textOf(t);
  assert.ok(text.includes(sim.sentence().replace(/\.$/, '')), 'sentence');
  const c = sim.counts(); assert.ok(text.includes(c.need + ' need you'));
  const verifying = Object.values(sim.state.missions).filter((m) => m.state === 'VERIFYING').length; assert.ok(text.includes(verifying + ' verifying'));
  assert.ok(text.includes('RUNNING ' + sim.liveWork().length), 'core mark count');
});

test('parity: every mission has its state word and its spine cluster on Work', () => {
  const { sim, t } = mk(); t.keys('2'); const text = textOf(t, 100, 90);
  for (const m of Object.values(sim.state.missions)) {
    assert.ok(text.includes(m.title), m.title);
    assert.ok(text.includes(spineText(m.state, m.held_from, false)), m.title + ' ' + spineText(m.state, m.held_from, false));
  }
  const { t: ta } = mk(400, { prefs: { ascii: true } }); ta.keys('2'); const at = textOf(ta, 100, 90);
  for (const m of Object.values(sim.state.missions)) assert.ok(at.includes(spineText(m.state, m.held_from, true)), 'ascii ' + m.title);
});

test('parity: the first mission screen shows the same facts as the app inspector', () => {
  const { sim, t } = mk(); t.keys('2'); t.state.sel['work:list'] = 'mission:m-date'; t.frame({ cols: 100, rows: 40 }); t.key('enter');
  const text = textOf(t, 100, 40), m = sim.state.missions['m-date'];
  for (const s of ['State', present('mission', m.state).label, 'Project', 'Archeus', m.branch, m.origin, 'version ' + m.plan_version, '0 of 1 done']) assert.ok(text.includes(s), s);
  t.key('p'); assert.ok(textOf(t, 100, 40).includes('Run the date suite and fix the failing check'));
  t.key('n'); assert.match(textOf(t, 100, 40), /x-date-1/);
  t.key('e'); assert.match(textOf(t, 100, 40), /Verification|Nothing has been verified yet/);
  t.key('w'); assert.match(textOf(t, 100, 40), /Why it is in this state/i);
  t.key('t'); assert.match(textOf(t, 100, 40), /Last recorded steps/i);
  t.key('r'); assert.match(textOf(t, 100, 40), /Recorded relations/i);
});

test('parity: the decision card carries what, why, consequence and the spine', () => {
  const { sim, t } = mk(); t.keys('a enter'); const text = textOf(t, 100, 40), a = sim.state.approvals['a-1'];
  assert.equal(t.state.screen, 'decision');
  for (const s of [a.presented.what, a.presented.why, 'Approving starts 3 tasks', '✓✓◆○○○ Approval', '[Approve plan]'.slice(1, -1)]) assert.ok(text.includes(s), s);
});

test('parity: usage shows the numbers and "unknown", never a zero for a missing reading', () => {
  const { sim, t } = mk(); t.keys('4'); const text = textOf(t, 100, 60);
  assert.match(text, /5 hour window\s+unknown/); assert.ok(!/Codex, work[\s\S]{0,200}0%/.test(text));
  assert.ok(text.includes(Math.round(sim.state.usage['acc-personal'].window5h) + '%'));
  assert.ok(text.includes('5 h window resets 13:10'));
  t.keys('tab tab'); assert.equal(t.state.section, 'clients');
});

test('parity: security and health list what the simulation lists', () => {
  const { sim, t } = mk(); t.keys('g s'); assert.equal(t.state.section, 'security'); const sec = textOf(t, 100, 80);
  for (const x of sim.security()) { assert.ok(sec.includes(x.label.slice(0, 30)), x.label); assert.ok(sec.includes(x.word), x.word); }
  t.keys('g h'); const hl = textOf(t, 100, 80);
  for (const x of sim.health()) assert.ok(hl.includes(x.label), x.label);
  assert.match(hl, /Disk space[\s\S]*Unknown/);
});

test('parity: Replay rows and categories are the simulation\'s', () => {
  const { sim, t } = mk(); t.keys('r'); const r = sim.replay(t.state.mission), text = textOf(t, 120, 60);
  const m = Object.values(sim.state.missions)[t.state.replayMission], rr = sim.replay(m.id);
  assert.ok(text.includes(m.title));
  for (const row of rr.rows) { assert.ok(text.includes(row.category), row.category); assert.ok(text.includes(row.time + ' ' + row.category), row.time); }
  assert.ok(text.includes('NOT RECORDED') || text.includes('Not recorded') || /NOT RECORDED/i.test(text));
  for (const c of ['INTENDED', 'AUTHORIZED', 'RECORDED', 'MAY-HAVE-TAKEN-EFFECT', 'UNCERTAIN', 'SUSPENDED', 'RECONCILED', 'NONE', 'UNKNOWN']) assert.ok(text.includes(c), c);
  void r;
});

test('the map has every mission once, with the shapes of the encoding', () => {
  const { sim, t } = mk(); const f = t.frame({ cols: 160, rows: 50 }), map = f.panes.map;
  const ids = map.items.map((i) => i.mission).sort();
  assert.deepEqual(ids, Object.keys(sim.state.missions).sort());
  const text = textOf(t, 160, 50);
  for (const g of ['○', '▲', '◎']) assert.ok(text.includes(g), g);
  for (const p of sim.state.projects) assert.ok(text.includes(p.name), p.name);
  const { t: ta } = mk(400, { prefs: { ascii: true } }); const ft = textOf(ta, 160, 50);
  for (const g of ['o ', '^', '*']) assert.ok(ft.includes(g), 'ascii ' + g);
});

test('the map leaves out settled missions when it is short of room and says how many', () => {
  const { t } = mk(); const small = t.frame({ cols: 40, rows: 20 }).panes.map.lines.length, big = t.frame({ cols: 40, rows: 60 }).panes.map.lines.length;
  assert.ok(small < big, small + ' < ' + big); assert.match(t.frame({ cols: 40, rows: 20 }).panes.map.lines.map((l) => l.s.map((x) => x[0]).join('')).join(' '), /1 hidden/);
});

test('keys: j k and arrows move, Enter opens, Esc goes back, q leaves from Now', () => {
  let left = 0; const { t } = mk(400, { onQuit: () => { left++; } });
  t.frame({ cols: 100, rows: 36 });
  const sel = () => t.selected() && t.selected().key;
  const first = sel(); t.key('j'); assert.notEqual(sel(), first); t.key('k'); assert.equal(sel(), first);
  t.key('down'); t.key('up'); assert.equal(sel(), first);
  t.key('enter'); assert.equal(t.state.screen, 'decision'); t.key('esc'); assert.equal(t.state.screen, 'now');
  t.keys('2 j enter'); assert.equal(t.state.screen, 'mission'); t.key('b'); assert.equal(t.state.screen, 'work');
  t.key('q'); assert.equal(t.state.screen, 'now'); t.key('q'); assert.equal(left, 1);
});

test('keys: Tab switches panes on Now and tabs on a mission', () => {
  const { t } = mk(); t.frame({ cols: 120, rows: 40 }); assert.equal(t.state.focus, 'list');
  t.key('tab'); assert.equal(t.state.focus, 'map'); t.key('tab'); assert.equal(t.state.focus, 'detail'); t.key('tab'); assert.equal(t.state.focus, 'list'); t.key('shift-tab'); assert.equal(t.state.focus, 'detail');
  t.keys('2 j enter'); t.key('tab'); assert.equal(t.state.tab, 'plan'); t.key('shift-tab'); t.key('shift-tab'); assert.equal(t.state.tab, 'relations');
});

test('keys: in the map pane j k and left right walk the nodes', () => {
  const { t } = mk(); t.frame({ cols: 160, rows: 40 }); t.key('tab'); assert.equal(t.state.focus, 'map');
  const k0 = t.selected().key; t.key('j'); const k1 = t.selected().key; assert.notEqual(k0, k1);
  t.key('right'); const k2 = t.selected().key; assert.notEqual(k1, k2); t.key('left'); assert.equal(t.selected().key.startsWith('mission:'), true);
});

test('the decision keys: approve asks first, y approves, any other key cancels, nothing is decided without the card', () => {
  const { sim, t } = mk(); t.keys('a enter'); assert.equal(sim.state.approvals['a-1'].state, 'PENDING');
  t.key('A'); assert.equal(t.state.mode.kind, 'confirm'); assert.match(textOf(t), /Type|\[y\] Yes/); t.key('x'); assert.equal(t.state.mode, null); assert.equal(sim.state.approvals['a-1'].state, 'PENDING');
  t.key('A'); t.key('y');
  assert.equal(sim.state.missions['m-search'].state, 'APPROVED'); assert.equal(t.state.screen, 'attention');
  assert.match(t.frame({ cols: 100, rows: 30 }).lines.at(-1).s.map((x) => x[0]).join(''), /Approved \(simulated\)/);
});

test('the decision keys: reject cancels the mission and a letter that is not an action does nothing', () => {
  const { sim, t } = mk(); t.keys('a enter'); t.key('R'); t.key('y');
  assert.equal(sim.state.approvals['a-1'].state, 'REJECTED'); assert.equal(sim.state.missions['m-search'].state, 'CANCELLED');
  const { sim: s2, t: t2 } = mk(); t2.keys('2'); assert.equal(t2.key('Q'), false); assert.equal(s2.state.missions['m-search'].state, 'APPROVAL_REQUIRED');
});

test('actions follow the state: pause a running mission, resume a paused one, replan a failed one, accept a reviewed one', () => {
  const { sim, t } = mk(30);
  const pick = (id) => { t.go('work'); t.frame({ cols: 100, rows: 60 }); t.state.sel['work:list'] = 'mission:' + id; t.frame({ cols: 100, rows: 60 }); };
  pick('m-date'); assert.deepEqual(t.actions(t.selected()).map((a) => a.key), ['P']); t.key('P'); assert.equal(t.state.mode, null);
  sim.advance(20000); assert.equal(sim.state.missions['m-date'].state, 'PAUSED');
  pick('m-voice'); assert.ok(t.actions(t.selected()).some((a) => a.label === 'Resume')); t.key('R'); sim.advance(60000); assert.equal(sim.state.missions['m-voice'].state, 'EXECUTING');
  pick('m-lint'); t.key('R'); sim.advance(1000); assert.equal(sim.state.missions['m-lint'].state, 'REPLANNING');
  pick('m-export'); assert.ok(t.actions(t.selected()).some((a) => a.label === 'Answer and unblock'));
});

test('emergency stop asks, then stops every running mission', () => {
  const { sim, t } = mk(30); t.key('E'); assert.equal(t.state.mode.kind, 'confirm'); t.key('y'); sim.advance(10000);
  assert.equal(Object.values(sim.state.missions).filter((m) => m.state === 'EXECUTING').length, 0);
  assert.equal(sim.state.missions['m-date'].reason, 'Emergency stop');
  t.key('E'); assert.match(t.frame({ cols: 100, rows: 30 }).lines.at(-1).s.map((x) => x[0]).join(''), /Nothing is running/);
});

test('places: g then a letter goes there', () => {
  const { t } = mk(); for (const [k, id] of [['1', 'now'], ['2', 'work'], ['3', 'world'], ['a', 'attention'], ['r', 'replay'], ['4', 'control']]) { t.keys('g'); assert.equal(t.state.mode.kind, 'places'); t.key(k); assert.equal(t.state.screen, id); }
  t.keys('g u'); assert.equal(t.state.section, 'accounts'); t.keys('g s'); assert.equal(t.state.section, 'security'); t.keys('g h'); assert.equal(t.state.section, 'health');
});

test('the help overlay lists the keys and the commands, and any key closes it', () => {
  const { t } = mk(); t.key('?'); const text = textOf(t, 100, 40);
  for (const s of ['Keys and help', 'Tab', 'Esc', '/status', 'emergency stop']) assert.ok(text.includes(s), s);
  t.key('x'); assert.equal(t.state.mode, null);
});

test('the command line: places, slash commands, a mission by name, and plain text for Archeus', () => {
  const { sim, t } = mk();
  t.openCmd(''); t.cmdSet('wo'); assert.match(textOf(t), /Go to Work/); t.key('enter'); assert.equal(t.state.screen, 'work');
  t.openCmd(''); t.cmdSet('search'); t.key('down'); t.key('enter');
  t.go('now'); t.openCmd('/'); assert.match(textOf(t), /\/status/); t.cmdSet('/stat'); t.key('tab'); assert.equal(t.state.mode.buf, '/status'); t.cmdSet('/paus'); t.key('tab'); assert.equal(t.state.mode.buf, '/pause ');
  t.cmdSet('/status'); t.key('enter'); assert.equal(t.state.mode.kind, 'reply'); assert.match(textOf(t), /Archeus \(simulated reply\)/);
  assert.ok(sim.state.messages.at(-1).text.includes('Simulated reply'));
  t.key('x'); assert.equal(t.state.mode, null);
  t.openCmd(''); t.cmdSet('hello there'); t.cmdSubmit(); assert.equal(sim.state.messages.at(-2).text, 'hello there');
});

test('the command line: /pause makes a card, y confirms it and the mission pauses; /nope keeps the draft', () => {
  const { sim, t } = mk(30);
  t.openCmd('/'); t.cmdSet('/pause fix'); t.cmdSubmit(); assert.equal(t.state.mode.kind, 'reply'); assert.equal(sim.state.missions['m-date'].state, 'EXECUTING');
  t.key('y'); sim.advance(10000); assert.equal(sim.state.missions['m-date'].state, 'PAUSED');
  t.openCmd('/'); t.cmdSet('/nope'); t.cmdSubmit(); assert.equal(t.state.mode.kind, 'cmd'); assert.equal(t.state.mode.buf, '/nope'); assert.match(t.frame({ cols: 100, rows: 30 }).lines.at(-3).s.map((x) => x[0]).join('') + textOf(t), /Unknown command|No such command/);
  t.cmdSet('/mission x sk-abcdefghij'); t.cmdSubmit(); assert.equal(t.state.mode.kind, 'cmd');
});

test('the command line: a card with a link opens the screen it names', () => {
  const { t } = mk(); t.openCmd('/'); t.cmdSet('/replay search'); t.cmdSubmit(); assert.equal(t.state.mode.msg.card.href, '#/replay/m-search'); t.key('enter');
  assert.equal(t.state.screen, 'replay'); assert.match(textOf(t), /Search provenance/);
});

test('the slash grammar is shared with the chat: names, Italian aliases, arguments', () => {
  assert.equal(parse('/stato').cmd.name, 'status'); assert.equal(parse('/pausa fix').arg, 'fix'); assert.equal(parse('/nope').kind, 'unknown');
  assert.equal(parse('/status x').kind, 'error'); assert.equal(parse('//status').kind, 'tell'); assert.equal(parse('hi').kind, 'text'); assert.equal(parse('  ').kind, 'empty');
  assert.ok(complete('/p', 'en').every((c) => c.insert.startsWith('/p'))); assert.ok(complete('/ap', 'it').some((c) => c.insert === '/apri ' || c.insert === '/approva '));
  assert.ok(complete('/', 'en').length >= 16);
});

test('the key hints are in Italian when the language is Italian', () => {
  const it = mk(400, { lang: () => 'it' }).t, en = mk().t;
  const a = rowsOf(it, 120, 36), b = rowsOf(en, 120, 36);
  assert.ok(a.join('\n').includes('muovi') && a.join('\n').includes('apri') && a.join('\n').includes('aiuto'));
  assert.ok(b.join('\n').includes('move') && b.join('\n').includes('help'));
  assert.ok(a[1].includes('Adesso') && a[1].includes('Attenzione'));
  it.key('?'); assert.ok(textOf(it, 100, 40).includes('Tasti e aiuto'));
});

test('reduced motion: the core mark is the static glyph; with motion it swaps slowly, and only with live work', () => {
  const { t } = mk(400, { reduced: () => true }); t.setBreath(false); assert.ok(textOf(t, 80, 30).includes('◎ ARCHEUS')); assert.ok(!textOf(t, 80, 30).includes('◉'));
  const m = mk(400, { reduced: () => false }).t; m.setBreath(true); assert.ok(textOf(m, 80, 30).includes('◉ ARCHEUS'));
  assert.match(rowsOf(mk(400, { reduced: () => true }).t, 100, 30)[2], /Quiet/);
});

test('looks and glyphs are prefs: L cycles the four looks, G toggles ascii, T the linear mode; the prefs call back', () => {
  let got = null; const { t } = mk(400, { onPrefs: (p) => { got = Object.assign({}, p); } });
  assert.deepEqual(LOOKS.map((x) => x.id), ['app', 'ansi', 'hc', 'mono']);
  t.key('L'); assert.equal(t.prefs.look, 'ansi'); t.key('L'); t.key('L'); assert.equal(t.prefs.look, 'mono'); t.key('L'); assert.equal(t.prefs.look, 'app');
  t.key('G'); assert.equal(got.ascii, true); assert.ok(/^[\x20-\x7e\n]*$/.test(textOf(t, 100, 40))); t.key('T'); assert.equal(got.linear, true);
});

test('a selection stays on the same thing when the list changes under it', () => {
  const { sim, t } = mk(30); t.go('work'); t.frame({ cols: 100, rows: 60 }); t.state.sel['work:list'] = 'mission:m-voice'; t.frame({ cols: 100, rows: 60 });
  sim.act('approve', 'a-1'); sim.advance(60000);
  assert.equal(t.frame({ cols: 100, rows: 60 }) && t.selected().key, 'mission:m-voice');
});

test('the screen reader line of a spine is the generated sentence, and every state glyph has a word', () => {
  const { t } = mk(); const f = t.frame({ cols: 100, rows: 40 });
  const spineLine = f.lines.find((l) => l.s.some((x) => x[3] && /step 3 of 6/.test(x[3])));
  assert.ok(spineLine, 'a spine carries its sentence');
  for (const l of f.lines) for (const x of l.s) if (/[◆●■✓✕‖◌]/.test(x[0]) && x[0].length === 1 && x[1].includes('b') === false && !(x[1] === 'ln')) assert.ok(x[3] !== undefined || x[1] !== '', 'glyph with a word or a role: ' + x[0]);
});

test('the layout tier follows the number of columns', () => {
  const { t } = mk(); for (const [cols, tier] of [[40, '40'], [59, '40'], [60, '80'], [109, '80'], [110, '120'], [149, '120'], [150, '160'], [200, '160']]) assert.equal(t.frame({ cols, rows: 30 }).tier, tier);
});

test('wide screens show the selected thing beside the list; narrow ones do not', () => {
  const { t } = mk(); assert.ok(textOf(t, 140, 40).includes('Approve this plan?')); assert.ok(!textOf(t, 80, 40).includes('Approve this plan?'));
  t.keys('2'); assert.ok(textOf(t, 140, 40).includes('WHERE IT IS') || textOf(t, 140, 40).includes('Where it is') || /WHERE THE MISSION IS/.test(textOf(t, 140, 40)));
});

test('the route follows the screen: deep links open the screen, missions and decisions by id', () => {
  const { t } = mk(); assert.equal(t.routeId(), ''); t.route('work'); assert.equal(t.state.screen, 'work'); t.route('m-date'); assert.equal(t.state.screen, 'mission'); assert.equal(t.routeId(), 'm-date');
  t.route('a-1'); assert.equal(t.state.screen, 'decision'); t.route('security'); assert.equal(t.state.section, 'security'); assert.equal(t.routeId(), 'security'); t.route('help'); assert.equal(t.state.mode.kind, 'help'); t.route('');
  assert.equal(t.state.screen, 'now');
});

test('cells: clip, lr and wrap keep to their width', () => {
  assert.equal(len(clip([['abcdef', '']], 4)), 4); assert.equal(len(lr([['left text here', '']], [['right', '']], 24)), 24); assert.ok(wrap('one two three four five six', 9).every((l) => l.length <= 9));
  const c = new Canvas(6, 2); c.hline(0, 5, 0); c.vline(2, 0, 1); assert.equal(c.lines(false)[0].map((x) => x[0]).join(''), '──┬───'); assert.equal(c.lines(true)[0].map((x) => x[0]).join(''), '--+---');
});

test('a simulation that moves on keeps the terminal consistent: 600 s of play at every step, every screen, no throw', () => {
  const { sim, t } = mk(0);
  for (let i = 0; i < 60; i++) { sim.advance(10000); for (const k of ['1', '2', '3', 'a', 'r', '4']) { t.key(k); const f = t.frame({ cols: 100, rows: 40 }); assert.equal(f.lines.length, 40); } }
});
