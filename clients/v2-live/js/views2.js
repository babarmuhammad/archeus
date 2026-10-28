// Security, Health, More and Chat screens (decided areas: security and health, chat with slash commands).
import { h } from './dom.js';
import { icon, glyph } from './icons.js';
import { ROUTES, head, panel, empty, dnote, projName } from './views.js';

const FIG = { ok: ['done', 'Ok'], off: ['paused', 'Off'], open: ['blocked', 'Open'], attention: ['needs_you', 'Needs attention'], unknown: ['inactive', 'Unknown'] };
const fig = (state, word) => { const f = FIG[state] || FIG.unknown; return h('span', { class: 'badge', 'data-role': f[0] }, h('span', { class: 'g', 'aria-hidden': 'true' }, glyph(f[0])), h('span', { class: 'w' }, word || f[1])); };

export function viewHealth(ctx) {
  const items = ctx.sim.health();
  const n = (s) => items.filter((x) => x.state === s).length;
  return h('div', null, head(ctx, 'Health'), h('div', { class: 'view' },
    dnote('H15', 'Health is read from records, one live derivation (P21 D12). A missing reading is shown as unknown, never as 0.'),
    h('div', { class: 'chips' }, h('span', { class: 'chip static' }, n('ok') + ' ok'), h('span', { class: 'chip static' }, n('attention') + ' need attention'), h('span', { class: 'chip static' }, n('unknown') + ' unknown')),
    panel('Checks', items.length, h('div', { class: 'body' }, ...items.map((x) => h('div', { class: 'row-line', 'data-key': 'hl-' + x.id }, h('span', { class: 'a' }, x.label, h('span', { class: 'sp-text', style: 'display:block;padding:2px 0 0' }, x.detail)), fig(x.state)))))));
}

const BLURB = { chat: 'Talk to Archeus; slash commands', replay: 'What Core recorded, step by step', security: 'Isolation, switches, spawn breaker', health: 'Checks and readings', accounts: 'Accounts, models, failover, launch settings', usage: 'How much of each account is left', extensions: 'Hooks, MCP servers, agents, automations, clients', settings: 'Theme, language, motion, devices, simulation', map: 'The live constellation' };
export function viewMore(ctx) {
  const ids = ['map', 'chat', 'replay', 'security', 'health', 'usage', 'accounts', 'extensions', 'settings'];
  return h('div', null, head(ctx, 'More'), h('div', { class: 'view' }, h('section', { class: 'panel' }, h('div', { class: 'stack' },
    ...ids.map((id) => { const r = ROUTES.find((x) => x.id === id); return h('a', { class: 'mrow', href: '#/' + (id === 'replay' ? 'replay/m-date' : id) }, h('span', { class: 't' }, h('span', { class: 'name' }, r.label)), h('span', { class: 'm' }, BLURB[id]), h('span', { class: 'sp' }, icon(r.icon, 22))); }),
    h('a', { class: 'mrow', href: '#/terminal' }, h('span', { class: 't' }, h('span', { class: 'name' }, 'Terminal view')), h('span', { class: 'm' }, 'The same state as text, as the TUI shows it'), h('span', { class: 'sp' }, icon('terminal', 22)))))));
}
