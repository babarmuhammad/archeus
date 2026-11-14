import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { sender, CoreError } from '../src/api/transport.ts';

const g = globalThis as Record<string, unknown>;
const realFetch = globalThis.fetch;

interface Call {
  url: string;
  init: RequestInit;
}

let calls: Call[] = [];

function fakeFetch(reply: () => Response) {
  calls = [];
  g.fetch = (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return Promise.resolve(reply());
  };
}

async function failure(p: Promise<unknown>): Promise<CoreError> {
  try {
    await p;
  } catch (e) {
    if (e instanceof CoreError) return e;
    throw e;
  }
  assert.fail('expected a CoreError');
}

afterEach(() => {
  g.fetch = realFetch;
});

test('authorization header only when the sender has a token', async () => {
  fakeFetch(() => new Response('{}', { status: 200 }));
  await sender()('GET', '/v1/a');
  await sender('t1')('GET', '/v1/a');
  const [anon, authed] = calls.map((c) => c.init.headers as Record<string, string>);
  assert.equal(anon.Authorization, undefined);
  assert.equal(authed.Authorization, 'Bearer t1');
});

test('content type and body only when there is a body', async () => {
  fakeFetch(() => new Response('{}', { status: 200 }));
  await sender()('GET', '/v1/a');
  await sender()('POST', '/v1/a', { a: 1 });
  const [get, post] = calls;
  assert.equal((get.init.headers as Record<string, string>)['Content-Type'], undefined);
  assert.equal(get.init.body, undefined);
  assert.equal((post.init.headers as Record<string, string>)['Content-Type'], 'application/json');
});

test('body is sent as one JSON string', async () => {
  fakeFetch(() => new Response('{}', { status: 200 }));
  await sender()('POST', '/v1/x', { a: 1 });
  assert.equal(calls[0].init.body, '{"a":1}');
  assert.equal(calls[0].init.method, 'POST');
  assert.equal(calls[0].url, '/v1/x');
});

test('a rejected fetch is a network CoreError', async () => {
  g.fetch = () => Promise.reject(new TypeError('connection refused'));
  const err = await failure(sender()('GET', '/v1/a'));
  assert.equal(err.status, 0);
  assert.equal(err.code, 'network');
  assert.deepEqual(err.detail, {});
});

test('the seq header is reported only when present and onSeq is given', async () => {
  const seen: [string, number][] = [];
  const onSeq = (p: string, s: number) => {
    seen.push([p, s]);
  };
  fakeFetch(() => new Response('{}', { status: 200, headers: { 'X-Archeus-Seq': '42' } }));
  await sender(undefined, onSeq)('GET', '/v1/a');
  fakeFetch(() => new Response('{}', { status: 200 }));
  await sender(undefined, onSeq)('GET', '/v1/b');
  fakeFetch(() => new Response('{}', { status: 200, headers: { 'X-Archeus-Seq': '43' } }));
  await sender()('GET', '/v1/c');
  assert.deepEqual(seen, [['/v1/a', 42]]);
});

test('an OK reply whose body is not JSON is a network error, never data', async () => {
  fakeFetch(() => new Response('{"partial":', { status: 200 }));
  const err = await failure(sender()('GET', '/v1/a'));
  assert.equal(err.status, 0);
  assert.equal(err.code, 'network');
  assert.deepEqual(err.detail, {});
});

test('a non-OK reply whose body is not JSON is invalid_response', async () => {
  fakeFetch(() => new Response('<html>502 Bad Gateway</html>', { status: 502 }));
  const err = await failure(sender()('GET', '/v1/a'));
  assert.equal(err.status, 502);
  assert.equal(err.code, 'invalid_response');
  assert.deepEqual(err.detail, {});
});

test('an error body maps its code and detail, and a missing detail becomes {}', async () => {
  fakeFetch(() => new Response(JSON.stringify({ error: 'forbidden', detail: { x: 1 } }), { status: 403 }));
  const withDetail = await failure(sender()('GET', '/v1/a'));
  assert.equal(withDetail.status, 403);
  assert.equal(withDetail.code, 'forbidden');
  assert.deepEqual(withDetail.detail, { x: 1 });

  fakeFetch(() => new Response(JSON.stringify({ error: 'not_found' }), { status: 404 }));
  const noDetail = await failure(sender()('GET', '/v1/a'));
  assert.equal(noDetail.status, 404);
  assert.equal(noDetail.code, 'not_found');
  assert.deepEqual(noDetail.detail, {});
});

test('an error body without an error key yields an undefined code (typed contract limit)', async () => {
  fakeFetch(() => new Response(JSON.stringify({ message: 'nope' }), { status: 400 }));
  const err = await failure(sender()('GET', '/v1/a'));
  assert.equal(err.status, 400);
  assert.equal(err.code, undefined);
  assert.deepEqual(err.detail, {});
});
