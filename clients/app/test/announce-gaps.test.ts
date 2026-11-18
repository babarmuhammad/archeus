// T-1467: the screen-reader writer (announce, announceApproval). Time is faked by
// hand: Date.now reads `clock`, and setTimeout comes from node:test mock.timers,
// advanced one millisecond at a time so each timer fires at its due clock value.
import { test, beforeEach, afterEach, mock } from 'node:test';
import assert from 'node:assert/strict';
import { announce, announceApproval } from '../src/a11y/announce.ts';

const g = globalThis as Record<string, unknown>;

class Region {
  private value = '';
  readonly texts: string[] = [];
  readonly html: string[] = [];
  get textContent(): string {
    return this.value;
  }
  set textContent(v: string) {
    this.value = v;
    this.texts.push(v);
  }
  set innerHTML(v: string) {
    this.html.push(v);
  }
}

const regions: Record<string, Region> = {};
const doc = { getElementById: (id: string) => regions[id] ?? null };

let clock = 1_000_000;
let base = 0;
let hadDocument: boolean;
let savedDocument: unknown;
const realNow = Date.now;

function advance(ms: number) {
  for (let i = 0; i < ms; i++) {
    clock += 1;
    mock.timers.tick(1);
  }
}

// move to a time measured from the start of this test
function at(offset: number, fn?: () => void) {
  advance(base + offset - clock);
  fn?.();
}

beforeEach(() => {
  Date.now = () => clock;
  mock.timers.enable({ apis: ['setTimeout'] });
  base = clock;
  regions['live-polite'] = new Region();
  regions['live-assertive'] = new Region();
  hadDocument = 'document' in globalThis;
  savedDocument = g.document;
  g.document = doc;
});

afterEach(() => {
  // every timer a test left behind fires, and the window is clear for the next test
  at(30000);
  if (hadDocument) g.document = savedDocument;
  else delete g.document;
  mock.timers.reset();
  Date.now = realNow;
});

test('an announce outside the window clears the region at once and sets the text 30 ms later', () => {
  const polite = regions['live-polite'];
  announce('p');
  assert.deepEqual(polite.texts, ['']);
  at(29);
  assert.deepEqual(polite.texts, ['']);
  at(30);
  assert.deepEqual(polite.texts, ['', 'p']);
});

test('a missing region is a silent no-op', () => {
  delete regions['live-polite'];
  assert.doesNotThrow(() => {
    announce('x');
    at(100);
  });
});

test('with no document global, announce is a silent no-op', () => {
  delete g.document;
  assert.doesNotThrow(() => {
    announce('x');
    at(100);
  });
});

test('a held announce is flushed with the latest held text, not the first', () => {
  const polite = regions['live-polite'];
  announce('a');
  at(30);
  at(1000, () => announce('b'));
  at(2000, () => announce('c'));
  at(10000);
  assert.deepEqual(polite.texts, ['', 'a', '', 'c']);
});

test('an immediate announce after a held one writes once, and the old timer writes nothing more', () => {
  const polite = regions['live-polite'];
  announce('x');
  at(30);
  at(1000, () => announce('h'));
  at(5500, () => announce('new'));
  at(6100);
  assert.deepEqual(polite.texts, ['', 'x', '', 'new']);
});

test('a silent announce still uses up the 5 s window, so the next one is held', () => {
  const polite = regions['live-polite'];
  delete g.document;
  announce('a');
  g.document = doc;
  at(1000, () => announce('b'));
  assert.deepEqual(polite.texts, []);
  at(6030);
  assert.deepEqual(polite.texts, ['', 'b']);
});

test('an approval is announced once per id, and a second id is announced again', () => {
  const assertive = regions['live-assertive'];
  announceApproval('ap-8a', 'first');
  at(30);
  assert.deepEqual(assertive.texts, ['', 'first']);
  announceApproval('ap-8a', 'again');
  at(60);
  assert.deepEqual(assertive.texts, ['', 'first']);
  announceApproval('ap-8b', 'second');
  at(90);
  assert.deepEqual(assertive.texts, ['', 'first', '', 'second']);
});

test('an approval id is recorded even when the region is missing, so a later call does not announce it', () => {
  delete regions['live-assertive'];
  announceApproval('ap-9', 'lost');
  at(30);
  regions['live-assertive'] = new Region();
  announceApproval('ap-9', 'lost');
  at(60);
  assert.deepEqual(regions['live-assertive'].texts, []);
});

test('untrusted text is written as text only, never as markup', () => {
  const assertive = regions['live-assertive'];
  const payload = '<img src=x onerror=alert(1)>';
  announceApproval('ap-10', payload);
  at(30);
  assert.deepEqual(assertive.texts, ['', payload]);
  assert.deepEqual(assertive.html, []);
});
