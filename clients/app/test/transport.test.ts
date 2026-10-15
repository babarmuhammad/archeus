// T-096: the Qt shell's page (`memory=1`) keeps its device token in memory only
// (p20 D1), and a load with no launch code still finds a Core that is down, so
// B7's offline snapshot is what it shows.
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { authenticate, takeFragment, CoreError } from '../src/api/transport.ts';

let disk: Map<string, unknown>;
let answer: () => Promise<Response>;
const g = globalThis as Record<string, unknown>;

function request(result?: unknown) {
  const r: Record<string, unknown> = { result };
  setTimeout(() => (r.onsuccess as () => void)?.());
  return r;
}

beforeEach(() => {
  disk = new Map();
  const session = new Map<string, string>();
  g.sessionStorage = { getItem: (k: string) => session.get(k) ?? null, setItem: (k: string, v: string) => session.set(k, v) };
  g.location = { hash: '', pathname: '/', search: '' };
  g.history = { replaceState: () => {} };
  const store = {
    get: (k: string) => request(disk.get(k)),
    put: (v: unknown, k: string) => (disk.set(k, v), request()),
    delete: (k: string) => (disk.delete(k), request()),
    clear: () => request(),
  };
  g.indexedDB = { open: () => request({ transaction: () => ({ objectStore: () => store }) }) };
  g.fetch = () => answer();
});

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

function shellPage(launch?: string) {
  (g.location as { hash: string }).hash = launch ? `#launch=${launch}&memory=1` : '#memory=1';
  return takeFragment().launch;
}

test('a shell page redeems its code, keeps the token off disk and drops one an earlier shell kept', async () => {
  disk.set('device-token', 'old');
  answer = () => json(200, { device_id: 'dvc_1', token: 'tok', scopes: ['observe'] });
  assert.equal(await authenticate(shellPage('code')), 'tok');
  assert.equal(disk.has('device-token'), false);
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
