// T-1465: the offline snapshot store (keep, loadSnapshot, clearSnapshot) and its
// IndexedDB open. The fake IndexedDB keeps rows in a Map keyed like the real store.
import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { paths } from '../src/api/generated.ts';
import { NOW_READS, clearSnapshot, keep, loadSnapshot, type Kept } from '../src/data/snapshot.ts';

const g = globalThis as Record<string, unknown>;
const ORIGIN = 'http://core.test';
const OTHER = 'http://other.test';

let rows: Map<string, Kept>;
let opens: number;
let created: string[];
let failOpen: boolean;
let failPut: boolean;
let failClear: boolean;
let hadLocation: boolean;
let savedLocation: unknown;
let savedIndexedDB: unknown;

function request(result: unknown, fail = false) {
  const r: Record<string, unknown> = { result };
  setTimeout(() => {
    if (fail) (r.onerror as () => void)?.();
    else (r.onsuccess as () => void)?.();
  });
  return r;
}

function fakeIndexedDB() {
  const store = {
    put: (v: Kept, key: string) => {
      if (!failPut) rows.set(key, v);
      return request(key, failPut);
    },
    get: (key: string) => request(rows.get(key)),
    getAll: () => request([...rows.values()]),
    clear: () => {
      if (!failClear) rows.clear();
      return request(undefined, failClear);
    },
  };
  const db = {
    createObjectStore: (name: string) => created.push(name),
    transaction: () => ({ objectStore: () => store }),
  };
  return {
    open: () => {
      opens += 1;
      const req: Record<string, unknown> = { result: db, error: { name: 'UnknownError' } };
      setTimeout(() => {
        if (failOpen) {
          (req.onerror as () => void)?.();
          return;
        }
        (req.onupgradeneeded as () => void)?.();
        (req.onsuccess as () => void)?.();
      });
      return req;
    },
  };
}

// a few event-loop turns: keep() and the snapshot calls chain several requests
async function settle() {
  for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0));
}

const row = (origin: string, path: string, data: unknown = { path }): Kept => ({
  origin,
  path,
  data,
  seq: 7,
  at: '2026-11-14T10:00:00.000Z',
});

beforeEach(() => {
  rows = new Map();
  opens = 0;
  created = [];
  failOpen = false;
  failPut = false;
  failClear = false;
  hadLocation = 'location' in globalThis;
  savedLocation = g.location;
  savedIndexedDB = g.indexedDB;
  g.indexedDB = fakeIndexedDB();
  g.location = { origin: ORIGIN, pathname: '/', search: '', hash: '' };
});

afterEach(() => {
  if (hadLocation) g.location = savedLocation;
  else delete g.location;
  g.indexedDB = savedIndexedDB;
});

test('keep ignores a path that is not a Now read: no IndexedDB call', () => {
  keep(paths.health(), { ok: true }, 3);
  assert.equal(opens, 0);
  assert.equal(rows.size, 0);
});

test('keep writes a row keyed by origin and path, with seq null when seq is undefined', async () => {
  keep(paths.status(), { state: 'ok' }, undefined);
  await settle();
  const k = `${ORIGIN} ${paths.status()}`;
  assert.deepEqual([...rows.keys()], [k]);
  const r = rows.get(k) as Kept;
  assert.equal(r.origin, ORIGIN);
  assert.equal(r.path, paths.status());
  assert.deepEqual(r.data, { state: 'ok' });
  assert.equal(r.seq, null);
  assert.equal(new Date(r.at).toISOString(), r.at);
});

test('keep stores the seq it was given and filters the ended missions out of the list', async () => {
  keep(paths.listMissions(), { missions: [{ id: 'a', state: 'RUNNING' }, { id: 'b', state: 'COMPLETED' }] }, 42);
  await settle();
  const r = rows.get(`${ORIGIN} ${paths.listMissions()}`) as Kept;
  assert.equal(r.seq, 42);
  assert.deepEqual(r.data, { missions: [{ id: 'a', state: 'RUNNING' }] });
});

test('keep without a location global throws ReferenceError to the caller and opens nothing', () => {
  delete g.location;
  assert.throws(() => keep(paths.status(), {}, undefined), ReferenceError);
  assert.equal(opens, 0);
});

test('keep swallows a failed put: it returns undefined and writes nothing', async () => {
  failPut = true;
  assert.equal(keep(paths.digest(), { text: 'x' }, 1), undefined);
  await settle();
  assert.equal(rows.size, 0);
});

test('loadSnapshot returns this origin only, one row per Now read, in Now read order', async () => {
  const shuffled = [NOW_READS[2], NOW_READS[0], NOW_READS[3], NOW_READS[1]];
  for (const p of shuffled) rows.set(`${ORIGIN} ${p}`, row(ORIGIN, p));
  for (const p of NOW_READS) rows.set(`${OTHER} ${p}`, row(OTHER, p));
  const snap = await loadSnapshot();
  assert.ok(snap);
  assert.deepEqual(
    snap.map((k) => [k.origin, k.path]),
    NOW_READS.map((p) => [ORIGIN, p]),
  );
});

test('loadSnapshot is all or nothing: three rows of four give null', async () => {
  for (const p of NOW_READS.slice(0, 3)) rows.set(`${ORIGIN} ${p}`, row(ORIGIN, p));
  assert.equal(await loadSnapshot(), null);
});

test('loadSnapshot gives null when the database cannot be opened', async () => {
  failOpen = true;
  for (const p of NOW_READS) rows.set(`${ORIGIN} ${p}`, row(ORIGIN, p));
  assert.equal(await loadSnapshot(), null);
});

test('loadSnapshot gives null when every row belongs to another origin', async () => {
  for (const p of NOW_READS) rows.set(`${OTHER} ${p}`, row(OTHER, p));
  assert.equal(await loadSnapshot(), null);
});

test('clearSnapshot empties the store for every origin, resolves undefined, and swallows an error', async () => {
  for (const p of NOW_READS) {
    rows.set(`${ORIGIN} ${p}`, row(ORIGIN, p));
    rows.set(`${OTHER} ${p}`, row(OTHER, p));
  }
  assert.equal(await clearSnapshot(), undefined);
  assert.equal(rows.size, 0);
  failClear = true;
  assert.equal(await clearSnapshot(), undefined);
});

test('the database creates the now store on upgrade', async () => {
  await loadSnapshot();
  assert.deepEqual(created, ['now']);
});
