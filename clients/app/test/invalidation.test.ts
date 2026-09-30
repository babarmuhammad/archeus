// Which reads a frame makes stale (§14.2; M28), and that a frame is never read
// as state (§19).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { RULES, staleBy } from '../src/data/invalidation.ts';

const frame = (kind: string, id: string, event = kind + '.state_changed') => ({ event, data: { subject: { kind, id }, scope: {} } });

test('every subject kind Core registers has a rule, even an empty one', () => {
  const src = readFileSync(new URL('../../../archeus/core/domain/events.py', import.meta.url), 'utf8');
  const kinds = new Set([...src.matchAll(/^\s*\('[a-z_.]+', '([a-z_]+)', '(?:user|system)'/gm)].map((m) => m[1]));
  assert.ok(kinds.size > 20, 'read the registry');
  for (const k of kinds) assert.ok(k in RULES, `no invalidation rule for subject kind ${k}`);
});

test('a mission frame re-reads the mission, the lists and what waits on the user (M28)', () => {
  const stale = staleBy(frame('mission', 'msn_1'));
  for (const p of ['/v1/missions', '/v1/missions/msn_1', '/v1/missions/msn_1/plan', '/v1/attention', '/v1/digest', '/v1/missions?project=prj_1'])
    assert.ok(stale(p), p);
  assert.ok(!stale('/v1/devices'));
  assert.ok(!stale('/v1/knowledge'));
});

test('execution progress re-reads only that execution', () => {
  const stale = staleBy(frame('execution', 'exe_1', 'execution.progress'));
  assert.ok(stale('/v1/executions/exe_1/stream'));
  assert.ok(stale('/v1/executions/exe_1'));
  assert.ok(!stale('/v1/executions/exe_2/stream'));
});

test('an approval frame re-reads approvals, attention and missions', () => {
  const stale = staleBy(frame('approval', 'apr_1'));
  assert.ok(stale('/v1/approvals/apr_1') && stale('/v1/attention') && stale('/v1/missions/msn_9'));
});

test('an unknown kind makes nothing stale: late, never wrong', () => {
  const stale = staleBy(frame('spaceship', 'x'));
  assert.ok(!stale('/v1/missions'));
});

test('the stream handler reads identities only, never a payload', () => {
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.ok(!/f\.data\.(payload|state|to|from)/.test(app));
  const stream = readFileSync(new URL('../src/api/stream.ts', import.meta.url), 'utf8');
  assert.ok(!/payload/.test(stream.replace(/\/\/.*$/gm, '')));
});
