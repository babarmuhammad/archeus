// The polite announcer for screen readers (SPEC E15, V1 a11y/announce.ts): at most one announcement per 5 s, a burst of changes
// is spoken as its most important one, nothing is spoken when nothing changed, and the emergency stop is respected.
// Pure: the caller passes the clock (real milliseconds, never the simulated one) and owns every timer and the DOM.
import { present } from '../core-words.js';

export const EVERY_MS = 5000;

// importance, lowest first: a change of a higher rank hides the lower ones in the same burst
const ORDER = ['running', 'done', 'rearmed', 'failed', 'needs_you', 'stopped'];
const RANK = Object.fromEntries(ORDER.map((c, i) => [c, i]));
const FROM_CORE = { needs_you: 'needs_you', failed: 'failed', done: 'done', active: 'running' };

// A simulation event as a change worth saying, or null. The key is the thing that changed (its mission), so two events about
// one mission in a burst count once, and its latest state wins.
export function classify(ev, titleOf) {
  const p = ev.payload || {}, name = (id) => (id && titleOf(id)) || '';
  if (ev.type === 'core.estop_engaged') return { key: 'core', cls: 'stopped', title: '' };
  if (ev.type === 'core.estop_rearmed') return { key: 'core', cls: 'rearmed', title: '' };
  if (ev.type === 'approval.requested') return ev.mission ? { key: ev.mission, cls: 'needs_you', title: name(ev.mission) } : null;
  if (ev.type === 'mission.state_changed' || ev.type === 'execution.state_changed') {
    const cls = FROM_CORE[present(ev.subject.kind, p.to).cls];
    if (!cls || p.from === p.to) return null;
    if (ev.subject.kind === 'execution' && p.to !== 'ENDED_ERROR') return null; // other execution ends are the mission's news, and a kill by the stop is not a failure
    return ev.mission ? { key: ev.mission, cls, title: name(ev.mission) } : null;
  }
  return null;
}

const WORDS = {
  en: { needs_you: 'Needs you', failed: 'Failed', done: 'Done', running: 'Running', stopped: 'Emergency stop engaged. New work is blocked.', rearmed: 'Emergency stop released. New work can start.', more: (n) => (n === 1 ? ' One more change.' : ' ' + n + ' more changes.') },
  it: { needs_you: 'Richiede la tua attenzione', failed: 'Fallita', done: 'Fatta', running: 'In esecuzione', stopped: 'Arresto di emergenza attivo. Il nuovo lavoro è bloccato.', rearmed: 'Arresto di emergenza rilasciato. Il nuovo lavoro può partire.', more: (n) => (n === 1 ? ' Un altro cambiamento.' : ' Altri ' + n + ' cambiamenti.') }
};

export function say(best, others, lang) {
  const w = WORDS[lang] || WORDS.en;
  return (best.cls === 'stopped' || best.cls === 'rearmed' ? w[best.cls] : w[best.cls] + ': ' + best.title + '.') + (others ? w.more(others) : '');
}

export function createAnnouncer(opts) {
  const every = (opts && opts.every) || EVERY_MS;
  const told = new Map(), pending = new Map();
  let last = -Infinity, stopped = false;

  return {
    // Record a change (an item from classify). It is spoken by a later due().
    note(item) {
      if (item.cls === 'stopped') { stopped = true; for (const [k, v] of pending) if (v.cls === 'running') pending.delete(k); }
      else if (item.cls === 'rearmed') stopped = false;
      else if (item.cls === 'running' && stopped) return; // nothing starts while the stop holds; a running word would be untrue
      if (told.get(item.key) === item.cls) pending.delete(item.key); // back to what the listener last heard: no change
      else pending.set(item.key, item);
    },
    // The sentence to speak now, or null: nothing pending, or the 5 s are not over.
    due(now) {
      if (!pending.size || now - last < every) return null;
      const all = [...pending.values()];
      const best = all.reduce((a, b) => (RANK[b.cls] >= RANK[a.cls] ? b : a)); // latest wins a tie
      all.forEach((i) => told.set(i.key, i.cls));
      pending.clear(); last = now;
      return { best, others: all.length - 1 };
    },
    // The simulation started over: what was told before is history.
    reset() { told.clear(); pending.clear(); stopped = false; },
    // Milliseconds until a pending change may be spoken, or null when none waits.
    wait(now) { return pending.size ? Math.max(0, last + every - now) : null; }
  };
}
