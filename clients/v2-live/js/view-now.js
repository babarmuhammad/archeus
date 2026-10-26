import { h } from './dom.js';
import { present } from '../core-words.js';
import { clockLabel } from '../sim.js';
import { word, panel, dnote, empty, missionRow, attentionItem, mapPanel, controlBody } from './views.js';

function counters(ctx) {
  const sim = ctx.sim, ms = Object.values(sim.state.missions);
  const c = (n, label, role, href) => h('a', { class: 'ctr', 'data-role': role, href }, h('b', null, String(n)), h('span', null, label));
  return h('nav', { class: 'counters', 'aria-label': 'Counts' },
    c(sim.attention().filter((i) => i.kind !== 'knowledge').length, 'needs you', 'needs_you', '#/attention'), c(sim.liveWork().length, 'running', 'active', '#/work'),
    c(ms.filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED').length, 'stopped', 'blocked', '#/work'), c(ms.filter((m) => present('mission', m.state).cls === 'verifying').length, 'verifying', 'verifying', '#/work'));
}

export function render(ctx) {
  const sim = ctx.sim, st = sim.state, att = sim.attention();
  const decide = att.filter((a) => a.group === 'Decide').slice(0, 3);
  const live = Object.values(st.missions).filter((m) => ['active', 'verifying', 'reviewing'].includes(present('mission', m.state).cls));
  const upcoming = Object.values(st.missions).filter((m) => ['planning', 'approved'].includes(present('mission', m.state).cls));
  const recent = st.events.filter((e) => /state_changed$/.test(e.type) && e.subject.kind === 'mission').slice(-6).reverse();
  return h('div', { class: 'view' },
    h('div', { class: 'now-hero' }, h('p', { class: 'state-sentence', 'data-key': 'sentence' }, sim.sentence()), h('p', { class: 'sub2' }, 'The sentence is built only from Core state words and counts.'), dnote('A10', 'The serif display font is used for this one line only.'), dnote('A12', 'The core mark sits on the centre of the live map, with its static twin under reduced motion.')),
    counters(ctx),
    h('section', { class: 'ctlbar', 'aria-label': 'Pause, resume and emergency stop' }, controlBody(ctx, true)),
    h('div', { class: 'cols two now-cols' },
      mapPanel(ctx, false),
      h('div', { class: 'col', style: 'gap:var(--gut)' },
        panel('Needs you', att.filter((a) => a.group === 'Decide').length, decide.length ? h('div', { class: 'stack' }, ...decide.map((a) => attentionItem(ctx, a))) : empty('Nothing is waiting for a decision.', 'clear'),
          att.filter((a) => a.group !== 'Decide').length ? h('div', { class: 'actions', style: 'padding:12px 16px 16px' }, h('a', { class: 'btn', href: '#/attention' }, att.filter((a) => a.group !== 'Decide').length + ' more in Attention')) : null),
        panel('Happening now', live.length, live.length ? h('div', { class: 'stack' }, ...live.map((m) => missionRow(ctx, m, 'now'))) : empty('Nothing is running.', 'missions')))),
    h('div', { class: 'cols eq' },
      panel('Upcoming', upcoming.length, upcoming.length ? h('div', { class: 'stack' }, ...upcoming.map((m) => missionRow(ctx, m, 'now'))) : empty('Nothing is planned or approved.')),
      panel('Recent decisions and changes', recent.length, h('div', { class: 'body' }, ...recent.map((e) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, (st.missions[e.subject.id] || { title: e.subject.id }).title, ': ', word('mission', e.payload.from), ' to ', word('mission', e.payload.to)), h('span', { class: 'b' }, clockLabel(e.at) + (e.actor === 'device' ? ' · you' : ' · Core')))), recent.length ? null : empty('Nothing has changed yet.')))));
}
