// The Ideas stepper (rulebook §43; D-11, §46.1): where an idea is on Core's
// path, read-only. Core has no idea-transition command, so no step is a
// button — a recorded deviation from §43's "the one transition available now".
// The path is not linear (an idea may skip steps), so a step before the
// current one is only "earlier", never claimed as done.
import { badge } from './present.ts';

/** Core's main path for an idea (`states.py`), in order. */
export const IDEA_PATH = ['CAPTURED', 'UNDERSTOOD', 'EXPLORED', 'VALIDATED', 'CONCEPT', 'PLANNED', 'SCHEDULED', 'IMPLEMENTING', 'COMPLETED', 'LEARNED'] as const;
/** The side exits; revive takes either back to CAPTURED. */
export const IDEA_ASIDE = ['PARKED', 'DISCARDED'] as const;

export interface Step {
  state: string;
  label: string;
  at: 'earlier' | 'now' | 'later';
}

/** The main path with the idea's place on it, and the side exit it is in. */
export function ideaSteps(state: string): { path: Step[]; aside: string | null } {
  const i = (IDEA_PATH as readonly string[]).indexOf(state);
  const path = IDEA_PATH.map((s, j): Step => ({ state: s, label: badge('idea', s).label, at: i < 0 ? 'later' : j < i ? 'earlier' : j === i ? 'now' : 'later' }));
  return { path, aside: (IDEA_ASIDE as readonly string[]).includes(state) ? badge('idea', state).label : null };
}
