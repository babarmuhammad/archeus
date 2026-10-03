// The Relations list from Core's graph read (p19-design-gate B1): every edge
// incident to the object, said from its end; containment is the graph's alone.
// Which edges exist is Core's (tests/v1/unit/test_graph_parity.py).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EDGE_WORDS, edgeRows, edgeWords, relationsPath } from '../src/graph/relations.ts';

const at = (kind: string, id: string) => ({ kind, id });
const col = (from: [string, string], to: [string, string], field: string, extra = {}) => ({
  from: at(...from), to: at(...to), field, rel: null, tier: null, inactive: false, structural: false, ...extra,
});

test('an edge is said from the end one stands at, and points at the other end', () => {
  const g = [col(['execution', 'exe_2'], ['execution', 'exe_1'], 'Execution.handoff_from')];
  assert.deepEqual(edgeRows(g, at('execution', 'exe_2')), [{ rel: 'continues', to: at('execution', 'exe_1'), field: 'Execution.handoff_from' }]);
  assert.deepEqual(edgeRows(g, at('execution', 'exe_1')), [{ rel: 'continued by', to: at('execution', 'exe_2'), field: 'Execution.handoff_from' }]);
});

test('only edges touching the object are its rows, and containment is never one', () => {
  const g = [
    col(['task', 'tsk_1'], ['plan', 'pln_1'], 'tasks.plan_id', { structural: true }),
    col(['execution', 'exe_1'], ['task', 'tsk_1'], 'executions.task_id'),
    col(['plan', 'pln_1'], ['mission', 'msn_1'], 'plans.mission_id'),
  ];
  assert.deepEqual(edgeRows(g, at('plan', 'pln_1')).map((e) => e.to.id), ['msn_1']);
  assert.deepEqual(edgeRows(g, at('task', 'tsk_1')).map((e) => e.to.id), ['exe_1']);
});

test('superseded plan versions are marked, never current', () => {
  const g = [
    col(['plan', 'p1'], ['mission', 'msn_1'], 'plans.mission_id', { inactive: true }),
    col(['plan', 'p2'], ['mission', 'msn_1'], 'plans.mission_id'),
  ];
  assert.deepEqual(edgeRows(g, at('mission', 'msn_1')).map((x) => [x.to.id, !!x.inactive]), [
    ['p1', true],
    ['p2', false],
  ]);
});

test('knowledge relations keep their tier and direction; a column edge has no tier', () => {
  const me = at('knowledge_item', 'kno_1');
  const g = [
    col(['knowledge_item', 'kno_1'], ['meeting', 'mtg_1'], 'relations.decided_in', { rel: 'decided_in', tier: 'EXTRACTED' }),
    col(['knowledge_item', 'kno_9'], ['knowledge_item', 'kno_1'], 'relations.contradicts', { rel: 'contradicts', tier: 'INFERRED' }),
    col(['knowledge_item', 'kno_1'], ['knowledge_item', 'kno_0'], 'KnowledgeItem.supersedes_id'),
  ];
  assert.deepEqual(edgeRows(g, me).map((x) => [x.rel, x.to.id, x.tier ?? null]), [
    ['decided_in', 'mtg_1', 'EXTRACTED'],
    ['contradicts (from)', 'kno_9', 'INFERRED'],
    ['replaces', 'kno_0', null],
  ]);
});

test('every field has words at both ends; an unknown field says its own name', () => {
  for (const [field, [h, r]] of Object.entries(EDGE_WORDS)) {
    assert.ok(h && r, field);
    assert.equal(edgeWords(field, true), h);
    assert.equal(edgeWords(field, false), r);
  }
  assert.equal(edgeWords('Not.a_field', true), 'Not.a_field');
});

test('the list reads one hop around its object, every edge', () => {
  assert.equal(relationsPath('mission', 'msn_1'), '/v1/world/graph?focus=mission%3Amsn_1&depth=1&limit=1000');
});
