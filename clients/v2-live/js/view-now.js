import { h } from './dom.js';
import { present } from '../core-words.js';
import { clockLabel } from '../sim.js';
import { tr } from './i18n.js';
import { word, panel, empty, missionRow, attentionItem, projName } from './views.js';
import { icon } from './icons.js';
import * as store from './store.js';
import { mapBox, syncMap, buildOverview } from './map.js';
import { dockNode } from './chat.js';
import * as motion from './motion.js';

// The phone shows the four counts as its headline; the desktop headline already says them.
function counters(ctx) {
  const sim = ctx.sim, ms = Object.values(sim.state.missions);
  const c = (n, label, role, href) => h('a', { class: 'ctr', 'data-role': role, 'data-zero': String(n === 0), href }, h('b', null, String(n)), h('span', null, label));
  return h('nav', { class: 'counters', 'aria-label': 'Counts' },
    c(sim.attention().filter((i) => i.kind !== 'knowledge').length, 'needs you', 'needs_you', '#/work'), c(sim.liveWork().length, 'running', 'active', '#/work'),
    c(ms.filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED').length, 'stopped', 'blocked', '#/work'), c(ms.filter((m) => present('mission', m.state).cls === 'verifying').length, 'verifying', 'verifying', '#/work'));
}

const KIND = [[/need/, 'need'], [/running/, 'run'], [/stopped/, 'stop']];
// The headline counts wear the state colour: amber needs you, blue running, red stopped.
const sentenceNodes = (text) => text.split(' · ').flatMap((part, i) => [i ? ' · ' : null, h('span', { class: 'ss ss-' + ((KIND.find(([re]) => re.test(part)) || [])[1] || 'plain') }, tr(part))]);
function ledgerText(l) {
  if (!l.done) return tr('Archeus has not completed a mission today.');
  const top = l.byProject.slice(0, 2).map((x) => `${x.n} in ${x.name}`), more = l.byProject.length - 2;
  return tr(`Archeus completed ${l.done} ${l.done === 1 ? 'mission' : 'missions'} today:`) + ' ' + top.join(', ') + (more > 0 ? ', ' + tr(`+${more} more projects`) : '') + '.';
}

// The headline clears the top of the scene and the drawer strip the bottom; both shrink with the width.
let calmNow = false;
const phone = () => document.getElementById('app').clientWidth < 600;
// The slim Tell dock (56 px) stands on the status strip (56 px) and the map keeps clear of both. While the Details sheet is open the scene box itself gives up the area the sheet takes
// (its right side when wide, its bottom when narrow, see now.css), so the map lays itself out again in what is left and the strip and dock are not in it.
let sheetOn = false;
const viewWidth = () => { const e = document.querySelector('.now-view'); return e ? e.clientWidth : 1e4; };
// The map starts under the headline whatever its height (one or two lines of headline, the lede), measured on the page.
const heroBottom = () => { const e = document.querySelector('.now-hero'); return e ? Math.round(e.offsetTop + e.offsetHeight + 8) : 150; };
const DOCK = 56 + 12 + 14, BAND = 76;
const nowInset = (w, hh) => calmNow ? { top: 16, bottom: phone() ? 170 : Math.max(250, Math.round(hh * .33)) + DOCK, left: 24, right: 24 } : phone() ? { top: 16, bottom: 16, left: 16, right: 16 } : { top: heroBottom(), bottom: sheetOn && viewWidth() < 900 ? 16 : BAND + 12, left: 24, right: 24 };

// Calm (concept 07): the bottom band says what is true now (headline and Tell), what was verified today and the known projects.
function calmBand(ctx) {
  const st = ctx.sim.state, ms = Object.values(st.missions), done = ms.filter((m) => m.state === 'COMPLETED');
  const sentence = tr('Nothing running. Tell Archeus what to do.').split(/(?<=\.) /);
  const dot = (s) => h('span', { class: 'cdot', 'data-s': s, 'aria-hidden': 'true' });
  const projects = st.projects.map((p) => {
    const own = ms.filter((m) => m.project === p.id), count = own.length + st.ideas.filter(i => i.project === p.id && i.state === 'CAPTURED').length, last = Math.max(0, ...own.map((m) => m.updated_at || 0));
    return h('li', null, h('a', { class: 'cproj', href: '#/work', 'data-proj': p.id, onclick: (e) => { e.preventDefault(); ctx.ui.workProject = p.id; ctx.nav('#/work'); } },
      dot(own.length && own.every((m) => m.state === 'COMPLETED') ? 'done' : 'idle'),
      h('span', { class: 'ctext' }, h('b', null, p.name), h('small', null, tr(`${count} ${count === 1 ? 'item' : 'items'}`) + (last ? ' · ' + clockLabel(last) : ''))), h('span', { class: 'cchev', 'aria-hidden': 'true' }, '›')));
  });
  return h('section', { class: 'calm-band', 'aria-label': tr('Today and known projects') },
    h('div', { class: 'calm-say' },
      h('h1', { class: 'state-sentence calm', 'data-key': 'sentence' }, ...sentence.map((t) => h('span', null, t))),
      h('button', { class: 'tell-cta', type: 'button', onclick: () => document.querySelector('[data-key="tell"]')?.click() }, h('span', null, tr('Tell')), h('span', { class: 'tell-arrow', 'aria-hidden': 'true' }, '→'))),
    h('div', { class: 'calm-col calm-today' }, h('p', { class: 'eyebrow' }, tr('Today')), h('p', { class: 'calm-big' }, tr(`${done.length} verified`)),
      h('ul', null, ...done.slice(0, 3).map((m) => h('li', null, dot('done'), h('span', { class: 'ctext' }, h('b', null, m.title)), h('span', { class: 'cword' }, tr('Done')))))),
    h('div', { class: 'calm-col calm-known' }, h('p', { class: 'eyebrow' }, tr('Known projects')), h('ul', null, ...projects)));
}

function viewSwitch(ctx) {
  const cur = store.get('overview'), opt = (id, ic, label) => h('button', { class: 'vs-btn', type: 'button', 'aria-pressed': String(cur === id), 'aria-label': tr(label), title: tr(label), 'data-key': 'vs-' + id, onclick: () => { if (cur !== id) { store.set('overview', id); ctx.render(); } } }, icon(ic, 20));
  return h('div', { class: 'view-switch', role: 'group', 'aria-label': tr('Overview view') }, opt('projects', 'viewgrid', 'Projects view'), opt('network', 'viewnet', 'Network view'));
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
  sheetOn = open && !calm;
  const toggle = (e) => {
    const closing = ctx.ui.nowDrawer === true, d = e.currentTarget.closest('.now-drawer'), body = d.querySelector('.now-body');
    // the sheet comes from its edge (the right when wide, the bottom when narrow) and leaves the same way, a little faster; on the phone it is part of the page and does not fly
    const fly = phone() ? null : viewWidth() >= 900 ? { x: 24, y: 0 } : { x: 0, y: 24 };
    if (closing && fly) motion.exitClone(body, { ...fly, dur: 2 });
    ctx.ui.nowDrawer = !ctx.ui.nowDrawer; sheetOn = ctx.ui.nowDrawer === true;
    d.dataset.open = String(ctx.ui.nowDrawer === true);
    d.closest('.now-view').dataset.sheet = String(ctx.ui.nowDrawer === true);
    e.currentTarget.setAttribute('aria-expanded', String(ctx.ui.nowDrawer === true));
    if (!closing && fly) motion.enter(body, { ...fly, dur: 3 });
  };
  const first = att.find((a) => a.group === 'Decide' || a.group === 'Review'), fm = first && first.mission_id ? st.missions[first.mission_id] : null, ap = first && first.kind === 'approval' ? st.approvals[first.ref] : null;
  const card = first && first.kind !== 'knowledge' ? h('article', { class: 'pn-card', 'data-key': 'pn-card' },
    h('div', { class: 'pn-top' }, h('span', { class: 'pn-dot', 'aria-hidden': 'true' }), h('div', null, h('p', { class: 'pn-title' }, fm ? fm.title : first.reason), h('p', { class: 'pn-origin' }, tr('Origin') + ' ' + (projName(sim, first.project_id) || '-'))), icon('attention', 28)),
    h('p', { class: 'pn-k' }, tr('What') + ':'), h('p', { class: 'pn-v' }, ap ? ap.presented.what : first.reason),
    ap ? h('p', { class: 'pn-k' }, tr('Why') + ':') : null, ap ? h('p', { class: 'pn-v' }, ap.presented.why) : null,
    h('a', { class: 'pn-review', href: first.kind === 'approval' ? '#/work/' + first.ref : '#/work/' + first.mission_id }, tr('Review'))) : null;
  const drawer = h('section', { class: 'now-drawer', 'data-open': String(open), 'aria-label': 'Details' },
    h('div', { class: 'now-strip' }, phone() ? counters(ctx) : null, h('button', { class: 'now-toggle', type: 'button', 'aria-expanded': String(open), 'aria-controls': 'now-details', 'data-key': 'now-details-btn', 'aria-label': tr('Details'), onclick: toggle }, tr('Details'))),
    card,
    h('div', { class: 'now-body', id: 'now-details' },
      h('div', { class: 'now-panels' },
        panel('Needs you', decide.length, decide.length ? h('div', { class: 'stack' }, ...decide.slice(0, 3).map((a) => attentionItem(ctx, a))) : empty('Nothing is waiting for a decision.'),
          att.filter((a) => a.group !== 'Decide').length ? h('div', { class: 'actions', style: 'padding:12px 16px 16px' }, h('a', { class: 'btn', href: '#/work' }, att.filter((a) => a.group !== 'Decide').length + ' more in Attention')) : null),
        panel('Happening now', live.length, live.length ? h('div', { class: 'stack' }, ...live.map((m) => missionRow(ctx, m, 'now'))) : empty('Nothing is running.')),
        panel('Upcoming', upcoming.length, upcoming.length ? h('div', { class: 'stack' }, ...upcoming.map((m) => missionRow(ctx, m, 'now'))) : empty('Nothing is planned or approved.')),
        panel('Recent decisions and changes', recent.length, h('div', { class: 'body' }, ...recent.map((e) => h('div', { class: 'row-line' }, h('span', { class: 'a' }, (st.missions[e.subject.id] || { title: e.subject.id }).title, ': ', word('mission', e.payload.from), ' to ', word('mission', e.payload.to)), h('span', { class: 'b' }, clockLabel(e.at) + (e.actor === 'device' ? ' · you' : ' · Core')))), recent.length ? null : empty('Nothing has changed yet.'))))));
  return h('div', { class: 'now-wrap' }, h('div', { class: 'view now-view', 'data-calm': String(calm), 'data-sheet': String(open && !calm) },
    h('div', { class: 'now-scene' }, box),
    calm ? calmBand(ctx) : h('div', { class: 'now-hero' },
      h('h1', { class: 'state-sentence', 'data-key': 'sentence' }, ...sentenceNodes(sim.sentence())),
      h('p', { class: 'ledger', 'data-key': 'ledger' }, ledgerText(buildOverview(sim).ledger))),
    calm ? null : viewSwitch(ctx),
    calm ? null : drawer,
    phone() ? null : h('div', { class: 'tell-dock' }, dockNode(ctx))));
}
