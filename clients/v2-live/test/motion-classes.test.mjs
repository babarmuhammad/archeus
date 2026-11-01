import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { CLASSES, OUT, AMBIENT, MOMENTS, classOf, ambient } from '../js/motion-model.js';
import { MOTION } from '../js/constellation/map.js';

const root = fileURLToPath(new URL('..', import.meta.url));
const read = (p) => readFileSync(root + p, 'utf8');
const list = (dir, ext) => readdirSync(root + dir).filter((f) => f.endsWith(ext)).map((f) => dir + '/' + f);
const css = [...list('css', '.css'), ...list('js/constellation', '.css')];
const js = [...list('js', '.js'), ...list('js/constellation', '.js')];
const tokens = Object.fromEntries([...read('css/tokens.css').matchAll(/--dur-([a-z]+):\s*(\d+)ms/g)].map((m) => [m[1], +m[2]]));

test('the class table is the A55 table', () => {
  assert.deepEqual(Object.entries(CLASSES).map(([k, v]) => [k, v.ms, v.max ?? null]), [
    ['instant', 0, null], ['quick', 160, null], ['standard', 240, null], ['layer', 200, 280], ['travel', 600, null], ['orbit', 900, null], ['breath', 6000, null]
  ]);
  assert.equal(OUT, 100);
});

test('classOf names a duration, takes the layer range, and refuses a number that fits no class', () => {
  assert.deepEqual([0, 100, 160, 200, 220, 280, 240, 600, 900, 6000].map(classOf), ['instant', 'out', 'quick', 'layer', 'layer', 'layer', 'standard', 'travel', 'orbit', 'breath']);
  for (const ms of [80, 120, 140, 180, 281, 1200, 2600]) assert.equal(classOf(ms), null, String(ms));
});

test('tokens.css carries every class as --dur-<class>, with the same number', () => {
  for (const [name, c] of Object.entries(CLASSES)) assert.equal(tokens[name], c.ms, name);
  assert.equal(tokens.out, OUT);
  assert.equal(tokens.ring, AMBIENT.ring.min);
  assert.deepEqual(Object.keys(tokens).sort(), [...Object.keys(CLASSES), 'out', 'ring'].sort());
});

test('no transition or animation in the css carries a magic duration', () => {
  const found = [];
  for (const f of css) {
    if (f === 'css/tokens.css') continue;
    for (const [, decl] of read(f).matchAll(/(?:transition|animation)(?:-duration)?\s*:([^;}]*)/g)) {
      let rest = decl.replace(/var\(--(?:dp|tp|dd|td),[^)]*\)/g, '');
      for (const [whole, name, ms] of [...rest.matchAll(/var\(--dur-([a-z]+),\s*(\d+)ms\)/g)]) {
        assert.equal(+ms, tokens[name], `${f}: the fallback of --dur-${name} is ${ms}`);
        rest = rest.replace(whole, '');
      }
      for (const m of rest.matchAll(/(?<![\w.-])(\d+(?:\.\d+)?)(ms|s)\b/g)) if (m[0] !== '40ms') found.push(f + ': ' + decl.trim());
    }
  }
  assert.deepEqual(found, []);
});

test('every duration passed to the Web Animations API is a class', () => {
  const bad = [];
  for (const f of js) for (const m of read(f).matchAll(/duration:\s*(\d+)/g)) if (classOf(+m[1]) === null) bad.push(f + ': ' + m[0]);
  assert.deepEqual(bad, []);
  for (const [k, ms] of Object.entries(MOTION)) assert.notEqual(classOf(ms), null, k);
  assert.equal(MOTION.breath, CLASSES.breath.ms);
  assert.equal(MOTION.travel, CLASSES.travel.ms);
});

test('only the named ambient loops repeat, each one cycle of 3.6 s or more', () => {
  const loops = new Set();
  for (const f of css) for (const [, decl] of read(f).matchAll(/animation\s*:([^;}]*\binfinite\b[^;}]*)/g)) loops.add(decl.trim().split(/\s+/)[0]);
  assert.deepEqual([...loops].sort(), ['am-drift', 'am-ring', 'am-travel', 'core-breath', 'wg-soft']);
  for (const a of Object.values(AMBIENT)) assert.ok(a.min >= 3600 && a.max >= a.min);
});

test('thinking and scrolling do not move: no working dots loop, no smooth scroll', () => {
  const chat = read('css/chat.css');
  assert.ok(!/\bcp-work\b/.test(chat), 'the cp-work keyframe is gone');
  assert.ok(!/\.cp-dots[^{]*\{[^}]*animation/.test(chat), 'the dots carry no animation');
  for (const f of [...js, ...css]) assert.ok(!/behavior:\s*['"]?smooth/.test(read(f)), f);
});

test('the still moments are written down: arriving, thinking, failing, reconnecting and scrolling, plus the rest of A55 section 2', () => {
  for (const m of ['arriving', 'disappearing', 'thinking', 'failing', 'quiet', 'reconnecting', 'scrolling']) {
    assert.ok(MOMENTS[m] && MOMENTS[m].rule, m);
    for (const k of MOMENTS[m].pause) assert.ok(k in AMBIENT, m + ' pauses ' + k);
  }
  assert.deepEqual(MOMENTS.failing.moves, ['cross-fade']);
  for (const m of ['thinking', 'quiet', 'reconnecting', 'scrolling']) assert.deepEqual(MOMENTS[m].moves, [], m);
});

test('ambient: off by default, drift, ring and travel for a playing simulation, the breath for a fresh read of running work', () => {
  assert.deepEqual(ambient(), { breath: false, drift: false, ring: false, travel: false });
  assert.deepEqual(ambient({ playing: true }), { breath: false, drift: true, ring: true, travel: true });
  assert.deepEqual(ambient({ live: true }), { breath: true, drift: false, ring: false, travel: false });
});

test('ambient: Quiet, a hidden tab and the emergency stop switch all of it off', () => {
  const busy = { playing: true, live: true };
  const off = { breath: false, drift: false, ring: false, travel: false };
  assert.deepEqual(ambient({ ...busy, full: false }), off);
  assert.deepEqual(ambient({ ...busy, visible: false }), off);
  assert.deepEqual(ambient({ ...busy, stopped: true }), off);
});

test('ambient: a still moment pauses exactly what it lists', () => {
  const busy = { playing: true, live: true };
  assert.deepEqual(ambient({ ...busy, moments: ['reconnecting'] }), { breath: false, drift: false, ring: false, travel: false });
  assert.deepEqual(ambient({ ...busy, moments: ['quiet'] }), { breath: false, drift: true, ring: true, travel: false });
  for (const m of ['arriving', 'disappearing', 'thinking', 'failing', 'scrolling', 'no such moment']) assert.deepEqual(ambient({ ...busy, moments: [m] }), { breath: true, drift: true, ring: true, travel: true }, m);
});
