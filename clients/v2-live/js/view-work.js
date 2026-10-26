import { h } from './dom.js';
import { missionGroups } from '../term.js';
import { head, panel, dnote, missionRow, projName, word } from './views.js';

export function render(ctx) {
  const sim = ctx.sim, st = sim.state;
  const pf = ctx.ui.workProject, pn = pf && st.projects.find((p) => p.id === pf);
  const groups = missionGroups(sim).map((g) => (pn ? Object.assign({}, g, { items: g.items.filter((m) => m.project === pf) }) : g)).filter((g) => !pn || g.items.length);
  return h('div', null, head(ctx, 'Work'), h('div', { class: 'view' },
    dnote('E03', 'Missions grouped by what they wait on, as in V1; the spine shows where each one is (A13).'),
    pn ? h('div', { class: 'chips', role: 'group', 'aria-label': 'Project filter' }, h('span', { class: 'chip', 'aria-pressed': 'true' }, 'Project: ' + pn.name), h('button', { class: 'chip', type: 'button', 'data-key': 'work-all', onclick: () => { ctx.ui.workProject = null; ctx.render(); } }, 'Show all projects')) : null,
    ...groups.map((g) => panel(g.title, g.items.length, h('div', { class: 'stack' }, ...g.items.map((m) => missionRow(ctx, m, 'work'))))),
    panel('Ideas', st.ideas.length, h('div', { class: 'body' }, ...st.ideas.map((i) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, i.title), h('span', { class: 'b' }, projName(sim, i.project) + ' · ' + word('idea', i.state))))))));
}
