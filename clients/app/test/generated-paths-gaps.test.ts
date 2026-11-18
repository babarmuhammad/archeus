// T-1466: the generated request builders. The file is generated (tools/gen_ui.py);
// these tests pin what it sends, so a change to the generator shows here.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { api, paths, type Method, type Send } from '../src/api/generated.ts';

interface Call {
  method: Method;
  path: string;
  body: unknown;
}

function recorder(): { calls: Call[]; send: Send } {
  const calls: Call[] = [];
  const send: Send = <T>(method: Method, path: string, body?: unknown) => {
    calls.push({ method, path, body });
    return Promise.resolve(undefined as T);
  };
  return { calls, send };
}

test('qs keeps 0 and empty strings and drops undefined', () => {
  assert.equal(paths.metricsDays({ days: 0 }), '/v1/metrics?days=0');
  assert.equal(paths.listMissions({ project: '' }), '/v1/missions?project=');
  assert.equal(paths.listMissions({ state: undefined }), '/v1/missions');
});

test('no query means no question mark', () => {
  assert.equal(paths.listMissions(), '/v1/missions');
  assert.equal(paths.metricsDays(), '/v1/metrics');
});

test('qs encodes both the key and the value', () => {
  assert.equal(paths.listMissions({ project: 'a b&c=d' }), '/v1/missions?project=a%20b%26c%3Dd');
});

test('an id is one path segment: slash, question mark, hash and percent are encoded', () => {
  assert.equal(paths.getMission('a/b?c#d%e'), '/v1/missions/a%2Fb%3Fc%23d%25e');
});

test('a non-ASCII id is percent-encoded UTF-8 and decodes back to the input', () => {
  const id = 'mission-é€\u{1F600}';
  const path = paths.getMission(id);
  assert.equal(path.startsWith('/v1/missions/'), true);
  assert.equal(decodeURIComponent(path.slice('/v1/missions/'.length)), id);
});

test('optional query on a route with a path id keeps order and presence', () => {
  assert.equal(paths.missionTimeline('m', { before: 0, limit: 5 }), '/v1/missions/m/timeline?before=0&limit=5');
  assert.equal(paths.missionTimeline('m', { limit: 5 }), '/v1/missions/m/timeline?limit=5');
  assert.equal(paths.missionTimeline('m'), '/v1/missions/m/timeline');
});

test('a GET wrapper sends one GET with its path and returns the result unchanged', async () => {
  const { calls, send } = recorder();
  const out = await api.getMission(send, 'x');
  assert.deepEqual(calls, [{ method: 'GET', path: '/v1/missions/x', body: undefined }]);
  assert.equal(out, undefined);
});

test('a POST wrapper passes its body through as the third argument, with the id encoded', async () => {
  const { calls, send } = recorder();
  const body = {} as Parameters<typeof api.editPlan>[2];
  await api.editPlan(send, 'p/1', body);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, 'POST');
  assert.equal(calls[0].path, '/v1/plans/p%2F1/edit');
  assert.equal(calls[0].body, body);
});

test('a wrapper with a default query sends the same path as the path builder', async () => {
  const { calls, send } = recorder();
  await api.metricsDays(send);
  assert.deepEqual(calls, [{ method: 'GET', path: paths.metricsDays(), body: undefined }]);
});

// A dot segment makes the browser resolve the URL to a list route ('/v1/' or
// '/v1/missions/'), so an id of '..' names no object. Reach: destinations.ts:24
// parses '#/o/mission/..' to the id '..', which the object route then reads.
test('a dot-only id is encoded, never sent as a dot segment', { todo: 'generated.ts:1782 encodes only the characters encodeURIComponent touches; a dot-only id is left as a dot segment' }, () => {
  assert.equal(paths.getMission('..').endsWith('/..'), false);
  assert.equal(paths.getMission('.').endsWith('/.'), false);
});
