// The SPA against the shared parity cases (p17-design-gate A2): the TUI's
// tests/v1/tui/test_parity.py holds the Python side to the same outputs, so the
// two presentations cannot drift apart silently.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as rel from '../src/graph/relations.ts';
import * as pr from '../src/state/present.ts';
import * as cn from '../src/data/connection.ts';
import * as cm from '../src/data/commands.ts';
import { staleBy } from '../src/data/invalidation.ts';

type Fn = (...a: never[]) => unknown;
const FN: Record<string, Fn> = {
  missionEdges: rel.missionEdges, planEdges: rel.planEdges, taskDependencies: rel.taskDependencies,
  executionEdges: rel.executionEdges, verificationEdges: rel.verificationEdges, sessionEdges: rel.sessionEdges,
  knowledgeEdges: rel.knowledgeEdges, runEdges: rel.runEdges,
  present: pr.present, badge: pr.badge, isDone: pr.isDone, offers: pr.offers, presenceLabel: pr.presenceLabel,
  resourceLine: pr.resourceLine, statusLine: pr.statusLine, explainState: pr.explainState, ago: pr.ago,
  next: cn.next, freshness: cn.freshness, canCommand: cn.canCommand,
  explain: cm.explain, decideBody: cm.decideBody, retryable: cm.retryable,
  keyAfter: ((p: string, o: 'ok' | 'refused' | 'network') => cm.keyAfter(p, o, () => 'NEW')) as Fn,
  staleBy: ((f: { event: string; data?: unknown }, p: string) => staleBy(f)(p)) as Fn,
};

const { cases } = JSON.parse(readFileSync(new URL('./fixtures/parity.json', import.meta.url), 'utf-8')) as {
  cases: { fn: string; args: never[]; out: unknown }[];
};

test('every shared parity case gives the recorded output', () => {
  for (const c of cases) assert.deepEqual(FN[c.fn](...c.args), c.out, `${c.fn}(${JSON.stringify(c.args)})`);
});

test('every function held to parity has cases, and every case names one', () => {
  const named = new Set(cases.map((c) => c.fn));
  assert.deepEqual([...named].filter((f) => !(f in FN)), []);
  assert.deepEqual(Object.keys(FN).filter((f) => !named.has(f)), []);
});
