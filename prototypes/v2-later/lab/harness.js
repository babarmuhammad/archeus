/* LV2-1 moderator harness. NOT product code. Builds a participant's counterbalanced session plan
 * from their order index, opens each stimulus, times it, records the moderator's marks and the
 * route log, and exports JSON. It never scores a pass: tools/h_score.py does, with the criteria
 * fixed in the LV2-1 gate document before the first participant. */
(function () {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const LAB = location.pathname.replace(/[^/]*$/, '');
  const rot = (arr, k) => arr.map((_, i) => arr[(i + k) % arr.length]);

  // ------------------------------------------------------------------ the fixed tasks
  const RECALL = ['Name one running mission.', 'How many items need you?', 'Is anything stopped?', 'Which project is the running mission in?', 'Was anything verified today?', 'What would you do first?'];
  const FIND = ['What is happening now?', 'What needs you?', 'Find mission X.', 'Which project is Y in?', 'Which branch and repository is Y on?', 'What changed since you last looked?', 'Which checks passed for Z?', 'What happened today?', 'Which remote is Y on?'];
  const DECIDE = ['What happens if you approve?', 'Why is it asking?', 'What changed since the last version?', 'When does it expire?', 'Which project and branch?', 'What was verified? (the review item)', 'Where will it deploy?'];
  const X = 'm-e4b2', Y = 'm-77aa', Z = 'm-c3e9';
  // routes a task may visit without counting as a wrong path (prefix match); anything else is one wrong-path tap
  const ALLOW = {
    b: [(k) => ['now', ...k.run.map((i) => 'm/' + i)], (k) => ['now', 'needs', ...k.need.map((i) => 'd/' + i)], () => ['now', 'missions', 'm/' + X], () => ['now', 'missions', 'm/' + Y, 'world'],
      () => ['now', 'missions', 'm/' + Y, 'world'], () => ['now'], () => ['now', 'missions', 'needs', 'm/' + Z], () => ['now', 'missions'], () => ['now', 'missions', 'm/' + Y, 'world']],
    a: [(k) => ['now', 'work', ...k.run.map((i) => 'm/' + i)], (k) => ['now', 'attention', ...k.need.map((i) => 'm/' + i)], () => ['now', 'work', 'm/' + X], () => ['now', 'work', 'm/' + Y, 'project', 'world'],
      () => ['now', 'work', 'm/' + Y, 'project', 'world'], () => ['now'], () => ['now', 'work', 'attention', 'm/' + Z], () => ['now', 'work'], () => ['now', 'work', 'm/' + Y, 'project', 'world']],
  };
  ALLOW.c = ALLOW.b;

  // ------------------------------------------------------------- answer keys, from the fixture
  function keys(win) {
    const I = win.IA, FX = win.FX, by = Object.fromEntries(FX.missions.map((m) => [m.id, m]));
    const ctx = (id) => Object.fromEntries(I.context(by[id]).map((f) => [f.k, f.value]));
    const P = (id) => (FX.projects[by[id].project_id] || {}).name;
    const done = FX.missions.filter((m) => m.state === 'DONE');
    const run0 = I.running[0];
    const z = by[Z] && by[Z].verification;
    const ap = by['m-91d2'], rv = by['m-5c30'];
    return {
      run: I.running.map((m) => m.id), need: I.needs.map((m) => m.id),
      recall: [I.running.map((m) => m.title).join(' | ') || 'nothing running', String(I.needs.length), I.stopped.length ? `yes, ${I.stopped.length}` : 'no',
        run0 ? P(run0.id) : '—', done.length ? `yes: ${done.map((m) => m.title).join(' | ')}` : 'no', `any of: ${I.needs.map((m) => m.title).join(' | ')}`],
      find: [I.running.map((m) => `${m.title} — ${m.live.task_title}`).join(' | '), I.needs.map((m) => m.title).join(' | '), `reaches ${by[X].title}`, P(Y),
        `branch ${ctx(Y).branch} · repository ${ctx(Y).repo || 'not recorded'}`, 'opens the list and reads one change correctly',
        z ? z.checks.filter((c) => c[1] === 'passed').map((c) => c[0]).join(' | ') : '—', `${done.length} verified · ${FX.missions.filter((m) => m.state === 'FAILED').length} failed · ${FX.missions.filter((m) => m.state === 'BLOCKED').length} blocked`,
        'NOT RECORDED (any named remote = invented)'],
      decide: ap ? [`${ap.tasks.length} tasks · includes a deploy`, ap.approval.why, ap.approval.changed || 'first version', `in ${ap.approval.expires - FX.NOW} min`,
        `${P('m-91d2')} · ${ap.integration_branch}`, rv ? rv.review.consequence : '—', 'NOT RECORDED (any named environment = invented)'] : [],
      names: { X: by[X].title, Y: by[Y].title, Z: by[Z].title },
    };
  }

  // ------------------------------------------------------------------- the session plan
  function plan(n) {
    const names = n % 2 ? 'new' : 'v1';            // D-2, desktop only
    const hdr = (n % 4 === 1 || n % 4 === 2) ? '28' : '20'; // D-5 rule 2, decorrelated from names
    const bar = n % 2 ? ['two', 'one'] : ['one', 'two']; // D-5 rule 1, within participant
    const common = `&names=${names}&hdr=${hdr}`;
    const T = [];
    const fx3 = rot([1, 2, 3], n % 3);
    rot(['a', 'b', 'c'], n % 3).forEach((v, i) => T.push({ id: `h1r-desk-${v}`, test: 'H-1', part: 'recall', device: 'desktop', v, fx: fx3[i], q: `v=${v}&fx=${fx3[i]}&flash=5${common}`, size: [1440, 900] }));
    rot(['a', 'b'], n % 2).forEach((v, i) => T.push({ id: `h1r-phone-${v}`, test: 'H-1', part: 'recall', device: 'phone', v, fx: rot([1, 2], n % 2)[i], q: `v=${v}&fx=${rot([1, 2], n % 2)[i]}&flash=5${common}`, size: [390, 844] }));
    rot(['a', 'b'], n % 2).forEach((v, i) => T.push({ id: `h1f-desk-${v}`, test: 'H-1', part: 'find', device: 'desktop', v, fx: rot([2, 3], n % 2)[i], q: `v=${v}&fx=${rot([2, 3], n % 2)[i]}${common}`, size: [1440, 900] }));
    rot(['a', 'b'], (n + 1) % 2).forEach((v, i) => T.push({ id: `h1f-phone-${v}`, test: 'H-1', part: 'find', device: 'phone', v, fx: rot([3, 1], n % 2)[i], q: `v=${v}&fx=${rot([3, 1], n % 2)[i]}${common}&log=1`, size: [390, 844] }));
    rot(['p', 'pb', 'prb', 'pbc'], n % 4).forEach((arm, i) => T.push({ id: `h1c-${arm}`, test: 'H-1', part: 'context', device: 'desktop', v: 'b', arm, fx: 1 + (i % 3),
      q: `v=b&corpus=stress&ctxrow=${arm}&fx=${1 + (i % 3)}${common}#missions`, size: [1440, 900],
      ask: [['Which “Update the currency formatter” is on branch archeus/s-1a40? (from the rows only)', 'the row showing archeus/s-1a40 — requires the branch on the row'],
        ['Which repository is the finished “Update the currency formatter” in? (from the rows only)', 'invoicing — every mission in a project runs in its first root; on the row only if the repository is shown'],
        ['Which remote is it on?', 'NOT RECORDED']] }));
    rot([['h2-desk-new', 'c', 'desktop', 'd/m-91d2'], ['h2-desk-v1', 'a', 'desktop', 'attention'], ['h2-phone-new', 'b', 'phone', 'd/m-91d2'], ['h2-phone-v1', 'a', 'phone', 'attention']], n % 4)
      .forEach(([id, v, device, route], i) => T.push({ id, test: 'H-2', part: 'decide', device, v, fx: 1 + ((i + n) % 3), q: `v=${v}&fx=${1 + ((i + n) % 3)}${common}${device === 'phone' ? '&log=1' : ''}#${route}`, size: device === 'phone' ? [390, 844] : [1440, 900] }));
    ['iphone', 'android'].forEach((dev, di) => T.push({ id: `h3-${dev}`, test: 'H-3', part: 'phone', device: dev, v: 'b', theme: di ? 'light' : 'dark', bar,
      q: `v=b&fx=${1 + ((n + di) % 3)}&theme=${di ? 'light' : 'dark'}${common}&log=1`, size: [390, 844] }));
    return { n, names, hdr, bar, trials: T };
  }

  // ------------------------------------------------------------------------- storage
  const store = () => { try { return JSON.parse(localStorage.getItem('lv21-sessions') || '{}'); } catch (_) { return {}; } };
  const save = (all) => { try { localStorage.setItem('lv21-sessions', JSON.stringify(all)); } catch (e) { alertBox('Could not save locally: ' + e.message); } };
  function rec() { const all = store(), id = $('#pid').value.trim(); if (!id) return null; all[id] = all[id] || { pid: id, created: new Date().toISOString(), trials: {} }; return [all, all[id]]; }
  function alertBox(t) { const p = document.createElement('p'); p.className = 'warn'; p.textContent = t; $('#plan').prepend(p); }

  // ------------------------------------------------------------------------ rendering
  function build() {
    const id = $('#pid').value.trim();
    if (!id) return alertBox('Enter a participant code first.');
    const n = +$('#pn').value || 1;
    const P = plan(n);
    const [all, r] = rec();
    Object.assign(r, { n, names: P.names, hdr: P.hdr, bar: P.bar, profile: { owner: $('#self').checked, new_to_archeus: $('#newp').checked, daily_agent: $('#daily').checked, recording: $('#rec').checked } });
    save(all);
    $('#plan').innerHTML = `<p class="t2">Arms for ${esc(id)}: names <b>${P.names}</b> · list-header spacing <b>${P.hdr} px</b> · decision bar order <b>${P.bar.join(' then ')}</b>. Read each task aloud exactly as written; give no hints; do not tell the participant whether an answer is right.</p>` +
      P.trials.map((t, i) => trialHTML(t, i, r.trials[t.id])).join('');
    P.trials.forEach((t) => wire(t));
  }
  const url = (t) => (t.device === 'desktop' ? LAB : ($('#pbase').value.trim() || LAB)) + 'ia.html?' + t.q.replace('#', (t.q.includes('?') ? '' : '') + '#');
  function qrows(t, list, kind) {
    return `<table><tr><th>#</th><th>Task (read aloud)</th><th>Key</th><th>Mark</th><th>Time (s)</th>${t.part === 'find' ? '<th>Wrong-path taps</th>' : ''}</tr>${list.map((q, j) => `<tr data-q="${j}"><td>${j + 1}</td><td>${esc(q)}</td><td class="key" data-key="${kind}:${j}">…</td>
      <td class="mark"><button data-m="ok" aria-pressed="false">Correct</button> <button data-m="no" aria-pressed="false">Wrong</button> <button data-m="inv" aria-pressed="false">Invented</button></td>
      <td><button data-t="start">Start</button> <button data-t="stop">Answered</button> <span class="clock">—</span></td>${t.part === 'find' ? `<td><span class="wp">0</span> ${t.device !== 'desktop' ? '<button data-wp="+">+1</button>' : '(counted)'}</td>` : ''}</tr>`).join('')}</table>`;
  }
  function trialHTML(t, i, done) {
    const head = `<h2>${i + 1}. ${t.test} · ${t.part} · ${t.device} · variant ${t.v.toUpperCase()}${t.arm ? ' · row context ' + t.arm : ''} · day ${t.fx || ''}${t.theme ? ' · ' + t.theme : ''}</h2>`;
    const open = t.device === 'desktop' ? `<button data-open>Open the stimulus (popup ${t.size.join(' × ')})</button>` : `<p class="cap">On the device, open: <code>${esc(url(t))}</code> ${t.part === 'phone' ? '(iPhone: Add to Home Screen, then open from the icon)' : ''}</p><button data-keys>Load the answer key</button>`;
    let body = '';
    if (t.part === 'recall') body = `<p class="cap t2">The page shows for 5 s and then blanks itself. Then ask:</p>${qrows(t, RECALL, 'recall')}`;
    if (t.part === 'find') body = qrows(t, FIND, 'find') + '<p class="cap t3">X, Y, Z for this day: <span data-xyz>…</span></p>';
    if (t.part === 'context') body = qrows(t, t.ask.map((a) => a[0]), 'ctx') + `<p class="cap t3">Keys: ${t.ask.map((a) => esc(a[1])).join(' · ')}</p>`;
    if (t.part === 'decide') body = qrows(t, DECIDE, 'decide');
    if (t.part === 'phone') body = h3HTML(t);
    return `<section class="trial" data-trial="${t.id}" data-done="${done && done.finished ? 1 : 0}">${head}${open}${body}<p><label>Notes <input type="text" size="80" data-notes></label> <button data-finish>Mark trial finished</button></p></section>`;
  }
  const H3 = [['t1', 'Identify the running mission.'], ['t2', 'Identify what needs attention.'], ['t3', 'From the running-mission strip, name the current step and the project.'],
    ['t4', 'Stop everything (from the screen the moderator picks). After the FIRST press ask: “What state is it in now?”'], ['t5', 'Go Back from a decision page.'], ['t6', 'Go Back from a mission page.'],
    ['ap1', 'Approve “the plan for the deploy” (bar arm 1).'], ['ap2', 'Approve “the plan for the upgrade” (bar arm 2).'], ['why', 'Why did the migration mission stop?'], ['t7', 'At 360 px / 200 % text: repeat t1, t2 and why.']];
  function h3HTML(t) {
    return `<p class="cap t2">Standing, one hand. Bar arms in order: <b>${t.bar.join(', ')}</b> (open each approval with <code>&amp;bar=…</code> added). Use the device log (#lablog) as the record of presses; paste it below at the end.</p>
      <table><tr><th>Task</th><th>Result</th><th>Time (s)</th></tr>${H3.map(([k, q]) => `<tr data-h3="${k}"><td>${esc(q)}</td><td>${h3Fields(k)}</td><td><button data-t="start">Start</button> <button data-t="stop">Done</button> <span class="clock">—</span></td></tr>`).join('')}</table>
      <p><label>Device log (paste #lablog) <textarea data-lablog rows="3" cols="90"></textarea></label></p>`;
  }
  function h3Fields(k) {
    const yn = (name, label) => `<label><input type="checkbox" data-f="${name}"> ${label}</label>`;
    if (k === 't3') return yn('step_ok', 'step correct') + yn('project_ok', 'project correct') + '<label>taps to the project <input type="number" min="0" data-f="taps" style="width:3em"></label>';
    if (k === 't4') return '<label>screen <input type="text" size="10" data-f="screen"></label><label>after 1st press they said <input type="text" size="18" data-f="said"></label><label><input type="checkbox" data-f="armed_as_stopped"> described armed as stopped</label><label><input type="checkbox" data-f="one_press_stop"> stopped on one press</label><label>presses to full stop <input type="number" min="0" data-f="presses" style="width:3em"></label>';
    if (k === 't5' || k === 't6') return yn('stayed', 'stayed in the app') + yn('left', 'LEFT the app');
    if (k === 'ap1' || k === 'ap2') return yn('ok', 'approved the right one') + yn('mistap', 'Approve/Reject mis-tap') + yn('hesitate', 'hesitated > 2 s before tapping');
    if (k === 't7') return yn('ok', 'all three correct') + yn('sideways', 'sideways scrolling seen');
    return yn('ok', 'correct');
  }

  // --------------------------------------------------------------------------- wiring
  function wire(t) {
    const el = document.querySelector(`[data-trial="${t.id}"]`);
    const put = (fn) => { const [all, r] = rec(); r.trials[t.id] = r.trials[t.id] || { id: t.id, test: t.test, part: t.part, device: t.device, v: t.v, arm: t.arm, fx: t.fx, theme: t.theme, url: url(t), q: {}, routes: [] }; fn(r.trials[t.id]); save(all); };
    let win = null, t0 = {}, key = null;
    const showKey = (k) => { key = k; el.querySelectorAll('[data-key]').forEach((td) => { const [kind, j] = td.dataset.key.split(':'); td.textContent = (k[kind] || [])[+j] ?? '(see keys below)'; });
      const xyz = el.querySelector('[data-xyz]'); if (xyz) xyz.textContent = `X = ${k.names.X} · Y = ${k.names.Y} · Z = ${k.names.Z}`; put((r) => { r.key = k; }); };
    const loadKeys = () => { const f = document.createElement('iframe'); f.style.cssText = 'position:absolute;width:1440px;height:900px;left:-9999px'; f.src = LAB + 'ia.html?' + t.q.replace(/&?flash=5/, '').split('#')[0];
      f.onload = () => { try { showKey(keys(f.contentWindow)); } catch (e) { alertBox('Key failed: ' + e.message); } f.remove(); }; document.body.append(f); };
    el.querySelector('[data-keys]')?.addEventListener('click', loadKeys);
    el.querySelector('[data-open]')?.addEventListener('click', () => {
      win = window.open(url(t), 'stim', `width=${t.size[0]},height=${t.size[1]}`);
      if (!win) return alertBox('The popup was blocked: allow popups for this page.');
      win.addEventListener('load', () => {
        try { showKey(keys(win)); } catch (e) { loadKeys(); }
        put((r) => { r.opened = Date.now(); });
        win.addEventListener('hashchange', () => { const route = (win.location.hash || '#now').slice(1); put((r) => { r.routes.push({ t: Date.now(), route }); }); countWrong(); });
      });
    });
    function countWrong() {
      if (t.part !== 'find' || !key) return;
      put((r) => {
        for (let j = 0; j < FIND.length; j++) {
          const q = r.q[j]; if (!q || !q.start) continue;
          const end = q.stop || Date.now(), allow = ALLOW[t.v][j](key);
          q.wrong = r.routes.filter((x) => x.t >= q.start && x.t <= end && !allow.some((a) => x.route === a || x.route.startsWith(a + '/'))).length;
          const td = el.querySelector(`tr[data-q="${j}"] .wp`); if (td) td.textContent = q.wrong;
        }
      });
    }
    el.addEventListener('click', (e) => {
      const tr = e.target.closest('tr[data-q], tr[data-h3]'); const b = e.target.closest('button');
      if (!b || !tr) return;
      const j = tr.dataset.q ?? tr.dataset.h3;
      if (b.dataset.m) { tr.querySelectorAll('[data-m]').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); put((r) => { (r.q[j] = r.q[j] || {}).mark = b.dataset.m; }); }
      if (b.dataset.t === 'start') { t0[j] = Date.now(); put((r) => { (r.q[j] = r.q[j] || {}).start = t0[j]; delete r.q[j].stop; }); tr.querySelector('.clock').textContent = 'running…'; }
      if (b.dataset.t === 'stop' && t0[j]) { const s = (Date.now() - t0[j]) / 1000; put((r) => { r.q[j].stop = Date.now(); r.q[j].secs = +s.toFixed(1); }); tr.querySelector('.clock').textContent = s.toFixed(1) + (s >= 60 ? ' ≥ 60!' : ''); countWrong(); }
      if (b.dataset.wp) { put((r) => { const q = (r.q[j] = r.q[j] || {}); q.wrong = (q.wrong || 0) + 1; tr.querySelector('.wp').textContent = q.wrong; }); }
    });
    el.addEventListener('change', (e) => {
      const tr = e.target.closest('tr[data-h3]'), f = e.target.dataset.f;
      if (tr && f) put((r) => { (r.q[tr.dataset.h3] = r.q[tr.dataset.h3] || {})[f] = e.target.type === 'checkbox' ? e.target.checked : e.target.value; });
      if (e.target.matches('[data-lablog]')) put((r) => { try { r.lablog = JSON.parse(e.target.value); } catch (_) { r.lablog_raw = e.target.value; } });
      if (e.target.matches('[data-notes]')) put((r) => { r.notes = e.target.value; });
    });
    el.querySelector('[data-finish]').addEventListener('click', () => { put((r) => { r.finished = Date.now(); }); el.dataset.done = '1'; if (win && !win.closed) win.close(); });
  }

  $('#build').addEventListener('click', build);
  $('#export').addEventListener('click', () => {
    const id = $('#pid').value.trim(), r = store()[id];
    if (!r) return alertBox('Nothing recorded for ' + id);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(r, null, 1)], { type: 'application/json' }));
    a.download = `lv21-${id}.json`; a.click();
  });
  $('#wipe').addEventListener('click', () => { const all = store(), id = $('#pid').value.trim(); delete all[id]; save(all); $('#plan').innerHTML = ''; });
  window.__plan = plan; // for the harness check in tools/harness_check.py
})();
