// The mission lifecycle spine (ADR-0054), pure: where a mission is in its life, from
// its state and its held_from and nothing else. The table (stations, a position per
// mission state, the text equivalent) is tokens/spine.json, generated into
// spineTable.ts; the TUI's present.py `spine_of` is this function in Python and the
// shared parity cases hold the two to the same output. Never guessed: a hold with no
// held_from that names a station draws every station unknown, and a state this
// client does not know draws its own word and no stations.
import { present } from './present.ts';
import { SPINE } from './spineTable.ts';

export type MarkKind = 'passed' | 'current' | 'held' | 'failed' | 'ahead' | 'none' | 'unknown';

export interface Spine {
  /** one mark per station, in order; empty for a state this client does not know */
  marks: MarkKind[];
  /** the 1-based station the current, held or failed mark sits on */
  at: number | null;
  /** all stations passed, in the Done colour: COMPLETED only */
  done: boolean;
  /** the glyph and role of the mission state's own class, for the marked station */
  look: { cls: string; glyph: string; role: string } | null;
  /** the text equivalent, built from Core's state word and the table */
  text: string;
}

const STATES: Record<string, { kind: string; station?: number }> = SPINE.states;
const SENTENCES: Record<string, string> = SPINE.sentences;
const known = (s: unknown): s is string => typeof s === 'string' && Object.hasOwn(STATES, s);

export function spineOf(state: string, heldFrom?: unknown): Spine {
  const look = present('mission', state);
  if (!known(state)) return { marks: [], at: null, done: false, look: null, text: look.label };
  const total = SPINE.stations.length;
  let { kind, station: at = null } = STATES[state] as { kind: string; station: number | null };
  if (kind === 'held' || kind === 'resumed') {
    const from = known(heldFrom) ? STATES[heldFrom] : undefined;
    if (from?.kind === 'current') at = from.station ?? null;
    else kind = 'unknown';
  }
  const marks = Array.from({ length: total }, (_, i): MarkKind => {
    const n = i + 1;
    if (kind === 'ahead') return 'ahead';
    if (kind === 'cancelled') return 'none';
    if (kind === 'unknown') return 'unknown';
    if (kind === 'complete') return 'passed';
    if (at === null) return 'unknown';
    if (kind === 'passed') return n <= at ? 'passed' : 'ahead';
    if (n < at) return 'passed';
    if (n > at) return 'ahead';
    return kind === 'held' || kind === 'failed' ? kind : 'current';
  });
  const marked = marks.some((m) => m === 'current' || m === 'held' || m === 'failed');
  const words: Record<string, string> = {
    word: look.label,
    n: String(at),
    total: String(total),
    station: at === null ? '' : SPINE.stations[at - 1].label,
  };
  return {
    marks,
    at: marked ? at : null,
    done: kind === 'complete',
    look: marked ? { cls: look.cls, glyph: look.glyph, role: look.role } : null,
    text: SENTENCES[kind].replace(/\{(\w+)\}/g, (_m, k: string) => words[k]),
  };
}
