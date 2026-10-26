// The terminal's brain, DOM free: screens, panes, keys, the command line, overlays. frame({cols, rows}) answers with the lines to draw;
// key(name) changes the state. The view (view.js) turns key events into names and frames into elements, and nothing else.
import { present } from '../../core-words.js';
import { clockLabel } from '../../sim.js';
import { seg, len, clip, pad, lr, wrap, slice, speech, glyphs, boxChar, asciify } from './cells.js';
import { parse, complete } from './cmd.js';
import {
  nowScreen, workScreen, attentionScreen, worldScreen, replayScreen, missionScreen, controlScreen, decisionPane, summaryPane, Pane,
  TABS, SECTIONS, PLACES, helpLines
} from './screens.js';

export const LOOKS = [{ id: 'app', label: 'App colours', short: 'Colours' }, { id: 'ansi', label: 'ANSI 16 colours', short: 'ANSI 16' }, { id: 'hc', label: 'High contrast', short: 'Contrast' }, { id: 'mono', label: 'Monochrome', short: 'Mono' }];
const SAY = { approve: 'Approved (simulated). Nothing was run.', reject: 'Rejected (simulated).', accept: 'Accepted (simulated).', changes: 'Changes requested (simulated).', unblock: 'Unblocked (simulated).', resume: 'Resumed (simulated).', replan: 'Replanning (simulated).', cancel: 'Cancelled (simulated).', pause: 'Pausing (simulated).', confirm: 'Remembered (simulated).', retract: 'Not remembered (simulated).', enable: 'Enabled (simulated).' };
const NAV = [['1', 'now', 'Now', 'Adesso'], ['2', 'work', 'Work', 'Lavoro'], ['3', 'world', 'World', 'Mondo'], ['a', 'attention', 'Attention', 'Attenzione'], ['r', 'replay', 'Replay', 'Replay'], ['4', 'control', 'Control', 'Controllo']];
const SCREENS = { now: nowScreen, work: workScreen, attention: attentionScreen, world: worldScreen, replay: replayScreen, mission: missionScreen, control: controlScreen };
const NAMED = /^(up|down|left|right|enter|esc|tab|shift-tab|backspace|pageup|pagedown|home|end)$/;
export const TERM_SCREENS = ['now', 'work', 'world', 'attention', 'replay', 'control', 'mission', 'decision'];
const HINT = {
  en: { move: 'move', open: 'open', pane: 'pane', tab: 'tab', help: 'help', cmd: 'command', back: 'back', more: 'more below' },
  it: { move: 'muovi', open: 'apri', pane: 'riquadro', tab: 'scheda', help: 'aiuto', cmd: 'comando', back: 'indietro', more: 'altro sotto' }
};

export function createTui(sim, opts = {}) {
  const lang = () => (opts.lang ? opts.lang() : 'en');
  const S = {
    screen: 'now', stack: [], focus: 'list', src: 'list', sel: {}, idx: {}, top: {}, mission: Object.keys(sim.state.missions)[1] || Object.keys(sim.state.missions)[0], tab: 'outcome', section: 'accounts',
    replayMission: 1, replaySel: null, approval: null, mode: null, status: null, breath: false, cols: 80, rows: 30
  };
  const prefs = Object.assign({ look: 'app', ascii: false, linear: false }, opts.prefs);
  let last = null, dirty = true;
  const changed = () => { dirty = true; if (opts.onChange) opts.onChange(); };
  const say = (text, err) => { S.status = { text, err: !!err }; };
  const missionIds = () => Object.keys(sim.state.missions);

  // ---------- going places ----------
  function go(screen, arg) {
    if (screen !== S.screen && S.screen !== 'mission' && S.screen !== 'decision') S.stack = [];
    if (SECTIONS.some((x) => x[0] === screen)) { S.section = screen; screen = 'control'; }
    if (screen === 'control' && arg) S.section = arg;
    if (screen === 'replay') { const i = missionIds().indexOf(arg || S.mission); S.replayMission = i < 0 ? S.replayMission : i; S.sel['replay:list'] = undefined; S.idx['replay:list'] = undefined; }
    S.screen = screen; S.focus = ''; S.mode = null; S.status = null;
    changed();
  }
  function push(screen, patch) { S.stack.push({ screen: S.screen, focus: S.focus, mission: S.mission, tab: S.tab, approval: S.approval }); Object.assign(S, patch, { screen, focus: '', mode: null, status: null }); if (patch && patch.tab == null) S.tab = 'outcome'; changed(); }
  function back() {
    const p = S.stack.pop();
    if (!p) return false;
    Object.assign(S, p, { mode: null, status: null }); changed(); return true;
  }
  function openHref(href) {
    const m = /^#\/(\w+)(?:\/([\w-]+))?/.exec(href || ''); if (!m) return;
    if (m[1] === 'work' && m[2]) push('mission', { mission: m[2] });
    else if (m[1] === 'attention' && m[2] && sim.state.approvals[m[2]]) push('decision', { approval: m[2] });
    else if (m[1] === 'replay') go('replay', m[2]);
    else go(m[1] === 'attention' ? 'attention' : 'now');
  }

  // ---------- what can be done to the selected thing ----------
  const missionActs = (m) => {
    const out = [], st = m.state;
    if (st === 'APPROVAL_REQUIRED' && m.approval && sim.state.approvals[m.approval]) return approvalActs(sim.state.approvals[m.approval]);
    if (st === 'EXECUTING') out.push({ key: 'P', label: 'Pause', kind: 'pause', id: m.id });
    if (st === 'PAUSED') out.push({ key: 'R', label: 'Resume', kind: 'resume', id: m.id });
    if (st === 'BLOCKED') out.push({ key: 'R', label: 'Answer and unblock', kind: 'unblock', id: m.id });
    if (st === 'FAILED') out.push({ key: 'R', label: 'Replan', kind: 'replan', id: m.id });
    if (st === 'REVIEWING') out.push({ key: 'A', label: 'Accept', kind: 'accept', id: m.id, confirm: 'Accept: the mission is marked Done once you confirm.' }, { key: 'C', label: 'Request changes', kind: 'changes', id: m.id, confirm: 'Request changes: the mission replans and waits for a new plan.' });
    if (['CREATED', 'PAUSED', 'BLOCKED', 'FAILED'].includes(st)) out.push({ key: 'X', label: 'Cancel mission', kind: 'cancel', id: m.id, confirm: 'Cancel this mission. It cannot be restarted; you would start a new one.' });
    return out;
  };
  const approvalActs = (a) => (a.state === 'PENDING' ? [
    { key: 'A', label: a.kind === 'plan' ? 'Approve plan' : 'Approve', kind: 'approve', id: a.id, confirm: 'Approve: ' + a.presented.consequence },
    { key: 'R', label: 'Reject', kind: 'reject', id: a.id, confirm: 'Reject: ' + a.presented.consequence }] : []);
  function actions(item) {
    const st = sim.state;
    if (S.screen === 'decision') { const a = st.approvals[S.approval]; return a ? approvalActs(a) : []; }
    if (S.screen === 'mission') return missionActs(st.missions[S.mission]);
    if (!item) return [];
    if (item.kind === 'att') {
      const a = item.att;
      if (a.kind === 'approval') return approvalActs(st.approvals[a.ref]);
      if (a.kind === 'knowledge') return [{ key: 'A', label: 'Remember', kind: 'confirm', id: a.ref }, { key: 'R', label: 'Not this', kind: 'retract', id: a.ref }];
      if (a.kind === 'automation') return [{ key: 'A', label: a.state === 'SUSPENDED' ? 'Re-enable' : 'Approve', kind: 'enable', id: a.ref }];
      if (a.mission_id) return missionActs(st.missions[a.mission_id]);
      return [];
    }
    if (item.kind === 'mission') return missionActs(st.missions[item.mission]);
    return [];
  }
  const estop = () => { const run = Object.values(sim.state.missions).filter((m) => m.state === 'EXECUTING'); return run.length ? { key: 'E', label: 'Emergency stop', kind: 'estop', ids: run.map((m) => m.id), confirm: 'Pause every running mission (' + run.map((m) => m.title).join(', ') + '). Nothing is lost; each one waits for you.' } : null; };
  function run(act) {
    if (act.confirm && !act.done) { S.mode = { kind: 'confirm', act }; changed(); return; }
    S.mode = null;
    const ids = act.ids || [act.id]; let r = { ok: true };
    ids.forEach((id) => { const x = sim.act(act.kind === 'estop' ? 'pause' : act.kind, id); if (!x.ok) r = x; });
    if (r.ok && S.screen === 'decision') back();
    say(r.ok ? (act.kind === 'estop' ? 'Pausing every running mission (simulated).' : SAY[act.kind] || 'Done (simulated).') : 'Not done: ' + r.reason, !r.ok);
    changed();
  }

  // ---------- the command line ----------
  const navHits = (q) => {
    const needle = q.trim().toLowerCase(), out = [];
    PLACES.forEach(([k, id, en, it]) => out.push({ label: 'Go to ' + en, run: () => go(id) }));
    Object.values(sim.state.missions).forEach((m) => out.push({ label: 'Mission: ' + m.title, run: () => push('mission', { mission: m.id }) }));
    const hit = out.filter((h) => !needle || h.label.toLowerCase().includes(needle));
    if (needle) hit.push({ label: 'Tell Archeus: ' + q.trim(), run: () => tell(q.trim()) });
    return hit;
  };
  function cmdHits() {
    const buf = S.mode.buf;
    if (buf.startsWith('/') && !buf.includes(' ')) return complete(buf, lang()).map((c) => ({ label: c.label, cls: c.cls, desc: c.desc, insert: c.insert, run: () => { S.mode.buf = c.insert; } }));
    if (buf.startsWith('/')) { const p = parse(buf); return [{ label: p.kind === 'command' ? 'Run ' + buf.trim() : p.reason || 'Unknown command', cls: p.kind === 'command' ? p.cmd.cls : '', run: () => tell(buf) }]; }
    return navHits(buf);
  }
  function tell(text) {
    const before = sim.state.messages.length, r = sim.say(text);
    if (!r.ok) { say(r.reason, true); return false; }
    const msgs = sim.state.messages.slice(before + 1);
    S.mode = msgs.length ? { kind: 'reply', msg: msgs[msgs.length - 1] } : null;
    changed(); return true;
  }
  function cmdKey(k) {
    const m = S.mode, hits = cmdHits();
    m.i = Math.max(0, Math.min(m.i || 0, hits.length - 1));
    if (k === 'esc') { S.mode = null; } else if (k === 'up') m.i = Math.max(0, m.i - 1); else if (k === 'down') m.i = Math.min(hits.length - 1, m.i + 1);
    else if (k === 'tab') { const h = hits[m.i]; if (h && h.insert) m.buf = h.insert; } else if (k === 'backspace') { m.buf = m.buf.slice(0, -1); m.i = 0; }
    else if (k === 'enter') {
      const h = hits[m.i];
      if (!m.buf.trim()) S.mode = null;
      else if (m.buf.startsWith('/') && !m.buf.includes(' ') && h && h.insert && m.buf.trim() !== h.insert.trim()) m.buf = h.insert;
      else if (m.buf.startsWith('/')) tell(m.buf);
      else if (h) { S.mode = null; h.run(); }
      else tell(m.buf);
    } else if (k.length === 1) { m.buf += k; m.i = 0; } else return false;
    changed(); return true;
  }
  const openCmd = (buf) => { S.mode = { kind: 'cmd', buf: buf || '', i: 0 }; changed(); };

  // ---------- keys ----------
  function modeKey(k) {
    const m = S.mode;
    if (m.kind === 'cmd') return cmdKey(k);
    if (m.kind === 'confirm') { const a = m.act; S.mode = null; if (k === 'y' || k === 'Y') run(Object.assign({}, a, { done: true })); else say('Cancelled. Nothing was sent.'); changed(); return true; }
    if (m.kind === 'places') { const p = PLACES.find((x) => x[0] === k); S.mode = null; if (p) go(p[1]); changed(); return true; }
    if (m.kind === 'reply') {
      const c = m.msg.card;
      if (c && c.kind === 'proposal' && c.state === 'open' && (k === 'y' || k === 'n')) { const r = sim.cardAction(m.msg.id, k === 'y' ? 'confirm' : 'dismiss'); S.mode = null; say(r.ok ? (k === 'y' ? 'Confirmed (simulated).' : 'Dismissed.') : 'Not done: ' + r.reason, !r.ok); }
      else if (c && c.kind === 'link' && (k === 'enter' || k === 'o')) { S.mode = null; openHref(c.href); }
      else S.mode = null;
      changed(); return true;
    }
    S.mode = null; changed(); return true; // help: any key closes
  }

  function cycleTab(d) {
    if (S.screen === 'mission') { const i = TABS.findIndex((t) => t[0] === S.tab); S.tab = TABS[(i + d + TABS.length) % TABS.length][0]; S.top.main = 0; }
    else if (S.screen === 'control') { const i = SECTIONS.findIndex((t) => t[0] === S.section); S.section = SECTIONS[(i + d + SECTIONS.length) % SECTIONS.length][0]; S.top.main = 0; }
    else if (last) { const f = last.focusOrder, i = f.indexOf(S.focus); S.focus = f[(i + d + f.length) % f.length]; }
    changed();
  }
  function move(d) {
    if (!last) return;
    const pane = last.panes[S.focus];
    if (!pane || !pane.items.length) { S.dscroll = Math.max(0, Math.min(Math.max(0, (pane ? pane.lines.length : 1) - 1), (S.dscroll || 0) + d)); changed(); return; }
    const key = S.screen + ':' + S.focus, i = Math.max(0, Math.min(pane.items.length - 1, (pane.cur || 0) + d));
    S.sel[key] = pane.items[i].key; S.idx[key] = i; S.src = S.focus;
    if (S.screen === 'replay' && pane.items[i].row) S.replaySel = pane.items[i].idx;
    S.dscroll = 0; changed();
  }
  function moveSide(d) {
    const pane = last && last.panes[S.focus]; if (!pane || S.focus !== 'map' || !pane.items.length) return;
    const cur = pane.items[pane.cur || 0], x = (n) => n.x;
    const row = cur.line, cand = pane.items.filter((n) => (d > 0 ? n.x > cur.x : n.x < cur.x)).sort((a, b) => Math.abs(a.line - row) - Math.abs(b.line - row) || Math.abs(x(a) - x(cur)) - Math.abs(x(b) - x(cur)))[0];
    if (!cand) return;
    S.sel[S.screen + ':map'] = cand.key; S.idx[S.screen + ':map'] = pane.items.indexOf(cand); changed();
  }
  function open(item) {
    if (!item) return false;
    if (item.kind === 'go') { go(item.id); return true; }
    if (item.kind === 'att') {
      const a = item.att;
      if (a.kind === 'approval') { push('decision', { approval: a.ref }); return true; }
      if (a.mission_id) { push('mission', { mission: a.mission_id }); return true; }
      say(a.kind === 'knowledge' ? 'A remembers it, R does not.' : 'Use the keys on the bottom line.'); changed(); return true;
    }
    if (item.kind === 'mission') { push('mission', { mission: item.mission }); return true; }
    return false;
  }
  const selected = () => { if (dirty) frame({ cols: S.cols, rows: S.rows }); return last ? last.item : null; };

  function key(k) {
    if (dirty) frame({ cols: S.cols, rows: S.rows });
    if (S.mode) return modeKey(k);
    S.status = null;
    const scr = S.screen;
    if (scr === 'mission') { const t = TABS.find((x) => x[1] === k); if (t) { S.tab = t[0]; S.top.main = 0; changed(); return true; } }
    if (k === 'up' || k === 'k') move(-1); else if (k === 'down' || k === 'j') move(1);
    else if (k === 'left' || k === 'h') { if (scr === 'mission' || scr === 'control') cycleTab(-1); else moveSide(-1); } else if (k === 'right' || k === 'l') { if (scr === 'mission' || scr === 'control') cycleTab(1); else moveSide(1); }
    else if (k === 'pagedown' || k === ']') move(Math.max(1, (last ? last.bodyH : 10) - 2)); else if (k === 'pageup' || k === '[') move(-Math.max(1, (last ? last.bodyH : 10) - 2));
    else if (k === 'home') move(-1e6); else if (k === 'end') move(1e6);
    else if (k === 'tab') cycleTab(1); else if (k === 'shift-tab') cycleTab(-1);
    else if (k === 'enter') { if (!open(selected())) { if (scr === 'mission' || scr === 'control') cycleTab(1); } }
    else if (k === 'esc' || k === 'b') { if (!back()) { if (scr !== 'now') go('now'); } }
    else if (k === 'q') { if (!back()) { if (scr !== 'now') go('now'); else if (opts.onQuit) opts.onQuit(); } }
    else if (k === '?') { S.mode = { kind: 'help' }; changed(); } else if (k === ':' || k === '/') openCmd(k === '/' ? '/' : '');
    else if (k === 't' && scr !== 'mission') openCmd(''); else if (k === 'g') { S.mode = { kind: 'places' }; changed(); }
    else if (k === '1') go('now'); else if (k === '2') go('work'); else if (k === '3') go('world'); else if (k === '4') go('control');
    else if (k === 'a' && scr !== 'mission') go('attention');
    else if (k === 'r' && scr !== 'mission') { const it = selected(); go('replay', it && it.mission); }
    else if ((k === 'n' || k === 'N') && scr === 'replay') { const n = missionIds().length; S.replayMission = (S.replayMission + (k === 'n' ? 1 : n - 1)) % n; S.sel['replay:list'] = undefined; S.idx['replay:list'] = undefined; S.replaySel = null; changed(); }
    else if (k === 'E') { const e = estop(); if (e) run(e); else { say('Nothing is running.'); changed(); } }
    else if (k === 'L') { prefs.look = LOOKS[(LOOKS.findIndex((x) => x.id === prefs.look) + 1) % LOOKS.length].id; if (opts.onPrefs) opts.onPrefs(prefs); changed(); }
    else if (k === 'G') { prefs.ascii = !prefs.ascii; if (opts.onPrefs) opts.onPrefs(prefs); changed(); } else if (k === 'T' ) { prefs.linear = !prefs.linear; if (opts.onPrefs) opts.onPrefs(prefs); changed(); }
    else if (k.length === 1 && k === k.toUpperCase() && k !== k.toLowerCase()) {
      const act = actions(selected()).find((a) => a.key === k);
      if (act) run(act); else return false;
    } else return false;
    return true;
  }

  // a click names a hit: nav:<screen>, tab:<id>, sec:<id>, act:<KEY>, mission:<id>, att:<id>
  function click(hit) {
    if (!hit) return;
    const [kind, id] = [hit.slice(0, hit.indexOf(':')), hit.slice(hit.indexOf(':') + 1)];
    if (S.mode) { if (S.mode.kind === 'confirm' && kind === 'act') return key(id); return key('esc'); }
    if (kind === 'nav') go(id); else if (kind === 'tab') { S.tab = id; changed(); } else if (kind === 'sec') { S.section = id; changed(); }
    else if (kind === 'act') key(id);
    else if (kind === 'mission' || kind === 'att' || kind === 'step' || kind === 'go') {
      const pid = last && Object.keys(last.panes).find((p) => last.panes[p].items.some((it) => it.key === hit));
      if (!pid) return;
      const pane = last.panes[pid], i = pane.items.findIndex((it) => it.key === hit), already = S.sel[S.screen + ':' + pid] === hit && S.focus === pid;
      S.focus = pid; S.src = pid; S.sel[S.screen + ':' + pid] = hit; S.idx[S.screen + ':' + pid] = i;
      if (S.screen === 'replay' && pane.items[i].row) S.replaySel = pane.items[i].idx;
      if (already) open(pane.items[i]);
      changed();
    }
  }

  // ---------- the frame ----------
  function layoutOf(cols, rows) {
    const wide = cols >= 110, cl = Math.floor((cols - 3) / 2), cr = cols - 3 - cl;
    return { cols, rows, wide, cl, cr, tier: cols < 60 ? '40' : cols < 110 ? '80' : cols < 150 ? '120' : '160', bodyH: Math.max(3, rows - 7) };
  }
  function build(L) {
    const o = {
      ascii: prefs.ascii, wide: L.wide, cols: L.cols, rows: L.rows, tier: L.tier, look: LOOKS.find((x) => x.id === prefs.look), linear: prefs.linear, reduced: opts.reduced ? opts.reduced() : false,
      mission: S.screen === 'replay' ? S.replayMission : S.mission, replaySel: S.replaySel, tab: S.tab, section: S.section, breath: S.breath
    };
    const single = ['control', 'decision'].includes(S.screen);
    o.w1 = L.wide && !single ? L.cl - 2 : L.cols - 2; o.wd = L.wide && !single ? L.cr - 2 : L.cols - 2; o.wm = o.wd; o.wf = o.w1;
    o.mapMax = Math.max(8, L.bodyH - 8);
    o.sel = S.sel['now:map'] || null;
    if (S.screen === 'decision') {
      const a = sim.state.approvals[S.approval], p = decisionPane(sim, a, L.cols - 2, prefs.ascii);
      return { o, scr: { title: 'Approval', panes: { main: p }, order: ['main'], focus: ['main'], lead: 'main', wide: null } };
    }
    const scr = SCREENS[S.screen](sim, o);
    if (S.screen === 'now') { scr.order = ['map', 'list', 'feed']; scr.wide = { left: ['list', 'feed'], right: ['map', 'detail'] }; scr.focus = ['list', 'map']; }
    else if (S.screen === 'replay') { scr.order = ['list', 'detail']; scr.wide = { left: ['list'], right: ['detail'] }; }
    else if (S.screen === 'work' || S.screen === 'attention' || S.screen === 'world') { scr.order = ['list']; scr.wide = { left: ['list'], right: ['detail'] }; }
    else if (S.screen === 'mission') { scr.order = ['main']; scr.wide = { left: ['main'], right: ['side'] }; }
    else { scr.order = ['main']; scr.wide = null; }
    return { o, scr };
  }
  function frame(size) {
    const cols = Math.max(30, size.cols), rows = Math.max(12, size.rows), L = layoutOf(cols, rows), g = glyphs(prefs.ascii);
    S.cols = cols; S.rows = rows;
    const { o, scr } = build(L), P = scr.panes;
    // selections: by key first, then by index, so a list that changes under the cursor keeps it on the same thing
    Object.keys(P).forEach((id) => {
      const pane = P[id]; if (!pane.items.length) { pane.cur = 0; return; }
      const k = S.screen + ':' + id, at = S.sel[k] ? pane.items.findIndex((it) => it.key === S.sel[k]) : -1;
      const want = at >= 0 ? at : S.idx[k] == null ? (S.screen === 'replay' ? pane.items.length - 1 : 0) : S.idx[k];
      pane.cur = Math.max(0, Math.min(pane.items.length - 1, want)); S.sel[k] = pane.items[pane.cur].key; S.idx[k] = pane.cur;
    });
    const wideDetail = L.wide && scr.wide && scr.wide.right.includes('detail') && !P.detail;
    const itemPanes = scr.focus.filter((id) => P[id] && P[id].items.length);
    const focusOrder = scr.focus.concat(L.wide && scr.wide && scr.wide.right.includes('detail') || P.detail ? ['detail'] : []);
    if (!focusOrder.includes(S.focus)) S.focus = scr.lead;
    if (S.focus !== 'detail' && itemPanes.includes(S.focus)) S.src = S.focus;
    const srcPane = P[itemPanes.includes(S.src) ? S.src : scr.lead], item = srcPane && srcPane.items[srcPane.cur];
    if (wideDetail) { P.detail = summaryPane(sim, item, L.cr - 2, prefs.ascii); }
    // columns of lines
    const colsDef = L.wide && scr.wide ? [{ ids: scr.wide.left, w: L.cl }, { ids: scr.wide.right, w: L.cr }] : [{ ids: scr.order.filter((id) => P[id]), w: L.cols }];
    const built = colsDef.map((c, ci) => {
      const lines = []; let anchor = null, anchorEnd = 0;
      c.ids.filter((id) => P[id]).forEach((id, pi) => {
        const pane = P[id]; if (pi) lines.push({ s: [], pane: id });
        pane.offset = lines.length;
        const cur = pane.items[pane.cur || 0];
        pane.lines.forEach((l, i) => lines.push(Object.assign({}, l, { pane: id, sel: !!cur && l.it === pane.cur, foc: !!cur && l.it === pane.cur && S.focus === id, first: !!cur && i === cur.line })));
        if (cur) {
          let e = cur.line; while (pane.lines[e + 1] && pane.lines[e + 1].it === pane.cur) e++;
          if (S.focus === id || anchor == null) { anchor = pane.offset + cur.line; anchorEnd = pane.offset + e; }
        } else if (S.focus === id) { S.dscroll = Math.min(S.dscroll || 0, Math.max(0, pane.lines.length - 1)); anchor = pane.offset + S.dscroll; anchorEnd = anchor; }
      });
      return { lines, anchor: anchor == null ? 0 : anchor, anchorEnd, w: c.w, ci };
    });
    // windowing: keep the selection on screen, move as little as possible
    built.forEach((c) => {
      const key = S.screen + ':' + c.ci + ':' + L.cols + 'x' + L.rows;
      let top = S.top[key] || 0; const h = L.bodyH;
      if (c.anchor < top) top = Math.max(0, c.anchor - 2);
      if (c.anchorEnd >= top + h) top = c.anchorEnd - h + 1;
      top = Math.max(0, Math.min(top, Math.max(0, c.lines.length - h)));
      S.top[key] = top; c.top = top; c.more = c.lines.length > top + h;
    });
    // the marker column, the band of the selected thing, and the hit of every cell of an item
    const pre = (l, w) => {
      const key = l.it != null ? P[l.pane].items[l.it].key : null, mk = !l.first ? seg(' ') : l.foc ? seg(g.arrow, 'b') : seg(g.arrow, 'dim');
      const band = l.foc ? ' sel' : '';
      return clip(pad([mk, seg(' ')].concat(l.s), w), w, g.ell).map((x) => [x[0], (x[1] + band).trim(), x[2] || key, x[3]]);
    };
    const out = [];
    for (let r = 0; r < L.bodyH; r++) {
      const cells = built.map((c) => { const l = c.lines[c.top + r]; return l ? pre(l, c.w) : pad([], c.w); });
      const s = built.length === 2 ? cells[0].concat([seg(' '), seg(boxChar(12, prefs.ascii), 'ln'), seg(' ')], cells[1]) : cells[0];
      const first = built[0].lines[built[0].top + r];
      out.push({ s, h: first && first.h ? 2 : 0, deco: !!(first && first.deco) });
    }
    // header
    const st = sim.state, att = sim.counts(), verifying = Object.values(st.missions).filter((m) => m.state === 'VERIFYING').length;
    const clock = clockLabel(st.clock) + ' ' + (st.playing ? 'x' + st.speed : 'paused');
    const head = [
      { s: lr([seg('ARCHEUS', 'b'), seg('  '), seg(g.tag + ' SIMULATED', 'att b', null, 'SIMULATED'), seg(' ' + g.dot + ' no Core connected', 'dim')], [seg(clock, 'dim')], cols, g.ell, true), k: 'head' },
      { s: navLine(L), k: 'nav' },
      { s: lr(stateLine(att, verifying, g), [seg([prefs.look === 'app' ? '' : LOOKS.find((x) => x.id === prefs.look).label, prefs.ascii ? 'ASCII' : '', opts.reduced && opts.reduced() ? 'Quiet' : ''].filter(Boolean).join(' ' + g.dot + ' '), 'dim')], cols, g.ell, true), k: 'state' },
      { rule: true, s: [seg(boxChar(3, prefs.ascii).repeat(cols), 'ln')] }
    ];
    // footer: the actions of the selected thing, then the keys or the last answer
    const acts = actions(item).concat(estopAct());
    const actLine = acts.length ? acts.reduce((a, x, i) => a.concat([seg(i ? '  ' : ''), seg('[' + x.key + '] ' + x.label, 'b', 'act:' + x.key)]), []) : [seg('')];
    const h = HINT[lang()] || HINT.en;
    const mv = prefs.ascii ? 'Up/Dn' : '↑↓', en = prefs.ascii ? 'Enter' : '⏎';
    const hint = [mv + ' ' + h.move, en + ' ' + h.open, (S.screen === 'mission' || S.screen === 'control' ? 'Tab ' + h.tab : 'Tab ' + h.pane), '? ' + h.help, ': ' + h.cmd, 'q ' + h.back].join('  ');
    const more = built.some((c) => c.more);
    const foot = [
      { rule: true, s: [seg(boxChar(3, prefs.ascii).repeat(cols), 'ln')] },
      { s: clip(actLine, cols, g.ell), k: 'acts' },
      { s: S.status ? [seg(S.status.text, S.status.err ? 'blk' : 'b')] : lr([seg(hint, 'dim')], more ? [seg(g.down + ' ' + h.more, 'dim')] : [], cols, g.ell), k: 'keys', status: !!S.status }
    ];
    let lines = head.concat(out, foot.map((l) => Object.assign(l, { s: clip(l.s, cols, g.ell) })));
    head.forEach((l) => { l.s = clip(l.s, cols, g.ell); });
    lines = overlay(lines, L, g, P, item);
    if (prefs.ascii) lines.forEach((l) => { l.s = l.s.map((x) => [asciify(x[0]), x[1], x[2], x[3]]); });
    last = { panes: P, item, focusOrder, bodyH: L.bodyH }; dirty = false;
    const live = S.status ? S.status.text : (item ? speech(P[itemPanes.includes(S.src) ? S.src : scr.lead].lines.filter((l) => l.it === srcPane.cur).flatMap((l) => l.s).map((x) => x)) : scr.title);
    return { cols, rows, tier: L.tier, wide: L.wide, lines, title: scr.title, screen: S.screen, focus: S.focus, look: prefs.look, ascii: prefs.ascii, linear: prefs.linear, mode: S.mode ? S.mode.kind : null, live: scr.title + '. ' + live, sentence: scr.sentence, bodyH: L.bodyH, panes: P };
  }
  const estopAct = () => { const e = estop(); return e && S.screen !== 'decision' ? [e] : []; };

  function navLine(L) {
    const g = glyphs(prefs.ascii), n = sim.attention().filter((a) => a.group === 'Decide' || a.group === 'Review').length, it = lang() === 'it', cur = S.screen === 'mission' || S.screen === 'decision' ? (S.stack.length ? S.stack[0].screen : 'now') : S.screen;
    const label = (x) => (it ? x[3] : x[2]);
    const full = NAV.reduce((a, x, i) => a.concat([seg(i ? '  ' : ''), seg((x[1] === cur ? '[' + x[0] + ' ' + label(x) + ']' : x[0] + ' ' + label(x)) + (x[1] === 'attention' && n ? ' (' + n + ')' : ''), x[1] === cur ? 'b' : x[1] === 'attention' && n ? 'att' : 't2', 'nav:' + x[1])]), []);
    if (len(full) <= L.cols) return full;
    return NAV.reduce((a, x, i) => a.concat([seg(i ? ' ' : ''), seg(x[1] === cur ? '[' + x[0] + ' ' + label(x) + ']' : x[0] + (x[1] === 'attention' && n ? '(' + n + ')' : ''), x[1] === cur ? 'b' : x[1] === 'attention' && n ? 'att' : 't2', 'nav:' + x[1])]), []);
  }
  function stateLine(c, verifying, g) {
    const parts = sim.sentence().replace(/\.$/, '').split(' · '), cls = (t) => (/need/.test(t) ? 'att b' : /running/.test(t) ? 'act' : /stopped/.test(t) ? 'blk' : 'dim');
    if (verifying) parts.push(verifying + ' verifying');
    return parts.reduce((a, t, i) => a.concat([seg(i ? ' ' + g.dot + ' ' : '', 'dim'), seg(t, /verifying/.test(t) ? 'act' : cls(t))]), []);
  }

  // ---------- overlays: help, places, confirm, reply, command line ----------
  function boxed(title, body, L, g, o2) {
    const w = Math.min(L.cols - 2, o2 && o2.w || 74), inner = w - 4, bc = (m) => boxChar(m, prefs.ascii);
    const rows = [];
    rows.push([seg(bc(10), 'ln ov'), seg(bc(3), 'ln ov'), seg(' ' + title + ' ', 'b ov'), seg(bc(3).repeat(Math.max(0, w - 6 - title.length)), 'ln ov'), seg(bc(9), 'ln ov')]);
    body.forEach((l) => rows.push([seg(bc(12), 'ln ov'), seg(' ', 'ov')].concat(pad(clip(l.s, inner, g.ell), inner).map((x) => [x[0], (x[1] + ' ov').trim(), x[2], x[3]]), [seg(' ', 'ov'), seg(bc(12), 'ln ov')])));
    rows.push([seg(bc(6), 'ln ov'), seg(bc(3).repeat(w - 2), 'ln ov'), seg(bc(5), 'ln ov')]);
    return { rows, w };
  }
  function overlay(lines, L, g, P, item) {
    const m = S.mode; if (!m) return lines;
    let body, title, anchor = 'center';
    const T = (t, c) => ({ s: [seg(t, c || '')] });
    if (m.kind === 'help') { title = lang() === 'it' ? 'Tasti e aiuto' : 'Keys and help'; body = helpLines(Math.min(L.cols - 2, 74) - 4, lang(), prefs.ascii); }
    else if (m.kind === 'places') { title = lang() === 'it' ? 'Vai a' : 'Go to'; body = PLACES.map(([k, id, en, it]) => ({ s: [seg(k, 'b'), seg('  ' + (lang() === 'it' ? it : en))] })).concat([T(''), T(lang() === 'it' ? 'Premi la lettera; Esc annulla.' : 'Press the letter; Esc cancels.', 'dim')]); }
    else if (m.kind === 'confirm') { title = m.act.label; const w = Math.min(L.cols - 2, 74) - 4; body = wrap(m.act.confirm, w).map((l) => T(l)).concat([T(''), { s: [seg('[y] Yes', 'b', 'act:y'), seg('   '), seg('[n] No', 'b', 'act:n'), seg('  ' + (lang() === 'it' ? 'Qualsiasi altro tasto annulla.' : 'Any other key cancels.'), 'dim')] }]); }
    else if (m.kind === 'reply') {
      title = lang() === 'it' ? 'Archeus (risposta simulata)' : 'Archeus (simulated reply)'; const w = Math.min(L.cols - 2, 74) - 4, c = m.msg.card;
      body = wrap(m.msg.text, w).map((l) => T(l)); body.push(T(''));
      if (c && c.kind === 'proposal' && c.state === 'open') body.push({ s: [seg('[y] Confirm', 'b', 'act:y'), seg('   '), seg('[n] Dismiss', 'b', 'act:n'), seg('  ' + (c.text || ''), 'dim')] });
      else if (c && c.kind === 'link') body.push({ s: [seg('[Enter] ' + c.text, 'b', 'act:enter')] }); else body.push(T(lang() === 'it' ? 'Qualsiasi tasto chiude.' : 'Any key closes this.', 'dim'));
    } else if (m.kind === 'cmd') {
      const hits = cmdHits(); m.i = Math.max(0, Math.min(m.i || 0, hits.length - 1));
      const room = Math.max(1, L.bodyH - 3), from = Math.max(0, Math.min(m.i - Math.floor(room / 2), hits.length - room)), shown = hits.slice(from, from + room);
      const w = L.cols - 2;
      const rowsC = shown.map((h, i) => ({ s: lr([seg(from + i === m.i ? g.arrow + ' ' : '  ', 'b'), seg(h.label, from + i === m.i ? 'b' : '')], [seg(h.cls ? h.cls : '', 'dim')], w - 4, g.ell) }));
      if (!shown.length) rowsC.push(T(m.buf.startsWith('/') ? 'No such command. /help lists them.' : 'Nothing matches. Enter tells Archeus.', 'dim'));
      body = rowsC; title = lang() === 'it' ? 'Vai a, o scrivi ad Archeus' : 'Go to, or tell Archeus'; anchor = 'bottom';
      const bx = boxed(title, body, L, g, { w: L.cols });
      const start = lines.length - 3 - bx.rows.length;
      const res = lines.slice();
      bx.rows.forEach((r, i) => { res[start + i] = Object.assign({}, res[start + i], { s: r, ov: true }); });
      res[lines.length - 1] = { s: clip([seg(': ', 'b'), seg(m.buf, ''), seg(prefs.ascii ? '_' : '▏', 'b')], L.cols, g.ell), k: 'cmd', ov: true };
      const hintTxt = lang() === 'it' ? (prefs.ascii ? 'Invio esegui  Tab completa  Su/Giu scegli  Esc annulla' : '⏎ esegui  Tab completa  ↑↓ scegli  Esc annulla') : (prefs.ascii ? 'Enter run  Tab complete  Up/Dn choose  Esc cancel' : '⏎ run  Tab complete  ↑↓ choose  Esc cancel');
      res[lines.length - 2] = { s: clip([seg(hintTxt, 'dim')], L.cols, g.ell), k: 'acts' };
      return res;
    }
    const bx = boxed(title, body, L, g), h = bx.rows.length, top = Math.max(4, Math.floor((lines.length - h) / 2)), x0 = Math.floor((L.cols - bx.w) / 2), res = lines.slice();
    void anchor;
    bx.rows.forEach((r, i) => {
      const y = top + i; if (y >= lines.length - 3) return;
      const base = res[y].s;
      res[y] = Object.assign({}, res[y], { s: slice(pad(base, L.cols), 0, x0).concat(r, slice(pad(base, L.cols), x0 + bx.w, L.cols)), ov: true, hit: null, cells: [] });
    });
    return res;
  }

  const routeId = () => (S.screen === 'mission' ? S.mission : S.screen === 'decision' ? S.approval : S.screen === 'control' ? S.section : S.screen === 'now' ? '' : S.screen);
  function route(id) {
    if (id === routeId() || (!id && S.screen === 'now')) return;
    if (!id) return go('now');
    if (id === 'help') { S.mode = { kind: 'help' }; return changed(); }
    if (['now', 'work', 'world', 'attention', 'replay', 'control'].includes(id) || SECTIONS.some((x) => x[0] === id)) return go(id);
    if (sim.state.missions[id]) return push('mission', { mission: id });
    if (sim.state.approvals[id]) return push('decision', { approval: id });
  }
  const api = {
    state: S, routeId, route, prefs, frame, key, click, go, push, back, openHref, actions, selected,
    cmdSet(v) { if (S.mode && S.mode.kind === 'cmd') { S.mode.buf = v; S.mode.i = 0; changed(); } },
    cmdSubmit() { if (S.mode && S.mode.kind === 'cmd') return cmdKey('enter'); return false; },
    openCmd, tell, clearStatus() { S.status = null; },
    setPrefs(p) { Object.assign(prefs, p); changed(); },
    setBreath(b) { if (S.breath !== b) { S.breath = b; changed(); } },
    keys(str) { String(str).split(' ').filter(Boolean).forEach((k) => (NAMED.test(k) ? key(k) : k.split('').forEach((c) => key(c)))); },
    text(size) { return api.frame(size).lines.map((l) => l.s.map((x) => x[0]).join('')); }
  };
  return api;
}
