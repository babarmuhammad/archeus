// P19.5 R7: the mark, its orbit as Archeus's presence, the favicon and the
// operations strip (ADR-0027 §1-3, rulebook §6 O-1, §8, §21 A-07).
// Mutation-verified by tools/mutate_p19_5.py (N154 onward).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { MOTIONS } from '../src/state/motion.ts';
import { DARK, MOTION } from '../src/state/tokens.ts';
import { Timeline } from '../src/state/timeline.ts';
import { staleBy } from '../src/data/invalidation.ts';
import { MARK, ORBIT_EVERY_MS, Orbit, attemptIds, favicon, presence, runningMissions } from '../src/state/orbit.ts';

const src = (p: string) => readFileSync(new URL(p, import.meta.url), 'utf8');
const frame = (id: number | undefined, event = 'execution.progress', kind = 'execution') => ({
  id,
  event,
  data: { subject: { kind, id: 'exe_1' } },
});

function rig(reduced = false) {
  let now = 0;
  const flags = { reduced };
  const tl = new Timeline();
  const o = new Orbit(tl, { now: () => now, reduced: () => flags.reduced });
  let heard = 0;
  o.subscribe(() => heard++);
  return { o, tl, flags, tick: (ms: number) => void (now += ms), now: () => now, heard: () => heard };
}

test('the orbit is a built CSS motion with the approved budget', () => {
  const m = MOTIONS['presence-orbit'];
  assert.equal(m.status, 'built');
  assert.equal(m.runs_on, 'css');
  assert.deepEqual([...(m.css ?? [])], ['orbit-turn', 'orbit-counter']);
  assert.equal(m.max_ms, 900);
  assert.equal(MOTION.orbit, 900, 'dur-orbit (rulebook §38)');
  assert.equal(m.easing, 'ease-in-out');
  assert.equal(m.cap, 1);
  assert.equal(ORBIT_EVERY_MS, 5000);
  assert.deepEqual([...m.surfaces], ['shell']);
});

test('presence: hollow when not connected, then needs you, then working, then idle', () => {
  const run = [{ state: 'RUNNING' }];
  assert.equal(presence(false, 3, run), 'disconnected');
  assert.equal(presence(true, 1, run), 'attention', 'attention outranks active work (rulebook §7.1)');
  assert.equal(presence(true, 0, run), 'active');
  assert.equal(presence(true, 0, []), 'idle');
  for (const s of ['STARTING', 'INTENT', 'HANDING_OFF']) assert.equal(presence(true, 0, [{ state: s }]), 'active', s);
  for (const s of ['PAUSED', 'AWAITING_APPROVAL', 'PAUSING', 'STOPPING'])
    assert.equal(presence(true, 0, [{ state: s }]), 'idle', `${s} is live work that is not running`);
  // G8: an own call in flight is live work that never animates, even with a running-looking state
  assert.equal(presence(true, 0, [{ kind: 'own_call', state: 'RUNNING' }]), 'idle');
});

test('the strip counts missions with an attempt running, each once', () => {
  assert.equal(
    runningMissions([
      { state: 'RUNNING', mission_id: 'm1' },
      { state: 'STARTING', mission_id: 'm1' },
      { state: 'RUNNING', mission_id: 'm2' },
      { state: 'PAUSED', mission_id: 'm3' },
      { kind: 'own_call', state: 'RUNNING', mission_id: 'm4' },
    ]),
    2,
  );
  assert.equal(runningMissions([]), 0);
});

test('one turn per batch of execution.* frames, at most once per 5 s', () => {
  const r = rig();
  r.o.frame(frame(10));
  assert.equal(r.o.current(), 10);
  assert.equal(r.heard(), 1);
  assert.deepEqual([...r.tl.progress('presence-orbit', r.now()).values()], [0], 'a turn starts at 0');
  r.tick(450);
  assert.deepEqual([...r.tl.progress('presence-orbit', r.now()).values()], [0.5], 'half way at 450 ms');
  r.tick(450);
  assert.equal(r.tl.progress('presence-orbit', r.now()).size, 0, 'gone after 900 ms: parked');
  r.o.frame(frame(11));
  assert.equal(r.o.current(), 10, 'inside 5 s: no second turn');
  r.tick(ORBIT_EVERY_MS - 900);
  r.o.frame(frame(12));
  assert.equal(r.o.current(), 12, 'after 5 s the next batch turns');
  assert.equal(r.heard(), 2);
});

test('nothing presented turns again; nothing but an execution frame with a seq turns at all', () => {
  const r = rig();
  r.o.frame(frame(10));
  r.tick(10_000);
  r.o.frame(frame(10));
  r.o.frame(frame(9));
  assert.equal(r.o.current(), 10, 'the same or an older event: no turn');
  r.o.frame(frame(undefined));
  r.o.frame(frame(20, 'mission.state_changed', 'mission'));
  r.o.frame(frame(21, 'execution.progress', 'task'));
  r.o.frame({ id: 22, event: 'resync', data: undefined });
  assert.equal(r.o.current(), 10);
  assert.equal(r.heard(), 1);
});

test('under reduced motion no turn is drawn and the event still counts as presented', () => {
  const r = rig(true);
  r.o.frame(frame(10));
  assert.equal(r.o.current(), 0);
  assert.equal(r.tl.progress('presence-orbit', r.now()).size, 0);
  r.flags.reduced = false;
  r.tick(10_000);
  r.o.frame(frame(10));
  assert.equal(r.o.current(), 0, 'switching reduced motion off replays nothing');
});

test('the favicon is the mark on the dark tile, its node in the presence', () => {
  const svg = (p: Parameters<typeof favicon>[0]) => decodeURIComponent(favicon(p, DARK).replace('data:image/svg+xml,', ''));
  const node = (s: string) => s.match(/<circle [^>]*>/)![0];
  assert.ok(favicon('idle', DARK).startsWith('data:image/svg+xml,'));
  const idle = svg('idle');
  assert.ok(idle.includes(`<rect width="32" height="32" rx="7" fill="${DARK.bg}"/>`), 'the dark tile');
  for (const d of MARK.letter) assert.ok(idle.includes(`d="${d}"`), 'the letter');
  assert.ok(idle.includes(`rx="${MARK.rx}" ry="${MARK.ry}"`), 'the orbit');
  assert.ok(node(idle).includes(`fill="${DARK.text}"`), 'idle: neutral');
  assert.ok(node(svg('active')).includes(`fill="${DARK['state.active']}"`), 'working: active');
  assert.ok(node(svg('attention')).includes(`fill="${DARK['state.attention']}"`), 'needs you: attention');
  const hollow = node(svg('disconnected'));
  assert.ok(hollow.includes(`fill="${DARK.bg}"`) && hollow.includes(`stroke="${DARK.text}"`), 'disconnected: hollow');
  const a = (MARK.at * Math.PI) / 180;
  assert.ok(node(idle).includes(`cx="${(MARK.cx + MARK.rx * Math.cos(a)).toFixed(2)}" cy="${(MARK.cy + MARK.ry * Math.sin(a)).toFixed(2)}"`), 'the node sits on the orbit');
  assert.ok(!/animat/i.test(idle), 'the favicon is still');
  assert.equal(new Set((['idle', 'active', 'attention', 'disconnected'] as const).map((p) => favicon(p, DARK))).size, 4);
});

test('the mark is the site\'s glyph, the same figure', () => {
  const site = src('../../../www/components/site/Mark.tsx');
  for (const d of MARK.letter) assert.ok(site.includes(`d="${d}"`), d);
  assert.ok(site.includes(`rotate(${MARK.tilt} ${MARK.cx} ${MARK.cy})`));
  assert.ok(site.includes(`rx="${MARK.rx}"`) && site.includes(`ry="${MARK.ry}"`));
});

test('the turn and its counter-turn: both transform-only, once, on the orbit token', () => {
  const css = src('../src/styles/app.css');
  assert.match(css, /\.orbit-turn \{\s*animation: orbit-turn var\(--dur-orbit\) ease-in-out 1;/);
  assert.match(css, /\.orbit-counter \{\s*animation: orbit-counter var\(--dur-orbit\) ease-in-out 1;/);
  assert.match(css, /@keyframes orbit-turn \{\s*from \{\s*transform: rotate\(0deg\);\s*\}\s*to \{\s*transform: rotate\(360deg\);/);
  assert.match(css, /@keyframes orbit-counter \{\s*from \{\s*transform: rotate\(0deg\);\s*\}\s*to \{\s*transform: rotate\(-360deg\);/);
  assert.match(src('../src/styles/tokens.css'), /--dur-orbit: 900ms;/);
});

test('the mark lives in the shell alone: the header and the boot screen', () => {
  const app = src('../src/App.tsx');
  assert.equal(app.match(/<Mark\b/g)?.length, 2);
  assert.match(app, /<main className="notice boot">\s*<Mark \/>\s*<p>Connecting to Archeus…<\/p>/);
  assert.match(app, /<span className="brand">\s*<Mark presence=\{p\} \/>\s*Archeus/);
  const dir = new URL('../src/', import.meta.url);
  const files = readdirSync(dir, { recursive: true }).map(String).filter((f) => /\.tsx?$/.test(f) && !f.endsWith('App.tsx'));
  for (const f of files) assert.ok(!/<Mark\b|className="mark"/.test(src('../src/' + f.replaceAll('\\', '/'))), `${f} draws the mark`);
});

test('the strip is a navigation landmark whose numbers link to their lists', () => {
  const app = src('../src/App.tsx');
  assert.match(app, /<nav className="strip" aria-label="Operations">/);
  assert.match(app, /href="#\/now" data-strip="running"/);
  assert.match(app, /href="#\/attention" data-strip="needs"/);
  assert.match(app, /href="#\/control\/devices" data-strip="clients"/);
  assert.match(app, /<span className="sr" role="status" data-strip-said>/);
  assert.match(app, /const STRIP_SAYS_EVERY_MS = 30_000;/);
});

test('the app icons are the tile mark, not the Attention diamond', () => {
  // tools/make_icon.py writes both sites' icons from one master
  for (const n of ['icon-192.png', 'icon-512.png'])
    assert.deepEqual(readFileSync(new URL('../public/assets/' + n, import.meta.url)), readFileSync(new URL('../../../www/public/' + n, import.meta.url)), n);
  assert.match(src('../index.html'), /<link rel="icon" href="\/assets\/icon-192.png" \/>/);
});

test('an execution frame makes /v1/status stale: its live work moved', () => {
  const stale = staleBy({ event: 'execution.state_changed', data: { subject: { kind: 'execution', id: 'exe_1' }, scope: {} } });
  assert.ok(stale('/v1/status'));
  assert.ok(stale('/v1/status?project=prj_1'));
});

test('the live map lights attempts only: an own call is never a node (G8)', () => {
  const live = [{ id: 'exe_1', kind: 'execution', state: 'RUNNING' }, { id: 'own_1', kind: 'own_call', state: null }];
  assert.deepEqual(attemptIds(live), ['exe_1']);
  assert.deepEqual(attemptIds([]), []);
  assert.deepEqual(attemptIds(undefined), []);      // a status not read yet lights nothing
});
