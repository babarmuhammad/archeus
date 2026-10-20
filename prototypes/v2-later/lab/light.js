/* LE-3 the day's light: what did Archeus actually touch today? NOT product code.
 *
 *   ?r=quiet   the current quiet state: the verdict sentence and nothing else (V1 / V2 today)
 *   ?r=lanes   R1 (LR §18): a fixed 06:00–24:00 axis, one lane per project touched, one line per
 *              mission from its first to its last recorded event, ended by the PR-5 figure
 *              grammar (tied off / cut / wall / open / needs you); a tick per checkpoint
 *   ?r=ledger  R2: the same record as type — per project, the missions and what became of
 *              them, with the checkpoint file counts; no axis at all
 *   ?day=yesterday  the same scale on a quiet day (LV-14: a quiet day must look quiet)
 *   ?corpus=heavy   40 missions over 6 projects (the density stress)
 * Every drawn element carries data-src naming the event seqs or mission it came from; the
 * probe checks that nothing is drawn without one. Static SVG: no animation, no timer.
 */
(function () {
  'use strict';
  /*<shared>*/
  const Q = new URLSearchParams(location.search);
  const FX = window.FX;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const clock = (m) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
  /** Reduce the event log to one record per mission: span, outcome, checkpoints. This is the
   * read Core does not serve today (LQ-8): it needs /v1/events filtered by local day. */
  function day(events, missions, now) {
    const by = new Map();
    for (const e of events) {
      const d = by.get(e.mission_id) || { id: e.mission_id, seqs: [], t0: e.at, t1: e.at, cps: [], files: 0 };
      d.seqs.push(e.seq); d.t0 = Math.min(d.t0, e.at); d.t1 = Math.max(d.t1, e.at);
      if (e.kind === 'checkpoint.created') { d.cps.push([e.at, e.seq, e.files]); d.files += e.files; }
      by.set(e.mission_id, d);
    }
    const OUT = { DONE: 'done', FAILED: 'failed', BLOCKED: 'blocked', EXECUTING: 'active', VERIFYING: 'verifying', REVIEWING: 'reviewing', APPROVAL_REQUIRED: 'needs_you', PLANNING: 'planning' };
    const res = [];
    for (const m of missions) {
      const d = by.get(m.id);
      if (!d) continue;
      d.m = m; d.out = OUT[m.state];
      if (['active', 'verifying', 'planning'].includes(d.out)) d.t1 = now; // still open: the line reaches now
      res.push(d);
    }
    return res;
  }
  const WORDS = { done: 'verified', failed: 'failed', blocked: 'blocked', active: 'running', verifying: 'verifying', reviewing: 'waiting for your review', needs_you: 'waiting for you', planning: 'planning' };
  /*</shared>*/

  /*<lanes>*/
  /** R1. One scale across days: the axis is fixed, so a quiet day is visibly a quiet day. */
  function lanes(rec, projects, now, W) {
    const T0 = 6 * 60, T1 = 24 * 60, padL = 92, padR = 14, laneH = 26, top = 18;
    const x = (t) => padL + ((Math.max(T0, Math.min(T1, t)) - T0) / (T1 - T0)) * (W - padL - padR);
    const pids = [...new Set(rec.map((d) => d.m.project_id))];
    const H = top + pids.length * laneH * 1 + rec.length * 0 + 22 + pids.reduce((a, p) => a + Math.max(0, rec.filter((d) => d.m.project_id === p).length - 1) * 9, 0);
    let y = top, svg = '';
    for (let h = 6; h <= 24; h += 3) svg += `<line class="tick" x1="${x(h * 60)}" x2="${x(h * 60)}" y1="${top - 6}" y2="${H - 18}" data-src="axis"/><text class="hr" x="${x(h * 60)}" y="${H - 4}" text-anchor="middle" data-src="axis">${String(h % 24).padStart(2, '0')}</text>`;
    if (now != null) svg += `<line class="now" x1="${x(now)}" x2="${x(now)}" y1="${top - 8}" y2="${H - 18}" data-src="clock"/>`;
    for (const p of pids) {
      const ds = rec.filter((d) => d.m.project_id === p).sort((a, b) => a.t0 - b.t0);
      svg += `<text class="lane" x="0" y="${y + 4}" data-src="project:${p}">${esc(projects[p].name)}</text>`;
      ds.forEach((d, i) => {
        const yy = y + i * 9, a = x(d.t0), b = Math.max(x(d.t1), a + 3);
        const src = `mission:${d.m.id} seq:${d.seqs.join(',')}`;
        svg += `<a href="ia.html?v=c#m/${d.m.id}" data-src="${src}" aria-label="${esc(d.m.title)}: ${WORDS[d.out]}, ${clock(d.t0)}–${clock(d.t1)}"><title>${esc(d.m.title)} · ${WORDS[d.out]} · ${clock(d.t0)}–${clock(d.t1)}</title>`;
        svg += `<line class="ml r-${d.out}" x1="${a}" x2="${b}" y1="${yy}" y2="${yy}" data-src="${src}"/>`;
        for (const c of d.cps) svg += `<line class="cp" x1="${x(c[0])}" x2="${x(c[0])}" y1="${yy - 3}" y2="${yy + 3}" data-src="seq:${c[1]}"/>`;
        svg += end(d.out, b, yy, src);
        svg += `<rect class="hit" x="${a - 2}" y="${yy - 5}" width="${b - a + 12}" height="10" data-src="${src}"/></a>`;
      });
      y += laneH + Math.max(0, ds.length - 1) * 9;
    }
    return `<svg class="daylight lanes" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="group" aria-label="Today, 06:00 to 24:00, one lane per project">${svg}</svg>`;
  }
  /** The end of a mission's line is its outcome, by SHAPE (PR-5 C grammar), never hue alone. */
  function end(out, x, y, src) {
    const s = `data-src="${src}"`;
    if (out === 'done') return `<path class="e r-done" d="M${x - 1} ${y}l3 3l6-7" ${s}/>`;                    // tied off
    if (out === 'failed') return `<path class="e r-failed" d="M${x + 1} ${y - 4}l6 8M${x + 7} ${y - 4}l-6 8" ${s}/>`; // cut
    if (out === 'blocked') return `<line class="e r-blocked" x1="${x + 2}" x2="${x + 2}" y1="${y - 5}" y2="${y + 5}" ${s}/>`; // wall
    if (out === 'needs_you') return `<path class="e r-needs_you f" d="M${x + 4} ${y - 4}l4 4l-4 4l-4-4z" ${s}/>`;
    if (out === 'reviewing') return `<circle class="e r-reviewing" cx="${x + 4}" cy="${y}" r="3.5" ${s}/>`;
    return `<circle class="e r-${out} f" cx="${x + 2}" cy="${y}" r="2.6" ${s}/>`;                                // open, still running
  }
  /*</lanes>*/

  /*<ledger>*/
  /** R2. The same record as type: what was touched, by project, and what became of it. */
  function ledger(rec, projects) {
    const pids = [...new Set(rec.map((d) => d.m.project_id))];
    return `<div class="daylight ledger">${pids.map((p) => {
      const ds = rec.filter((d) => d.m.project_id === p);
      const files = ds.reduce((a, d) => a + d.files, 0), cps = ds.reduce((a, d) => a + d.cps.length, 0);
      return `<section data-src="project:${p}"><h3>${esc(projects[p].name)} <span class="t3 cap">${ds.length} mission${ds.length === 1 ? '' : 's'}${cps ? ` · ${files} files in ${cps} checkpoint${cps === 1 ? '' : 's'}` : ''}</span></h3>
        <ul>${ds.map((d) => `<li data-src="mission:${d.m.id} seq:${d.seqs.join(',')}"><span class="figslot r-${d.out}">${window.FIG.C(d.out, 16)}</span><a href="ia.html?v=c#m/${d.m.id}">${esc(d.m.title)}</a> <span class="t2">${WORDS[d.out]}</span> <span class="num t3">${clock(d.t0)}–${clock(d.t1)}</span></li>`).join('')}</ul></section>`;
    }).join('')}</div>`;
  }
  /*</ledger>*/

  // ---------------------------------------------------------------------- the page
  const heavy = () => {
    const P = {}, M = [], E = [];
    const names = ['archeus', 'website', 'invoicing', 'ledger', 'mobile', 'infra'];
    names.forEach((n, i) => { P['h' + i] = { name: n, repos: [] }; });
    const outs = ['DONE', 'DONE', 'DONE', 'FAILED', 'BLOCKED', 'EXECUTING', 'DONE', 'APPROVAL_REQUIRED'];
    let seq = 0;
    for (let i = 0; i < 40; i++) {
      const t0 = 6 * 60 + 20 + ((i * 137) % (8 * 60)), len = 15 + ((i * 53) % 120);
      const m = { id: 'h-' + i, title: 'Mission ' + (i + 1), project_id: 'h' + (i % 6), state: outs[i % outs.length] };
      M.push(m);
      E.push({ seq: ++seq, mission_id: m.id, at: t0, kind: 'mission.created' });
      E.push({ seq: ++seq, mission_id: m.id, at: t0 + Math.round(len / 2), kind: 'checkpoint.created', files: 1 + (i % 9) });
      E.push({ seq: ++seq, mission_id: m.id, at: Math.min(t0 + len, FX.NOW), kind: 'execution.ended' });
    }
    return { P, M, E };
  };
  let projects = FX.projects, missions = FX.missions, events = FX.events, now = FX.NOW;
  if (Q.get('corpus') === 'heavy') { const hv = heavy(); projects = hv.P; missions = hv.M; events = hv.E; }
  if (Q.get('day') === 'yesterday') {
    missions = FX.yesterday.map(([id, p, , , o]) => ({ id, title: id === 'm-y1' ? 'Bump the CI cache key' : 'Fix a typo on the pricing page', project_id: p, state: o === 'done' ? 'DONE' : 'FAILED' }));
    events = FX.yesterday.flatMap(([id, , a, b], i) => [{ seq: 900 + i * 2, mission_id: id, at: a, kind: 'mission.created' }, { seq: 901 + i * 2, mission_id: id, at: b, kind: 'mission.done' }]);
    now = null;
  }
  const r = Q.get('r') || 'lanes';
  const t = performance.now();
  const rec = day(events, missions, now);
  const W = Math.min(innerWidth - 32, 760);
  const verified = rec.filter((d) => d.out === 'done').length;
  const head = rec.length ? `${verified} verified today` + (rec.length - verified ? ` · ${rec.length - verified} other${rec.length - verified === 1 ? '' : 's'} touched` : '') : 'Nothing touched today.';
  const body = r === 'quiet' ? '' : r === 'ledger' ? ledger(rec, projects) : lanes(rec, projects, now, W);
  const projN = new Set(rec.map((d) => d.m.project_id)).size;
  document.getElementById('host').innerHTML = `<h1 class="verdict">${r === 'quiet' ? (rec.some((d) => d.out === 'active') ? 'Archeus is working.' : 'All clear.') : 'All clear.'}</h1>
    <p class="t2">${head}${r !== 'quiet' && projN ? ` in ${projN} project${projN === 1 ? '' : 's'}` : ''}.</p>${body}
    ${r === 'lanes' ? `<details class="mirror"><summary>Today as a list</summary>${ledger(rec, projects)}</details>` : ''}`;
  window.__render_ms = +(performance.now() - t).toFixed(2);
  window.__rec = rec.map((d) => ({ id: d.id, out: d.out, seqs: d.seqs }));
})();
