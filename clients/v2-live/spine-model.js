// The mission lifecycle spine (ADR-0054), pure part: six stations, drawn from Core's mission state and held_from, never guessed.
// No DOM. spine.js draws it; term.js prints it.
import { present, WORDS } from './core-words.js';

export const STATIONS = ['Understanding', 'Planning', 'Approval', 'Executing', 'Verifying', 'Reviewing'];

// state -> station reached (1 based). BLOCKED and PAUSED use held_from, CREATED and CANCELLED have none.
const AT = { UNDERSTANDING: 1, CONTEXT_GATHERING: 1, REASONING: 1, PLANNING: 2, REPLANNING: 2, APPROVAL_REQUIRED: 3, APPROVED: 3, EXECUTING: 4, VERIFYING: 5, REVIEWING: 6 };
export const SPINE_STATES = Object.keys(AT);

function result(over) {
  return Object.assign({ marks: [], segments: [], station: null, unknown: false, done: false, none: false, text: '' }, over);
}

export function spineOf(state, heldFrom) {
  const p = present('mission', state);
  const word = p.label;
  const six = (f) => STATIONS.map((_, i) => f(i + 1));
  const segs = (curr) => [1, 2, 3, 4, 5].map((i) => (i + 1 <= curr ? 'solid' : 'dashed'));
  const known = (s) => Object.prototype.hasOwnProperty.call(AT, s);
  const label = (n) => STATIONS[n - 1];

  if (state === 'COMPLETED') return result({ marks: six(() => ({ kind: 'passed' })), segments: segs(6), station: 6, done: true, text: word + ', all 6 steps passed.' });
  if (state === 'CREATED') return result({ marks: six(() => ({ kind: 'ahead' })), segments: ['dashed', 'dashed', 'dashed', 'dashed', 'dashed'], none: true, text: word + ', not started.' });
  if (state === 'CANCELLED') return result({ marks: six(() => ({ kind: 'none' })), segments: ['dashed', 'dashed', 'dashed', 'dashed', 'dashed'], none: true, text: 'Cancelled.' });
  if (state === 'FAILED') {
    const n = 4;
    return result({ marks: six((i) => (i < n ? { kind: 'passed' } : i === n ? { kind: 'current', cls: 'failed' } : { kind: 'ahead' })), segments: segs(n), station: n, text: word + ' at step ' + n + ' of 6 (' + label(n) + ').' });
  }
  if (state === 'BLOCKED' || state === 'PAUSED' || state === 'RESUMED') {
    if (!known(heldFrom)) {
      return result({ marks: six(() => ({ kind: 'unknown' })), segments: ['dotted', 'dotted', 'dotted', 'dotted', 'dotted'], unknown: true, text: word + ', position unknown.' });
    }
    const n = AT[heldFrom];
    const cls = p.cls;
    const t = state === 'RESUMED' ? word + ', step ' + n + ' of 6.' : word + ' at step ' + n + ' of 6 (' + label(n) + ').';
    return result({ marks: six((i) => (i < n ? { kind: 'passed' } : i === n ? { kind: 'current', cls } : { kind: 'ahead' })), segments: segs(n), station: n, text: t });
  }
  if (!known(state)) return result({ marks: [], segments: [], unknown: true, none: true, text: word });
  const n = AT[state];
  if (state === 'APPROVED') {
    return result({ marks: six((i) => (i <= n ? { kind: 'passed' } : { kind: 'ahead' })), segments: segs(n), station: n, text: word + ', 3 of 6 steps passed.' });
  }
  return result({ marks: six((i) => (i < n ? { kind: 'passed' } : i === n ? { kind: 'current', cls: p.cls } : { kind: 'ahead' })), segments: segs(n), station: n, text: word + ', step ' + n + ' of 6.' });
}

// TUI form (ADR-0054 section 7): one cluster and one word. ascii = the presentation.json fallback set.
export function spineText(state, heldFrom, ascii) {
  const s = spineOf(state, heldFrom);
  const pick = (kind, cls) => {
    if (kind === 'passed') return ascii ? '+' : '✓';
    if (kind === 'ahead') return ascii ? 'o' : '○';
    if (kind === 'unknown') return '?';
    if (kind === 'none') return ascii ? '-' : '–';
    const c = WORDS.classes[cls];
    return ascii ? c.ascii : c.glyph;
  };
  const cluster = s.marks.map((m) => pick(m.kind, m.cls)).join('');
  const p = present('mission', state);
  let word;
  if (state === 'COMPLETED') word = 'Done';
  else if (state === 'CREATED') word = 'Created';
  else if (state === 'CANCELLED') word = 'Cancelled';
  else if (state === 'APPROVED') word = 'Approved';
  else if (state === 'FAILED' || state === 'BLOCKED' || state === 'PAUSED') word = WORDS.classes[p.cls].name;
  else if (s.station) word = STATIONS[s.station - 1];
  else word = p.label;
  return cluster + ' ' + word;
}

export const isOpenMission = (m) => !['COMPLETED', 'CANCELLED', 'FAILED'].includes(m.state);
