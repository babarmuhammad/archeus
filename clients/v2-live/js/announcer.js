// The DOM and timers for the polite announcer (SPEC E15). The rules live in announcer-model.js.
import { h } from './dom.js';
import { createAnnouncer, classify, say } from './announcer-model.js';
import { get } from './store.js';

const SETTLE_MS = 150; // a burst of events is one moment: wait this long so the most important of them is the one spoken

export function installAnnouncer(sim, root) {
  const region = h('p', { class: 'vh announcer', role: 'status', 'aria-live': 'polite', 'aria-atomic': 'true' });
  root.append(region);
  const a = createAnnouncer();
  let timer = 0;
  // cleared first, then set: a screen reader announces a change of the region, and the same sentence twice is not one
  const speak = (text) => { region.textContent = ''; setTimeout(() => { region.textContent = text; }, 30); };
  const pump = () => {
    clearTimeout(timer);
    const w = a.wait(performance.now());
    if (w == null) return;
    timer = setTimeout(() => {
      const d = a.due(performance.now());
      if (d) speak(say(d.best, d.others, get('lang')));
      pump();
    }, Math.max(w, SETTLE_MS));
  };
  const title = (id) => (sim.state.missions[id] || {}).title;
  return sim.subscribe((ev) => {
    if (ev.type === 'sim.reset') { a.reset(); return; }
    const item = classify(ev, title); if (item) { a.note(item); pump(); }
  });
}
