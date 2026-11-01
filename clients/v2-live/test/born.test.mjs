import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.location = { search: '?lang=it' };
const { createSim } = await import('../sim.js');
const { createBornLog } = await import('../js/born-model.js');
const { tr } = await import('../js/i18n.js');
const { BORN_MS } = await import('../js/constellation/born.js');

const watch = (sim, log) => sim.subscribe((e) => log.note(e));

test('what the chat creates is logged with its project, and nothing else is', () => {
  const sim = createSim(), log = createBornLog(() => 0);
  watch(sim, log);
  sim.advance(30 * 60 * 1000);
  assert.deepEqual(log.live(), [], 'the simulation’s own creations are never tagged');
  sim.say('Create a project called Zephyr');
  sim.say('/mission Write the docs @archeus');
  sim.say('/idea A far thought');
  const born = log.live();
  assert.deepEqual(born.map((b) => b.kind), ['project', 'mission', 'idea']);
  assert.equal(born[0].project, born[0].id);
  assert.equal(born[1].project, 'archeus');
  assert.ok(sim.state.projects.some((p) => p.id === born[0].id) && sim.state.missions[born[1].id] && sim.state.ideas.some((i) => i.id === born[2].id));
});

test('a general answer or a read command logs nothing', () => {
  const sim = createSim(), log = createBornLog(() => 0);
  watch(sim, log);
  sim.say('What is a mission?');
  sim.say('/status');
  assert.deepEqual(log.live(), []);
});

test('an entry leaves the log after the tag time, by the wall clock', () => {
  let t = 1000;
  const sim = createSim(), log = createBornLog(() => t);
  watch(sim, log);
  sim.say('Create a project called Zephyr');
  t += BORN_MS - 1;
  assert.equal(log.live().length, 1);
  t += 1;
  assert.deepEqual(log.live(), []);
});

test('the New tag has an Italian word', () => {
  assert.equal(tr('New'), 'Nuovo');
});
