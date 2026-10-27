// Phone shell (below 600 px): the bottom bar Tell | Places | Stop, and the Places sheet that lists every destination and the projects.
import { h } from './dom.js';
import { icon } from './icons.js';
import { ROUTES } from './views.js';

export function buildBottom({ tell, places, stop }) {
  const b = (key, ic, label, fn, cls = '') => h('button', { class: 'bb-item ' + cls, type: 'button', 'data-key': key, onclick: fn }, icon(ic, 24), h('span', null, label), key === 'bb-places' ? h('span', { class: 'count', hidden: true }) : null);
  return h('nav', { class: 'bottombar', 'aria-label': 'Main' }, b('bb-tell', 'chat', 'Tell', tell), b('bb-places', 'places', 'Places', places), b('bb-stop', 'estop', 'Stop', stop, 'bb-stop'));
}

export function syncBottom(root, { engaged, placesOpen, count }) {
  const stop = root.querySelector('[data-key="bb-stop"] span'), pl = root.querySelector('[data-key="bb-places"]');
  if (stop) { stop.textContent = engaged ? 'Re-arm' : 'Stop'; stop.parentElement.setAttribute('aria-label', engaged ? 'Re-arm new work' : 'Emergency stop all missions'); }
  if (pl) { pl.setAttribute('aria-expanded', String(!!placesOpen)); const c = pl.querySelector('.count'); c.hidden = !count; c.textContent = String(count); c.setAttribute('aria-label', count + ' need you'); }
}

// Same destinations and dividers as the desktop rail, then PROJECTS. Every row is 56 px; Work carries the count of what needs you.
export function placesSheet(ctx, { close, projState, projectStates, count }) {
  const ui = ctx.ui, here = (id) => ctx.route.name === id;
  const go = (href) => (e) => { ui.placesOpen = false; if (location.hash === href) { e.preventDefault(); ctx.render(); } };
  const row = (href, ic, label, id, extra) => h('a', { class: 'pl-item', href, 'data-key': 'places-route-' + id, 'data-route': id, 'aria-current': here(id) ? 'page' : null, onclick: go(href) }, icon(ic, 24), h('span', { class: 'nl' }, label), extra || null);
  const items = ROUTES.flatMap((r) => [row('#/' + r.id, r.icon, r.id === 'now' ? 'Overview' : r.label, r.id, r.id === 'work' && count ? h('span', { class: 'count', 'aria-label': count + ' need you' }, String(count)) : null),
    ['chat', 'extensions'].includes(r.id) ? h('div', { class: 'rail-sep' }) : null]);
  const projects = ctx.sim.state.projects.map((p) => h('a', { class: 'pl-item', href: '#/work', 'data-key': 'places-project-' + p.id, 'data-proj': p.id, onclick: (e) => { e.preventDefault(); ui.placesOpen = false; ui.workProject = p.id; ctx.nav('#/work'); } },
    h('span', { class: 'pdot', 'data-s': projState(p), 'aria-hidden': 'true' }), h('span', { class: 'nl' }, p.name), h('span', { class: 'vh pl-state' }, projectStates[projState(p)])));
  const sheet = h('section', { class: 'places', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Places' },
    h('div', { class: 'grab', 'aria-hidden': 'true' }),
    h('div', { class: 'pl-head' }, h('h2', null, 'Places'), h('button', { class: 'btn quiet', type: 'button', 'data-key': 'places-x', 'aria-label': 'Close', onclick: close }, icon('close', 20))),
    h('div', { class: 'pl-list' }, ...items, row('#/terminal', 'terminal', 'Terminal view', 'terminal'), h('div', { class: 'rail-sep' }), h('p', { class: 'eyebrow rail-eye' }, 'Projects'), ...projects));
  sheet.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(); } });
  return h('div', { class: 'pl-wrap' }, h('div', { class: 'pl-scrim', 'aria-hidden': 'true', onclick: close }), sheet);
}
