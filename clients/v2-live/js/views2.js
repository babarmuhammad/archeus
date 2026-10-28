// The More page: every destination as a row, for the phone and for a direct link.
import { h } from './dom.js';
import { icon } from './icons.js';
import { ROUTES, head } from './views.js';

const BLURB = { chat: 'Talk to Archeus; slash commands', replay: 'What Core recorded, step by step', security: 'Isolation, switches, spawn breaker', health: 'Checks and readings', accounts: 'Accounts, models, failover, launch settings', usage: 'How much of each account is left', extensions: 'Hooks, MCP servers, agents, automations, clients', settings: 'Theme, language, motion, devices, simulation' };
export function viewMore(ctx) {
  const ids = ['chat', 'replay', 'security', 'health', 'usage', 'accounts', 'extensions', 'settings'];
  return h('div', null, head(ctx, 'More'), h('div', { class: 'view' }, h('section', { class: 'panel' }, h('div', { class: 'stack' },
    ...ids.map((id) => { const r = ROUTES.find((x) => x.id === id); return h('a', { class: 'mrow', href: '#/' + (id === 'replay' ? 'replay/m-date' : id) }, h('span', { class: 't' }, h('span', { class: 'name' }, r.label)), h('span', { class: 'm' }, BLURB[id]), h('span', { class: 'sp' }, icon(r.icon, 22))); }),
    h('a', { class: 'mrow', href: '#/terminal' }, h('span', { class: 't' }, h('span', { class: 'name' }, 'Terminal view')), h('span', { class: 'm' }, 'The same state as text, as the TUI shows it'), h('span', { class: 'sp' }, icon('terminal', 22)))))));
}
