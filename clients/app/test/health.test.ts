// Health and Attention labels (P21 D2, D12): a reason that changes what an item is
// is named as such, and a figure Core could not measure reads "unknown", never 0.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { attentionLabel, known, pct, spanText } from '../src/state/present.ts';

test('an attention item is named by its reason when the reason changes what it is', () => {
  assert.equal(attentionLabel({ kind: 'account', reason_code: 'limited' }), 'Account at its usage limit');
  assert.equal(attentionLabel({ kind: 'account', reason_code: 'degraded' }), 'Account failing');
  assert.equal(attentionLabel({ kind: 'account', reason_code: 'open' }), 'Account stopped after repeated errors');
  assert.equal(attentionLabel({ kind: 'mission', reason_code: 'no_resource' }), 'No resource can run this mission');
  assert.equal(attentionLabel({ kind: 'account', reason_code: 'reauth' }), 'Account needs signing in');
  assert.equal(attentionLabel({ kind: 'mission', reason_code: 'planning_blocked' }), 'Planning asks you');
  assert.equal(attentionLabel({ kind: 'unheard_of', reason_code: 'x' }), 'unheard_of');
});

test('a figure Core could not measure is unknown, and a measured zero stays 0', () => {
  assert.equal(known(null, pct), 'unknown');
  assert.equal(known(0, pct), '0%');
  assert.equal(known(0.256, pct), '26%');
  assert.equal(known(0, String), '0');
});

test('a duration reads in minutes under an hour and in hours after', () => {
  assert.equal(spanText(30), '1 min');
  assert.equal(spanText(90), '2 min');
  assert.equal(spanText(7200), '2.0 h');
});
