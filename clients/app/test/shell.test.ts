// Navigation, commands, announcements, motion and the no-shadow-system scans
// (§4.2, §13.3, §17, §18, §19; M14, M15, M17, M18, M19, M29).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { limiter } from '../src/a11y/announce.ts';
import { decideBody, explain, keyAfter, motionMode } from '../src/data/commands.ts';
import { DESTINATIONS, INSPECTOR_TABS, href, parse, phoneTabs } from '../src/nav/destinations.ts';

test('the navigation table: unique ids and shortcuts, and routes round-trip', () => {
  assert.equal(new Set(DESTINATIONS.map((d) => d.id)).size, DESTINATIONS.length);
  assert.equal(new Set(DESTINATIONS.map((d) => d.key)).size, DESTINATIONS.length);
  for (const r of [{ view: 'now' as const }, { view: 'world' as const, project: 'prj_1' }, { view: 'work' as const, project: 'prj_1' }, { view: 'control' as const, section: 'devices' }])
    assert.deepEqual(parse(href(r)), r);
  assert.deepEqual(parse('#/o/mission/msn_1/plan'), { view: 'object', kind: 'mission', id: 'msn_1', tab: 'plan', under: 'now' });
  assert.deepEqual(parse('#launch=abc'), { view: 'now' }); // a bootstrap is never a route
  assert.deepEqual(parse('#pair=abc'), { view: 'now' });
});

test('a phone always reaches Attention and Now from its tab bar (M18)', () => {
  const tabs = phoneTabs().map((d) => d.id);
  assert.ok(tabs.includes('attention') && tabs.includes('now'));
  assert.ok(tabs.length <= 4);
});

test('the mission inspector has its tabs in the gate order', () => {
  assert.deepEqual(INSPECTOR_TABS.mission, ['outcome', 'plan', 'now', 'evidence', 'why', 'timeline', 'relations']);
});

test('a decision echoes the displayed action hash and version (M14)', () => {
  const b = decideBody({ action_hash: 'ab'.repeat(32), version: 3 }, 'approve', 'k1', { step_up: '123456' });
  assert.deepEqual(b, { decision: 'approve', action_hash: 'ab'.repeat(32), expected_version: 3, idempotency_key: 'k1', step_up: '123456' });
});

test('after a network failure the retry reuses its key; after an answer it is new (M15)', () => {
  let n = 0;
  const fresh = () => `k${++n}`;
  assert.equal(keyAfter('k0', 'network', fresh), 'k0');
  assert.equal(keyAfter('k0', 'ok', fresh), 'k1');
  assert.equal(keyAfter('k0', 'refused', fresh), 'k2');
});

test('refusals are Core’s words', () => {
  assert.match(explain({ status: 403, code: 'scope_required', detail: { scope: 'approve' } }), /approve/);
  assert.match(explain({ status: 409, code: 'queued_intent_refused', detail: {} }), /late/);
  assert.match(explain({ status: 422, code: 'guard_failed', detail: { reason: 'plan not newer' } }), /plan not newer/);
});

test('the polite announcer says at most one thing per 5 s, the latest (M19)', () => {
  const l = limiter(5000);
  assert.equal(l.offer('a', 0), 'a');
  assert.equal(l.offer('b', 1000), null);
  assert.equal(l.offer('c', 2000), null);
  assert.equal(l.flush(4000), null);
  assert.equal(l.flush(5000), 'c');
  assert.equal(l.flush(9000), null);
});

test('reduced motion follows the system or the setting (M17)', () => {
  assert.equal(motionMode(false, 'system'), 'full');
  assert.equal(motionMode(true, 'system'), 'reduced');
  assert.equal(motionMode(false, 'reduced'), 'reduced');
});

const SRC = fileURLToPath(new URL('../src', import.meta.url));
function sources(dir = SRC): [string, string][] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? sources(p) : /\.tsx?$/.test(n) ? [[p, readFileSync(p, 'utf8')] as [string, string]] : [];
  });
}

test('the client holds no shadow policy, grammar or session logic (§19, M29)', () => {
  for (const [path, text] of sources()) {
    if (path.includes('generated')) continue;
    const code = text.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
    // no verb parsing of what the user typed: text goes to Core's grammar
    assert.ok(!/\.(startsWith|match|test)\(\s*['"`/^]*\^?(pause|resume|approve|reject|stop)\b/i.test(code), path);
    // no policy evaluation: decisions are displayed, never computed
    assert.ok(!/(decision|decide)\s*===?\s*['"]ALLOW_WITHIN_BOUNDARY/.test(code), path);
  }
  // a session row wears the session's own state, never its mission's (M10)
  const control = readFileSync(join(SRC, 'surfaces', 'Control.tsx'), 'utf8');
  assert.ok(!/machine="mission" state=\{(x|y)\.state\}/.test(control));
  assert.ok((control.match(/machine="session"/g) ?? []).length >= 3);
  // the connection code never creates or resumes a session (P15 M13)
  for (const f of ['data/connection.ts', 'data/cache.ts', 'api/stream.ts', 'api/transport.ts'])
    assert.ok(!readFileSync(join(SRC, f), 'utf8').includes('/v1/sessions'), f);
});
