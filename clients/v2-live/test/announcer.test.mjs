import test from 'node:test';
import assert from 'node:assert/strict';
import { createAnnouncer, classify, say, EVERY_MS } from '../js/announcer-model.js';
import { createSim } from '../sim.js';

const item = (key, cls, title) => ({ key, cls, title: title || key });
const speak = (a, now, lang) => { const d = a.due(now); return d && say(d.best, d.others, lang || 'en'); };

test('the limit is five seconds', () => assert.equal(EVERY_MS, 5000));

test('one change is spoken at once, the next waits until 5 s after it', () => {
  const a = createAnnouncer();
  a.note(item('m1', 'needs_you', 'Search')); assert.equal(speak(a, 0), 'Needs you: Search.');
  a.note(item('m2', 'done', 'Docs'));
  assert.equal(speak(a, 4999), null); assert.equal(a.wait(1000), 4000);
  assert.equal(speak(a, 5000), 'Done: Docs.');
});

test('a burst is spoken as its most important change, with the count of the rest', () => {
  const a = createAnnouncer();
  [item('a', 'running'), item('b', 'done'), item('c', 'failed'), item('d', 'needs_you', 'Search'), item('e', 'done')].forEach((i) => a.note(i));
  assert.equal(speak(a, 0), 'Needs you: Search. 4 more changes.');
  assert.equal(speak(a, 60000), null, 'what was folded in is not said again');
});

test('importance runs needs you, failed, done, running; the latest wins a tie', () => {
  const pick = (...cls) => { const a = createAnnouncer(); cls.forEach((c, i) => a.note(item('m' + i, c))); return a.due(0).best.cls; };
  assert.equal(pick('running', 'done', 'failed', 'needs_you'), 'needs_you');
  assert.equal(pick('needs_you', 'failed', 'done', 'running'), 'needs_you');
  assert.equal(pick('running', 'done', 'failed'), 'failed');
  assert.equal(pick('running', 'done'), 'done');
  const a = createAnnouncer(); a.note(item('x', 'failed', 'First')); a.note(item('y', 'failed', 'Second')); assert.equal(a.due(0).best.title, 'Second');
});

test('a thing that moved twice in the burst counts once, by its latest state', () => {
  const a = createAnnouncer();
  a.note(item('m', 'needs_you')); a.note(item('m', 'running', 'Search'));
  assert.equal(speak(a, 0), 'Running: Search.');
});

test('no change, no announcement', () => {
  const a = createAnnouncer();
  assert.equal(a.due(0), null); assert.equal(a.wait(0), null);
  a.note(item('m', 'done', 'Docs')); assert.ok(speak(a, 0));
  a.note(item('m', 'done', 'Docs')); assert.equal(speak(a, 10000), null, 'the same state again');
  a.note(item('m', 'failed', 'Docs')); a.note(item('m', 'done', 'Docs'));
  assert.equal(speak(a, 20000), null, 'it moved and came back inside the burst: the listener heard Done last');
  assert.equal(a.wait(20000), null);
});

test('the emergency stop is announced first and holds back running words until it is released', () => {
  const a = createAnnouncer();
  a.note(item('m1', 'running', 'Date test')); a.note(item('core', 'stopped'));
  assert.equal(speak(a, 0), 'Emergency stop engaged. New work is blocked.');
  a.note(item('m2', 'running', 'Docs')); assert.equal(a.wait(0), null, 'nothing runs while stopped');
  a.note(item('m3', 'failed', 'Build')); assert.equal(speak(a, 5000), 'Failed: Build.', 'real changes still get said');
  a.note(item('core', 'rearmed')); assert.equal(speak(a, 10000), 'Emergency stop released. New work can start.');
  a.note(item('m2', 'running', 'Docs')); assert.equal(speak(a, 15000), 'Running: Docs.');
});

test('a stop in the burst outranks a decision', () => {
  const a = createAnnouncer(); a.note(item('m', 'needs_you', 'Search')); a.note(item('core', 'stopped'));
  assert.match(speak(a, 0), /^Emergency stop engaged\./);
});

test('a restarted simulation forgets what was told', () => {
  const a = createAnnouncer(); a.note(item('m', 'done', 'Docs')); speak(a, 0);
  a.reset(); a.note(item('m', 'done', 'Docs')); assert.equal(speak(a, 5000), 'Done: Docs.');
});

test('Italian words', () => {
  const a = createAnnouncer(); a.note(item('m', 'failed', 'Docs')); a.note(item('n', 'done', 'x'));
  assert.equal(speak(a, 0, 'it'), 'Fallita: Docs. Un altro cambiamento.');
});

test('classify: only the four states, the stop and its release', () => {
  const t = (id) => 'Title of ' + id;
  const m = (to, from) => ({ type: 'mission.state_changed', subject: { kind: 'mission', id: 'm-1' }, payload: { from: from || 'PLANNING', to }, mission: 'm-1' });
  assert.deepEqual(classify(m('APPROVAL_REQUIRED'), t), { key: 'm-1', cls: 'needs_you', title: 'Title of m-1' });
  assert.equal(classify(m('FAILED'), t).cls, 'failed');
  assert.equal(classify(m('COMPLETED'), t).cls, 'done');
  assert.equal(classify(m('EXECUTING'), t).cls, 'running');
  assert.equal(classify(m('PLANNING'), t), null);
  assert.equal(classify(m('PAUSED'), t), null);
  assert.equal(classify(m('EXECUTING', 'EXECUTING'), t), null);
  assert.equal(classify({ type: 'approval.requested', subject: { kind: 'approval', id: 'a-1' }, payload: {}, mission: 'm-2' }, t).key, 'm-2');
  assert.equal(classify({ type: 'core.estop_engaged', subject: { kind: 'core', id: 'core' }, payload: {} }, t).cls, 'stopped');
  assert.equal(classify({ type: 'core.estop_rearmed', subject: { kind: 'core', id: 'core' }, payload: {} }, t).cls, 'rearmed');
  assert.equal(classify({ type: 'execution.progress', subject: { kind: 'execution', id: 'x' }, payload: {} }, t), null);
  const x = (to) => ({ type: 'execution.state_changed', subject: { kind: 'execution', id: 'x-1' }, payload: { from: 'RUNNING', to }, mission: 'm-1' });
  assert.equal(classify(x('ENDED_ERROR'), t).cls, 'failed');
  assert.equal(classify(x('ENDED_KILLED'), t), null);
});

test('over the real simulation: a decision, a failure and the stop come out as classified items', () => {
  const run = (go) => {
    const sim = createSim({ seed: 20261025 }); sim.pause(); sim.advance(60000);
    const got = []; sim.subscribe((ev) => { const i = classify(ev, (id) => (sim.state.missions[id] || {}).title); if (i) got.push(i); });
    go(sim); return got;
  };
  const asked = run((sim) => { assert.ok(sim.triggerApproval().ok); sim.act('estop'); });
  assert.ok(asked.some((i) => i.cls === 'needs_you' && i.title), JSON.stringify(asked));
  assert.ok(asked.some((i) => i.cls === 'stopped'));
  const failed = run((sim) => assert.ok(sim.injectFailure('execution').ok));
  assert.ok(failed.some((i) => i.cls === 'failed' && i.title), JSON.stringify(failed));
});
