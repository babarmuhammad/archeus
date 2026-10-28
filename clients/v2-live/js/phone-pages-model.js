// Pure logic for the phone versions of Replay, the five area pages, Settings and the terminal keys. The DOM side is js/phone-pages.js and the pages themselves.

// A horizontal row (chips, tabs) fades the edge that has more behind it instead of showing a scrollbar. left/client/scroll are scrollLeft, clientWidth, scrollWidth.
export const edgeOf = ({ left, client, scroll }) => {
  const l = left > 1, r = left < scroll - client - 1;
  return l && r ? 'both' : l ? 'left' : r ? 'right' : '';
};

// scrollLeft that puts an item in the middle of its row, kept inside the row.
export const centerLeft = ({ offset, width, client, scroll }) => Math.max(0, Math.min(scroll - client, Math.round(offset - (client - width) / 2)));

// One line for a Replay event row. Normal says what Core recorded and why it counts that way; Thinking gives the reason in words; Verbose names the actor and the sequence.
const words = (s) => String(s || '').replace(/_/g, ' ');
export function eventLine(step, detail) {
  const title = step.machine + ' ' + words(step.state);
  const summary = detail === 'thinking' ? step.why || words(step.reason)
    : detail === 'verbose' ? [step.trigger ? 'trigger ' + step.trigger : null, 'by ' + (step.actor || 'unknown'), 'seq ' + step.seq].filter(Boolean).join(' · ')
    : step.trigger ? 'after ' + words(step.trigger) : words(step.reason);
  return { title, summary };
}

// Settings on the phone is a list of sections; each opens as a page of its own (#/settings/appearance). Desktop keeps the tabs and opens on Safety.
export const SET_SECTIONS = [['safety', 'Safety'], ['appearance', 'Appearance'], ['prototype', 'Prototype'], ['about', 'About']];
export const settingsPage = (id, phone) => (SET_SECTIONS.some(([s]) => s === id) ? id : phone ? 'list' : 'safety');

// The grey line under a Settings row, as parts (each one a string the Italian dictionary knows): the current choices, so most of the list is readable without opening it.
export function settingsLine(id, s) {
  if (id === 'safety') return s.engaged ? ['Stopped', 'new work is blocked'] : [s.running + ' running', s.paused + ' paused'];
  if (id === 'appearance') return [s.theme, s.lang === 'it' ? 'Italiano' : 'English', s.motion === 'reduced' ? 'Quiet motion' : s.motion === 'full' ? 'Full motion' : 'Motion follows the system'];
  if (id === 'prototype') return [s.device, s.playing ? 'simulation playing' : 'simulation paused'];
  return ['Simulated', 'no Core connected'];
}
