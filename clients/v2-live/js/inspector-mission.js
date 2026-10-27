// The mission page (concept 03 and 12): a graph of the mission on the left, the opaque inspector on the right. Sans titles, vector only, no glow.
// Only relations that exist in the record are drawn: a node without a record is left out with its arrows.
import { h, s } from './dom.js';
import { icon } from './icons.js';
import { present } from '../core-words.js';
import { tr } from './i18n.js';
import { STATE, themeOf } from './map.js';
import { missionScene, sceneMarkup, BOX } from './constellation/scene.js';
import { spineOf } from '../spine-model.js';
import { clockLabel } from '../sim.js';
import { badge, projName, word } from './views.js';
import { spineInspector } from './spine.js';
import { whyOf, stationTimes, harnessLabel, accountLabel } from './areas-model.js';
import { sec, note, link, hrefFor } from './ax.js';

const cut = (t, n) => (t.length > n ? t.slice(0, n - 1) + '…' : t);
const ACTIVE = ['ROUTING', 'RUNNING', 'VERIFYING'];
const TASK_MARK = (st) => (st === 'SUCCEEDED' ? 'done' : ACTIVE.includes(st) ? 'now' : st === 'FAILED' || st === 'BLOCKED' ? 'bad' : 'open');
const TASK_ICON = { done: 'approve', now: 'running', bad: 'reject', open: 'running' };

// The graph is the live map's engine: seeded crystals, depth-dimmed wireframe, state as line colour (js/constellation/scene.js).
function graph(S, m, compact) {
  const execs = Object.values(S.executions).filter((x) => x.mission === m.id).sort((a, b) => a.started_at - b.started_at), x = execs[execs.length - 1];
  const vs = Object.values(S.verifications).filter((v) => v.mission === m.id), v = vs[vs.length - 1];
  const rs = Object.values(S.reviews).filter((r) => r.mission === m.id), r = rs[rs.length - 1];
  const tasks = m.tasks.map((t) => S.tasks[t]), tk = tasks.find((t) => !['SUCCEEDED', 'SKIPPED'].includes(t.state)) || tasks[tasks.length - 1];
  const resTxt = v ? word('verification', v.state) : r ? word('review', r.state) : null;
  const scene = missionScene({ id: m.id, title: cut(m.title, 26), state: STATE[present('mission', m.state).cls] || 'idle',
    lines: ['Project: ' + cut(projName({ state: S }, m.project) || '', 24), m.branch ? 'Branch: ' + cut(m.branch, 24) : null].filter(Boolean),
    exec: x ? { title: harnessLabel(x.harness), lines: [word('execution', x.state)], state: ACTIVE.includes(x.state) ? 'running' : 'idle' } : null,
    result: resTxt ? { title: v ? 'Verification' : 'Review', meta: v ? 'VERIFICATION' : 'REVIEW', lines: [resTxt] } : null,
    task: tk ? { title: cut(tk.title, 24), lines: [word('task', tk.state)] } : null, out: Boolean(resTxt && tk) });
  const svg = s('svg', { class: 'msn-svg', viewBox: compact ? '0 20 ' + BOX.width + ' 420' : '0 0 ' + BOX.width + ' ' + BOX.height, role: 'img', preserveAspectRatio: 'xMidYMid meet',
    'aria-label': 'Mission graph: ' + m.title + '. ' + scene.arrows.map((a) => (scene.nodes.find((n) => n.id === a.from) || { title: 'Archeus' }).title + ' ' + a.label.toLowerCase() + ' ' + scene.nodes.find((n) => n.id === a.to).title).join('; ') });
  svg.innerHTML = sceneMarkup(scene, tr);
  return h('div', { class: 'archeus-map msn-scene', 'data-theme': themeOf() }, svg);
}

const labelled = (ic, k, t, d) => h('div', { class: 'msn-row' }, h('span', { class: 'msn-ic', 'aria-hidden': 'true' }, icon(ic, 22)), h('div', null, h('p', { class: 'ax-eyebrow' }, k), h('p', { class: 'msn-t' }, t), d ? h('p', { class: 'msn-d' }, d) : null));

const evText = (e) => (e.type === 'mission.state_changed' ? word('mission', e.payload.to) : e.type.replace(/[._]/g, ' ').replace(/^./, (c) => c.toUpperCase()));
const isBad = (e) => e.type === 'mission.state_changed' && ['FAILED', 'BLOCKED'].includes(e.payload.to);

export function overview(ctx, S, m, tasks, execs, bits) {
  const sp = spineInspector(m.state, m.held_from, 22), times = stationTimes(S, m), spn = spineOf(m.state, m.held_from);
  if (times) sp.querySelectorAll('ol > li').forEach((li, i) => { if (times[i] != null) li.append(h('span', { class: 'ax-st-time' }, clockLabel(times[i]))); });
  const evs = S.events.filter((e) => e.mission === m.id), last = evs[evs.length - 1];
  const x = execs.slice().sort((a, b) => a.started_at - b.started_at).pop();
  const tk = tasks.find((t) => ACTIVE.includes(t.state)) || tasks.find((t) => !['SUCCEEDED', 'SKIPPED'].includes(t.state));
  const compact = bits.compact;
  const why = whyOf(S, m).slice(0, 3);
  return h('div', { class: 'ax-body msn-ov' },
    sec('Where it is', sp, times ? note('The time under a station is when the mission first reached it.') : note('Station times are left out: older steps were pruned from the event log.'), bits.d08),
    h('div', { class: 'msn-phase' }, h('p', { class: 'ax-eyebrow' }, 'Current phase'), h('p', { class: 'msn-ph' }, word('mission', m.state)), h('p', { class: 'msn-d' }, spn.text)),
    h('div', { class: 'msn-rows' },
      labelled('execution', 'Agent', x ? harnessLabel(x.harness) + ' · ' + word('execution', x.state) : 'Not recorded.', x ? (S.models.find((q) => q.id === x.model) || {}).label + ' · ' + accountLabel(S, x.account) : null),
      labelled('task', 'Current task', tk ? tk.title : 'Not recorded.', tk ? word('task', tk.state) : null),
      labelled('status', 'Latest record', last ? evText(last) : 'Not recorded.', last ? clockLabel(last.at) : null)),
    h('div', { class: 'msn-boxes' },
      h('details', { class: 'msn-box', open: compact ? null : '' }, h('summary', null, h('span', null, 'Activity log'), icon('chevron', 18)),
        evs.length ? h('ol', { class: 'msn-log' }, ...evs.slice(-5).reverse().map((e) => h('li', { 'data-bad': isBad(e) ? 'true' : null }, icon(isBad(e) ? 'reject' : 'chevron', 16), h('span', { class: 'l-t' }, evText(e)), h('span', { class: 'l-c' }, clockLabel(e.at))))) : note('Nothing recorded yet.')),
      h('details', { class: 'msn-box', open: compact ? null : '' }, h('summary', null, h('span', null, 'Plan steps'), icon('chevron', 18)),
        tasks.length ? h('ol', { class: 'msn-steps' }, ...tasks.map((t) => h('li', null, h('a', { href: hrefFor('task', t.id), 'data-s': TASK_MARK(t.state) }, h('span', { class: 'st-g', 'aria-hidden': 'true' }, icon(TASK_ICON[TASK_MARK(t.state)], 18)), h('span', { class: 'st-n' }, t.title), h('span', { class: 'vh' }, word('task', t.state)))))) : note('No plan yet.')),
      h('details', { class: 'msn-box why' }, h('summary', null, h('span', null, 'Why'), icon('chevron', 18)),
        why.length ? h('ol', { class: 'msn-log' }, ...why.map((q) => h('li', null, icon('chevron', 16), h('span', { class: 'l-t' }, q.title), h('span', { class: 'l-c' }, q.time)))) : note('Nothing has been decided yet.'))),
    sec('Facts', bits.facts));
}

export function crumb(ctx, S, m) {
  const proj = S.projects.find((p) => p.id === m.project);
  return h('nav', { class: 'msn-crumb', 'aria-label': 'Breadcrumb' },
    h('a', { class: 'crumb-back', href: '#/work', 'aria-label': 'Back' }, icon('back', 20), h('span', { class: 'cb-w' }, 'Back')),
    h('ol', null, h('li', null, h('a', { href: '#/now' }, 'Overview')), proj ? h('li', null, h('a', { href: hrefFor('project', 'prj-' + proj.id) }, proj.name)) : null, h('li', { 'aria-current': 'page' }, cut(m.title, 30))));
}

export const pane = (ctx, S, m, compact) => h('section', { class: 'msn-graph', 'aria-label': 'Mission graph' }, crumb(ctx, S, m), graph(S, m, compact));

export function meta(ctx, S, m) {
  const cell = (k, v) => h('div', null, h('dt', null, k), h('dd', null, v));
  return h('dl', { class: 'msn-meta' }, cell('Project', link(hrefFor('project', 'prj-' + m.project), projName(ctx.sim, m.project))), cell('Branch', m.branch), cell('Status', badge('mission', m.state)));
}
