import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createSim } from '../sim.js';
import { termModel, TERM_SCREENS, trunc, fit, wrap } from '../term.js';

test('every screen fits its columns at every width, unicode and ascii', () => {
  const s = createSim(); s.advance(400000);
  for (const cols of [30, 40, 60, 80, 120, 200]) for (const ascii of [false, true]) for (const sc of TERM_SCREENS) {
    const m = termModel(s, { cols, ascii, screen: sc.id, sel: 0 });
    assert.ok(m.lines.length > 5, sc.id);
    for (const l of m.lines) assert.ok(l.t.length <= m.cols, sc.id + ' ' + cols + ': ' + l.t.length + ' ' + l.t);
  }
});

test('the first line says SIMULATED and that no Core is connected', () => {
  const m = termModel(createSim(), { cols: 80, screen: 'now' });
  assert.match(m.lines[0].t, /SIMULATED/); assert.match(m.lines[0].t, /no Core connected/);
});

test('the terminal shows the same state sentence, spine and decisions as the app model', () => {
  const s = createSim();
  const m = termModel(s, { cols: 100, screen: 'now' });
  const text = m.lines.map((l) => l.t).join('\n');
  assert.ok(text.includes(s.sentence()));
  assert.ok(text.includes('Plan v1 for "Search provenance"'));
  assert.ok(text.includes('\u2713\u2713\u25c6\u25cb\u25cb\u25cb Approval'));
  assert.ok(m.items.some((i) => i.ref === 'a-1'));
});

test('helpers', () => {
  assert.equal(trunc('abcdef', 4), 'abc\u2026');
  assert.equal(fit('left', 'right', 20).length, 20);
  assert.ok(wrap('one two three four five', 9).every((l) => l.length <= 9));
});
