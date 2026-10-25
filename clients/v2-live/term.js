// Text-mode renderer: the same simulated state as the TUI would show, as lines of at most `cols` characters.
// No DOM. Each line is { t: text, k: kind } where kind styles the whole line (head, dim, sel, warn, plain).
import { present } from './core-words.js';
import { spineText } from './spine-model.js';
import { clockLabel } from './sim.js';

export const TERM_SCREENS = [
  { id: 'now', key: '1', label: 'Now' }, { id: 'work', key: '2', label: 'Work' }, { id: 'attention', key: 'a', label: 'Attention' }, { id: 'replay', key: 'r', label: 'Replay' }
];

const GROUPS = [
  ['Needs you', ['needs_you']], ['Active', ['active', 'verifying', 'reviewing', 'approved']], ['Planning', ['planning']],
  ['Blocked', ['blocked']], ['Paused', ['paused']], ['Done', ['done']], ['Failed or cancelled', ['failed', 'inactive']]
];

export const trunc = (s, n) => (s.length <= n ? s : n <= 1 ? s.slice(0, n) : s.slice(0, n - 1) + '…');
export function fit(left, right, cols) {
  if (!right) return trunc(left, cols);
  const room = cols - right.length - 1;
  if (room < 8) return trunc(left, cols);
  return trunc(left, room).padEnd(room) + ' ' + right;
}
export function wrap(s, n) {
  const out = []; let cur = '';
  s.split(' ').forEach((w) => { if ((cur + ' ' + w).trim().length > n) { out.push(cur); cur = w; } else cur = (cur + ' ' + w).trim(); });
  if (cur) out.push(cur);
  return out;
}
const rule = (cols, ch) => ({ t: (ch || '─').repeat(cols), k: 'dim' });

export function missionGroups(sim) {
  const out = GROUPS.map(([title, classes]) => ({ title, items: [] }));
  Object.values(sim.state.missions).forEach((m) => {
    const cls = present('mission', m.state).cls;
    const g = out[GROUPS.findIndex((x) => x[1].includes(cls))];
    (g || out[out.length - 1]).items.push(m);
  });
  return out.filter((g) => g.items.length);
}

export function termModel(sim, opts) {
  const cols = Math.max(30, opts.cols || 80), ascii = !!opts.ascii, screen = opts.screen || 'now';
  const st = sim.state, att = sim.attention();
  const lines = [], items = [];
  const projName = (id) => (st.projects.find((p) => p.id === id) || { name: '' }).name;
  const glyph = (machine, state) => { const p = present(machine, state); return ascii ? p.ascii : p.glyph; };
  const add = (t, k) => lines.push({ t: trunc(t, cols), k: k || 'plain' });
  const sel = (n) => (opts.sel === n ? '>' : ' ');

  add(fit('V2 Live · SIMULATED · no Core connected', clockLabel(st.clock) + (st.playing ? ' x' + st.speed : ' paused'), cols), 'head');
  add(fit(TERM_SCREENS.map((s) => (s.id === screen ? '[' + s.key + ' ' + s.label + ']' : s.key + ' ' + s.label)).join('  ') + (att.length && screen !== 'attention' ? '  (' + att.length + ')' : ''), '', cols), 'plain');
  lines.push(rule(cols));

  if (screen === 'now') {
    add(sim.sentence(), 'head');
    add('');
    const need = att.filter((a) => a.group === 'Decide').slice(0, 3);
    add('NEEDS YOU', 'dim');
    if (!need.length) add('  Nothing is waiting for a decision.');
    need.forEach((a) => {
      const i = items.push({ kind: 'attention', id: a.id, ref: a.ref, mission: a.mission_id }) - 1;
      add(fit(sel(i) + ' ' + (ascii ? '!' : '◆') + ' ' + a.reason, projName(a.project_id), cols), opts.sel === i ? 'sel' : 'warn');
      if (a.mission_id) { const m = st.missions[a.mission_id]; add('    ' + spineText(m.state, m.held_from, ascii)); }
    });
    add('');
    add('HAPPENING NOW', 'dim');
    const live = Object.values(st.missions).filter((m) => ['active', 'verifying', 'reviewing'].includes(present('mission', m.state).cls));
    if (!live.length) add('  Nothing is running.');
    live.forEach((m) => {
      const i = items.push({ kind: 'mission', id: m.id, mission: m.id }) - 1;
      const x = Object.values(st.executions).find((e) => e.mission === m.id && (e.state === 'RUNNING' || e.state === 'LOST'));
      add(fit(sel(i) + ' ' + glyph('mission', m.state) + ' ' + m.title + '  ' + spineText(m.state, m.held_from, ascii), x ? sim.reading(x) || '' : '', cols), opts.sel === i ? 'sel' : 'plain');
    });
    add('');
    add('RECENT', 'dim');
    st.events.filter((e) => /state_changed$/.test(e.type) && e.subject.kind === 'mission').slice(-4).reverse().forEach((e) => add('  ' + clockLabel(e.at) + ' ' + e.subject.id.slice(2) + ' ' + e.payload.from + ' > ' + e.payload.to, 'dim'));
  }

  if (screen === 'work') {
    missionGroups(sim).forEach((g) => {
      add(g.title.toUpperCase() + ' · ' + g.items.length, 'dim');
      g.items.forEach((m) => {
        const i = items.push({ kind: 'mission', id: m.id, mission: m.id }) - 1;
        add(fit(sel(i) + ' ' + glyph('mission', m.state) + ' ' + m.title, projName(m.project), cols), opts.sel === i ? 'sel' : 'plain');
        add('    ' + spineText(m.state, m.held_from, ascii) + (m.reason ? '  ' + m.reason : ''), 'dim');
      });
      add('');
    });
  }

  if (screen === 'attention') {
    if (!att.length) add('  Nothing waits on you.');
    ['Decide', 'Review', 'Unblock'].forEach((grp) => {
      const g = att.filter((a) => a.group === grp);
      if (!g.length) return;
      add(grp.toUpperCase() + ' · ' + g.length, 'dim');
      g.forEach((a) => {
        const i = items.push({ kind: 'attention', id: a.id, ref: a.ref, mission: a.mission_id, att: a }) - 1;
        add(fit(sel(i) + ' ' + (a.group === 'Unblock' ? (ascii ? '#' : '■') : (ascii ? '!' : '◆')) + ' ' + a.reason, projName(a.project_id), cols), opts.sel === i ? 'sel' : a.group === 'Decide' ? 'warn' : 'plain');
      });
      add('');
    });
  }

  if (screen === 'replay') {
    const ms = Object.values(st.missions);
    const m = ms[(opts.mission == null ? 1 : opts.mission) % ms.length];
    items.push({ kind: 'mission', id: m.id, mission: m.id });
    add('REPLAY · ' + m.title + ' · ' + spineText(m.state, m.held_from, ascii), 'head');
    const r = sim.replay(m.id);
    r.rows.slice(-14).forEach((row, i) => add(fit('  ' + row.time + ' ' + row.category.padEnd(22) + ' ' + row.title, row.settled_by, cols), 'plain'));
    add('');
    wrap(r.gaps, cols).forEach((l) => add(l, 'dim'));
  }

  const body = lines.length;
  const hint = screen === 'replay' ? 'n next mission  1 now  2 work  a attention  q back' : 'j/k move  Enter open  p approve  x reject  1 2 a r screens  q back';
  while (opts.rows && lines.length < opts.rows - 2) lines.push({ t: '', k: 'plain' });
  lines.push(rule(cols));
  add(hint, 'dim');
  return { lines, items, body, cols };
}
