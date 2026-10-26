// Character-cell toolkit for the terminal view. DOM free. One cell = one column: every glyph the terminal draws is one BMP
// code unit and one column wide (test/tui.test.mjs checks it), so line length in code units is its width in columns.
// A segment is [text, cls, hit, sr]: cls styles it, hit names what a click on it means, sr is what a screen reader hears instead.
import { present } from '../../core-words.js';

export const seg = (t, c, h, sr) => [t, c || '', h, sr];
export const len = (segs) => segs.reduce((n, s) => n + s[0].length, 0);
export const plain = (segs) => segs.map((s) => s[0]).join('');
export const speech = (segs) => segs.map((s) => (s[3] != null ? s[3] : s[0])).join('').replace(/\s+/g, ' ').trim();

// The terminal's own glyphs and what an ASCII-only terminal gets instead (same width).
const UNI = { dot: '·', arrow: '›', ell: '…', core: '◎', core2: '◉', hub: '○', exec: '▲', on: '█', off: '░', tag: '◆', up: '↑', down: '↓', enter: '⏎', left: '←', right: '→' };
const ASC = { dot: '-', arrow: '>', ell: '.', core: '*', core2: '+', hub: 'o', exec: '^', on: '#', off: '.', tag: '!', up: '^', down: 'v', enter: '<', left: '<', right: '>' };
export const glyphs = (ascii) => (ascii ? ASC : UNI);
// 1:1 replacements for text that comes from the fixtures and the Core words
const FOLD = { '—': '-', '–': '-', '…': '.', '·': '-', '’': "'", '‘': "'", '“': '"', '”': '"', '→': '>', '×': 'x', '≥': '>', '≤': '<' };
export const asciify = (s) => s.replace(/[^\x20-\x7e]/g, (c) => FOLD[c] || '?');

export const role = (cls) => ({ needs_you: 'att', active: 'act', verifying: 'act', reviewing: 'act', blocked: 'blk', failed: 'blk', paused: 'pau', planning: 'thk', done: 'done' }[cls] || 't2');

// The state mark of a Core state: glyph, role colour, and its word for the screen reader.
export function mark(machine, state, ascii) {
  const p = present(machine, state);
  return seg(ascii ? p.ascii : p.glyph, role(p.cls), null, p.label);
}

export function clip(segs, n, ell) {
  if (len(segs) <= n) return segs;
  const out = []; let left = n - 1;
  for (const s of segs) {
    if (left <= 0) break;
    out.push(s[0].length <= left ? s : [s[0].slice(0, left), s[1], s[2], s[3]]);
    left -= s[0].length;
  }
  if (n < 1) return [];
  const last = out[out.length - 1] || ['', '', null];
  out.push([ell || '…', last[1], last[2]]);
  return out;
}
export const pad = (segs, n) => { const k = len(segs); return k >= n ? segs : segs.concat([[' '.repeat(n - k), '']]); };
// left clipped, right aligned; the right side wins its space only when 8 columns are left for the left
export function lr(left, right, n, ell, strict) {
  const r = len(right);
  if (!r) return clip(left, n, ell);
  const room = n - r - 1;
  if (room < 8 || (strict && len(left) > room)) return clip(left, n, ell);
  return pad(clip(left, room, ell), room + 1).concat(right);
}
export function wrap(s, n) {
  const out = []; let cur = '';
  for (let w of String(s).split(/\s+/)) {
    if (!w) continue;
    while (w.length > n) { if (cur) { out.push(cur); cur = ''; } out.push(w.slice(0, n)); w = w.slice(n); }
    if (!cur) cur = w; else if (cur.length + 1 + w.length <= n) cur += ' ' + w; else { out.push(cur); cur = w; }
  }
  if (cur) out.push(cur);
  return out.length ? out : [''];
}

// ---- box drawing: a cell holds the arms it has (left 1, right 2, up 4, down 8); the character follows from the arms ----
export const L = 1, R = 2, U = 4, D = 8;
const BOX = { 3: '─', 12: '│', 10: '┌', 9: '┐', 6: '└', 5: '┘', 11: '┬', 7: '┴', 14: '├', 13: '┤', 15: '┼', 1: '─', 2: '─', 4: '│', 8: '│' };
export const boxChar = (m, ascii) => (ascii ? ((m & 3) && !(m & 12) ? '-' : (m & 12) && !(m & 3) ? '|' : '+') : BOX[m]);
export const BOX_MASK = { '─': 3, '│': 12, '┌': 10, '┐': 9, '└': 6, '┘': 5, '┬': 11, '┴': 7, '├': 14, '┤': 13, '┼': 15 };

export class Canvas {
  constructor(w, h) { this.w = w; this.h = h; this.cells = Array.from({ length: h }, () => Array.from({ length: w }, () => ({ c: ' ', k: '', h: null, m: 0, sr: null }))); }
  put(x, y, s, cls, hit, sr) {
    if (y < 0 || y >= this.h) return;
    for (let i = 0; i < s.length; i++) {
      const cell = this.cells[y][x + i]; if (!cell || x + i < 0) continue;
      cell.c = s[i]; cell.k = cls || ''; cell.h = hit || null; cell.m = 0; cell.sr = i === 0 && sr != null ? sr : null;
    }
  }
  box(x, y, mask, cls) {
    const cell = this.cells[y] && this.cells[y][x]; if (!cell) return;
    cell.m |= mask; cell.k = cls || cell.k || 'ln';
  }
  hline(x1, x2, y, cls) { for (let x = x1; x <= x2; x++) this.box(x, y, (x > x1 ? L : 0) | (x < x2 ? R : 0), cls); }
  vline(x, y1, y2, cls) { for (let y = y1; y <= y2; y++) this.box(x, y, (y > y1 ? U : 0) | (y < y2 ? D : 0), cls); }
  // rows as segments: runs of the same class and hit are merged
  lines(ascii) {
    return this.cells.map((row) => {
      const out = [];
      for (const cell of row) {
        const ch = cell.m ? boxChar(cell.m, ascii) : cell.c, last = out[out.length - 1];
        if (last && last[1] === cell.k && last[2] === cell.h && cell.sr == null && last[3] == null) last[0] += ch;
        else out.push([ch, cell.k, cell.h, cell.sr == null ? undefined : cell.sr]);
      }
      return out;
    });
  }
}

// the part of a line between columns a and b
export function slice(segs, a, b) {
  const out = []; let x = 0;
  for (const s of segs) {
    const e = x + s[0].length;
    if (e > a && x < b) { const t = s[0].slice(Math.max(0, a - x), Math.max(0, b - x)); if (t) out.push([t, s[1], s[2], x >= a ? s[3] : undefined]); }
    x = e;
  }
  return out;
}
