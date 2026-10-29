import test from 'node:test';
import assert from 'node:assert/strict';
import {pickGrid, layoutTerritories, levelOf, edgePoint, stateOf, describeProject, preserveFocus} from './territories.js';

const overlap = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
const INSET = {top: 150, right: 24, bottom: 80, left: 24};

test('cramped Details scenes use the scrollable project grid instead of overflowing minimum cells', () => {
  for (const count of [30, 100]) for (const width of [180, 240, 360]) {
    const layout = layoutTerritories(count, width, 480, INSET);
    if (layout.overflow) assert.deepEqual(layout.cells, []);
    else for (const cell of layout.cells) {
      assert.ok(cell.w >= 24 && cell.h >= 24);
      assert.ok(cell.x >= INSET.left && cell.x + cell.w <= width - INSET.right + .01);
      assert.ok(cell.y >= INSET.top && cell.y + cell.h <= 480 - INSET.bottom + .01);
    }
  }
  assert.equal(layoutTerritories(30, 180, 480, INSET).overflow, true);
  assert.equal(layoutTerritories(100, 360, 480, INSET).overflow, true);
});

test('every count from 1 to 100 gets a cell each, none overlapping, none on the core', () => {
  for (const n of [1, 2, 3, 5, 12, 28, 60, 100]) {
    const {cells, core} = layoutTerritories(n, 1248, 800, INSET);
    assert.ok(cells.length >= n, `${n} projects need ${n} cells, got ${cells.length}`);
    for (let i = 0; i < cells.length; i++) {
      assert.ok(cells[i].x >= INSET.left - 1 && cells[i].x + cells[i].w <= 1248 - INSET.right + 1, `cell ${i} of ${n} inside the width`);
      assert.ok(cells[i].y >= INSET.top - 1 && cells[i].y + cells[i].h <= 800 - INSET.bottom + 1, `cell ${i} of ${n} inside the height`);
      assert.ok(Math.hypot(Math.max(cells[i].x - core.x, 0, core.x - cells[i].x - cells[i].w), Math.max(cells[i].y - core.y, 0, core.y - cells[i].y - cells[i].h)) > core.radius, `cell ${i} of ${n} clear of the core`);
      for (let j = i + 1; j < cells.length; j++) assert.ok(!overlap(cells[i], cells[j]), `cells ${i} and ${j} of ${n} overlap`);
    }
  }
});

test('the first cells sit beside the core, the later ones further out', () => {
  const {cells, core} = layoutTerritories(12, 1248, 800, INSET), d = c => Math.hypot(c.x + c.w / 2 - core.x, c.y + c.h / 2 - core.y);
  assert.ok(d(cells[0]) < d(cells[cells.length - 1]));
  assert.ok(d(cells[0]) <= d(cells[3]) + 1);
});

test('a few projects get big cells, a hundred get marks that still fit a 44 px target', () => {
  assert.equal(layoutTerritories(3, 1248, 800, INSET).level, 'full');
  const huge = layoutTerritories(100, 1248, 800, INSET);
  assert.equal(huge.level, 'mark');
  assert.ok(huge.cells[0].w >= 44 && huge.cells[0].h >= 44, `mark ${huge.cells[0].w}x${huge.cells[0].h}`);
});

test('the same input gives the same layout', () => {
  assert.deepEqual(layoutTerritories(12, 1248, 800, INSET), layoutTerritories(12, 1248, 800, INSET));
});

test('the smaller grid wins a tie', () => {
  const g = pickGrid(3, 1200, 600, 12, 120);
  assert.equal(g.cols * g.rows, 4);
});

test('levelOf thresholds', () => {
  assert.equal(levelOf(300, 200), 'full');
  assert.equal(levelOf(150, 100), 'compact');
  assert.equal(levelOf(80, 50), 'mark');
});

test('a spoke ends on the cell outline, on the side facing the core', () => {
  const cell = {x: 100, y: 100, w: 200, h: 100}, p = edgePoint(cell, {x: 600, y: 150});
  assert.equal(p.x, 300);
  assert.equal(p.y, 150);
});


test('rebuilds preserve project, equivalent-list and panel controls by identity', () => {
  const previous = globalThis.document;
  const control = key => ({dataset: {focusKey: key}, focus() { document.activeElement = this; }});
  let controls = [];
  const root = {contains: el => controls.includes(el), querySelectorAll: () => controls, querySelector: () => controls.find(el => el.dataset.focusKey === 'am-focus-back')};
  globalThis.document = {activeElement: null};
  try {
    for (const key of ['project:p1', 'equivalent:p1', 'am-focus-back', 'am-focus-open', 'mission:m1', 'review:m1']) {
      const old = control(key); controls = [old]; document.activeElement = old;
      preserveFocus(root, () => { controls = [control('project:p2'), control(key)]; });
      assert.equal(document.activeElement, controls[1], key);
    }
    const outside = control('outside'); document.activeElement = outside;
    preserveFocus(root, () => { controls = [control('am-focus-back')]; });
    assert.equal(document.activeElement, outside);
    document.activeElement = controls[0];
    preserveFocus(root, () => {});
    assert.equal(document.activeElement, controls[0]);
    const mission = control('mission:removed'); controls.push(mission); document.activeElement = mission;
    preserveFocus(root, () => { controls = [control('am-focus-back')]; });
    assert.equal(document.activeElement, controls[0]);
  } finally { if (previous === undefined) delete globalThis.document; else globalThis.document = previous; }
});

test('project state follows mission lanes, including paused, planning and mixed work', () => {
  for (const [states, attention, expected] of [
    [['paused'], 0, 'paused'], [['thinking'], 0, 'paused'], [['done', 'thinking'], 0, 'paused'],
    [[], 0, 'paused'], [['done', 'completed'], 0, 'done'], [['running', 'blocked'], 0, 'blocked'],
    [['running', 'done'], 0, 'running'], [['blocked'], 1, 'needs-you'], [['needs-you'], 0, 'needs-you']
  ]) {
    assert.equal(stateOf({missions: states.map(state => ({state})), attention, total: states.length}), expected);
  }
});

test('project descriptions translate whole attention phrases for accessible names and equivalent lists', async () => {
  globalThis.location = {search: '?lang=it'};
  const {tr} = await import('../i18n.js');
  for (const [attention, phrase] of [[1, '1 richiede la tua attenzione'], [2, '2 richiedono la tua attenzione']]) {
    const project = {name: 'Alpha', code: 'AL', attention, missions: [], worktrees: [{}, {}]};
    assert.equal(describeProject(project), 'Alpha, AL, Needs you, ' + attention + ' need you, 2 worktrees');
    assert.equal(describeProject(project, tr), 'Alpha, AL, Richiede la tua attenzione, ' + phrase + ', 2 worktree');
  }
});
