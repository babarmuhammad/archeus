// Control → About's emergency stop (P20 F7, F8; p20-design-gate D3, D4): the
// armed state in words and one status line from what Core answered.
// Mutation-verified by tools/mutate_p20.py (Q09 onward).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { armedText, estopSaid, stepUpBlocked } from '../src/state/present.ts';

test('the state is said, and unreachable is not guessed (F8)', () => {
  assert.equal(armedText(true), 'Armed: Archeus accepts new work.');
  assert.equal(armedText(false), 'Emergency stop engaged: Archeus refuses new work until you re-arm.');
  const unknown = armedText(undefined);
  assert.match(unknown, /^Core cannot be reached, so whether it is armed is not known here/);
  assert.doesNotMatch(unknown, /^Armed|engaged/);
});

test('an accepted stop says what Core stopped, in the tray’s words (F7)', () => {
  const s = estopSaid('estop', { ok: true, out: { stopped: ['exe_1', 'exe_2'], armed: false } });
  assert.deepEqual(s, { text: 'Emergency stop: 2 execution(s) stopped; Core is disarmed until re-armed.', alert: false, when: false });
});

test('a refusal says nothing was stopped, and why (F7)', () => {
  const s = estopSaid('estop', { ok: false, kind: 'refused', why: 'This client does not hold the “control” scope.' });
  assert.equal(s.text, 'Core refused the emergency stop, so nothing was stopped: This client does not hold the “control” scope.');
  assert.equal(s.alert, true);
  assert.equal(s.when, true);
});

test('a failure inside Core claims nothing stopped (F7)', () => {
  const s = estopSaid('estop', { ok: false, kind: 'failed', why: 'internal' });
  assert.equal(s.text, 'The emergency stop failed inside Core, so nothing is confirmed stopped: internal');
  assert.equal(s.alert, true);
});

test('no answer claims nothing and names the stop that works without Core (F7)', () => {
  const s = estopSaid('estop', { ok: false, kind: 'network', why: '' });
  assert.match(s.text, /^Core did not answer, so nothing is confirmed stopped\./);
  assert.match(s.text, /tray’s Emergency stop and “archeus estop” stop without Core/);
  assert.equal(s.alert, true);
  assert.equal(s.when, undefined);
});

test('a re-arm is said only from Core’s answer (F8)', () => {
  assert.deepEqual(estopSaid('rearm', { ok: true, out: { armed: true } }),
    { text: 'Re-armed: Core accepts new work again.', alert: false, when: true });
  const still = estopSaid('rearm', { ok: true, out: { armed: false } });
  assert.equal(still.alert, true);
  assert.equal(still.when, false);
  const refused = estopSaid('rearm', { ok: false, kind: 'refused', why: 'no' });
  assert.equal(refused.text, 'Core refused the re-arm, so it stays disarmed: no');
  assert.equal(refused.when, false);
  assert.equal(estopSaid('rearm', { ok: false, kind: 'network', why: '' }).text,
    'Core did not answer, so the re-arm is not confirmed.');
});

test('a step-up is sent only when it can be answered (T-098)', () => {
  assert.equal(stepUpBlocked('local', ''), null);
  assert.equal(stepUpBlocked(undefined, ''), null);
  assert.equal(stepUpBlocked('none', '482913'), 'This client has no PIN: it cannot satisfy a step-up.');
  assert.equal(stepUpBlocked('pin', ''), 'Enter this client’s PIN first.');
  assert.equal(stepUpBlocked('pin', '48291'), 'Enter this client’s PIN first.');
  assert.equal(stepUpBlocked('pin', '482913'), null);
});
