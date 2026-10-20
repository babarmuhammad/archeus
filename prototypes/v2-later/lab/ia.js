/* LE-1 / LE-2 / LE-4: information architecture, mission context and the phone, as one lab.
 * NOT product code.
 *
 *   ?v=a  the V1 structure as built (Now / Work / World / Attention / Control; full cards; the
 *         conversation repeating each approval) — a replica, calibrated against the D-1 capture
 *   ?v=b  the three places (Now / Needs you / Missions) with the mission strip on the phone,
 *         a one-column desktop and the inspector as an overlay
 *   ?v=c  B with the container-driven desktop composition (list + inspector from 1,100,
 *         list + mission + evidence inspector from 1,700)
 *   ?ctx=v1 (default) only facts V1 Core records; ?ctx=proposed adds the LE-2 data
 *         requirements, each visibly marked "proposed"
 * Every answer to the eight LE-1 questions carries data-q="qN"; window.PATHS says which clicks
 * reach it from Now, per variant and device, so tools/ia_probe.py can walk them.
 */
(function () {
  'use strict';
  const Q = new URLSearchParams(location.search);
  const V = Q.get('v') || 'b';
  const CTX = Q.get('ctx') || 'v1';
  const root = document.documentElement;
  root.dataset.v = V;
  if (Q.get('text')) root.dataset.text = Q.get('text');
  if (Q.get('motion')) root.dataset.motion = Q.get('motion');
  const FX = window.FX, F = window.FIG;
  const phone = () => innerWidth < 600;
  const DP = Q.get('dp') !== '0' && V !== 'a'; // A is the V1 replica: it never gets the design pass
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const clock = (m) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
  const dur = (m) => (m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60 ? (m % 60) + ' min' : ''}`.trim());
  const ago = (m) => { const d = FX.NOW - m; return d < 1 ? 'just now' : d < 60 ? `${d} min ago` : `${Math.floor(d / 60)} h ago`; };
  const byId = Object.fromEntries(FX.missions.map((m) => [m.id, m]));
  const FIGST = { APPROVAL_REQUIRED: 'needs_you', EXECUTING: 'active', VERIFYING: 'verifying', REVIEWING: 'reviewing', BLOCKED: 'blocked',
    FAILED: 'failed', DONE: 'done', PLANNING: 'planning' };
  const fig = (m) => { const st = FIGST[m.state]; return `<span class="figslot" data-role="${F.ROLE[st]}" title="${F.WORD[st]}">${F.C(st, 16)}</span><span class="sr">${F.WORD[st]}.</span>`; };
  const word = (m) => F.WORD[FIGST[m.state]];
  const needs = FX.missions.filter((m) => m.approval || m.state === 'REVIEWING');
  const running = FX.missions.filter((m) => m.state === 'EXECUTING' || m.state === 'VERIFYING');
  const stopped = FX.missions.filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED');
  const done = FX.missions.filter((m) => m.state === 'DONE');
  const upcoming = FX.missions.filter((m) => m.state === 'PLANNING');
  const changes = FX.events.filter((e) => e.at >= FX.NOW - 45);

  // ------------------------------------------------------------- LE-2: mission context
  /** Every context fact with its provenance: known (a Core field), derived (computed from
   * known fields, and says how), proposed (needs a data requirement), unknown (not recorded). */
  function context(m) {
    const P = FX.projects[m.project_id];
    const L = m.live;
    const out = [];
    const add = (k, label, value, prov, src) => out.push({ k, label, value, prov, src });
    if (P) add('project', 'Project', P.name, 'known', 'Project.name, joined on Mission.project_id (V1 reads carry only the id)');
    else add('project', 'Project', null, 'unknown', 'Mission.project_id is empty');
    let repo = null;
    // the LONGEST repository path containing the workdir: a submodule lies inside its parent's path,
    // and the first match attributed submodule work to the parent (LV2-1 W0)
    if (P && L && L.workdir) repo = P.repos.filter((r) => (L.workdir.toLowerCase() + '\\').startsWith(r.path.toLowerCase() + '\\')).sort((a, b) => b.path.length - a.path.length)[0];
    if (repo) add('repo', 'Repository', repo.path, 'derived', 'Execution.workdir lies under Repository.path');
    else if (P && P.repos.length === 1) { repo = P.repos[0]; add('repo', 'Repository', repo.path, 'derived', "the project's only Repository"); }
    else if (P) add('repo', 'Repository', null, 'unknown', `a mission has no repository link and ${P.name} has ${P.repos.length}`);
    if (P && CTX === 'proposed') add('remote', 'Remote', `${P.proposed.provider} · ${P.proposed.remote}`, 'proposed', 'DR-2 Repository.remote_url');
    else add('remote', 'Remote', null, 'unknown', 'Repository has no remote_url; provider and owner are not modelled');
    if (m.integration_branch) add('branch', 'Branch', m.integration_branch, 'known', 'Mission.integration_branch');
    if (repo && m.integration_branch) add('base', 'Into', repo.default_branch, 'derived', 'Repository.default_branch; the mission records its fork commit, not a branch name');
    if (m.integration_head) add('head', 'Commit', m.integration_head, 'known', 'Mission.integration_head');
    if (L) {
      add('workdir', 'Working directory', L.workdir, 'known', 'Execution.workdir (open field; never rendered in V1)');
      add('where', 'Runs', 'on this computer', 'derived', 'V1 executes on the local node only (ExecutionNode is never written)');
      add('task', 'Task', `${L.task_title} · step ${L.step} of ${L.of}`, 'derived', 'LiveItem.task_title; step from the plan\'s task order');
      if (CTX === 'proposed' && L.proposed) add('op', 'Doing', L.proposed.operation, 'proposed', 'DR-6 the current operation (P21 activity record)');
      else add('op', 'Doing', null, 'unknown', 'Core records the task, not the operation inside it (P21)');
      add('elapsed', 'Running for', dur(FX.NOW - L.started_at), 'derived', 'now − Execution.started_at');
    }
    if (m.approval) {
      if (CTX === 'proposed' && m.approval.proposed) add('env', 'Environment', m.approval.proposed.environment, 'proposed', 'DR-4 keep Action.environment in the approval record');
      else if (m.approval.action_class === 'deploy') add('env', 'Environment', null, 'unknown', 'Core knows it at the action; presented.what drops it');
    }
    if (m.verification) add('verify', 'Verification', verdictOf(m.verification), 'known', 'Verification.state and checks[]');
    return out;
  }
  function verdictOf(v) {
    const n = v.checks.length, ok = v.checks.filter((c) => c[1] === 'passed').length;
    if (v.state === 'PASSED') return `verified · ${ok} of ${n} checks passed`;
    if (v.state === 'FAILED') return `not verified · ${n - ok} of ${n} checks failed`;
    return `verifying · ${ok} of ${n} checks passed so far`;
  }
  /** The row's context: one line, known and derived only, never a badge per fact. LV2-1 W3 arms
   * (?ctxrow=): p project · pb + branch (LV2-0's desktop row) · prb + repository · pbc + commit.
   * A field that is unknown for this mission is left out of the row, never filled in; the context
   * block one level down says it is not recorded. */
  const CTXROW = Q.get('ctxrow');
  function ctxLine(m, set) {
    const c = Object.fromEntries(context(m).map((f) => [f.k, f]));
    const want = set || CTXROW || 'pb';
    const bits = [];
    if (c.project && c.project.value) bits.push(esc(c.project.value));
    if (want === 'prb' && c.repo && c.repo.value) bits.push(`<span class="mono" data-ctx="repo">${esc(c.repo.value.split('\\').pop())}</span>`);
    if (want !== 'p' && c.branch) bits.push(`<span class="mono" data-ctx="branch">${esc(c.branch.value)}</span>`);
    if (want === 'pbc' && c.head) bits.push(`<span class="mono" data-ctx="head">${esc(c.head.value)}</span>`);
    return bits.join(' · ');
  }
  // the phone row's context: the project only (LV2-0), unless an arm is being tested
  const phoneCtx = (m) => (CTXROW ? ctxLine(m) : esc(FX.projects[m.project_id]?.name || ''));
  function ctxBlock(m) {
    const facts = context(m);
    const shown = facts.filter((f) => f.value != null);
    const missing = facts.filter((f) => f.value == null);
    return `<section class="ctx" aria-label="Context"><h3>Context</h3><dl>${shown.map((f) => `<div data-prov="${f.prov}"><dt>${f.label}</dt><dd>${
      /path|branch|head|workdir|remote/.test(f.k) || f.k === 'repo' || f.k === 'head' ? `<span class="mono">${esc(f.value)}</span>` : esc(f.value)}${
      f.prov === 'derived' ? ` <span class="prov" title="${esc(f.src)}">derived</span>` : f.prov === 'proposed' ? ` <span class="prov proposed" title="${esc(f.src)}">proposed</span>` : ''}</dd></div>`).join('')}</dl>${
      missing.length ? `<p class="cap t3 notrec">Not recorded by Core: ${missing.map((f) => `<span title="${esc(f.src)}">${f.label.toLowerCase()}</span>`).join(', ')}.</p>` : ''}</section>`;
  }

  // ------------------------------------------------------------------ the human words
  const verbOf = (m) => (m.approval ? `Approve plan v${m.approval.plan_version}` : 'Review the result');
  const expires = (a) => { const d = a.expires - FX.NOW; return d < 60 ? `expires in ${d} min` : d < 1440 ? `expires in ${Math.round(d / 60)} h` : 'expires tomorrow'; };
  const consequence = (m) => (m.approval ? `${m.approval.consequence} · ${expires(m.approval)}` : m.review.consequence);
  const becauseShort = (m) => (m.because ? m.because[1] : '');
  function verdict() {
    const n = needs.length, r = running.length, s = stopped.length;
    if (!n && !r) return s ? `All quiet. ${s} stopped.` : 'All clear.';
    return [n ? `${n} need${n === 1 ? 's' : ''} you` : null, r ? `${r} running` : null, s ? `${s} stopped` : 'nothing failing'].filter(Boolean).join(' · ');
  }
  function subline() {
    const m = running[0];
    if (!m) return needs.length ? `Nothing is running. ${needs[0].title} is waiting for you.` : 'Nothing is running.';
    return `<span data-q="q1 q2">${esc(m.title)} <span class="t3">(${esc(FX.projects[m.project_id].name)})</span> is on step ${m.live.step} of ${m.live.of}: ${esc(m.live.task_title.toLowerCase())}.</span>`;
  }

  // ===================================================================== variant A
  const A = {
    top() {
      return `<header class="a-top"><span class="mark">⟁ Archeus</span><a href="#work">${running.length} running</a><a href="#attention">${needs.length} need you</a><a href="#control">1 client</a>
        <span class="a-desk"><button>Pause all</button><button class="a-stop">Emergency stop</button></span><span class="grow"></span><button class="a-go">Go to or tell… <kbd>Ctrl K</kbd></button><a class="a-phone" href="#control">Control</a></header>`;
    },
    nav(cur) {
      const it = [['now', 'Now'], ['work', 'Work'], ['world', 'World'], ['attention', 'Attention'], ['control', 'Control']];
      return `<nav class="a-nav">${it.map(([k, l]) => `<a href="#${k}" ${cur === k ? 'aria-current="page"' : ''} data-k="${k}">${l}${k === 'attention' ? ` <span class="badge">${needs.length}</span>` : ''}</a>`).join('')}</nav>`;
    },
    card(m) {
      const a = m.approval;
      if (!a) return `<article class="a-card" data-ap="${m.id}"><p><span data-role="active">●</span> Pending <strong>Review</strong> <span class="t3 r">${ago(m.review.since)}</span></p><p><strong>Review the result</strong> of <a href="#m/${m.id}">${esc(m.title)}</a></p><p class="t2">${esc(m.review.consequence)}</p><p><button>Reject</button> <button class="primary">Accept</button></p></article>`;
      return `<article class="a-card" data-ap="${m.id}"><p><span data-role="needs">◆</span> <span data-role="needs">Pending</span> <strong>Approval</strong> <span class="t3 r">${ago(a.since)}</span></p>
        <p><strong>Approve this plan version</strong> for <a href="#m/${m.id}">${esc(m.title)}</a> · plan v${a.plan_version}</p>
        <dl class="a-dl"><dt>Task</dt><dd class="mono">${esc(m.tasks[0][0].toLowerCase().split(' ')[0])} · ${esc(m.tasks[0][0])}</dd><dt>Class</dt><dd class="mono">${a.action_class}</dd><dt>Target</dt><dd class="mono">${a.target}</dd>
        <dt>Policy</dt><dd>ASK — ASK ${a.action_class}: ${esc(a.policy)}</dd></dl>
        <dl class="a-kv"><dt>Why it asks</dt><dd>ASK ${a.action_class}: ${esc(a.policy)}</dd><dt>If you approve</dt><dd>the plan runs; its tasks dispatch under it</dd><dt>If you reject</dt><dd>the mission is cancelled</dd>
        <dt>Expires</dt><dd>${FX.iso(a.expires)} (in ${Math.round((a.expires - FX.NOW) / 60) || 1} h)</dd><dt>Covers</dt><dd>plan-lifetime</dd></dl>
        <details><summary>Details</summary><p class="mono">${a.id}</p></details>
        <p class="a-sum">Plan summary, the planner (model-written): ${esc(a.said)}</p>
        <p><button class="a-rej">Reject</button> <button class="primary">Approve plan</button></p>
        <label class="cap">What should change? (the planner reads this)<textarea rows="2"></textarea></label><p><button disabled>Request changes</button></p><p class="cap t3">Say what should change.</p></article>`;
    },
    row(m) {
      // V1 MissionRow: state badge, title, tag, statusLine(m) WITHOUT tasks (always empty on rows), age
      return `<a class="a-row" href="#m/${m.id}" data-id="${m.id}"><span data-role="${F.ROLE[FIGST[m.state]]}">${{ needs_you: '◆', active: '●', verifying: '●', reviewing: '●', blocked: '■', failed: '✕', done: '✓', planning: '◌' }[FIGST[m.state]]} ${m.state === 'EXECUTING' ? 'Active' : word(m)}</span>
        <strong data-qa="${m.id}">${esc(m.title)}</strong>${m.approval ? '<span class="tag">waiting on you</span>' : ''}<span class="status"></span><span class="t3 r">${ago(m.created)}</span><button class="pin">Pin</button></a>`;
    },
    now() {
      const conv = needs.filter((m) => m.approval).map((m) => `<div class="a-msg"><p class="cap t3">Archeus</p><p>"${esc(m.title)}" needs your approval: this plan version.</p><div class="a-ask"><p>Approve this plan version?</p><p><button>Approve</button> <button>Reject</button></p></div><p class="a-ref">mission ${esc(m.title)}</p><p class="cap t3">${ago(m.approval.since)}</p></div>`).join('');
      const dig = changes.map((e) => `<li class="mono cap">${e.kind} · ${esc(byId[e.mission_id].title)} · seq ${e.seq}</li>`).join('');
      return `<div class="a-view"><h1>Now</h1><p class="a-sentence">${running.length ? `Archeus is working on ${running.length} missions.` : 'Archeus is idle.'} ${needs.length} need you.</p>
        <div class="a-grid"><div class="a-main"><h2>Needs you</h2><div data-q="q3">${needs.slice(0, 3).map(A.card).join('')}</div>
        <h2>Happening now</h2><div class="a-rows" data-q="q5">${running.map(A.row).join('') || '<p class="t3">Nothing is in progress. Tell Archeus what you want below.</p>'}</div>
        ${changes.length ? `<h2>Since you last looked · ${changes.length} changes</h2><ul data-q="q6">${dig}</ul>` : ''}
        ${upcoming.length ? `<h2>Upcoming</h2><div class="a-rows">${upcoming.map(A.row).join('')}</div>` : ''}
        ${FX.events.some((e) => e.kind === 'approval.decided') ? `<h2>Recent decisions</h2><div class="a-rows">${FX.events.filter((e) => e.kind === 'approval.decided').slice(-3).map((e) => `<div class="a-row"><span>approval ${e.decision}d</span><strong>${esc(byId[e.mission_id].title)}</strong><span class="t3 r">${ago(e.at)}</span></div>`).join('')}</div>` : ''}
        </div><aside class="a-side"><section class="a-conv"><h2>Conversation</h2>${conv}<textarea placeholder="Tell Archeus what you want…"></textarea><button disabled>Send</button><p class="cap t3">Write a message first.</p></section></aside></div></div>`;
    },
    work() {
      const grp = [['Needs you', needs], ['Working', running], ['Blocked', stopped], ['Upcoming', upcoming], ['Done', done]];
      return `<div class="a-view"><h1>Work</h1><button>Pause all</button>${grp.map(([t, l]) => l.length ? `<h2>${t} · ${l.length}</h2><div class="a-rows" ${t === 'Done' ? 'data-q="q4"' : ''}>${l.map(A.row).join('')}</div>` : '').join('')}</div>`;
    },
    attention() { return `<div class="a-view"><h1>Attention</h1>${needs.map(A.card).join('')}</div>`; },
    mission(id, tab) {
      const m = byId[id];
      tab = tab || 'outcome';
      const tabs = ['Outcome', 'Plan', 'Now', 'Evidence', 'Why', 'Timeline', 'Relations'];
      let body = '';
      if (tab === 'outcome') body = `<h3>Objective</h3><p>${esc(m.objective)}</p><h3>Success criteria</h3><p>the result passes its automatic check <span class="tag">automatic</span></p><h3>Scope and control</h3><p class="t3">Origin</p><p>conversation</p>`;
      if (tab === 'now') body = m.live ? `<ul data-q="q1"><li>${esc(m.live.task_title)} · ${m.live.task_state}</li></ul>` : '<p>Nothing is running now.</p>';
      if (tab === 'evidence') body = m.verification ? `<div data-q="q7 q8"><p>${m.verification.state} · verifier: archeus</p><ul>${m.verification.checks.map((c) => `<li>${c[0]} · ${c[1]}${c[2] != null ? ' · exit ' + c[2] : ''}</li>`).join('')}</ul></div>` : '<p>No verification yet.</p>';
      if (tab === 'plan') body = `<ol>${m.tasks.map((t, i) => `<li>Step ${i + 1}: ${esc(t[0])} · ${t[1]}</li>`).join('')}</ol>`;
      return `<div class="a-view a-mission"><header><h1>${esc(m.title)}</h1><a href="#now" class="a-close">Close</a></header><p><span data-role="${F.ROLE[FIGST[m.state]]}">${word(m)}</span></p>
        <p>Priority <input value="0" size="3"> <button>Set priority</button></p><p class="cap t3">Higher is started first when missions wait for capacity. Every mission starts at 0.</p>
        <details><summary>Details</summary><p class="mono">${m.id}</p><p class="mono">branch ${m.integration_branch || '—'} · head ${m.integration_head || '—'}</p></details>
        <p><a href="#project/${m.project_id}" data-k="project">project</a></p>
        <div class="a-tabs" role="tablist">${tabs.map((t) => `<a href="#m/${id}/${t.toLowerCase()}" role="tab" aria-selected="${t.toLowerCase() === tab}">${t}</a>`).join('')}</div><div class="a-tab">${body}</div></div>`;
    },
    project(pid) { const P = FX.projects[pid]; return `<div class="a-view"><h1 data-q="q2">${esc(P.name)}</h1>${P.repos.map((r) => `<h2>${r.kind} ${esc(r.path)}</h2>`).join('')}</div>`; },
    world() { return `<div class="a-view"><h1>World</h1>${Object.entries(FX.projects).map(([k, p]) => `<p><a href="#project/${k}">${esc(p.name)}</a></p>`).join('')}</div>`; },
    control() { return `<div class="a-view"><h1>Control</h1><p><button class="a-stop">Emergency stop</button></p></div>`; },
    render(route) {
      const [k, id, tab] = route.split('/');
      const body = k === 'm' ? A.mission(id, tab) : k === 'project' ? A.project(id) : (A[k] || A.now)();
      const cur = k === 'm' || k === 'project' ? 'work' : k;
      return `${A.top()}<div class="a-shell">${A.nav(cur)}<main id="main">${body}</main></div>`;
    },
  };

  // ================================================================== variants B and C
  const estop = () => `<button class="estop" data-estop aria-describedby="estop-hint"><span aria-hidden="true">■</span> <span data-estop-label>Stop all</span></button><span id="estop-hint" class="sr">Press twice to stop all running work.</span>`;
  const B = {
    top() {
      return `<header class="b-top"><a class="mark" href="#now">⟁ <span>Archeus</span></a><span class="core t3 cap">Core connected</span><span class="grow"></span>
        <button class="compose" aria-label="Tell Archeus">${phone() ? '＋' : 'Tell Archeus… <kbd>Ctrl K</kbd>'}</button>${estop()}</header>`;
    },
    nav(cur) {
      const it = [['now', 'Now'], ['needs', PLACE.needs], ['missions', PLACE.missions]];
      const main = it.map(([k, l]) => `<a href="#${k}" data-k="${k}" ${cur === k ? 'aria-current="page"' : ''}>${l}${k === 'needs' ? ` <span class="badge" data-role="needs">${needs.length}</span>` : ''}</a>`).join('');
      return phone() ? `<nav class="b-tabs" aria-label="Places">${main}</nav>`
        : `<nav class="b-nav" aria-label="Places">${main}<hr><a href="#world" class="sec" data-k="world">World</a><a href="#control" class="sec" data-k="control">Control</a></nav>`;
    },
    strip() {
      if (!phone()) return '';
      const m = running[0];
      const txt = m ? `${fig(m)} <strong>${esc(m.title)}</strong> <span class="t2">· step ${m.live.step} of ${m.live.of} · ${dur(FX.NOW - m.live.started_at)}</span>` : '<span class="t2">Nothing running</span>';
      return `<a class="b-strip" href="${m ? '#m/' + m.id : '#missions'}" aria-label="Running mission">${txt}${running.length > 1 ? `<span class="more t3">+${running.length - 1}</span>` : ''}<span class="chev" aria-hidden="true">${DP ? '›' : '⌃'}</span></a>`;
    },
    decideRow(m, i) {
      const a = m.approval;
      return `<li class="b-row decide" data-id="${m.id}" ${i === 0 ? 'data-first-decide' : ''}>${fig(m)}<a class="b-main" href="#d/${m.id}"><strong>${verbOf(m)}</strong> for ${esc(m.title)} <span class="t2">· ${esc(consequence(m))}</span>
        <span class="ctxl cap t3">${ctxLine(m)}</span></a>${phone() ? '' : `<span class="acts"><button data-verb class="primary">${a ? 'Approve' : 'Accept'}</button><button>${a ? 'Reject' : 'Ask for changes'}</button></span>`}</li>`;
    },
    runRow(m) {
      return `<li class="b-row run" data-id="${m.id}">${fig(m)}<a class="b-main" href="#m/${m.id}"><strong data-q="q2">${esc(m.title)}</strong> <span class="t2" data-q="q1">· ${esc(m.live.task_title)} · step ${m.live.step} of ${m.live.of}</span>
        <span class="ctxl cap t3">${ctxLine(m)} · on this computer</span></a><span class="num t3 r">${dur(FX.NOW - m.live.started_at)}</span></li>`;
    },
    stopRow(m) {
      return `<li class="b-row stop" data-id="${m.id}">${fig(m)}<a class="b-main" href="#m/${m.id}"><strong>${esc(m.title)}</strong> <span class="t2" data-q="q7">· ${m.state === 'BLOCKED' ? 'blocked' : 'failed'} because ${esc(becauseShort(m))}</span>
        <span class="ctxl cap t3">${ctxLine(m)}</span></a></li>`;
    },
    plainRow(m) {
      return `<li class="b-row" data-id="${m.id}">${fig(m)}<a class="b-main" href="#m/${m.id}"><strong>${esc(m.title)}</strong> <span class="t2">· ${m.state === 'DONE' ? 'verified ' + clock(m.done_at) : word(m).toLowerCase()}</span><span class="ctxl cap t3">${ctxLine(m)}</span></a></li>`;
    },
    today() {
      const v = done.length, f = FX.missions.filter((m) => m.state === 'FAILED').length, b = FX.missions.filter((m) => m.state === 'BLOCKED').length;
      return `<p class="b-today" data-q="q4">Today: ${v} verified · ${f} failed · ${b} blocked · <a href="#missions">all missions</a></p>`;
    },
    since() {
      return `<details class="b-since"><summary>Since you looked · ${changes.length} changes</summary><ul data-q="q6">${changes.map((e) => `<li>${clock(e.at)} · ${esc(byId[e.mission_id].title)} — ${({ 'execution.output': 'new output', 'approval.requested': 'asked for approval', 'verification.started': 'verification started', 'checkpoint.created': `checkpoint (${e.files} files)`, 'mission.created': 'created', 'approval.decided': 'you decided' })[e.kind] || e.kind}</li>`).join('')}</ul></details>`;
    },
    now() {
      return `<section class="b-now" aria-labelledby="vh"><h1 id="vh" class="verdict" tabindex="-1">${verdict()}</h1><p class="sub">${subline()}</p>
        ${needs.length ? `<h2>Needs you</h2><ul class="b-list" data-q="q3">${needs.slice(0, 3).map(B.decideRow).join('')}</ul>${needs.length > 3 ? `<a href="#needs">${needs.length - 3} more</a>` : ''}` : ''}
        ${running.length ? `<h2>Running</h2><ul class="b-list" data-q="q5">${running.map(B.runRow).join('')}</ul>` : ''}
        ${stopped.length ? `<h2>Stopped</h2><ul class="b-list">${stopped.map(B.stopRow).join('')}</ul>` : ''}
        ${B.today()}${changes.length ? B.since() : ''}</section>`;
    },
    needsPage() {
      const dec = needs.filter((m) => m.approval), rev = needs.filter((m) => !m.approval);
      return `<section><h1 class="headline" tabindex="-1">Needs you</h1>${dec.length ? `<h2>Decide</h2><ul class="b-list" data-q="q3">${dec.map(B.decideRow).join('')}</ul>` : ''}
        ${rev.length ? `<h2>Review</h2><ul class="b-list">${rev.map(B.decideRow).join('')}</ul>` : ''}${stopped.length ? `<h2>Unblock</h2><ul class="b-list">${stopped.map(B.stopRow).join('')}</ul>` : ''}</section>`;
      // LV2-1 W0 (T-2): LV2-0 had a "Decided for you by policy today" list here written as literal
      // strings, from no fixture record. Removed rather than sourced: O-13 is not under test in LV2-1.
    },
    missions() {
      const g = [['Running', running, B.runRow], ['Needs you', needs, B.decideRow], ['Stopped', stopped, B.stopRow], ['Upcoming', upcoming, B.plainRow], ['Done today', done, B.plainRow]];
      return `<section><h1 class="headline" tabindex="-1">Missions</h1><p class="chips" role="group" aria-label="Filter"><button aria-pressed="true">All ${FX.missions.length}</button><button aria-pressed="false">Running ${running.length}</button><button aria-pressed="false">Stopped ${stopped.length}</button></p>
        ${g.map(([t, l, f]) => l.length ? `<h2>${t}</h2><ul class="b-list" ${t === 'Done today' ? 'data-q="q4"' : ''}>${l.map(f).join('')}</ul>` : '').join('')}<p><a href="#world">World and Relations</a></p></section>`;
    },
    decision(id) {
      const m = byId[id], a = m.approval;
      const spine = '';
      const what = a ? a.what : 'The work ran and verified. Accepting merges it into ' + context(m).find((f) => f.k === 'base')?.value + '.';
      return `<article class="b-dec" aria-labelledby="dh">${phone() ? `<header class="b-push"><a href="#back" data-back>‹ Back</a><span class="t3 cap">${esc(m.title)}</span></header>` : ''}
        <h1 id="dh" class="headline" tabindex="-1">${verbOf(m)}</h1><p class="lead">${esc(what)}</p>
        <p class="t2">${a ? esc(consequence(m)) : esc(m.review.consequence)}</p>
        ${a ? `<h2>Why it asks</h2><p>${esc(a.why)}</p>
        <h2>Decision context</h2><dl class="kv"><dt>You asked</dt><dd>“${esc(a.asked)}”</dd><dt>It said</dt><dd>${esc(a.said)}</dd><dt>Last tools</dt><dd>${esc(a.tools)}</dd><dt>Waiting since</dt><dd>${clock(a.since)} (${ago(a.since)})</dd></dl>
        ${a.changed ? `<h2>Changed since v${a.plan_version - 1}</h2><p>${esc(a.changed)}</p>` : ''}` : B.evidence(m)}
        ${ctxBlock(m)}${a ? `<details class="raw"><summary>Policy record</summary><p class="mono cap">${esc(a.policy)}</p><p class="mono cap">expires ${FX.iso(a.expires)} · ${a.id}</p></details>` : ''}
        <div class="b-decide-bar"><button class="reject">${a ? 'Reject' : 'Ask for changes'}</button>${a ? '<button>Ask for changes</button>' : ''}<button class="primary" data-verb>${a ? 'Approve' : 'Accept'}</button></div></article>`;
    },
    evidence(m) {
      if (!m.verification) return '';
      return `<section class="b-ev" data-q="q8" aria-label="Verification evidence"><h2>Verification</h2><p>${esc(verdictOf(m.verification))}</p><ul class="checks">${m.verification.checks.map((c) => `<li data-r="${c[1]}"><span aria-hidden="true">${c[1] === 'passed' ? '✓' : c[1] === 'failed' ? '✕' : '…'}</span> ${esc(c[0])} <span class="t3">${c[1]}${c[2] ? ' · exit ' + c[2] : ''}</span> ${c[1] === 'failed' ? '<a href="#log">output</a>' : ''}</li>`).join('')}</ul></section>`;
    },
    chain(m) {
      if (!m.because) return '';
      return `<section class="b-chain" aria-label="Because"><h2>Why it stopped</h2><ol data-q="q7">${m.because.map((b, i) => `<li>${i ? '<span class="t3">because</span> ' : ''}${esc(b)}</li>`).join('')}</ol></section>`;
    },
    mission(id) {
      const m = byId[id];
      const at = F.AT[FIGST[m.state]];
      return `<article class="b-mis" aria-labelledby="mh">${phone() ? `<header class="b-push"><a href="#back" data-back>‹ Back</a></header>` : ''}
        <h1 id="mh" class="headline" tabindex="-1">${esc(m.title)}</h1><p class="t2">${fig(m)} ${word(m)} · ${ctxLine(m)}</p>
        <ol class="spine" aria-label="Lifecycle">${F.STATIONS.map((s, i) => `<li ${i === at ? 'aria-current="step"' : ''} data-past="${i < at}">${s}</li>`).join('')}</ol>
        ${m.live ? `<p class="doing"><strong>Now:</strong> <span data-q="q1">${esc(m.live.task_title)}, step ${m.live.step} of ${m.live.of}</span> · ${dur(FX.NOW - m.live.started_at)}</p>` : ''}
        ${B.chain(m)}${m.next ? `<p class="nexts">${m.next.map((n, i) => `<button ${i === 0 ? 'class="primary"' : ''}>${esc(n)}</button>`).join(' ')}</p>` : ''}
        <p class="goal"><span class="t3">Goal</span> ${esc(m.objective)}</p>${B.evidence(m)}${ctxBlock(m)}</article>`;
    },
    world() { return `<section><h1 class="headline">World</h1>${Object.entries(FX.projects).map(([k, p]) => `<p>${esc(p.name)} <span class="t3 mono cap">${p.repos.map((r) => esc(r.path)).join(' · ')}</span></p>`).join('')}</section>`; },
    control() { return `<section><h1 class="headline">Control</h1><p class="t2">Autonomy, policy, resources.</p></section>`; },
    page(route) {
      const [k, id] = route.split('/');
      if (k === 'd') return B.decision(id);
      if (k === 'm') return B.mission(id);
      return ({ now: B.now, needs: B.needsPage, missions: B.missions, world: B.world, control: B.control })[k]?.() || B.now();
    },
    render(route) {
      const k = route.split('/')[0];
      const cur = k === 'd' ? 'needs' : k === 'm' ? 'missions' : k;
      if (phone()) return `${B.top()}<main id="main" class="b-phone">${B.page(route)}</main>${B.strip()}${B.nav(cur)}`;
      // desktop
      const wide = V === 'c';
      const W = innerWidth - 200;
      const isObj = k === 'd' || k === 'm';
      if (wide && W >= 900) {
        // C: container-driven panes. The list place stays; the object opens beside it; from
        // 1,700 an evidence inspector docks right. The default object is the first decision.
        const listRoute = isObj ? (k === 'd' ? 'needs' : 'missions') : route;
        const objId = isObj ? id : (needs[0] || running[0] || FX.missions[0]).id;
        const objRoute = isObj ? route : (needs[0] ? 'd/' + objId : 'm/' + objId);
        const m = byId[objId];
        const three = innerWidth >= 1700;
        const insp = three ? `<aside class="c-insp" aria-label="Evidence">${B.chain(m) || ''}${B.evidence(m) || ''}${ctxBlock(m)}${m.approval ? '' : ''}</aside>` : '';
        let obj = B.page(objRoute);
        if (three) obj = obj.replace(/<section class="ctx"[\s\S]*?<\/section>/, ''); // the context moves to the inspector
        return `${B.top()}<div class="b-shell c">${B.nav(k === 'd' ? 'needs' : k === 'm' ? 'missions' : cur)}<main id="main" class="c-list">${B.page(listRoute)}</main><section class="c-obj" aria-label="Selected">${obj}</section>${insp}</div>`;
      }
      return `${B.top()}<div class="b-shell">${B.nav(cur)}<main id="main" class="b-desk">${B.page(route)}</main></div>`;
    },
  };

  // ------------------------------------------------------------------ e-stop (LD-7)
  // In-place two-step: the first press ARMS for 3 s and says what the second does; the second
  // engages at once. No modal, nothing to aim at twice, never a single-tap kill.
  let armT = 0;
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-estop]');
    if (!b) return;
    const lbl = b.querySelector('[data-estop-label]');
    if (b.dataset.state === 'armed') { clearTimeout(armT); b.dataset.state = 'engaged'; lbl.textContent = 'Stopped · re-arm in Control'; window.__estop = (window.__estop || 0) + 1; announce('Everything is stopped.'); return; }
    if (b.dataset.state === 'engaged') return;
    b.dataset.state = 'armed'; lbl.textContent = 'Press again to stop all'; announce('Press again within 3 seconds to stop all running work.');
    armT = setTimeout(() => { b.dataset.state = ''; lbl.textContent = 'Stop all'; }, 3000);
  });
  function announce(t) { const l = $('#live'); if (l) l.textContent = t; }

  /*<typeset>*/
  // DP-1: a number never parts from its word, a separator stays at the end of its line and is
  // drawn one tier quieter. Text nodes only, so every word a probe reads is unchanged.
  function typeset(root) {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.parentElement.closest('script, svg, kbd, .mono, .sr') ? 2 : 1) });
    const ns = [];
    while (w.nextNode()) ns.push(w.currentNode);
    for (const n of ns) {
      const t = n.data.replace(/(\d) /g, '$1 ').replace(/(?<!·) (\d)/g, ' $1').replace(/ · /g, ' · ');
      if (!t.includes('·')) { if (t !== n.data) n.data = t; continue; }
      const f = document.createDocumentFragment();
      t.split('·').forEach((s, i) => { if (i) f.append(Object.assign(document.createElement('span'), { className: 'sep', textContent: '·' })); f.append(s); });
      n.replaceWith(f);
    }
  }
  /*</typeset>*/

  // ---------------------------------------------------------------------- routing
  let stack = [];
  function render() {
    const route = (location.hash || '#now').slice(1);
    const html = (V === 'a' ? A : B).render(route);
    document.body.innerHTML = html + '<p id="live" class="sr" aria-live="polite"></p>';
    if (DP) typeset(document.body);
    const h = $('main h1, .c-obj h1');
    if (h && stack.length) h.focus({ preventScroll: true });
    window.__route = route;
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-back]');
    if (b) { e.preventDefault(); history.back(); }
  });
  /*<lablog>*/
  // LV2-1 H-3: ?log=1 keeps an on-device log of routes and presses (localStorage only, nothing is
  // sent anywhere) so mis-taps and e-stop presses are counted from the record, not from memory.
  // #lablog shows it for the moderator to copy; #lablog-clear empties it between participants.
  if (Q.get('log') === '1') {
    const put = (e) => { try { const l = JSON.parse(localStorage.getItem('lv21log') || '[]'); l.push(Object.assign({ t: Date.now(), route: location.hash || '#now' }, e)); localStorage.setItem('lv21log', JSON.stringify(l)); } catch (_) { /* private mode: moderator notes only */ } };
    document.addEventListener('click', (e) => { const b = e.target.closest('button, a'); if (b) put({ ev: 'press', label: b.textContent.trim().slice(0, 40), estop: b.dataset.estop != null ? (b.dataset.state || 'idle') : undefined }); }, true);
    addEventListener('hashchange', () => put({ ev: 'route' }));
    addEventListener('pagehide', () => put({ ev: 'leave' }));
  }
  /*</lablog>*/
  addEventListener('hashchange', () => {
    if (location.hash === '#lablog' || location.hash === '#lablog-clear') {
      if (location.hash === '#lablog-clear') try { localStorage.removeItem('lv21log'); } catch (_) { /* nothing to clear */ }
      let l = '[]'; try { l = localStorage.getItem('lv21log') || '[]'; } catch (_) { /* unavailable */ }
      document.body.innerHTML = `<main style="padding:16px"><h1 class="headline">Session log</h1><textarea readonly style="width:100%;height:70vh">${esc(l)}</textarea></main>`;
      return;
    }
    stack.push(location.hash); render(); scrollTo(0, 0);
  });
  addEventListener('resize', () => { clearTimeout(window.__rz); window.__rz = setTimeout(render, 80); });
  render();

  // ------------------------------------------------------- the question paths (LE-1)
  // Clicks from Now that reach each answer, per variant and device. A walks the best route
  // V1 offers; where V1 has no answer on any screen the path is null (unanswerable).
  const blocked = stopped.find((m) => m.state === 'BLOCKED') || {};
  const run0 = running[0] || {};
  window.PATHS = {
    a: {
      q1: [`a.a-row[data-id="${run0.id}"]`, `a[href="#m/${run0.id}/now"]`], q2: [`a.a-row[data-id="${run0.id}"]`, '[data-k="project"]'],
      q3: [], q4: ['a[data-k="work"]'], q5: [], q6: [], q7: ['a[data-k="work"]', `a.a-row[data-id="${blocked.id}"]`, `a[href="#m/${blocked.id}/evidence"]`],
      q8: ['a[data-k="work"]', `a.a-row[data-id="${blocked.id}"]`, `a[href="#m/${blocked.id}/evidence"]`],
    },
    b: { q1: [], q2: [], q3: [], q4: [], q5: [], q6: ['.b-now .b-since summary'], q7: [], q8: [`.b-row.stop[data-id="${blocked.id}"] a`] },
  };
  window.PATHS.c = window.PATHS.b;
  window.IA = { context, verdict, needs, running, stopped, A, B };
})();
