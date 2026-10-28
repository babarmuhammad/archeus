import test from 'node:test';
import assert from 'node:assert/strict';
import {pickGrid, layoutTerritories, levelOf, edgePoint, orderProjects} from './territories.js';

const overlap = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
const INSET = {top: 150, right: 24, bottom: 80, left: 24};

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

test('projects needing you come first, then running, then the most recent', () => {
  const list = orderProjects([{id: 'a', attention: 0, running: 0, lastAt: 9}, {id: 'b', attention: 1, running: 0, lastAt: 1}, {id: 'c', attention: 0, running: 2, lastAt: 5}, {id: 'd', attention: 0, running: 0, lastAt: 20}]);
  assert.deepEqual(list.map(p => p.id), ['b', 'c', 'd', 'a']);
});
