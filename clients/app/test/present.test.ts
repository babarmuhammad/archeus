// Status lines, explanations, resources and presence (§6.1, §6.3, §6.4, §6.12;
// M09, M10, M13).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { explainState, presenceLabel, resourceLine, statusLine } from '../src/state/present.ts';
import { PRESENTATION } from '../src/state/presentation.ts';

test('harness, model and account stay three fields; nothing is merged or borrowed (M13)', () => {
  const f = resourceLine({ harness_id: 'claude_code', model: 'claude-opus-5-5', account_id: 'acc_1', effort: 'high' });
  assert.deepEqual(f.map((x) => [x.key, x.value]), [
    ['harness', 'claude_code'],
    ['model', 'claude-opus-5-5'],
    ['account', 'acc_1'],
    ['effort', 'high'],
  ]);
  const missing = resourceLine({ harness_id: 'pi' });
  assert.deepEqual(missing.map((x) => x.value), ['pi', '—', '—']);
  for (const x of f) assert.ok(!x.value.includes('/') || x.key === 'model');
});

test('presence is transport, labelled as such; recent is not connected (M09)', () => {
  assert.equal(presenceLabel({ state: 'connected', connections: 2 }), 'connected (2 streams)');
  assert.equal(presenceLabel({ state: 'recent', connections: 0 }), 'seen in the last minute');
  assert.equal(presenceLabel({ state: 'absent', connections: 0 }), 'not connected');
  assert.notEqual(presenceLabel({ state: 'recent', connections: 0 }), presenceLabel({ state: 'connected', connections: 0 }));
});

test('a session has its own machine: it never borrows a mission state (M10)', () => {
  assert.deepEqual(Object.keys(PRESENTATION.session).sort(), ['CLOSED', 'LOST', 'OPEN']);
  for (const s of Object.keys(PRESENTATION.session)) assert.ok(!(s in PRESENTATION.mission), s);
});

test('the status line is derived from rows only', () => {
  assert.equal(statusLine({ state: 'APPROVAL_REQUIRED', pending_approval: { kind: 'plan' }, plan_version: 2 }), 'Waiting: approve plan v2');
  assert.equal(statusLine({ state: 'PLANNING', planning_blocked: { kind: 'clarification', questions: ['Which chart library?'] } }), 'Waiting: Which chart library?');
  assert.equal(statusLine({ state: 'REPLANNING', planning_blocked: { kind: 'policy' } }), 'Blocked: the policy denies this plan');
  assert.equal(
    statusLine({ state: 'EXECUTING', tasks: [{ key: 't1', title: 'Data layer', state: 'SUCCEEDED' }, { key: 't2', title: 'Charts', state: 'RUNNING' }] }),
    'Charts · 1 of 2 tasks done',
  );
  assert.equal(statusLine({ state: 'COMPLETED' }), '');
});

test('why a mission is where it is comes from rows, most specific first; no guess', () => {
  assert.deepEqual(explainState({ mission: { state: 'EXECUTING' } }), [{ text: 'No recorded reason.', source: 'none' }]);
  const w = explainState({
    mission: { state: 'BLOCKED' },
    approval: { kind: 'task', state: 'PENDING', expires_at: '2999-01-01', eligible: false, eligible_why: 'the plan changed' },
    route: { result: 'blocked', explanation: 'all accounts at ceiling', unblock_at: '16:05' },
  });
  assert.deepEqual(w.map((x) => x.source), ['approval', 'approval.eligible_why', 'route_decision']);
  assert.match(w[2].text, /16:05/);
  assert.equal(explainState({ mission: { state: 'COMPLETED' }, route: { result: 'blocked' } }).length, 1);
  const v = explainState({ mission: { state: 'VERIFYING' }, verification: { state: 'FAILED', checks: [{ name: 'pytest', result: 'fail' }] } });
  assert.match(v[0].text, /pytest/);
});
