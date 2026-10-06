// The graph's list form: every edge from its field, none without it
// (§20.2, §20.17; M11, M12).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { executionEdges, knowledgeEdges, missionEdges, sessionEdges, taskDependencies, verificationEdges } from '../src/graph/relations.ts';

test('a hand-off points from the continuation to the execution it continues (M11)', () => {
  const e = executionEdges({ id: 'exe_2', task_id: 'tsk_1', mission_id: 'msn_1', handoff_from: 'exe_1', session_id: 'ses_1' });
  const cont = e.find((x) => x.rel === 'continues');
  assert.deepEqual(cont?.to, { kind: 'execution', id: 'exe_1' });
  assert.equal(cont?.field, 'Execution.handoff_from');
  assert.equal(executionEdges({ id: 'exe_1', task_id: 't', mission_id: 'm' }).find((x) => x.rel === 'continues'), undefined);
});

test('no verification-to-execution edge without the recorded execution (M12)', () => {
  const none = verificationEdges({ subject: { kind: 'task', id: 'tsk_1' }, plan_id: 'pln_1' });
  assert.equal(none.find((x) => x.to.kind === 'execution'), undefined);
  const some = verificationEdges({ subject: { kind: 'task', id: 'tsk_1' }, plan_id: 'pln_1', execution_id: 'exe_1' });
  assert.deepEqual(some.find((x) => x.to.kind === 'execution')?.to, { kind: 'execution', id: 'exe_1' });
});

test('superseded plan versions are marked, never current', () => {
  const e = missionEdges({ id: 'msn_1' }, { versions: [{ id: 'p1', plan_version: 1, state: 'SUPERSEDED' }, { id: 'p2', plan_version: 2, state: 'PROPOSED' }] });
  assert.deepEqual(e.filter((x) => x.to.kind === 'plan').map((x) => [x.to.id, !!x.inactive]), [
    ['p1', true],
    ['p2', false],
  ]);
});

test('knowledge relations keep their tier and direction', () => {
  const e = knowledgeEdges({
    id: 'kno_1',
    supersedes_id: 'kno_0',
    relations: [
      { src_kind: 'knowledge_item', src_id: 'kno_1', rel: 'decided_in', dst_kind: 'meeting', dst_id: 'mtg_1', confidence_tier: 'EXTRACTED' },
      { src_kind: 'knowledge_item', src_id: 'kno_9', rel: 'contradicts', dst_kind: 'knowledge_item', dst_id: 'kno_1', confidence_tier: 'INFERRED' },
    ],
  });
  assert.deepEqual(e.map((x) => [x.rel, x.to.id, x.tier ?? null]), [
    ['decided_in', 'mtg_1', 'EXTRACTED'],
    ['contradicts (from)', 'kno_9', 'INFERRED'],
    ['replaces', 'kno_0', null],
  ]);
});

test('session lineage and task dependencies come from their fields', () => {
  const s = sessionEdges({ id: 'ses_2', handoff_from_session_id: 'ses_1', mission_id: 'msn_1' }, { targets: [{ id: 'ses_3' }] });
  assert.deepEqual(s.map((x) => [x.rel, x.to.id]), [
    ['continues mission', 'msn_1'],
    ['handed off from', 'ses_1'],
    ['handed off to', 'ses_3'],
  ]);
  const d = taskDependencies({ depends_on: ['t1', 'tX'] }, { t1: { id: 'tsk_1' } });
  assert.deepEqual(d.map((x) => x.to.id), ['tsk_1']); // an unknown key is no edge
});
