/* LV2-X.2 fixture for the refined E (?d=e2). Prototype only. Loaded after ../lab/fixture.js and
 * before data.js; it does nothing unless d=e2, so A–E render exactly as before.
 *
 * Adds, in V1 shapes only (Mission, Approval, events as the LV2-0 fixture already names them):
 *   - two settled missions the accepted states need: one REJECTED at its plan approval
 *     (APPROVAL_REQUIRED → reject → CANCELLED) and one CANCELLED after it was blocked
 *     (BLOCKED → cancel → CANCELLED). Core records both as mission.state_changed{from, to, reason}.
 *   - the ideas (Idea{title, text, project_id, state}), moved here from d.js so the stress
 *     corpus can extend them; `research` is DR-10 sample content, marked as such where rendered.
 *   - ?corpus=x2: the stress day (LV2-X.2 §8): 7 projects, 25 missions, 13 ideas, look-alike
 *     titles and project names, long names and branches, Unicode, a mission still blocked by an
 *     emergency stop that was later cleared.
 *   - ?s=empty (projects, no missions yet) · ?s=noprojects (first run) · ?s=resumed (the stop of
 *     15:14 cleared at 15:17; core.rearmed) · ?did=reject|accept|cancel (the moment after).
 */
(function () {
  'use strict';
  const Q = new URLSearchParams(location.search);
  if (Q.get('d') !== 'e2') return;
  const FX = window.FX, h = (hh, mm) => hh * 60 + mm, S = Q.get('s') || 'normal';
  const W = 'profile:standard@2:USER:write (ASK, USER)';
  let seq = 700;
  const ev = (mid, at, kind, x) => FX.events.push(Object.assign({ seq: ++seq, mission_id: mid, at, kind }, x || {}));

  FX.missions.push(
    { id: 'm-a3f0', title: 'Remove the legacy export endpoint', objective: 'No /v1/export route; the API docs say so', project_id: 'p-arch',
      state: 'CANCELLED', integration_branch: 'archeus/m-a3f0', integration_head: '8fe7ce3', created: h(13, 20),
      ended: { at: h(13, 40), how: 'rejected', phase: 2 },
      approval: { id: 'ap-9', kind: 'plan', plan_version: 1, action_class: 'write', policy: W, expires: h(14, 31), since: h(13, 31),
        allowed: ['approve', 'reject', 'request_changes'], changed: null, asked: 'Remove the old export endpoint',
        what: 'Delete the /v1/export route and its tests, then update the API docs.',
        why: 'Writing outside a mission worktree needs your approval under the standard profile.' },
      tasks: [['Remove the route and its tests', 'CANCELLED'], ['Update the API docs', 'CANCELLED']] },
    { id: 'm-b81c', title: 'Seed the demo invoices', objective: 'A demo database with 200 realistic invoices', project_id: 'p-inv',
      state: 'CANCELLED', integration_branch: 'archeus/m-b81c', integration_head: '7c1d0aa', created: h(11, 30),
      ended: { at: h(12, 30), how: 'cancelled', phase: 4 },
      because: ['Verification failed at 12:05', 'check “fixtures load” failed (exit 1)'],
      verification: { state: 'FAILED', checks: [['fixtures load', 'failed', 1], ['full test suite', 'passed', 0]] },
      tasks: [['Write the seed script', 'SUCCEEDED'], ['Verify', 'FAILED']] });
  // Core's own record of both: mission.state_changed{to, trigger, reason} (commands.py:486-495, authorization.py:659-681);
  // there is no HTTP cancel route, so the second one was cancelled through the conversation's cancel verb
  ev('m-a3f0', h(13, 20), 'mission.created'); ev('m-a3f0', h(13, 31), 'approval.requested');
  ev('m-a3f0', h(13, 40), 'approval.decided', { decision: 'reject' });
  ev('m-a3f0', h(13, 40), 'mission.state_changed', { to: 'CANCELLED', trigger: 'reject', reason: 'plan v1 rejected' });
  ev('m-b81c', h(11, 30), 'mission.created'); ev('m-b81c', h(11, 34), 'approval.decided', { decision: 'approve' }); ev('m-b81c', h(11, 35), 'execution.started');
  ev('m-b81c', h(11, 58), 'checkpoint.created', { files: 1 }); ev('m-b81c', h(12, 0), 'verification.started'); ev('m-b81c', h(12, 5), 'verification.failed');
  ev('m-b81c', h(12, 5), 'mission.blocked');
  ev('m-b81c', h(12, 30), 'mission.state_changed', { to: 'CANCELLED', trigger: 'cancel', reason: 'cancel: asked in a message' });

  // X.4: Core gives a plan, task or start approval 24 h (authorization.py:41-43); the LV2-0 fixture had them expire in
  // minutes. m-2b7f keeps its afternoon deadline and so was asked yesterday; every other one expires a day after it was asked
  const TTL = 1440;
  const ttl = (list) => {
    for (const m of list) {
      const a = m.approval;
      if (!a || !['plan', 'task', 'start'].includes(a.kind) || a.expires - a.since === TTL) continue;
      if (m.id !== 'm-2b7f') { a.expires = a.since + TTL; continue; }
      a.since = a.expires - TTL; m.created = a.since - 12;
      for (const e of FX.events) if (e.mission_id === m.id) e.at = e.kind === 'mission.created' ? m.created : e.kind === 'approval.requested' ? a.since : e.at;
    }
  };
  ttl(FX.missions);

  // the moment after an answer, as Core records it (?did=…&id=…); approve is data.js's own
  const DID = Q.get('did'), target = FX.missions.find((m) => m.id === Q.get('id'));
  const NOWD = FX.NOW;
  if (target && DID === 'reject' && target.state === 'APPROVAL_REQUIRED') {
    target.state = 'CANCELLED'; target.ended = { at: NOWD, how: 'rejected', phase: 2 };
    target.tasks = target.tasks.map((t) => [t[0], 'CANCELLED']);
    ev(target.id, NOWD, 'approval.decided', { decision: 'reject' });
    ev(target.id, NOWD, 'mission.state_changed', { to: 'CANCELLED', trigger: 'reject', reason: 'plan v' + target.approval.plan_version + ' rejected' });
  }
  if (target && DID === 'accept' && target.state === 'REVIEWING') {
    target.state = 'DONE'; target.done_at = NOWD;
    ev(target.id, NOWD, 'review.decided', { decision: 'accept' }); ev(target.id, NOWD, 'mission.done');
  }
  if (target && DID === 'cancel' && (target.state === 'BLOCKED' || target.state === 'FAILED')) {
    target.ended = { at: NOWD, how: 'cancelled', phase: target.state === 'FAILED' ? 3 : 4 }; target.state = 'CANCELLED';
    ev(target.id, NOWD, 'mission.state_changed', { to: 'CANCELLED', trigger: 'cancel', reason: 'cancelled on request' });
  }
  // an approval past its time: approval.state_changed{ttl_elapsed}; the mission machine has no expiry edge, so the
  // mission stays APPROVAL_REQUIRED with nothing pending (authorization.py:808-819) — what follows is not defined
  if (target && DID === 'expire' && target.state === 'APPROVAL_REQUIRED') {
    target.approval.expired = true; FX.NOW = target.approval.expires + 4;
    ev(target.id, target.approval.expires, 'approval.expired');
  }

  const at = h;
  FX.ideas = [
    { id: 'ida-7c21', project_id: 'p-arch', title: 'Show what each mission cost on its page', state: 'CAPTURED', at: at(13, 20),
      text: 'On the mission page, show what the mission has cost so far, task by task.' },
    { id: 'ida-3e90', project_id: 'p-inv', title: 'Export the invoice list as CSV', state: 'EXPLORED', at: at(11, 41),
      text: 'A button on the invoice list that downloads what is on screen as CSV, with the same filters.',
      research: { at: at(12, 30), version: 2,
        summary: 'Stream the filtered invoice list from the API as CSV, add an Export button to the list, and test it with 10 000 invoices.',
        tasks: [['Find the list query and its filters', 'inspection', 'small', 'in_place', 1, []],
          ['Stream the CSV from the API', 'code_change', 'mid', 'worktree', 2, ['write']],
          ['Add the Export button to the list', 'code_change', 'small', 'worktree', 1, ['write']],
          ['Test with 10 000 invoices', 'verification', 'mid', 'worktree', 2, []]],
        prev: { version: 1, summary: 'Build the CSV in memory from the filtered list, add an Export button, and test it.', changed: [1] },
        capabilities: ['code_edit', 'shell'],
        question: 'Should voided invoices be in the export?',
        comments: [['you', at(13, 5), 'Stream it — exports can be large.'],
          ['archeus', at(13, 6), 'Revised the plan to v2: task 2 now streams rows instead of building the file in memory.']] } },
    { id: 'ida-5b14', project_id: 'p-inv', title: 'Make invoice lookups by customer fast', state: 'IMPLEMENTING', at: at(12, 4), mission: 'm-5c30',
      text: 'Looking up a customer’s invoices takes seconds; it should be instant.' },
    { id: 'ida-0d77', project_id: 'p-www', title: 'A dark theme for the docs site', state: 'PARKED', at: at(9, 12),
      text: 'A dark theme for the docs site that follows the system setting.' },
    { id: 'ida-9a02', project_id: null, title: 'A small tool that compares two release notes', state: 'CAPTURED', at: at(8, 47),
      text: 'Paste two release notes, see what was added, removed and changed.' },
  ];

  if (S === 'empty') { FX.missions = []; FX.events = []; FX.ideas = []; }
  if (S === 'noprojects') { FX.projects = {}; FX.missions = []; FX.events = []; FX.ideas = []; }
  // the stop of 15:14 was cleared at 15:17 from this computer: the missions it stopped stay
  // BLOCKED (executions.py blocks each mission that had a live execution; nothing unblocks them)
  if (S === 'resumed') {
    FX.NOW = h(15, 17);
    for (const m of FX.missions) if (m.live) { m.state = 'BLOCKED'; m.estop = true; m.estop_at = h(15, 14); m.live.task_state = 'STOPPED'; }
    FX.events.push({ seq: 990, at: h(15, 14), kind: 'core.estopped', mission_id: null, killed: 2 }, { seq: 991, at: h(15, 17), kind: 'core.rearmed', mission_id: null });
  }

  if (Q.get('corpus') === 'x2') {
    Object.assign(FX.projects, {
      'p-ia': { name: 'invoicing-api', repos: [{ path: 'D:\\work\\invoicing-api', kind: 'repo', default_branch: 'main', last_revision: '3b7a91c' }] },
      'p-long': { name: 'customer-portal-internationalisation', repos: [{ path: 'D:\\repos\\customer-portal-internationalisation', kind: 'repo', default_branch: 'release/2026.10-customer-portal-locale-rollout', last_revision: '6e0a7d2' }] },
      'p-uni': { name: 'café-menü', repos: [{ path: 'D:\\work\\café-menü', kind: 'repo', default_branch: 'main', last_revision: '0b9c4a1' }] },
      'p-www2': { name: 'website-legacy', repos: [{ path: 'D:\\repos\\archeus-site-legacy', kind: 'repo', default_branch: 'main', last_revision: 'aa41f07' }] },
    });
    for (const P of Object.values(FX.projects)) P.root_paths = P.root_paths || [P.repos[0].path];
    const NOW = FX.NOW;
    const run = (id, pid, title, step, tasks, start, branch, verifying, checks) => ({ id, title, objective: title, project_id: pid, state: verifying ? 'VERIFYING' : 'EXECUTING',
      integration_branch: 'archeus/' + id, integration_head: id.slice(2) + 'e0f1', created: start - 20,
      live: { task_title: tasks[step - 1], task_state: 'RUNNING', branch: branch || 'archeus/' + id + '.' + step, started_at: start, step, of: tasks.length },
      verification: checks ? { state: 'RUNNING', checks } : undefined,
      tasks: tasks.map((t, i) => [t, i < step - 1 ? 'SUCCEEDED' : i === step - 1 ? 'RUNNING' : 'PENDING']) });
    const ask = (id, pid, title, v, mins, what, tasks) => ({ id, title, objective: title, project_id: pid, state: 'APPROVAL_REQUIRED', integration_branch: 'archeus/' + id, integration_head: '0c' + id.slice(2) + 'd1', created: NOW - 50,
      approval: { id: 'ap-' + id, kind: 'plan', plan_version: v, action_class: 'write', policy: W, expires: NOW + mins, since: NOW - 12, allowed: ['approve', 'reject', 'request_changes'], changed: null,
        asked: title, what, why: 'Writing outside a mission worktree needs your approval under the standard profile.' },
      tasks: tasks.map((t) => [t, 'PENDING']) });
    const done = (id, pid, title, t, checks) => ({ id, title, objective: title, project_id: pid, state: 'DONE', integration_branch: 'archeus/' + id, integration_head: 'd0' + id.slice(2) + '9e', created: t - 60, done_at: t,
      verification: { state: 'PASSED', checks }, tasks: [[title, 'SUCCEEDED']] });
    const X = [
      ask('x-01', 'p-ia', 'Upgrade the auth library', 1, 25, 'Rewrite the 6 call sites for auth-lib 5, then run the API suite.', ['Rewrite call sites', 'Run the API suite']),
      { id: 'x-02', title: 'Migrate every invoice PDF template to the new rendering pipeline without changing a single pixel of output', objective: 'All 41 templates render byte-identical PDFs on the new pipeline',
        project_id: 'p-long', state: 'REVIEWING', integration_branch: 'archeus/x-02', integration_head: 'a1f5c3e', created: h(12, 40), review: { since: h(14, 55) },
        verification: { state: 'PASSED', checks: [['templates compile', 'passed', 0], ['golden PDFs identical', 'passed', 0]] },
        tasks: [['Inventory templates', 'SUCCEEDED'], ['Port the layout engine', 'SUCCEEDED'], ['Port the templates', 'SUCCEEDED'], ['Compare every rendered PDF with its golden file', 'SUCCEEDED']] },
      ask('x-03', 'p-uni', 'Übersetzungen für das Kundenportal prüfen — 日本語ラベル', 1, 55, 'Check every German and Japanese label against its control, then fix the ones that overflow.', ['Prüfen (de)', 'ラベル確認 (ja)', 'Fix overflowing labels']),
      run('x-04', 'p-inv', 'Update the currency formatter', 2, ['Find call sites', 'Format amounts', 'Verify'], h(14, 20)),
      run('x-05', 'p-inv', 'Update the currency formatter', 2, ['Find call sites', 'Format amounts', 'Verify'], h(14, 25)),
      run('x-06', 'p-www2', 'Fix the flaky date test', 1, ['Reproduce', 'Find the cause', 'Patch the clock', 'Verify'], h(15, 4)),
      run('x-07', 'p-long', 'Port the locale switcher to the new router and keep every existing deep link working', 3,
        ['Map the old routes', 'Port the switcher', 'Check every deep link still resolves'], h(14, 58), 'archeus/x-07.check-every-deep-link-still-resolves-on-the-new-router', true,
        [['type check', 'passed', 0], ['deep links resolve', 'running', null], ['full test suite', 'pending', null]]),
      { id: 'x-08', title: 'Rotate the signing keys', objective: 'New signing keys in use; the old ones revoked', project_id: 'p-ia', state: 'FAILED', created: h(12, 40), failed_at: h(13, 2),
        because: ['The execution ended at 13:02', 'the harness exited with an error (exit 2)'], tasks: [['Generate the new keys', 'SUCCEEDED'], ['Switch the service over', 'FAILED']] },
      { id: 'x-09', title: 'Clear the CDN cache for the docs', objective: 'The docs serve the 1.9 pages everywhere', project_id: 'p-www', state: 'BLOCKED', estop: true, estop_at: h(11, 40),
        integration_branch: 'archeus/x-09', integration_head: '41c09ab', created: h(11, 20),
        live: { task_title: 'Purge the cache', task_state: 'STOPPED', branch: 'archeus/x-09.purge', started_at: h(11, 31), step: 2, of: 3 },
        tasks: [['List the stale paths', 'SUCCEEDED'], ['Purge the cache', 'RUNNING'], ['Check the pages', 'PENDING']] },
      { id: 'x-10', title: 'Add a Japanese currency format', objective: 'Amounts in ja-JP render with ¥ and no decimals', project_id: 'p-uni', state: 'PLANNING', created: h(15, 6), tasks: [] },
      done('x-11', 'p-long', 'Inventory the PDF templates', h(12, 35), [['inventory complete', 'passed', 0]]),
      done('x-12', 'p-uni', 'Übersetzungen prüfen (Deutsch)', h(11, 50), [['labels fit (de)', 'passed', 0]]),
      done('x-13', 'p-ia', 'Bump the API client', h(10, 15), [['unit tests', 'passed', 0], ['contract tests', 'passed', 0]]),
    ];
    FX.missions.push(...X);
    ttl(X);
    for (const m of X) {
      ev(m.id, m.created, 'mission.created');
      if (m.approval) ev(m.id, m.approval.since, 'approval.requested');
      if (m.live) { ev(m.id, m.live.started_at - 1, 'approval.decided', { decision: 'approve' }); ev(m.id, m.live.started_at, 'execution.started'); }
      if (m.id === 'x-09') { ev(null, h(11, 40), 'core.estopped', { killed: 1 }); ev(null, h(11, 52), 'core.rearmed'); }
      if (m.state === 'FAILED') ev(m.id, m.failed_at, 'execution.failed');
      if (m.state === 'REVIEWING') { ev(m.id, h(14, 50), 'verification.passed'); ev(m.id, m.review.since, 'review.requested'); }
      if (m.state === 'DONE') { ev(m.id, m.done_at, 'verification.passed'); ev(m.id, m.done_at, 'mission.done'); }
    }
    FX.events.sort((a, b) => a.at - b.at || a.seq - b.seq);
    FX.ideas.push(
      { id: 'idx-01', project_id: 'p-ia', title: 'Rate-limit the export endpoint', state: 'CAPTURED', at: at(14, 2), text: 'Exports should not be able to starve the API.' },
      { id: 'idx-02', project_id: 'p-ia', title: 'Rate-limit the search endpoint', state: 'CAPTURED', at: at(14, 3), text: 'Same as exports, for search.' },
      { id: 'idx-03', project_id: 'p-inv', title: 'Export the invoice list as PDF', state: 'CAPTURED', at: at(13, 50), text: 'Like the CSV export, but a printable PDF.' },
      { id: 'idx-04', project_id: 'p-long', title: 'Let translators preview their strings in context on a staging copy of every customer-facing page', state: 'CAPTURED', at: at(10, 5), text: 'Translators see the label where it will appear, not in a spreadsheet.' },
      { id: 'idx-05', project_id: 'p-uni', title: 'Menükarte als PDF — 印刷用', state: 'PARKED', at: at(9, 30), text: 'A printable menu in German and Japanese.' },
      { id: 'idx-06', project_id: 'p-www2', title: 'Redirect every legacy page to its new address', state: 'CAPTURED', at: at(8, 15), text: 'No legacy URL should 404.' },
      { id: 'idx-07', project_id: 'p-www', title: 'A dark theme for the blog', state: 'CAPTURED', at: at(12, 50), text: 'The docs idea, for the blog.' },
      { id: 'idx-08', project_id: null, title: 'A changelog bot for every repository', state: 'CAPTURED', at: at(7, 58), text: 'Write the changelog entry from the merged missions.' });
  }
})();
