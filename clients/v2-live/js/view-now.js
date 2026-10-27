import { h } from './dom.js';
import { present } from '../core-words.js';
import { clockLabel } from '../sim.js';
import { tr } from './i18n.js';
import { word, panel, empty, missionRow, attentionItem } from './views.js';
import { mapBox, syncMap } from './map.js';

function counters(ctx) {
  const sim = ctx.sim, ms = Object.values(sim.state.missions);
  const c = (n, label, role, href) => h('a', { class: 'ctr', 'data-role': role, href }, h('b', null, String(n)), h('span', null, label));
  return h('nav', { class: 'counters', 'aria-label': 'Counts' },
    c(sim.attention().filter((i) => i.kind !== 'knowledge').length, 'needs you', 'needs_you', '#/attention'), c(sim.liveWork().length, 'running', 'active', '#/work'),
    c(ms.filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED').length, 'stopped', 'blocked', '#/work'), c(ms.filter((m) => present('mission', m.state).cls === 'verifying').length, 'verifying', 'verifying', '#/work'));
}

// The headline clears the top of the scene and the drawer strip the bottom; both shrink with the width.
let calmNow = false;
const nowInset = (w, hh) => calmNow ? { top: 16, bottom: w < 600 ? 170 : Math.max(250, Math.round(hh * .33)), left: 24, right: 24 } : { top: w >= 1000 ? 170 : 150, bottom: 76, left: 24, right: 24 };

// Calm (concept 07): the bottom band says what is true now (headline and Tell), what was verified today and the known projects.
function calmBand(ctx) {
  const st = ctx.sim.state, ms = Object.values(st.missions), done = ms.filter((m) => m.state === 'COMPLETED');
  const sentence = tr('Nothing running. Tell Archeus what to do.').split(/(?<=\.) /);
  const dot = (s) => h('span', { class: 'cdot', 'data-s': s, 'aria-hidden': 'true' });
  const projects = st.projects.map((p) => {
    const own = ms.filter((m) => m.project === p.id), last = Math.max(0, ...own.map((m) => m.updated_at || 0));
    return h('li', null, h('a', { class: 'cproj', href: '#/work', 'data-proj': p.id, onclick: (e) => { e.preventDefault(); ctx.ui.workProject = p.id; ctx.nav('#/work'); } },
      dot(own.length && own.every((m) => m.state === 'COMPLETED') ? 'done' : 'idle'),
      h('span', { class: 'ctext' }, h('b', null, p.name), h('small', null, tr(`${own.length} ${own.length === 1 ? 'item' : 'items'}`) + (last ? ' · ' + clockLabel(last) : ''))), h('span', { class: 'cchev', 'aria-hidden': 'true' }, '›')));
  });
  return h('section', { class: 'calm-band', 'aria-label': tr('Today and known projects') },
    h('div', { class: 'calm-say' },
      h('h1', { class: 'state-sentence calm', 'data-key': 'sentence' }, ...sentence.map((t) => h('span', null, t))),
      h('button', { class: 'tell-cta', type: 'button', onclick: () => document.querySelector('[data-key="tell"]')?.click() }, h('span', null, tr('Tell')), h('span', { class: 'tell-arrow', 'aria-hidden': 'true' }, '→'))),
    h('div', { class: 'calm-col calm-today' }, h('p', { class: 'eyebrow' }, tr('Today')), h('p', { class: 'calm-big' }, tr(`${done.length} verified`)),
      h('ul', null, ...done.slice(0, 3).map((m) => h('li', null, dot('done'), h('span', { class: 'ctext' }, h('b', null, m.title)), h('span', { class: 'cword' }, tr('Done')))))),
    h('div', { class: 'calm-col calm-known' }, h('p', { class: 'eyebrow' }, tr('Known projects')), h('ul', null, ...projects)));
}

export function render(ctx) {
  const sim = ctx.sim, st = sim.state, att = sim.attention();
  const decide = att.filter((a) => a.group === 'Decide');
  const live = Object.values(st.missions).filter((m) => ['active', 'verifying', 'reviewing'].includes(present('mission', m.state).cls));
  const upcoming = Object.values(st.missions).filter((m) => ['planning', 'approved'].includes(present('mission', m.state).cls));
  const recent = st.events.filter((e) => /state_changed$/.test(e.type) && e.subject.kind === 'mission').slice(-6).reverse();
  const calm = sim.sentence() === 'Nothing needs you.';
  calmNow = calm;
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
      h('div', { class: 'now-panels' },
        panel('Needs you', decide.length, decide.length ? h('div', { class: 'stack' }, ...decide.slice(0, 3).map((a) => attentionItem(ctx, a))) : empty('Nothing is waiting for a decision.'),
          att.filter((a) => a.group !== 'Decide').length ? h('div', { class: 'actions', style: 'padding:12px 16px 16px' }, h('a', { class: 'btn', href: '#/attention' }, att.filter((a) => a.group !== 'Decide').length + ' more in Attention')) : null),
        panel('Happening now', live.length, live.length ? h('div', { class: 'stack' }, ...live.map((m) => missionRow(ctx, m, 'now'))) : empty('Nothing is running.')),
        panel('Upcoming', upcoming.length, upcoming.length ? h('div', { class: 'stack' }, ...upcoming.map((m) => missionRow(ctx, m, 'now'))) : empty('Nothing is planned or approved.')),
        panel('Recent decisions and changes', recent.length, h('div', { class: 'body' }, ...recent.map((e) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, (st.missions[e.subject.id] || { title: e.subject.id }).title, ': ', word('mission', e.payload.from), ' to ', word('mission', e.payload.to)), h('span', { class: 'b' }, clockLabel(e.at) + (e.actor === 'device' ? ' · you' : ' · Core')))), recent.length ? null : empty('Nothing has changed yet.'))))));
  return h('div', { class: 'now-wrap' }, h('div', { class: 'view now-view', 'data-calm': String(calm) },
    h('div', { class: 'now-scene' }, box),
    calm ? calmBand(ctx) : h('div', { class: 'now-hero' }, h('p', { class: 'eyebrow' }, tr('Overview')),
      h('h1', { class: 'state-sentence', 'data-key': 'sentence' }, sim.sentence()),
      h('p', { class: 'lede' }, tr('Live constellation of your work. Missions, projects and ideas in context, moving forward together.'))),
    calm ? null : drawer));
}
