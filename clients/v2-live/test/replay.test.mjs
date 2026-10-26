import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createSim, CATEGORY } from '../sim.js';
import { VOCAB, CATS, vocabCounts, category, classify, buildReplay, FIVE_ROWS, GAPS, NEVER, recovery } from '../replay-model.js';
import { fmt } from '../chat-engine.js';

test('vocabulary: 130 states over 19 machines, the pinned totals, ENDED_REJECTED is RECORDED', () => {
  const v = vocabCounts();
  assert.equal(v.total, 130); assert.equal(v.machines, 19);
  assert.deepEqual(v.n, { INTENDED: 29, RECORDED: 46, SUSPENDED: 16, 'MAY-HAVE-TAKEN-EFFECT': 12, AUTHORIZED: 9, UNCERTAIN: 5, RECONCILED: 5, UNKNOWN: 5, NONE: 3 });
  assert.equal(category('execution', 'ENDED_REJECTED'), 'RECORDED');
  assert.equal(CATS.length, 9);
  assert.ok(Object.keys(v.n).every((c) => CATS.includes(c)));
});

test('a state with no entry answers UNKNOWN, never a guess; it agrees with the simulation table', () => {
  assert.equal(category('execution', 'NO_SUCH_STATE'), 'UNKNOWN');
  assert.equal(category('nomachine', 'X'), 'UNKNOWN');
  for (const [machine, states] of Object.entries(CATEGORY)) for (const [s, c] of Object.entries(states)) assert.equal(category(machine, s), c, machine + '.' + s);
  assert.ok(Object.keys(VOCAB).includes('harness'));
});

test('RECONCILED is read from the recorded edge: a kill by discard is RECORDED, a sweep is RECONCILED, no event is UNKNOWN', () => {
  assert.equal(classify('execution', 'ENDED_KILLED', { payload: { to: 'ENDED_KILLED', trigger: 'reconciled_kill' }, actor: 'system' }).answer, 'RECONCILED');
  assert.equal(classify('execution', 'ENDED_KILLED', { payload: { to: 'ENDED_KILLED', trigger: 'reconciled_kill' }, actor: 'system' }).by, 'core');
  assert.equal(classify('execution', 'ENDED_KILLED', { payload: { to: 'ENDED_KILLED', trigger: 'discarded' }, actor: 'device' }).answer, 'RECORDED');
  const none = classify('execution', 'ENDED_KILLED', null, false); assert.equal(none.answer, 'UNKNOWN'); assert.equal(none.reason, 'no_retained_transition');
  assert.equal(classify('execution', 'ENDED_KILLED', null, true).reason, 'retained_event_prefix_pruned');
  const lost = classify('execution', 'LOST', { payload: { to: 'LOST', trigger: 'heartbeat_missing' }, actor: 'system' });
  assert.equal(lost.answer, 'UNCERTAIN'); assert.equal(lost.by, 'unknown'); assert.equal(lost.byWhy, 'unsettled_lost_awaiting_core_sweep');
  assert.equal(classify('knowledge_item', 'CONFIRMED', { payload: { to: 'CONFIRMED', trigger: 'confirm' }, actor: 'device' }).by, 'device');
});

test('the read of the story: LOST is UNCERTAIN, adopted is RECONCILED by core, a failed verification is a recorded verdict', () => {
  const s = createSim(); s.advance(520 * 1000);
  const r = buildReplay(s, 'm-date');
  assert.ok(r.steps.length > 12);
  const lost = r.steps.find((x) => x.state === 'LOST'); assert.equal(lost.category, 'UNCERTAIN');
  assert.ok(lost.evidence.some((e) => e.strength === 'NOT_RECORDED' && /External effect/.test(fmt(e.label, 'en'))));
  const ad = r.steps.find((x) => x.trigger === 'adopted'); assert.equal(ad.category, 'RECONCILED'); assert.equal(ad.settled_by, 'core');
  const vf = r.steps.find((x) => x.machine === 'verification' && x.state === 'FAILED'); assert.equal(vf.category, 'RECORDED');
  assert.ok(vf.evidence.some((e) => e.value === 'fail'));
  const ok = r.steps.find((x) => x.state === 'ENDED_OK');
  assert.ok(ok.evidence.some((e) => e.strength === 'REPORTED') && ok.evidence.some((e) => e.strength === 'SUMMARY'));
  assert.equal(r.external_effects.answer, 'UNKNOWN');
  assert.equal(r.history.event_days, 180); assert.equal(r.history.open_mission_extension, false);
  assert.ok(r.starting_state.some((b) => b.source === 'Verification.base_revision' && b.answer === 'RECORDED'));
  assert.ok(r.starting_state.filter((b) => b.answer === 'UNKNOWN').length >= 2);
  const total = Object.values(r.counts).reduce((a, b) => a + b, 0); assert.equal(total, r.steps.length);
});

test('every step has a category from the vocabulary and no step is invented: each maps to an event of the mission', () => {
  const s = createSim(); s.advance(600 * 1000);
  for (const m of Object.keys(s.state.missions)) {
    const r = buildReplay(s, m);
    r.steps.forEach((x) => { assert.ok(CATS.includes(x.category)); assert.ok(s.state.events.some((e) => e.seq === x.seq && e.mission === m)); assert.ok(x.evidence.length >= 1); });
    r.records.forEach((x) => assert.ok(CATS.includes(x.answer)));
  }
});

test('a pruned log answers UNKNOWN with a reason, never "nothing happened"', () => {
  const s = createSim({ maxEvents: 40 }); s.advance(900 * 1000);
  assert.equal(s.state.pruned, true);
  const r = buildReplay(s, 'm-docs');
  assert.equal(r.history.answer, 'UNKNOWN'); assert.equal(r.history.reason, 'retained_event_prefix_pruned');
  assert.ok(r.records.every((x) => CATS.includes(x.answer)));
  const ex = r.records.find((x) => x.machine === 'execution'); assert.ok(['UNKNOWN', 'RECORDED', 'RECONCILED'].includes(ex.answer));
});

test('the five example rows and the gaps are complete; both languages exist', () => {
  assert.equal(FIVE_ROWS.length, 5); assert.equal(GAPS.length, 8); assert.equal(NEVER.length, 5);
  FIVE_ROWS.forEach((r) => { assert.ok(r.parts.length >= 2); r.parts.forEach(([s, c]) => { assert.ok(['RECORDED', 'UNKNOWN', 'SUMMARY', 'NOT_RECORDED'].includes(s)); assert.ok(c.it && c.en); }); });
  assert.ok(FIVE_ROWS.some((r) => r.parts.some((p) => p[0] === 'NOT_RECORDED')));
});

test('recovery: options follow the mission state, a LOST execution cannot be forced, nothing is offered as a re-run', () => {
  const s = createSim(); s.advance(340 * 1000);
  assert.equal(s.state.executions['x-date-1'].state, 'LOST');
  const o = recovery(s, 'm-date');
  assert.equal(o.find((x) => x.id === 'resume').ok, false); assert.match(fmt(o.find((x) => x.id === 'resume').why, 'en'), /cannot force/);
  assert.equal(o.find((x) => x.id === 'ask').ok, true);
  assert.equal(recovery(s, 'm-voice').find((x) => x.id === 'resume').act, 'resume');
  assert.equal(recovery(s, 'm-lint').find((x) => x.id === 'retry').act, 'replan');
  assert.equal(recovery(s, 'm-export').find((x) => x.id === 'resume').act, 'unblock');
  o.forEach((x) => assert.ok(x.would.length && x.wont.length));
});
