// The presentation table and its lookups (p16-design-gate §6, §24 M01–M05, M16).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CLASSES, LABELS, PRESENTATION, TRIGGERS } from '../src/state/presentation.ts';
import { badge, isDone, offers, present } from '../src/state/present.ts';

test('every state of every machine has a class with a glyph, a role and a label', () => {
  for (const [machine, table] of Object.entries(PRESENTATION)) {
    for (const [state, cls] of Object.entries(table)) {
      const c = CLASSES[cls];
      assert.ok(c, `${machine}.${state} names unknown class ${cls}`);
      assert.ok(c.glyph && c.role && c.name, `${cls} is incomplete`);
      assert.ok(LABELS[machine][state], `${machine}.${state} has no label`);
    }
  }
});

test('a badge always carries a text label, never a glyph alone (M16)', () => {
  for (const [machine, table] of Object.entries(PRESENTATION))
    for (const state of Object.keys(table)) {
      const b = badge(machine, state);
      assert.ok(b.label.trim().length > 0, `${machine}.${state}`);
      assert.notEqual(b.label, b.glyph);
    }
});

test('proposed, approved, executing, verifying, reviewing and done are six different looks (M01–M04)', () => {
  const look = (s: string) => present('mission', s);
  assert.equal(look('APPROVAL_REQUIRED').cls, 'needs_you');
  assert.equal(look('APPROVED').cls, 'approved');
  assert.equal(look('EXECUTING').cls, 'active');
  assert.equal(look('VERIFYING').cls, 'verifying');
  assert.equal(look('REVIEWING').cls, 'reviewing');
  assert.equal(look('COMPLETED').cls, 'done');
  const labels = ['APPROVAL_REQUIRED', 'APPROVED', 'EXECUTING', 'VERIFYING', 'REVIEWING', 'COMPLETED'].map((s) => look(s).label);
  assert.equal(new Set(labels).size, labels.length);
  const glyphs = ['APPROVAL_REQUIRED', 'APPROVED', 'EXECUTING', 'COMPLETED'].map((s) => look(s).glyph);
  assert.equal(new Set(glyphs).size, glyphs.length);
  // a plan that is proposed is not approved
  assert.notEqual(present('plan', 'PROPOSED').cls, present('plan', 'APPROVED').cls);
  assert.match(present('plan', 'PROPOSED').label, /not approved/);
});

test('only a COMPLETED mission is done: verified is not accepted', () => {
  const done = Object.keys(PRESENTATION.mission).filter((s) => isDone('mission', s));
  assert.deepEqual(done, ['COMPLETED']);
  assert.match(present('mission', 'REVIEWING').label, /not accepted/);
});

test('an execution that exited ok is not a success: verification decides (M05)', () => {
  assert.notEqual(present('execution', 'ENDED_OK').cls, 'done');
  assert.match(present('execution', 'ENDED_OK').label, /not verified/);
  for (const s of Object.keys(PRESENTATION.execution)) assert.notEqual(present('execution', s).cls, 'done', s);
  assert.notEqual(present('verification', 'ERROR').cls, 'failed'); // a broken verifier is not failed work
});

test('an unknown state is shown as itself, never guessed into a class', () => {
  const l = present('mission', 'TELEPORTED');
  assert.equal(l.cls, 'neutral');
  assert.equal(l.label, 'TELEPORTED');
});

test('a button is offered only where the state table has the trigger', () => {
  assert.ok(offers('mission', 'EXECUTING', 'pause'));
  assert.ok(!offers('mission', 'PLANNING', 'pause'));
  assert.ok(offers('mission', 'PAUSED', 'resume'));
  assert.ok(offers('mission', 'BLOCKED', 'resume', 'unblock'));
  assert.ok(!offers('mission', 'COMPLETED', 'resume', 'unblock', 'pause'));
  assert.deepEqual(TRIGGERS.mission.COMPLETED, undefined);
});
