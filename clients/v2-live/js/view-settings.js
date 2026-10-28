import { h } from './dom.js';
import { THEMES, DEVICES } from './store.js';
import * as store from './store.js';
import { head, dnote, simControls, controlBody } from './views.js';

// A section is a heading and rows; a row is a label with its note, and the control next to it (below it when the control is wide).
const section = (title, ...rows) => h('section', { class: 'set-sec' }, h('h2', null, title), ...rows);
const row = (label, note, control) => h('div', { class: 'set-row' }, h('div', { class: 'set-txt' }, h('span', { class: 'r-name' }, label), note ? h('span', { class: 'r-note' }, note) : null), h('div', { class: 'set-ctl' }, control));
const choice = (label, current, options, on) => h('div', { class: 'chips', role: 'group', 'aria-label': label }, ...options.map(([id, l]) => h('button', { class: 'chip', type: 'button', 'aria-pressed': current === id ? 'true' : 'false', onclick: () => on(id) }, l)));

// One section at a time, chosen by the route (#/settings/appearance), so a section can be linked to and the browser's back button works.
const SECTIONS = [['safety', 'Safety'], ['appearance', 'Appearance'], ['prototype', 'Prototype'], ['about', 'About']];

export function render(ctx) {
  const pick = (key) => (id) => { store.set(key, id); ctx.render(); };
  const id = SECTIONS.some(([s]) => s === ctx.route.id) ? ctx.route.id : 'safety';
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
  return h('div', null, head(ctx, 'Settings'), h('div', { class: 'view' },
    h('div', { class: 'set-wrap' },
      h('nav', { class: 'set-nav', 'aria-label': 'Settings sections' }, ...SECTIONS.map(([s, label]) => h('a', { class: 'set-nav-item', href: '#/settings/' + s, 'data-key': 'set-nav-' + s, 'aria-current': s === id ? 'page' : null }, label))),
      h('div', { class: 'set-body' }, body))));
}
