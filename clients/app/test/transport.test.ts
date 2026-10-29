// T-096: the Qt shell's page (`memory=1`) keeps its device token in memory only
// (p20 D1), and a load with no launch code still finds a Core that is down, so
// B7's offline snapshot is what it shows.
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { authenticate, clearToken, takeFragment, CoreError } from '../src/api/transport.ts';

let disk: Map<string, unknown>;
let answer: (path: string, init: RequestInit) => Promise<Response>;
let log: string[];
const g = globalThis as Record<string, unknown>;

function request(result?: unknown) {
  const r: Record<string, unknown> = { result };
  setTimeout(() => (r.onsuccess as () => void)?.());
  return r;
}

beforeEach(() => {
  disk = new Map();
  log = [];
  const session = new Map<string, string>();
  g.sessionStorage = { getItem: (k: string) => session.get(k) ?? null, setItem: (k: string, v: string) => session.set(k, v) };
  g.location = { hash: '', pathname: '/', search: '' };
  g.history = { replaceState: () => {} };
  const store = {
    get: (k: string) => request(disk.get(k)),
    put: (v: unknown, k: string) => (disk.set(k, v), request()),
    delete: (k: string) => (log.push('delete ' + k), disk.delete(k), request()),
    clear: () => request(),
  };
  g.indexedDB = { open: () => request({ transaction: () => ({ objectStore: () => store }) }) };
  g.fetch = (path: string, init: RequestInit) => {
    log.push(`${init.method} ${path} ${(init.headers as Record<string, string>).Authorization ?? '-'}`);
    return answer(path, init);
  };
});

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

function shellPage(launch?: string) {
  (g.location as { hash: string }).hash = launch ? `#launch=${launch}&memory=1` : '#memory=1';
  return takeFragment().launch;
}

// a Core that knows the earlier shell's token as device dvc_old
const core = (path: string) =>
  path === '/v1/sync'
    ? json(200, { client: { id: 'dvc_old' } })
    : path.endsWith('/revoke')
      ? json(200, { ok: true })
      : json(200, { device_id: 'dvc_1', token: 'tok', scopes: ['observe'] });

test('a shell page revokes the token an earlier shell kept through itself, then deletes it, then redeems its code', async () => {
  disk.set('device-token', 'old');
  answer = core;
  assert.equal(await authenticate(shellPage('code')), 'tok');
  assert.deepEqual(log.slice(0, 3), [
    'GET /v1/sync Bearer old',
    'POST /v1/devices/dvc_old/revoke Bearer old',
    'delete device-token',
  ]);
  assert.equal(disk.has('device-token'), false);
});

test('Core down: the token an earlier shell kept stays until a launch can revoke it', async () => {
  disk.set('device-token', 'old');
  shellPage();
  answer = () => Promise.reject(new TypeError('connection refused'));
  await assert.rejects(authenticate(undefined), (e) => e instanceof CoreError && e.status === 0);
  assert.equal(disk.get('device-token'), 'old');
  assert.equal(log.some((l) => l.startsWith('delete')), false);
});

test('a token Core already revoked is deleted with no revoke of its own', async () => {
  disk.set('device-token', 'old');
  answer = (path) => (path === '/v1/sync' ? json(401, { error: 'unauthenticated' }) : core(path));
  assert.equal(await authenticate(shellPage('code')), 'tok');
  assert.equal(log.some((l) => l.includes('/revoke')), false);
  assert.equal(disk.has('device-token'), false);
});

// T-096 review finding 1: only a revoke that worked, or a 401, may delete it
for (const [why, refuse] of [
  ['sync 503 busy', (p: string) => (p === '/v1/sync' ? json(503, { error: 'busy' }) : core(p))],
  ['revoke 500', (p: string) => (p.endsWith('/revoke') ? json(500, { error: 'internal' }) : core(p))],
  ['revoke 403', (p: string) => (p.endsWith('/revoke') ? json(403, { error: 'forbidden' }) : core(p))],
  ['a sync with no client', (p: string) => (p === '/v1/sync' ? json(200, {}) : core(p))],
] as const) {
  test(`Core refusing (${why}) keeps the token an earlier shell kept`, async () => {
    disk.set('device-token', 'old');
    answer = refuse;
    await authenticate(shellPage('code'));
    assert.equal(disk.get('device-token'), 'old');
    assert.equal(log.some((l) => l.startsWith('delete')), false);
  });
}

test('signing this shell page out forgets its token and leaves the disk to retire()', async () => {
  answer = core;
  assert.equal(await authenticate(shellPage('code')), 'tok');
  disk.set('device-token', 'kept');               // a live one retire() could not revoke
  await clearToken();
  assert.equal(disk.get('device-token'), 'kept');
  assert.equal(log.some((l) => l.startsWith('delete')), false);
  disk.delete('device-token');
  assert.equal(await authenticate(undefined), null); // held is gone
});

test('a shell page with no code is signed out when Core answers', async () => {
  shellPage();
  answer = () => json(401, { error: 'unauthenticated' });
  assert.equal(await authenticate(undefined), null);
});

test('a shell page with no code meets a Core that is down, which is B7\'s cue', async () => {
  shellPage();
  answer = () => Promise.reject(new TypeError('connection refused'));
  await assert.rejects(authenticate(undefined), (e) => e instanceof CoreError && e.status === 0);
});
