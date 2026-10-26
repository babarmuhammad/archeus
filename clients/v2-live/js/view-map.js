import { h } from './dom.js';
import { tr } from './i18n.js';
import { panel, missionRow } from './views.js';
import { mapBox, syncMap } from './map.js';

const mapInset = (w) => ({ top: w >= 600 ? 110 : 96, bottom: 76, left: 24, right: 24 });

export function render(ctx) {
  const st = ctx.sim.state, open = ctx.ui.mapDrawer === true;
  const box = mapBox('map', true, mapInset);
  ctx.mounts.push(() => syncMap(ctx, 'map'));
  const toggle = (e) => {
    ctx.ui.mapDrawer = !ctx.ui.mapDrawer;
    e.currentTarget.closest('.now-drawer').dataset.open = String(ctx.ui.mapDrawer === true);
    e.currentTarget.setAttribute('aria-expanded', String(ctx.ui.mapDrawer === true));
  };
  const k = (g, w) => h('span', { class: 'k' }, h('span', { 'aria-hidden': 'true' }, g), ' ' + w);
  return h('div', { class: 'view now-view map-view' },
    h('div', { class: 'now-scene' }, box),
    h('div', { class: 'now-hero' }, h('p', { class: 'eyebrow' }, tr('Map')), h('h1', { class: 'map-title' }, tr('Constellation'))),
    h('section', { class: 'now-drawer', 'data-open': String(open), 'aria-label': 'Text mirror' },
      h('div', { class: 'now-strip' }, h('div', { class: 'legend' }, k('⬡', 'Project'), k('●', 'Mission'), k('▲', 'Execution'), k('◆', 'Decision')),
        h('button', { class: 'now-toggle', type: 'button', 'aria-expanded': String(open), onclick: toggle }, tr('Details'))),
      h('div', { class: 'now-body' }, h('div', { class: 'now-panels' },
        ...st.projects.map((p) => { const ms = Object.values(st.missions).filter((m) => m.project === p.id); return panel(p.name, ms.length, h('p', { class: 'lede' }, p.note), h('div', { class: 'stack' }, ...ms.map((m) => missionRow(ctx, m, 'map')))); })))));
}
