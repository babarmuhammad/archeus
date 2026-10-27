// Work: the one page for what is happening and what waits on you. The graph (js/constellation/workgraph.js) sits on top, the grouped list under it;
// both show the same missions and decisions and follow the route id, so selecting in one highlights the other and opens the inspector.
import { h } from './dom.js';
import { present } from '../core-words.js';
import { tr } from './i18n.js';
import * as store from './store.js';
import { head, panel, dnote, empty, missionRow, attentionItem, projName, word } from './views.js';
import { STATE, themeOf } from './map.js';
import { createWorkGraph } from './constellation/workgraph.js';

const LEGEND = [['needs-you', 'Needs you'], ['running', 'Running'], ['blocked', 'Blocked'], ['done', 'Done']];
const MAX_NODES = 12;
let graph = null;

// The graph survives the re-renders the simulation causes; app.js destroys it when the route leaves Work.
export function leave() { if (graph) graph.destroy(); graph = null; }

function modelOf(sim, pf) {
  const st = sim.state, rank = (m) => ({ needs_you: 0, active: 1, verifying: 1, reviewing: 1, blocked: 2, failed: 2, done: 4 })[present('mission', m.state).cls] ?? 3;
  const ms = Object.values(st.missions).filter((m) => !pf || m.project === pf).sort((a, b) => rank(a) - rank(b)).slice(0, MAX_NODES);
  const nodes = ms.map((m) => ({ id: m.id, kind: 'Mission', label: m.title, word: tr(word('mission', m.state)), project: projName(sim, m.project), state: STATE[present('mission', m.state).cls] || 'idle' }));
  const asks = Object.values(st.approvals).filter((a) => a.state === 'PENDING' && ms.some((m) => m.id === a.mission));
  for (const a of asks) nodes.push({ id: a.id, kind: 'Decision', label: tr(a.kind === 'plan' ? 'Approve plan' : 'Allow action'), word: tr('Needs you'), project: projName(sim, a.project), state: 'needs-you' });
  return { nodes, edges: asks.map((a) => ({ from: a.mission, to: a.id })) };
}

export function render(ctx) {
  const sim = ctx.sim, st = sim.state, sel = ctx.route.id, pf = ctx.ui.workProject, pn = pf && st.projects.find((p) => p.id === pf);
  const mine = (id) => !pn || id === pf;
  const att = sim.attention().filter((a) => mine(a.project_id)), cards = new Set(att.filter((a) => a.mission_id).map((a) => a.mission_id));
  const need = att.filter((a) => a.group === 'Decide' || a.group === 'Review'), stuck = att.filter((a) => a.group === 'Unblock');
  const rest = Object.values(st.missions).filter((m) => mine(m.project) && !cards.has(m.id)), cls = (m) => present('mission', m.state).cls;
  const active = rest.filter((m) => !['paused', 'done', 'inactive'].includes(cls(m))), paused = rest.filter((m) => cls(m) === 'paused'), done = rest.filter((m) => ['done', 'inactive'].includes(cls(m)));
  const model = modelOf(sim, pf), ids = new Set(model.nodes.map((n) => n.id));

  // Rows and cards carry data-link: a hover on one lights the other, and the route id marks the current one.
  const link = (el, ...keys) => {
    const own = keys.filter(Boolean), node = own.find((k) => ids.has(k));
    el.dataset.link = own.join(' ');
    if (sel && own.includes(sel)) el.setAttribute('aria-current', 'true');
    if (node) { el.addEventListener('pointerenter', () => graph.hover(node)); el.addEventListener('pointerleave', () => graph.hover(null)); }
    return el;
  };
  const card = (a) => h('div', { class: 'panel' }, link(attentionItem(ctx, a), a.ref, a.mission_id));
  const rows = (ms) => h('div', { class: 'stack' }, ...ms.map((m) => link(missionRow(ctx, m, 'work'), m.id)));
  const chip = (key, label, on, go) => h('button', { class: 'chip', type: 'button', 'aria-pressed': String(on), 'data-key': key, onclick: go }, label);
  const filter = h('div', { class: 'chips', role: 'group', 'aria-label': 'Project filter' },
    chip('work-all', pn ? 'Show all projects' : 'All projects', !pn, () => { ctx.ui.workProject = null; ctx.render(); }),
    ...st.projects.map((p) => chip('work-p-' + p.id, p.name, pf === p.id, () => { ctx.ui.workProject = pf === p.id ? null : p.id; ctx.render(); })));

  if (!graph) {
    graph = createWorkGraph(h('div'), { t: tr, theme: themeOf(), reduced: store.reducedMotion(), label: tr('Work graph: missions and decisions grouped by what they wait on. The list below has the same content.'),
      onSelect: (id) => ctx.nav(ctx.route.id === id ? '#/work' : '#/work/' + id),
      onReview: (id) => { const a = Object.values(sim.state.approvals).find((x) => x.state === 'PENDING' && x.mission === id); ctx.nav('#/work/' + (a ? a.id : id)); } });
    graph.element.addEventListener('wg-hover', (e) => document.querySelectorAll('[data-link]').forEach((x) => x.classList.toggle('is-linked', !!e.detail && x.dataset.link.split(' ').includes(e.detail))));
  }
  graph.setTheme(themeOf()); graph.setReduced(store.reducedMotion()); graph.update(model); graph.setSelection(ids.has(sel) ? sel : null);

  const list = h('div', { class: 'work-list' },
    h('section', { class: 'panel work-need' }, h('h2', null, h('span', { class: 'gt' }, 'Needs you'), h('span', { class: 'n' }, String(need.length))),
      need.length ? h('div', { class: 'att-rows' }, ...need.map(card)) : empty('Nothing waits on you.', 'clear')),
    active.length ? panel('Active', active.length, rows(active)) : null,
    stuck.length || paused.length ? panel('Blocked', stuck.length + paused.length, stuck.length ? h('div', { class: 'att-rows' }, ...stuck.map(card)) : null, paused.length ? rows(paused) : null) : null,
    done.length ? panel('Done', done.length, rows(done)) : null,
    panel('Ideas', st.ideas.filter((i) => mine(i.project)).length));
  return h('div', null, head(ctx, 'Work'), h('div', { class: 'view work-view' },
    h('div', { class: 'work-split' },
      h('div', { class: 'work-side' }, dnote('E03', 'One page for Work and Attention: missions and decisions grouped by what they wait on, as a graph and as a list. The spine shows where each mission is (A13); an obligation is a 12 % amber tint with its state in words (B09).'), filter),
      h('section', { class: 'work-graph', 'aria-label': tr('Work graph') }, graph.element, h('ul', { class: 'work-legend', 'aria-hidden': 'true' }, ...LEGEND.map(([s, w]) => h('li', { 'data-s': s }, h('span', { class: 'wl-dot' }), w)))),
      list)));
}
