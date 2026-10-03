// The Ideas stepper (rulebook §43; D-11): Core's own path and side exits, the
// idea's place on it, and nothing claimed about steps it may have skipped.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { IDEA_ASIDE, IDEA_PATH, ideaSteps } from '../src/state/ideas.ts';
import { PRESENTATION } from '../src/state/presentation.ts';

test('the path and the side exits are exactly Core\'s idea states', () => {
  assert.deepEqual([...IDEA_PATH, ...IDEA_ASIDE].sort(), Object.keys(PRESENTATION.idea).sort());
  assert.equal(IDEA_PATH[0], 'CAPTURED');
  assert.equal(IDEA_PATH[IDEA_PATH.length - 1], 'LEARNED');
});

test('the current step is now, those before it only earlier, those after later', () => {
  const { path, aside } = ideaSteps('PLANNED');
  assert.equal(aside, null);
  assert.deepEqual(path.filter((s) => s.at === 'now').map((s) => s.state), ['PLANNED']);
  assert.deepEqual(path.filter((s) => s.at === 'earlier').map((s) => s.state), ['CAPTURED', 'UNDERSTOOD', 'EXPLORED', 'VALIDATED', 'CONCEPT']);
  assert.equal(path.find((s) => s.state === 'IMPLEMENTING')?.label, 'Implementing');
});

test('a set-aside idea has no place on the path and says which exit it took', () => {
  for (const s of IDEA_ASIDE) {
    const { path, aside } = ideaSteps(s);
    assert.ok(path.every((x) => x.at === 'later'), s);
    assert.equal(aside, s === 'PARKED' ? 'Parked' : 'Discarded');
  }
});
