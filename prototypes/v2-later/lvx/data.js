/* LV2-X shared model over the LV2-0 fixture (../lab/fixture.js). Prototype code, never shipped.
 *
 * Every fact a direction renders goes through K() and carries its kind:
 *   known    a Core field shown as it is                 data-k="known"
 *   derived  computed from known fields by a stated rule data-k="derived"  (rule in title)
 *   nr       not recorded by Core; names the gate        data-k="nr"       ("requires DR-x")
 * Nothing renders a `proposed:` fixture field. tools/lvx_check.py fails the run if one appears.
 *
 * Scenario (?s=): normal · idle (nothing in motion) · primed (e-stop pressed once) · stopped
 * (e-stop engaged at 15:14 from this computer: Core stops every live execution and blocks each
 * mission that had one, executions.py:410-425; the policy engine then denies every action,
 * policy/engine.py:123).
 */
(function () {
  'use strict';
  const FX = window.FX, Q = new URLSearchParams(location.search);
  const S = Q.get('s') || 'normal';
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const hm = (m) => String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
  const dur = (m) => (m < 60 ? m + ' min' : Math.floor(m / 60) + ' h ' + (m % 60) + ' min');
  const NOW = FX.NOW, STOP_AT = NOW + 2;

  // K(kind, text, src[, rule]) — the only way a fact reaches the screen
  const K = (k, text, src, rule) => `<span class="f" data-k="${k}" data-src="${esc(src)}"${rule ? ` title="${esc(rule)}"` : ''}>${esc(text)}</span>`;
  const NR = (what, gate) => `<span class="f nr" data-k="nr" data-src="${esc(gate)}">${esc(what)}: not recorded<span class="gate"> · requires ${esc(gate)}</span></span>`;

  const projects = FX.projects;
  const pname = (m) => (projects[m.project_id] || {}).name;
  let missions = JSON.parse(JSON.stringify(FX.missions));

  if (S === 'idle') {
    // nothing in motion: the same day after every mission settled. Decided missions keep their record.
    missions = missions.filter((m) => m.state === 'DONE').concat([
      Object.assign({}, FX.missions.find((m) => m.id === 'm-5c30'), { state: 'DONE', done_at: NOW - 38 }),
    ]);
  }
  // ?did=approve&id=<mission>: the moment after you approve, as the state machine moves it
  // (APPROVAL_REQUIRED → approve → APPROVED → dispatch): the first task starts now
  const DID = Q.get('did') === 'approve' && missions.find((m) => m.id === Q.get('id') && m.state === 'APPROVAL_REQUIRED');
  if (DID) {
    DID.state = 'EXECUTING'; DID.tasks[0][1] = 'RUNNING';
    DID.live = { task_title: DID.tasks[0][0], task_state: 'RUNNING', branch: DID.integration_branch + '.1', started_at: NOW, step: 1, of: DID.tasks.length };
  }
  const estop = { state: S === 'stopped' ? 'stopped' : S === 'primed' ? 'primed' : 'running', at: STOP_AT, by: 'this computer', left: 2 };
  if (S === 'stopped') {
    estop.stopped = [];
    for (const m of missions) if (m.live) { estop.stopped.push(m.id); m.state = 'BLOCKED'; m.estop = true; m.live.task_state = 'STOPPED'; }
  }

  const byId = Object.fromEntries(missions.map((m) => [m.id, m]));
  const decisions = missions.filter((m) => m.state === 'APPROVAL_REQUIRED' || m.state === 'REVIEWING')
    .sort((a, b) => (a.approval ? a.approval.expires : 1e9) - (b.approval ? b.approval.expires : 1e9));
  const running = missions.filter((m) => m.state === 'EXECUTING' || m.state === 'VERIFYING');
  const starting = missions.filter((m) => m.state === 'PLANNING');
  const problems = missions.filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED');
  const done = missions.filter((m) => m.state === 'DONE').sort((a, b) => b.done_at - a.done_at);
  const events = S === 'idle' ? FX.events.filter((e) => e.at <= NOW - 38) : FX.events.slice();
  if (DID) events.push({ seq: 996, mission_id: DID.id, at: NOW, kind: 'approval.decided', decision: 'approve' },
    { seq: 997, mission_id: DID.id, at: NOW, kind: 'execution.started' });
  if (S === 'stopped') events.push({ seq: 999, at: STOP_AT, kind: 'core.estopped', mission_id: null, killed: estop.stopped.length });
  const LAST_LOOKED = 14 * 60 + 30; // User.last_ack_event_seq, as a time

  // ── state in words (Core state names; "stopped" is reserved for the emergency stop) ──
  const WORD = { APPROVAL_REQUIRED: 'Needs approval', REVIEWING: 'Needs review', EXECUTING: 'Running', VERIFYING: 'Verifying',
    BLOCKED: 'Blocked', FAILED: 'Failed', DONE: 'Done', PLANNING: 'Planning' };
  const TONE = { APPROVAL_REQUIRED: 'attention', REVIEWING: 'attention', EXECUTING: 'active', VERIFYING: 'active',
    BLOCKED: 'blocked', FAILED: 'blocked', DONE: 'done', PLANNING: 'thinking' };
  const word = (m) => (m.estop ? 'Blocked by emergency stop' : WORD[m.state]);
  const tone = (m) => TONE[m.state];

  // the lifecycle the state machine walks (states.py 'mission'), collapsed to six phases
  const PHASES = ['Understand', 'Plan', 'Approve', 'Run', 'Verify', 'Review'];
  const PHASE_OF = { CREATED: 0, UNDERSTANDING: 0, CONTEXT_GATHERING: 0, REASONING: 1, PLANNING: 1, REPLANNING: 1,
    APPROVAL_REQUIRED: 2, APPROVED: 3, EXECUTING: 3, PAUSED: 3, RESUMED: 3, VERIFYING: 4, REVIEWING: 5, DONE: 6, COMPLETED: 6 };
  const phase = (m) => {
    if (m.state === 'BLOCKED') return m.estop ? 3 : (m.verification ? 4 : 3);
    if (m.state === 'FAILED') return 3;
    return PHASE_OF[m.state];
  };

  // ── context: known facts, one derivation, and the gaps by name ──
  const ctx = (m) => {
    const P = projects[m.project_id] || {};
    const repos = P.repos || [];
    const live = m.live || {};
    return {
      project: P.name ? K('known', P.name, 'Project.name (client join on /v1/projects, DR-1 option A)') : NR('project', 'DR-1'),
      branch: m.integration_branch ? K('known', m.integration_branch, 'Mission.integration_branch') : '',
      taskBranch: live.branch ? K('known', live.branch, 'Execution.branch') : '',
      head: m.integration_head ? K('known', m.integration_head, 'Mission.integration_head') : '',
      repo: repos.length === 1
        ? K('derived', repos[0].path, 'Repository.path', 'the repository at Project.root_paths[0] (DR-3 documented rule); the project has one repository')
        : repos.length > 1 ? NR('repository', 'DR-3') : '',
      where: K('derived', 'this computer', 'ExecutionNode', 'V1 runs only on the local node'),
      remote: NR('remote', 'DR-2'), env: NR('environment', 'DR-4'), op: NR('current operation', 'DR-6'),
    };
  };

  const checks = (m) => (m.verification ? m.verification.checks : []);
  const passed = (m) => checks(m).filter((c) => c[1] === 'passed').length;
  const stepsDone = (m) => m.tasks.filter((t) => t[1] === 'SUCCEEDED').length;
  const evOf = (m, kind) => events.filter((e) => e.mission_id === m.id && (!kind || e.kind === kind));
  const lastEv = (m) => evOf(m).slice(-1)[0];

  // ── the explanation frame: what · where · why · evidence · next ──
  // each slot is { html } built from K()/NR(); a slot Core cannot fill is left out or names its gate
  const explain = (m) => {
    const c = ctx(m), a = m.approval, x = {};
    x.where = c.project + (c.branch ? ' · ' + c.branch : '');
    if (m.estop) {
      x.what = `Stopped at step ${m.live.step} of ${m.live.of}: ${K('known', m.live.task_title, 'Task.title')}`;
      x.why = `${K('known', 'Emergency stop', 'Execution.stop_reason = estop')} at ${K('known', hm(STOP_AT), 'core.estopped.at')} from ${K('known', 'this computer', 'Device.name')}`;
      x.evidence = `${K('derived', stepsDone(m) + ' of ' + m.live.of + ' steps finished before the stop', 'Task.state', 'count of SUCCEEDED tasks')}`;
      x.next = `${K('derived', 'Stays blocked until you resume Archeus and unblock it', 'states.py mission: BLOCKED → unblock → RESUMED', 'the only exit from BLOCKED other than cancel')}`;
    } else if (m.state === 'APPROVAL_REQUIRED') {
      x.what = `${K('known', 'Approve plan v' + a.plan_version, 'Approval.kind=plan, plan_version')} for ${K('known', m.title, 'Mission.title')}`;
      x.why = `${K('derived', a.action_class === 'deploy' ? 'Your policy asks before every deploy' : 'Your policy asks before writing files', 'PolicyDecision.matched_rules', 'the matched rule ' + a.policy.split(';')[0] + ', in words')}`;
      x.evidence = `${K('known', m.tasks.length + ' tasks', 'Plan.tasks')} · ${K('derived', 'nothing has run yet', 'Execution (none)', 'the mission has no execution')}`
        + (a.action_class === 'deploy' ? ' · ' + K('known', 'includes a deploy', 'Task.action_classes') : '');
      x.next = `${K('derived', 'Approve: Archeus starts “' + m.tasks[0][0] + '”', 'states.py: APPROVAL_REQUIRED → approve → APPROVED → dispatch', 'the state machine, first task of the plan')}`;
      x.expires = K('known', 'expires ' + hm(a.expires) + ' (in ' + (a.expires - NOW) + ' min)', 'Approval.expires_at');
      x.expiresIn = a.expires - NOW;
    } else if (m.state === 'REVIEWING') {
      x.what = `${K('known', 'Review the result', 'Review requested')} of ${K('known', m.title, 'Mission.title')}`;
      x.why = `${K('derived', 'Finished and verified; Archeus asks you to accept it', 'states.py: VERIFYING → verified → REVIEWING')}`;
      x.evidence = `${K('known', passed(m) + ' of ' + checks(m).length + ' checks passed', 'Verification.checks')} at ${c.head}`;
      x.next = `${K('derived', 'Accept: the mission completes · Ask for changes: Archeus re-plans', 'states.py: REVIEWING → accepted / changes_requested')}`;
    } else if (m.state === 'EXECUTING' || m.state === 'VERIFYING') {
      const L = m.live;
      x.what = `Step ${K('known', L.step, 'Task (plan order)')} of ${K('known', L.of, 'Plan.tasks')}: ${K('known', L.task_title, 'LiveItem.task_title')}`;
      const ap = evOf(m, 'approval.decided').filter((e) => e.decision === 'approve').slice(-1)[0];
      x.why = ap ? `${K('known', 'You approved the plan at ' + hm(ap.at), 'approval.decided')}` : '';
      x.evidence = m.state === 'VERIFYING'
        ? `${K('known', passed(m) + ' of ' + checks(m).length + ' checks passed', 'Verification.checks')}, ${K('known', checks(m).filter((k) => k[1] === 'running').length + ' running', 'Verification.checks')}`
        : `${K('derived', stepsDone(m) + ' steps finished', 'Task.state')}` + (evOf(m, 'checkpoint.created').length ? ` · ${K('known', 'last checkpoint ' + hm(evOf(m, 'checkpoint.created').slice(-1)[0].at), 'checkpoint.created')}` : '');
      const nxt = m.tasks.find((t) => t[1] === 'PENDING');
      x.next = nxt ? `${K('known', 'Then: ' + nxt[0], 'Task.title (next PENDING)')}` : `${K('derived', 'Then: review', 'states.py: VERIFYING → verified → REVIEWING')}`;
      x.elapsed = K('derived', dur(NOW - L.started_at), 'Execution.started_at', 'now − started_at');
    } else if (m.state === 'BLOCKED') {
      x.what = `${K('known', 'Blocked', 'Mission.state')}: ${K('known', m.because[1], 'Verification.checks[rollback]')}`;
      x.why = `${K('known', m.because[0], 'verification.failed')}`;
      x.evidence = `${K('known', passed(m) + ' of ' + checks(m).length + ' checks passed', 'Verification.checks')} · ${NR('check output', 'DR-8')}`;
      x.next = `${K('derived', 'Archeus waits for you', 'states.py: BLOCKED → unblock / cancel')}`;
    } else if (m.state === 'FAILED') {
      x.what = `${K('known', 'Failed', 'Mission.state')}: ${K('known', m.because[1], 'Execution.failure')}`;
      x.why = `${K('known', m.because[0], 'execution.failed')}`;
      x.evidence = K('known', 'no checks ran', 'Verification (none)');
      x.next = `${K('derived', 'Retry re-plans it · or cancel', 'states.py: FAILED → replan / cancel')}`;
    } else if (m.state === 'DONE') {
      x.what = `${K('known', 'Done', 'Mission.state')} at ${K('known', hm(m.done_at), 'mission.done')}`;
      x.evidence = m.verification ? K('known', passed(m) + ' of ' + checks(m).length + ' checks passed', 'Verification.checks') : '';
    } else if (m.state === 'PLANNING') {
      x.what = K('known', 'Planning', 'Mission.state');
      x.next = K('derived', 'Archeus asks you if the plan needs approval', 'states.py: PLANNING → plan_needs_approval / plan_auto_approved');
    }
    return x;
  };

  // a decision, field by field (the only approval fields a direction may render)
  const decision = (m) => {
    const a = m.approval;
    if (!a) return { kind: K('known', 'Result review', 'Review'), title: K('known', m.title, 'Mission.title'),
      actions: [
        { key: 'accept', label: 'Accept', primary: true, then: K('derived', 'The mission completes. Its changes stay on ' + m.integration_branch + '.', 'states.py: REVIEWING → accepted → COMPLETED') },
        { key: 'changes', label: 'Ask for changes', then: K('derived', 'Archeus re-plans with your note and asks again.', 'states.py: REVIEWING → changes_requested → REPLANNING') }],
      checks: checks(m) };
    const rules = a.policy.split(';').map((r) => r.trim());
    return {
      kind: K('known', 'Plan approval · v' + a.plan_version, 'Approval.kind, plan_version'),
      title: K('known', m.title, 'Mission.title'),
      summary: K('known', a.what, 'Plan.summary'),
      asked: K('known', a.asked, 'Intent.utterance (your request)'),
      why: K('derived', a.why, 'PolicyDecision.matched_rules', 'the matched rules in words'),
      rules: rules.map((r) => K('known', r, 'PolicyDecision.matched_rules')),
      changed: a.changed ? K('derived', a.changed, 'Plan v' + (a.plan_version - 1) + ' → v' + a.plan_version + ' tasks + approval.decided note', 'difference between the two plan versions, and your note') : '',
      tasks: m.tasks.map((t) => K('known', t[0], 'Task.title')),
      expires: K('known', hm(a.expires), 'Approval.expires_at'), expiresIn: a.expires - NOW,
      since: K('known', hm(a.since), 'approval.requested'),
      actions: [
        { key: 'approve', label: 'Approve', primary: true, then: K('derived', 'Archeus starts “' + m.tasks[0][0] + '” now, then the other ' + (m.tasks.length - 1) + ' tasks.', 'states.py: APPROVAL_REQUIRED → approve → APPROVED → dispatch') },
        { key: 'changes', label: 'Ask for changes', then: K('derived', 'Archeus re-plans with your note. Nothing runs.', 'states.py: APPROVAL_REQUIRED → request_changes → PLANNING') },
        { key: 'reject', label: 'Reject', then: K('derived', 'The mission is cancelled. Nothing has run.', 'states.py: APPROVAL_REQUIRED → reject → CANCELLED') }],
      expiry: K('derived', 'If nobody decides by ' + hm(a.expires) + ', the approval expires and nothing runs.', 'authorization.expire_due: PENDING → EXPIRED'),
      unknown: [NR('environment', 'DR-4'), NR('remote', 'DR-2')],
    };
  };

  // the safety frame (never the word "armed" — see the reassessment §8)
  const safety = {
    running: { label: 'Working normally', sub: 'Accepts new work', src: 'STOP sentinel absent' },
    primed: { label: 'Stop is ready', sub: 'Press again within ' + estop.left + ' s to stop all work', src: 'client state (LD-7 first press)' },
    stopped: { label: 'Emergency stop', sub: 'All work stopped at ' + hm(STOP_AT) + '. New work is refused.', src: 'core.estopped' },
  }[estop.state];

  // one event in words; every word comes from the event's kind and its mission
  const EVW = { 'mission.created': 'created', 'execution.started': 'started work', 'checkpoint.created': 'saved a checkpoint',
    'verification.started': 'started verifying', 'verification.passed': 'verified — all checks passed', 'verification.failed': 'verification failed',
    'mission.done': 'finished', 'mission.blocked': 'blocked', 'approval.requested': 'asked for your approval', 'approval.decided': 'decision recorded',
    'execution.failed': 'failed', 'review.requested': 'asked you to review the result', 'execution.output': 'produced output', 'core.estopped': 'Emergency stop: all work stopped' };
  const evText = (e) => {
    if (e.kind === 'core.estopped') return K('known', EVW[e.kind] + ' (' + e.killed + ' executions)', 'core.estopped');
    let w = EVW[e.kind];
    if (e.kind === 'approval.decided') w = { approve: 'you approved the plan', request_changes: 'you asked for changes', reject: 'you rejected the plan' }[e.decision];
    if (e.kind === 'checkpoint.created') w += ' (' + e.files + (e.files === 1 ? ' file)' : ' files)');
    return K('known', w, 'event ' + e.kind);
  };
  const tl = (m) => evOf(m);

  const icon = {
    mark: '<svg viewBox="0 0 24 24" class="ico mark" aria-hidden="true"><path d="M12 3 21 20H3Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 9.5 16.4 17.5H7.6Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    stop: '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/></svg>',
    home: '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><path d="M4 11 12 4l8 7v9h-5v-6H9v6H4Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    decide: '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><path d="M12 3 21 12 12 21 3 12Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    missions: '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    record: '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><circle cx="6" cy="6" r="2" fill="currentColor"/><circle cx="6" cy="18" r="2" fill="currentColor"/><path d="M6 8v8M11 6h9M11 18h9M11 12h6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    control: '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><path d="M5 7h14M5 17h14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="9" cy="7" r="2.2" fill="var(--bg)" stroke="currentColor" stroke-width="1.6"/><circle cx="15" cy="17" r="2.2" fill="var(--bg)" stroke="currentColor" stroke-width="1.6"/></svg>',
    tell: '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    back: '<svg viewBox="0 0 24 24" class="ico" aria-hidden="true"><path d="M15 5 8 12l7 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    chev: '<svg viewBox="0 0 24 24" class="ico chev" aria-hidden="true"><path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    check: '<svg viewBox="0 0 16 16" class="ico ck" aria-hidden="true"><path d="M3.5 8.5 6.5 11.5 12.5 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    cross: '<svg viewBox="0 0 16 16" class="ico ck" aria-hidden="true"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    dot: '<svg viewBox="0 0 16 16" class="ico ck" aria-hidden="true"><circle cx="8" cy="8" r="3" fill="currentColor"/></svg>',
    ring: '<svg viewBox="0 0 16 16" class="ico ck" aria-hidden="true"><circle cx="8" cy="8" r="4" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  };
  const checkIcon = (r) => ({ passed: icon.check, failed: icon.cross, running: icon.dot, pending: icon.ring }[r]);

  // navigation: every link is a query string, so every screen is a URL the capture script can shoot
  const go = (patch) => {
    const p = new URLSearchParams(location.search);
    for (const [k, v] of Object.entries(patch)) (v == null ? p.delete(k) : p.set(k, v));
    return '?' + p.toString();
  };

  window.AX = { Q, S, NOW, STOP_AT, LAST_LOOKED, hm, dur, esc, K, NR, projects, pname, missions, byId, decisions, running, starting,
    problems, done, events, estop, safety, word, tone, PHASES, phase, ctx, explain, decision, checks, passed, stepsDone, evOf, lastEv, evText, tl,
    icon, checkIcon, go };
})();
