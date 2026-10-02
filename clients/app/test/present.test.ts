// Status lines, explanations, resources and presence (§6.1, §6.3, §6.4, §6.12;
// M09, M10, M13).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ended, explainState, firedText, inline, mentions, presenceLabel, resourceLine, statusLine, technical, templateText, triggerText, usageText } from '../src/state/present.ts';
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

// ── R1 (rulebook §15, ADR-0029 §4): words in the default view, identifiers in Details ──

const JSONISH = /[{[]\s*"[^"]+"\s*:/;

test('a row splits into words and its identifiers, each labelled, none dropped (R1)', () => {
  const row = {
    id: 'pdc_01',
    stage: 'dispatch',
    decision: 'allow',
    policy_version: 'ab12cd34ef56',
    subject: { kind: 'task', id: 'tsk_01' },
    items: [{ task: 't1', class: 'read', approval_id: 'apr_01' }],
    related_ids: ['msn_01', 'msn_02'],
  };
  const [clean, tech] = technical(row);
  assert.deepEqual(clean, { stage: 'dispatch', decision: 'allow', subject: { kind: 'task' }, items: [{ task: 't1', class: 'read' }] });
  assert.deepEqual(tech, [
    ['Id', 'pdc_01'],
    ['Policy version', 'ab12cd34ef56'],
    ['Subject · id', 'tsk_01'],
    ['Items 1 · approval id', 'apr_01'],
    ['Related ids', 'msn_01, msn_02'],
  ]);
  // every identifier is somewhere, and the readable half carries none
  for (const v of ['pdc_01', 'ab12cd34ef56', 'tsk_01', 'apr_01', 'msn_02']) {
    assert.ok(tech.some(([, x]) => x.includes(v)), v);
    assert.ok(!inline(clean).includes(v), v);
  }
});

test("Core's own sentences name objects, never show their ids (R1)", () => {
  const apr = 'apr_01M3WNGS8FDY37GE2K1XRAJMAT';
  const acc = 'acc_01M3WNNW2D4GWJSFBYY12PK4KQ';
  assert.deepEqual(mentions(`plan v1 approved (approval ${apr})`), ['plan v1 approved (', { kind: 'approval', id: apr }, ')']);
  assert.deepEqual(mentions(`ranked below ${acc}`), ['ranked below ', { kind: 'account', id: acc }]);
  assert.deepEqual(mentions('nothing here; acc_short is not an id'), ['nothing here; acc_short is not an id']);
  assert.deepEqual(mentions(`${apr}`), [{ kind: 'approval', id: apr }]);
});

test('a value reads as words on one line, never as JSON (R1)', () => {
  assert.equal(inline({ type: 'tool', name: 'Bash', input: { command: 'ls' } }), 'Type tool · Name Bash · Input Command ls');
  assert.equal(inline([1, 'a']), '1, a');
  assert.equal(inline(null), '—');
  assert.ok(!JSONISH.test(inline({ a: { b: [{ c: 1 }] } })));
});

test('an automation says when it fires, what it asks for and why it fired, in words (R1)', () => {
  const t = triggerText({ type: 'mission.failed', where: { project: 'Atlas', path: { glob: 'src/*' }, kind: { not_glob: 'doc*' } } });
  assert.equal(t, 'When a mission.failed event happens, where project is Atlas and path matches src/* and kind does not match doc*');
  assert.equal(triggerText({ type: 'mission.completed', where: {} }), 'When a mission.completed event happens');
  assert.equal(templateText({ title: 'Fix it', objective: 'Tests pass', success_criteria: [{}] }), 'Start a mission “Fix it”: Tests pass (1 success criterion)');
  assert.equal(firedText({ type: 'mission.failed', where: { project: { test: 'Atlas', value: 'Atlas' } } }), 'It fired on a mission.failed event: project was Atlas.');
  for (const s of [t, firedText({ type: 'x', where: { a: { test: { glob: '*' }, value: { deep: 1 } } } })]) assert.ok(!JSONISH.test(s), s);
});

test('usage reads as windows and when it was seen; an unreported window is unknown, never 0 (R1)', () => {
  const now = Date.parse('2026-10-01T12:00:00Z');
  const u = usageText({ windows: { five_hour: 42, seven_day: null }, resets_at: { five_hour: '2026-10-01T14:00:00Z' }, observed_at: now / 1000 - 120, source: 'statusline' }, now);
  assert.equal(u, 'five hour 42% (resets in 2 h) · seven day unknown, observed 2 min ago from statusline');
  assert.equal(usageText(null), 'not observed');
  assert.ok(!JSONISH.test(u));
});

test('a state ends its machine exactly when no trigger leaves it (R10b: where priority is offered)', () => {
  assert.deepEqual(Object.keys(PRESENTATION.mission).filter((x) => ended('mission', x)).sort(), ['CANCELLED', 'COMPLETED']);
  assert.equal(ended('mission', 'EXECUTING'), false);
  assert.equal(ended('mission', 'PAUSED'), false);
  assert.equal(ended('mission', 'FAILED'), false); // a failed mission may still be replanned
});
