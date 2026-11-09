// The connection machine and view freshness (§13; M07, M08).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { canCommand, freshness, initial, next, type Signal } from '../src/data/connection.ts';

const run = (...sigs: Signal[]) => sigs.reduce((s, sig) => next(s, sig, 0), initial(0));

test('first open is live; a fresh-start resync is not announced as "back"', () => {
  assert.equal(run('resync', 'stream_open').conn, 'live');
  assert.equal(run('frame').conn, 'live');
});

test('a drop is reconnecting; coming back is a resync that makes everything read before stale (M08)', () => {
  const live = run('stream_open');
  const lost = next(live, 'stream_lost', 1);
  assert.equal(lost.conn, 'reconnecting');
  const back = next(lost, 'stream_open', 2);
  assert.equal(back.conn, 'resynced');
  assert.ok(back.gen > live.gen);
  assert.equal(next(back, 'settled', 3).conn, 'live');
  assert.ok(next(live, 'resync', 1).gen > live.gen);
});

test('a signed-out client stays signed out', () => {
  const out = run('stream_open', 'unauthorized');
  assert.equal(out.conn, 'unauthenticated');
  assert.equal(next(out, 'stream_open', 5).conn, 'unauthenticated');
  assert.equal(run('self_revoked').conn, 'revoked');
});

test('offline and back', () => {
  const off = run('stream_open', 'offline');
  assert.equal(off.conn, 'offline');
  assert.equal(next(off, 'stream_lost', 1).conn, 'offline');
  assert.equal(next(off, 'online', 1).conn, 'reconnecting');
});

test('commands are sent only on a live connection', () => {
  assert.ok(canCommand('live') && canCommand('resynced'));
  for (const c of ['connecting', 'reconnecting', 'offline', 'unauthenticated', 'revoked'] as const) assert.ok(!canCommand(c), c);
});

test('freshness: current only when read in this generation on a live connection (M07)', () => {
  const live = run('stream_open');
  assert.equal(freshness(live, { gen: live.gen, hasData: true }), 'current');
  const lost = next(live, 'stream_lost', 1);
  assert.equal(freshness(lost, { gen: live.gen, hasData: true }), 'reconnecting');
  const back = next(lost, 'stream_open', 2);
  assert.equal(freshness(back, { gen: live.gen, hasData: true }), 'stale');
  assert.equal(freshness(back, { gen: back.gen, hasData: true }), 'current');
  assert.equal(freshness(back, { gen: back.gen, hasData: true, pending: true }), 'stale');
  assert.equal(freshness(live, { gen: live.gen, hasData: false, error: new Error('x') }), 'unavailable');
  assert.equal(freshness(run('stream_open', 'offline'), { gen: 0, hasData: true }), 'stale');
});
