/* LV2-X.2 — Direction E, refined (?d=e2). Prototype only, never shipped.
 *
 * E as the owner accepted it (reassessment §19), made into one coherent product: every state of
 * the overview, the mission page, the approval, the error, projects, ideas and Control, on the
 * desktop and the phone. E itself (?d=e, d.js) is untouched and stays the accepted evidence.
 *
 * Honesty rules as before: every fact goes through K()/NR() (data.js); research content is
 * marked `sample`; a capability Core lacks is a gap tag naming what it needs. New here:
 *   - safety copy follows P20 as recorded: approve is refused while stopped, reject and changes
 *     still work (authorization.py:711-720); with Core unreachable the page holds no stop
 *     authority and says where the stop is (tray, `archeus estop`; P20 item 15); no device asks a
 *     PIN to resume today, and D10's phone PIN (approved, not built, P20 V2-3) is drawn only with ?pin=d10.
 *   - a move Core has only as a conversation command (cancel a mission, start an idea) is prepared in Tell;
 *     a move Core has no way to ask for (retry a failed mission) is said to be impossible, not drawn.
 * LV2-X.4: the owner's Q12–Q18 decisions; "Not stopped" for the safety line; queued is not "working on";
 * a deadline is amber only within 2 h; the left bar keeps the place a page was opened from.
 */
(function () {
  'use strict';
  const A = window.AX, I = A.icon, K = A.K, NR = A.NR, hm = A.hm, go = A.go, Q = A.Q, FX = window.FX;
  const S = A.S;
  const stopped = A.estop.state === 'stopped', primed = A.estop.state === 'primed';
  const offline = S === 'offline', loading = S === 'loading', resumed = S === 'resumed';
  const CORE_ONLY = Q.get('core') === '1';
  const SHOT = !!Q.get('shot');
  const n = (k, v, src, rule) => K(k, String(v), src, rule);
  const plural = (c, one, many) => (c === 1 ? one : many);
  const T = (m) => K('known', m.title, 'Mission.title');
  const NAVQ = ['id', 'did', 'ask', 'drawer', 'wait', 'pid', 'compose', 'iid', 'research', 'rev', 'f', 'log', 'from', 'tell', 'resume', 'demo', 'sending', 'pin'];
  const to = (patch) => go(Object.assign(Object.fromEntries(NAVQ.map((k) => [k, null])), patch));
  const V = Q.get('v') || 'home';
  const here = () => (V === 'project' ? 'project:' + Q.get('pid') : V === 'idea' ? 'idea:' + Q.get('iid') : V === 'home' ? 'overview' : V === 'mission' ? (Q.get('from') || 'overview') : V);
  const open = (m) => to({ v: 'mission', id: m.id, from: here() });
  const place = (v) => to({ v });
  const projPage = (pid) => to({ v: 'project', pid });
  const tip = (html) => ` title="${String(html).replace(/<[^>]+>/g, '').replace(/"/g, '&quot;')}"`;
  const gap = (gate, what, short) => `<span class="f nr x-gap" data-k="nr" data-src="${A.esc(gate)}" title="${A.esc(what)}: not in Core yet">${A.esc(short)} · ${A.esc(gate)}</span>`;
  const SMP = (text, what) => `<span class="f" data-k="sample" data-src="${A.esc('DR-10 research (sample): ' + what)}">${A.esc(String(text))}</span>`;

  // ── groups (E's order: waiting · blocked or failed · running · today) ──
  const expired = (m) => !!(m.approval && m.approval.expired);
  const nowStop = (m) => m.estop && !m.estop_at;          // stopped by the stop that is engaged now
  const pastStop = (m) => m.estop && !!m.estop_at;        // stopped by a stop that was cleared: still BLOCKED
  // waiting is a pending approval or review, not a mission state: a task approval at dispatch BLOCKS its mission
  // (authorization.py:529-535), so a blocked mission with a pending approval waits for you, it is not in trouble
  const askBlocked = (m) => m.state === 'BLOCKED' && !!m.approval && !m.estop && !expired(m);
  const waiting = A.decisions.concat(A.missions.filter(askBlocked)).filter((m) => !expired(m))
    .sort((a, b) => (a.approval ? a.approval.expires : 1e9) - (b.approval ? b.approval.expires : 1e9));
  const trouble = A.missions.filter((m) => ((m.state === 'BLOCKED' || m.state === 'FAILED') && !nowStop(m) && !askBlocked(m)) || expired(m));
  const halted = A.missions.filter(nowStop);
  const running = A.running, planning = A.starting;
  // X.4 (Q17): EXECUTING with no live execution is queued for an agent, not at work, and the e-stop ends only live
  // executions (executions.py:418-433). "Working on" counts only missions an agent or the checks are on
  const isQueued = (m) => m.state === 'EXECUTING' && !m.live;
  const working = running.filter((m) => !isQueued(m)), queued = running.filter(isQueued);
  // a deadline is news only when it is near: within 2 h, the shortest life Core gives an approval (action)
  const SOON = 120;
  const done = A.done;
  const ended = A.missions.filter((m) => m.state === 'CANCELLED');
  const openOf = (pid) => A.missions.filter((m) => m.project_id === pid && !['DONE', 'CANCELLED'].includes(m.state));
  const IDEAS = FX.ideas || [];

  // ── words and tones (Core's state names; "stopped" belongs to the emergency stop) ──
  const word = (m) => (m.state === 'CANCELLED' ? 'Cancelled' : expired(m) ? 'Approval expired' : nowStop(m) ? 'Stopped' : pastStop(m) ? 'Blocked' : askBlocked(m) ? 'Needs approval' : isQueued(m) ? 'Queued' : A.word(m));
  const toneOf = (m) => (m.state === 'CANCELLED' ? 'ended' : expired(m) ? 'ended' : nowStop(m) ? 'stop' : pastStop(m) ? 'blocked' : askBlocked(m) ? 'attention' : isQueued(m) ? 'ended' : A.tone(m));
  const near = (m) => !!m.approval && !expired(m) && m.approval.expires - A.NOW <= SOON;
  const chip = (m) => `<span class="chip tone-${toneOf(m)}">${K('known', word(m), m.state === 'CANCELLED' ? 'mission.state_changed → CANCELLED' : 'Mission.state')}</span>`;
  const phaseOf = (m) => (m.state === 'CANCELLED' ? m.ended.phase : A.phase(m));

  // ── project identity: a monogram in one of six shapes; colour stays state-only ──
  const SH = ['<circle cx="12" cy="12" r="10.4"/>', '<rect x="1.6" y="1.6" width="20.8" height="20.8" rx="4"/>',
    '<path d="M12 1.3 21.5 6.7v10.6L12 22.7 2.5 17.3V6.7Z"/>', '<path d="M3 2.2h18v9.4c0 4.9-3.8 8.3-9 10.3-5.2-2-9-5.4-9-10.3Z"/>',
    '<path d="M7.6 1.6h8.8l6 6v8.8l-6 6H7.6l-6-6V7.6Z"/>', '<path d="M1.6 1.6h14.2l6.6 6.6v14.2H1.6Z"/>'];
  const PIDS = Object.keys(A.projects);
  const letters = (name) => { const w = name.split(/[-_ .]+/).filter(Boolean); return (w.length > 1 ? w[0][0] + w[1][0] : name.slice(0, 2)).toLocaleUpperCase(); };
  const mono = (pid, cls) => {
    const P = A.projects[pid];
    if (!P) return '';
    return `<svg class="x-mono${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" aria-hidden="true"><g fill="var(--x-mono-bg)" stroke="currentColor" stroke-width="1.3">${SH[PIDS.indexOf(pid) % 6]}</g>`
      + `<text x="12" y="15.6" text-anchor="middle">${A.esc(letters(P.name))}</text></svg>`;
  };
  const pName = (pid) => (A.projects[pid] ? K('known', A.projects[pid].name, 'Project.name (client join, DR-1 option A)') : NR('project', 'DR-1'));
  // ── which mission (Q15): project + branch (D-1) always; a look-alike (same title, same project) adds when it
  // was asked and what for. Core's branch is archeus/<Mission.id>, an opaque ULID, so it never tells a person
  // which is which; a row shows its prefix and the id's last four characters, the mission page the whole ──
  const norm = (t) => String(t).toLocaleLowerCase().replace(/\s+/g, ' ').trim();
  const twin = (m) => A.missions.some((o) => o !== m && o.project_id === m.project_id && norm(o.title) === norm(m.title));
  const brShort = (b) => { const x = /^archeus\/msn_[0-9A-Z]{22}([0-9A-Z]{4})(\.t\d+)?$/.exec(b || ''); return x ? 'archeus/…' + x[1] + (x[2] || '') : b; };
  const branchOf = (m, full) => (m.integration_branch ? `<span class="mono x-br"${full ? '' : tip(m.integration_branch)}>${full
    ? K('known', m.integration_branch, 'Mission.integration_branch')
    : K('derived', brShort(m.integration_branch), 'Mission.integration_branch = archeus/<Mission.id> (queries.py:35)', 'the middle elided: the id’s last four characters tell two missions apart')}</span>` : '');
  const askedAt = (m) => K('known', 'asked ' + hm(m.created), 'Mission.created_at');
  const idParts = (m, full) => [pName(m.project_id), branchOf(m, full), twin(m) && m.created != null ? askedAt(m) : '', full && m.integration_head ? `<span class="mono">${K('known', m.integration_head, 'Mission.integration_head')}</span>` : '']
    .filter(Boolean).join('<span class="x-sep"> · </span>');
  const where = (m, full) => `<span class="x-where">${mono(m.project_id)}<span class="x-wt">${idParts(m, full)}</span></span>`;
  const objLine = (m) => (twin(m) && m.objective && m.objective !== m.title ? `<p class="x-objl">${K('known', m.objective, 'Mission.objective')}</p>` : '');
  // who does the work: the live item's harness and model (live.py:69-77)
  const HARNESS = { claude_code: 'Claude Code' };
  const agentOf = (m) => (m.live && m.live.harness_id ? K('derived', HARNESS[m.live.harness_id] || m.live.harness_id, 'LiveItem.harness_id = ' + m.live.harness_id, 'the harness id in words') : '');
  const stepOf = (m) => K('known', 'step ' + m.live.step + ' of ' + m.live.of, 'Task (plan order)');
  // what Archeus is doing, as a verb (S-0): the agent and its step, or the checks
  const doing = (m) => (m.state === 'VERIFYING'
    ? `Archeus is checking the result: ${K('known', A.passed(m) + ' of ' + A.checks(m).length + ' checks passed', 'Verification.checks')}`
    : `<b class="x-agent">${agentOf(m)}</b> is on ${stepOf(m)}: ${K('known', m.live.task_title, 'LiveItem.task_title')}`);
  // the most urgent thing in a project, as one state dot (amber waits for you, red is a problem, blue runs)
  const projTone = (pid) => {
    const ms = openOf(pid);
    if (ms.some((m) => waiting.includes(m))) return 'attention';
    if (ms.some((m) => trouble.includes(m) || nowStop(m))) return 'blocked';
    if (ms.some((m) => working.includes(m))) return 'active';
    return '';
  };

  // ── the mission line: the six phases of states.py ──
  const approvedEv = (m) => A.evOf(m, 'approval.decided').filter((e) => e.decision === 'approve').slice(-1)[0];
  const nodeState = (m, i) => {
    const p = phaseOf(m);
    if (m.state === 'CANCELLED') return i < p ? 'past' : i === p ? 'ended' : 'never';
    if (p === 6 || i < p) return 'past';
    if (i > p) return 'future';
    if (m.estop) return 'stop';
    if (expired(m)) return 'ended';
    return m.state === 'BLOCKED' || m.state === 'FAILED' ? 'bad' : 'now';
  };
  const caption = (m) => {
    const x = A.explain(m);
    if (m.state === 'CANCELLED') return K('known', (m.ended.how === 'rejected' ? 'rejected ' : 'cancelled ') + hm(m.ended.at), 'mission.state_changed → CANCELLED');
    if (nowStop(m)) return K('known', 'stopped ' + hm(A.STOP_AT), 'core.estopped');
    if (pastStop(m)) return K('known', 'stopped ' + hm(m.estop_at), 'core.estopped') + ' · still blocked';
    if (expired(m)) return K('known', 'expired ' + hm(m.approval.expires), 'approval.state_changed (ttl_elapsed)');
    if (m.state === 'APPROVAL_REQUIRED') return 'waiting for you · ' + K('known', 'expires ' + hm(m.approval.expires), 'Approval.expires_at');
    if (m.state === 'REVIEWING') return 'waiting for you';
    if (m.state === 'EXECUTING' || m.state === 'VERIFYING') return K('known', 'step ' + m.live.step + ' of ' + m.live.of, 'Task (plan order)') + ' · ' + x.elapsed;
    if (m.state === 'BLOCKED') return K('known', 'check failed', 'verification.failed');
    if (m.state === 'FAILED') return K('known', 'failed ' + hm(m.failed_at), 'execution.failed');
    if (m.state === 'PLANNING') return 'planning';
    if (m.state === 'DONE') return K('known', 'done ' + hm(m.done_at), 'mission.done');
    return '';
  };
  const approvedLink = (m) => {
    const ap = approvedEv(m);
    return ap ? `<a class="x-ok" href="${go({ drawer: 'approval' })}">${K('known', 'Approved ' + hm(ap.at), 'approval.decided')}${I.check}</a>` : '';
  };
  const NODE_IC = { past: I.check, bad: I.cross, stop: '<i class="x-sq"></i>', ended: '<i class="x-bar"></i>' };
  const line = (m, size) => {
    const p = phaseOf(m);
    const full = size === 'full';
    const parts = A.PHASES.map((ph, i) => {
      const s = nodeState(m, i), cur = !['past', 'future', 'never'].includes(s) || (p === 6 && i === 5);
      const ic = full ? (NODE_IC[s] || '<i class="x-core"></i>') : '';
      const lab = full ? `<span class="x-ph">${ph}</span>${cur ? `<span class="x-cap">${caption(m)}</span>` : i === 2 && s === 'past' ? `<span class="x-cap">${approvedLink(m)}</span>` : ''}` : '';
      const seg = i ? `<span class="x-sg ${i <= p && m.state !== 'CANCELLED' ? 'past' : i <= p ? 'past' : s === 'never' ? 'never' : 'future'}" data-i="${i}"><i class="x-fill"></i></span>` : '';
      return seg + `<span class="x-nd ${s}${s === 'now' ? ' tone-' + A.tone(m) : ''}" data-i="${i}">${ic}${lab}</span>`;
    });
    const label = m.state === 'CANCELLED' ? 'Cancelled at ' + A.PHASES[p] : p === 6 ? 'Done' : A.PHASES[p] + ' phase';
    return `<div class="x-line x-line-${size}" role="img" aria-label="${label}">${parts.join('')}</div>`
      + (full ? `<p class="x-lcap"><b>${p === 6 ? 'Done' : A.PHASES[p]}</b> · ${caption(m)}${p > 2 && p < 6 && approvedEv(m) ? '<span class="x-lok">' + approvedLink(m) + '</span>' : ''}</p>` : '');
  };
  const phaseWord = (m) => `<span class="x-pw tone-${toneOf(m)}">${m.state === 'CANCELLED' ? 'Cancelled' : phaseOf(m) === 6 ? 'Done' : nowStop(m) ? 'Stopped' : A.PHASES[phaseOf(m)]}</span>`;

  // ── the frame ──
  const dot = (s) => `<span class="x-dot x-dot-${s || (offline || loading ? 'unknown' : A.estop.state)}"></span>`;
  const estopBtn = (short) => {
    if (offline || loading) return `<span class="estop x-estop-off" aria-disabled="true"${tip(offline ? 'Core cannot be reached, so this page cannot stop anything. Use the tray’s Emergency stop or run archeus estop on the computer running Archeus.' : 'Connecting to Core…')}>${I.stop}${short ? 'Stop' : 'Stop all work'}</span>`;
    if (stopped && Q.get('resume') === 'sending') return `<span class="estop" data-state="stopped" aria-busy="true">Resuming…</span>`;
    if (stopped) return `<a class="estop" data-state="stopped" href="${go(A.S === 'stopped' && isPhone ? { v: 'resume' } : { resume: 'sending' })}">Resume work…</a>`;
    return A.estopButton({ short });
  };
  let isPhone = false;
  const safetyWords = () => {
    if (loading) return { dot: 'unknown', b: 'Connecting to Core…', s: 'state not known yet' };
    if (offline) return { dot: 'unknown', b: 'Core cannot be reached', s: 'state not known · showing what this client read at ' + hm(A.NOW) };
    // X.4 (Q17): the safety line speaks of the stop and nothing else; "working" belongs to what Archeus is doing
    return { dot: A.estop.state, b: K('known', A.estop.state === 'running' ? 'Not stopped' : A.safety.label, A.safety.src), s: primed ? K('known', A.safety.sub, A.safety.src) : K('known', 'accepts new work', A.safety.src) + ' · ' + K('known', 'Core connected', 'connection.state') };
  };
  const OFFLINE_BAND = () => `<div class="x-band x-band-off" role="status"><b>${K('known', 'Offline since ' + hm(A.NOW + 1), 'connection.state = offline')}.</b> Nothing you do here is sent. Work on the computer running Archeus continues. <span class="x-bandk">To stop all work now: the tray’s <b>Emergency stop</b>, or <code>archeus estop</code> on that computer.</span></div>`;
  const STOP_TEXT = () => `${K('known', 'All work stopped at ' + hm(A.STOP_AT), 'core.estopped.at')} from ${K('known', A.estop.by, 'Device.name')}. Nothing runs until you resume.`;
  const RESUMED_BAND = () => {
    const held = A.missions.filter(pastStop);
    return resumed ? `<div class="x-band x-band-ok" role="status"><b>${K('known', 'Work resumed at ' + hm(A.NOW), 'core.rearmed')}.</b> ${n('derived', held.length + ' ' + plural(held.length, 'mission', 'missions') + ' the stop interrupted', 'Mission.state = BLOCKED, reason emergency stop', 'count')} ${plural(held.length, 'stays', 'stay')} blocked until you unblock ${plural(held.length, 'it', 'each one')}. <a href="${to({ v: 'missions' })}#stopped">Show ${plural(held.length, 'it', 'them')}</a></div>` : '';
  };
  const sysbar = () => {
    if (stopped) return `<header class="x-sys x-sys-stop"><span class="x-brand">${I.mark}Archeus</span><span class="x-stopline">${I.stop}<b>Emergency stop</b><span>${STOP_TEXT()}</span></span><span class="x-end">${estopBtn()}</span></header>`;
    const w = safetyWords();
    const live = running.length && !offline && !loading ? `<a class="x-live" href="${to({ v: 'missions' })}#running"><span class="x-livedot"></span>${[working.length ? n('derived', working.length + ' running', 'LiveItem', 'missions with a live execution') : '',
      queued.length ? n('derived', queued.length + ' queued', 'Mission.state = EXECUTING, no live execution', 'count') : ''].filter(Boolean).join(' · ')}</a>` : '';
    return `<header class="x-sys${primed ? ' x-sys-primed' : ''}${offline || loading ? ' x-sys-off' : ''}"><span class="x-brand">${I.mark}Archeus</span>
      <span class="x-safe">${dot(w.dot)}<b>${w.b}</b><span class="t2">${w.s}</span></span>${live}
      <a class="x-tell" href="${go({ tell: '1' })}"${offline || loading ? ' aria-disabled="true"' : ''}>${I.tell}<span>Tell Archeus what to do…</span><kbd>Ctrl K</kbd></a>
      <span class="x-end">${estopBtn()}</span></header>${primed ? `<div class="x-band x-band-primed">${A.primedHint()}</div>` : ''}${offline ? OFFLINE_BAND() : ''}${RESUMED_BAND()}`;
  };
  const PLACES = [['home', 'Overview', I.home], ['missions', 'Missions', I.missions], ['ideas', 'Ideas', '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><path d="M9.5 18h5M10.5 21h3M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.3 1.1 2.2h5c0-.9.4-1.6 1.1-2.2A6 6 0 0 0 12 3Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>'],
    ['projects', 'Projects', '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><path d="M3 6.5h6.5l2 2H21V19H3Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>'], ['control', 'Control', I.control]];
  // a mission or idea is opened inside the place you came from: the left bar keeps that place, as the back link names it
  const FROM = Q.get('from') || '';
  const fromPid = FROM.startsWith('project:') ? FROM.slice(8) : '';
  const navOn = () => {
    if (V === 'mission' || V === 'idea') {
      if (FROM === 'overview' || FROM === 'notif') return 'home';
      if (fromPid) return 'projects';
      if (['missions', 'ideas', 'projects', 'control'].includes(FROM)) return FROM;
    }
    return { home: 'home', mission: 'missions', missions: 'missions', ideas: 'ideas', idea: 'ideas', projects: 'projects', project: 'projects', control: 'control', resume: 'control' }[V] || 'home';
  };
  const badge = (k) => (k === 'missions' && waiting.length ? `<span class="x-badge">${n('derived', waiting.length, 'Approval PENDING + review requested', 'count')}</span>` : '');
  const nav = () => {
    const sel = V === 'project' ? Q.get('pid') : fromPid;
    const ctxP = V === 'mission' ? (A.byId[Q.get('id')] || {}).project_id : V === 'idea' ? (IDEAS.find((i) => i.id === Q.get('iid')) || {}).project_id : '';
    return `<nav class="x-nav" aria-label="Places">${PLACES.map(([k, l, ic]) => `<a href="${place(k)}" class="x-place${k === navOn() ? ' on' : ''}"${k === navOn() ? ' aria-current="page"' : ''}>${ic}<span>${l}</span>${badge(k)}</a>`).join('')}
      <div class="label x-navlabel">Projects</div>${PIDS.map((id) => {
        const k = openOf(id).length, tn = projTone(id);
        return `<a class="x-proj${id === sel ? ' on' : id === ctxP ? ' ctx' : ''}" href="${projPage(id)}">${mono(id)}<span class="x-pn">${K('known', A.projects[id].name, 'Project.name')}</span>${tn ? `<span class="x-pdot tone-${tn}"></span>` : ''}<span class="num t3">${k ? n('derived', k, 'Mission.project_id', 'missions not done') : ''}</span></a>`;
      }).join('') || `<p class="x-navempty t3">No projects yet</p>`}</nav>`;
  };
  const desk = (main, over) => `<div class="x-desk${offline ? ' is-off' : ''}">${sysbar()}<div class="x-body">${nav()}<main class="x-main" id="main">${main}</main></div>${over || ''}${tellModal()}</div>`;

  // phone: tabs on the five places; a pushed page has Back + its parent's name and no tabs
  const tabs = () => `<nav class="x-tabs" aria-label="Places">${PLACES.map(([k, l, ic]) => `<a href="${place(k)}" class="${k === navOn() ? 'on' : ''}"${k === navOn() ? ' aria-current="page"' : ''}><span class="x-tic">${ic}${k === 'missions' && waiting.length ? `<span class="x-badge">${n('derived', waiting.length, 'Approval PENDING', 'count')}</span>` : ''}</span><span>${l}</span></a>`).join('')}</nav>`;
  const liveStrip = () => {
    if (stopped || offline || loading || !running.length) return '';
    const m = running[0];
    return `<a class="x-strip" href="${running.length === 1 ? open(m) : to({ v: 'missions' }) + '#running'}"><span class="x-livedot"></span><b>${n('derived', running.length + ' running', 'Mission.state', 'EXECUTING + VERIFYING')}</b><span class="x-stt">${T(m)} · ${K('known', 'step ' + m.live.step + ' of ' + m.live.of, 'Task (plan order)')}</span>${I.chev}</a>`;
  };
  const pbar = (back) => {
    if (stopped && !back) return `<header class="x-pbar x-pbar-stop"><span class="x-brand">${I.mark}Archeus</span><span class="x-stoptag">${I.stop}Emergency stop</span></header>`;
    const left = back ? `<a class="x-pback" href="${back[1]}">${I.back}<span>${back[0]}</span></a>` : `<span class="x-brand">${I.mark}Archeus${dot(safetyWords().dot)}</span>`;
    return `<header class="x-pbar${stopped ? ' x-pbar-stop' : offline || loading ? ' x-pbar-off' : ''}">${left}<span class="x-end">${back || stopped ? '' : `<a class="x-round" href="${to({ v: 'tell' })}" aria-label="Tell Archeus what to do">${I.tell}</a>`}${stopped && back ? `<span class="x-stoptag">${I.stop}Stopped</span>` : estopBtn(true)}</span></header>`
      + (primed ? `<div class="x-pband">${A.primedHint()}</div>` : '') + (offline ? OFFLINE_BAND() : '') + RESUMED_BAND();
  };
  const phone = (body, extra) => `<div class="x-phone${offline ? ' is-off' : ''}">${pbar()}<main class="x-pmain" id="main">${body}</main><div class="x-dock">${liveStrip()}${tabs()}</div>${extra || ''}</div>`;
  const pushed = (back, body, extra, cls) => `<div class="x-phone x-pushed${cls ? ' ' + cls : ''}${offline ? ' is-off' : ''}">${pbar(back)}<main class="x-pmain" id="main">${body}</main>${extra || ''}</div>`;
  const backOf = () => {
    const f = Q.get('from') || (V === 'idea' ? 'ideas' : V === 'project' ? 'projects' : 'overview');
    if (f.startsWith('project:')) { const pid = f.slice(8); return [A.projects[pid] ? A.esc(A.projects[pid].name) : 'Project', projPage(pid)]; }
    if (f.startsWith('idea:')) return ['Idea', to({ v: 'idea', iid: f.slice(5) })];
    const k = { overview: 'home', notif: 'home', missions: 'missions', ideas: 'ideas', projects: 'projects', control: 'control' }[f] || 'home';
    return [{ home: 'Overview', missions: 'Missions', ideas: 'Ideas', projects: 'Projects', control: 'Control' }[k], place(k)];
  };

  // ── overview ──
  const zone = (label, meta, body, cls, id) => `<section class="x-zone ${cls || ''}"${id ? ` id="${id}"` : ''}><header class="x-zh"><h2 class="label">${label}</h2><span class="x-zmeta">${meta || ''}</span></header>${body}</section>`;
  const more = (all, shown, label, href) => (all > shown ? `<a class="x-more" href="${href}">${n('derived', all - shown + ' more', 'count', 'beyond the first ' + shown)} ${label}${I.chev}</a>` : '');
  const zmeta = () => [working.length ? n('derived', working.length, 'LiveItem', 'missions with a live execution') : '',
    queued.length ? n('derived', queued.length + ' queued', 'Mission.state = EXECUTING, no live execution', 'count') : ''].filter(Boolean).join(' · ');
  const expiryOf = (m, longForm) => {
    if (!m.approval) return `<span class="num t3">${K('known', 'since ' + hm(m.review.since), 'review.requested')}</span>`;
    const left = m.approval.expires - A.NOW;
    return `<span class="num ${left <= 15 ? 'x-urgent' : 't3'}">${K('known', 'expires ' + hm(m.approval.expires), 'Approval.expires_at')}${longForm ? ' · ' + K('derived', 'in ' + left + ' min', 'Approval.expires_at', 'expires_at − now') : ''}</span>`;
  };
  const askRow = (m, ph) => {
    const x = A.explain(m), d = A.decision(m);
    const body = `<div class="x-rtop"><span class="label x-kind">${d.kind}</span>${expiryOf(m, !ph)}</div>
      <div class="x-rtitle">${T(m)}</div>${where(m)}
      <p class="x-why"><span class="x-k">Why</span><span>${x.why}</span></p>`;
    return ph ? `<a class="x-row x-ask x-card" href="${open(m)}">${body}<span class="x-go">Review${I.chev}</span></a>`
      : `<div class="x-row x-ask">${body}<a class="btn primary x-review" href="${open(m)}"${offline ? ' aria-disabled="true"' : ''}>Review</a></div>`;
  };
  const troubleRow = (m, ph) => {
    const tag = ph ? 'a' : 'div', link = ph ? '' : `<a class="btn x-review" href="${open(m)}">Open</a>`;
    const because = expired(m) ? K('known', 'Nobody decided by ' + hm(m.approval.expires) + '; nothing ran', 'approval.state_changed (ttl_elapsed)')
      : pastStop(m) ? K('known', 'Stopped by the emergency stop at ' + hm(m.estop_at), 'mission.state_changed reason: emergency stop')
        : K('known', m.because[1], m.state === 'FAILED' ? 'Execution.failure' : 'Verification.checks');
    return `<${tag} class="x-row x-bad x-card"${ph ? ` href="${open(m)}"` : ''}><div class="x-rtop">${chip(m)}<span class="num t3">${caption(m)}</span></div>
      <div class="x-rtitle">${ph ? T(m) : `<a href="${open(m)}">${T(m)}</a>`}</div>${where(m)}
      <p class="x-why"><span class="x-k">Because</span><span>${because}</span></p>${link}${ph ? `<span class="x-go">Open${I.chev}</span>` : ''}</${tag}>`;
  };
  const runTile = (m, ph) => {
    const x = A.explain(m), tag = ph ? 'a' : 'a';
    return `<${tag} class="x-tile x-card" href="${open(m)}"><div class="x-rtop">${chip(m)}<span class="num t3">${m.estop ? caption(m) : x.elapsed}</span></div>
      <div class="x-rtitle">${T(m)}</div>${where(m)}
      <div class="x-lr">${line(m, 'mid')}${phaseWord(m)}</div>
      <p class="x-now">${x.what}</p>${m.estop ? '' : `<p class="x-then t3">${x.next}</p>`}</${tag}>`;
  };
  const sumChecks = (r) => A.missions.reduce((s, m) => s + A.checks(m).filter((c) => c[1] === r).length, 0);
  const todayStats = () => `<div class="x-stats">
      <div><span class="x-big num">${n('derived', done.length, 'Mission.state = DONE', 'count today')}</span><span class="label">Done</span></div>
      <div><span class="x-big num">${n('derived', sumChecks('passed'), 'Verification.checks', 'passed checks today')}</span><span class="label">Checks passed</span></div>
      <div><span class="x-big num${sumChecks('failed') ? ' x-red' : ''}">${n('derived', sumChecks('failed'), 'Verification.checks', 'failed checks today')}</span><span class="label">Checks failed</span></div></div>`;
  const titleOf = (id) => (A.byId[id] || {}).title;
  const evText = (e) => {
    if (e.kind === 'core.rearmed') return K('known', 'Work resumed: the emergency stop was cleared', 'core.rearmed');
    if (e.kind === 'mission.state_changed' && e.to === 'CANCELLED') return K('known', e.trigger === 'reject' ? 'cancelled: you rejected the plan' : 'cancelled', 'mission.state_changed → CANCELLED (' + e.reason + ')');
    if (e.kind === 'approval.expired') return K('known', 'approval expired; nothing ran', 'approval.state_changed (ttl_elapsed)');
    if (e.kind === 'review.decided') return K('known', 'you accepted the result', 'review.state_changed (verdict accept)');
    return A.evText(e);
  };
  const evRows = (evs) => `<ol class="x-events">${evs.map((e) => {
    const m = A.byId[e.mission_id];
    return `<li><span class="num t3">${K('known', hm(e.at), 'event.at')}</span><span>${m ? `<a href="${open(m)}"><b>${T(m)}</b></a>` : '<b>Archeus</b>'} ${evText(e)}</span></li>`;
  }).join('')}</ol>`;
  const recent = (k) => evRows(A.events.slice().sort((a, b) => b.at - a.at || b.seq - a.seq).slice(0, k));
  const headline = () => {
    if (stopped) return 'Archeus is stopped.';
    if (waiting.length) return `${n('derived', waiting.length + ' ' + plural(waiting.length, 'decision is', 'decisions are'), 'Approval PENDING + review requested', 'count')} waiting for you.`;
    if (trouble.length) return `${n('derived', trouble.length + ' ' + plural(trouble.length, 'mission needs', 'missions need'), 'Mission.state', 'BLOCKED + FAILED')} you.`;
    return 'Nothing needs you.';
  };
  const counts = () => [stopped ? '' : working.length ? `${waiting.length ? 'Meanwhile ' : ''}Archeus is working on ${n('derived', working.length + ' ' + plural(working.length, 'mission', 'missions'), 'LiveItem', 'missions with a live execution')}`
      : 'Archeus is not working on anything right now',
    !stopped && queued.length && n('derived', queued.length + ' queued for an agent', 'Mission.state = EXECUTING, no live execution', 'count'),
    halted.length && n('derived', halted.length + ' stopped', 'Execution.stop_reason = estop'),
    trouble.length && n('derived', trouble.length + ' blocked or failed', 'Mission.state', 'BLOCKED + FAILED'),
    planning.length && n('derived', planning.length + ' planning', 'Mission.state = PLANNING'),
    n('derived', done.length + ' done today', 'Mission.state = DONE')].filter(Boolean).join('<span class="t3"> · </span>');
  const deadline = () => {
    if (stopped) return `<p class="x-lead">${K('known', halted.length + ' ' + plural(halted.length, 'mission was', 'missions were') + ' stopped', 'core.estopped.killed')}. ${n('derived', waiting.length + ' ' + plural(waiting.length, 'decision stays', 'decisions stay') + ' open', 'Approval PENDING', 'count')}: you can reject them or ask for changes, but approving is refused until you resume.</p>`;
    const f = waiting.find(near);
    return f ?`<p class="x-lead"><span class="x-urgent x-lk">${I.decide}Next deadline</span>${T(f)}: plan v${f.approval.plan_version} expires at ${K('known', hm(f.approval.expires), 'Approval.expires_at')} — ${K('derived', 'in ' + (f.approval.expires - A.NOW) + ' min', 'Approval.expires_at', 'expires_at − now')}.</p>` : '';
  };
  const tellBig = () => `<a class="x-tellbig" href="${go(isPhone ? { v: 'tell' } : { tell: '1' })}">${I.tell}<span>Tell Archeus what to do</span><kbd>Ctrl K</kbd></a>`;
  const CAP = { w: 4, t: 3, r: 4 };
  const homeDesk = () => {
    if (loading) return desk(skeleton('home'));
    if (A.S === 'noprojects') return desk(firstRun());
    if (A.S === 'idle' || A.S === 'empty') return desk(quiet());
    const head = `<div class="x-head"><div class="label">Overview · ${K('known', 'Tuesday ' + hm(A.NOW), 'clock')}</div>
      <h1 class="x-display">${headline()}</h1><div class="x-counts">${counts()}</div>${deadline()}</div>`;
    const wz = zone('Waiting for you', waiting.length ? n('derived', waiting.length, 'Approval PENDING', 'count') : '',
      waiting.length ? waiting.slice(0, CAP.w).map((m) => askRow(m)).join('') + more(waiting.length, CAP.w, 'waiting', to({ v: 'missions' }) + '#waiting') : '<p class="x-empty">Nothing waits for you.</p>', 'x-zw', 'waiting');
    const tz = trouble.length ? zone('Blocked or failed', n('derived', trouble.length, 'Mission.state', 'BLOCKED + FAILED'), trouble.slice(0, CAP.t).map((m) => troubleRow(m)).join('') + more(trouble.length, CAP.t, 'blocked or failed', to({ v: 'missions' }) + '#trouble'), 'x-zt') : '';
    const live = stopped ? halted : running;
    const rz = zone(stopped ? 'Stopped by the emergency stop' : 'Running now', live.length ? n('derived', live.length, 'Mission.state', 'count') : '',
      live.length ? `<div class="x-tiles">${live.slice(0, CAP.r).map((m) => runTile(m)).join('')}</div>` + more(live.length, CAP.r, 'running', to({ v: 'missions' }) + '#running') : '<p class="x-empty">Nothing is running.</p>', stopped ? 'x-zstop' : 'x-zr', 'running');
    const today = zone('Today', `<span class="t3">${K('derived', A.events.filter((e) => e.at > A.LAST_LOOKED).length + ' changes since you looked', 'events after User.last_ack_event_seq', 'count')}</span>`, todayStats() + recent(6));
    // two columns, one reading order: what needs you (left), what Archeus is doing (right)
    return desk(`${head}<div class="x-grid"><div class="x-col">${stopped ? rz + wz : wz + tz}</div><div class="x-col">${stopped ? tz + today : rz + today}</div></div>`);
  };
  const projectList = () => `<div class="x-plist">${PIDS.map((id) => {
    const k = openOf(id).length, last = A.events.filter((e) => (A.byId[e.mission_id] || {}).project_id === id).reduce((t, e) => Math.max(t, e.at), -1), tn = projTone(id);
    return `<a class="x-prow" href="${projPage(id)}">${mono(id)}<span class="x-pn">${K('known', A.projects[id].name, 'Project.name')}</span><span class="num t3">${[tn ? `<span class="x-pdot tone-${tn}"></span>` : '', k ? n('derived', k + ' open', 'Mission.project_id', 'missions not done') : '', last >= 0 ? K('derived', 'last ' + hm(last), 'event.at of the project’s missions', 'latest') : ''].filter(Boolean).join(' ')}</span>${I.chev}</a>`;
  }).join('')}</div>`;
  const doneRows = (ms) => (ms.length ? `<div class="x-done">${ms.map((m) => `<a class="x-drow" href="${open(m)}">${I.check}<span class="x-dt">${T(m)}</span>
      <span class="x-dm">${mono(m.project_id)}${pName(m.project_id)} · ${K('known', hm(m.done_at), 'mission.done')}${A.explain(m).evidence ? ' · ' + A.explain(m).evidence : ''}</span></a>`).join('')}</div>` : '<p class="x-empty">Nothing finished yet today.</p>');
  // quiet: the invitation first, then what was done and where (S-7)
  const quiet = () => `<div class="x-invite">${tellBig()}</div>
    <div class="x-qcols">${zone('Done today', done.length ? n('derived', done.length, 'Mission.state = DONE', 'count') : '', doneRows(done))}${zone('Projects', '', projectList())}</div>`;
  // first run: no project yet. Registering one is POST /v1/projects, an admin route: an admin device can, others are told where
  const firstRun = () => `<div class="x-first"><h1 class="x-display">Add a project to start.</h1>
    <p class="x-firstp">Archeus works inside your repositories. Add one, then tell Archeus what to do there.</p>
    <div class="x-firsta"><a class="btn primary x-big-btn" href="#"${tip('Registers a folder and its repositories with Core (POST /v1/projects, admin).')}>Add a project…</a></div>
    <ol class="x-how">${A.PHASES.map((p, i) => `<li><span class="num t3">${i + 1}</span><b>${p}</b><span class="t2">${['Archeus reads what you asked', 'it writes a plan', 'you approve it, if your policy asks', 'agents do the work', 'checks run', 'you accept the result'][i]}</span></li>`).join('')}</ol></div>`;

  const homePhone = () => {
    if (loading) return phone(skeleton('home'));
    if (A.S === 'noprojects') return phone(firstRun());
    if (A.S === 'idle' || A.S === 'empty') return phone(quiet());
    if (stopped) {
      return phone(`<section class="x-status x-status-stop"><div class="label">${K('known', 'Tuesday ' + hm(A.STOP_AT), 'core.estopped.at')}</div><h1 class="x-phl">Archeus is stopped</h1>
        <p class="t2">${STOP_TEXT()}</p><p class="t2">${n('derived', waiting.length + ' ' + plural(waiting.length, 'decision stays', 'decisions stay') + ' open', 'Approval PENDING')}; approving waits until you resume.</p>
        <div class="x-resume">${estopBtn()}</div></section>
        ${zone('Stopped by the emergency stop', halted.length, halted.map((m) => runTile(m, true)).join(''), 'x-zstop')}
        ${zone('Waiting for you', waiting.length, waiting.map((m) => askRow(m, true)).join(''))}`);
    }
    const ctr = `<div class="x-ctr"><a class="tone-attention" href="#waiting"><b>${n('derived', waiting.length, 'Mission.state', 'APPROVAL_REQUIRED + REVIEWING')}</b><span>Waiting</span></a>
      <a class="tone-active" href="#running"><b>${n('derived', working.length, 'LiveItem', 'missions with a live execution')}</b><span>Running${queued.length ? ' · ' + n('derived', queued.length + ' queued', 'Mission.state = EXECUTING, no live execution', 'count') : ''}</span></a>
      <a class="tone-blocked" href="#trouble"><b>${n('derived', trouble.length, 'Mission.state', 'BLOCKED + FAILED')}</b><span>Blocked or failed</span></a></div>`;
    const hero = `<section class="x-hero"><div class="label">${K('known', 'Tuesday ' + hm(A.NOW), 'clock')}</div>
      <h1 class="x-phl">${waiting.length ? n('derived', waiting.length + ' ' + plural(waiting.length, 'decision waits', 'decisions wait'), 'Approval PENDING', 'count') + ' for you' : 'Nothing needs you'}</h1>
      <p class="x-safeline">${dot()}<b>${safetyWords().b}</b><span class="t3">${offline ? '' : K('known', 'accepts new work', A.safety.src)}</span></p>${ctr}</section>`;
    const pw = 3;
    return phone(`${hero}
      ${waiting.length ? zone('Waiting for you', waiting.length, waiting.slice(0, pw).map((m) => askRow(m, true)).join('') + more(waiting.length, pw, 'waiting', to({ v: 'missions' }) + '#waiting'), 'x-pz', 'waiting') : ''}
      ${trouble.length ? zone('Blocked or failed', trouble.length, trouble.slice(0, pw).map((m) => troubleRow(m, true)).join('') + more(trouble.length, pw, 'blocked or failed', to({ v: 'missions' }) + '#trouble'), 'x-pz', 'trouble') : ''}
      ${running.length ? zone('Running now', running.length, running.slice(0, pw).map((m) => runTile(m, true)).join('') + more(running.length, pw, 'running', to({ v: 'missions' }) + '#running'), 'x-pz', 'running') : ''}
      ${zone('Projects', '', projectList(), 'x-pz')}`);
  };

  // loading: the frame says it is connecting; the page holds the shape and asserts nothing
  const skeleton = (kind) => `<div class="x-skel" aria-busy="true" aria-label="Reading from Core">
    <div class="x-sk x-sk-l"></div><div class="x-sk x-sk-h"></div><div class="x-sk x-sk-m"></div>
    ${kind === 'mission' ? '<div class="x-sk x-sk-line"></div>' : ''}<div class="x-skg"><div class="x-sk x-sk-c"></div><div class="x-sk x-sk-c"></div></div>
    <p class="x-sktext t3">${K('known', 'Reading from Core…', 'connection.state = connecting')}</p></div>`;

  // ── missions ──
  const MGROUPS = () => [['waiting', 'Waiting for you', waiting], ['stopped', 'Stopped by the emergency stop', halted.concat(A.missions.filter(pastStop))], ['trouble', 'Blocked or failed', trouble.filter((m) => !pastStop(m))],
    ['running', 'Running', stopped ? [] : working], ['queued', 'Queued for an agent', stopped ? [] : queued], ['planning', 'Planning', planning], ['done', 'Done today', done], ['ended', 'Cancelled today', ended]];
  const missionRow = (m) => `<a class="x-mi" href="${open(m)}">${mono(m.project_id, 'x-mi-mono')}<span class="x-mi1"><span class="x-mt">${T(m)}</span><span class="x-mw">${pName(m.project_id)}${A.ctx(m).branch ? ' · <span class="mono">' + A.ctx(m).branch + '</span>' : ''}</span></span>
      <span class="x-mi2">${line(m, 'mid')}${phaseWord(m)}</span><span class="x-mi3">${chip(m)}<span class="num t3">${caption(m)}</span></span></a>`;
  const missionsBody = () => {
    const f = Q.get('f'), keep = (m) => !f || m.project_id === f;
    const filt = `<div class="x-filter" role="toolbar" aria-label="Filter by project"><a class="x-fchip${f ? '' : ' on'}" href="${go({ f: null })}">All projects</a>${PIDS.filter((id) => A.missions.some((m) => m.project_id === id)).map((id) => `<a class="x-fchip${f === id ? ' on' : ''}" href="${go({ f: id })}">${mono(id)}${K('known', A.projects[id].name, 'Project.name')}</a>`).join('')}</div>`;
    const gs = MGROUPS().map(([id, l, ms]) => [id, l, ms.filter(keep)]).filter((g) => g[2].length);
    return filt + (gs.length ? gs.map(([id, l, ms]) => `<section class="x-grp" id="${id}"><h2 class="label">${l}<span class="num t3">${ms.length}</span></h2><div class="x-mis">${ms.map(missionRow).join('')}</div></section>`).join('')
      : `<p class="x-empty x-emptybig">No missions yet. ${tellBig()}</p>`);
  };

  // ── the mission page: one page, every state ──
  const dl = (rows) => `<dl class="x-dl">${rows.filter((r) => r[1]).map(([k, v]) => `<dt>${k}</dt><dd>${v.replace(/>[a-z ]+: (not recorded|kept by Core)/, '>$1')}</dd>`).join('')}</dl>`;
  const steps = (m) => `<ol class="x-steps">${m.tasks.map((t, i) => {
    const st = t[1] === 'RUNNING' && m.estop ? 'STOPPED' : t[1];
    const ic = { SUCCEEDED: I.check, RUNNING: I.dot, FAILED: I.cross, STOPPED: I.stop, CANCELLED: '<i class="x-bar"></i>' }[st] || I.ring;
    const w = { SUCCEEDED: 'Done', RUNNING: 'Running', FAILED: 'Failed', STOPPED: 'Stopped', PENDING: 'Waiting', CANCELLED: 'Cancelled' }[st];
    return `<li class="s-${st.toLowerCase()}"><span class="x-sic">${ic}</span><span class="num t3">${i + 1}</span><span class="x-st">${K('known', t[0], 'Task.title')}</span><span class="x-sw">${K('known', w, 'Task.state')}</span></li>`;
  }).join('')}</ol>`;
  // the mission's state as a sentence with Archeus as its subject (S-0: what is Archeus doing, here)
  const sayOf = (m, x) => {
    const D = (t, rule) => K('derived', t, 'Mission.state = ' + m.state, rule || 'the state in words');
    if (nowStop(m)) return D('Archeus stopped this at ' + hm(A.STOP_AT) + '.', 'core.estopped');
    if (pastStop(m)) return D('Archeus is waiting for you to unblock this.', 'BLOCKED since the emergency stop');
    if (m.state === 'CANCELLED') return D(m.ended.how === 'rejected' ? 'You rejected its plan; nothing ran.' : 'Cancelled at ' + hm(m.ended.at) + '.');
    if (expired(m)) return D('Nobody decided in time; nothing ran.', 'approval.state_changed (ttl_elapsed)');
    if (askBlocked(m)) return D('Archeus is waiting for you to approve task ' + m.approval.task + '.');
    return {
      APPROVAL_REQUIRED: () => D('Archeus is waiting for you to approve plan v' + (m.approval || {}).plan_version + '.'),
      REVIEWING: () => D('Archeus finished and checked this; it waits for you to accept it.'),
      EXECUTING: () => D('Archeus is working on this.') + (m.live ? ` <span class="t2">${agentOf(m)} · for ${x.elapsed}</span>` : ''),
      VERIFYING: () => D('Archeus is checking the result.') + (x.elapsed ? ` <span class="t2">for ${x.elapsed}</span>` : ''),
      BLOCKED: () => D('Archeus cannot go on; it waits for you.'),
      FAILED: () => D('Archeus could not finish this.'),
      PLANNING: () => D('Archeus is planning this.'),
      DONE: () => D('Archeus finished this at ' + hm(m.done_at) + '.'),
    }[m.state]();
  };
  const mhead = (m, ph) => {
    const x = A.explain(m);
    return `${ph ? '' : `<a class="x-back" href="${backOf()[1]}">${I.back}${backOf()[0]}</a>`}
      <p class="x-mtop">${chip(m)}<span class="x-say">${sayOf(m, x)}</span></p>
      <h1 class="x-headline">${T(m)}</h1>${m.objective ? `<p class="x-obj">${K('known', m.objective, 'Mission.objective')}</p>` : ''}
      ${where(m, true)}`;
  };
  const verifiedSec = (m) => {
    const ck = A.checks(m);
    const body = ck.length ? `<ul class="x-checks">${ck.map((c) => `<li class="r-${c[1]}">${A.checkIcon(c[1])}<span>${K('known', c[0], 'Verification.checks.name')}</span><span class="num t3">${K('known', c[1] + (c[2] != null ? ' · exit ' + c[2] : ''), 'Verification.checks.result')}</span></li>`).join('')}</ul>`
      : `<p class="t2">${K('derived', m.state === 'CANCELLED' || m.state === 'APPROVAL_REQUIRED' || m.state === 'PLANNING' ? 'Nothing has run, so nothing is verified.' : 'Not verified yet: checks run after the last step.', 'Verification (none)', 'the mission has no verification record')}</p>`;
    return `<section class="x-sec"><h2 class="label">Verified${ck.length ? ' · ' + K('known', A.passed(m) + ' of ' + ck.length + ' passed', 'Verification.checks') : ''}</h2>${body}</section>`;
  };
  const decisionsSec = (m) => {
    const all = A.evOf(m, 'approval.decided'), W = { approve: 'You approved the plan', request_changes: 'You asked for changes', reject: 'You rejected the plan' };
    if (!all.length) return '';
    return `<section class="x-sec"><h2 class="label">Your decisions</h2><ol class="x-events x-decs">${all.map((e) => `<li><span class="num t3">${K('known', hm(e.at), 'approval.decided.at')}</span><span>${e.decision === 'approve' && !SHOT_DRAWER ? `<a href="${go({ drawer: 'approval' })}">${K('known', W[e.decision], 'approval.decided.decision')}</a>` : K('known', W[e.decision], 'approval.decided.decision')}${e.decision === 'request_changes' && NOTE[m.id] ? `<span class="x-note">“${K('known', NOTE[m.id], NOTE_SRC)}”</span>` : ''}</span></li>`).join('')}</ol></section>`;
  };
  const SHOT_DRAWER = false;
  const ctxSec = (m) => {
    const c = A.ctx(m);
    return `<section class="x-sec"><h2 class="label">Context</h2>${dl([['Project', `<span class="x-wt">${mono(m.project_id)}${c.project}</span>`], ['Repository', c.repo], ['Branch', c.branch && '<span class="mono">' + c.branch + '</span>'], ['Task branch', c.taskBranch && '<span class="mono">' + c.taskBranch + '</span>'], ['Commit', c.head && '<span class="mono">' + c.head + '</span>'], ['Runs on', c.where], ['Remote', c.remote]])}</section>`;
  };
  const nowSec = (m) => {
    if (!m.live || m.estop) return '';
    const x = A.explain(m);
    return `<section class="x-sec x-nowsec"><h2 class="label">Right now</h2>${dl([['Doing', x.what], ['Next', x.next], ['Evidence', x.evidence], ['Operation', A.ctx(m).op]])}</section>`;
  };
  const planSec = (m) => (m.tasks.length ? `<section class="x-sec"><h2 class="label">Plan · ${K('derived', A.stepsDone(m) + ' of ' + m.tasks.length + ' steps done', 'Task.state', 'count')}</h2>${steps(m)}</section>` : '');

  // the answer component under the line: a plan approval or a result review (S-9)
  const off = offline ? ' aria-disabled="true"' : '';
  const sending = Q.get('sending');
  const askComp = (m, ph) => {
    const d = A.decision(m), x = A.explain(m), c = A.ctx(m);
    if (!m.approval) {
      return `<section class="x-comp" id="ask"><div class="x-cb"><div class="label x-kind">${d.kind} · ${K('known', 'asked at ' + hm(m.review.since), 'review.requested')}</div><h2 class="x-ch">Accept the result?</h2>
        <div class="x-cs"><h3 class="label">What you accept</h3><p>${x.what} · ${where(m, true)}</p></div>
        <div class="x-cs"><h3 class="label">Verified</h3><ul class="x-checks">${d.checks.map((k) => `<li class="r-${k[1]}">${A.checkIcon(k[1])}<span>${K('known', k[0], 'Verification.checks.name')}</span><span class="num t3">${K('known', k[1] + ' · exit ' + k[2], 'Verification.checks.result')}</span></li>`).join('')}</ul></div>
        <div class="x-cs"><h3 class="label">If you accept</h3><p>${d.actions[0].then}</p></div></div>
        ${ph ? '' : `<div class="x-ca">${d.actions.map((a) => `<a class="btn${a.primary ? ' primary' : ''}" href="${a.key === 'accept' ? go({ did: 'accept' }) : '#'}"${tip(a.then)}${off}>${a.label}</a>`).join('')}</div>`}</section>`;
    }
    const by = Object.fromEntries(d.actions.map((a) => [a.key, a]));
    const refused = stopped ? ' aria-disabled="true"' : off;
    const btn = (a, label, cls) => {
      if (sending) return `<span class="btn${cls}${a.key === sending ? ' is-busy' : ''}" aria-disabled="true">${a.key === sending ? { approve: 'Approving…', reject: 'Rejecting…', changes: 'Sending…' }[a.key] : label || a.label}</span>`;
      return `<a class="btn${cls}" href="${a.key === 'approve' ? go({ did: 'approve' }) : a.key === 'reject' ? go({ did: 'reject' }) : '#'}"${tip(a.then)}${a.key === 'approve' ? refused : off}>${label || a.label}</a>`;
    };
    const why = `${d.why}<details class="x-rules"><summary>The rules that asked</summary><p class="mono t3">${d.rules.join('<br>')}</p></details>`;
    const answers = ph ? '' : `<div class="x-ca">${btn(by.approve, '', ' primary')}${btn(by.changes, '', '')}${btn(by.reject, '', ' danger')}
      ${stopped ? `<p class="x-refused">${K('derived', 'Approving is refused while Archeus is stopped.', 'policy/engine.py builtin:estop: every action DENY; the approval stays PENDING (authorization.py:711-720)')}</p>` : ''}
      ${sending ? `<p class="x-refused t2">${K('derived', 'Sent. Nothing is shown as approved until Core records it.', 'P20 item 18 (only Core’s answer counts)')}</p>` : ''}</div>`;
    return `<section class="x-comp" id="ask">
      <div class="x-cb"><div class="x-ctop"><span class="label x-kind">${d.kind} · asked ${K('known', hm(m.approval.since), 'approval.requested')}</span>${expiryOf(m, true)}</div>
        <h2 class="x-ch">Approve the plan?</h2>
        <div class="x-cgrid">
          <div class="x-cs"><h3 class="label">What you approve</h3><p>${d.summary}</p><ol class="x-tasks">${d.tasks.map((t, i) => `<li><span class="num t3">${i + 1}</span>${t}</li>`).join('')}</ol></div>
          <div class="x-cs"><h3 class="label">If you approve</h3><p>${by.approve.then}</p><p class="t2">${d.expiry}</p></div>
          <div class="x-cs"><h3 class="label">Why Archeus asks</h3><p>${why}</p></div>
          <div class="x-cs"><h3 class="label">Where</h3><p>${where(m, true)}</p><p class="t2">${c.repo ? 'Repository ' + c.repo + ' · ' : ''}runs on ${c.where}</p></div>
          ${d.changed ? `<div class="x-cs"><h3 class="label">What changed since v${m.approval.plan_version - 1}</h3><p>${d.changed}</p></div>` : ''}
          <div class="x-cs"><h3 class="label">Verified</h3><p class="t2">${K('derived', 'Nothing has run yet, so nothing is verified.', 'Execution (none)', 'the mission has no execution')}</p></div>
        </div>
        <p class="x-gaps"><span class="label">Archeus does not know</span> ${d.unknown.join(' · ')}</p></div>
      ${answers}</section>`;
  };

  // the error component: what failed, what Archeus knows, what it does not, what it asks of you (S-11)
  const ANSWER = 'The down-migration drops the table before the index that depends on it, so test_migration_rollback exits 1 when it runs down(). Dropping invoices_customer_idx first, then the table, should fix it. I have not changed anything.';
  const NO_CANCEL = () => gap('no route in Core', 'cancelling a mission: Core has the command but no HTTP route; today it is reached only through the conversation', 'cancel');
  const askArea = (m) => {
    const ask = Q.get('ask');
    if (ask === 'explain') {
      return `<div class="x-full x-answer" id="answer"><h3 class="label">Explain the error</h3>
        <p class="x-asked">You asked the agent that ran “${K('known', m.tasks[0][0], 'Task.title')}”: <i>what went wrong?</i></p>
        <div class="x-wait"${Q.get('wait') ? '' : ' hidden'}><span class="x-dots"><i></i><i></i><i></i></span>Asking the agent…</div>
        <p class="x-typed"${Q.get('wait') ? ' hidden' : ''} data-text="${A.esc(ANSWER)}">${SHOT ? A.esc(ANSWER) : ''}</p>
        <p class="x-gaps">${gap('DR-9', 'asking a mission’s agent a question and streaming back its answer', 'sample answer')}</p></div>`;
    }
    if (ask === 'fix') return `<div class="x-full x-fix" id="answer"><div class="x-flab"><label class="label" for="fx">Tell Archeus how to fix it</label>${gap('DR-9', 'your instructions reaching the agent (the resume route takes no note)', 'instructions')}</div>
        <textarea id="fx" rows="3" placeholder="For example: drop the index before the table in down(), then run the rollback check again."></textarea>
        <div class="x-fixrow"><a class="btn primary" href="#"${tip(K('derived', 'Archeus unblocks the mission and runs it again.', 'POST /v1/missions/{id}/resume: BLOCKED → unblock → RESUMED → redispatch'))}>Send and run again</a><a class="btn quiet" href="${go({ ask: null })}">Cancel</a></div></div>`;
    return '';
  };
  const badComp = (m, ph) => {
    const ck = A.checks(m), failedRun = m.state === 'FAILED';
    const known = failedRun
      ? [K('known', m.because[0], 'execution.failed'), K('known', m.because[1], 'Execution.failure'), K('derived', A.stepsDone(m) + ' of ' + m.tasks.length + ' steps finished', 'Task.state', 'count')]
      : [K('known', A.passed(m) + ' of ' + ck.length + ' checks passed', 'Verification.checks'), ...A.evOf(m, 'checkpoint.created').slice(-1).map((e) => K('known', 'last checkpoint ' + hm(e.at) + ' (' + e.files + plural(e.files, ' file)', ' files)'), 'checkpoint.created')), K('derived', A.stepsDone(m) + ' of ' + m.tasks.length + ' steps finished', 'Task.state', 'count')];
    const unknown = failedRun ? [NR('why the harness stopped', 'DR-8', 'its output is kept by Core, not readable here')] : [NR('why the check failed', 'DR-8', 'its output is kept by Core, not readable here')];
    const fixThen = failedRun ? K('derived', 'Archeus re-plans with your instructions.', 'states.py: FAILED → replan (no HTTP route)') : K('derived', 'Archeus unblocks the mission and runs it again.', 'POST /v1/missions/{id}/resume: BLOCKED → unblock → RESUMED → redispatch');
    const acts = `<a class="btn primary${Q.get('ask') === 'explain' ? ' on' : ''}" href="${go({ ask: 'explain', wait: null })}"${tip(K('derived', 'Asks the agent that ran it what went wrong. Nothing changes.', 'a question, no transition'))}${off}>Explain the error</a>
      <a class="btn${Q.get('ask') === 'fix' ? ' on' : ''}" href="${go({ ask: 'fix', wait: null })}"${tip(fixThen)}${off}>Ask Archeus to fix it</a>${failedRun ? gap('no route in Core', 're-planning a failed mission: Core has the transition (FAILED → replan) but no HTTP route', 'fix') : ''}
      <a class="btn danger" href="${go({ did: 'cancel' })}"${tip(K('derived', 'The mission is cancelled. Nothing more runs.', 'states.py: ' + m.state + ' → cancel → CANCELLED'))}${off}>Cancel mission</a>${NO_CANCEL()}`;
    return `<section class="x-comp x-comp-bad" id="ask">
      <div class="x-cb"><div class="label x-red">${failedRun ? 'Why it failed' : 'Why it is blocked'}</div>
        <ol class="x-chain">${m.because.map((b, i) => `<li><span class="x-cdot"></span><span>${K('known', b, i ? (failedRun ? 'Execution.failure' : 'Verification.checks') : (failedRun ? 'execution.failed' : 'verification.failed'))}</span></li>`).join('')}</ol>
        <div class="x-kn"><div><h3 class="label">Archeus knows</h3><ul>${known.map((k) => `<li>${k}</li>`).join('')}</ul>
          ${ck.length ? `<ul class="x-checks">${ck.map((c) => `<li class="r-${c[1]}">${A.checkIcon(c[1])}<span>${K('known', c[0], 'Verification.checks.name')}</span><span class="num t3">${K('known', c[1] + (c[2] != null ? ' · exit ' + c[2] : ''), 'Verification.checks.result')}</span></li>`).join('')}</ul>` : ''}</div>
          <div><h3 class="label">Archeus does not know</h3><ul>${unknown.map((k) => `<li>${k}</li>`).join('')}</ul>
          <h3 class="label x-mt">Asked of you</h3><p>${K('derived', 'Archeus waits for you: explain, fix or cancel.', 'states.py: ' + m.state + ' exits are your commands')}</p></div></div></div>
      <div class="x-ca">${ph ? `<div class="x-cacol">${acts}</div>` : acts}</div>
      ${askArea(m)}</section>`;
  };
  // the stop component: a mission the emergency stop interrupted
  const stopComp = (m) => {
    if (nowStop(m)) return `<section class="x-comp x-comp-stop" id="ask"><div class="x-cb"><div class="label x-stopk">Stopped by the emergency stop</div>
      <p>${K('known', 'Stopped at ' + hm(A.STOP_AT), 'core.estopped.at')} from ${K('known', A.estop.by, 'Device.name')}, at step ${K('known', m.live.step + ' of ' + m.live.of, 'Task (plan order)')}: ${K('known', m.live.task_title, 'Task.title')}.</p>
      <p class="t2">${K('derived', 'It stays blocked after you resume work, until you unblock it.', 'executions.py:418-441: re-arm does not touch missions')}</p></div></section>`;
    return `<section class="x-comp x-comp-bad" id="ask"><div class="x-cb"><div class="label x-red">Why it is blocked</div>
      <p>${K('known', 'The emergency stop at ' + hm(m.estop_at) + ' interrupted it', 'mission.state_changed reason: emergency stop')} at step ${K('known', m.live.step + ' of ' + m.live.of, 'Task (plan order)')}. Work has resumed since; this mission waits for you.</p></div>
      <div class="x-ca"><a class="btn primary" href="#"${tip(K('derived', 'Archeus runs it again from where it was held.', 'POST /v1/missions/{id}/resume: BLOCKED → unblock → RESUMED → redispatch'))}${off}>Unblock and run again</a><a class="btn danger" href="${go({ did: 'cancel' })}"${off}>Cancel mission</a>${NO_CANCEL()}</div></section>`;
  };
  // the outcome of a mission that has ended: what happened, nothing to answer
  const outcome = (m) => {
    if (m.state === 'CANCELLED') {
      const ev = A.evOf(m, 'mission.state_changed').slice(-1)[0] || {};
      const rej = m.ended.how === 'rejected';
      return `<section class="x-comp x-comp-end"><div class="x-cb"><div class="label">Outcome</div>
        <p>${rej ? `You rejected plan v${m.approval.plan_version} at ${K('known', hm(m.ended.at), 'approval.decided.at')}. The mission was cancelled; ${K('derived', 'nothing ran', 'Execution (none)', 'the mission has no execution')}.`
          : `${K('known', 'Cancelled at ' + hm(m.ended.at), 'mission.state_changed → CANCELLED')}${ev.reason ? ' · ' + K('known', ev.reason.startsWith('cancel: asked') ? 'you asked for it in a message' : 'on your request', 'mission.state_changed.reason: ' + ev.reason) : ''}. ${K('derived', A.stepsDone(m) + ' of ' + m.tasks.length + ' steps had finished', 'Task.state', 'count')}; nothing more runs.`}</p>
        ${rej ? `<p class="t2"><a href="${go({ drawer: 'approval' })}">What you rejected</a></p>` : ''}</div></section>`;
    }
    if (m.state === 'DONE') return `<section class="x-comp x-comp-ok"><div class="x-cb"><div class="label x-okk">Done</div>
      <p>${K('known', 'Finished at ' + hm(m.done_at), 'mission.done')}${A.checks(m).length ? ' · ' + K('known', A.passed(m) + ' of ' + A.checks(m).length + ' checks passed', 'Verification.checks') : ''}${A.ctx(m).branch ? ' · on ' + '<span class="mono">' + A.ctx(m).branch + '</span>' : ''}.</p></div></section>`;
    if (expired(m)) return `<section class="x-comp x-comp-end" id="ask"><div class="x-cb"><div class="label">Approval expired</div>
      <p>${K('known', 'Nobody decided plan v' + m.approval.plan_version + ' by ' + hm(m.approval.expires), 'approval.state_changed (ttl_elapsed)')}. ${K('derived', 'Nothing ran.', 'Execution (none)')}</p>
      <p class="t2">${NR('what Archeus does next', 'Core', 'not defined: the mission machine has no expiry edge')}</p></div></section>`;
    return '';
  };
  const component = (m, ph) => {
    if (m.estop) return stopComp(m);
    if (expired(m) || m.state === 'CANCELLED' || m.state === 'DONE') return outcome(m);
    if (m.state === 'APPROVAL_REQUIRED' || m.state === 'REVIEWING') return askComp(m, ph);
    if (m.state === 'BLOCKED' || m.state === 'FAILED') return badComp(m, ph);
    if (m.state === 'PLANNING') return `<section class="x-comp x-comp-plan"><div class="x-cb"><div class="label x-thinkk">Planning</div><p>${A.explain(m).next}</p></div></section>`;
    return '';
  };
  // after you approve: Core's recorded result, once it has recorded it
  const confirmLine = (m) => {
    const ap = approvedEv(m), st = A.evOf(m, 'execution.started').filter((e) => ap && e.at >= ap.at)[0];
    return Q.get('did') === 'approve' && ap ? `<p class="x-confirm">${I.check}<span>${K('known', 'Approved at ' + hm(ap.at), 'approval.decided')}${st ? '. Archeus started ' + K('known', '“' + m.tasks[0][0] + '”', 'Task.title') + ' at ' + K('known', hm(st.at), 'execution.started') : ''}.</span></p>` : '';
  };

  // activity: Core's events with their times; between them, what the agent's stream carries
  const STREAM = {
    'm-4c1e': [['ev', 'mission.created'], ['ev', 'approval.decided'], ['ev', 'execution.started'],
      ['say', 'Reproducing the failure: running test_date_rollover in a loop until it fails.'],
      ['tool', 'Bash', 'py -m pytest -q -k test_date_rollover --count 20'], ['res', true],
      ['say', 'It fails when a run crosses midnight UTC: the fixture reads the real clock.'],
      ['tool', 'Edit', 'tests/conftest.py'], ['res', false], ['ev', 'checkpoint.created'],
      ['say', 'The fixture now freezes the clock. Running the date suite 50 times.'],
      ['tool', 'Bash', 'py -m pytest -q -k test_date_rollover --count 50'], ['ev', 'execution.output'], ['live']],
    'm-c3e9': [['ev', 'mission.created'], ['ev', 'approval.decided'], ['ev', 'execution.started'],
      ['say', 'Writing the migration: invoices gets customer_id and an index on it.'],
      ['tool', 'Write', 'migrations/0042_invoices_customer.py'], ['res', false], ['ev', 'checkpoint.created'],
      ['say', 'The migration is written. Handing it to verification.'],
      ['ev', 'verification.started'], ['check', 0], ['check', 1], ['check', 2], ['ev', 'verification.failed'], ['ev', 'mission.blocked']],
  };
  const NOTE = { 'm-91d2': 'Add a smoke test after the deploy.' };
  const NOTE_SRC = 'approval.decided.reason (commands.request_changes requires one)';
  const activity = (m, ph) => {
    const evs = A.evOf(m).slice(), used = new Set();
    const take = (kind) => { const e = evs.find((x) => x.kind === kind && !used.has(x)); if (e) used.add(e); return e; };
    const row = (cls, t, who, txt) => `<li class="${cls}"><span class="num t3">${t}</span><span class="x-who">${who}</span><span class="x-tx">${txt}</span></li>`;
    const evRow = (e) => row('l-core', K('known', hm(e.at), 'event.at'), 'core', evText(e) + (e.decision === 'request_changes' && NOTE[m.id] ? ': “' + K('known', NOTE[m.id], NOTE_SRC) + '”' : ''));
    const live = m.live && !m.estop && !offline;
    const script = STREAM[m.id] || evs.map((e) => ['ev', e.kind]).concat(live ? [['live']] : []);
    const lines = script.map((s) => {
      if (s[0] === 'ev') { const e = take(s[1]); return e ? evRow(e) : ''; }
      if (s[0] === 'say') return row('l-say', '', 'agent', K('known', s[1], 'stream: assistant'));
      if (s[0] === 'tool') return row('l-tool', '', '$ ' + s[1].toLowerCase(), K('known', s[2], 'stream: tool.input'));
      if (s[0] === 'res') return row(s[1] ? 'l-err' : 'l-ok', '', '', s[1] ? K('known', '✗ error', 'stream: tool_result.is_error') : K('known', '✓ ok', 'stream: tool_result.is_error'));
      if (s[0] === 'check') { const c = A.checks(m)[s[1]]; return row(c[1] === 'failed' ? 'l-err' : 'l-ok', '', 'check', K('known', (c[1] === 'failed' ? '✗ ' : '✓ ') + c[0] + ' · exit ' + c[2], 'Verification.checks') + (c[1] === 'failed' ? ' ' + NR('output', 'DR-8', 'kept by Core, not readable here') : '')); }
      if (s[0] === 'live') return live ? row('l-live', '', '', '<span class="x-caret"></span>') : '';
      return '';
    }).concat(evs.filter((e) => !used.has(e)).map(evRow)).filter(Boolean);
    const cap = ph ? 4 : 8, all = Q.get('log') === 'all' || lines.length <= cap;
    if (!lines.length) return '';
    return `<section class="x-term" id="activity"><header><h2 class="label">${live ? '<span class="x-livedot"></span>' : ''}Activity</h2>
      <span class="t3 x-tsrc">${STREAM[m.id] ? 'Core’s events and the agent’s stream · tool output is not in the stream' : 'Core’s events'}</span></header>
      <ol>${(all ? lines : lines.slice(-cap)).join('')}</ol>${all ? '' : `<a class="x-tmore" href="${go({ log: 'all' })}#activity">Show all ${n('derived', lines.length, 'events + stream', 'count')} lines</a>`}</section>`;
  };

  // the decision record behind “Approved ✓” and behind a rejection (S-10)
  const drawer = (m) => {
    if (Q.get('drawer') !== 'approval') return '';
    const all = A.evOf(m, 'approval.decided'), last = all.slice(-1)[0];
    if (!last || !m.approval) return '';
    const d = A.decision(m), W = { approve: 'Approved', request_changes: 'Asked for changes', reject: 'Rejected' };
    const verb = { approve: 'approved', reject: 'rejected', request_changes: 'sent back' }[last.decision];
    return `<a class="x-scrim" href="${go({ drawer: null })}" aria-label="Close"></a><aside class="x-drawer" role="dialog" aria-label="Decision record">
      <div class="x-dtop"><span class="label">Decision record</span><a class="x-x" href="${go({ drawer: null })}" aria-label="Close">${I.cross}</a></div>
      <h2 class="x-ch">Plan v${m.approval.plan_version} ${verb}</h2>
      <p class="t2">${K('known', 'by you', 'approval.decided.actor')} · ${K('known', 'at ' + hm(last.at), 'approval.decided.at')} · ${T(m)}</p>
      <div class="x-cs"><h3 class="label">What was ${verb}</h3><p>${d.summary}</p><ol class="x-tasks">${m.tasks.map((t, i) => `<li><span class="num t3">${i + 1}</span>${K('known', t[0], 'Plan.tasks')}</li>`).join('')}</ol></div>
      <div class="x-cs"><h3 class="label">Why Archeus asked</h3><p>${d.why}</p><p class="mono t3">${d.rules.join('<br>')}</p></div>
      <div class="x-cs"><h3 class="label">Every answer on this mission</h3><ol class="x-events">${all.map((e) => `<li><span class="num t3">${K('known', hm(e.at), 'approval.decided.at')}</span><span><b>${K('known', W[e.decision], 'approval.decided.decision')}</b>${e.decision === 'request_changes' && NOTE[m.id] ? `<span class="x-note">“${K('known', NOTE[m.id], NOTE_SRC)}”</span>` : ''}</span></li>`).join('')}</ol></div>
      <div class="x-cs"><h3 class="label">Then</h3><p>${last.decision === 'approve' ? (A.evOf(m, 'execution.started').filter((e) => e.at >= last.at).slice(0, 1).map((e) => `${K('known', hm(e.at), 'execution.started')} · Archeus started ${K('known', '“' + m.tasks[0][0] + '”', 'Task.title')}`).join('') || 'Nothing has run yet.') : K('derived', 'The mission was cancelled. Nothing ran.', 'mission.state_changed → CANCELLED')}</p></div>
    </aside>`;
  };

  // the phone's answers, fixed at the bottom: Reject left, Changes centre, Approve right (S-9)
  const abar = (m) => {
    if (m.estop || !(m.state === 'APPROVAL_REQUIRED' || m.state === 'REVIEWING') || expired(m)) return '';
    const by = Object.fromEntries(A.decision(m).actions.map((a) => [a.key, a]));
    const b = (a, label, cls, href, dis) => (sending ? `<span class="btn${cls}${a.key === sending ? ' is-busy' : ''}" aria-disabled="true">${a.key === sending ? 'Approving…' : label}</span>`
      : `<a class="btn${cls}" href="${href}"${tip(a.then)}${dis || off}>${label}</a>`);
    const exp = m.approval ? `<span class="x-abexp num ${near(m) ? 'x-urgent' : 't3'}">${K('known', 'Expires ' + hm(m.approval.expires), 'Approval.expires_at')} · ${K('derived', 'in ' + (m.approval.expires - A.NOW) + ' min', 'Approval.expires_at', 'expires_at − now')}${stopped ? ' · ' + K('derived', 'approving waits until you resume', 'policy builtin:estop') : ''}</span>` : '';
    return `<div class="x-abar${m.approval ? '' : ' two'}">${exp}<div class="x-abtns">${m.approval
      ? b(by.reject, 'Reject', ' danger', go({ did: 'reject' })) + b(by.changes, 'Changes', '', '#') + b(by.approve, 'Approve', ' primary', go({ did: 'approve' }), stopped ? ' aria-disabled="true"' : '')
      : b(by.changes, 'Changes', '', '#') + b(by.accept, 'Accept', ' primary', go({ did: 'accept' }))}</div></div>`;
  };

  const missionDesk = (m) => {
    if (loading) return desk(`<a class="x-back" href="${backOf()[1]}">${I.back}${backOf()[0]}</a>` + skeleton('mission'));
    return desk(`<div class="x-mp">${mhead(m)}<section class="x-linecard">${line(m, 'full')}</section>${confirmLine(m)}${component(m)}
      <div class="x-two"><div class="x-colm">${nowSec(m)}${planSec(m)}${activity(m)}</div><aside class="x-cols">${verifiedSec(m)}${decisionsSec(m)}${ctxSec(m)}</aside></div></div>`, drawer(m));
  };
  const missionPhone = (m) => {
    if (loading) return pushed(backOf(), skeleton('mission'));
    const bar = abar(m);
    return pushed(backOf(), `${mhead(m, true)}<section class="x-linecard">${line(m, 'full')}</section>${confirmLine(m)}${component(m, true)}
      ${nowSec(m)}${verifiedSec(m)}${planSec(m)}${decisionsSec(m)}${ctxSec(m)}${activity(m, true)}`, bar + drawer(m), bar ? 'has-abar' : '');
  };

  // ── Tell: a centred dialog on the desktop, its own page on the phone; then the work it made (journey 7) ──
  const TELL_M = 'm-6d4c';
  const tellBody = () => {
    const st = Q.get('tell');
    if (st === 'sent') return `<div class="x-wait"><span class="x-dots"><i></i><i></i><i></i></span>${K('known', 'Archeus is reading it…', 'message.created; waiting for intent.created')}</div>`;
    if (st === 'done') {
      const m = A.byId[TELL_M];
      return `<p class="x-told t2">“${K('known', 'Draft an ADR for the P21 activity record', 'message.created (your message)')}”</p>
        <p class="x-tres">${I.check}<span>Archeus made it a mission</span></p>
        ${m ? `<a class="x-mi x-mi-tell" href="${open(m)}">${mono(m.project_id, 'x-mi-mono')}<span class="x-mi1"><span class="x-mt">${T(m)}</span><span class="x-mw">${pName(m.project_id)}</span></span><span class="x-mi2">${line(m, 'mid')}${phaseWord(m)}</span></a>` : ''}
        <div class="x-fixrow"><a class="btn primary" href="${m ? open(m) : '#'}">Open the mission</a><a class="btn quiet" href="${go({ tell: null })}">Close</a></div>`;
    }
    return `<textarea rows="4" placeholder="What should Archeus do? For example: fix the flaky date test in archeus."${offline ? ' disabled' : ''}></textarea>
      ${stopped ? `<p class="x-refused">${K('derived', 'Archeus is stopped: a mission you start now is blocked until you resume and unblock it.', 'P20 gate item 5: missions created while stopped stay BLOCKED')}</p>` : ''}
      <div class="x-fixrow"><a class="btn primary" href="${go({ tell: 'sent' })}"${off}>Send</a><a class="btn quiet" href="${go({ tell: null })}">Cancel</a></div>`;
  };
  function tellModal() {
    if (!Q.get('tell') || isPhone) return '';
    return `<div class="x-modal-wrap"><a class="x-mscrim" href="${go({ tell: null })}" aria-label="Close"></a><div class="x-modal" role="dialog" aria-modal="true" aria-label="Tell Archeus">
      <div class="x-dtop"><h2 class="x-ch">Tell Archeus what to do</h2><a class="x-x" href="${go({ tell: null })}" aria-label="Close">${I.cross}</a></div>${tellBody()}</div></div>`;
  }
  const tellPhone = () => `<div class="x-phone x-pushed">${pbar(backOf())}<main class="x-pmain"><h1 class="x-phl">Tell Archeus what to do</h1>${tellBody()}</main></div>`;

  // ── projects ──
  const projChips = (pid) => {
    const ms = A.missions.filter((m) => m.project_id === pid);
    const c = (f, w, tone) => { const k = ms.filter(f).length; return k ? `<span class="chip tone-${tone}">${n('derived', k + ' ' + w, 'Mission.project_id + Mission.state', 'count')}</span>` : ''; };
    return c((m) => waiting.includes(m), 'waiting', 'attention') + c((m) => working.includes(m), 'running', 'active') + c((m) => queued.includes(m), 'queued', 'ended') + c((m) => trouble.includes(m) || m.estop, 'blocked or failed', 'blocked') + c((m) => m.state === 'DONE', 'done today', 'done');
  };
  const projectsBody = () => (PIDS.length ? `<div class="x-prs">${PIDS.map((id) => {
    const P = A.projects[id], ms = openOf(id), lead = ms.find((m) => waiting.includes(m)) || ms.find((m) => trouble.includes(m)) || ms.find((m) => running.includes(m));
    return `<a class="x-pr x-card" href="${projPage(id)}"><span class="x-prh">${mono(id, 'x-mono-l')}<span><span class="x-prn">${K('known', P.name, 'Project.name')}</span><span class="x-where mono">${(P.repos || []).map((r) => K('known', r.path, 'Repository.path')).join(' · ')}</span></span></span>
      <span class="x-prc">${projChips(id) || `<span class="t3">${K('derived', 'Nothing open', 'Mission.project_id', 'no open missions')}</span>`}</span>
      ${lead ? `<span class="x-prl"><span class="t3">${waiting.includes(lead) ? 'Waiting' : trouble.includes(lead) ? 'Blocked' : 'Now'}:</span> ${T(lead)}</span>` : ''}</a>`;
  }).join('')}</div>` : firstRun());
  const token = (m) => `<a class="x-tok tone-${toneOf(m)}" href="${open(m)}"><span class="chip">${K('known', word(m), 'Mission.state')}</span><span class="x-tt">${T(m)}</span>
      ${m.tasks.length ? `<span class="steps">${m.tasks.map((t) => `<i class="${{ SUCCEEDED: 'ok', RUNNING: m.estop ? 'stop' : 'now', FAILED: 'bad' }[t[1]] || ''}"></i>`).join('')}</span>` : ''}</a>`;
  const ASKS = [false, false, true, false, false, true];
  const timeboard = (pid) => {
    const ms = A.missions.filter((m) => m.project_id === pid && phaseOf(m) < 6 && m.state !== 'CANCELLED');
    if (!ms.length) return `<p class="x-empty">Nothing is open in this project.</p>`;
    return `<div class="x-board">${A.PHASES.map((ph, i) => {
      const col = ms.filter((m) => phaseOf(m) === i), cap = 3;
      return `<div class="x-bcol${col.length ? '' : ' empty'}"><div class="x-bch"><b>${ph}</b>${ASKS[i] ? '<span class="x-asks">asks you</span>' : ''}<span class="num t3">${col.length || ''}</span></div>${col.slice(0, cap).map(token).join('')}${col.length > cap ? `<a class="x-more" href="${to({ v: 'missions', f: pid })}">${n('derived', col.length - cap + ' more', 'count')}</a>` : ''}</div>`;
    }).join('')}</div>`;
  };
  const projectBody = (pid, ph) => {
    const P = A.projects[pid], ms = A.missions.filter((m) => m.project_id === pid);
    const evs = A.events.filter((e) => (A.byId[e.mission_id] || {}).project_id === pid).sort((a, b) => b.at - a.at || b.seq - a.seq).slice(0, 8);
    const repos = `<ul class="x-repos">${P.repos.map((r) => `<li><span class="mono">${K('known', r.path, 'Repository.path')}</span><span class="t3">${K('known', r.kind, 'Repository.kind')} · ${K('known', r.default_branch, 'Repository.default_branch')} · ${K('known', r.last_revision, 'Repository.last_revision')}</span></li>`).join('')}</ul>`;
    const details = zone('Details', '', `<div class="x-pad">${dl([['Repositories', repos], ['Root', K('known', P.root_paths[0], 'Project.root_paths')], ['Missions', n('derived', ms.length + ' today', 'Mission.project_id', 'count')], ['Remote', NR('remote', 'DR-2')]])}</div>`);
    const ideas = zone('Ideas', ideasOf(pid).length ? n('derived', ideasOf(pid).length, 'Idea.project_id', 'count') : '',
      `${ideasOf(pid).map(ideaRow).join('') || '<p class="x-empty">No ideas yet.</p>'}${CORE_ONLY ? '' : `<div class="x-pad"><a class="btn" href="${go({ compose: pid })}">${I.tell}New idea</a></div>`}`);
    const act = zone('Activity', '', evs.length ? evRows(evs) : '<p class="x-empty">Nothing yet today.</p>');
    const dn = ms.filter((m) => m.state === 'DONE');
    return `${ph ? '' : `<a class="x-back" href="${backOf()[1]}">${I.back}${backOf()[0]}</a>`}
      <div class="x-phead">${mono(pid, 'x-mono-xl')}<div><div class="label">Project</div><h1 class="x-headline">${K('known', P.name, 'Project.name')}</h1><div class="x-prc">${projChips(pid)}</div></div></div>
      <section class="x-boardwrap"><h2 class="label">Now · each open mission where it stands</h2>${timeboard(pid)}</section>
      <div class="x-grid x-grid-p"><div class="x-col">${zone('Done today', dn.length ? n('derived', dn.length, 'Mission.state = DONE', 'count') : '', doneRows(dn))}${act}</div><div class="x-col">${ideas}${details}</div></div>`;
  };

  // ── ideas ──
  const ideaState = (i) => (i.mission && (A.byId[i.mission] || {}).state === 'DONE' ? 'COMPLETED' : i.state);
  const IW = { CAPTURED: ['Captured', ''], EXPLORED: ['Researched', 'tone-thinking'], IMPLEMENTING: ['In a mission', 'tone-active'], PARKED: ['Parked', 'tone-ended'], COMPLETED: ['Done', 'tone-done'] };
  const canStart = (st) => st === 'CAPTURED' || st === 'EXPLORED' || st === 'PARKED';
  const START = K('derived', 'Archeus makes it a mission and starts planning it.', 'conversation.py _promote: Idea → IMPLEMENTING; Mission origin idea (no HTTP route: through the conversation)');
  const startBtn = (cls) => `<a class="btn primary${cls}" href="#"${tip(START)}${off}>Start</a>`;
  const changeBtn = (i, cls) => (CORE_ONLY ? '' : `<a class="btn${cls}" href="${go({ compose: 'idea:' + i.id })}"${off}>Change</a>`);
  const ideaPage = (i) => to({ v: 'idea', iid: i.id, from: here() });
  const ideaMeta = (i, st) => `<span class="x-im"><span class="chip ${IW[st][1]}">${K('known', IW[st][0], 'Idea.state')}</span><span class="num t3">${K('known', hm(i.at), 'idea.created')}</span></span>`;
  const ideaRow = (i) => {
    const st = ideaState(i), m = i.mission && A.byId[i.mission];
    return `<div class="x-idea"><a class="x-it" href="${ideaPage(i)}"><span class="x-itt">${K('known', i.title, 'Idea.title')}</span>${ideaMeta(i, st)}</a>
      ${m ? `<a class="x-ilink" href="${open(m)}">${T(m)}${I.chev}</a>` : canStart(st) ? `<div class="x-iacts">${changeBtn(i, ' sm')}${startBtn(' sm')}</div>` : ''}</div>`;
  };
  const ideasOf = (pid) => IDEAS.filter((i) => i.project_id === pid);
  const IDEA_CAP = 3;
  const ideaGroup = (pid) => {
    const list = ideasOf(pid), all = Q.get('f') === (pid || 'new');
    return `<section class="x-ig"><header class="x-igh">${pid ? mono(pid) : ''}<span class="x-ign">${pid ? K('known', A.projects[pid].name, 'Project.name') : 'New projects'}</span><span class="num t3">${list.length || ''}</span>
      ${pid && !CORE_ONLY ? `<a class="btn sm x-plus" href="${go({ compose: pid })}" aria-label="New idea for ${A.esc(A.projects[pid].name)}"${off}>${I.tell}Idea</a>` : ''}</header>
      ${(all ? list : list.slice(0, IDEA_CAP)).map(ideaRow).join('') || '<p class="x-empty">No ideas yet.</p>'}${!all && list.length > IDEA_CAP ? `<a class="x-more" href="${go({ f: pid || 'new' })}">${n('derived', list.length - IDEA_CAP + ' more', 'count')} ideas${I.chev}</a>` : ''}</section>`;
  };
  const ideasBody = () => {
    const hero = CORE_ONLY
      ? `<div class="x-ihero x-ihero-core"><p class="t2">Ideas are captured when you tell Archeus one.</p><a class="x-tellbig" href="${go(isPhone ? { v: 'tell' } : { tell: '1' })}">${I.tell}<span>Tell Archeus an idea</span></a></div>`
      : `<div class="x-ihero"><a class="x-big" href="${go({ compose: 'new' })}">${PLACES[2][2]}<span>New project idea</span></a><a class="x-big x-go" href="${go({ compose: 'start' })}">${I.tell}<span>Start a new project</span></a></div>`;
    return hero + `<div class="x-igs">${PIDS.map(ideaGroup).join('')}${ideaGroup(null)}</div>`;
  };
  const composer = () => {
    const c = Q.get('compose');
    if (!c) return '';
    const idea = c.startsWith('idea:') && IDEAS.find((i) => i.id === c.slice(5)), P = A.projects[c];
    const title = idea ? 'Change the idea' : c === 'new' ? 'New project idea' : c === 'start' ? 'Start a new project' : 'New idea';
    const pid = idea ? idea.project_id : P ? c : null;
    const gaps = [idea ? gap('DR-10', 'changing an idea', 'editing') : gap('DR-10', 'capturing an idea directly, not from a Tell message', 'direct capture'),
      !idea && c !== 'start' ? gap('DR-10', 'Archeus researching the idea: branch, plan', 'research') : ''].filter(Boolean);
    return `<div class="x-modal-wrap"><a class="x-mscrim" href="${go({ compose: null })}" aria-label="Close"></a>
      <div class="x-modal" role="dialog" aria-modal="true" aria-label="${title}">
        <div class="x-dtop"><h2 class="x-ch">${title}</h2><a class="x-x" href="${go({ compose: null })}" aria-label="Close">${I.cross}</a></div>
        ${pid ? `<p class="x-wt t2">${mono(pid)}${K('known', A.projects[pid].name, 'Project.name')}</p>` : '<p class="t2">A new project</p>'}
        <textarea rows="5" placeholder="What should Archeus build?">${idea ? A.esc(idea.text) : ''}</textarea>
        <div class="x-fixrow"><a class="btn primary" href="#">${idea ? 'Save' : c === 'start' ? 'Save and start' : 'Save idea'}</a><a class="btn quiet" href="${go({ compose: null })}">Cancel</a></div>
        <p class="x-gaps">${gaps.join('')}</p></div></div>`;
  };
  const icoSearch = '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><circle cx="11" cy="11" r="6" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M15.5 15.5 20 20" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
  const KIND = { inspection: 'inspect', code_change: 'code', verification: 'verify', research: 'research', document: 'write-up' };
  const TIERS = ['small', 'mid', 'large'];
  const sizeOf = (ts) => { const sc = ts.reduce((s, t) => s + { small: 1, mid: 2, large: 4 }[t[2]] * t[4], 0); return [sc <= 6 ? 'low' : sc <= 20 ? 'medium' : 'high', sc]; };
  const ideaBody = (i, ph) => {
    const st = ideaState(i), R = i.research, m = i.mission && A.byId[i.mission];
    const proj = i.project_id ? `<span class="x-wt">${mono(i.project_id)}${K('known', A.projects[i.project_id].name, 'Project.name')}</span>` : 'New project';
    const acts = m ? `<a class="btn" href="${open(m)}">Open the mission</a>` : canStart(st) ? changeBtn(i, '') + startBtn('') : '';
    const head = `${ph ? '' : `<a class="x-back" href="${backOf()[1]}">${I.back}${backOf()[0]}</a>`}
      <div class="x-ihead"><div><div class="label">Idea</div><h1 class="x-headline">${K('known', i.title, 'Idea.title')}</h1><div class="x-ihm">${proj}${ideaMeta(i, st)}</div></div>
        ${acts ? `<div class="x-iacts">${acts}</div>` : ''}</div>
      <p class="x-quote">${K('known', i.text, 'Idea.text')}</p>`;
    const researchTag = gap('DR-10', 'Archeus researching an idea: plan, branch, tools, size', 'research');
    if (m) return `${head}<section class="x-rs"><header class="x-rsh"><h2 class="label">Its mission</h2></header>${missionRow(m)}</section>`;
    if (CORE_ONLY) return `${head}<section class="x-rs x-empty"><p class="t2">${K('derived', 'Start makes it a mission; Archeus plans it there.', 'conversation.py _promote')}</p></section>`;
    if (!R) {
      const body = Q.get('research') ? `<div class="x-wait"><span class="x-dots"><i></i><i></i><i></i></span>Researching the idea in ${proj}…</div>`
        : `<a class="btn primary x-rbtn" href="${go({ research: '1' })}"${tip(K('derived', 'Archeus reads the project and drafts a plan for this idea. Nothing changes in the project.', 'DR-10: Idea CAPTURED → explore → EXPLORED'))}${off}>${icoSearch}Research</a><span class="t3">No plan yet.</span>`;
      return `${head}<section class="x-rs x-rsempty">${body}${researchTag}</section>`;
    }
    const [band, score] = sizeOf(R.tasks), tier = TIERS[Math.max(...R.tasks.map((t) => TIERS.indexOf(t[2])))];
    const asks = R.tasks.map((t, k) => (t[5].length ? k + 1 : 0)).filter(Boolean);
    const rev = Q.get('rev') === '1' && R.prev;
    const plan = `<section class="x-rs"><header class="x-rsh"><h2 class="label">Plan · v${R.version}</h2><span class="num t3">${SMP('researched ' + hm(R.at), 'idea.explored')}</span>${researchTag}
        ${R.prev ? `<a class="x-revl" href="${go({ rev: rev ? null : '1' })}">${rev ? 'Hide' : 'What changed from v' + R.prev.version}</a>` : ''}<a class="btn sm" href="${go({ research: '1' })}"${off}>${icoSearch}Research again</a></header>
      ${rev ? `<div class="x-rev"><div><span class="label">v${R.prev.version}</span><p class="t2"><s>${SMP(R.prev.summary, 'Plan v' + R.prev.version + '.summary')}</s></p></div><div><span class="label">v${R.version}</span><p>${SMP(R.summary, 'Plan.summary')}</p></div><p class="t3">${SMP('Changed: task ' + R.prev.changed.map((k) => k + 1).join(', ') + ', after your comment at ' + hm(R.comments[0][1]), 'plan.created v' + R.version + ' supersedes v' + R.prev.version)}</p></div>`
        : `<p class="x-sum">${SMP(R.summary, 'Plan.summary')}</p>`}
      <ol class="x-plan">${R.tasks.map((t, k) => `<li class="${rev && R.prev.changed.includes(k) ? 'is-changed' : ''}"><span class="num t3">${k + 1}</span><span class="x-pt">${SMP(t[0], 'Task.title')}</span>
        <span class="x-tm">${[SMP(KIND[t[1]], 'Task.kind'), SMP(t[2], 'Task.min_model_tier'), SMP(t[3] === 'worktree' ? 'worktree' : 'in place', 'Task.workspace_mode'), SMP('size ' + t[4], 'Task.estimate (1–5)')]
          .concat(t[5].length ? [SMP('asks you', 'Task.action_classes: ' + t[5].join(', '))] : []).join(' · ')}</span></li>`).join('')}</ol>
      ${R.question ? `<div class="x-q"><h3 class="label">Open question</h3><p>${SMP(R.question, 'a question research left open')}</p></div>` : ''}</section>`;
    const thread = `<section class="x-rs x-cm"><header class="x-rsh"><h2 class="label">Comments</h2>${gap('DR-10', 'comments that revise an idea’s plan', 'comments')}</header>
      <ol class="x-thread">${R.comments.map(([who, t, txt]) => `<li class="x-c x-c-${who}"><span class="x-cw">${who === 'you' ? 'You' : 'Archeus'}</span><span class="num t3">${SMP(hm(t), 'comment.at')}</span><p>${SMP(txt, who === 'you' ? 'your comment' : 'the revision')}</p></li>`).join('')}</ol>
      <div class="x-cbox"><textarea rows="2" placeholder="Comment on the plan…"${offline ? ' disabled' : ''}></textarea><a class="btn primary" href="#"${off}>Send</a></div></section>`;
    const glance = zone('What it will take', '', `<div class="x-pad">${dl([
      ['Size', SMP(band, 'planning.validate.cost_band over the plan: score ' + score)],
      ['Time', K('derived', 'not estimated', 'domain-model §7.2: Core sizes work in bands, never in hours')],
      ['Tools', SMP(R.capabilities.join(' · '), 'Task.capabilities_required')],
      ['Models', SMP(tier + ' at most', 'Task.min_model_tier')],
      ['Agents', K('derived', 'picked per task when it starts', 'RouteDecision: harness, account and model are chosen at dispatch')],
      ['Needs you', asks.length ? SMP('before writing files: steps ' + asks.join(', '), 'Task.action_classes write × policy profile:standard@2:USER:write (ASK)') : 'never'],
      ['Branch', K('derived', 'its own, when it starts', 'Mission.integration_branch is made with the mission')]])}</div>`);
    return `${head}<div class="x-grid"><div class="x-col">${plan}${thread}</div><div class="x-col">${glance}</div></div>`;
  };

  // ── Control: one place for how Archeus is allowed to work, grouped by what you came to do ──
  const POL = FX.POLICY || '';
  const controlBody = (ph) => {
    const safetyCard = `<section class="x-zone x-ctl-safe${stopped ? ' x-zstop' : ''}" id="safety"><header class="x-zh"><h2 class="label">Safety</h2></header><div class="x-pad">
      <p class="x-ctls">${dot(safetyWords().dot)}<b>${stopped ? 'Emergency stop' : safetyWords().b}</b></p>
      <p class="t2">${stopped ? STOP_TEXT() : offline ? 'This page cannot stop anything while Core cannot be reached.' : K('known', 'Accepts new work', A.safety.src)}</p>
      <div class="x-ctla">${estopBtn()}</div>
      <ul class="x-facts">
        <li>${K('derived', 'A stop ends every running mission at once and blocks it.', 'executions.py:410-433')}</li>
        <li>${K('derived', 'Nothing runs until you resume. A mission started meanwhile is blocked.', 'policy builtin:estop; P20 gate item 5')}</li>
        <li>${K('derived', 'Resuming does not restart them: unblock each one.', 'executions.py:436-441: re-arm does not touch missions')}</li>
        <li>${K('derived', 'With Core unreachable, stop from the computer running Archeus: the tray’s Emergency stop, or archeus estop.', 'P20 gate item 1, item 15')}</li>
        <li>${isPhone ? K('derived', 'Resuming from this phone will ask for your PIN.', 'P20 D10 (approved for paired devices)') + ' ' + gap('P20 V2-3', 'the PIN step-up on re-arm is approved but not built', 'not built') : K('derived', 'Resuming from this computer needs no PIN.', 'P20 D10: the PIN step-up applies to paired devices; a local client passes by being local')}</li></ul></div></section>`;
    const sec = (id, label, rows, note) => `<section class="x-zone" id="${id}"><header class="x-zh"><h2 class="label">${label}</h2></header><div class="x-pad">${rows ? dl(rows) : ''}${note ? `<p class="t3 x-cnote">${note}</p>` : ''}</div></section>`;
    const prof = /profile:(\w+)@(\d+)/.exec(POL);
    const cards = [
      sec('autonomy', 'Autonomy', [['Profile', prof ? K('known', prof[1] + ', version ' + prof[2], 'PolicyRule profile:' + prof[1] + '@' + prof[2]) : NR('profile', 'Core')],
        ['Asks before', K('derived', 'every deploy; writing outside a worktree', 'the ASK rules of the profile, in words')], ['Locked', K('known', 'deploy to production', 'builtin:floor:deploy-prod (locked)')]], 'Rules, and “what would happen if…”, live here.'),
      sec('agents', 'Agents and accounts', [['Runs on', K('derived', 'this computer', 'ExecutionNode: V1 runs only on the local node')]], 'Harnesses, accounts and their health, what each execution may load (read only), and the recent routing decisions.'),
      sec('automations', 'Automations', null, 'What starts missions on its own, and the last runs of each.'),
      sec('devices', 'Devices', [['This one', K('known', isPhone ? 'this phone' : 'this computer', 'Device.name')]], 'Paired phones and clients; pairing a new one needs an admin device.'),
      sec('appearance', 'Appearance', [['Motion', K('known', 'follows the system', 'Appearance.motion (kept by this client)')]], 'Theme, contrast and motion, kept by this device only.'),
      sec('about', 'About', [['Core', offline ? NR('Core', 'connection', 'cannot be reached') : K('known', 'connected', 'connection.state')]], null),
    ];
    return ph ? safetyCard + `<div class="x-ctlist">${cards.join('')}</div>` : `<div class="x-ctl">${safetyCard}<div class="x-ctlgrid">${cards.join('')}</div></div>`;
  };
  // resume from a paired phone: D10's PIN step-up (approved, not built), and nothing counts until Core answers
  const resumePhone = () => pushed(['Overview', place('home')], `<h1 class="x-phl">Resume work</h1>
    <p class="t2">${STOP_TEXT()}</p>
    <ul class="x-facts"><li>${K('derived', 'New work can start again.', 'POST /v1/rearm')}</li><li>${K('derived', 'The ' + halted.length + ' stopped missions stay blocked until you unblock each one.', 'executions.py:436-441')}</li></ul>
    <label class="label" for="pin">Your PIN</label><input id="pin" class="x-pin" inputmode="numeric" autocomplete="one-time-code" placeholder="••••">
    <p class="x-gaps">${gap('P20 V2-3', 'the PIN step-up on re-arm from a paired device (D10) is approved but not built', 'PIN step-up · not built')}</p>
    <div class="x-fixrow"><a class="btn primary" href="${go({ v: 'home', resume: 'sending' })}">Resume work</a><a class="btn quiet" href="${place('home')}">Cancel</a></div>`);

  // ── places ──
  const pageHead = (t, sub) => `<div class="x-head"><h1 class="x-headline">${t}</h1>${sub ? `<p class="t2">${sub}</p>` : ''}</div>`;
  const placeDesk = (v) => {
    if (loading) return desk(skeleton());
    const H = { missions: ['Missions', missionsBody()], projects: ['Projects', projectsBody()], control: ['Control', controlBody()], ideas: ['Ideas', ideasBody()] }[v];
    return desk(pageHead(H[0]) + H[1], v === 'ideas' ? composer() : '');
  };
  const placePhone = (v) => {
    if (loading) return phone(skeleton());
    const body = { missions: missionsBody, projects: projectsBody, control: () => controlBody(true), ideas: ideasBody }[v]();
    return phone(`<h1 class="x-phl x-ptitle">${{ missions: 'Missions', ideas: 'Ideas', projects: 'Projects', control: 'Control' }[v]}</h1>${body}`, v === 'ideas' ? composer() : '');
  };

  // ── motion: the light along the mission line (proposal, reassessment LV2-X.2 §M) ──
  // Only a Core-recorded phase change emits light. Focus surface (the mission page): a head travels the segment in
  // 600 ms linear, a ring lands on the node in 240 ms, the segment stays lit (residue). Peripheral lines (rows,
  // tiles): no head, the segment fills in 160 ms per station. One travel at a time; transform and opacity only;
  // reduced motion renders the end state; the stop cancels any travel (the safety frame never shares the stage).
  const travel = (lineEl, from, toI) => {
    const seg = lineEl.querySelector(`.x-sg[data-i="${toI}"]`), node = lineEl.querySelector(`.x-nd[data-i="${toI}"]`);
    if (!seg || !node) return [];
    const box = lineEl.getBoundingClientRect(), r = seg.getBoundingClientRect();
    const head = document.createElement('i'); head.className = 'x-head-light';
    head.style.left = (r.left - box.left) + 'px'; head.style.top = (r.top - box.top + r.height / 2) + 'px';
    lineEl.appendChild(head);
    const ring = document.createElement('i'); ring.className = 'x-ring';
    node.appendChild(ring);
    const fill = seg.querySelector('.x-fill'), core = node.querySelector('.x-core');
    const L = r.width;
    return [
      head.animate([{ transform: 'translateX(0)', opacity: 0 }, { opacity: 0.9, offset: 0.08 }, { transform: `translateX(${L}px)`, opacity: 0.9, offset: 0.97 }, { transform: `translateX(${L}px)`, opacity: 0 }], { duration: 600, easing: 'linear', fill: 'both' }),
      fill.animate([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: 600, easing: 'linear', fill: 'both' }),
      core ? core.animate([{ opacity: 0 }, { opacity: 0, offset: 0.7 }, { opacity: 1 }], { duration: 840, easing: 'linear', fill: 'both' }) : null,
      ring.animate([{ transform: 'scale(.6)', opacity: 0 }, { transform: 'scale(.6)', opacity: 0, offset: 0.714 }, { transform: 'scale(.6)', opacity: 0.85, offset: 0.72 }, { transform: 'scale(1)', opacity: 0 }], { duration: 840, easing: 'cubic-bezier(.22,.8,.18,1)', fill: 'both' }),
    ].filter(Boolean);
  };
  const progressRow = (lineEl, toI) => {
    const fill = lineEl.querySelector(`.x-sg[data-i="${toI}"] .x-fill`);
    return fill ? [fill.animate([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: 160, easing: 'cubic-bezier(.22,.8,.18,1)', fill: 'both' })] : [];
  };

  window.DIR = window.DIR || {};
  window.DIR.e2 = {
    render(v, ph) {
      isPhone = ph;
      const m = A.byId[Q.get('id')];
      if (m && (v === 'mission' || v === 'live' || v === 'decide')) return ph ? missionPhone(m) : missionDesk(m);
      if (v === 'tell' && ph) return tellPhone();
      if (v === 'resume' && ph) return resumePhone();
      const idea = v === 'idea' && IDEAS.find((i) => i.id === Q.get('iid'));
      if (idea) return ph ? pushed(backOf(), ideaBody(idea, true), composer()) : desk(ideaBody(idea), composer());
      if (v === 'project' && A.projects[Q.get('pid')]) return ph ? pushed(backOf(), projectBody(Q.get('pid'), true), composer()) : desk(projectBody(Q.get('pid')), composer());
      if (['missions', 'projects', 'control', 'ideas'].includes(v)) return ph ? placePhone(v) : placeDesk(v);
      return ph ? homePhone() : homeDesk();
    },
    after() {
      document.documentElement.classList.toggle('x-is-off', offline);
      if (SHOT && innerWidth < 600 && Q.get('pin')) { const t = document.querySelector(Q.get('pin')); if (t) t.scrollIntoView({ block: 'start' }); }
      const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
      // the light: after an approve, Approve → Run on the page you are looking at
      const anims = [];
      if (!reduce && Q.get('did') === 'approve' && !stopped) {
        const full = document.querySelector('.x-line-full');
        if (full) anims.push(...travel(full, 2, 3));
      }
      if (!reduce && Q.get('demo') === 'row') document.querySelectorAll('.x-line-mid').forEach((l, k) => { if (k === 0) anims.push(...progressRow(l, 3)); });
      // a capture freezes the motion at ?t= ms (the filmstrip), or shows its end state
      if (SHOT) for (const a of anims) { a.pause(); a.currentTime = Q.get('t') != null ? +Q.get('t') : 1000; }
      // the primed stop counts down its lapse (transform only)
      if (primed && !SHOT && !reduce) { const b = document.querySelector('.estop[data-state="primed"]'); if (b) { const c = document.createElement('i'); c.className = 'x-count'; b.appendChild(c); c.animate([{ transform: 'scaleX(.66)' }, { transform: 'scaleX(0)' }], { duration: A.estop.left * 1000, easing: 'linear', fill: 'both' }); } }
      // the explanation arrives as the agent writes it; a capture shows it whole, reduced motion at once
      const el = document.querySelector('.x-typed');
      if (SHOT) { const t = document.getElementById('answer'); if (t && innerWidth < 600) t.scrollIntoView({ block: 'center' }); }
      if (el && !SHOT && !Q.get('wait')) {
        const text = el.dataset.text, wait = document.querySelector('.x-answer .x-wait');
        if (reduce) { el.textContent = text; return; }
        wait.hidden = false;
        setTimeout(() => { wait.hidden = true; let i = 0; const tick = () => { el.textContent = text.slice(0, ++i); if (i < text.length) setTimeout(tick, 18); }; tick(); }, 1400);
      }
    },
  };
})();
