// Phone shell (below 600 px): the bottom bar drawn from slots(), the 48 px top bar, and what goes inside the Places and safety sheets.
// The state (which slot is current, the badge, Re-arm) is phone-model.js; the sheets themselves are js/sheet.js.
import { h } from './dom.js';
import { icon } from './icons.js';
import { star } from './brand.js';
import { BAR, slots } from './phone-model.js';

// ---------- bottom bar ----------
// on(slot, event) runs for a tap on the slot. A route slot's page is the first of its `routes` in BAR, so the bar is changed by editing BAR alone.
export function buildBottom(on) {
  return h('nav', { class: 'bottombar', 'aria-label': 'Main' }, ...BAR.map((s) => h('button', { class: 'bb-item' + (s.primary ? ' bb-primary' : '') + (s.danger ? ' bb-stop' : ''), type: 'button', 'data-key': 'bb-' + s.id, onclick: (e) => on(s, e) },
    h('span', { class: 'bb-ic' }, icon(s.icon, 24), h('span', { class: 'count', 'aria-hidden': 'true', hidden: true })), h('span', { class: 'bb-lab' }, s.label))));
}

export function syncBottom(root, state) {
  for (const s of slots(state)) {
    const b = root.querySelector('[data-key="bb-' + s.id + '"]');
    if (!b) continue;
    b.querySelector('.bb-lab').textContent = s.label;
    b.setAttribute('aria-label', s.aria);
    b.toggleAttribute('data-current', s.current);
    if (s.kind === 'route' && s.current) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    if (s.expanded === undefined) b.removeAttribute('aria-expanded'); else b.setAttribute('aria-expanded', String(s.expanded));
    b.toggleAttribute('data-engaged', s.id === 'stop' && s.label === 'Re-arm');
    const c = b.querySelector('.count');
    c.hidden = !s.badge; c.textContent = s.badge || '';
  }
}

// ---------- top bar ----------
// Star (Overview), the page title when the page's own heading is a bare label, the SIMULATED tag when the prototype toolbar row is folded away (a button that opens the
// prototype tools, a plain note in an embedded pane), the safety status with its word, and search.
export function topbarParts({ title, tag, playing, engaged, safetyOpen, on }) {
  const glyph = h('span', { class: 'g', 'aria-hidden': 'true' }, playing ? '◆' : '◇');
  return [
    h('button', { class: 'tb-home', type: 'button', 'data-key': 'home', 'aria-label': 'Overview', onclick: on.home }, star(24)),
    title ? h('span', { class: 'tb-title' }, title) : h('span', { class: 'tb-fill' }),
    tag === 'tools' ? h('button', { class: 'sim-badge', type: 'button', 'data-key': 'tools', 'data-sim': playing ? 'playing' : 'paused', 'aria-label': 'SIMULATED, prototype tools', 'aria-haspopup': 'dialog', onclick: on.tools }, glyph, 'SIMULATED')
      : tag ? h('span', { class: 'sim-badge', role: 'note', 'data-sim': playing ? 'playing' : 'paused' }, glyph, 'SIMULATED') : null,
    h('div', { class: 'safety', 'data-state': engaged ? 'stopped' : 'ok' },
      h('button', { class: 'safety-btn', type: 'button', 'data-key': 'safety', 'aria-haspopup': 'dialog', 'aria-expanded': safetyOpen ? 'true' : 'false', onclick: on.safety }, h('span', { class: 'sdot', 'aria-hidden': 'true' }), h('span', { class: 'stext' }, engaged ? 'Stopped' : 'Not stopped'))),
    h('button', { class: 'tb-search', type: 'button', 'data-key': 'search', 'aria-label': 'Search or run a command', onclick: on.search }, icon('search', 22))
  ].filter(Boolean);
}

// ---------- sheets ----------
// Close a sheet, and run fn once its history entry is gone: an action that navigates (or opens another sheet) must not be undone by the system Back that closing sends.
export function closeThen(sheet, fn) {
  const own = history.state && typeof history.state.sheet === 'string';
  sheet.close();
  if (!own) { fn(); return; }
  let done = false;
  const run = () => { if (!done) { done = true; removeEventListener('popstate', run); fn(); } };
  addEventListener('popstate', run); setTimeout(run, 400);
}

// The Places sheet: search, the desktop groups as 2-column tiles (count on Work), then the projects that need you most, each with its state word and last activity.
// model is places() from phone-model.js; on: { go(href), project(p), all(), search() }.
export function placesBody({ route, model, codeOf, stateOf, wordOf, sinceOf, total, on }) {
  const tile = (it) => h('a', { class: 'pl-tile', href: it.href, 'data-key': 'places-route-' + it.id, 'aria-current': route === it.id ? 'page' : null, 'aria-label': it.badge ? it.label + ', ' + it.badge + ' need you' : null, onclick: (e) => { e.preventDefault(); on.go(it.href); } },
    icon(it.icon, 20), h('span', { class: 'nl' }, it.label), it.badge ? h('span', { class: 'count', 'aria-hidden': 'true' }, it.badge) : null);
  const row = (p) => {
    const st = stateOf(p);
    return h('a', { class: 'pl-proj', href: '#/work', 'data-key': 'places-project-' + p.id, onclick: (e) => { e.preventDefault(); on.project(p); } },
      h('span', { class: 'pl-code' }, codeOf(p)),
      h('span', { class: 'pl-pn' }, h('span', { class: 'pl-name' }, p.name), h('span', { class: 'pl-st' }, h('span', { class: 'pdot', 'data-s': st, 'aria-hidden': 'true' }), wordOf(st))),
      h('span', { class: 'pl-when' }, sinceOf(p)));
  };
  return h('div', { class: 'pl' },
    h('button', { class: 'pl-search', type: 'button', 'data-key': 'places-search', onclick: on.search }, icon('search', 20), h('span', null, 'Search pages, actions and projects')),
    ...model.groups.map((g) => h('section', { class: 'pl-grp', 'aria-label': g.label }, h('h3', { class: 'pl-eye' }, g.label), h('div', { class: 'pl-grid' }, ...g.items.map(tile)))),
    h('section', { class: 'pl-grp', 'aria-label': 'Projects' }, h('h3', { class: 'pl-eye' }, 'Projects'), ...model.projects.map(row),
      model.more ? h('a', { class: 'pl-all', href: '#/projects', 'data-key': 'places-all-projects', onclick: (e) => { e.preventDefault(); on.all(); } }, h('span', null, 'All ' + total + ' projects'), icon('chevron', 20)) : null));
}

// The safety sheet. stop is the stopStep state: while armed the named confirm sits on `side`, away from the tap that armed it.
// on: { arm(e), confirm(), back(), pause(), resume() }.
export function safetyBody({ engaged, running, paused, stop, side }, on) {
  const armed = stop.phase === 'armed';
  const btn = (cls, label, key, fn) => h('button', { class: 'btn l ' + cls, type: 'button', 'data-key': key, onclick: fn }, label);
  return h('div', { class: 'sf' },
    h('p', { class: 'sf-state', 'data-state': engaged ? 'stopped' : 'ok' }, engaged ? 'Stopped. New work is blocked until you re-arm.' : 'Not stopped. Archeus accepts new work.'),
    h('p', { class: 'sf-count' }, running + ' running, ' + paused + ' paused'),
    h('div', { class: 'sf-row' }, btn('', 'Pause all', 'pause-all', on.pause), btn('', 'Resume all', 'resume-all', on.resume)),
    armed
      ? h('div', { class: 'sf-confirm', role: 'group', 'aria-label': stop.label }, h('p', { class: 'sf-q' }, stop.label + '?'),
        h('p', { class: 'sf-note' }, engaged ? 'New work can start again.' : 'Every running mission stops. New work is blocked until you re-arm.'),
        h('div', { class: 'sf-row sf-side', 'data-side': side }, btn(engaged ? 'primary' : 'danger solid', engaged ? 'Yes, re-arm' : 'Yes, stop everything', engaged ? 'rearm-yes' : 'estop-yes', on.confirm), btn('', 'Back', engaged ? 'rearm-back' : 'estop-back', on.back)))
      : h('div', { class: 'sf-row' }, engaged ? btn('primary', 'Re-arm', 'rearm', on.arm) : btn('danger', 'Emergency stop', 'estop', on.arm)));
}
