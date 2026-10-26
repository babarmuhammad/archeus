import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createChat } from '../chat-engine.js';
import { createSim, EDGES, TIME_SCALE, SPEEDS, clockLabel, categoryOf, REPLAY_CATEGORIES } from '../sim.js';

const run = (sim, secs) => sim.advance(secs * 1000);
const edge = (machine, from, to) => EDGES[machine].some((e) => e[0] === from && e[1] === to);

test('every state change in the log follows a declared edge, from the backfilled history on', () => {
  const s = createSim();
  run(s, 1800);
  const changes = s.state.events.filter((e) => e.type.endsWith('.state_changed') && EDGES[e.subject.kind]);
  assert.ok(changes.length > 60);
  for (const e of changes) assert.ok(edge(e.subject.kind, e.payload.from, e.payload.to), e.type + ' ' + e.payload.from + ' -> ' + e.payload.to);
});

test('fixtures: 3 projects and eight missions in the real mission state words', () => {
  const s = createSim();
  assert.equal(s.state.projects.length, 3);
  const states = Object.fromEntries(Object.values(s.state.missions).map((m) => [m.id, m.state]));
  assert.deepEqual(states, { 'm-docs': 'COMPLETED', 'm-date': 'EXECUTING', 'm-search': 'APPROVAL_REQUIRED', 'm-lint': 'FAILED', 'm-offline': 'VERIFYING', 'm-export': 'BLOCKED', 'm-voice': 'PAUSED', 'm-theme': 'CREATED' });
  assert.equal(s.state.missions['m-export'].held_from, 'UNDERSTANDING');
  assert.equal(s.state.missions['m-voice'].held_from, 'EXECUTING');
  assert.equal(s.state.missions['m-date'].held_from, null);
});

test('deterministic: same seed, same log; the advance chunking does not matter', () => {
  const a = createSim({ seed: 7 }), b = createSim({ seed: 7 }), c = createSim({ seed: 8 });
  run(a, 1200); for (let i = 0; i < 1200; i++) run(b, 1); run(c, 1200);
  assert.equal(a.hash(), b.hash());
  assert.notEqual(a.hash(), c.hash());
  const a2 = createSim({ seed: 7 }); run(a2, 1200);
  assert.equal(a.hash(), a2.hash());
});

test('the script: stuck then recovers, verification fails once, a plan needs approval, a review arrives', () => {
  const s = createSim();
  run(s, 195); assert.equal(s.state.executions['x-date-1'].state, 'RUNNING');
  run(s, 20); assert.equal(s.state.executions['x-date-1'].stuck, true);
  run(s, 140); assert.equal(s.state.executions['x-date-1'].state, 'LOST');
  assert.match(s.reading(s.state.executions['x-date-1']), /Lost/);
  run(s, 70); assert.equal(s.state.executions['x-date-1'].state, 'RUNNING');
  assert.equal(s.state.executions['x-date-1'].stuck, false);
  run(s, 600);
  const v = Object.values(s.state.verifications).find((x) => x.mission === 'm-date');
  assert.equal(v.state, 'FAILED');
  assert.equal(s.state.missions['m-date'].state, 'APPROVAL_REQUIRED');
  assert.ok(s.attention().some((a) => a.group === 'Decide' && a.mission_id === 'm-date'));
  const off = s.state.missions['m-offline'];
  assert.equal(off.state, 'REVIEWING');
  assert.ok(s.attention().some((a) => a.group === 'Review' && a.mission_id === 'm-offline'));
});

test('m-theme runs the auto-approved path to EXECUTING', () => {
  const s = createSim();
  run(s, 300);
  assert.equal(s.state.missions['m-theme'].state, 'EXECUTING');
  assert.equal(Object.values(s.state.plans).filter((p) => p.mission === 'm-theme')[0].state, 'APPROVED');
});

test('approve the waiting plan: it executes, verifies and reaches review', () => {
  const s = createSim();
  const r = s.act('approve', 'a-1'); assert.equal(r.ok, true);
  assert.equal(s.state.missions['m-search'].state, 'APPROVED');
  run(s, 20); assert.equal(s.state.missions['m-search'].state, 'EXECUTING');
  run(s, 900);
  assert.equal(s.state.missions['m-search'].state, 'REVIEWING');
  assert.equal(s.act('approve', 'a-1').ok, false);
  assert.equal(s.act('accept', 'm-search').ok, true);
  assert.equal(s.state.missions['m-search'].state, 'COMPLETED');
  assert.ok(s.state.events.some((e) => e.actor === 'device'));
});

test('reject the waiting plan cancels the mission', () => {
  const s = createSim();
  assert.equal(s.act('reject', 'a-1').ok, true);
  assert.equal(s.state.missions['m-search'].state, 'CANCELLED');
});

test('unblock, resume and replan follow real edges and refuse the wrong state', () => {
  const s = createSim();
  assert.equal(s.act('resume', 'm-export').ok, false);
  assert.equal(s.act('unblock', 'm-export').ok, true);
  assert.equal(s.state.missions['m-export'].state, 'RESUMED');
  assert.equal(s.state.missions['m-export'].held_from, 'UNDERSTANDING');
  run(s, 20); assert.equal(s.state.missions['m-export'].state, 'UNDERSTANDING');
  assert.equal(s.state.missions['m-export'].held_from, null);
  assert.equal(s.act('resume', 'm-voice').ok, true);
  run(s, 20); assert.equal(s.state.missions['m-voice'].state, 'EXECUTING');
  assert.equal(s.act('replan', 'm-lint').ok, true);
  assert.equal(s.state.missions['m-lint'].state, 'REPLANNING');
  run(s, 40); assert.equal(s.state.missions['m-lint'].state, 'APPROVAL_REQUIRED');
});

test('trigger an approval: a hook asks, the owner decides, nothing happens without the decision', () => {
  const s = createSim();
  const r = s.triggerApproval(); assert.equal(r.ok, true);
  const x = s.state.executions[r.execution];
  assert.equal(x.state, 'AWAITING_APPROVAL');
  const a = Object.values(s.state.approvals).find((p) => p.ref === x.id);
  assert.equal(a.state, 'PENDING');
  run(s, 600); assert.equal(x.state, 'AWAITING_APPROVAL');
  assert.equal(s.act('approve', a.id).ok, true);
  run(s, 10); assert.equal(x.state, 'RUNNING');
  const r2 = s.triggerApproval();
  const a2 = Object.values(s.state.approvals).find((p) => p.ref === r2.execution && p.state === 'PENDING');
  assert.equal(s.act('reject', a2.id).ok, true);
  assert.equal(s.state.executions[r2.execution].state, 'ENDED_REJECTED');
  assert.equal(s.state.missions[s.state.executions[r2.execution].mission].state, 'BLOCKED');
  assert.equal(s.state.missions[s.state.executions[r2.execution].mission].held_from, 'EXECUTING');
});

test('inject a failure: an execution ends in error and the mission replans, then fails for good', () => {
  const s = createSim();
  const r = s.injectFailure('execution'); assert.equal(r.ok, true);
  assert.equal(s.state.missions[r.mission].state, 'REPLANNING');
  const s2 = createSim();
  Object.values(s2.state.missions).forEach((m) => { m.replans = 2; });
  const r2 = s2.injectFailure('execution');
  assert.equal(s2.state.missions[r2.mission].state, 'FAILED');
  assert.match(s2.state.missions[r2.mission].reason, /Unrecoverable/);
});

test('fuzz: random decisions and failures for hours of simulated time never break an edge or throw', () => {
  for (const seed of [1, 2, 3, 4, 5]) {
    const s = createSim({ seed, strict: true });
    let x = seed * 7919;
    const rnd = () => { x = (x * 1103515245 + 12345) & 0x7fffffff; return x / 0x7fffffff; };
    const kinds = ['approve', 'reject', 'accept', 'changes', 'unblock', 'resume', 'replan', 'cancel', 'pause'];
    for (let i = 0; i < 400; i++) {
      const roll = rnd();
      if (roll < 0.15) s.triggerApproval(); else if (roll < 0.25) s.injectFailure(['execution', 'verification', 'spawn'][Math.floor(rnd() * 3)]);
      else if (roll < 0.7) {
        const k = kinds[Math.floor(rnd() * kinds.length)];
        const ids = k === 'approve' || k === 'reject' ? Object.keys(s.state.approvals) : Object.keys(s.state.missions);
        s.act(k, ids[Math.floor(rnd() * ids.length)]);
      }
      s.advance(Math.floor(rnd() * 90000));
    }
    for (const e of s.state.events.filter((q) => q.type.endsWith('.state_changed') && EDGES[q.subject.kind])) assert.ok(edge(e.subject.kind, e.payload.from, e.payload.to));
  }
});

test('inject a spawn failure trips the harness breaker, dispatch waits, then it closes', () => {
  const s = createSim();
  assert.equal(s.injectFailure('spawn').ok, true);
  const b = () => s.state.harnesses.find((h) => h.id === 'claude_code').breaker;
  assert.equal(b().state, 'open');
  assert.equal(s.act('approve', 'a-1').ok, true);
  run(s, 120);
  assert.equal(s.state.missions['m-search'].state, 'APPROVED');
  assert.match(s.state.missions['m-search'].reason, /breaker/);
  run(s, 190); assert.equal(b().state, 'half_open');
  run(s, 40); assert.equal(b().state, 'closed');
  run(s, 40); assert.equal(s.state.missions['m-search'].state, 'EXECUTING');
});

test('inject with nothing to fail says so', () => {
  const s = createSim();
  s.state.executions['x-date-1'].state = 'ENDED_OK';
  assert.equal(s.injectFailure('execution').ok, false);
  assert.equal(s.injectFailure('verification').ok, true);
});

test('play, pause, speed and reset', () => {
  const s = createSim();
  s.tickReal(1000); assert.equal(s.state.clock, 0);
  s.play(); s.tickReal(1000); assert.equal(s.state.clock, 1000 * TIME_SCALE);
  s.setSpeed(4); s.tickReal(1000); assert.equal(s.state.clock, 1000 * TIME_SCALE * 5);
  assert.equal(s.setSpeed(3), false);
  assert.ok(SPEEDS.includes(s.state.speed));
  s.pause(); s.tickReal(5000); assert.equal(s.state.clock, 1000 * TIME_SCALE * 5);
  s.act('approve', 'a-1'); const h = s.hash();
  s.reset(); assert.equal(s.state.clock, 0); assert.equal(s.state.missions['m-search'].state, 'APPROVAL_REQUIRED'); assert.notEqual(s.hash(), h);
  assert.equal(s.state.speed, 4);
});

test('subscribers get every event, and can unsubscribe', () => {
  const s = createSim(); const seen = [];
  const off = s.subscribe((e) => seen.push(e.type));
  s.act('approve', 'a-1'); assert.ok(seen.includes('approval.state_changed') && seen.includes('mission.state_changed'));
  off(); const n = seen.length; s.act('accept', 'm-offline'); assert.equal(seen.length, n);
});

test('usage is unknown (null), never 0, and an account near its ceiling is told apart', () => {
  const s = createSim();
  assert.equal(s.state.usage['acc-codex'].window5h, null);
  assert.equal(s.state.accounts.find((a) => a.id === 'acc-personal').state, 'CONSTRAINED');
  run(s, 1800);
  assert.equal(s.state.usage['acc-codex'].window5h, null);
  assert.ok(Object.values(s.state.usage).every((u) => u.window5h === null || u.window5h > 0));
});

test('attention groups are Decide, Review, Unblock in that order, and the sentence uses the counts', () => {
  const s = createSim();
  const groups = s.attention().map((a) => a.group);
  const order = ['Decide', 'Review', 'Unblock'];
  assert.deepEqual(groups, [...groups].sort((a, b) => order.indexOf(a) - order.indexOf(b)));
  assert.match(s.sentence(), /need you/);
  assert.match(s.sentence(), /running/);
});

test('replay: categories come from the vocabulary, an unclassified state is UNKNOWN, LOST is UNCERTAIN, adopted is RECONCILED', () => {
  const s = createSim(); run(s, 420);
  const r = s.replay('m-date');
  assert.ok(r.rows.length > 8);
  for (const row of r.rows) assert.ok(REPLAY_CATEGORIES.includes(row.category), row.category);
  assert.ok(r.rows.some((x) => x.category === 'UNCERTAIN' && /execution LOST/.test(x.title)));
  assert.ok(r.rows.some((x) => x.category === 'RECONCILED'));
  assert.equal(categoryOf('execution', 'ENDED_REJECTED'), 'UNKNOWN');
  assert.equal(categoryOf('mission', 'NO_SUCH'), 'UNKNOWN');
  assert.match(r.gaps, /NOT RECORDED/);
});

test('say records the message and a scripted reply from the shared chat engine', () => {
  const s = createSim(); const n = s.state.messages.length;
  const r = s.say('what needs me today');
  assert.equal(r.ok, true);
  assert.equal(s.state.messages.length, n + 2);
  assert.equal(r.reply.card.kind, 'status');
  assert.equal(s.say('   ').ok, false);
});

test('the event log is bounded and says when it pruned', () => {
  const s = createSim({ maxEvents: 80 }); run(s, 60 * 60);
  assert.ok(s.state.events.length <= 80);
  assert.equal(s.state.pruned, true);
});

test('clock label starts at 09:00', () => { assert.equal(clockLabel(0), '09:00'); assert.equal(clockLabel(90 * 60000), '10:30'); assert.equal(clockLabel(-30 * 60000), '08:30'); });

test('knowledge candidates and automations that wait for you can be decided', () => {
  const s = createSim();
  assert.equal(s.act('confirm', 'k-4').ok, true);
  assert.equal(s.state.knowledge.find((k) => k.id === 'k-4').state, 'CONFIRMED');
  assert.equal(s.act('confirm', 'k-4').ok, false);
  assert.equal(s.act('retract', 'k-6').ok, true);
  assert.equal(s.act('enable', 'au-3').ok, true);
  assert.equal(s.state.automations.find((a) => a.id === 'au-3').state, 'ENABLED');
  assert.equal(s.act('enable', 'au-1').ok, false);
  assert.equal(s.act('enable', 'au-2').ok, true);
});

test('say runs the one slash table: READ answers, CREATE writes, PROPOSE only proposes until the card is confirmed', () => {
  const s = createSim(), eng = createChat(s);
  assert.equal(s.say('/nope').ok, false);
  assert.equal(s.say('/status extra').ok, false);
  assert.equal(s.say('/usage').reply.card.kind, 'usage');
  assert.equal(s.say('/stato').reply.card.kind, 'status');
  assert.equal(s.say('/sk-abcdef1234').ok, false);
  assert.equal(s.say('here is sk-abcdefghij').ok, false);
  const n = Object.keys(s.state.missions).length;
  const made = s.say('/missione add dark mode');
  assert.equal(Object.keys(s.state.missions).length, n + 1);
  const m = s.state.missions['m-n1']; assert.equal(m.state, 'CREATED');
  s.advance(200000); assert.equal(m.state, 'CREATED');
  assert.equal(made.reply.card.kind, 'start');
  assert.equal(eng.card(made.reply.id, 'start').ok, true);
  s.advance(200000); assert.equal(m.state, 'APPROVAL_REQUIRED');
  assert.equal(s.say('/idea try a calm mode').ok, true); assert.ok(s.state.ideas.some((i) => i.title === 'try a calm mode'));
  const prop = s.say('/pausa fix date');
  assert.equal(prop.reply.card.kind, 'confirm');
  assert.equal(s.state.missions['m-date'].state, 'EXECUTING');
  assert.equal(eng.card(prop.reply.id, 'yes').ok, true);
  s.advance(10000); assert.equal(s.state.missions['m-date'].state, 'PAUSED');
  s.say('/approve search');
  assert.equal(s.state.approvals['a-1'].state, 'PENDING');
  assert.equal(s.say('//status').ok, true);
});

test('security and health lists: unknown stays unknown, a tripped breaker shows', () => {
  const s = createSim();
  assert.ok(s.security().some((x) => x.id === 'iso' && x.state === 'open'));
  assert.equal(s.security().find((x) => x.id === 'breaker').state, 'ok');
  s.injectFailure('spawn');
  assert.equal(s.security().find((x) => x.id === 'breaker').state, 'attention');
  const h = s.health();
  assert.equal(h.find((x) => x.id === 'disk').state, 'unknown');
  assert.equal(h.find((x) => x.id === 'h-pi').state, 'unknown');
  assert.equal(h.find((x) => x.id === 'h-claude_code').state, 'attention');
  assert.deepEqual(s.counts().need >= 1, true);
});

test('H16: pause all, resume all and emergency stop are one action each', () => {
  const s = createSim();
  s.advance(60000);
  assert.equal(s.act('pause_all').ok, true); s.advance(10000);
  assert.equal(Object.values(s.state.missions).filter((m) => m.state === 'EXECUTING').length, 0);
  assert.equal(s.act('pause_all').ok, false);
  assert.equal(s.act('resume_all').ok, true); s.advance(20000);
  assert.ok(Object.values(s.state.missions).some((m) => m.state === 'EXECUTING'));
  assert.equal(s.act('resume_all').ok, false);
  assert.equal(s.act('estop').ok, true);
  assert.equal(Object.values(s.state.missions).filter((m) => m.state === 'EXECUTING').length, 0);
  assert.equal(s.state.missions['m-date'].reason, 'Emergency stop');
  assert.equal(s.act('estop').ok, false);
});

test('after an emergency stop nothing new dispatches or resumes until it is re-armed (a step-up in the apps)', () => {
  const s = createSim(); s.advance(60000);
  assert.equal(s.state.estop.engaged, false); assert.equal(s.act('rearm').ok, false);
  assert.equal(s.act('estop').ok, true);
  assert.equal(s.state.estop.engaged, true);
  assert.equal(s.security().find((x) => x.id === 'estop').state, 'attention');
  const m = s.state.missions['m-date']; assert.equal(m.state, 'BLOCKED'); assert.equal(m.reason, 'Emergency stop');
  for (const k of ['unblock', 'resume_all']) assert.equal(s.act(k, 'm-date').ok, false, k);
  assert.match(s.act('unblock', 'm-date').reason, /re-arm/);
  // a plan approved now waits instead of dispatching
  const a = Object.values(s.state.approvals).find((x) => x.state === 'PENDING' && x.kind === 'plan'), pm = s.state.missions[a.mission];
  assert.equal(s.act('approve', a.id).ok, true); s.advance(120000);
  assert.equal(pm.state, 'APPROVED'); assert.match(pm.reason, /emergency stop is engaged/);
  assert.equal(Object.values(s.state.missions).filter((x) => x.state === 'EXECUTING').length, 0);
  // re-arm: dispatch starts again and a blocked mission can be unblocked
  assert.equal(s.act('rearm').ok, true); assert.equal(s.state.estop.engaged, false);
  s.advance(120000); assert.equal(pm.state, 'EXECUTING');
  assert.equal(s.act('unblock', 'm-date').ok, true);
});
