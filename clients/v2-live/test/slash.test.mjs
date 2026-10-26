import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as simModule from '../sim.js';
import { createSim } from '../sim.js';
import { createChat } from '../chat-engine.js';
import { createTui } from '../js/tui/controller.js';
import { COMMANDS, find } from '../slash.js';

const argsOf = (c) => (c.choices ? c.choices[0] : c.arg === 'none' ? '' : 'date');
const line = (c, name) => '/' + name + (argsOf(c) ? ' ' + argsOf(c) : '');

test('there is one slash table: sim.js, the chat and the terminal all read slash.js', () => {
  assert.equal(simModule.COMMANDS, undefined);
  assert.equal(COMMANDS.length, 34);
  const src = (f) => readFileSync(new URL(f, import.meta.url), 'utf8');
  assert.ok(!/findCommand|SECRET\s*=|name: 'help'/.test(src('../sim.js')), 'sim.js keeps no table, parser or secret rule of its own');
  assert.ok(!/from '\.\/cmd\.js'|findCommand/.test(src('../js/tui/controller.js')), 'the terminal has no grammar of its own');
  assert.ok(/from '\.\.\/\.\.\/slash\.js'/.test(src('../js/tui/controller.js')) && /from '\.\/slash\.js'/.test(src('../chat-engine.js')));
});

test('every command, by English name and Italian alias, is accepted or refused the same way by sim.say, the chat engine and the terminal', () => {
  for (const c of COMMANDS) for (const name of [c.name, c.alias]) {
    assert.equal(find(name).name, c.name);
    const want = !c.unavailable;
    assert.equal(createSim().say(line(c, name)).ok, want, 'sim.say ' + name);
    const eng = createChat(createSim());
    assert.equal(eng.send(line(c, name), { force: true }).ok, want, 'chat ' + name);
    const sim = createSim(), t = createTui(sim); t.openCmd('');
    t.cmdSet(line(c, name)); t.cmdSubmit();
    assert.equal(!(t.state.mode && t.state.mode.kind === 'cmd'), want, 'terminal ' + name);
  }
});

test('the secret, unknown and no-argument rules are the same on every surface', () => {
  const bad = ['/nope', '/status extra', '/sk-abcdef1234', 'here is sk-abcdefghij', '/mission x sk-abcdefghij', '   '];
  for (const text of bad) {
    assert.equal(createSim().say(text).ok, false, 'sim.say ' + text);
    assert.equal(createChat(createSim()).send(text, { force: true }).ok, false, 'chat ' + text);
    const t = createTui(createSim()); t.openCmd(''); t.cmdSet(text); t.cmdSubmit();
    assert.ok(text.trim() ? t.state.mode.kind === 'cmd' : t.state.mode === null, 'terminal ' + text);
  }
});
