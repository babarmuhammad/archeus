import test from 'node:test';
import assert from 'node:assert/strict';
import { edgeOf, centerLeft, eventLine, SET_SECTIONS, settingsPage, settingsLine } from '../js/phone-pages-model.js';

test('a scrolling row fades only the edge that has more behind it', () => {
  assert.equal(edgeOf({ left: 0, client: 358, scroll: 358 }), '');
  assert.equal(edgeOf({ left: 0, client: 358, scroll: 600 }), 'right');
  assert.equal(edgeOf({ left: 120, client: 358, scroll: 600 }), 'both');
  assert.equal(edgeOf({ left: 242, client: 358, scroll: 600 }), 'left');
  assert.equal(edgeOf({ left: 0.5, client: 358, scroll: 358.5 }), '', 'sub-pixel rounding is not an edge');
});

test('the current tab is centred in its row and the row never scrolls past its ends', () => {
  const row = { client: 358, scroll: 700 };
  assert.equal(centerLeft({ offset: 0, width: 80, ...row }), 0);
  assert.equal(centerLeft({ offset: 300, width: 100, ...row }), 171);
  assert.equal(centerLeft({ offset: 640, width: 60, ...row }), 342, 'the last tab stops at the end');
  assert.equal(centerLeft({ offset: 10, width: 50, client: 400, scroll: 400 }), 0, 'a row that fits does not move');
});

const step = { machine: 'execution', state: 'LOST_CONTACT', reason: 'last_event_is_lost', why: 'Core lost contact with the execution.', trigger: 'heartbeat_timeout', actor: 'core', seq: 41 };
test('an event row is one title and one line, by detail', () => {
  assert.deepEqual(eventLine(step, 'normal'), { title: 'execution LOST CONTACT', summary: 'after heartbeat timeout' });
  assert.equal(eventLine(step, 'thinking').summary, 'Core lost contact with the execution.');
  assert.equal(eventLine(step, 'verbose').summary, 'trigger heartbeat_timeout · by core · seq 41');
  const bare = { ...step, trigger: null, why: '' };
  assert.equal(eventLine(bare, 'normal').summary, 'last event is lost');
  assert.equal(eventLine(bare, 'thinking').summary, 'last event is lost', 'no why falls back to the reason');
  assert.equal(eventLine(bare, 'verbose').summary, 'by core · seq 41');
});

test('settings is a list on a phone and opens on Safety on a desktop', () => {
  assert.deepEqual(SET_SECTIONS.map(([id]) => id), ['safety', 'appearance', 'prototype', 'about']);
  assert.equal(settingsPage(undefined, true), 'list');
  assert.equal(settingsPage('nope', true), 'list');
  assert.equal(settingsPage('appearance', true), 'appearance');
  assert.equal(settingsPage(undefined, false), 'safety');
  assert.equal(settingsPage('about', false), 'about');
});

test('each settings row says what is set', () => {
  assert.deepEqual(settingsLine('safety', { engaged: false, running: 2, paused: 1 }), ['2 running', '1 paused']);
  assert.deepEqual(settingsLine('safety', { engaged: true }), ['Stopped', 'new work is blocked']);
  assert.deepEqual(settingsLine('appearance', { theme: 'Dark', lang: 'it', motion: 'reduced' }), ['Dark', 'Italiano', 'Quiet motion']);
  assert.deepEqual(settingsLine('appearance', { theme: 'Light', lang: 'en', motion: 'system' }), ['Light', 'English', 'Motion follows the system']);
  assert.deepEqual(settingsLine('prototype', { device: 'Phone', playing: true }), ['Phone', 'simulation playing']);
  assert.deepEqual(settingsLine('about', {}), ['Simulated', 'no Core connected']);
});
