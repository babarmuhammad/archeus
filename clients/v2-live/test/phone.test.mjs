import test from 'node:test';
import assert from 'node:assert/strict';
import { phoneBox, keyboard, slots, BAR, stopStep, STOP_IDLE, STOP_MS, confirmSide, places, overviewProjects, badgeText, topTitle, sideOf } from '../js/phone-model.js';
import { DETENTS, heights, snap, velocity, follow, step, stepLabel, isModal } from '../js/sheet-model.js';
import { RAIL_GROUPS } from '../js/rail-model.js';

const ROUTES = ['now', 'work', 'replay', 'chat', 'security', 'health', 'usage', 'accounts', 'extensions', 'settings'].map((id) => ({ id, label: id[0].toUpperCase() + id.slice(1), icon: id }));
const ps = Array.from({ length: 30 }, (_, i) => ({ id: 'p' + i, name: i === 11 ? 'Zebra Docs' : 'Project ' + i }));
const states = { p7: 'needs_you', p3: 'running', p9: 'needs_you', p1: 'done', p11: 'running' };
const st = (p) => states[p.id] || 'idle';

// ---------- the one phone threshold ----------
test('phone: narrow frame, or a short coarse window held sideways', () => {
  assert.equal(phoneBox({ frameW: 390, landscape: false }), true);
  assert.equal(phoneBox({ frameW: 599, landscape: false }), true);
  assert.equal(phoneBox({ frameW: 600, landscape: false }), false);
  assert.equal(phoneBox({ frameW: 844, landscape: true }), true);
  assert.equal(phoneBox({ frameW: 1440, landscape: false }), false);
});
test('keyboard: needs a focused field, a real height loss and no pinch zoom', () => {
  assert.deepEqual(keyboard({ innerH: 844, vvH: 844, editing: true }), { bottom: 0, open: false });
  assert.deepEqual(keyboard({ innerH: 844, vvH: 500, editing: true }), { bottom: 344, open: true });
  assert.equal(keyboard({ innerH: 844, vvH: 500, editing: false }).open, false);
  assert.equal(keyboard({ innerH: 844, vvH: 790, editing: true }).open, false, 'a collapsing browser bar is not a keyboard');
  assert.equal(keyboard({ innerH: 844, vvH: 500, scale: 2, editing: true }).open, false);
  assert.equal(keyboard({ innerH: 844, vvH: 500, vvTop: 100, editing: true }).bottom, 244);
});

// ---------- bottom bar ----------
test('bar: five slots in the owner order, defined in one array', () => {
  assert.deepEqual(BAR.map((s) => s.id), ['overview', 'work', 'tell', 'places', 'stop']);
  const s = slots({ route: 'now' });
  assert.deepEqual(s.map((x) => x.id), ['overview', 'work', 'tell', 'places', 'stop']);
  assert.equal(s.find((x) => x.id === 'tell').primary, true);
  assert.equal(s.find((x) => x.id === 'stop').danger, true);
});
test('bar: exactly one slot is current; a page without a slot belongs to Places', () => {
  const cur = (state) => slots(state).filter((x) => x.current).map((x) => x.id);
  assert.deepEqual(cur({ route: 'now' }), ['overview']);
  assert.deepEqual(cur({ route: 'work' }), ['work']);
  assert.deepEqual(cur({ route: 'security' }), ['places']);
  assert.deepEqual(cur({ route: 'chat' }), ['tell']);
  assert.deepEqual(cur({ route: 'now', placesOpen: true }), ['places']);
  assert.deepEqual(cur({ route: 'work', tellOpen: true }), ['tell']);
  assert.deepEqual(cur({ route: 'work', safetyOpen: true }), ['stop']);
});
test('bar: Work carries the needs-you count, with a word in its label; Stop turns into Re-arm', () => {
  const w = slots({ route: 'now', attention: 5 }).find((x) => x.id === 'work');
  assert.equal(w.badge, '5'); assert.equal(w.aria, 'Work, 5 need you');
  assert.equal(slots({ route: 'now', attention: 0 }).find((x) => x.id === 'work').badge, null);
  assert.equal(badgeText(120), '99+');
  const stop = (engaged) => slots({ route: 'now', engaged }).find((x) => x.id === 'stop');
  assert.equal(stop(false).label, 'Stop'); assert.equal(stop(true).label, 'Re-arm'); assert.equal(stop(true).aria, 'Re-arm new work');
});

// ---------- Stop two-step ----------
test('stop: tap arms a named confirm, confirm completes, nothing else does', () => {
  const armed = stopStep(STOP_IDLE, 'tap', { running: 3, now: 1000 });
  assert.equal(armed.phase, 'armed'); assert.equal(armed.label, 'Stop all 3 missions'); assert.equal(armed.action, 'estop');
  assert.equal(stopStep(STOP_IDLE, 'confirm', { running: 3, now: 1000 }).phase, 'idle', 'a confirm with nothing armed does nothing');
  const done = stopStep(armed, 'confirm', { now: 1500 });
  assert.equal(done.phase, 'done'); assert.equal(done.action, 'estop');
  assert.equal(stopStep(done, 'tick', { now: 1600 }).phase, 'idle');
});
test('stop: one mission is singular; an engaged stop offers Re-arm', () => {
  assert.equal(stopStep(STOP_IDLE, 'tap', { running: 1 }).label, 'Stop all 1 mission');
  const a = stopStep(STOP_IDLE, 'tap', { running: 0, engaged: true });
  assert.equal(a.action, 'rearm'); assert.equal(a.label, 'Re-arm new work');
});
test('stop: disarms after 5 s or on cancel; a second tap restarts the timer and never confirms', () => {
  const armed = stopStep(STOP_IDLE, 'tap', { running: 2, now: 0 });
  assert.equal(stopStep(armed, 'tick', { now: STOP_MS - 1 }).phase, 'armed');
  assert.equal(stopStep(armed, 'tick', { now: STOP_MS }).phase, 'idle');
  assert.equal(stopStep(armed, 'cancel', { now: 100 }).phase, 'idle');
  const again = stopStep(armed, 'tap', { running: 2, now: 4000 });
  assert.equal(again.phase, 'armed'); assert.equal(again.at, 4000);
});
test('stop: the confirm opens on the other half of the screen from the tap', () => {
  assert.equal(confirmSide(340, 390), 'start');
  assert.equal(confirmSide(40, 390), 'end');
});

// ---------- Places ----------
test('places: the desktop groups in order, from the shared rail model', () => {
  const p = places({ routes: ROUTES, projects: ps, stateOf: st });
  assert.deepEqual(p.groups.map((g) => g.label), RAIL_GROUPS.map(([l]) => l));
  assert.deepEqual(p.groups[0].items.map((i) => i.id), ['now', 'work', 'chat', 'replay', 'terminal']);
  assert.equal(p.groups[0].items[0].label, 'Overview'); assert.equal(p.groups[0].items[4].label, 'Terminal view');
  assert.equal(p.groups[0].items[1].badge, null);
  assert.equal(places({ routes: ROUTES, projects: ps, stateOf: st, attention: 7 }).groups[0].items[1].badge, '7');
});
test('places: top 5 projects by attention, then All N', () => {
  const p = places({ routes: ROUTES, projects: ps, stateOf: st });
  assert.deepEqual(p.projects.map((x) => x.id), ['p7', 'p9', 'p3', 'p11', 'p0']);
  assert.equal(p.more, 25); assert.equal(p.total, 30);
  assert.equal(places({ routes: ROUTES, projects: ps, stateOf: st, selected: 'p20' }).projects.at(-1).id, 'p20');
  assert.equal(places({ routes: ROUTES, projects: ps.slice(0, 4), stateOf: st }).more, 0);
});
test('places: a query searches every page and every project, best first', () => {
  const p = places({ routes: ROUTES, projects: ps, stateOf: st, query: ' zeb ' });
  assert.deepEqual(p.projects.map((x) => x.id), ['p11']); assert.deepEqual(p.pages, []); assert.deepEqual(p.groups, []);
  const q = places({ routes: ROUTES, projects: ps, stateOf: st, query: 'sec' });
  assert.deepEqual(q.pages.map((x) => x.id), ['security']);
  assert.equal(places({ routes: ROUTES, projects: ps, stateOf: st, query: 'nothing here' }).pages.length, 0);
});

// ---------- Overview list ----------
test('overview: five attention-ranked rows, All N for the rest, search only above 12 projects', () => {
  const o = overviewProjects({ projects: ps, stateOf: st });
  assert.deepEqual(o.rows.map((x) => x.id), ['p7', 'p9', 'p3', 'p11', 'p0']);
  assert.equal(o.more, 25); assert.equal(o.searchable, true);
  const few = overviewProjects({ projects: ps.slice(0, 12), stateOf: st });
  assert.equal(few.searchable, false); assert.equal(few.rows.length, 5); assert.equal(few.more, 7);
  assert.equal(overviewProjects({ projects: ps.slice(0, 13), stateOf: st }).searchable, true);
  assert.equal(overviewProjects({ projects: ps.slice(0, 3), stateOf: st }).more, 0);
});
test('overview: a query filters when searchable, and is ignored when not', () => {
  const o = overviewProjects({ projects: ps, stateOf: st, query: 'zebra' });
  assert.deepEqual(o.rows.map((x) => x.id), ['p11']); assert.equal(o.matches, 1); assert.equal(o.more, 0);
  const many = overviewProjects({ projects: ps, stateOf: st, query: 'project' });
  assert.equal(many.rows.length, 5); assert.equal(many.matches, 29); assert.equal(many.more, 24);
  assert.equal(overviewProjects({ projects: ps.slice(0, 8), stateOf: st, query: 'zebra' }).rows.length, 5);
});

// ---------- sheet maths ----------
test('sheet detents: shares of the space, never taller than what the keyboard leaves', () => {
  assert.deepEqual(heights(['full', 'peek', 'half'], 800), [{ name: 'peek', px: 320 }, { name: 'half', px: 448 }, { name: 'full', px: 736 }]);
  const kb = heights(['peek', 'half', 'full'], 400);
  assert.equal(kb.at(-1).px, 368); assert.ok(kb.every((d) => d.px <= 392));
  assert.equal(DETENTS.peek < DETENTS.half && DETENTS.half < DETENTS.full, true);
});
const D = heights(['peek', 'half', 'full'], 800);
test('sheet snap: a slow release goes to the nearest detent, below half the lowest it closes', () => {
  assert.equal(snap({ height: 400, velocity: 0, detents: D }), 'half');
  assert.equal(snap({ height: 540, velocity: 0.1, detents: D }), 'half');
  assert.equal(snap({ height: 700, velocity: -0.1, detents: D }), 'full');
  assert.equal(snap({ height: 200, velocity: 0, detents: D }), 'peek');
  assert.equal(snap({ height: 100, velocity: 0, detents: D }), 'close');
  assert.equal(snap({ height: 100, velocity: 0, detents: D, dismissible: false }), 'peek');
});
test('sheet snap: a flick goes to the next detent that way, and closes past the lowest', () => {
  assert.equal(snap({ height: 330, velocity: 0.8, detents: D }), 'half');
  assert.equal(snap({ height: 460, velocity: 0.8, detents: D }), 'full');
  assert.equal(snap({ height: 740, velocity: 0.9, detents: D }), 'full');
  assert.equal(snap({ height: 440, velocity: -0.8, detents: D }), 'peek');
  assert.equal(snap({ height: 300, velocity: -0.8, detents: D }), 'close');
  assert.equal(snap({ height: 300, velocity: -0.8, detents: D, dismissible: false }), 'peek');
  assert.equal(snap({ height: 330, velocity: 0.49, detents: D }), 'peek', 'just under the flick speed is a slow release');
});
test('sheet velocity: up is positive, measured over the last 100 ms', () => {
  assert.equal(velocity([]), 0);
  assert.equal(velocity([{ t: 0, y: 500 }]), 0);
  assert.equal(velocity([{ t: 0, y: 500 }, { t: 50, y: 450 }, { t: 100, y: 400 }]), 1);
  assert.equal(velocity([{ t: 0, y: 100 }, { t: 400, y: 100 }, { t: 450, y: 125 }, { t: 500, y: 150 }]), -0.5);
  assert.equal(velocity([{ t: 10, y: 300 }, { t: 10, y: 200 }]), 0);
});
test('sheet follow: 1:1 with the finger between zero and the tallest detent', () => {
  assert.equal(follow(400, 100, 736), 300);
  assert.equal(follow(400, -500, 736), 736);
  assert.equal(follow(400, 600, 736), 0);
});
test('sheet handle: steps up through the detents and wraps to the smallest; label says which way', () => {
  const n = ['full', 'peek', 'half'];
  assert.equal(step('peek', n), 'half'); assert.equal(step('half', n), 'full'); assert.equal(step('full', n), 'peek');
  assert.equal(step('half', n, -1), 'peek'); assert.equal(step('peek', n, -1), 'peek');
  assert.equal(stepLabel('peek', n), 'Expand'); assert.equal(stepLabel('half', n), 'Expand'); assert.equal(stepLabel('full', n), 'Collapse');
});
test('sheet modality: modal always when asked, otherwise only at full', () => {
  assert.equal(isModal('peek'), true);
  assert.equal(isModal('peek', false), false); assert.equal(isModal('half', false), false); assert.equal(isModal('full', false), true);
});
test('top bar title: only a page whose h1 is its bare label gets one', () => {
  assert.equal(topTitle('work', 'Work'), 'Work');
  assert.equal(topTitle('settings', ' Settings '), 'Settings');
  assert.equal(topTitle('work', 'Work, 3 need you'), null);
  assert.equal(topTitle('now', 'Now'), null);
  assert.equal(topTitle('work', ''), null); assert.equal(topTitle('work', null), null);
});
test('stop confirm side: opposite the thumb, start when the tap has no position (keyboard)', () => {
  assert.equal(sideOf(300, 0, 390), 'start'); assert.equal(sideOf(80, 0, 390), 'end');
  assert.equal(sideOf(150, 100, 390), 'end'); assert.equal(sideOf(320, 100, 390), 'start'); assert.equal(sideOf(0, 0, 390), 'start'); assert.equal(sideOf(undefined, 0, 390), 'start');
});
