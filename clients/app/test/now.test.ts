// P19.5 R8: Now as the operational surface — the state sentence, upcoming
// (step 1), recent decisions, the automation line and the live map
// (ADR-0027 §4-5, rulebook §6 O-4-O-6, §9, §22). Mutation-verified by
// tools/mutate_p19_5.py (N181 onward).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { activeMissions, automationLine, DECISIONS_SHOWN, liveMap, MAP_CAP, mapRead, mapSeeds, recentDecisions, scheduled, stateSentence, upcoming } from '../src/state/now.ts';
import { MAP_MIN_WIDTH } from '../src/graph/wide.ts';
import { build } from '../src/graph/model.ts';

const src = (p: string) => readFileSync(new URL(p, import.meta.url), 'utf8');
const mission = (id: string, state: string) => ({ id, state, title: id, objective: '', version: 1, created_at: '', updated_at: '' }) as never;

test('the state sentence is two counts in words, never a greeting', () => {
  assert.equal(stateSentence(2, 1), 'Archeus is working on 2 missions. 1 needs you.');
  assert.equal(stateSentence(1, 0), 'Archeus is working on 1 mission. Nothing needs you.');
  assert.equal(stateSentence(0, 0), 'Archeus is idle. Nothing needs you.');
  assert.equal(stateSentence(0, 3), 'Archeus is idle. 3 need you.');
  for (const [a, n] of [[0, 0], [1, 1], [5, 2]]) assert.doesNotMatch(stateSentence(a, n), /\b(good|morning|afternoon|evening|hello|hi|welcome)\b/i);
});

test('active missions are the unsettled ones; upcoming is approved and planning', () => {
  const ms = ['PLANNING', 'APPROVED', 'EXECUTING', 'APPROVAL_REQUIRED', 'COMPLETED', 'PAUSED', 'CREATED'].map((s, i) => mission(`m${i}`, s));
  assert.deepEqual(activeMissions(ms).map((m: { state: string }) => m.state), ['PLANNING', 'APPROVED', 'EXECUTING', 'CREATED']);
  assert.deepEqual(upcoming(ms).map((m: { state: string }) => m.state), ['PLANNING', 'APPROVED', 'CREATED'], 'what the screen calls Approved or Planning');
  const thinking = ['UNDERSTANDING', 'CONTEXT_GATHERING', 'REASONING', 'REPLANNING'].map((s, i) => mission(`p${i}`, s));
  assert.equal(upcoming(thinking).length, 4);
  assert.equal(upcoming(['EXECUTING', 'VERIFYING', 'REVIEWING', 'RESUMED', 'APPROVAL_REQUIRED', 'BLOCKED'].map((s, i) => mission(`x${i}`, s))).length, 0);
});

test('the automation line counts the enabled automations, and is absent at none', () => {
  const a = (state: string) => ({ id: state, name: state, state, trigger: {}, template: {}, version: 1 }) as never;
  assert.equal(automationLine([a('ENABLED'), a('ENABLED'), a('DISABLED'), a('DRAFT'), a('SUSPENDED')]), '2 automations watching');
  assert.equal(automationLine([a('ENABLED')]), '1 automation watching');
  assert.equal(automationLine([a('DISABLED'), a('PENDING_APPROVAL')]), null);
});

test('upcoming step 2 (P21 D9): the enabled schedules, soonest first, by Core\'s next_run_at', () => {
  const a = (id: string, state: string, next_run_at: string | null) => ({ id, name: id, state, next_run_at, trigger: { kind: 'schedule', every: '1h' }, template: {}, version: 1 }) as never;
  const got = scheduled([a('late', 'ENABLED', '2026-10-21T11:00:00.000Z'), a('off', 'DISABLED', '2026-10-21T09:30:00.000Z'), a('soon', 'ENABLED', '2026-10-21T09:15:00.000Z'), a('event', 'ENABLED', null)]);
  assert.deepEqual(got.map((x: { id: string }) => x.id), ['soon', 'late']);
});

test('upcoming step 2: a schedule its gate holds is not upcoming (Control says why)', () => {
  const a = (id: string, waiting: string | null) => ({ id, name: id, state: 'ENABLED', next_run_at: '2026-10-21T09:15:00.000Z', waiting, trigger: { kind: 'schedule', every: '1h' }, template: {}, version: 1 }) as never;
  assert.deepEqual(scheduled([a('held', 'Core disarmed'), a('free', null)]).map((x: { id: string }) => x.id), ['free']);
});

test('recent decisions: decided approvals, fallbacks and confirmed DECISION knowledge, newest first', () => {
  const ap = [
    { id: 'apr_1', state: 'CONSUMED', decision: 'approve', decided_at: '2026-10-02T10:00:03Z', mission_id: 'm1' },
    { id: 'apr_2', state: 'PENDING', mission_id: 'm2' },
    { id: 'apr_3', state: 'REJECTED', decision: 'reject', decided_at: '2026-10-02T10:00:01Z', mission_id: 'm3' },
  ] as never[];
  const rd = [
    { id: 'rd_1', result: 'selected', created_at: '2026-10-02T10:00:09Z' },
    { id: 'rd_2', result: 'fallback', created_at: '2026-10-02T10:00:02Z' },
  ] as never[];
  const kn = [
    { id: 'kn_1', type: 'DECISION', state: 'CONFIRMED', updated_at: '2026-10-02T10:00:04Z' },
    { id: 'kn_2', type: 'DECISION', state: 'CANDIDATE', updated_at: '2026-10-02T10:00:08Z' },
    { id: 'kn_3', type: 'LESSON', state: 'CONFIRMED', updated_at: '2026-10-02T10:00:07Z' },
  ] as never[];
  const got = recentDecisions(ap, rd, kn);
  assert.deepEqual(got.map((d) => [d.kind, d.id, d.words]), [
    ['knowledge_item', 'kn_1', 'decision'],
    ['approval', 'apr_1', 'approved'],
    ['route_decision', 'rd_2', 'fell back'],
    ['approval', 'apr_3', 'rejected'],
  ]);
  assert.equal(got[1].mission, 'm1', 'an approval names its mission');
  const many = Array.from({ length: 9 }, (_, i) => ({ id: `a${i}`, decision: 'request_changes', decided_at: `2026-10-02T10:00:0${i}Z`, mission_id: 'm' })) as never[];
  const top = recentDecisions(many, [], []);
  assert.equal(top.length, DECISIONS_SHOWN);
  assert.deepEqual(top.map((d) => d.id), ['a8', 'a7', 'a6', 'a5', 'a4']);
  assert.equal(top[0].words, 'changes requested');
});

const node = (kind: string, id: string, extra = {}) => ({ kind, id, label: `${kind} ${id}`, ...extra });
const edge = (a: [string, string], b: [string, string], field = 'executions.mission_id') => ({
  id: `${field}|${a.join(':')}|${b.join(':')}`,
  from: { kind: a[0], id: a[1] },
  to: { kind: b[0], id: b[1] },
  field,
});

test('the live map holds the seed missions and their live attempts, and nothing else', () => {
  const r1 = {
    nodes: [node('mission', 'm1'), node('execution', 'x1', { parent: { kind: 'task', id: 't1' } }), node('execution', 'x0'), node('plan', 'p1'), node('project', 'pr'), node('task', 't9', { endpoint: true })],
    edges: [edge(['execution', 'x1'], ['mission', 'm1']), edge(['execution', 'x0'], ['mission', 'm1']), edge(['plan', 'p1'], ['mission', 'm1'], 'plans.mission_id'), edge(['mission', 'm1'], ['project', 'pr'], 'missions.project_id')],
  };
  const r2 = { nodes: [node('mission', 'm2'), node('mission', 'm1'), node('execution', 'x1')], edges: [edge(['execution', 'x1'], ['mission', 'm1'])] };
  const d = liveMap(['m1', 'm2'], [r1, r2, undefined], new Set(['x1']));
  assert.deepEqual(d.nodes.map((n) => `${n.kind}:${n.id}`), ['mission:m1', 'mission:m2', 'execution:x1'], 'missions first, live attempts, each once');
  assert.deepEqual(d.edges.map((e) => e.field), ['executions.mission_id'], 'only the recorded edges between what is drawn');
  assert.equal(d.truncated, false);
  // the attempt's task is not in the picture: it stands at the top, never invented
  assert.equal(build(d).parentOf.get('execution:x1'), null);
  // a mission that is not a seed is never drawn, even when a read returns it
  assert.deepEqual(liveMap(['m2'], [r1, r2], new Set(['x1'])).nodes.map((n) => n.id), ['m2', 'x1']);
});

test('the live map is bounded: at most 40 nodes, what the cap cut is counted', () => {
  const ms = Array.from({ length: 45 }, (_, i) => mission(`m${i}`, 'EXECUTING'));
  assert.equal(MAP_CAP, 40);
  const seeds = mapSeeds([mission('done', 'COMPLETED'), mission('asks', 'APPROVAL_REQUIRED'), ...ms]);
  assert.equal(seeds.length, 40, 'at most 40 seeds, so at most 40 reads');
  assert.ok(!seeds.includes('done') && !seeds.includes('asks'), 'a settled mission is not live work');
  assert.deepEqual(seeds.slice(0, 2), ['m0', 'm1']);
  const reads = [{ nodes: [...ms.map((m: { id: string }) => node('mission', m.id)), ...Array.from({ length: 5 }, (_, i) => node('execution', `x${i}`))], edges: [] }];
  const all = ms.map((m: { id: string }) => m.id);
  const d = liveMap(all, reads, new Set(['x0', 'x1', 'x2', 'x3', 'x4']));
  assert.equal(d.nodes.length, 40);
  assert.ok(d.nodes.every((n) => n.kind === 'mission'), 'missions first');
  assert.equal(d.truncated, true);
  assert.deepEqual(d.hidden?.map((h) => [h.kind, h.count]).sort(), [['execution', 5], ['mission', 5]]);
});

test('the map reads each mission at depth 1, capped, and is shown from 1000 px', () => {
  assert.equal(mapRead('mis_1'), '/v1/world/graph?focus=mission%3Amis_1&depth=1&limit=40');
  assert.equal(MAP_MIN_WIDTH, 1000);
});

test('Now holds at most seven blocks, in ADR-0027 §4 order, under the state sentence', () => {
  const now = src('../src/surfaces/Now.tsx');
  const view = now.slice(now.indexOf('export function NowView'), now.indexOf('function AutomationLine'));
  const order = ['state-sentence', 'AutomationLine', 'title="Needs you"', 'title="Happening now"', '<DigestSection', 'title="Upcoming"', '<Decisions', '<MapSection', '<Conversation'];
  const at = order.map((o) => view.indexOf(o));
  assert.ok(at.every((i) => i >= 0), `every block is on Now: ${order.filter((_, i) => at[i] < 0)}`);
  assert.deepEqual([...at].sort((a, b) => a - b), at, 'in order');
  assert.ok(order.slice(2).length <= 7);
  assert.doesNotMatch(now, /Archeus · /, 'the presence line is gone');
  assert.match(src('../src/styles/app.css'), /\.state-sentence \{\r?\n {2}font: 600 var\(--type-display\);/, 'the sentence is in the display role');
});
