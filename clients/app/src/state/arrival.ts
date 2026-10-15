// A-08 attention arrival (rulebook §17, §20, §21; §46.2). When a read of
// Attention shows more things needing the user than the read before it, the
// nav badge pulses once (240 ms) and the new count is announced politely. The
// count is Core's, read at Core's seq: the first read sets the baseline and
// never pulses, a read no newer than the one held changes nothing, and a fall
// in the count is not an arrival. Under reduced motion the pulse is removed,
// and the announcement and the count still happen.
import type { Timeline } from './timeline.ts';

export const needsYou = (n: number) => `${n} ${n === 1 ? 'thing needs' : 'things need'} you`;

/** The tab's name: the count, so the tab says it while another one is in front. */
export const tabTitle = (n: number) => (n > 0 ? `(${n}) Archeus` : 'Archeus');

export class Arrival {
  private count: number | undefined;
  private at = -Infinity;
  private seq = 0;
  private listeners = new Set<() => void>();
  private timeline: Timeline;
  private host: { now: () => number; reduced: () => boolean; announce: (text: string) => void };
  constructor(timeline: Timeline, host: { now: () => number; reduced: () => boolean; announce: (text: string) => void }) {
    this.timeline = timeline;
    this.host = host;
  }
  /** A read of Attention's *count*, taken at Core's *seq*. */
  read(count: number, seq: number | undefined) {
    if (seq === undefined || seq <= this.at) return;
    const rose = this.count !== undefined && count > this.count;
    this.count = count;
    this.at = seq;
    if (!rose) return;
    this.host.announce(needsYou(count));
    if (!this.timeline.start('attention-arrival', 'nav badge', seq, this.host.now(), this.host.reduced())) return;
    this.seq = seq;
    this.listeners.forEach((l) => l());
  }
  /** The seq of the newest pulse (0: none). */
  current(): number {
    return this.seq;
  }
  subscribe(l: () => void): () => void {
    this.listeners.add(l);
    return () => void this.listeners.delete(l);
  }
}
