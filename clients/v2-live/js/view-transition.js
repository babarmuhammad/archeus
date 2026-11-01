// Route changes through the View Transitions API (SPEC C12). The decision is pure so a test can run it without a DOM; start() is the only line that touches document.
// Timing is css/motion.css (--dur-out out, --dur-quick in); nothing here carries a duration.
import { direction } from './motion-model.js';

// The terminal view draws its own screen, a cross-fade over it would show two terminals.
const OWN_SCREEN = new Set(['terminal']);

// api: the browser has document.startViewTransition. quiet: the in-app or OS Reduced motion (Quiet). A route to itself never transitions.
export function decide({ from, to, api, quiet }) {
  const dir = direction(from, to);
  const run = !!api && !quiet && from !== to && !OWN_SCREEN.has(from) && !OWN_SCREEN.has(to);
  return { run, dir, name: dir > 0 ? 'fwd' : 'back' };
}

// Runs update inside a transition, or straight away when the decision says no. The data-vt attribute names the direction for css and exists only while the transition runs.
export function start(doc, d, update) {
  if (!d.run) { update(d.dir); return false; }
  const root = doc.documentElement, clear = () => { delete root.dataset.vt; };
  root.dataset.vt = d.name;
  const t = doc.startViewTransition(() => update(d.dir));
  t.finished.then(clear, clear);
  t.ready.catch(() => {}); // a route change inside a running transition skips it, which rejects ready
  return true;
}
