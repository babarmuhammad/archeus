// T-1076: the hidden-tab notification. Off until the user opts in, never for
// what the first read already showed, once per item, only the three kinds the
// user must answer, fixed title and a reason with no ids.
// Mutation-verified by tools/mutate_t1076.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { AttentionItem } from '../src/api/generated.ts';
import { BODY_MAX, NOTIFY_KEY, Notifier, mayNotify, noteOf, notifyState, notifyWanted, setNotifyWanted, type Note } from '../src/state/notify.ts';

const item = (kind: AttentionItem['kind'], id: string, reason: string | null = null): AttentionItem => ({
  kind, ref: { kind, id }, state: 'PENDING', reason_code: 'x', reason, mission_id: null, project_id: null, since: '2026-11-09T10:00:00Z',
});

function rig(o: { enabled?: boolean; hidden?: boolean } = {}) {
  const f = { enabled: o.enabled ?? true, hidden: o.hidden ?? true };
  const shown: Note[] = [];
  const n = new Notifier({ enabled: () => f.enabled, hidden: () => f.hidden, show: (x) => shown.push(x) });
  return { n, f, shown };
}

test('the first read is the baseline: what it shows never notifies', () => {
  const { n, shown } = rig();
  n.read([item('approval', 'apr_1')], 1);
  assert.equal(shown.length, 0);
  n.read([item('approval', 'apr_1'), item('approval', 'apr_2')], 2);
  assert.deepEqual(shown.map((x) => x.key), ['approval:apr_2']);
});

test('an item notifies once, however often it is read again', () => {
  const { n, shown } = rig();
  n.read([], 1);
  const a = [item('approval', 'apr_1')];
  n.read(a, 2);
  n.read(a, 3);
  n.read([], 4);
  n.read(a, 5);
  assert.equal(shown.length, 1);
});

test('an older or the same read changes nothing', () => {
  const { n, shown } = rig();
  n.read([], 5);
  n.read([item('approval', 'apr_1')], 5);
  n.read([item('approval', 'apr_1')], 4);
  assert.equal(shown.length, 0);
  n.read([item('approval', 'apr_1')], 6);
  assert.equal(shown.length, 1);
});

test('nothing shows while the tab is visible or the setting is off, and that item is not saved for later', () => {
  const { n, f, shown } = rig({ hidden: false });
  n.read([], 1);
  n.read([item('approval', 'apr_1')], 2);
  f.hidden = true;
  f.enabled = false;
  n.read([item('approval', 'apr_1'), item('approval', 'apr_2')], 3);
  f.enabled = true;
  n.read([item('approval', 'apr_1'), item('approval', 'apr_2'), item('approval', 'apr_3')], 4);
  assert.deepEqual(shown.map((x) => x.key), ['approval:apr_3']);
});

test('only an approval, a verification and a planning question notify', () => {
  const { n, shown } = rig();
  n.read([], 1);
  n.read(['approval', 'verification', 'mission', 'knowledge', 'drift', 'automation', 'account'].map((k) => item(k as AttentionItem['kind'], 'id_' + k)), 2);
  assert.deepEqual(shown.map((x) => x.key), ['approval:id_approval', 'verification:id_verification', 'mission:id_mission']);
});

test('the title is the fixed label, the body Core\'s reason with ids said as their kind and a length cap', () => {
  const id = 'apr_' + '0'.repeat(26);
  assert.equal(noteOf(item('approval', id, `plan v1 awaits approval ${id}`)).body, 'plan v1 awaits approval');
  assert.equal(noteOf(item('approval', id, `see ${id}`)).body, 'see approval');
  const n = noteOf(item('mission', 'msn_1', 'the key sk-secret is'.padEnd(500, 'x')));
  assert.equal(n.title, 'Planning asks you');
  assert.ok(!n.title.includes('msn_1') && n.body.length === BODY_MAX && n.body.endsWith('…'));
  assert.equal(noteOf(item('approval', id)).body, '');
});

test('the setting is off unless stored on, and a failing store is off', () => {
  const mem = new Map<string, string>();
  const s = { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => void mem.set(k, v) };
  assert.equal(notifyWanted(s), false);
  setNotifyWanted(s, true);
  assert.equal(mem.get(NOTIFY_KEY), 'on');
  assert.equal(notifyWanted(s), true);
  setNotifyWanted(s, false);
  assert.equal(notifyWanted(s), false);
  const bad = { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } };
  assert.equal(notifyWanted(bad), false);
  assert.doesNotThrow(() => setNotifyWanted(bad, true));
  assert.equal(notifyWanted(null), false);
});

test('notifications need both the user\'s choice and the browser\'s grant', () => {
  assert.equal(mayNotify(true, 'granted'), true);
  assert.equal(mayNotify(false, 'granted'), false);
  assert.equal(mayNotify(true, 'default'), false);
  assert.equal(mayNotify(true, 'denied'), false);
  assert.equal(mayNotify(true, undefined), false);
  assert.equal(notifyState(true, 'granted'), 'on');
  assert.equal(notifyState(false, 'granted'), 'off');
  assert.equal(notifyState(true, 'default'), 'off');
  assert.equal(notifyState(true, 'denied'), 'blocked');
  assert.equal(notifyState(false, undefined), 'unsupported');
});
