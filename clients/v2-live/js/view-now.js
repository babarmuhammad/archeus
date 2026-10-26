import { h } from './dom.js';
import { present } from '../core-words.js';
import { clockLabel } from '../sim.js';
import { tr } from './i18n.js';
import { word, panel, empty, missionRow, attentionItem, controlBody } from './views.js';
import { mapBox, syncMap } from './map.js';

function counters(ctx) {
  const sim = ctx.sim, ms = Object.values(sim.state.missions);
  const c = (n, label, role, href) => h('a', { class: 'ctr', 'data-role': role, href }, h('b', null, String(n)), h('span', null, label));
  return h('nav', { class: 'counters', 'aria-label': 'Counts' },
    c(sim.attention().filter((i) => i.kind !== 'knowledge').length, 'needs you', 'needs_you', '#/attention'), c(sim.liveWork().length, 'running', 'active', '#/work'),
    c(ms.filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED').length, 'stopped', 'blocked', '#/work'), c(ms.filter((m) => present('mission', m.state).cls === 'verifying').length, 'verifying', 'verifying', '#/work'));
}

// The headline clears the top of the scene and the drawer strip the bottom; both shrink with the width.
const nowInset = (w) => ({ top: w >= 1000 ? 170 : w >= 600 ? 150 : 150, bottom: 76, left: 24, right: 24 });

export function render(ctx) {
  const sim = ctx.sim, st = sim.state, att = sim.attention();
  const decide = att.filter((a) => a.group === 'Decide');
  const live = Object.values(st.missions).filter((m) => ['active', 'verifying', 'reviewing'].includes(present('mission', m.state).cls));
  const upcoming = Object.values(st.missions).filter((m) => ['planning', 'approved'].includes(present('mission', m.state).cls));
  const recent = st.events.filter((e) => /state_changed$/.test(e.type) && e.subject.kind === 'mission').slice(-6).reverse();
  const calm = !att.some((a) => a.kind !== 'knowledge') && !sim.liveWork().length;
  const box = mapBox('now', true, nowInset);
  ctx.mounts.push(() => syncMap(ctx, 'now'));
  const open = ctx.ui.nowDrawer === true;
  const toggle = (e) => {
    ctx.ui.nowDrawer = !ctx.ui.nowDrawer;
    const d = e.currentTarget.closest('.now-drawer');
    d.dataset.open = String(ctx.ui.nowDrawer === true);
    e.currentTarget.setAttribute('aria-expanded', String(ctx.ui.nowDrawer === true));
  };
  const drawer = h('section', { class: 'now-drawer', 'data-open': String(open), 'aria-label': 'Details' },
    h('div', { class: 'now-strip' }, counters(ctx), h('button', { class: 'now-toggle', type: 'button', 'aria-expanded': String(open), onclick: toggle }, tr('Details'))),
    h('div', { class: 'now-body' },
      h('section', { class: 'ctlbar', 'aria-label': 'Pause, resume and emergency stop' }, controlBody(ctx, true)),
      h('div', { class: 'now-panels' },
        panel('Needs you', decide.length, decide.length ? h('div', { class: 'stack' }, ...decide.slice(0, 3).map((a) => attentionItem(ctx, a))) : empty('Nothing is waiting for a decision.'),
          att.filter((a) => a.group !== 'Decide').length ? h('div', { class: 'actions', style: 'padding:12px 16px 16px' }, h('a', { class: 'btn', href: '#/attention' }, att.filter((a) => a.group !== 'Decide').length + ' more in Attention')) : null),
        panel('Happening now', live.length, live.length ? h('div', { class: 'stack' }, ...live.map((m) => missionRow(ctx, m, 'now'))) : empty('Nothing is running.')),
        panel('Upcoming', upcoming.length, upcoming.length ? h('div', { class: 'stack' }, ...upcoming.map((m) => missionRow(ctx, m, 'now'))) : empty('Nothing is planned or approved.')),
        panel('Recent decisions and changes', recent.length, h('div', { class: 'body' }, ...recent.map((e) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, (st.missions[e.subject.id] || { title: e.subject.id }).title, ': ', word('mission', e.payload.from), ' to ', word('mission', e.payload.to)), h('span', { class: 'b' }, clockLabel(e.at) + (e.actor === 'device' ? ' · you' : ' · Core')))), recent.length ? null : empty('Nothing has changed yet.'))))));
  return h('div', { class: 'view now-view', 'data-calm': String(calm) },
    h('div', { class: 'now-scene' }, box),
    h('div', { class: 'now-hero' }, h('p', { class: 'eyebrow' }, tr('Overview')),
      h('h1', { class: 'state-sentence', 'data-key': 'sentence' }, calm ? tr('Nothing running. Tell Archeus what to do.') : sim.sentence()),
      h('p', { class: 'lede' }, calm ? tr('Archeus is quiet. Tell it what to do next, or open a project.') : tr('Live constellation of your work. Missions, projects and ideas in context, moving forward together.'))),
    drawer);
}
