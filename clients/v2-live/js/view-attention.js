import { h } from './dom.js';
import { head, panel, dnote, empty, attentionItem } from './views.js';

export function render(ctx) {
  const att = ctx.sim.attention();
  const groups = ['Decide', 'Review', 'Unblock'].map((g) => [g, att.filter((a) => a.group === g)]).filter((x) => x[1].length);
  return h('div', null, head(ctx, 'Attention'), h('div', { class: 'view' },
    dnote('E20', 'Groups Decide, Review, Unblock; the band is a 12 % tint with the word in ink (B09). No acknowledge or snooze: that needs a Core record.'),
    groups.length ? groups.map(([g, items]) => h('section', { class: 'col', style: 'gap:8px' }, h('h2', { class: 'group-h' }, g, h('span', { class: 'n' }, items.length + (g === 'Decide' ? ' · asks you to decide' : g === 'Review' ? ' · results to accept' : ' · work that needs a person'))),
      h('div', { class: 'att-rows' }, ...items.map((a) => h('div', { class: 'panel' }, attentionItem(ctx, a)))))) : [panel('Attention', 0, empty('Nothing waits on you.', 'clear'))]));
}
