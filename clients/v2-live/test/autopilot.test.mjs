import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { CHAPTERS, GROUPS, VERBS, familiesCovered } from '../js/autopilot-script.js';

const root = new URL('../', import.meta.url);
const read = (p) => readFileSync(new URL(p, root), 'utf8');
const sources = [...readdirSync(new URL('js/', root), { recursive: true }).filter((f) => f.endsWith('.js') && !f.includes('autopilot')).map((f) => 'js/' + f.replace(/\\/g, '/')), 'sim.js', 'replay-model.js', 'page-model.js']
  .map(read).join('\n');
// Keys are built from parts ('itab-' + id), so a literal match is too strict: every dash separated word of the key has to appear in the source. This catches a typo; the browser check
// (tools/v2_live_autopilot_check.py) is what proves a target resolves on a real screen.
const keyExists = (key) => key.split('-').filter(Boolean).every((w) => w.length < 2 || sources.includes(w));
const isKey = (t) => !/^[[.#]|[\s>,:]/.test(t);
const inMode = (mode) => (x) => !x.on || x.on === mode;

test('chapters: ids are unique, every chapter has a group, a title and a caption in both languages, and steps', () => {
  const ids = CHAPTERS.map((c) => c.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(CHAPTERS.length >= 35);
  for (const c of CHAPTERS) {
    assert.ok(GROUPS[c.group], c.id + ' group');
    for (const pair of [c.t, c.c]) assert.ok(Array.isArray(pair) && pair.length === 2 && pair.every((x) => typeof x === 'string' && x.trim()), c.id + ' text');
    assert.ok(c.c[0].length < 260 && c.c[1].length < 280, c.id + ' caption stays short');
    assert.ok(Array.isArray(c.covers) && c.covers.length, c.id + ' covers');
    assert.ok(c.steps.length, c.id + ' steps');
    assert.ok(!c.on || c.on === 'desktop' || c.on === 'phone', c.id + ' on');
  }
  for (const [g, pair] of Object.entries(GROUPS)) assert.ok(CHAPTERS.some((c) => c.group === g), g + ' has a chapter');
});

test('steps: known verbs, a target where the verb needs one, a pause that is a number', () => {
  for (const c of CHAPTERS) for (const [k, s] of c.steps.entries()) {
    const at = c.id + ' step ' + k;
    assert.ok(VERBS.includes(s.do), at + ' verb ' + s.do);
    if (['click', 'hover', 'type', 'clear', 'select'].includes(s.do)) assert.ok(typeof s.target === 'string' && s.target, at + ' target');
    if (s.do === 'nav') assert.match(s.arg, /^#\/\w+/, at);
    if (['type', 'press', 'select'].includes(s.do)) assert.ok(typeof s.arg === 'string' && s.arg, at + ' arg');
    if (s.ms != null) assert.ok(Number.isFinite(s.ms) && s.ms >= 0 && s.ms <= 5000, at + ' ms');
    assert.ok(!s.on || s.on === 'desktop' || s.on === 'phone', at + ' on');
  }
});

test('coverage: every SPEC row family has a chapter that shows it (L is the not decided list)', () => {
  const spec = read('SPEC.md');
  const families = new Set([...spec.matchAll(/^\| ([A-Z]+)\d+ \|/gm)].map((m) => m[1]));
  families.delete('L');
  const covered = familiesCovered();
  assert.deepEqual([...families].filter((f) => !covered.has(f)), []);
  assert.deepEqual([...covered].filter((f) => !families.has(f)), [], 'a covers entry names a family the SPEC does not have');
});

for (const mode of ['desktop', 'phone']) {
  test('every non optional data-key target exists in the source, on a ' + mode, () => {
    const missing = [];
    for (const c of CHAPTERS.filter(inMode(mode))) for (const s of c.steps.filter(inMode(mode))) {
      if (s.optional || !s.target || s.target === 'document' || !isKey(s.target)) continue;
      if (!keyExists(s.target.replace(/\*$/, ''))) missing.push(c.id + ': ' + s.target);
    }
    assert.deepEqual(missing, []);
  });

  test('no chapter is empty on a ' + mode + ': each one that is in the tour has a step that runs there', () => {
    for (const c of CHAPTERS.filter(inMode(mode))) assert.ok(c.steps.some((s) => inMode(mode)(s) && !s.optional), c.id);
  });
}

test('a phone has no hover target and no dock: those chapters and steps are desktop only', () => {
  for (const c of CHAPTERS.filter((x) => x.on !== 'desktop')) for (const s of c.steps.filter(inMode('phone'))) {
    assert.ok(s.target !== 'chat-in-dock' && !String(s.target).startsWith('.am-') && !String(s.target).startsWith('vs-'), c.id + ' ' + s.target);
  }
});

test('the tour ends where it began: it never leaves an effect it cannot undo', () => {
  const lastSteps = CHAPTERS.flatMap((c) => c.steps);
  assert.ok(!lastSteps.some((s) => s.do === 'click' && /danger|reject/.test(String(s.target))), 'work-approve approves only');
  const sim = CHAPTERS.find((c) => c.id === 'sim');
  assert.ok(sim.steps.some((s) => s.nth === 4), 'the sim chapter ends with Reset');
});
