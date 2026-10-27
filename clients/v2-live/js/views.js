// Shared view helpers and the route list. Each screen lives in its own view-*.js and exports render(ctx); ctx = { sim, nav(hash), act(kind, id), toast(text), route, ui }.
// Everything shown comes from the simulation (fixtures), and every screen says so in its header.
import { h } from './dom.js';
import { icon, glyph } from './icons.js';
import { illustration } from './illustrations.js';
import { present } from '../core-words.js';
import { clockLabel, SPEEDS } from '../sim.js';
import { spineRow, spineCard } from './spine.js';
import { areasOf } from './areas-model.js';

export const ROUTES = [
  { id: 'now', label: 'Now', icon: 'now' }, { id: 'work', label: 'Work', icon: 'work' },
  { id: 'replay', label: 'Replay', icon: 'replay' }, { id: 'chat', label: 'Chat', icon: 'chat' },
  { id: 'security', label: 'Security', icon: 'security' }, { id: 'health', label: 'Health', icon: 'health' }, { id: 'usage', label: 'Usage', icon: 'usage' }, { id: 'accounts', label: 'Accounts', icon: 'accounts' }, { id: 'extensions', label: 'Extensions', icon: 'extensions' },
  { id: 'settings', label: 'Settings', icon: 'settings' }
];

export const projName = (sim, id) => (sim.state.projects.find((p) => p.id === id) || { name: '' }).name;
export const word = (machine, state) => present(machine, state).label;

export function badge(machine, state) {
  const p = present(machine, state);
  return h('span', { class: 'badge', 'data-role': p.cls }, h('span', { class: 'g', 'aria-hidden': 'true' }, glyph(p.cls)), h('span', { class: 'w' }, p.label));
}

export function head(ctx, title, extra) {
  return h('header', { class: 'page-head' }, h('div', null, h('h1', null, title)), extra || null);
}

export const panel = (title, n, ...kids) => h('section', { class: 'panel' }, h('h2', null, h('span', { class: 'gt' }, title), n != null ? h('span', { class: 'n' }, String(n)) : null), ...kids);
export const dnote = (id, text) => h('p', { class: 'dnote' }, h('b', null, 'Decision ' + id), ' \u00b7 ' + text);
export const empty = (t, art) => (art ? h('div', { class: 'empty art' }, illustration(art), h('p', null, t)) : h('p', { class: 'empty' }, t));

export function missionRow(ctx, m, base) {
  const p = present('mission', m.state);
  const x = Object.values(ctx.sim.state.executions).find((e) => e.mission === m.id && (e.state === 'RUNNING' || e.state === 'LOST'));
  const meta = [projName(ctx.sim, m.project), m.branch, m.reason || (x ? ctx.sim.reading(x) : null)].filter(Boolean).join(' · ');
  return h('a', { class: 'mrow', href: '#/' + base + '/' + m.id, 'aria-current': ctx.route.id === m.id ? 'true' : null, 'data-key': 'm-' + m.id },
    h('span', { class: 't' }, badge('mission', m.state), h('span', { class: 'name' }, m.title)),
    h('span', { class: 'm' }, meta, x ? h('span', { class: 'vh' }, ' ') : null),
    h('span', { class: 'sp' }, spineRow(m.state, m.held_from)));
}

const KIND_ICON = { approval: 'approval', verification: 'status', mission: 'mission', knowledge: 'knowledge', automation: 'execution', account: 'account' };
export function attentionItem(ctx, a) {
  const sim = ctx.sim, m = a.mission_id ? sim.state.missions[a.mission_id] : null;
  const need = a.group === 'Decide' || a.group === 'Review';
  const open = a.kind === 'approval' ? '#/work/' + a.ref : m ? '#/work/' + m.id : null;
  const btns = [];
  if (a.kind === 'knowledge') btns.push(h('button', { class: 'btn primary', type: 'button', onclick: () => ctx.act('confirm', a.ref) }, 'Remember'), h('button', { class: 'btn', type: 'button', onclick: () => ctx.act('retract', a.ref) }, 'Not this'));
  else if (a.kind === 'automation') btns.push(h('button', { class: 'btn primary', type: 'button', onclick: () => ctx.act('enable', a.ref) }, a.state === 'SUSPENDED' ? 'Re-enable' : 'Approve'));
  else if (a.kind === 'account') btns.push(h('a', { class: 'btn', href: '#/settings' }, 'Open Settings'));
  else if (open) btns.push(h('a', { class: 'btn primary', href: open }, a.kind === 'approval' ? 'Open decision' : a.group === 'Review' ? 'Open review' : 'Open'));
  return h('article', { class: 'card band', 'data-key': a.id, 'data-state': need ? 'needs_you' : 'blocked' },
    h('div', { class: 'top' }, h('span', { class: 'kind' }, icon(KIND_ICON[a.kind] || 'status', 20), a.kind === 'approval' || a.kind === 'verification' || a.kind === 'mission' ? badge('mission', m ? m.state : 'APPROVAL_REQUIRED') : h('span', { class: 'badge', 'data-role': need ? 'needs_you' : 'blocked' }, h('span', { class: 'g', 'aria-hidden': 'true' }, glyph(need ? 'needs_you' : 'blocked')), h('span', { class: 'w' }, a.kind === 'knowledge' ? 'Candidate' : a.kind === 'automation' ? 'Automation' : 'Account'))),
      h('span', { class: 'why' }, [projName(sim, a.project_id), a.since ? 'since ' + clockLabel(a.since) : ''].filter(Boolean).join(' · '))),
    h('p', { class: 'ttl' }, a.reason),
    m ? spineCard(m.state, m.held_from) : null,
    btns.length ? h('div', { class: 'actions' }, ...btns) : null);
}

export function simControls(ctx) {
  const sim = ctx.sim, st = sim.state;
  const pr = (kind, label) => h('button', { class: 'btn', type: 'button', onclick: () => ctx.act(kind) }, label);
  return h('div', { class: 'col', style: 'gap:10px' },
    h('div', { class: 'actions' }, h('button', { class: 'btn primary', type: 'button', 'aria-pressed': st.playing ? 'true' : 'false', onclick: () => ctx.act(st.playing ? 'pause-sim' : 'play-sim') }, st.playing ? 'Pause' : 'Play'),
      h('div', { class: 'sel-wrap', style: 'padding:0' }, h('label', { for: 'sim-speed-' + (ctx.where || 'a') }, 'Speed'), h('select', { id: 'sim-speed-' + (ctx.where || 'a'), onchange: (e) => ctx.act('speed', e.target.value) }, ...SPEEDS.map((x) => h('option', { value: String(x), selected: x === st.speed ? true : null }, 'x' + x))))),
    h('div', { class: 'actions' }, pr('trigger-approval', 'Trigger an approval'), pr('inject-failure', 'Inject a failure'), pr('inject-spawn', 'Break the harness'), pr('offline-toggle', areasOf(sim).isOffline() ? 'Reconnect' : 'Go offline'), pr('reset', 'Reset')),
    h('p', { class: 'note', style: 'padding:0' }, 'Simulated clock ', h('span', { 'data-live': 'clock' }, clockLabel(st.clock)), '. One real second is ten simulated seconds at x1. Same seed, same story.'));
}

export function controlBody(ctx, compact) {
  const ms = Object.values(ctx.sim.state.missions), run = ms.filter((m) => m.state === 'EXECUTING').length, paused = ms.filter((m) => m.state === 'PAUSED').length;
  const b = (cls, label, onclick, key) => h('button', { class: 'btn ' + cls, type: 'button', 'data-key': key, onclick }, label);
  const ask = ctx.ui.estopAsk, armed = ctx.sim.state.estop.engaged, askR = ctx.ui.rearmAsk;
  return h('div', { class: 'body' },
    armed ? h('p', { class: 'note', style: 'padding:0 0 8px', 'data-key': 'estop-note' }, 'The emergency stop is engaged: nothing new starts and no mission resumes until you re-arm. Re-arming needs a step-up (simulated here).') : compact ? h('p', { class: 'note', style: 'padding:0 0 8px' }, ask ? 'Stop every running mission and block new dispatch until you re-arm? Each mission then waits for you.' : 'Not stopped: accepts new work.') : null,
    compact ? null : h('p', { class: 'note', style: 'padding:0 0 8px' }, run + ' running, ' + paused + ' paused. Pause all waits for each execution to reach a safe boundary. Emergency stop ends every running execution; each mission then waits for you.'),
    h('div', { class: 'actions' },
      b('', 'Pause all', () => ctx.act('pause_all'), 'pause-all'), b('', 'Resume all', () => ctx.act('resume_all'), 'resume-all'),
      armed ? (askR ? [b('primary', 'Yes, re-arm', () => { ctx.ui.rearmAsk = false; ctx.act('rearm'); }, 'rearm-yes'), b('', 'Back', () => { ctx.ui.rearmAsk = false; ctx.render(); }, 'rearm-back')] : b('primary', 'Re-arm', () => { ctx.ui.rearmAsk = true; ctx.render(); }, 'rearm'))
      : ask ? [b('danger', 'Yes, stop everything', () => { ctx.ui.estopAsk = false; ctx.act('estop'); }, 'estop-yes'), b('', 'Back', () => { ctx.ui.estopAsk = false; ctx.render(); }, 'estop-back')]
        : b('danger', 'Emergency stop', () => { ctx.ui.estopAsk = true; ctx.render(); }, 'estop')));
}
