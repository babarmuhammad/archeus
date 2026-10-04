// The offline snapshot (p19-design-gate B7): what is kept, by whom, as of when.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { paths, type Mission } from '../src/api/generated.ts';
import { NOW_READS, asOf, keptData, mayKeep, type Kept } from '../src/data/snapshot.ts';

test('only the Now composition is kept', () => {
  assert.deepEqual([...NOW_READS], ['/v1/status', '/v1/digest', '/v1/attention', '/v1/missions']);
});

test('the missions kept are the ones that have not ended: working, or waiting on a person (R13-02)', () => {
  const m = (id: string, state: string) => ({ id, state, title: id }) as unknown as Mission;
  const all = [m('a', 'EXECUTING'), m('b', 'COMPLETED'), m('c', 'APPROVED'), m('d', 'CANCELLED'), m('e', 'APPROVAL_REQUIRED'), m('f', 'FAILED'), m('g', 'PAUSED'), m('h', 'BLOCKED')];
  const kept = keptData(paths.listMissions(), { missions: all });
  assert.deepEqual((kept as { missions: Mission[] }).missions.map((x) => x.id), ['a', 'c', 'e', 'g', 'h']);
  const status = { live: [] };
  assert.equal(keptData(paths.status(), status), status);
});

test('never on a client paired observe-only; anywhere else', () => {
  assert.equal(mayKeep({ origin: 'paired', scopes: ['observe'] }), false);
  assert.equal(mayKeep({ origin: 'paired', scopes: ['observe', 'control'] }), true);
  assert.equal(mayKeep({ origin: 'local', scopes: ['observe'] }), true);
});

test('a snapshot is as old as its oldest read', () => {
  const k = (at: string) => ({ at }) as Kept;
  assert.equal(asOf([k('2026-10-04T10:05:00.000Z'), k('2026-10-04T09:00:00.000Z'), k('2026-10-04T11:00:00.000Z')]), '2026-10-04T09:00:00.000Z');
});

test('the service worker still never touches the API (D6 holds for it)', () => {
  const sw = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8');
  assert.match(sw, /url\.pathname\.startsWith\('\/v1\/'\)\) return;/);
  assert.doesNotMatch(sw, /indexedDB/);
});
