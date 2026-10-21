// Health and Attention labels (P21 D2, D12): a reason that changes what an item is
// is named as such, and a figure Core could not measure reads "unknown", never 0.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { attentionLabel, known, pct, resetText, spanText } from '../src/state/present.ts';

const control = readFileSync(new URL('../src/surfaces/Control.tsx', import.meta.url), 'utf8');

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

test('the Health empty state claims only what Attention knows, never that every account works', () => {
  // DISABLED and UNVERIFIED accounts raise no item, and zero accounts is vacuous
  assert.ok(control.includes('No account has stopped or needs you, and no mission waits for a resource.'));
  assert.ok(!/every account/i.test(control));
  assert.ok(!control.includes('can work'));
});

test('every nullable Health figure is rendered through known(), so null shows unknown', () => {
  for (const field of ['median_time_to_complete_s', 'approvals_per_mission', 'fallback_rate', 'verification_failure_rate'])
    assert.ok(control.includes(`known(d.${field}, `), field);
});

test('a limited account whose reset instant has passed says reset due, not resets ago', () => {
  const now = Date.parse('2026-10-21T10:00:00Z');
  assert.equal(resetText('2026-10-21T10:05:00Z', now), 'resets in 5 min');
  assert.equal(resetText('2026-10-21T09:55:00Z', now), 'reset due');
});
