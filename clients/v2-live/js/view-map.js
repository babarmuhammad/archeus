import { h } from './dom.js';
import { head, panel, dnote, missionRow, mapPanel } from './views.js';

export function render(ctx) {
  const sim = ctx.sim, st = sim.state;
  return h('div', null, head(ctx, 'Map'), h('div', { class: 'view' },
    dnote('A03', 'A vector constellation drawn from the simulation and redrawn at every size. Selecting a star opens it; the list beside it is the text mirror with the same content.'),
    h('div', { class: 'cols two' }, mapPanel(ctx, true, 'Constellation'),
      h('div', { style: 'display:flex;flex-direction:column;gap:var(--gut)' },
        ...st.projects.map((p) => { const ms = Object.values(st.missions).filter((m) => m.project === p.id); return panel(p.name, ms.length, h('p', { class: 'lede' }, p.note), h('div', { class: 'stack' }, ...ms.map((m) => missionRow(ctx, m, 'map')))); })))));
}
