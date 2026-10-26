import { h } from './dom.js';
import { THEMES, DEVICES } from './store.js';
import * as store from './store.js';
import { head, panel, dnote, simControls, controlBody } from './views.js';

export function render(ctx) {
  return h('div', null, head(ctx, 'Settings'), h('div', { class: 'view' },
    dnote('A04', 'Six looks: Dark and Light, each standard and high contrast, plus System and forced colours. Reduced motion is Quiet (A05).'),
    h('div', { class: 'cols eq' },
      panel('Appearance', null, h('div', { class: 'body' }, h('h3', { class: 'group-h', style: 'font-size:var(--fs-cap)' }, 'Theme'),
        h('div', { class: 'chips', role: 'group', 'aria-label': 'Theme' }, ...THEMES.map((t) => h('button', { class: 'chip', type: 'button', 'aria-pressed': store.get('theme') === t.id ? 'true' : 'false', onclick: () => { store.set('theme', t.id); ctx.render(); } }, t.label))),
        h('h3', { class: 'group-h', style: 'font-size:var(--fs-cap);margin-top:16px' }, 'Motion'),
        h('div', { class: 'chips', role: 'group', 'aria-label': 'Motion' }, ...[['system', 'Follow the system'], ['full', 'Full'], ['reduced', 'Reduced (Quiet)']].map(([id, l]) => h('button', { class: 'chip', type: 'button', 'aria-pressed': store.get('motion') === id ? 'true' : 'false', onclick: () => { store.set('motion', id); ctx.render(); } }, l))),
        h('p', { class: 'note', style: 'padding:8px 0 0' }, 'The core mark is the one thing that moves: a 6 second breath while a fresh read shows live work. Reduced motion shows it still, with a count.'))),
      panel('Device preview', null, h('div', { class: 'body' }, h('div', { class: 'chips', role: 'group', 'aria-label': 'Device preview' }, ...DEVICES.map((d) => h('button', { class: 'chip', type: 'button', 'aria-pressed': store.get('device') === d.id ? 'true' : 'false', onclick: () => ctx.setDevice(d.id) }, d.label + (d.w ? ' ' + d.w : ''))), h('a', { class: 'chip', href: '#/terminal' }, 'Open the terminal view')))),
      panel('Simulation', null, h('div', { class: 'body' }, simControls(Object.assign({}, ctx, { where: 'set' })), h('div', { class: 'actions', style: 'margin-top:12px' }, h('button', { class: 'btn', type: 'button', 'data-key': 'show-keys', onclick: () => ctx.openHelp() }, 'Keyboard shortcuts (?)'))))),
    h('div', { class: 'cols eq' },
      panel('Pause, resume and emergency stop', null, controlBody(ctx)),
      panel('Language and notes', null, h('div', { class: 'body' }, h('h3', { class: 'group-h', style: 'font-size:var(--fs-cap)' }, 'Language'),
        h('div', { class: 'chips', role: 'group', 'aria-label': 'Language' }, ...[['en', 'English'], ['it', 'Italiano']].map(([id, l]) => h('button', { class: 'chip', type: 'button', 'aria-pressed': store.get('lang') === id ? 'true' : 'false', onclick: () => ctx.setLang(id) }, l))),
        h('h3', { class: 'group-h', style: 'font-size:var(--fs-cap);margin-top:16px' }, 'Decision notes'),
        h('div', { class: 'chips', role: 'group', 'aria-label': 'Decision notes' }, ...[['on', 'Show'], ['off', 'Hide']].map(([id, l]) => h('button', { class: 'chip', type: 'button', 'aria-pressed': store.get('notes') === id ? 'true' : 'false', onclick: () => ctx.setNotes(id) }, l))),
        dnote('A15', 'Everything on screen is simulated and says so; no Core is connected.'))),
      panel('About this prototype', null, h('div', { class: 'body' }, h('p', null, 'V2 Live is a prototype that simulates the Archeus app on every device. Nothing here is connected to a Core: the projects, missions, approvals, usage numbers and replies are fixtures and a scripted clock.'),
        h('p', { style: 'margin-top:8px' }, 'The shell, the map, the mission and decision views, chat, Replay and the terminal view are built on the simulation. A Core connection, real accounts and the native apps are not built.'))))));
}
