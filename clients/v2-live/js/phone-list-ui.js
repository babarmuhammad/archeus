// Small DOM pieces the three phone lists share (Overview, Work, Projects): a state as glyph and word, the project code chip, the "Show 20 more" button.
import { h } from './dom.js';
import { glyph } from './icons.js';

// cls is a Core presentation class (needs_you, active, done, blocked, inactive ...): the glyph repeats the word, colour only confirms it.
export const stateMark = (cls, text) => h('span', { class: 'ph-st', 'data-role': cls }, h('span', { class: 'g', 'aria-hidden': 'true' }, glyph(cls, 16)), h('span', { class: 'w' }, text));
export const codeChip = (c) => h('span', { class: 'ph-code', 'aria-hidden': 'true' }, c);
export const moreButton = (n, key, onclick) => h('button', { class: 'btn l ph-more', type: 'button', 'data-key': key, onclick }, 'Show ' + n + ' more');

const TONE = { needs_you: ['needs_you', 'Needs you'], running: ['active', 'Running'], done: ['done', 'Done'], idle: ['inactive', 'Quiet'] };
// What a project is doing, in one word: the same words as Work. p: an Overview project ({ attention, running, total, missions }).
export function projectTone(p) {
  const key = p.attention ? 'needs_you' : p.running ? 'running' : p.total && p.missions.every((m) => m.state === 'done') ? 'done' : 'idle';
  return { key, cls: TONE[key][0], word: TONE[key][1] };
}
