// The presentation clock of every registered motion (ADR-0024 §5, ADR-0029 §1;
// the two clocks come from zoetrope). An event's time is its place in Core's
// event log — the SSE id, `events.seq`; a presentation's time is this page's
// clock. The timeline holds which presentations are running and answers, for
// any presentation time t, how far each one is: a pure read (`at`, `progress`)
// with no clock, no random and no frame of its own, so a test renders a motion
// at a frozen t (renderAt) and the loop only asks it what to draw.
//
// No replay: per motion it keeps the newest event seq it has presented. An
// event at or below that mark — a reconnect re-sending it, a resync, a re-read,
// a second tab's copy — is refused, and a presentation already running keeps
// its own start: nothing restarts from zero because it was read again. The one
// timeline lives at module scope, so a React rerender, a remount or a route
// change never makes a new one. Refused too: reduced motion (the caller draws
// the entry's static equivalent), a static entry, a start at the cap unless the
// entry drops its oldest.
import { MOTIONS, type MotionId } from './motion.ts';

export interface Showing {
  motion: MotionId;
  target: string; // what it is drawn on: an edge id, a row key
  seq: number; // the event it presents
  start: number; // presentation time it began at
}

const duration = (m: MotionId) => MOTIONS[m].max_ms;

export class Timeline {
  private shows: Showing[] = [];
  private seen = new Map<MotionId, number>();

  /** Present *motion* on *target* for the event at *seq*, from presentation
   * time *now*. False when refused; the event counts as presented either way
   * (so switching reduced motion off later replays nothing). */
  start(motion: MotionId, target: string, seq: number | undefined, now: number, reduced: boolean): boolean {
    // ponytail: a Core whose event log restarts lower than the mark shows no motion until a reload; add a Core epoch to the mark if that happens
    if (seq === undefined || seq <= (this.seen.get(motion) ?? -Infinity)) return false;
    this.seen.set(motion, seq);
    const ms = duration(motion);
    if (reduced || ms === null) return false;
    this.shows = this.shows.filter((s) => now < s.start + (duration(s.motion) ?? 0));
    const m = MOTIONS[motion];
    if (m.cap !== null) {
      const same = this.shows.filter((s) => s.motion === motion && (m.cap_per !== 'target' || s.target === target));
      if (same.length >= m.cap) {
        if (m.over_cap !== 'drop-oldest') return false;
        this.shows.splice(this.shows.indexOf(same[0]), 1);
      }
    }
    this.shows.push({ motion, target, seq, start: now });
    return true;
  }

  /** renderAt: every presentation running at time *t*, with its progress
   * 0 (just began) .. <1; one that has ended is not in it. */
  at(t: number): (Showing & { p: number })[] {
    const out: (Showing & { p: number })[] = [];
    for (const s of this.shows) {
      const ms = duration(s.motion) ?? 0;
      if (t >= s.start && t < s.start + ms) out.push({ ...s, p: (t - s.start) / ms });
    }
    return out;
  }

  /** One motion's progress by target at *t* — what a renderer draws. */
  progress(motion: MotionId, t: number): Map<string, number> {
    return new Map(this.at(t).filter((s) => s.motion === motion).map((s) => [s.target, s.p]));
  }
}

/** The page's one timeline: outlives every render, remount and route. */
export const timeline = new Timeline();
