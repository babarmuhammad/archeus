import { h } from './dom.js';
import { icon } from './icons.js';
import { isPhone } from './viewport.js';
import { SET_SECTIONS, settingsPage, settingsLine } from './phone-pages-model.js';
import { THEMES, DEVICES } from './store.js';
import * as store from './store.js';
import { head, dnote, simControls, controlBody } from './views.js';

// A section is a heading and rows; a row is a label with its note, and the control next to it (below it when the control is wide).
const section = (title, ...rows) => h('section', { class: 'set-sec' }, h('h2', { class: title === shown ? 'vh' : null }, title), ...rows);
const row = (label, note, control) => h('div', { class: 'set-row' }, h('div', { class: 'set-txt' }, h('span', { class: 'r-name' }, label), note ? h('span', { class: 'r-note' }, note) : null), h('div', { class: 'set-ctl' }, control));
const choice = (label, current, options, on) => h('div', { class: 'chips', role: 'group', 'aria-label': label }, ...options.map(([id, l]) => h('button', { class: 'chip', type: 'button', 'aria-pressed': current === id ? 'true' : 'false', onclick: () => on(id) }, l)));

// One section at a time, chosen by the route (#/settings/appearance), so a section can be linked to and the browser's back button works.
// On a phone the sections are a list, and each opens as a page of its own with a Back button.
let shown = ''; // the label of the section being drawn: its heading is the page title on a phone, so the section does not say it twice
export function render(ctx) {
  const pick = (key) => (id) => { store.set(key, id); ctx.render(); };
  const phone = isPhone(), id = settingsPage(ctx.route.id, phone);
  if (id === 'list') return list(ctx);
  shown = phone ? SET_SECTIONS.find(([s]) => s === id)[1] : '';
  const body = {
    safety: () => section('Pause, resume and emergency stop', controlBody(ctx)),
    appearance: () => [
      section('Appearance',
        row('Theme', null, choice('Theme', store.get('theme'), THEMES.map((t) => [t.id, t.label]), pick('theme'))),
        row('Motion', 'Live work moves the map slowly: nodes drift, markers travel along active links and the core mark breathes. Reduced motion stops all of it.', choice('Motion', store.get('motion'), [['system', 'Follow the system'], ['full', 'Full'], ['reduced', 'Reduced (Quiet)']], pick('motion'))),
        row('Language', null, choice('Language', store.get('lang'), [['en', 'English'], ['it', 'Italiano']], ctx.setLang)),
        row('Decision notes', 'Show which decision each choice implements', choice('Decision notes', store.get('notes'), [['on', 'Show'], ['off', 'Hide']], ctx.setNotes))),
      dnote('A04', 'Six looks: Dark and Light, each standard and high contrast, plus System and forced colours. Reduced motion is Quiet (A05).')],
    prototype: () => section('Prototype controls',
      row('Device preview', null, h('div', { class: 'chips', role: 'group', 'aria-label': 'Device preview' }, ...DEVICES.map((d) => h('button', { class: 'chip', type: 'button', 'aria-pressed': store.get('device') === d.id ? 'true' : 'false', onclick: () => ctx.setDevice(d.id) }, d.label + (d.w ? ' ' + d.w : ''))), h('a', { class: 'chip', href: '#/terminal' }, 'Open the terminal view'))),
      row('Simulation', null, h('div', { class: 'col', style: 'gap:12px' }, simControls(Object.assign({}, ctx, { where: 'set' })), h('div', { class: 'actions' }, h('button', { class: 'btn', type: 'button', 'data-key': 'show-keys', onclick: () => ctx.openHelp() }, 'Keyboard shortcuts (?)'))))),
    about: () => [
      section('About this prototype',
        h('p', { class: 'set-about' }, 'V2 Live is a prototype that simulates the Archeus app on every device. Nothing here is connected to a Core: the projects, missions, approvals, usage numbers and replies are fixtures and a scripted clock.'),
        h('p', { class: 'set-about' }, 'The shell, the map, the mission and decision views, chat, Replay and the terminal view are built on the simulation. A Core connection, real accounts and the native apps are not built.')),
      dnote('A15', 'Everything on screen is simulated and says so; no Core is connected.')]
  }[id]();
  if (phone) {
    const back = () => { if (ctx.ui.setPush) { ctx.ui.setPush = false; history.back(); } else ctx.nav('#/settings'); };
    return h('div', null, h('header', { class: 'page-head set-head' }, h('button', { class: 'btn quiet set-back', type: 'button', 'data-key': 'set-back', 'aria-label': 'Back to Settings', onclick: back }, icon('chevronl', 20), 'Settings'), h('h1', null, shown)),
      h('div', { class: 'view' }, h('div', { class: 'set-body' }, body)));
  }
  return h('div', null, head(ctx, 'Settings'), h('div', { class: 'view' },
    h('div', { class: 'set-wrap' },
      h('nav', { class: 'set-nav', 'aria-label': 'Settings sections' }, ...SET_SECTIONS.map(([s, label]) => h('a', { class: 'set-nav-item', href: '#/settings/' + s, 'data-key': 'set-nav-' + s, 'aria-current': s === id ? 'page' : null }, label))),
      h('div', { class: 'set-body' }, body))));
}

function list(ctx) {
  ctx.ui.setPush = false;
  const ms = Object.values(ctx.sim.state.missions);
  const state = { engaged: ctx.sim.state.estop.engaged, running: ms.filter((m) => m.state === 'EXECUTING').length, paused: ms.filter((m) => m.state === 'PAUSED').length,
    theme: THEMES.find((t) => t.id === store.get('theme')).label, lang: store.get('lang'), motion: store.get('motion'), device: DEVICES.find((d) => d.id === store.get('device')).label, playing: ctx.sim.state.playing };
  return h('div', null, h('header', { class: 'page-head set-head' }, h('h1', null, 'Settings')), h('div', { class: 'view' }, h('nav', { class: 'set-list', 'aria-label': 'Settings sections' },
    ...SET_SECTIONS.map(([s, label]) => h('a', { class: 'set-li', href: '#/settings/' + s, 'data-key': 'set-li-' + s, onclick: () => { ctx.ui.setPush = true; } },
      h('span', { class: 'set-li-t' }, h('span', { class: 'r-name' }, label), h('span', { class: 'r-note' }, ...settingsLine(s, state).flatMap((p, i) => [i ? ' · ' : null, h('span', null, p)]).filter(Boolean))), icon('chevron', 20))))));
}
