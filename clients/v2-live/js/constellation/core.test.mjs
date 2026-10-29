import test from 'node:test';
import assert from 'node:assert/strict';
import {corePaths, coreMarkup, coreTier, coreState, arcPath, CORE_TIERS} from './nodeart.js';

const count = (R, opts) => corePaths(R, 1.75, opts).length;
test('coreState: stopped, then needs you, then working, then calm', () => {
  assert.equal(coreState({stopped: true, needsYou: true, running: true}), 'stopped');
  assert.equal(coreState({needsYou: true, running: true}), 'needs-you');
  assert.equal(coreState({running: true}), 'working');
  assert.equal(coreState({}), 'calm');
  assert.equal(coreState(), 'calm');
});
test('coreTier: boundaries at 71, 36 and 18 px of star radius, 4 px of hysteresis', () => {
  assert.deepEqual([200, 71, 70, 36, 35, 18, 17, 5].map(v => coreTier(v)), ['full', 'full', 'standard', 'standard', 'mini', 'mini', 'micro', 'micro']);
  assert.equal(coreTier(68, 'full'), 'full'); assert.equal(coreTier(66, 'full'), 'standard');
  assert.equal(coreTier(73, 'standard'), 'standard'); assert.equal(coreTier(76, 'standard'), 'full');
  assert.equal(coreTier(20, 'micro'), 'micro'); assert.equal(coreTier(23, 'micro'), 'mini');
  assert.equal(coreTier(16, 'mini'), 'mini'); assert.equal(coreTier(13, 'mini'), 'micro');
  assert.deepEqual(CORE_TIERS, ['full', 'standard', 'mini', 'micro']);
});
test('arcPath: both ends sit on the circle, the large flag follows the sweep', () => {
  for (const [from, to] of [[150, 355], [0, 90], [300, 20]]) {
    const d = arcPath(50, from, to), [x0, y0, x1, y1] = d.match(/-?\d+(\.\d+)?/g).filter((_, i) => [0, 1, 7, 8].includes(i)).map(Number);
    assert.ok(Math.abs(Math.hypot(x0, y0) - 50) < .2 && Math.abs(Math.hypot(x1, y1) - 50) < .2, d);
  }
  assert.ok(arcPath(50, 150, 355).includes(' 0 1 1 ') && arcPath(50, 0, 90).includes(' 0 0 1 '));
});
test('element budget: at most 20 in any state and tier, and the calm tiers are 8, 7, 6 and 5', () => {
  for (const tier of CORE_TIERS) for (const stopped of [false, true]) for (const needsYou of [false, true]) for (const running of [false, true]) {
    const n = count(50, {tier, stopped, needsYou, running});
    assert.ok(n <= 20, `${tier} ${stopped}${needsYou}${running}: ${n}`);
  }
  assert.deepEqual(CORE_TIERS.map(tier => count(50, {tier})), [8, 7, 6, 5]);
  assert.equal(count(50, {tier: 'full', running: true, needsYou: true}) <= 19, true);
});
test('state marks: working adds the sector, the blue arc and dot, a ring and a travelling dot; needs you one thread and a diamond; stopped slack threads and a cross', () => {
  const cls = o => corePaths(50, 1.75, o).map(p => p.c.split(' ')[0]);
  assert.ok(['am-core-sector', 'am-core-state-arc', 'am-core-state-dot', 'am-ring', 'am-travel'].every(c => cls({running: true}).includes(c)));
  assert.ok(['am-core-needs', 'am-diamond'].every(c => cls({needsYou: true}).includes(c)) && !cls({needsYou: true}).includes('am-ring'));
  const stop = cls({stopped: true, running: true, needsYou: true});
  assert.ok(stop.includes('am-core-cross') && !stop.includes('am-core-sector') && !stop.includes('am-core-needs') && !stop.includes('am-core-centre'));
  assert.ok(!cls({}).some(c => ['am-core-sector', 'am-core-needs', 'am-core-cross', 'am-ring'].includes(c)));
});
test('geometry stays inside 1.12 L (the amber diamond may reach 1.15 L) and the web is a few long paths', () => {
  const L = 50 * 1.75, big = Math.max(...corePaths(50, 1.75, {tier: 'full', needsYou: true}).filter(p => p.d && !p.c.includes('arc') && !p.c.includes('chords')).flatMap(p => (p.d.match(/-?\d+(\.\d+)?,-?\d+(\.\d+)?/g) || []).map(s => Math.hypot(...s.split(',').map(Number)))));
  assert.ok(big <= 1.15 * L, big / L);
  const web = corePaths(50, 1.75, {tier: 'full'}).filter(p => p.c.startsWith('am-core-chords'));
  assert.ok(web.length <= 2 && web.every(p => (p.d.match(/M/g) || []).length >= 60));
});
test('the markup string is the same art (used by the mission graph)', () => {
  const m = coreMarkup(26, 1.7, {tier: 'standard'});
  assert.ok(m.includes('am-core-thread') && m.includes('am-core-dot') && m.includes('am-core-chords') && m.includes('<circle'));
});
