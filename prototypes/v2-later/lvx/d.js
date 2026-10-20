/* LV2-X direction D — "Synthesis", built from the owner's review of A, B and C (reassessment §17).
 * A's frame and places (Overview · Missions · Projects · Control) and A's overview order; B's mission
 * line as the one progress element everywhere, with A's green ticks; one mission page on which every
 * state happens: a decision or a problem appears as a component under the line and goes away when it
 * is answered. Prototype only. */
(function () {
  'use strict';
  const A = window.AX, I = A.icon, K = A.K, NR = A.NR, hm = A.hm, go = A.go, Q = A.Q;
  const stopped = A.estop.state === 'stopped', primed = A.estop.state === 'primed';
  const halted = A.problems.filter((m) => m.estop);
  const trouble = A.problems.filter((m) => !m.estop);
  const n = (k, v, src, rule) => K(k, String(v), src, rule);
  const plural = (c, one, many) => (c === 1 ? one : many);
  const T = (m) => K('known', m.title, 'Mission.title');
  const open = (m) => go({ v: 'mission', id: m.id, did: null, ask: null, drawer: null, wait: null });
  const place = (v) => go({ v, id: null, did: null, ask: null, drawer: null, wait: null });
  const icoProj = '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><path d="M3 6.5h6.5l2 2H21V19H3Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  const toneOf = (m) => (m.estop ? 'stop' : A.tone(m));
  const chip = (m) => `<span class="chip tone-${toneOf(m)}">${K('known', A.word(m), 'Mission.state')}</span>`;

  // ── the mission line: the six phases of states.py; done = green tick (A), current lit, failed = red cross ──
  const approvedEv = (m) => A.evOf(m, 'approval.decided').filter((e) => e.decision === 'approve').slice(-1)[0];
  const nodeState = (m, i) => {
    const p = A.phase(m);
    if (p === 6 || i < p) return 'past';
    if (i > p) return 'future';
    if (m.estop) return 'stop';
    return m.state === 'BLOCKED' || m.state === 'FAILED' ? 'bad' : 'now tone-' + A.tone(m);
  };
  const caption = (m) => {
    const x = A.explain(m);
    if (m.estop) return K('known', 'stopped at ' + hm(A.STOP_AT), 'core.estopped');
    if (m.state === 'APPROVAL_REQUIRED') return 'waiting for you · ' + K('known', 'expires ' + hm(m.approval.expires), 'Approval.expires_at');
    if (m.state === 'REVIEWING') return 'waiting for you';
    if (m.state === 'EXECUTING' || m.state === 'VERIFYING') return K('known', 'step ' + m.live.step + ' of ' + m.live.of, 'Task (plan order)') + ' · ' + x.elapsed;
    if (m.state === 'BLOCKED') return K('known', 'check failed', 'verification.failed');
    if (m.state === 'FAILED') return K('known', 'failed ' + hm(m.failed_at), 'execution.failed');
    if (m.state === 'PLANNING') return 'planning';
    return '';
  };
  const approvedLink = (m) => {
    const ap = approvedEv(m);
    return ap ? `<a class="cap ok" href="${go({ drawer: 'approval' })}">${K('known', 'Approved ' + hm(ap.at), 'approval.decided')}${I.check}</a>` : '';
  };
  const mline = (m, size) => {
    const p = A.phase(m);
    const parts = A.PHASES.map((ph, i) => {
      const s = nodeState(m, i), now = s !== 'past' && s !== 'future';
      const ic = size !== 'full' ? '' : s === 'past' ? I.check : s === 'bad' ? I.cross : s === 'stop' ? '<i class="sq"></i>' : '';
      const lab = size !== 'full' ? '' : `<span class="ph">${ph}</span>${now ? `<span class="cap">${caption(m)}</span>` : i === 2 && s === 'past' ? approvedLink(m) : ''}`;
      return (i ? `<span class="sg ${i <= p ? 'past' : 'future'}"></span>` : '') + `<span class="nd ${s}">${ic}${lab}</span>`;
    });
    const cap = size === 'full' && p < 6 ? `<p class="lcap"><b>${A.PHASES[p]}</b> · ${caption(m)}${p > 2 ? ' ' + approvedLink(m) : ''}</p>` : '';
    return `<div class="ml ml-${size}" role="img" aria-label="${p === 6 ? 'Done' : A.PHASES[p] + ' phase'}">${parts.join('')}</div>${cap}`;
  };

  // ── frame (A) ──
  const dot = `<span class="d-dot d-dot-${A.estop.state}"></span>`;
  const sysbar = () => stopped
    ? `<header class="d-bar d-bar-stop"><span class="d-brand">${I.mark}Archeus</span>
        <span class="d-stopline">${I.stop}<b>Emergency stop</b><span>${K('known', 'All work stopped at ' + hm(A.STOP_AT), 'core.estopped.at')} from ${K('known', A.estop.by, 'Device.name')}. New work is refused.</span></span>
        <span class="d-end">${A.estopButton()}</span></header>`
    : `<header class="d-bar${primed ? ' d-bar-primed' : ''}"><span class="d-brand">${I.mark}Archeus</span>
        <span class="d-safe">${dot}<b>${K('known', A.safety.label, A.safety.src)}</b><span class="t3">${K('known', A.safety.sub, A.safety.src)} · ${K('known', 'Core connected', 'connection.state')}</span></span>
        <span class="d-tell">${I.tell}<span>Tell Archeus what to do…</span><kbd>Ctrl K</kbd></span>
        <span class="d-end">${A.estopButton()}</span></header>${primed ? `<div class="d-primed">${A.primedHint()}</div>` : ''}`;

  const lineItems = () => (stopped ? halted : []).concat(A.decisions, trouble, stopped ? [] : A.running, stopped ? [] : A.starting);
  const nav = (on, sel) => `<nav class="d-nav" aria-label="Places">
      ${[['home', 'Overview', I.home], ['missions', 'Missions', I.missions], ['projects', 'Projects', icoProj], ['control', 'Control', I.control]]
        .map(([k, l, ic]) => `<a href="${place(k)}" class="d-place${k === on ? ' on' : ''}">${ic}<span>${l}</span>${k === 'missions' && A.decisions.length ? `<span class="d-badge">${n('derived', A.decisions.length, 'Approval PENDING + review requested', 'count')}</span>` : ''}</a>`).join('')}
      <details class="d-lines" open><summary><span class="label">Mission lines</span><span class="num t3">${lineItems().length}</span>${I.chev}</summary>
        ${lineItems().map((m) => `<a class="d-li${m.id === sel ? ' sel' : ''}" href="${open(m)}"><span class="tt">${T(m)}</span>
          <span class="r2">${mline(m, 'mini')}<span class="pw tone-${toneOf(m)}">${m.estop ? 'Stopped' : A.word(m)}</span></span></a>`).join('')}
      </details></nav>`;
  const desk = (main, on, sel, over) => `<div class="d-desk">${sysbar()}<div class="d-body">${nav(on, sel)}<main class="d-main">${main}</main></div>${over || ''}</div>`;

  // ── overview rows (A), each with the mission line instead of a step bar ──
  const zone = (label, meta, body, cls) => `<section class="d-zone ${cls || ''}"><header class="d-zh"><span class="label">${label}</span><span class="d-zmeta">${meta || ''}</span></header>${body}</section>`;
  const decisionRow = (m, phone) => {
    const x = A.explain(m), d = A.decision(m);
    const exp = x.expiresIn != null
      ? `<span class="num ${x.expiresIn < 15 ? 'd-urgent' : 't3'}">${K('known', 'expires ' + hm(m.approval.expires), 'Approval.expires_at')}${phone ? '' : ' · ' + K('derived', 'in ' + x.expiresIn + ' min', 'Approval.expires_at', 'expires_at − now')}</span>`
      : `<span class="num t3">${K('known', 'since ' + hm(m.review.since), 'review.requested')}</span>`;
    const body = `<div class="d-rtop"><span class="label d-kind">${d.kind}</span>${exp}</div>
        <div class="d-rtitle">${T(m)}</div><div class="d-where">${x.where}</div>
        <div class="d-why"><span class="d-k">Why</span><span>${x.why}</span></div>`;
    return phone
      ? `<a class="d-row d-ask d-card" href="${open(m)}">${body}<span class="d-openrow">Review ${I.chev}</span></a>`
      : `<div class="d-row d-ask">${body}<a class="btn primary d-review" href="${open(m)}">Review</a></div>`;
  };
  const problemRow = (m, phone) => {
    const x = A.explain(m), tag = phone ? 'a' : 'div';
    return `<${tag} class="d-row d-bad${phone ? ' d-card' : ''}"${phone ? ` href="${open(m)}"` : ''}>
        <div class="d-rtop">${chip(m)}<span class="num t3">${x.why}</span></div>
        <div class="d-rtitle">${phone ? T(m) : `<a href="${open(m)}">${T(m)}</a>`}</div>
        <div class="d-why"><span class="d-k">Because</span><span>${K('known', m.because[1], m.state === 'FAILED' ? 'Execution.failure' : 'Verification.checks')}</span></div>
        ${phone ? '' : `<a class="btn d-review" href="${open(m)}">Open</a>`}</${tag}>`;
  };
  const runRow = (m, phone) => {
    const x = A.explain(m), tag = phone ? 'a' : 'div';
    return `<${tag} class="d-row d-run${phone ? ' d-card' : ''}"${phone ? ` href="${open(m)}"` : ''}>
        <div class="d-rtop">${chip(m)}<span class="num t3">${x.elapsed || ''}</span></div>
        <div class="d-rtitle">${phone ? T(m) : `<a href="${open(m)}">${T(m)}</a>`}</div>
        <div class="d-now">${x.what}</div>
        <div class="d-lr">${mline(m, 'mid')}<span class="pw tone-${toneOf(m)}">${m.estop ? 'Stopped' : A.PHASES[A.phase(m)]}</span></div>
        <div class="d-foot"><span class="d-where">${x.where}</span>${m.estop ? '' : `<span class="t2">${x.next}</span>`}</div></${tag}>`;
  };
  const sumChecks = (r) => A.missions.reduce((s, m) => s + A.checks(m).filter((c) => c[1] === r).length, 0);
  const stats = () => `<div class="d-stats">
      <div><span class="d-big num">${n('derived', A.done.length, 'Mission.state = DONE', 'count today')}</span><span class="label">Done</span></div>
      <div><span class="d-big num">${n('derived', sumChecks('passed'), 'Verification.checks', 'passed checks today')}</span><span class="label">Checks passed</span></div>
      <div><span class="d-big num d-red">${n('derived', sumChecks('failed'), 'Verification.checks', 'failed checks today')}</span><span class="label">Checks failed</span></div></div>`;
  const titleOf = (id) => (A.byId[id] || {}).title;
  const recent = (k) => `<ol class="d-events">${A.events.slice().sort((a, b) => b.at - a.at || b.seq - a.seq).slice(0, k).map((e) =>
    `<li><span class="num t3">${K('known', hm(e.at), 'event.at')}</span><span><b>${e.mission_id ? K('known', titleOf(e.mission_id), 'Mission.title') : 'Archeus'}</b> ${A.evText(e)}</span></li>`).join('')}</ol>`;

  const headline = () => {
    const d = A.decisions.length;
    if (stopped) return 'Archeus is stopped.';
    if (!d) return `Nothing needs you. ${n('derived', A.running.length + ' ' + plural(A.running.length, 'mission is', 'missions are'), 'Mission.state')} running.`;
    return `${n('derived', d + ' ' + plural(d, 'decision is', 'decisions are'), 'Approval PENDING + review requested', 'count')} waiting for you.`;
  };
  const counts = () => [A.running.length && n('derived', A.running.length + ' running', 'Mission.state', 'EXECUTING + VERIFYING'),
    halted.length && n('derived', halted.length + ' stopped by you', 'Execution.stop_reason = estop'),
    trouble.length && n('derived', trouble.length + ' blocked or failed', 'Mission.state', 'BLOCKED + FAILED'),
    n('derived', A.done.length + ' done today', 'Mission.state = DONE')].filter(Boolean).join('<span class="t3"> · </span>');
  const deadline = () => {
    if (stopped) return `<p class="d-lead">${K('known', halted.length + ' executions', 'core.estopped.killed')} were stopped. ${n('derived', A.decisions.length + ' decisions', 'Approval PENDING')} stay open; nothing they allow can run until you resume. Resuming needs your PIN.</p>`;
    const f = A.decisions.find((m) => m.approval);
    return f ? `<p class="d-lead"><span class="d-urgent">${I.decide}Next deadline</span>Plan v${f.approval.plan_version} for ${T(f)} expires at ${K('known', hm(f.approval.expires), 'Approval.expires_at')} — ${K('derived', 'in ' + (f.approval.expires - A.NOW) + ' min', 'Approval.expires_at', 'expires_at − now')}.</p>` : '';
  };

  // the empty overview is an invitation, not a report (owner review: less text, one call to action)
  const doneLine = () => A.done.length ? `<a class="d-quiet" href="${place('missions')}">${n('derived', A.done.length + ' ' + plural(A.done.length, 'mission', 'missions') + ' done today', 'Mission.state = DONE', 'count today')} · last at ${K('known', hm(A.done[0].done_at), 'mission.done')}</a>` : '';
  const tellBig = () => `<a class="d-tellbig" href="#">${I.tell}<span>Tell Archeus what to do</span><kbd>Ctrl K</kbd></a>`;

  const homeDesk = () => {
    if (A.S === 'idle') return desk(`<div class="d-invite">${tellBig()}${doneLine()}</div>`, 'home');
    const head = `<div class="d-head"><div class="label">Overview · ${K('known', 'Tuesday ' + hm(A.NOW), 'clock')}</div>
        <h1 class="d-display">${headline()}</h1><div class="d-counts">${counts()}</div>${deadline()}</div>`;
    const wz = zone('Waiting for you', A.decisions.length ? n('derived', A.decisions.length, 'Approval PENDING', 'count') + (stopped ? ' · held until you resume' : '') : '',
      A.decisions.length ? A.decisions.map((m) => decisionRow(m)).join('') : '<p class="d-empty">Nothing waits for you.</p>', 'd-zw');
    const pz = trouble.length ? zone('Needs attention', n('derived', trouble.length, 'Mission.state', 'BLOCKED + FAILED'), trouble.map((m) => problemRow(m)).join(''), 'd-zp') : '';
    const live = stopped ? halted : A.running;
    const rz = zone(stopped ? 'Stopped by the emergency stop' : 'Running now', live.length ? n('derived', live.length, 'Mission.state', 'count') : '',
      live.length ? live.map((m) => runRow(m)).join('') : '<p class="d-empty">Nothing is running.</p>', stopped ? 'd-zstop' : '');
    const tz = zone('Today', `<span class="t3">${K('derived', A.events.filter((e) => e.at > A.LAST_LOOKED).length + ' changes since you looked', 'events after User.last_ack_event_seq', 'count')}</span>`, stats() + recent(6));
    return desk(`${head}<div class="d-grid"><div class="d-col">${stopped ? rz + wz + pz : wz + pz + rz}</div><div class="d-col">${tz}</div></div>`, 'home');
  };

  // ── the mission page: one page, every state ──
  const dl = (rows) => `<dl class="d-dl">${rows.filter((r) => r[1]).map(([k, v]) => `<dt>${k}</dt><dd>${v.replace(/>[a-z ]+: (not recorded|kept by Core)/, '>$1')}</dd>`).join('')}</dl>`;
  const ctxRows = (m) => {
    const c = A.ctx(m);
    return [['Project', c.project], ['Repository', c.repo], ['Branch', c.branch], ['Task branch', c.taskBranch], ['Commit', c.head], ['Runs on', c.where], ['Remote', c.remote]];
  };
  const steps = (m) => `<ol class="d-steps">${m.tasks.map((t, i) => {
    const st = t[1] === 'RUNNING' && m.estop ? 'STOPPED' : t[1];
    const ic = { SUCCEEDED: I.check, RUNNING: I.dot, FAILED: I.cross, STOPPED: I.stop }[st] || I.ring;
    const w = { SUCCEEDED: 'Done', RUNNING: 'Running', FAILED: 'Failed', STOPPED: 'Stopped', PENDING: 'Waiting' }[st];
    return `<li class="s-${st.toLowerCase()}"><span class="sic">${ic}</span><span class="num t3">${i + 1}</span><span class="st">${K('known', t[0], 'Task.title')}</span><span class="sw">${K('known', w, 'Task.state')}</span></li>`;
  }).join('')}</ol>`;
  const mhead = (m, phone) => {
    const x = A.explain(m);
    return `${phone ? '' : `<a class="d-back" href="${place('home')}">${I.back}Overview</a>`}
      <div class="d-mtop">${chip(m)}${m.live && x.elapsed ? `<span class="num t3">for ${x.elapsed}</span>` : ''}</div>
      <h1 class="d-headline">${T(m)}</h1><p class="d-obj">${K('known', m.objective, 'Mission.objective')}</p>
      <div class="d-where">${x.where}${A.ctx(m).head ? ' · ' + A.ctx(m).head : ''}</div>`;
  };

  // approval component: what, why, then the three answers (owner: Approve on top filled, the others outlined)
  const askComp = (m, phone) => {
    const d = A.decision(m), x = A.explain(m);
    if (!m.approval) {
      return `<section class="d-comp"><div class="d-cb"><div class="label d-kind">${d.kind}</div><h2 class="d-ch">Accept the result?</h2>
        <div class="d-cs"><div class="label">What you review</div><p>${x.what}</p><p class="t2">${x.evidence}</p></div></div>
        <div class="d-ca">${d.actions.map((a) => `<a class="btn${a.primary ? ' primary' : ''}" href="#">${a.label}</a><p class="cons">${a.then}</p>`).join('')}</div></section>`;
    }
    const by = { approve: d.actions[0], changes: d.actions[1], reject: d.actions[2] };
    const btn = (a, label) => `<a class="btn${a.primary ? ' primary' : ''}${a.key === 'reject' ? ' danger' : ''}" href="${a.key === 'approve' ? go({ did: 'approve' }) : '#'}">${label || a.label}</a>`;
    const answers = phone
      ? `<p class="cons">${by.approve.then}</p><div class="d-arow">${btn(by.reject)}${btn(by.changes, 'Change')}${btn(by.approve)}</div>`
      : [by.approve, by.changes, by.reject].map((a) => `${btn(a)}<p class="cons">${a.then}</p>`).join('');
    return `<section class="d-comp" id="ask">
      <div class="d-cb"><div class="label d-kind">${d.kind} · asked at ${d.since}</div>
        <div class="d-cs"><div class="label">What you approve</div><p>${d.summary}</p><ol class="d-tasks">${d.tasks.map((t, i) => `<li><span class="num t3">${i + 1}</span>${t}</li>`).join('')}</ol></div>
        <div class="d-cs"><div class="label">Why Archeus asks</div><p>${d.why}</p><p class="mono t3">${d.rules.join('<br>')}</p></div>
        ${d.changed ? `<div class="d-cs"><div class="label">What changed since v${m.approval.plan_version - 1}</div><p>${d.changed}</p></div>` : ''}
        <p class="d-gaps">Archeus does not know: ${d.unknown.join(' · ')}</p></div>
      <div class="d-ca">${answers}
        <p class="d-exp"><span class="num ${d.expiresIn < 15 ? 'd-urgent' : ''}">Expires ${d.expires} · ${K('derived', 'in ' + d.expiresIn + ' min', 'Approval.expires_at', 'expires_at − now')}</span><br><span class="t3">${d.expiry} Closing this page decides nothing.</span></p></div></section>`;
  };

  // problem component: why, the checks, then explain / fix / cancel (owner review)
  const ANSWER = 'The down-migration drops the table before the index that depends on it, so test_migration_rollback exits 1 when it runs down(). Dropping invoices_customer_idx first, then the table, should fix it. I have not changed anything.';
  const askArea = (m) => {
    const ask = Q.get('ask');
    if (ask === 'explain') {
      const who = K('known', m.tasks[0][0], 'Task.title');
      return `<div class="d-full d-answer" id="answer"><div class="label">Explain the error</div>
        <p class="d-asked">You asked the agent that ran “${who}”: <i>what went wrong?</i></p>
        <div class="d-wait"${Q.get('wait') ? '' : ' hidden'}><span class="d-dots"><i></i><i></i><i></i></span>Asking the agent…</div>
        <p class="d-typed"${Q.get('wait') ? ' hidden' : ''} data-text="${A.esc(ANSWER)}">${Q.get('shot') ? A.esc(ANSWER) : ''}</p>
        <p class="d-gaps">${NR('the answer', 'DR-9', 'sample text; Core cannot ask a mission’s agent yet')}</p></div>`;
    }
    if (ask === 'fix') return `<div class="d-full d-fix" id="answer"><label class="label" for="fx">Tell Archeus how to fix it</label>
        <textarea id="fx" rows="3" placeholder="For example: drop the index before the table in down(), then run the rollback check again."></textarea>
        <div class="d-fixrow"><a class="btn primary" href="#">Send and run again</a><a class="btn quiet" href="${go({ ask: null })}">Cancel</a></div>
        <p class="cons">${K('derived', 'Archeus unblocks the mission and runs it again.', 'states.py: BLOCKED → unblock → RESUMED → redispatch')} ${NR('your instructions reaching the agent', 'DR-9', 'recorded as the reason, not passed on')}</p></div>`;
    return '';
  };
  const badComp = (m, phone) => {
    const ck = A.checks(m), failedRun = m.state === 'FAILED';
    const acts = [['explain', 'Explain the error', true, K('derived', 'Asks the agent that ran it what went wrong. Nothing changes.', 'a question, no transition')],
      ['fix', 'Ask Archeus to fix it', false, failedRun ? K('derived', 'Archeus re-plans with your instructions.', 'states.py: FAILED → replan') : K('derived', 'Archeus unblocks the mission and runs it again.', 'states.py: BLOCKED → unblock → RESUMED → redispatch')],
      ['cancel', 'Cancel mission', false, K('derived', 'The mission is cancelled. Nothing more runs.', 'states.py: ' + m.state + ' → cancel → CANCELLED')]];
    return `<section class="d-comp d-comp-bad" id="ask">
      <div class="d-cb"><div class="label d-red">${failedRun ? 'Why it failed' : 'Why it is blocked'}</div>
        <ol class="d-chain">${m.because.map((b, i) => `<li><span class="d-cdot"></span><span>${K('known', b, i ? (failedRun ? 'Execution.failure' : 'Verification.checks') : (failedRun ? 'execution.failed' : 'verification.failed'))}</span></li>`).join('')}</ol>
        ${ck.length ? `<div class="label d-mt">Checks · ${K('known', A.passed(m) + ' of ' + ck.length + ' passed', 'Verification.checks')}</div>
        <ul class="d-checks">${ck.map((c) => `<li class="r-${c[1]}">${A.checkIcon(c[1])}<span>${K('known', c[0], 'Verification.checks.name')}</span><span class="num t3">${K('known', c[1] + (c[2] != null ? ' · exit ' + c[2] : ''), 'Verification.checks.result')}</span></li>`).join('')}</ul>
        <p class="d-gaps">${NR('check output', 'DR-8', 'kept by Core, not readable here')}</p>` : ''}</div>
      <div class="d-ca${phone ? ' d-ca-col' : ''}">${acts.map(([k, l, p, then]) => `<a class="btn${p ? ' primary' : ''}${k === 'cancel' ? ' danger' : ''}${Q.get('ask') === k ? ' on' : ''}" href="${k === 'cancel' ? '#' : go({ ask: k, wait: null })}">${l}</a><p class="cons">${then}</p>`).join('')}</div>
      ${askArea(m)}</section>`;
  };
  const component = (m, phone) => {
    if (m.estop) return '';
    if (m.state === 'APPROVAL_REQUIRED' || m.state === 'REVIEWING') return askComp(m, phone);
    if (m.state === 'BLOCKED' || m.state === 'FAILED') return badComp(m, phone);
    return '';
  };

  // activity: Core's events with their times, between them what the agent's stream carries
  // (GET /v1/executions/{id}/stream, P16 D4: assistant text, tool calls with their input, ok/error; never tool output)
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
    'm-91d2': [['ev', 'mission.created'], ['ev', 'approval.requested'], ['ev', 'approval.decided'], ['ev', 'approval.requested'], ['ev', 'execution.started'], ['live']],
  };
  const NOTE = { 'm-91d2': 'Add a smoke test after the deploy.' };
  const NOTE_SRC = 'approval.decided.reason (commands.request_changes requires one)';
  const activity = (m) => {
    const evs = A.evOf(m).slice(), used = new Set();
    const take = (kind) => { const e = evs.find((x) => x.kind === kind && !used.has(x)); if (e) used.add(e); return e; };
    const row = (cls, t, who, txt) => `<li class="${cls}"><span class="num t3">${t}</span><span class="who">${who}</span><span class="tx">${txt}</span></li>`;
    const evRow = (e) => row('l-core', K('known', hm(e.at), 'event.at'), 'core', A.evText(e) + (e.decision === 'request_changes' && NOTE[m.id] ? ': “' + K('known', NOTE[m.id], NOTE_SRC) + '”' : ''));
    const script = STREAM[m.id] || evs.map((e) => ['ev', e.kind]).concat(m.live ? [['live']] : []);
    const live = m.live && !m.estop;
    const lines = script.map((s) => {
      if (s[0] === 'ev') { const e = take(s[1]); return e ? evRow(e) : ''; }
      if (s[0] === 'say') return row('l-say', '', 'agent', K('known', s[1], 'stream: assistant'));
      if (s[0] === 'tool') return row('l-tool', '', '$ ' + s[1].toLowerCase(), K('known', s[2], 'stream: tool.input'));
      if (s[0] === 'res') return row(s[1] ? 'l-err' : 'l-ok', '', '', s[1] ? K('known', '✗ error', 'stream: tool_result.is_error') : K('known', '✓ ok', 'stream: tool_result.is_error'));
      if (s[0] === 'check') { const c = A.checks(m)[s[1]]; return row(c[1] === 'failed' ? 'l-err' : 'l-ok', '', 'check', K('known', (c[1] === 'failed' ? '✗ ' : '✓ ') + c[0] + ' · exit ' + c[2], 'Verification.checks') + (c[1] === 'failed' ? ' ' + NR('output', 'DR-8', 'kept by Core, not readable here') : '')); }
      if (s[0] === 'live') return live ? row('l-live', '', '', '<span class="caret"></span>') : '';
      return '';
    }).join('') + evs.filter((e) => !used.has(e)).map(evRow).join('');
    return `<section class="d-term"><header><span class="label">${live ? '<span class="d-livedot"></span>' : ''}Activity</span>
      <span class="t3 d-tsrc">${m.live || STREAM[m.id] ? 'Core events, and the agent’s stream. Tool output is not in the stream.' : 'Core events'}</span></header><ol>${lines}</ol></section>`;
  };

  // the decision record behind “Approved ✓” (owner review): what, when, and every earlier answer
  const drawer = (m) => {
    if (Q.get('drawer') !== 'approval') return '';
    const ap = approvedEv(m);
    if (!ap) return '';
    const d = m.approval && A.decision(m);
    const all = A.evOf(m, 'approval.decided');
    const W = { approve: 'Approved', request_changes: 'Asked for changes', reject: 'Rejected' };
    return `<a class="d-scrim" href="${go({ drawer: null })}" aria-label="Close"></a><aside class="d-drawer" aria-label="Decision record">
      <div class="d-dtop"><span class="label">Decision record</span><a class="d-x" href="${go({ drawer: null })}" aria-label="Close">${I.cross}</a></div>
      <h2 class="d-ch">${d ? 'Plan v' + m.approval.plan_version + ' approved' : 'Plan approved'}</h2>
      <p class="t2">${K('known', 'by you', 'approval.decided.actor')} · ${K('known', 'at ' + hm(ap.at), 'approval.decided.at')} · ${T(m)}</p>
      <div class="d-cs"><div class="label">What was approved</div>${d ? `<p>${d.summary}</p>` : ''}<ol class="d-tasks">${m.tasks.map((t, i) => `<li><span class="num t3">${i + 1}</span>${K('known', t[0], 'Plan.tasks')}</li>`).join('')}</ol></div>
      ${d ? `<div class="d-cs"><div class="label">Why Archeus asked</div><p>${d.why}</p><p class="mono t3">${d.rules.join('<br>')}</p></div>` : ''}
      <div class="d-cs"><div class="label">Every answer on this mission</div><ol class="d-events">${all.map((e) => `<li><span class="num t3">${K('known', hm(e.at), 'approval.decided.at')}</span><span><b>${K('known', W[e.decision], 'approval.decided.decision')}</b>${e.decision === 'request_changes' && NOTE[m.id] ? `<span class="d-note">“${K('known', NOTE[m.id], NOTE_SRC)}”</span>` : ''}</span></li>`).join('')}</ol></div>
      <div class="d-cs"><div class="label">Then</div><p>${A.evOf(m, 'execution.started').filter((e) => e.at >= ap.at).slice(0, 1).map((e) => `${K('known', hm(e.at), 'execution.started')} · Archeus started ${K('known', '“' + m.tasks[0][0] + '”', 'Task.title')}`).join('') || 'Nothing has run yet.'}</p></div>
    </aside>`;
  };

  const nowSec = (m) => {
    if (!m.live || m.estop) return '';
    const x = A.explain(m);
    return `<section class="d-sec"><div class="label">Right now</div>${dl([['What', x.what], ['Why', x.why], ['Evidence', x.evidence], ['Next', x.next], ['Operation', A.ctx(m).op]])}</section>`;
  };
  const planSec = (m) => m.tasks.length ? `<section class="d-sec"><div class="label">Plan · ${K('derived', A.stepsDone(m) + ' of ' + m.tasks.length + ' steps done', 'Task.state', 'count')}</div>${steps(m)}</section>` : '';
  const missionDesk = (m) => desk(`<div class="d-mp">${mhead(m)}<section class="d-linecard">${mline(m, 'full')}</section>${component(m)}
      <div class="d-two"><div>${planSec(m)}${nowSec(m)}</div><div><section class="d-sec"><div class="label">Context</div>${dl(ctxRows(m))}</section></div></div>
      ${activity(m)}</div>`, 'missions', m.id, drawer(m));

  // ── places beyond the overview ──
  const groups = () => [['Waiting for you', A.decisions], ['Stopped by you', halted], ['Blocked or failed', trouble], ['In progress', stopped ? [] : A.running.concat(A.starting)], ['Done today', A.done]].filter((g) => g[1].length);
  const missionItem = (m) => `<a class="d-mi" href="${open(m)}"><span class="r1"><span class="tt">${T(m)}</span>${chip(m)}</span>
      <span class="d-where">${A.explain(m).where}</span><span class="d-lr">${mline(m, 'mid')}<span class="pw tone-${toneOf(m)}">${A.phase(m) === 6 ? 'Done' : m.estop ? 'Stopped' : A.PHASES[A.phase(m)]}</span></span></a>`;
  const missionsBody = () => groups().map(([l, ms]) => `<section class="d-grp"><h2 class="label">${l}<span class="num t3">${ms.length}</span></h2><div class="d-mis">${ms.map(missionItem).join('')}</div></section>`).join('');
  const projectsBody = () => Object.entries(A.projects).map(([id, p]) => {
    const ms = A.missions.filter((m) => m.project_id === id);
    const c = (f, w, tone) => { const k = ms.filter(f).length; return k ? `<span class="chip tone-${tone}">${n('derived', k + ' ' + w, 'Mission.project_id + Mission.state', 'count')}</span>` : ''; };
    return `<a class="d-pr" href="#"><span class="tt">${K('known', p.name, 'Project.name')}</span><span class="d-where">${(p.repos || []).map((r) => K('known', r.path, 'Repository.path')).join(' · ') || NR('repository', 'DR-3')}</span>
      <span class="d-prc">${c((m) => m.state === 'APPROVAL_REQUIRED' || m.state === 'REVIEWING', 'waiting', 'attention')}${c((m) => m.state === 'EXECUTING' || m.state === 'VERIFYING', 'running', 'active')}${c((m) => m.state === 'BLOCKED' || m.state === 'FAILED', 'blocked or failed', 'blocked')}${c((m) => m.state === 'DONE', 'done today', 'done')}</span></a>`;
  }).join('');
  const controlBody = () => `<section class="d-zone d-ctl${stopped ? ' d-zstop' : ''}"><header class="d-zh"><span class="label">Safety</span></header><div class="d-ctlb">
      <p class="d-ctls">${dot}<b>${K('known', A.safety.label, A.safety.src)}</b></p><p class="t2">${K('known', A.safety.sub, A.safety.src)}</p>
      <div class="d-ctla">${A.estopButton()}</div>
      <p class="t3">${stopped ? 'Resuming needs your PIN. Missions stopped by the emergency stop stay blocked until you unblock them.' : 'The first press asks you to press again within 3 seconds. The second stops every running mission and refuses new work.'}</p></div></section>`;
  const placeDesk = (v) => {
    const H = { missions: ['Missions', missionsBody()], projects: ['Projects', `<div class="d-prs">${projectsBody()}</div>`], control: ['Control', controlBody()] }[v];
    return desk(`<div class="d-head"><h1 class="d-headline">${H[0]}</h1></div>${H[1]}`, v);
  };

  // ── phone: tabs Overview · Missions · Projects · Control; a mission is its own page with a back button and no tabs ──
  const tabs = (on) => `<nav class="d-tabs" aria-label="Places">${[['home', 'Overview', I.home], ['missions', 'Missions', I.missions], ['projects', 'Projects', icoProj], ['control', 'Control', I.control]]
    .map(([k, l, ic]) => `<a href="${place(k)}" class="${k === on ? 'on' : ''}"><span class="d-tic">${ic}${k === 'missions' && A.decisions.length ? `<span class="d-badge">${n('derived', A.decisions.length, 'Approval PENDING', 'count')}</span>` : ''}</span><span>${l}</span></a>`).join('')}</nav>`;
  const appbar = () => stopped
    ? `<header class="d-pbar d-pbar-stop"><span class="d-brand">${I.mark}Archeus</span><span class="d-stoptag">${I.stop}Emergency stop</span></header>`
    : `<header class="d-pbar"><span class="d-brand">${I.mark}Archeus${dot}</span><span class="d-end"><a class="d-round" href="#" aria-label="Tell Archeus">${I.tell}</a>${A.estopButton({ short: true })}</span></header>${primed ? `<div class="d-phint">${A.primedHint()}</div>` : ''}`;
  const psec = (label, meta, body, id) => `<section class="d-psec"${id ? ` id="${id}"` : ''}><h2 class="label">${label}${meta ? `<span class="num t3">${meta}</span>` : ''}</h2>${body}</section>`;
  const phone = (body, on) => `<div class="d-phone">${appbar()}<main class="d-pmain">${body}</main>${tabs(on)}</div>`;

  const homePhone = () => {
    if (A.S === 'idle') return phone(`<div class="d-invite">${tellBig()}${doneLine()}</div>`, 'home');
    if (stopped) {
      return phone(`<section class="d-status d-status-stop"><div class="label">${K('known', 'Tuesday ' + hm(A.STOP_AT), 'core.estopped.at')}</div><h1 class="d-phl">Archeus is stopped</h1>
          <p class="t2">${K('known', halted.length + ' executions', 'core.estopped.killed')} were stopped at ${K('known', hm(A.STOP_AT), 'core.estopped.at')}. New work is refused. ${n('derived', A.decisions.length + ' decisions', 'Approval PENDING')} stay open; nothing they allow runs until you resume.</p>
          <div class="d-resume">${A.estopButton()}<span class="t3">Needs your PIN</span></div></section>
        ${psec('Stopped by the emergency stop', halted.length, halted.map((m) => runRow(m, true)).join(''))}
        ${psec('Waiting for you', A.decisions.length, A.decisions.map((m) => decisionRow(m, true)).join(''))}`, 'home');
    }
    const ctr = `<div class="d-ctr"><a class="tone-attention" href="#w"><b>${n('derived', A.decisions.length, 'Mission.state', 'APPROVAL_REQUIRED + REVIEWING')}</b><span>Waiting</span></a>
        <a class="tone-active" href="#r"><b>${n('derived', A.running.length, 'Mission.state', 'EXECUTING + VERIFYING')}</b><span>Running</span></a>
        <a class="tone-blocked" href="#e"><b>${n('derived', trouble.length, 'Mission.state', 'BLOCKED + FAILED')}</b><span>Blocked or failed</span></a></div>`;
    const hero = `<section class="d-hero"><div class="label">${K('known', 'Tuesday ' + hm(A.NOW), 'clock')}</div>
        <h1 class="d-phl">${A.decisions.length ? n('derived', A.decisions.length + ' ' + plural(A.decisions.length, 'decision waits', 'decisions wait'), 'Approval PENDING', 'count') + ' for you' : 'Nothing needs you'}</h1>
        <p class="d-safe">${dot}<b>${K('known', A.safety.label, A.safety.src)}</b><span class="t3">${K('known', A.safety.sub, A.safety.src)}</span></p>${ctr}</section>`;
    const projs = Object.entries(A.projects).map(([id, p]) => {
      const k = A.missions.filter((m) => m.project_id === id && m.state !== 'DONE').length;
      return `<a class="d-prow" href="${place('projects')}"><span>${K('known', p.name, 'Project.name')}</span><span class="num t3">${k ? n('derived', k + ' open', 'Mission.project_id', 'missions not done') : ''}</span>${I.chev}</a>`;
    }).join('');
    return phone(`${hero}
      ${A.decisions.length ? psec('Waiting for you', A.decisions.length, A.decisions.map((m) => decisionRow(m, true)).join(''), 'w') : ''}
      ${trouble.length ? psec('Needs attention', trouble.length, trouble.map((m) => problemRow(m, true)).join(''), 'e') : ''}
      ${A.running.length ? psec('Running now', A.running.length, A.running.map((m) => runRow(m, true)).join(''), 'r') : ''}
      ${psec('Projects', '', `<div class="d-card d-plist">${projs}</div>`)}`, 'home');
  };
  const placePhone = (v) => phone(`<h1 class="d-phl d-ptitle">${{ missions: 'Missions', projects: 'Projects', control: 'Control' }[v]}</h1>`
    + (v === 'missions' ? missionsBody() : v === 'projects' ? `<div class="d-prs">${projectsBody()}</div>` : controlBody()), v);
  const missionPhone = (m) => `<div class="d-phone d-phone-m"><header class="d-pbar"><a class="d-pback" href="${place('home')}" aria-label="Back">${I.back}</a><span class="d-ptl">Mission</span><span class="d-end">${A.estopButton({ short: true })}</span></header>
      ${primed ? `<div class="d-phint">${A.primedHint()}</div>` : ''}
      <main class="d-pmain">${mhead(m, true)}<section class="d-linecard">${mline(m, 'full')}</section>${component(m, true)}
        ${planSec(m)}${nowSec(m)}<section class="d-sec"><div class="label">Context</div>${dl(ctxRows(m))}</section>${activity(m)}</main>${drawer(m)}</div>`;

  window.DIR = window.DIR || {};
  window.DIR.d = {
    render(v, ph) {
      const m = A.byId[Q.get('id')];
      if (m && (v === 'mission' || v === 'live' || v === 'decide')) return ph ? missionPhone(m) : missionDesk(m);
      if (v === 'missions' || v === 'projects' || v === 'control') return ph ? placePhone(v) : placeDesk(v);
      return ph ? homePhone() : homeDesk();
    },
    // the answer appears as the agent writes it; a capture shows it whole, reduced motion shows it at once
    after() {
      const el = document.querySelector('.d-typed');
      if (el && Q.get('shot')) { const t = document.getElementById('answer'); if (t && innerWidth < 600) t.scrollIntoView({ block: 'center' }); return; }
      if (!el || Q.get('wait')) return;
      const text = el.dataset.text, wait = document.querySelector('.d-wait');
      if (matchMedia('(prefers-reduced-motion: reduce)').matches) { el.textContent = text; return; }
      wait.hidden = false;
      setTimeout(() => {
        wait.hidden = true;
        let i = 0;
        const tick = () => { el.textContent = text.slice(0, ++i); if (i < text.length) setTimeout(tick, 18); };
        tick();
      }, 1400);
    },
  };
})();
