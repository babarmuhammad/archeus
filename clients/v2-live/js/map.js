// The live map: the constellation module (js/constellation) fed from the simulation.
// The Network view: each project is a hub on a ring of cells round the core, its missions orbit it as crystals, live executions and pending decisions sit beside their mission.
// The Overview map survives the page re-renders: its box element is reused, so camera and focus are not lost on every simulation event.
// The module draws the core mark; its breath is the one allowed loop and is only switched on for a playing simulation with fresh output.
import { h } from './dom.js';
import { present } from '../core-words.js';
import { tr } from './i18n.js';
import * as store from './store.js';
import { createMap } from './constellation/map.js';
import { createTerritoryMap } from './constellation/territories.js';
import { clockLabel } from '../sim.js';

export const STATE = { needs_you: 'needs-you', active: 'running', verifying: 'running', reviewing: 'running', blocked: 'blocked', failed: 'blocked', paused: 'paused', planning: 'thinking', done: 'done' };
const THEME = { dark: 'dark', light: 'light', 'dark-hc': 'dark-high-contrast', 'light-hc': 'light-high-contrast', system: 'system', forced: 'forced' };
export const themeOf = () => THEME[store.get('theme')];
const maps = new Map();
const pending = [];
const lastPulse = new Map();

export const liveFresh = (sim) => { const st = sim.state; return st.playing && sim.liveWork().some((x) => x.state === 'RUNNING' && !x.stuck && st.clock - x.last_output_at < 120000); };

export function buildGraph(sim) {
  const st = sim.state, nodes = [], edges = [];
  const missions = Object.values(st.missions);
  for (const p of st.projects) {
    const own = missions.map((m) => (m.project === p.id ? STATE[present('mission', m.state).cls] : null));
    nodes.push({ id: p.id, kind: 'Project', label: p.name, project: p.id, weight: 8, state: own.includes('needs-you') ? 'needs-you' : own.includes('running') ? 'running' : 'idle' });
  }
  for (const m of missions) {
    nodes.push({ id: m.id, kind: 'Mission', label: m.title, project: m.project, weight: 3, state: STATE[present('mission', m.state).cls] || 'idle' });
    edges.push({ from: m.project, to: m.id, kind: 'contains' });
  }
  for (const x of Object.values(st.executions)) {
    if (present('execution', x.state).cls !== 'active') continue;
    const hn = st.harnesses.find((y) => y.id === x.harness);
    nodes.push({ id: x.id, kind: 'Execution', label: hn ? hn.label : x.harness, project: x.project, weight: 1.5, state: 'running' });
    edges.push({ from: x.mission, to: x.id, kind: 'runs' });
  }
  for (const a of Object.values(st.approvals)) {
    if (a.state !== 'PENDING') continue;
    nodes.push({ id: a.id, kind: 'Decision', label: tr(a.kind === 'plan' ? 'Approve plan' : 'Allow action'), project: a.project, weight: 1.5, state: 'needs-you' });
    edges.push({ from: a.mission, to: a.id, kind: 'asks' });
  }
  // Each project also carries what the Network view says about its hub: the neutral code, the counts and the last thing Archeus did (the same text as the Projects view).
  const view = buildOverview(sim).projects;
  return { nodes, edges, projects: st.projects.map((p, i) => { const { missions: _own, name: _name, ...hub } = view[i]; return { ...hub, label: p.name, captured: st.ideas.filter(i => i.project === p.id && i.state === 'CAPTURED').map(i => i.title) }; }) };
}

const VERB = { COMPLETED: 'completed', VERIFYING: 'is verifying', REVIEWING: 'is reviewing', EXECUTING: 'started', APPROVAL_REQUIRED: 'asks you to approve', BLOCKED: 'is blocked on', FAILED: 'has stopped', PAUSED: 'paused' };
const DAY = 24 * 3600 * 1000;
// The Overview model: one entry per project with its missions, counts and the last thing Archeus did there, and the day's ledger of completed missions.
export function buildOverview(sim) {
  const st = sim.state, used = new Set(), missions = Object.values(st.missions), att = sim.attention().filter((a) => a.kind !== 'knowledge');
  const code = (name) => { const w = name.trim().split(/\s+/); let c = (w.length > 1 ? w.map((x) => x[0]).join('').slice(0, 3) : name.slice(0, 2)).toUpperCase(); for (let i = 2; used.has(c); i++) c = c.slice(0, 2) + i; used.add(c); return c; };
  const last = new Map(), done = new Map();
  for (let i = st.events.length - 1; i >= 0; i--) {
    const e = st.events[i];
    if (!e.project || e.subject.kind !== 'mission' || e.type !== 'mission.state_changed') continue;
    const to = e.payload.to, m = st.missions[e.subject.id];
    if (!m) continue;
    if (to === 'COMPLETED' && st.clock - e.at < DAY) done.set(e.project, (done.get(e.project) || 0) + 1);
    if (VERB[to] && !last.has(e.project)) last.set(e.project, { at: e.at, time: clockLabel(e.at), text: tr('Archeus') + ' ' + tr(VERB[to]) + ' “' + m.title + '”' });
  }
  const projects = st.projects.map((p) => {
    const own = missions.filter((m) => m.project === p.id), cls = (m) => present('mission', m.state).cls, l = last.get(p.id);
    return { id: p.id, name: p.name, code: code(p.name), total: own.length, attention: att.filter((a) => a.project_id === p.id).length,
      running: own.filter((m) => ['active', 'verifying', 'reviewing'].includes(cls(m))).length, stopped: own.filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED').length,
      ideas: st.ideas.filter((i) => i.project === p.id && i.state === 'CAPTURED').length, last: l || null, lastAt: l ? l.at : 0,
      missions: own.map((m) => ({ id: m.id, title: m.title, state: STATE[cls(m)] || 'idle', at: m.updated_at, time: clockLabel(m.updated_at) })) };
  });
  const byProject = [...done].map(([id, n]) => ({ name: st.projects.find((p) => p.id === id).name, n })).sort((a, b) => b.n - a.n || a.name.localeCompare(b.name));
  return { projects, ledger: { done: byProject.reduce((t, x) => t + x.n, 0), byProject } };
}

export function mapBox(key, wide, inset) {
  let e = maps.get(key);
  if (!e) { e = { box: h('div', { class: 'map-box' + (wide ? ' wide' : ''), 'data-map': key }), map: null, lang: null, sel: undefined, inset }; maps.set(key, e); }
  return e.box;
}

export function syncMap(ctx, key) {
  const e = maps.get(key), sim = ctx.sim, lang = store.get('lang');
  if (!e || !e.box.isConnected) return;
  const calm = key === 'now' && sim.sentence() === 'Nothing needs you.';
  const terr = key === 'now' && !calm && store.get('overview') === 'projects' && document.getElementById('app').clientWidth >= 600;
  if (e.map && (e.lang !== lang || e.calm !== calm || e.terr !== terr)) { e.map.destroy(); e.map = null; e.sel = undefined; }
  if (!e.map) {
    e.lang = lang; e.calm = calm; e.terr = terr;
    e.map = (terr ? createTerritoryMap : createMap)(e.box, { seed: 'v2-live', overview: key === 'now', calm, theme: THEME[store.get('theme')], reducedMotion: store.reducedMotion(), live: liveFresh(sim), t: tr, inset: e.inset, label: tr('Live map of your projects and missions. The list beside it has the same content.') });
    e.map.on('review', (id) => { const a = Object.values(sim.state.approvals).find((x) => x.state === 'PENDING' && x.mission === id); ctx.nav(a ? '#/work/' + a.id : '#/' + ctx.route.name + '/' + id); });
    e.map.on('select', (id) => { if (!e.syncing && id && sim.state.projects.some((p) => p.id === id)) { ctx.ui.workProject = id; ctx.nav('#/work'); return; } if (!e.syncing && id && id !== ctx.route.id && (sim.state.missions[id] || sim.state.approvals[id] || sim.state.executions[id])) ctx.nav('#/' + ctx.route.name + '/' + (sim.state.executions[id] ? sim.state.executions[id].mission : id)); });
  }
  const g = terr ? buildOverview(sim) : buildGraph(sim);
  e.map.setTheme(THEME[store.get('theme')]);
  e.map.setReducedMotion(store.reducedMotion());
  e.map.setLive(liveFresh(sim)); e.map.setAmbient(sim.state.playing && !sim.state.estop.engaged);
  e.map.update(g);
  const want = (terr ? g.projects.some((p) => p.id === ctx.route.id || p.missions.some((m) => m.id === ctx.route.id)) : g.nodes.some((n) => n.id === ctx.route.id)) ? ctx.route.id : null;
  if (want !== e.sel) { e.sel = want; e.syncing = true; e.map.setSelection(want); e.syncing = false; }
  for (const id of pending.splice(0)) e.map.pulse(id);
}

// Maps of routes we have left are destroyed, so no stale instance keeps listening to the simulation.
export function pruneMaps(keep) {
  for (const [k, e] of maps) if (k !== keep) { if (e.map) e.map.destroy(); maps.delete(k); }
}

export function syncLive(sim) {
  for (const e of maps.values()) if (e.map) { e.map.setLive(liveFresh(sim)); e.map.setAmbient(sim.state.playing && !sim.state.estop.engaged); e.map.setReducedMotion(store.reducedMotion()); }
}

// An execution starting draws a marker down its edge, one ending down the mission's edge (the execution node is gone by then); output pulses at most once per 2 s per execution.
export function notePulse(sim, ev) {
  const x = ev.subject && ev.subject.kind === 'execution' ? sim.state.executions[ev.subject.id] : null;
  if (!x || !maps.size) return;
  if (ev.type === 'execution.state_changed') pending.push(ev.payload.to === 'RUNNING' ? x.mission + '->' + x.id + ':runs' : x.project + '->' + x.mission + ':contains');
  else if (ev.type === 'execution.progress') {
    const now = performance.now();
    if (now - (lastPulse.get(x.id) ?? -Infinity) < 2000) return;
    lastPulse.set(x.id, now);
    for (const e of maps.values()) if (e.map) e.map.pulse(x.mission + '->' + x.id + ':runs');
  }
}
