/* LV2-0 fixture: one synthetic Tuesday afternoon, shaped like V1's own reads. NOT product code.
 *
 * Every field below exists in V1 Core today unless it is marked `proposed:` — those are the
 * facts the context proposal (LE-2) says Core would need, and the lab renders them only with
 * ?ctx=proposed, visibly marked. Field names follow the V1 schemas they come from:
 *   Mission{title, objective, project_id, state, integration_branch, integration_head}
 *   Project{name}, Repository{path, kind, default_branch, last_revision}
 *   LiveItem{task_title, task_state, workdir, branch, waits_on}, Execution{started_at}
 *   Verification{state, checks[{name, result, exit_code}]}, Approval presented{...}
 *   events: mission./execution./verification.state_changed, checkpoint.created{files_changed}
 * Times are minutes since local midnight. ?corpus=diag reproduces the V1 diagnosis capture
 * (D-1: four plan approvals, nothing running) to calibrate the V1 replica against reality.
 */
(function () {
  'use strict';
  const h = (hh, mm) => hh * 60 + mm;
  const NOW = h(15, 12);
  const projects = {
    'p-arch': { name: 'archeus', repos: [{ path: 'D:\\Claude', kind: 'repo', default_branch: 'main', last_revision: '8fe7ce3' }],
      proposed: { remote: 'github.com/babarmuhammad/archeus', provider: 'GitHub' } },
    'p-www': { name: 'website', repos: [{ path: 'D:\\repos\\archeus-site', kind: 'repo', default_branch: 'main', last_revision: '41c09ab' }],
      proposed: { remote: 'github.com/babarmuhammad/archeus-site', provider: 'GitHub' } },
    'p-inv': { name: 'invoicing', repos: [{ path: 'D:\\work\\invoicing', kind: 'repo', default_branch: 'develop', last_revision: 'c77d2e1' },
      { path: 'D:\\work\\invoicing\\vendor\\ledger', kind: 'submodule', default_branch: 'main', last_revision: '09aa4f2' }],
      proposed: { remote: 'gitlab.com/k2k/invoicing', provider: 'GitLab' } },
  };
  const POLICY = 'profile:standard@2:USER:deploy (ASK, USER); builtin:floor:deploy-prod (ASK, GLOBAL, locked)';
  const POLICY_W = 'profile:standard@2:USER:write (ASK, USER)';
  const iso = (min) => `2026-10-06T${String(Math.floor(min / 60) - 2).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}:11.148Z`;
  const M = [
    { id: 'm-91d2', title: 'Deploy release notes to staging', objective: 'The 1.9 release notes are live on staging and the smoke test passes',
      project_id: 'p-www', state: 'APPROVAL_REQUIRED', integration_branch: 'archeus/m-91d2', integration_head: '41c09ab', created: h(14, 31),
      approval: { id: 'ap-1', kind: 'plan', plan_version: 2, action_class: 'deploy', target: 'task:deploy', policy: POLICY,
        expires: NOW + 8, since: h(14, 58), consequence: 'deploys to staging', allowed: ['approve', 'reject', 'request_changes'],
        changed: 'v2 adds a smoke test after the deploy (you asked for it at 14:40)',
        asked: 'Publish the 1.9 release notes to staging', said: 'Plan v2 is ready: 3 tasks; the last one deploys', tools: 'none — planning only',
        what: 'Build the site, deploy it to staging, then run the smoke test against staging.',
        why: 'Deploying is an action your policy asks about every time, and deploying to production is locked.',
        proposed: { environment: 'staging' } },
      tasks: [['Build the site', 'PENDING'], ['Deploy to staging', 'PENDING'], ['Smoke-test staging', 'PENDING']] },
    { id: 'm-2b7f', title: 'Upgrade the auth library', objective: 'auth-lib 5 everywhere; the login suite passes', project_id: 'p-inv',
      state: 'APPROVAL_REQUIRED', integration_branch: 'archeus/m-2b7f', integration_head: 'c77d2e1', created: h(14, 50),
      approval: { id: 'ap-2', kind: 'plan', plan_version: 1, action_class: 'write', target: 'task:upgrade', policy: POLICY_W,
        expires: NOW + 40, since: h(15, 2), consequence: 'changes 14 files', allowed: ['approve', 'reject', 'request_changes'],
        changed: null, asked: 'Move invoicing to auth-lib 5', said: 'Plan v1: 2 tasks, 14 files', tools: 'read 31 files',
        what: 'Rewrite the 14 call sites for auth-lib 5, then run the login suite.',
        why: 'Writing outside a mission worktree needs your approval under the standard profile.' },
      tasks: [['Rewrite call sites', 'PENDING'], ['Run the login suite', 'PENDING']] },
    { id: 'm-5c30', title: 'Index the invoices table', objective: 'Invoice lookups by customer under 50 ms', project_id: 'p-inv',
      state: 'REVIEWING', integration_branch: 'archeus/m-5c30', integration_head: 'e19b004', created: h(12, 10),
      review: { since: h(14, 21), consequence: 'executed and verified · 3 of 3 checks passed · nothing merged yet' },
      verification: { state: 'PASSED', checks: [['migrations apply', 'passed', 0], ['lookup benchmark', 'passed', 0], ['full test suite', 'passed', 0]] },
      tasks: [['Add the index', 'SUCCEEDED'], ['Benchmark', 'SUCCEEDED']] },
    { id: 'm-4c1e', title: 'Fix the flaky date test', objective: 'test_date_rollover passes 50 runs in a row', project_id: 'p-arch',
      state: 'EXECUTING', integration_branch: 'archeus/m-4c1e', integration_head: '2f9e1a0', created: h(14, 40),
      live: { task_title: 'Run the date suite 50 times', task_state: 'RUNNING', workdir: 'D:\\Claude\\.archeus\\worktrees\\m-4c1e', branch: 'archeus/m-4c1e', started_at: h(14, 52), step: 4, of: 7,
        proposed: { operation: 'pytest tests/v1/unit/test_dates.py — run 31 of 50' } },
      tasks: [['Reproduce', 'SUCCEEDED'], ['Find the cause', 'SUCCEEDED'], ['Patch the clock', 'SUCCEEDED'], ['Run the date suite 50 times', 'RUNNING'], ['Lint', 'PENDING'], ['Verify', 'PENDING'], ['Summarise', 'PENDING']] },
    { id: 'm-77aa', title: 'Rename the billing module', objective: 'billing → ledger with no behaviour change', project_id: 'p-inv',
      state: 'VERIFYING', integration_branch: 'archeus/m-77aa', integration_head: '5a0c3d9', created: h(13, 5),
      live: { task_title: 'Verify', task_state: 'RUNNING', workdir: 'D:\\work\\invoicing\\.archeus\\worktrees\\m-77aa', branch: 'archeus/m-77aa', started_at: h(15, 0), step: 3, of: 3 },
      verification: { state: 'RUNNING', checks: [['type check', 'passed', 0], ['unit tests', 'passed', 0], ['import graph unchanged', 'running', null], ['full test suite', 'pending', null]] },
      tasks: [['Rename', 'SUCCEEDED'], ['Fix imports', 'SUCCEEDED'], ['Verify', 'RUNNING']] },
    { id: 'm-c3e9', title: 'Write the migration for invoices', objective: 'The invoices migration applies and rolls back cleanly', project_id: 'p-inv',
      state: 'BLOCKED', integration_branch: 'archeus/m-c3e9', integration_head: 'b2d81f0', created: h(11, 2),
      because: ['Verification failed at 13:48', 'check “rollback” failed (exit 1): test_migration_rollback', 'the down-migration drops a column the up-migration never created'],
      verification: { state: 'FAILED', checks: [['migration applies', 'passed', 0], ['rollback', 'failed', 1], ['full test suite', 'passed', 0]] },
      next: ['Open the failing check', 'Ask Archeus to fix the down-migration', 'Cancel the mission'],
      tasks: [['Write the migration', 'SUCCEEDED'], ['Verify', 'FAILED']] },
    { id: 'm-0f61', title: 'Profile the startup path', objective: 'Know where the 1.4 s startup goes', project_id: 'p-arch',
      state: 'FAILED', created: h(10, 30), failed_at: h(11, 20),
      because: ['The execution ended at 11:20', 'the harness stopped producing output for 10 minutes and was stopped'],
      next: ['Retry', 'Open the execution log'], tasks: [['Profile', 'FAILED']] },
    { id: 'm-1a08', title: 'Tidy the release checklist', objective: 'One checklist, no duplicates', project_id: 'p-www', state: 'DONE', created: h(9, 40), done_at: h(10, 51),
      verification: { state: 'PASSED', checks: [['links resolve', 'passed', 0], ['site builds', 'passed', 0]] }, tasks: [['Tidy', 'SUCCEEDED']] },
    { id: 'm-e4b2', title: 'Bump the docs theme', objective: 'Docs on theme 3.2', project_id: 'p-www', state: 'DONE', created: h(8, 55), done_at: h(9, 30),
      verification: { state: 'PASSED', checks: [['site builds', 'passed', 0]] }, tasks: [['Bump', 'SUCCEEDED']] },
    { id: 'm-6d4c', title: 'Draft the P21 activity record', objective: 'An ADR draft for the activity record', project_id: 'p-arch', state: 'PLANNING', created: h(15, 9), tasks: [] },
  ];
  // the day's record: every mark on the day's light comes from one of these (LE-3)
  const E = [];
  const ev = (mid, at, kind, x) => E.push(Object.assign({ seq: E.length + 1, mission_id: mid, at, kind }, x || {}));
  ev('m-e4b2', h(8, 55), 'mission.created'); ev('m-e4b2', h(9, 2), 'execution.started'); ev('m-e4b2', h(9, 18), 'checkpoint.created', { files: 3 });
  ev('m-e4b2', h(9, 22), 'verification.started'); ev('m-e4b2', h(9, 30), 'verification.passed'); ev('m-e4b2', h(9, 30), 'mission.done');
  ev('m-1a08', h(9, 40), 'mission.created'); ev('m-1a08', h(9, 44), 'approval.decided', { decision: 'approve' }); ev('m-1a08', h(9, 45), 'execution.started');
  ev('m-1a08', h(10, 31), 'checkpoint.created', { files: 2 }); ev('m-1a08', h(10, 40), 'verification.started'); ev('m-1a08', h(10, 51), 'verification.passed'); ev('m-1a08', h(10, 51), 'mission.done');
  ev('m-0f61', h(10, 30), 'mission.created'); ev('m-0f61', h(10, 36), 'execution.started'); ev('m-0f61', h(11, 20), 'execution.failed');
  ev('m-c3e9', h(11, 2), 'mission.created'); ev('m-c3e9', h(11, 9), 'approval.decided', { decision: 'approve' }); ev('m-c3e9', h(11, 10), 'execution.started');
  ev('m-c3e9', h(12, 58), 'checkpoint.created', { files: 2 }); ev('m-c3e9', h(13, 30), 'verification.started'); ev('m-c3e9', h(13, 48), 'verification.failed'); ev('m-c3e9', h(13, 48), 'mission.blocked');
  ev('m-5c30', h(12, 10), 'mission.created'); ev('m-5c30', h(12, 15), 'approval.decided', { decision: 'approve' }); ev('m-5c30', h(12, 16), 'execution.started');
  ev('m-5c30', h(13, 50), 'checkpoint.created', { files: 4 }); ev('m-5c30', h(14, 0), 'verification.started'); ev('m-5c30', h(14, 21), 'verification.passed'); ev('m-5c30', h(14, 21), 'review.requested');
  ev('m-77aa', h(13, 5), 'mission.created'); ev('m-77aa', h(13, 12), 'approval.decided', { decision: 'approve' }); ev('m-77aa', h(13, 13), 'execution.started');
  ev('m-77aa', h(14, 49), 'checkpoint.created', { files: 38 }); ev('m-77aa', h(15, 0), 'verification.started');
  ev('m-91d2', h(14, 31), 'mission.created'); ev('m-91d2', h(14, 36), 'approval.requested'); ev('m-91d2', h(14, 40), 'approval.decided', { decision: 'request_changes' }); ev('m-91d2', h(14, 58), 'approval.requested');
  ev('m-4c1e', h(14, 40), 'mission.created'); ev('m-4c1e', h(14, 44), 'approval.decided', { decision: 'approve' }); ev('m-4c1e', h(14, 45), 'execution.started');
  ev('m-4c1e', h(14, 52), 'checkpoint.created', { files: 1 }); ev('m-4c1e', h(15, 8), 'execution.output');
  ev('m-2b7f', h(14, 50), 'mission.created'); ev('m-2b7f', h(15, 2), 'approval.requested');
  ev('m-6d4c', h(15, 9), 'mission.created');

  const diag = () => ['Deploy release notes to staging', 'Fix the flaky date test', 'Upgrade the auth library', 'Write the migration for invoices'].map((t, i) => ({
    id: 'd-' + i, title: t, objective: 'Done when tests pass', project_id: null, state: 'APPROVAL_REQUIRED', created: NOW,
    approval: { id: 'da-' + i, kind: 'plan', plan_version: 1, action_class: 'deploy', target: 'task:work', policy: POLICY, expires: NOW + 1440, since: NOW,
      consequence: 'runs 1 task on the fake harness', allowed: ['approve', 'reject', 'request_changes'], changed: null, asked: t, said: 'Plan v1: 1 task', tools: 'none',
      what: 'Run one task on the fake harness.', why: 'Deploying is an action your policy asks about every time.' },
    tasks: [['Do the work', 'PENDING']] }));

  /*<stress>*/
  // LV2-1 W0: ?corpus=stress adds the cases the context study needs, on top of the busy day:
  // three missions with the same title in one project (two repositories, one of them a submodule;
  // the third has no workdir, so its repository cannot be derived), a long title in a long-named
  // project, and Unicode in a project, a path and a title. Same honesty rules: V1 fields only.
  const stress = () => {
    const P = { 'p-long': { name: 'customer-portal-internationalisation', repos: [{ path: 'D:\\repos\\customer-portal-internationalisation', kind: 'repo', default_branch: 'main', last_revision: '6e0a7d2' }],
      proposed: { remote: 'github.com/example-org/customer-portal-internationalisation', provider: 'GitHub' } },
    'p-uni': { name: 'café-menü', repos: [{ path: 'D:\\work\\café-menü', kind: 'repo', default_branch: 'main', last_revision: '0b9c4a1' }],
      proposed: { remote: 'codeberg.org/example/cafe-menu', provider: 'Codeberg' } } };
    const same = 'Update the currency formatter';
    const S = [
      { id: 's-1a40', title: same, objective: 'Amounts render with the locale’s grouping', project_id: 'p-inv', state: 'EXECUTING', integration_branch: 'archeus/s-1a40', integration_head: '4d7e2b1', created: h(14, 2),
        live: { task_title: 'Format amounts', task_state: 'RUNNING', workdir: 'D:\\work\\invoicing\\.archeus\\worktrees\\s-1a40', branch: 'archeus/s-1a40', started_at: h(14, 20), step: 2, of: 3 },
        tasks: [['Find call sites', 'SUCCEEDED'], ['Format amounts', 'RUNNING'], ['Verify', 'PENDING']] },
      { id: 's-2b17', title: same, objective: 'Ledger totals render with the locale’s grouping', project_id: 'p-inv', state: 'EXECUTING', integration_branch: 'archeus/s-2b17', integration_head: '91a3c0e', created: h(14, 6),
        live: { task_title: 'Format amounts', task_state: 'RUNNING', workdir: 'D:\\work\\invoicing\\vendor\\ledger\\.archeus\\worktrees\\s-2b17', branch: 'archeus/s-2b17', started_at: h(14, 25), step: 2, of: 3 },
        tasks: [['Find call sites', 'SUCCEEDED'], ['Format amounts', 'RUNNING'], ['Verify', 'PENDING']] },
      { id: 's-3c02', title: same, objective: 'Receipt amounts render with the locale’s grouping', project_id: 'p-inv', state: 'DONE', integration_branch: 'archeus/s-3c02', integration_head: '2e8f6d4', created: h(9, 10), done_at: h(10, 2),
        verification: { state: 'PASSED', checks: [['unit tests', 'passed', 0], ['full test suite', 'passed', 0]] }, tasks: [['Format amounts', 'SUCCEEDED']] },
      { id: 's-4d9e', title: 'Migrate every invoice PDF template to the new rendering pipeline without changing a single pixel of output', objective: 'All 41 templates render byte-identical PDFs on the new pipeline',
        project_id: 'p-long', state: 'VERIFYING', integration_branch: 'archeus/s-4d9e', integration_head: 'a1f5c3e', created: h(12, 40),
        live: { task_title: 'Compare every rendered PDF with its golden file', task_state: 'RUNNING', workdir: 'D:\\repos\\customer-portal-internationalisation\\.archeus\\worktrees\\s-4d9e', branch: 'archeus/s-4d9e', started_at: h(14, 48), step: 5, of: 5 },
        verification: { state: 'RUNNING', checks: [['templates compile', 'passed', 0], ['golden PDFs identical', 'running', null]] },
        tasks: [['Inventory templates', 'SUCCEEDED'], ['Port the layout engine', 'SUCCEEDED'], ['Port the fonts', 'SUCCEEDED'], ['Port the templates', 'SUCCEEDED'], ['Compare every rendered PDF with its golden file', 'RUNNING']] },
      { id: 's-5e31', title: 'Übersetzungen für das Kundenportal prüfen — 日本語ラベル', objective: 'Every German and Japanese label fits its control', project_id: 'p-uni', state: 'DONE',
        integration_branch: 'archeus/s-5e31', integration_head: 'c3b0e97', created: h(8, 20), done_at: h(9, 5),
        verification: { state: 'PASSED', checks: [['labels fit (de)', 'passed', 0], ['labels fit (ja)', 'passed', 0]] }, tasks: [['Prüfen', 'SUCCEEDED']] },
    ];
    const SE = [];
    let seq = 500;
    const sev = (mid, at, kind, x) => SE.push(Object.assign({ seq: ++seq, mission_id: mid, at, kind }, x || {}));
    sev('s-5e31', h(8, 20), 'mission.created'); sev('s-5e31', h(8, 30), 'execution.started'); sev('s-5e31', h(8, 50), 'checkpoint.created', { files: 6 }); sev('s-5e31', h(9, 5), 'verification.passed'); sev('s-5e31', h(9, 5), 'mission.done');
    sev('s-3c02', h(9, 10), 'mission.created'); sev('s-3c02', h(9, 15), 'execution.started'); sev('s-3c02', h(9, 40), 'checkpoint.created', { files: 2 }); sev('s-3c02', h(10, 2), 'verification.passed'); sev('s-3c02', h(10, 2), 'mission.done');
    sev('s-4d9e', h(12, 40), 'mission.created'); sev('s-4d9e', h(12, 45), 'execution.started'); sev('s-4d9e', h(14, 30), 'checkpoint.created', { files: 41 }); sev('s-4d9e', h(14, 48), 'verification.started');
    sev('s-1a40', h(14, 2), 'mission.created'); sev('s-1a40', h(14, 20), 'execution.started');
    sev('s-2b17', h(14, 6), 'mission.created'); sev('s-2b17', h(14, 25), 'execution.started');
    return { P, S, SE };
  };
  /*</stress>*/

  /*<lookalike>*/
  // LV2-1 W0: ?fx=2 and ?fx=3 are the same day with different content, so a participant can meet
  // each variant without recognising it: every state, count, time, check result and structure is
  // identical; only names, paths, branches and commits change. Exact-string replacement over the
  // fixture, so a string not listed keeps its fx=1 value. Mission ids (routes) do not change.
  const LOOK = {
    2: [['archeus', 'mobile-app'], ['website', 'docs'], ['invoicing', 'payments'], ['D:\\Claude', 'D:\\repos\\mobile-app'], ['D:\\repos\\archeus-site', 'D:\\repos\\help-centre'],
      ['D:\\work\\invoicing', 'D:\\work\\payments'], ['D:\\work\\invoicing\\vendor\\ledger', 'D:\\work\\payments\\vendor\\fx-rates'],
      ['github.com/babarmuhammad/archeus', 'github.com/example-org/mobile-app'], ['github.com/babarmuhammad/archeus-site', 'github.com/example-org/help-centre'], ['gitlab.com/k2k/invoicing', 'gitlab.com/example/payments'],
      ['Deploy release notes to staging', 'Publish the help centre to preview'], ['Upgrade the auth library', 'Upgrade the payments SDK'], ['Index the invoices table', 'Cache the exchange rates'],
      ['Fix the flaky date test', 'Fix the flaky login test'], ['Rename the billing module', 'Rename the checkout module'], ['Write the migration for invoices', 'Write the migration for refunds'],
      ['Profile the startup path', 'Profile the cold start'], ['Tidy the release checklist', 'Tidy the style guide'], ['Bump the docs theme', 'Bump the icon set'], ['Draft the P21 activity record', 'Draft the offline-mode note'],
      ['The 1.9 release notes are live on staging and the smoke test passes', 'The help centre is live on preview and the link check passes'], ['auth-lib 5 everywhere; the login suite passes', 'payments-sdk 3 everywhere; the checkout suite passes'],
      ['Invoice lookups by customer under 50 ms', 'Rate lookups under 20 ms'], ['test_date_rollover passes 50 runs in a row', 'test_login_timeout passes 50 runs in a row'], ['billing → ledger with no behaviour change', 'checkout → basket with no behaviour change'],
      ['The invoices migration applies and rolls back cleanly', 'The refunds migration applies and rolls back cleanly'], ['Know where the 1.4 s startup goes', 'Know where the 2.1 s cold start goes'],
      ['One checklist, no duplicates', 'One style guide, no duplicates'], ['Docs on theme 3.2', 'Icons on set 4.0'], ['An ADR draft for the activity record', 'A design note for offline mode'],
      ['Publish the 1.9 release notes to staging', 'Publish the new help centre to preview'], ['Build the site, deploy it to staging, then run the smoke test against staging.', 'Build the help centre, deploy it to preview, then run the link check against preview.'],
      ['v2 adds a smoke test after the deploy (you asked for it at 14:40)', 'v2 adds a link check after the deploy (you asked for it at 14:40)'], ['staging', 'preview'], ['deploys to staging', 'deploys to preview'],
      ['Move invoicing to auth-lib 5', 'Move payments to payments-sdk 3'], ['Plan v1: 2 tasks, 14 files', 'Plan v1: 2 tasks, 9 files'], ['Rewrite the 14 call sites for auth-lib 5, then run the login suite.', 'Rewrite the 9 call sites for payments-sdk 3, then run the checkout suite.'],
      ['changes 14 files', 'changes 9 files'], ['read 31 files', 'read 22 files'], ['lookup benchmark', 'rate benchmark'], ['check “rollback” failed (exit 1): test_migration_rollback', 'check “rollback” failed (exit 1): test_refund_rollback'],
      ['Build the site', 'Build the help centre'], ['Deploy to staging', 'Deploy to preview'], ['Smoke-test staging', 'Link-check preview'], ['Run the login suite', 'Run the checkout suite'], ['Add the index', 'Add the cache'],
      ['Run the date suite 50 times', 'Run the login suite 50 times'], ['Patch the clock', 'Patch the timeout'], ['pytest tests/v1/unit/test_dates.py — run 31 of 50', 'pytest tests/test_login.py — run 31 of 50'],
      ['D:\\Claude\\.archeus\\worktrees\\m-4c1e', 'D:\\repos\\mobile-app\\.archeus\\worktrees\\m-4c1e'], ['D:\\work\\invoicing\\.archeus\\worktrees\\m-77aa', 'D:\\work\\payments\\.archeus\\worktrees\\m-77aa'],
      ['archeus/m-91d2', 'archeus/m-6f13'], ['archeus/m-2b7f', 'archeus/m-0c88'], ['archeus/m-5c30', 'archeus/m-71d4'], ['archeus/m-4c1e', 'archeus/m-8a2d'], ['archeus/m-77aa', 'archeus/m-3e91'], ['archeus/m-c3e9', 'archeus/m-b52a'],
      ['41c09ab', '7d3e0c2'], ['c77d2e1', 'a90f4b7'], ['e19b004', '3c6d1e8'], ['2f9e1a0', 'd41b7a9'], ['5a0c3d9', '86e2f0b'], ['b2d81f0', 'f07c9a3'], ['8fe7ce3', '5b18e6d'], ['09aa4f2', 'e2c4b91']],
    3: [['archeus', 'harbor'], ['website', 'brochure'], ['invoicing', 'stockroom'], ['D:\\Claude', 'D:\\repos\\harbor'], ['D:\\repos\\archeus-site', 'D:\\repos\\brochure-site'],
      ['D:\\work\\invoicing', 'D:\\work\\stockroom'], ['D:\\work\\invoicing\\vendor\\ledger', 'D:\\work\\stockroom\\vendor\\barcode'],
      ['github.com/babarmuhammad/archeus', 'github.com/example-org/harbor'], ['github.com/babarmuhammad/archeus-site', 'github.com/example-org/brochure-site'], ['gitlab.com/k2k/invoicing', 'gitlab.com/example/stockroom'],
      ['Deploy release notes to staging', 'Publish the spring catalogue to beta'], ['Upgrade the auth library', 'Upgrade the logging library'], ['Index the invoices table', 'Index the stock table'],
      ['Fix the flaky date test', 'Fix the flaky upload test'], ['Rename the billing module', 'Rename the orders module'], ['Write the migration for invoices', 'Write the migration for returns'],
      ['Profile the startup path', 'Profile the search path'], ['Tidy the release checklist', 'Tidy the product checklist'], ['Bump the docs theme', 'Bump the brochure font'], ['Draft the P21 activity record', 'Draft the barcode scanner note'],
      ['The 1.9 release notes are live on staging and the smoke test passes', 'The spring catalogue is live on beta and the page check passes'], ['auth-lib 5 everywhere; the login suite passes', 'log-kit 7 everywhere; the API suite passes'],
      ['Invoice lookups by customer under 50 ms', 'Stock lookups by SKU under 30 ms'], ['test_date_rollover passes 50 runs in a row', 'test_upload_resume passes 50 runs in a row'], ['billing → ledger with no behaviour change', 'orders → sales with no behaviour change'],
      ['The invoices migration applies and rolls back cleanly', 'The returns migration applies and rolls back cleanly'], ['Know where the 1.4 s startup goes', 'Know where the 900 ms search goes'],
      ['One checklist, no duplicates', 'One product checklist, no duplicates'], ['Docs on theme 3.2', 'Brochure on font 2.1'], ['An ADR draft for the activity record', 'A design note for the barcode scanner'],
      ['Publish the 1.9 release notes to staging', 'Publish the spring catalogue to beta'], ['Build the site, deploy it to staging, then run the smoke test against staging.', 'Build the catalogue, deploy it to beta, then run the page check against beta.'],
      ['v2 adds a smoke test after the deploy (you asked for it at 14:40)', 'v2 adds a page check after the deploy (you asked for it at 14:40)'], ['staging', 'beta'], ['deploys to staging', 'deploys to beta'],
      ['Move invoicing to auth-lib 5', 'Move stockroom to log-kit 7'], ['Plan v1: 2 tasks, 14 files', 'Plan v1: 2 tasks, 17 files'], ['Rewrite the 14 call sites for auth-lib 5, then run the login suite.', 'Rewrite the 17 call sites for log-kit 7, then run the API suite.'],
      ['changes 14 files', 'changes 17 files'], ['read 31 files', 'read 40 files'], ['lookup benchmark', 'SKU benchmark'], ['check “rollback” failed (exit 1): test_migration_rollback', 'check “rollback” failed (exit 1): test_returns_rollback'],
      ['Build the site', 'Build the catalogue'], ['Deploy to staging', 'Deploy to beta'], ['Smoke-test staging', 'Page-check beta'], ['Run the login suite', 'Run the API suite'], ['Add the index', 'Add the SKU index'],
      ['Run the date suite 50 times', 'Run the upload suite 50 times'], ['Patch the clock', 'Patch the resume logic'], ['pytest tests/v1/unit/test_dates.py — run 31 of 50', 'pytest tests/test_upload.py — run 31 of 50'],
      ['D:\\Claude\\.archeus\\worktrees\\m-4c1e', 'D:\\repos\\harbor\\.archeus\\worktrees\\m-4c1e'], ['D:\\work\\invoicing\\.archeus\\worktrees\\m-77aa', 'D:\\work\\stockroom\\.archeus\\worktrees\\m-77aa'],
      ['archeus/m-91d2', 'archeus/m-2d70'], ['archeus/m-2b7f', 'archeus/m-e815'], ['archeus/m-5c30', 'archeus/m-4b9c'], ['archeus/m-4c1e', 'archeus/m-c06f'], ['archeus/m-77aa', 'archeus/m-59d3'], ['archeus/m-c3e9', 'archeus/m-a7e2'],
      ['41c09ab', 'e6a2d91'], ['c77d2e1', '18c5f3a'], ['e19b004', '9f02b6d'], ['2f9e1a0', '0d8a4c5'], ['5a0c3d9', 'b7e19f2'], ['b2d81f0', '3a6c0e8'], ['8fe7ce3', 'c41d7b0'], ['09aa4f2', '72f8a3c']],
  };
  const swap = (o, map) => (typeof o === 'string' ? (map.has(o) ? map.get(o) : o) : Array.isArray(o) ? o.map((x) => swap(x, map))
    : o && typeof o === 'object' ? Object.fromEntries(Object.entries(o).map(([k, v]) => [k, k === 'id' || k === 'project_id' || k === 'mission_id' || k === 'state' ? v : swap(v, map)])) : o);
  /*</lookalike>*/

  const Q = new URLSearchParams(location.search);
  const corpus = Q.get('corpus');
  let projectsOut = projects, missionsOut = corpus === 'diag' ? diag() : M, eventsOut = corpus === 'diag' ? [] : E;
  if (corpus === 'stress') { const s = stress(); projectsOut = Object.assign({}, projects, s.P); missionsOut = M.concat(s.S); eventsOut = E.concat(s.SE); }
  if (LOOK[Q.get('fx')]) { const map = new Map(LOOK[Q.get('fx')]); projectsOut = swap(projectsOut, map); missionsOut = swap(missionsOut, map); }
  window.FX = { NOW, projects: projectsOut, missions: missionsOut, events: eventsOut, iso, POLICY };
  // the day before, for the one-scale-across-days check (LE-3): a quiet day
  window.FX.yesterday = [['m-y1', 'p-arch', h(10, 5), h(10, 40), 'done'], ['m-y2', 'p-www', h(16, 20), h(16, 52), 'done']];
})();
