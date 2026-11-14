// T-1464: the device token's two homes (memory-only for the Qt shell, IndexedDB
// otherwise) and the pairing redeem path. The token is a bearer credential: every
// value here is a fixed fake, and nothing prints one.
import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { authenticate, clearToken, memoryOnly, redeemPairing, CoreError } from '../src/api/transport.ts';

const g = globalThis as Record<string, unknown>;
// the flag transport.ts keeps in sessionStorage (its MEMORY constant)
const MEMORY_FLAG = 'archeus-token-in-memory';

let disk: Map<string, unknown>;
let log: string[];
let session: Map<string, string>;
let failPut: boolean;
let lastBody: Record<string, unknown> | undefined;
let answer: (path: string, init: RequestInit) => Promise<Response>;
let savedNavigator: PropertyDescriptor | undefined;
let savedSessionStorage: unknown;
let savedIndexedDB: unknown;
let savedFetch: unknown;

function request(result?: unknown, fail = false) {
  const r: Record<string, unknown> = { result, error: fail ? new Error('idb write failed') : undefined };
  setTimeout(() => {
    if (fail) (r.onerror as () => void)?.();
    else (r.onsuccess as () => void)?.();
  });
  return r;
}

function fakeIndexedDB() {
  const store = {
    get: (k: string) => request(disk.get(k)),
    put: (v: unknown, k: string) => {
      log.push(`put ${k}`);
      if (!failPut) disk.set(k, v);
      return request(undefined, failPut);
    },
    delete: (k: string) => {
      log.push(`delete ${k}`);
      disk.delete(k);
      return request(undefined);
    },
  };
  return {
    open: () => {
      const req: Record<string, unknown> = { result: { transaction: () => ({ objectStore: () => store }) } };
      setTimeout(() => (req.onsuccess as () => void)?.());
      return req;
    },
  };
}

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

const pairOk = (path: string) =>
  path === '/v1/devices/pair/redeem'
    ? json(200, { device_id: 'dvc_new', token: 'tok-new', scopes: ['admin'], expires_at: '2026-11-14T16:00:00Z' })
    : path.endsWith('/revoke')
      ? json(200, { ok: true })
      : json(200, { version: 'test' });

function setMemory(on: boolean) {
  session = new Map<string, string>();
  if (on) session.set(MEMORY_FLAG, '1');
  g.sessionStorage = { getItem: (k: string) => session.get(k) ?? null, setItem: (k: string, v: string) => session.set(k, v) };
}

function setUserAgent(userAgent: string) {
  Object.defineProperty(globalThis, 'navigator', { value: { userAgent }, configurable: true, writable: true });
}

beforeEach(async () => {
  disk = new Map();
  log = [];
  failPut = false;
  lastBody = undefined;
  answer = (path) => pairOk(path);
  savedNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  savedSessionStorage = g.sessionStorage;
  savedIndexedDB = g.indexedDB;
  savedFetch = g.fetch;
  setMemory(true);
  setUserAgent('Macintosh');
  g.indexedDB = fakeIndexedDB();
  g.fetch = (path: string, init: RequestInit) => {
    const auth = (init.headers as Record<string, string>).Authorization ?? '-';
    log.push(`${init.method} ${path} ${auth}`);
    lastBody = typeof init.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : undefined;
    return answer(path, init);
  };
  // the held token is module state: start every test with none held
  await clearToken();
  log = [];
});

afterEach(() => {
  if (savedNavigator) Object.defineProperty(globalThis, 'navigator', savedNavigator);
  else delete g.navigator;
  g.sessionStorage = savedSessionStorage;
  g.indexedDB = savedIndexedDB;
  g.fetch = savedFetch;
});

test('memoryOnly is true only when the flag reads exactly "1"', () => {
  delete g.sessionStorage;
  assert.equal(memoryOnly(), false);
  let value: string | null = null;
  g.sessionStorage = { getItem: () => value, setItem: () => undefined };
  for (const v of ['0', 'yes', '', null]) {
    value = v;
    assert.equal(memoryOnly(), false, `flag ${JSON.stringify(v)}`);
  }
  value = '1';
  assert.equal(memoryOnly(), true);
});

test('in memory mode the pairing save touches no IndexedDB', async () => {
  g.indexedDB = {
    open: () => {
      throw new Error('IndexedDB must not be opened in memory mode');
    },
  };
  assert.equal(await redeemPairing('code', 'phone'), 'tok-new');
  assert.deepEqual(log, ['POST /v1/devices/pair/redeem -']);
});

test('in memory mode the token saved by pairing is the one loaded back', async () => {
  await redeemPairing('code', 'phone');
  log = [];
  assert.equal(await authenticate(undefined), 'tok-new');
  assert.deepEqual(log, ['GET /v1/version -', 'GET /v1/version Bearer tok-new']);
});

test('memory-mode clear leaves the disk copy alone: no IndexedDB delete', async () => {
  disk.set('device-token', 'disk-tok');
  await clearToken();
  assert.equal(disk.get('device-token'), 'disk-tok');
  assert.equal(log.some((l) => l.startsWith('delete')), false);
});

test('memory-mode clear empties the held token', async () => {
  await redeemPairing('code', 'phone');
  await clearToken();
  log = [];
  assert.equal(await authenticate(undefined), null);
  assert.deepEqual(log, ['GET /v1/version -']);
});

test('disk-mode clear deletes the device-token record and nothing else is written', async () => {
  setMemory(false);
  disk.set('device-token', 'disk-tok');
  assert.equal(await clearToken(), undefined);
  assert.equal(disk.has('device-token'), false);
  assert.deepEqual(log, ['delete device-token']);
});

test('the pairing platform comes from the user agent, Android first', async () => {
  const cases: [string, string][] = [
    ['Mozilla/5.0 (Linux; Android 14; Pixel 8)', 'android'],
    ['Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)', 'ios'],
    ['Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)', 'ios'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)', 'web'],
    ['', 'web'],
    ['Mozilla/5.0 (Android 14; iPhone)', 'android'],
  ];
  for (const [ua, platform] of cases) {
    setUserAgent(ua);
    await redeemPairing('code', 'phone');
    assert.equal(lastBody?.platform, platform, `user agent ${JSON.stringify(ua)}`);
  }
});

test('a blank name and a blank pin are sent as null; filled ones pass through', async () => {
  await redeemPairing('code', '', '');
  assert.deepEqual(lastBody, { code: 'code', platform: 'web', name: null, pin: null });
  await redeemPairing('code', 'Kitchen', '4321');
  assert.deepEqual(lastBody, { code: 'code', platform: 'web', name: 'Kitchen', pin: '4321' });
});

test('disk mode: the redeemed token is stored under device-token and is the one authenticate uses', async () => {
  setMemory(false);
  assert.equal(await redeemPairing('code', 'phone'), 'tok-new');
  assert.equal(disk.get('device-token'), 'tok-new');
  log = [];
  assert.equal(await authenticate(undefined), 'tok-new');
  assert.deepEqual(log, ['GET /v1/version Bearer tok-new']);
});

test('a refused pairing code propagates the 401 and saves nothing', async () => {
  setMemory(false);
  disk.set('device-token', 'old');
  answer = () => json(401, { error: 'pairing_expired', detail: {} });
  await assert.rejects(redeemPairing('code', 'phone'), (e: unknown) => e instanceof CoreError && e.status === 401 && e.code === 'pairing_expired');
  assert.equal(disk.get('device-token'), 'old');
  assert.equal(log.some((l) => l.startsWith('put') || l.startsWith('delete')), false);
});

// Reach: App.tsx:100 calls redeemPairing from the pairing screen. In disk mode the
// device is issued before the save; if IndexedDB refuses the write (private
// windows), the token stays live on Core and no client holds it.
test(
  'a pairing whose token cannot be saved surfaces the device id or revokes the new token',
  { todo: 'transport.ts:149-151: saveToken runs after Core issues the device; its failure rejects with no revoke and no device id, leaving the new token live' },
  async () => {
    setMemory(false);
    failPut = true;
    let err: unknown;
    try {
      await redeemPairing('code', 'phone');
    } catch (e) {
      err = e;
    }
    const surfaced = err instanceof Error && err.message.includes('dvc_new');
    const revoked = log.some((l) => l.startsWith('POST /v1/devices/dvc_new/revoke'));
    assert.ok(surfaced || revoked, `save failure left dvc_new live (error: ${err instanceof Error ? err.message : String(err)})`);
  },
);
