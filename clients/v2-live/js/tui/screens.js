// The terminal's screens as character-cell panes. DOM free: every fact comes from the simulation, in the Core's own words.
// A pane is { id, w, lines, items }; a line is { s: segments, it?: item index, h?: heading level }; an item is something to select.
import { present } from '../../core-words.js';
import { spineOf, spineText, STATIONS } from '../../spine-model.js';
import { clockLabel, REPLAY_CATEGORIES, REPLAY_GAPS, COMMANDS } from '../../sim.js';
import { missionGroups } from '../../term.js';
import { seg, len, clip, pad, lr, wrap, mark, role, glyphs, Canvas, L, R, U, D } from './cells.js';

export class Pane {
  constructor(id, w, ascii) { this.id = id; this.w = w; this.ascii = !!ascii; this.g = glyphs(ascii); this.lines = []; this.items = []; }
  add(s, extra) { const l = Object.assign({ s: typeof s === 'string' ? [seg(s)] : s }, extra); this.lines.push(l); return l; }
  blank() { this.add([]); }
  head(title, n, note) { this.add([seg(title.toUpperCase(), 'dim b')].concat(n != null ? [seg(' ' + this.g.dot + ' ' + n, 'dim')] : [], note ? [seg(' ' + this.g.dot + ' ' + note, 'dim')] : []), { h: 2 }); }
  item(s, it) { const i = this.items.length; this.items.push(Object.assign({ line: this.lines.length }, it)); this.lines.push({ s, it: i }); return i; }
  more(s, i) { this.lines.push({ s, it: i }); }
  para(text, indent, cls) { wrap(text, Math.max(8, this.w - indent)).forEach((l) => this.add([seg(' '.repeat(indent) + l, cls || '')])); }
  kv(rows, indent, keyW) {
    const pre = ' '.repeat(indent || 0), k = Math.min(Math.max(...rows.map((r) => r[0].length)) + 2, keyW || 99);
    const stacked = this.w - (indent || 0) - k < 24;
    rows.forEach(([key, val, cls]) => {
      if (stacked) { this.add([seg(pre + key, 'dim')]); wrap(String(val == null ? '' : val), Math.max(8, this.w - (indent || 0) - 2)).forEach((t) => this.add([seg(pre + '  ' + t, cls || '')])); return; }
      wrap(String(val == null ? '' : val), Math.max(8, this.w - (indent || 0) - k)).forEach((t, i) => this.add([seg(pre + (i ? ' '.repeat(k) : key.padEnd(k)), i ? '' : 'dim'), seg(t, cls || '')]));
    });
  }
}

const projName = (sim, id) => (sim.state.projects.find((p) => p.id === id) || { name: '' }).name;
const liveExec = (sim, m) => Object.values(sim.state.executions).find((e) => e.mission === m.id && (e.state === 'RUNNING' || e.state === 'LOST'));
const word = (machine, state) => present(machine, state).label;
export const SETTLED = ['done', 'inactive'];

// the spine as one cluster and one word (ADR-0054 section 7); the screen reader gets the generated sentence
export function spineSegs(m, ascii) {
  const t = spineText(m.state, m.held_from, ascii), sp = spineOf(m.state, m.held_from), cut = t.indexOf(' ');
  const out = Array.from(t.slice(0, cut)).map((ch, i) => {
    const k = sp.marks[i] || { kind: 'none' };
    return seg(ch, k.kind === 'current' ? role(k.cls) : k.kind === 'passed' ? 't2' : 'dim', null, i ? '' : sp.text);
  });
  out.push(seg(' ' + t.slice(cut + 1), ''));
  return out;
}

// six stations with their labels: one line when it fits, otherwise a column
export function spineBlock(p, m) {
  const sp = spineOf(m.state, m.held_from), cl = spineSegs(m, p.ascii), g = p.g;
  p.add(cl);
  const names = STATIONS;
  if (sp.marks.length && p.w - 2 >= names.join(' / ').length) {
    const parts = [];
    names.forEach((n, i) => { const cur = sp.station === i + 1 && !sp.done && !sp.unknown; if (i) parts.push(seg(' / ', 'dim')); parts.push(seg(cur ? '[' + n + ']' : n, cur ? 'b' : sp.marks[i] && sp.marks[i].kind === 'passed' ? 't2' : 'dim', null, '')); });
    p.add(parts);
  } else if (sp.marks.length) {
    const cluster = Array.from(spineText(m.state, m.held_from, p.ascii).split(' ')[0]);
    names.forEach((n, i) => { const k = sp.marks[i]; p.add([seg(cluster[i] || '?', k.kind === 'current' ? role(k.cls) : k.kind === 'passed' ? 't2' : 'dim', null, ''), seg(' ' + n + (sp.station === i + 1 && !sp.done ? ' ' + g.left : ''), k.kind === 'current' ? 'b' : 't2', null, '')]); });
  }
}

// ---------------- the constellation in text ----------------
// Core at the top, one hub per project, one node per mission; columns when they fit, a tree when they do not.
export function mapPane(sim, w, o) {
  const p = new Pane('map', w, o.ascii), g = p.g, st = sim.state, live = sim.liveWork().length;
  let groups = st.projects.map((pr) => ({ pr, all: Object.values(st.missions).filter((m) => m.project === pr.id) }));
  const hide = (m) => SETTLED.includes(present('mission', m.state).cls);
  const build = (squeeze) => groups.map((x) => ({ pr: x.pr, ms: squeeze ? x.all.filter((m) => !hide(m)) : x.all, hidden: squeeze ? x.all.filter(hide).length : 0 }));
  const cols = Math.floor(w / Math.max(1, groups.length)) >= 22 && w >= 66;
  const height = (gs) => (cols ? 4 + Math.max(...gs.map((x) => x.ms.length), 0) : 1 + gs.reduce((a, x) => a + 1 + x.ms.length, 0));
  const label = (x) => x.pr.name + ' (' + (x.ms.length + x.hidden) + (x.hidden ? ', ' + x.hidden + ' hidden' : '') + ')';
  let gs = build(false);
  if (o.maxH && height(gs) > o.maxH) gs = build(true);
  const cv = new Canvas(w, height(gs));
  const coreTxt = (o.breath ? g.core2 : g.core) + ' ARCHEUS';
  const runTxt = live ? 'RUNNING ' + live : 'idle';
  const node = (x, y, m, avail, spine) => {
    const hit = 'mission:' + m.id, ex = liveExec(sim, m);
    const sel = o.sel === hit ? ' nsel' : '';
    const mk = mark('mission', m.state, o.ascii);
    cv.put(x, y, mk[0], mk[1], hit, mk[3]);
    let tw = avail - 2;
    if (spine) {
      const sg = spineSegs(m, o.ascii), sw = len(sg);
      tw = avail - 2 - 2 - sw - 1;
      cv.put(x + 2, y, pad([seg(m.title.length > tw ? m.title.slice(0, tw - 1) + g.ell : m.title)], tw)[0][0], sel.trim(), hit);
      cv.put(x + 2 + tw + 1, y, ex ? g.exec : ' ', 'act', hit, ex ? 'running' : '');
      let sx = x + 2 + tw + 3; sg.forEach((s) => { cv.put(sx, y, s[0], s[1], hit, s[3]); sx += s[0].length; });
    } else {
      const t = m.title.length > tw - (ex ? 2 : 0) ? m.title.slice(0, tw - (ex ? 2 : 0) - 1) + g.ell : m.title;
      cv.put(x + 2, y, t, sel.trim(), hit);
      if (ex) cv.put(x + 3 + t.length, y, g.exec, 'act', hit, 'running');
    }
  };
  if (cols) {
    const n = gs.length, colW = Math.floor(w / n), hx = gs.map((_, i) => i * colW + 1), cx = Math.floor((hx[0] + hx[n - 1]) / 2);
    const cl = coreTxt.length + 1 + runTxt.length, c0 = Math.max(0, Math.min(w - cl, cx - Math.floor(coreTxt.length / 2)));
    cv.put(c0, 0, coreTxt, 'b'); cv.put(c0 + coreTxt.length + 1, 0, runTxt, live ? 'act b' : 'dim');
    cv.vline(cx, 1, 1, 'ln'); cv.box(cx, 1, D | U, 'ln'); cv.hline(hx[0], hx[n - 1], 2, 'ln'); cv.box(cx, 2, U, 'ln');
    gs.forEach((x, i) => {
      cv.box(hx[i], 2, D, 'ln');
      cv.put(hx[i], 3, g.hub, 'b'); cv.put(hx[i] + 2, 3, label(x), 'b');
      x.ms.forEach((m, j) => { const y = 4 + j; cv.box(hx[i], y, U | R | (j < x.ms.length - 1 ? D : 0), 'ln'); node(hx[i] + 2, y, m, colW - 3, colW - 3 >= 36); });
    });
  } else {
    cv.put(0, 0, coreTxt, 'b'); cv.put(coreTxt.length + 1, 0, runTxt, live ? 'act b' : 'dim');
    let y = 1;
    gs.forEach((x, i) => {
      const last = i === gs.length - 1;
      cv.box(0, y, U | R | (last ? 0 : D), 'ln'); cv.put(2, y, g.hub, 'b'); cv.put(4, y, label(x), 'b');
      y += 1;
      x.ms.forEach((m, j) => {
        if (!last) cv.box(0, y, U | D, 'ln');
        cv.box(2, y, U | R | (j < x.ms.length - 1 ? D : 0), 'ln');
        node(4, y, m, w - 4, false); y += 1;
      });
    });
  }
  cv.lines(o.ascii).forEach((s) => p.add(s));
  // nodes are items in reading order, column by column
  const seen = new Set();
  p.lines.forEach((l, i) => { let x = 0; l.s.forEach((sg) => { if (sg[2] && sg[2].startsWith('mission:') && !seen.has(sg[2])) { seen.add(sg[2]); p.items.push({ key: sg[2], kind: 'mission', id: sg[2].slice(8), mission: sg[2].slice(8), line: i, x }); } x += sg[0].length; }); });
  return p;
}

// ---------------- rows ----------------
function missionItem(p, sim, m, o) {
  const x = liveExec(sim, m), reason = m.reason || (x ? sim.reading(x) : '');
  const i = p.item(lr([mark('mission', m.state, p.ascii), seg(' '), seg(m.title)], [seg(projName(sim, m.project), 'dim')], p.w, p.g.ell), { key: 'mission:' + m.id, kind: 'mission', id: m.id, mission: m.id });
  p.more(clip([seg('  ')].concat(spineSegs(m, p.ascii), reason ? [seg('  ' + reason, 'dim')] : []), p.w, p.g.ell), i);
  return i;
}
function attentionItem(p, sim, a) {
  const m = a.mission_id ? sim.state.missions[a.mission_id] : null, g = p.g;
  const gl = a.group === 'Unblock' ? mark('mission', 'BLOCKED', p.ascii) : mark('mission', 'APPROVAL_REQUIRED', p.ascii);
  const i = p.item(lr([gl, seg(' '), seg(a.reason, a.group === 'Decide' ? 'b' : '')], [seg(a.project_id ? projName(sim, a.project_id) : '', 'dim')], p.w, g.ell), { key: 'att:' + a.id, kind: 'att', id: a.id, ref: a.ref, att: a, mission: a.mission_id });
  const sub = [seg('  ')].concat(m ? spineSegs(m, p.ascii) : [seg(a.group + ' ' + g.dot + ' ' + a.kind, 'dim')], a.since ? [seg('  since ' + clockLabel(a.since), 'dim')] : []);
  p.more(clip(sub, p.w, g.ell), i);
  return i;
}

const MSG = (sim) => sim.state.messages.slice(-3);

export function nowScreen(sim, o) {
  const st = sim.state, att = sim.attention(), g = glyphs(o.ascii), list = new Pane('list', o.w1, o.ascii);
  const decide = att.filter((a) => a.group === 'Decide');
  list.head('Needs you', decide.length);
  if (!decide.length) list.add([seg('Nothing is waiting for a decision.', 'dim')]);
  decide.slice(0, 3).forEach((a) => attentionItem(list, sim, a));
  const rest = att.length - Math.min(3, decide.length);
  if (rest > 0) list.item([seg(rest + ' more in Attention', 'dim')], { key: 'go:attention', kind: 'go', id: 'attention' });
  list.blank();
  const liveM = Object.values(st.missions).filter((m) => ['active', 'verifying', 'reviewing'].includes(present('mission', m.state).cls));
  list.head('Happening now', liveM.length);
  if (!liveM.length) list.add([seg('Nothing is running.', 'dim')]);
  liveM.forEach((m) => missionItem(list, sim, m, o));
  const up = Object.values(st.missions).filter((m) => ['planning', 'approved'].includes(present('mission', m.state).cls));
  if (up.length) { list.blank(); list.head('Upcoming', up.length); up.forEach((m) => missionItem(list, sim, m, o)); }
  const feed = new Pane('feed', o.wf, o.ascii);
  const recent = st.events.filter((e) => /state_changed$/.test(e.type) && e.subject.kind === 'mission').slice(-(o.wide ? 6 : 4)).reverse();
  feed.head('Recent decisions and changes', recent.length);
  recent.forEach((e) => feed.add(clip([seg(clockLabel(e.at), 'dim'), seg(' ' + (st.missions[e.subject.id] || { title: e.subject.id }).title + ' ' + g.dot + ' ' + word('mission', e.payload.from) + ' ' + g.right + ' ' + word('mission', e.payload.to)), seg(e.actor === 'device' ? '  you' : '', 'dim')], feed.w, g.ell)));
  feed.blank(); feed.head('Conversation', null, 'use : to talk');
  MSG(sim).forEach((m) => { const who = m.from === 'you' ? 'you' : 'archeus'; const t = (who + ': ').padEnd(9) + m.text; wrap(t, feed.w).slice(0, 2).forEach((l, i) => feed.add([seg(i ? '         ' + l.trimStart() : l, m.from === 'you' ? '' : 't2')])); });
  const map = mapPane(sim, o.wm, Object.assign({}, o, { maxH: o.mapMax }));
  return { title: 'Now', sentence: sim.sentence(), panes: { list, map, feed }, focus: ['list', 'map'], lead: 'list' };
}

export function workScreen(sim, o) {
  const st = sim.state, list = new Pane('list', o.w1, o.ascii);
  missionGroups(sim).forEach((gr) => { list.head(gr.title, gr.items.length); gr.items.forEach((m) => missionItem(list, sim, m, o)); list.blank(); });
  list.head('Ideas', st.ideas.length);
  st.ideas.forEach((i) => list.add(lr([seg(i.title)], [seg(projName(sim, i.project) + ' ' + list.g.dot + ' ' + word('idea', i.state), 'dim')], list.w, list.g.ell)));
  return { title: 'Work', panes: { list }, focus: ['list'], lead: 'list' };
}

export function attentionScreen(sim, o) {
  const att = sim.attention(), list = new Pane('list', o.w1, o.ascii);
  if (!att.length) list.add([seg('Nothing waits on you.', 'dim')]);
  [['Decide', 'asks you to decide'], ['Review', 'results to accept'], ['Unblock', 'work that needs a person']].forEach(([grp, note]) => {
    const items = att.filter((a) => a.group === grp); if (!items.length) return;
    list.head(grp, items.length, note); items.forEach((a) => attentionItem(list, sim, a)); list.blank();
  });
  return { title: 'Attention', panes: { list }, focus: ['list'], lead: 'list' };
}

export function worldScreen(sim, o) {
  const st = sim.state, list = new Pane('list', o.w1, o.ascii), g = list.g;
  list.head('Projects', st.projects.length);
  st.projects.forEach((pr) => {
    const ms = Object.values(st.missions).filter((m) => m.project === pr.id);
    list.add(lr([seg(g.hub, 'b'), seg(' ' + pr.name, 'b')], [seg(ms.length + ' missions', 'dim')], list.w, g.ell));
    list.add([seg('  ' + pr.note, 'dim')]);
    ms.forEach((m) => list.item(lr([seg('  '), mark('mission', m.state, o.ascii), seg(' ' + m.title)], [seg(word('mission', m.state), 'dim')], list.w, g.ell), { key: 'mission:' + m.id, kind: 'mission', id: m.id, mission: m.id }));
  });
  list.blank(); list.head('What Archeus knows', st.knowledge.length);
  st.knowledge.forEach((k) => list.add(clip([mark('knowledge_item', k.state, o.ascii), seg(' ' + word('knowledge_item', k.state).padEnd(11), 't2'), seg(k.text)], list.w, g.ell)));
  return { title: 'World', panes: { list }, focus: ['list'], lead: 'list' };
}

// ---------------- replay ----------------
export const CATEGORY_MEANING = {
  INTENDED: 'Archeus means to do this; nothing has happened yet.', AUTHORIZED: 'A decision allowed it.', RECORDED: 'Core wrote down that it happened.',
  'MAY-HAVE-TAKEN-EFFECT': 'The work may have changed something; Core cannot confirm.', UNCERTAIN: 'Core cannot tell what happened.', SUSPENDED: 'It waits for a person.',
  RECONCILED: 'Core checked and settled it.', NONE: 'Nothing took effect.', UNKNOWN: 'Core cannot tell: no record, or the record was pruned.'
};
const CATCLS = { INTENDED: 'thk', AUTHORIZED: 't2', RECORDED: 'done', 'MAY-HAVE-TAKEN-EFFECT': 'act', UNCERTAIN: 'att', SUSPENDED: 'pau', RECONCILED: 'done', NONE: 'dim', UNKNOWN: 'att' };

export function replayScreen(sim, o) {
  const ms = Object.values(sim.state.missions), m = ms[((o.mission || 0) % ms.length + ms.length) % ms.length], r = sim.replay(m.id), g = glyphs(o.ascii);
  const list = new Pane('list', o.w1, o.ascii), det = new Pane('detail', o.wd, o.ascii);
  const sel = Math.max(0, Math.min(o.replaySel == null ? r.rows.length - 1 : o.replaySel, r.rows.length - 1));
  list.add(lr([seg(m.title, 'b'), seg('  ' + (o.mission % ms.length + 1) + '/' + ms.length + '  n next, N previous', 'dim')], [], list.w, g.ell));
  list.add(clip([].concat(spineSegs(m, o.ascii)), list.w, g.ell));
  list.blank();
  list.head('What Core recorded', r.rows.length);
  if (!r.rows.length) list.add([seg('No recorded steps for this mission.', 'dim')]);
  const cw = 21;
  r.rows.forEach((x, i) => list.item(clip([seg(x.time, 'dim'), seg(' ' + x.category.padEnd(cw), CATCLS[x.category] || ''), seg(' ' + x.title)], list.w, g.ell), { key: 'step:' + x.seq, kind: 'step', id: String(x.seq), idx: i, row: x, mission: m.id }));
  if (r.pruned) { list.blank(); list.para('Older steps were pruned from the event log, so anything before them is UNKNOWN, not "nothing happened".', 0, 'dim'); }
  const row = r.rows[sel];
  det.head('Selected step');
  if (row) {
    det.kv([['Step', row.title], ['Time', row.time], ['Category', row.category, CATCLS[row.category]], ['Means', CATEGORY_MEANING[row.category] || ''], ['Trigger', row.trigger || 'none recorded'], ['Settled by', row.settled_by], ['Record', row.subject.kind + ' ' + row.subject.id]], 0, 12);
  } else det.add([seg('Nothing selected.', 'dim')]);
  det.blank(); det.head('Categories', REPLAY_CATEGORIES.length, 'rows in this mission');
  REPLAY_CATEGORIES.forEach((c) => { const n = r.rows.filter((x) => x.category === c).length; det.add([seg(String(n).padStart(3), n ? '' : 'dim'), seg(' ' + c.padEnd(cw), CATCLS[c] || '')]); });
  det.blank(); det.head('Not recorded');
  det.para(r.gaps.replace(/^NOT RECORDED: /, ''), 0, 'dim');
  return { title: 'Replay', panes: { list, detail: det }, focus: ['list'], lead: 'list', replayCount: r.rows.length, replayMission: m.id };
}

// ---------------- mission ----------------
export function whyOf(sim, m) {
  const st = sim.state, out = [];
  if (m.state === 'COMPLETED') return [{ text: 'Completed: its result was verified, and a review accepted it.', source: 'mission.state' }];
  if (m.state === 'CANCELLED') return [{ text: 'Cancelled.', source: 'mission.state' }];
  if (m.reason) out.push({ text: m.reason, source: 'mission.reason' });
  const ap = m.approval && st.approvals[m.approval];
  if (ap && ap.state === 'PENDING') out.push({ text: 'A ' + ap.kind + ' approval waits for you until ' + clockLabel(ap.expires_at) + '.', source: 'approval' });
  if ((m.state === 'BLOCKED' || m.state === 'PAUSED') && m.held_from) out.push({ text: (m.state === 'PAUSED' ? 'Paused' : 'Blocked') + ' while ' + word('mission', m.held_from).toLowerCase() + '.', source: 'mission.held_from' });
  Object.values(st.executions).filter((x) => x.mission === m.id && x.state === 'LOST').forEach(() => out.push({ text: 'An execution was lost; Core is reconciling it.', source: 'execution' }));
  if (m.state === 'REVIEWING') out.push({ text: 'Verified, and waiting for your review.', source: 'review' });
  return out.length ? out : [{ text: 'No recorded reason explains this state.', source: 'none' }];
}

// a row of tabs that wraps instead of running off the edge
function tabBar(p, entries, cur, pre) {
  let line = [], n = 0;
  entries.forEach(([id, key, label]) => {
    const t = id === cur ? '[' + (key ? key + ' ' : '') + label + ']' : (key ? key + ' ' : '') + label;
    if (n + t.length + 2 > p.w && line.length) { p.add(line, { tabs: true }); line = []; n = 0; }
    line.push(seg(t, id === cur ? 'b' : 't2', pre + id), seg('  ')); n += t.length + 2;
  });
  if (line.length) p.add(line, { tabs: true });
}

export const TABS = [['outcome', 'o', 'Outcome'], ['plan', 'p', 'Plan'], ['now', 'n', 'Now'], ['evidence', 'e', 'Evidence'], ['why', 'w', 'Why'], ['timeline', 't', 'Timeline'], ['relations', 'r', 'Relations']];

export function missionScreen(sim, o) {
  const st = sim.state, m = st.missions[o.mission] || Object.values(st.missions)[0], g = glyphs(o.ascii), p = new Pane('main', o.w1, o.ascii);
  const tasks = m.tasks.map((id) => st.tasks[id]), execs = Object.values(st.executions).filter((x) => x.mission === m.id);
  const tab = o.tab || 'outcome';
  const pk = mark('mission', m.state, o.ascii);
  // header: title, state, where it is
  const header = (q) => {
    q.add(lr([seg(m.title, 'b')], [pk, seg(' ' + word('mission', m.state), role(present('mission', m.state).cls))], q.w, g.ell));
    q.add([seg(projName(sim, m.project) + ' ' + g.dot + ' ' + m.branch, 'dim')]);
    if (!o.wide) { q.blank(); spineBlock(q, m); const x = liveExec(sim, m); if (x) q.add([seg(sim.reading(x) || '', 'dim')]); }
  };
  header(p); p.blank();
  tabBar(p, TABS, tab, 'tab:');
  p.blank();
  if (tab === 'outcome') {
    p.head('Facts');
    p.kv([['State', word('mission', m.state)], ['Project', projName(sim, m.project)], ['Branch', m.branch], ['Origin', m.origin], ['Plan', m.plan_version ? 'version ' + m.plan_version : 'none yet'], ['Tasks', tasks.filter((t) => t.state === 'SUCCEEDED').length + ' of ' + tasks.length + ' done']].concat(m.reason ? [['Why', m.reason]] : []), 0, 10);
  } else if (tab === 'plan') {
    p.head('Tasks', tasks.length);
    if (!tasks.length) p.add([seg('No plan yet.', 'dim')]);
    tasks.forEach((t) => p.add(lr([mark('task', t.state, o.ascii), seg(' ' + t.title)], [seg(word('task', t.state), 'dim')], p.w, g.ell)));
    p.blank(); p.head('Plan versions');
    Object.values(st.plans).filter((x) => x.mission === m.id).forEach((x) => p.add(lr([mark('plan', x.state, o.ascii), seg(' Version ' + x.version)], [seg(word('plan', x.state), 'dim')], p.w, g.ell)));
  } else if (tab === 'now') {
    p.head('Executions', execs.length);
    if (!execs.length) p.add([seg('No execution yet.', 'dim')]);
    execs.forEach((x) => { p.add(lr([mark('execution', x.state, o.ascii), seg(' ' + x.id)], [seg(word('execution', x.state), 'dim')], p.w, g.ell)); p.add([seg('  ' + x.harness + ' ' + g.dot + ' ' + x.model + (sim.reading(x) ? ' ' + g.dot + ' ' + sim.reading(x) : ''), 'dim')]); });
  } else if (tab === 'evidence') {
    const vs = Object.values(st.verifications).filter((x) => x.mission === m.id);
    p.head('Verification', vs.length);
    if (!vs.length) p.add([seg('Nothing has been verified yet.', 'dim')]);
    vs.forEach((v) => { p.add(lr([mark('verification', v.state, o.ascii), seg(' ' + v.id + ' ' + g.dot + ' base ' + v.base_revision)], [seg(word('verification', v.state), 'dim')], p.w, g.ell)); v.checks.forEach((c) => p.add(lr([seg('  ' + c.name)], [seg(c.result, c.result === 'pass' ? 'done' : 'blk')], p.w, g.ell))); });
    const rs = Object.values(st.reviews).filter((x) => x.mission === m.id);
    if (rs.length) { p.blank(); p.head('Review', rs.length); rs.forEach((r) => p.add([mark('review', r.state, o.ascii), seg(' ' + r.id + ' ' + g.dot + ' ' + word('review', r.state))])); }
  } else if (tab === 'why') {
    p.head('Why it is in this state');
    whyOf(sim, m).forEach((w) => { wrap(w.text, p.w - 2).forEach((l, i) => p.add([seg('  ' + l), i === wrap(w.text, p.w - 2).length - 1 ? seg('  (' + w.source + ')', 'dim') : seg('')])); });
    p.blank(); p.head('Last state changes');
    st.events.filter((e) => e.mission === m.id && /state_changed$/.test(e.type) && e.subject.kind === 'mission').slice(-4).reverse().forEach((e) => p.add(clip([seg(clockLabel(e.at), 'dim'), seg(' ' + word('mission', e.payload.from) + ' ' + g.right + ' ' + word('mission', e.payload.to)), seg('  ' + e.payload.trigger, 'dim')], p.w, g.ell)));
  } else if (tab === 'timeline') {
    const r = sim.replay(m.id);
    p.head('Last recorded steps', Math.min(8, r.rows.length), 'r opens Replay');
    r.rows.slice(-8).reverse().forEach((x) => p.add(clip([seg(x.time, 'dim'), seg(' ' + x.category.padEnd(21), CATCLS[x.category] || ''), seg(' ' + x.title)], p.w, g.ell)));
  } else {
    p.head('Recorded relations');
    const rel = (kind, id, st2) => p.add(lr([seg(kind.padEnd(13), 'dim'), seg(id)], [seg(st2 || '', 'dim')], p.w, g.ell));
    rel('project', m.project, projName(sim, m.project));
    tasks.forEach((t) => rel('task', t.id, word('task', t.state)));
    execs.forEach((x) => rel('execution', x.id, word('execution', x.state)));
    Object.values(st.plans).filter((x) => x.mission === m.id).forEach((x) => rel('plan', x.id, word('plan', x.state)));
    Object.values(st.approvals).filter((x) => x.mission === m.id).forEach((x) => rel('approval', x.id, word('approval', x.state)));
    Object.values(st.verifications).filter((x) => x.mission === m.id).forEach((x) => rel('verification', x.id, word('verification', x.state)));
  }
  const panes = { main: p };
  if (o.wide) panes.side = summaryPane(sim, { kind: 'mission', mission: m.id }, o.wd, o.ascii, true);
  return { title: m.title, panes, focus: ['main'], lead: 'main', mission: m.id, tab };
}

// ---------------- the decision card (Attention, approval) ----------------
export function decisionPane(sim, a, w, ascii) {
  const p = new Pane('detail', w, ascii), g = p.g, m = sim.state.missions[a.mission];
  const open = a.state === 'PENDING';
  p.add(lr([mark('approval', a.state, ascii), seg(' ' + (a.kind === 'plan' ? 'Approve this plan?' : 'Allow this action?'), 'b')], [seg(word('approval', a.state), 'dim')], w, g.ell));
  p.add([seg(m.title + ' ' + g.dot + ' ' + projName(sim, a.project), 'dim')]);
  p.blank();
  p.kv([['What', a.presented.what, 'b'], ['Why it asks', a.presented.why], ['What Core does next', a.presented.consequence], ['Expires', open ? clockLabel(a.expires_at) : 'decided: ' + word('approval', a.state).toLowerCase()]], 0, 22);
  p.blank(); p.head('Where the mission is'); spineBlock(p, m);
  p.blank(); p.para(open ? 'This is a simulated decision: nothing is run, sent or spent.' : 'Decided.', 0, 'dim');
  return p;
}

// ---------------- control: accounts and usage, automations, clients, security, health, appearance, about ----------------
export const SECTIONS = [['accounts', 'Accounts'], ['automations', 'Automations'], ['clients', 'Clients'], ['security', 'Security'], ['health', 'Health'], ['appearance', 'Appearance'], ['about', 'About']];
const FIG = { ok: ['done', 'Ok'], off: ['paused', 'Off'], open: ['blocked', 'Open'], attention: ['needs_you', 'Needs attention'], unknown: ['inactive', 'Unknown'] };
const figMark = (state, ascii) => { const f = FIG[state] || FIG.unknown; return seg(ascii ? ({ done: '+', paused: '=', blocked: '#', needs_you: '!', inactive: '-' })[f[0]] : ({ done: '✓', paused: '‖', blocked: '■', needs_you: '◆', inactive: '–' })[f[0]], role(f[0]), null, f[1]); };

export function meterLine(p, label, v, cap) {
  const g = p.g, bw = Math.max(6, Math.min(24, p.w - 4 - label.length - 8));
  const pct = v == null ? 'unknown' : Math.round(v) + '%';
  if (v == null) return p.add([seg('  ' + label.padEnd(15)), seg('unknown', 'dim'), seg(cap ? '  ' + cap : '', 'dim')]);
  const on = Math.round(Math.min(100, v) / 100 * bw);
  p.add(clip([seg('  ' + label.padEnd(15)), seg('['), seg(g.on.repeat(on), v >= 85 ? 'att' : 'act', null, ''), seg(g.off.repeat(bw - on), 'dim', null, ''), seg('] '), seg(pct.padStart(4), v >= 85 ? 'att b' : ''), seg(cap ? '  ' + cap : '', 'dim')], p.w, g.ell));
}

export function controlScreen(sim, o) {
  const st = sim.state, p = new Pane('main', o.w1, o.ascii), g = p.g, sec = o.section || 'accounts';
  tabBar(p, SECTIONS.map(([id, label]) => [id, '', label]), sec, 'sec:');
  p.blank();
  const line = (left, right, rc) => p.add(lr(left, [seg(right || '', rc || 'dim')], p.w, g.ell));
  if (sec === 'accounts') {
    p.head('Accounts and usage', st.accounts.length);
    st.accounts.forEach((a) => { line([mark('account_health', a.state, o.ascii), seg(' ' + a.label, 'b')], word('account_health', a.state)); const u = st.usage[a.id]; meterLine(p, '5 hour window', u.window5h, u.resets); meterLine(p, 'Week', u.week); });
    p.blank(); p.head('Models and harnesses', st.models.length);
    st.models.forEach((m) => line([seg(m.label)], m.harness + ' ' + g.dot + ' ' + m.tier));
    st.harnesses.forEach((x) => line([seg(x.label + (x.breaker.state !== 'closed' ? ' ' + g.dot + ' breaker ' + x.breaker.state.replace('_', ' ') : ''))], x.breaker.last_error && x.breaker.state !== 'closed' ? x.breaker.last_error : x.state.toLowerCase()));
  } else if (sec === 'automations') {
    p.head('Automations', st.automations.length);
    st.automations.forEach((a) => { line([mark('automation', a.state, o.ascii), seg(' ' + a.name)], word('automation', a.state)); p.add([seg('  ' + a.trigger + (a.note ? ' ' + g.dot + ' ' + a.note : ''), 'dim')]); });
  } else if (sec === 'clients') {
    p.head('Clients', st.devices.length); st.devices.forEach((d) => line([mark('device', d.state, o.ascii), seg(' ' + d.name)], d.state.toLowerCase()));
    p.blank(); p.head('Hooks', st.hooks.length); st.hooks.forEach((x) => line([seg(x.name)], x.event + ' ' + g.dot + ' ' + x.state.toLowerCase()));
    p.blank(); p.head('MCP servers', st.mcp.length); st.mcp.forEach((x) => line([seg(x.name)], x.state.toLowerCase()));
    p.blank(); p.head('Agents', st.agents.length); st.agents.forEach((x) => line([seg(x.name)], x.tier));
  } else if (sec === 'security') {
    p.head('Isolation and switches', sim.security().length);
    sim.security().forEach((x) => { line([figMark(x.state, o.ascii), seg(' ' + x.label)], x.word); wrap(x.note, p.w - 4).forEach((l) => p.add([seg('    ' + l, 'dim')])); });
    p.blank(); p.head('Owner rules');
    ['Never push, never touch credentials: Archeus does not read, store, copy, inject or relay subscription tokens.', 'Decisions are the owner\'s: chat proposes; only a card on screen with its hash is decided.', 'No silent approval: a new mission from chat waits for a card here.'].forEach((t) => p.para(t, 2));
  } else if (sec === 'health') {
    const items = sim.health(), n = (s) => items.filter((x) => x.state === s).length;
    p.head('Checks', items.length, n('ok') + ' ok ' + g.dot + ' ' + n('attention') + ' need attention ' + g.dot + ' ' + n('unknown') + ' unknown');
    items.forEach((x) => { line([figMark(x.state, o.ascii), seg(' ' + x.label)], FIG[x.state] ? FIG[x.state][1] : ''); wrap(x.detail, p.w - 4).forEach((l) => p.add([seg('    ' + l, 'dim')])); });
  } else if (sec === 'appearance') {
    p.head('This terminal');
    p.kv([['Colours', o.look.label + ' (key C cycles)'], ['Glyphs', o.ascii ? 'ASCII only (key G)' : 'Unicode (key G)'], ['Reading mode', o.linear ? 'Linear text for a screen reader (key T)' : 'Character grid (key T)'], ['Motion', o.reduced ? 'Quiet: the core mark is still' : 'Full: the core mark breathes while work is live'], ['Layout', o.cols + ' columns ' + g.dot + ' ' + o.rows + ' rows ' + g.dot + ' ' + o.tier]], 0, 14);
    p.blank(); p.para('The terminal keeps its own colours; the app chooses its own. Nothing in the real terminal moves: a change is shown when it is read.', 0, 'dim');
  } else {
    p.head('This build');
    p.kv([['Prototype', 'V2 Live, a simulation'], ['Core', 'none connected'], ['Seed', String(st.seed)], ['Simulated time', clockLabel(st.clock, true)], ['Events kept', st.events.length + (st.pruned ? ' (older ones pruned)' : '')]], 0, 16);
    p.blank(); p.head('Emergency stop'); p.para('Pauses every running mission. Press E; you confirm first.', 0, 'dim');
  }
  return { title: 'Control', panes: { main: p }, focus: ['main'], lead: 'main', section: sec };
}

// ---------------- help ----------------
export const KEYS = [
  ['↑ ↓  j k', 'move', 'muovi'], ['Enter', 'open', 'apri'], ['Esc  b', 'back', 'indietro'], ['Tab', 'next pane or tab (Shift+Tab back)', 'riquadro o scheda successiva (Maiusc+Tab indietro)'],
  ['1 2 3 a r 4', 'Now, Work, World, Attention, Replay, Control', 'Adesso, Lavoro, Mondo, Attenzione, Replay, Controllo'], ['g', 'places: every screen by letter', 'luoghi: ogni schermata con una lettera'],
  [': or /', 'command line: go to, or a slash command', 'riga di comando: vai a, o un comando con barra'], ['t', 'tell Archeus (opens the command line)', 'scrivi ad Archeus (apre la riga di comando)'],
  ['[ ]  PgUp PgDn', 'page', 'pagina'], ['A  R  C  P  X', 'the actions on the bottom line; decisions ask y first', 'le azioni nella riga in basso; le decisioni chiedono prima y'],
  ['E', 'emergency stop: pause every running mission (asks y)', 'arresto di emergenza: mette in pausa ogni missione (chiede y)'], ['n N', 'next or previous mission in Replay', 'missione successiva o precedente in Replay'],
  ['?', 'this help', 'questo aiuto'], ['q', 'back; on Now it leaves the terminal view', 'indietro; in Adesso esce dal terminale']
];
export function helpLines(w, lang, ascii) {
  const it = lang === 'it', out = [{ s: [seg(it ? 'Tasti' : 'Keys', 'b')] }, { s: [] }];
  KEYS.forEach(([k, en, ita]) => {
    const kk = ascii ? k.replace('↑ ↓', 'Up Dn') : k, kw = 16;
    wrap(it ? ita : en, Math.max(10, w - kw - 2)).forEach((l, i) => out.push({ s: [seg(i ? ' '.repeat(kw) : kk.padEnd(kw), 'b'), seg(l)] }));
  });
  out.push({ s: [] }, { s: [seg('Slash commands', 'b')] });
  ['READ', 'NAVIGATE', 'CREATE', 'PROPOSE'].forEach((c) => wrap(COMMANDS.filter((x) => x.cls === c).map((x) => '/' + (it ? x.it : x.name)).join(' '), Math.max(10, w - 12)).forEach((l, i) => out.push({ s: [seg(i ? ' '.repeat(10) : c.padEnd(10), 'dim'), seg(l)] })));
  out.push({ s: [] }, { s: [seg(it ? 'Qualsiasi tasto chiude.' : 'Any key closes this.', 'dim')] });
  return out;
}
export const PLACES = [['1', 'now', 'Now', 'Adesso'], ['2', 'work', 'Work', 'Lavoro'], ['3', 'world', 'World', 'Mondo'], ['a', 'attention', 'Attention', 'Attenzione'], ['r', 'replay', 'Replay', 'Replay'], ['4', 'control', 'Control', 'Controllo'],
  ['s', 'security', 'Security', 'Sicurezza'], ['h', 'health', 'Health', 'Salute'], ['u', 'accounts', 'Usage and accounts', 'Uso e account']];

// ---------------- the short card of whatever is selected (the right hand pane on wide screens) ----------------
export function summaryPane(sim, item, w, ascii, noTitle) {
  const st = sim.state, p = new Pane('detail', w, ascii), g = p.g;
  if (!item) { p.add([seg('Nothing selected.', 'dim')]); return p; }
  const ap = item.kind === 'att' && item.att.kind === 'approval' ? st.approvals[item.att.ref] : null;
  if (ap) return decisionPane(sim, ap, w, ascii);
  const m = item.mission && st.missions[item.mission];
  if (m) {
    const x = liveExec(sim, m), tasks = m.tasks.map((id) => st.tasks[id]);
    if (!noTitle) {
      p.add(lr([seg(m.title, 'b')], [mark('mission', m.state, ascii), seg(' ' + word('mission', m.state), role(present('mission', m.state).cls))], w, g.ell));
      p.add([seg(projName(sim, m.project) + ' ' + g.dot + ' ' + m.branch, 'dim')]);
      p.blank();
    }
    p.head('Where it is'); spineBlock(p, m);
    if (x) p.add([seg(x.harness + ' ' + g.dot + ' ' + (sim.reading(x) || word('execution', x.state)), 'dim')]);
    p.blank(); p.kv([['Tasks', tasks.filter((t) => t.state === 'SUCCEEDED').length + ' of ' + tasks.length + ' done'], ['Plan', m.plan_version ? 'version ' + m.plan_version : 'none yet'], ['Origin', m.origin]], 0, 8);
    p.blank(); p.head('Why');
    whyOf(sim, m).forEach((r) => p.para(r.text, 0));
    return p;
  }
  if (item.att) { p.add([seg(item.att.reason, 'b')]); p.blank(); p.para(item.att.group + ' ' + g.dot + ' ' + item.att.kind, 0, 'dim'); return p; }
  p.add([seg('Nothing to show.', 'dim')]);
  return p;
}
