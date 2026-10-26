// The mission page (concept 03 and 12): a graph of the mission on the left, the opaque inspector on the right. Sans titles, vector only, no glow.
// Only relations that exist in the record are drawn: a node without a record is left out with its arrows.
import { h, s } from './dom.js';
import { icon } from './icons.js';
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

function hex(cx, cy, r, cls) {
  const p = (i, k) => [cx + r * k * Math.cos(Math.PI / 6 + i * Math.PI / 3), cy + r * k * Math.sin(Math.PI / 6 + i * Math.PI / 3)];
  const v = [0, 1, 2, 3, 4, 5].map((i) => p(i, 1));
  return s('g', { class: 'g-poly ' + (cls || '') },
    s('polygon', { points: v.map((q) => q.join(',')).join(' ') }),
    s('path', { d: [1, 3, 5].map((i) => 'M' + cx + ' ' + cy + 'L' + v[i].join(' ')).join('') }));
}
function glyph(name, cx, cy, d) {
  const g = icon(name, d); g.setAttribute('x', cx - d / 2); g.setAttribute('y', cy - d / 2); g.setAttribute('class', 'g-ico');
  return g;
}
const text = (cls, x, y, t, anchor) => s('text', { class: cls, x, y, 'text-anchor': anchor || 'middle' }, t);
const arrow = (x1, y1, x2, y2) => s('line', { class: 'g-arr', x1, y1, x2, y2, 'marker-end': 'url(#g-head)' });

function graph(S, m) {
  const execs = Object.values(S.executions).filter((x) => x.mission === m.id).sort((a, b) => a.started_at - b.started_at), x = execs[execs.length - 1];
  const vs = Object.values(S.verifications).filter((v) => v.mission === m.id), v = vs[vs.length - 1];
  const rs = Object.values(S.reviews).filter((r) => r.mission === m.id), r = rs[rs.length - 1];
  const tasks = m.tasks.map((t) => S.tasks[t]), tk = tasks.find((t) => !['SUCCEEDED', 'SKIPPED'].includes(t.state)) || tasks[tasks.length - 1];
  const resTxt = v ? word('verification', v.state) : r ? word('review', r.state) : null;
  const svg = s('svg', { class: 'msn-svg', viewBox: '0 0 640 420', role: 'img', 'aria-label': 'Mission graph: ' + m.title, preserveAspectRatio: 'xMidYMid meet' },
    s('defs', null, s('marker', { id: 'g-head', viewBox: '0 0 8 8', refX: 7, refY: 4, markerWidth: 8, markerHeight: 8, orient: 'auto' }, s('path', { d: 'M1 1L7 4L1 7', class: 'g-ah' }))),
    s('g', { class: 'g-star' }, s('path', { d: 'M320 18V62M298 40H342M305 25L335 55M335 25L305 55' }), s('circle', { cx: 320, cy: 40, r: 3 })),
    text('g-core', 320, 82, 'ARCHEUS'),
    arrow(320, 92, 320, 114), text('arr-l', 332, 108, 'ORCHESTRATES', 'start'),
    hex(320, 190, 70, 'main'), glyph('terminal', 320, 190, 34),
    text('nm main', 320, 288, cut(m.title, 24)), text('sub', 320, 308, cut(projName({ state: S }, m.project) || '', 28) + (m.branch ? ' · ' + cut(m.branch, 22) : '')));
  if (x) {
    svg.append(arrow(250, 190, 156, 190), text('arr-l', 203, 180, 'EXECUTES'), hex(100, 190, 52), glyph('execution', 100, 190, 30),
      text('nm', 100, 266, harnessLabel(x.harness)), text('sub', 100, 286, 'Execution'));
  }
  if (v || r) {
    svg.append(arrow(390, 190, 484, 190), text('arr-l', 437, 180, 'RESULTS IN'), hex(540, 190, 52), glyph('security', 540, 190, 30),
      text('nm', 540, 266, v ? 'Verification' : 'Review'), text('sub', 540, 286, resTxt));
  }
  if (tk) {
    svg.append(arrow(272, 246, 206, 316), text('arr-l', 232, 274, 'USES', 'end'), hex(170, 350, 40), glyph('task', 170, 350, 24),
      text('nm', 170, 412, cut(tk.title, 20)));
  }
  if (resTxt && tk) {
    svg.append(arrow(214, 350, 422, 350), text('arr-l', 318, 340, 'PRODUCES'), hex(470, 350, 40), glyph('repository', 470, 350, 24), text('nm', 470, 412, 'Results'));
    if (v) svg.append(arrow(520, 246, 490, 306), text('arr-l', 516, 282, 'VERIFIES', 'start'));
  }
  return svg;
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

export const pane = (ctx, S, m) => h('section', { class: 'msn-graph', 'aria-label': 'Mission graph' }, crumb(ctx, S, m), graph(S, m));

export function meta(ctx, S, m) {
  const cell = (k, v) => h('div', null, h('dt', null, k), h('dd', null, v));
  return h('dl', { class: 'msn-meta' }, cell('Project', link(hrefFor('project', 'prj-' + m.project), projName(ctx.sim, m.project))), cell('Branch', m.branch), cell('Status', badge('mission', m.state)));
}
