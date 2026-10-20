/* LV2-X.3 — the real-data replay (?d=e2&corpus=core). Prototype only.
 *
 * replay.js holds a real Core's reads, verbatim (tools/lvx_replay.py ran the runtime with the fake harness).
 * This adapter turns them into the fixture's shape and nothing else: a field E reads that Core did not return
 * is left out, and the reason is listed in window.REPLAY_GAPS (shown with ?gaps=1, and in the X.3 report).
 */
(function () {
  'use strict';
  const R = window.CORE_REPLAY, FX = window.FX;
  if (!R) return;
  const GAPS = window.REPLAY_GAPS = [];
  const gap = (what, why) => { if (!GAPS.some((g) => g[0] === what)) GAPS.push([what, why]); };
  // local minutes since the capture day's midnight (Core times are UTC; this machine is UTC+2)
  const day = new Date(R.captured_at).getUTCDate();
  const min = (iso) => { const d = new Date(iso); return (d.getUTCDate() - day) * 1440 + (d.getUTCHours() + 2) * 60 + d.getUTCMinutes(); };
  FX.NOW = min(R.captured_at);

  FX.projects = {};
  for (const p of R.projects.projects) {
    FX.projects[p.id] = { name: p.name, root_paths: p.root_paths,
      repos: p.repositories.map((r) => ({ path: r.path, kind: r.kind, default_branch: r.default_branch, last_revision: (r.last_revision || '').slice(0, 7) })) };
    if (p.repositories.some((r) => r.default_branch == null)) gap('Repository.default_branch', 'never written by Core (lv2-dr3): the project page shows no default branch');
  }

  const evs = R.events.events;
  const taskMission = {};
  for (const id of Object.keys(R.plan)) for (const t of (R.plan[id].plan || { tasks: [] }).tasks) taskMission[t.id] = id;
  // plan order is the dependency order, not the array order Core returns (it lists tasks by key)
  const ordered = (tasks) => {
    const out = [], done = new Set();
    while (out.length < tasks.length) {
      const next = tasks.filter((t) => !done.has(t.key) && t.depends_on.every((k) => done.has(k)));
      if (!next.length) break;
      for (const t of next) { out.push(t); done.add(t.key); }
    }
    return out;
  };
  const toLast = (mid, to) => evs.filter((e) => e.type === 'mission.state_changed' && e.subject.id === mid && e.payload.to === to).slice(-1)[0];
  const pending = R.approvals.approvals.filter((a) => a.state === 'PENDING');

  FX.missions = R.missions.missions.map((c) => {
    const v = R.mission[c.id] || c, tasks = ordered((R.plan[c.id] && R.plan[c.id].plan || { tasks: [] }).tasks);
    const m = { id: c.id, core_id: c.id, title: c.title, objective: c.objective, project_id: c.project_id,
      state: c.state === 'COMPLETED' ? 'DONE' : c.state, created: min(c.created_at), held_from: c.held_from,
      integration_branch: v.integration_branch, integration_head: v.integration_head ? v.integration_head.slice(0, 7) : null,
      tasks: tasks.map((t) => [t.title, t.state]) };
    if (!v.integration_branch) gap('Mission.integration_branch on the list', 'only GET /v1/missions/{id} adds it; a row derives archeus/<id> (queries.py:35)');
    const L = R.status.live.find((l) => l.mission_id === c.id);
    if (L) {
      const st = evs.find((e) => e.type === 'execution.started' && e.subject.id === L.id);
      m.live = { task_title: L.task_title, task_state: L.task_state, branch: L.branch, harness_id: L.harness_id, model: L.model,
        started_at: st ? min(st.at) : null, step: tasks.findIndex((t) => t.key === L.task_key) + 1, of: tasks.length };
      if (L.model == null) gap('LiveItem.model', 'null for this harness: the agent line names the harness only');
    } else if (c.state === 'EXECUTING') gap('an EXECUTING mission with no live execution', 'queued for capacity: E assumed every running mission has an agent on a step');
    const a = pending.find((x) => x.mission_id === c.id);
    if (a) {
      const P = a.presented, asks = P.what.filter((w) => w.decision === 'ASK');
      m.approval = { id: a.id, kind: a.kind, plan_version: a.plan_version, task: null, expires: min(a.expires_at), since: min(a.created_at),
        action_class: asks.map((w) => w.class)[0], allowed: Object.keys(P.consequences).filter((k) => k !== 'step_up'),
        consequences: P.consequences, step_up: a.step_up, summary_by: P.against.plan && P.against.plan.summary_by,
        what: P.against.plan ? P.against.plan.summary : '', policy: asks.map((w) => w.why.replace(/^ASK \w+: /, '')).join('; '),
        why: asks.length ? 'Your policy asks before every ' + asks.map((w) => w.class.replace('_', ' ')).join(' and ') + '.' : '',
        asked: c.objective, changed: null };
      gap('Intent.utterance (your words)', 'a mission made through POST /v1/missions has no message (origin_ref null); “what you asked” falls back to the objective');
    }
    const ver = (R.verifications[c.id] || { verifications: [] }).verifications;
    if (ver.length) {
      m.verification = { state: ver.slice(-1)[0].state, checks: [] };
      if (ver.every((x) => !x.checks.length)) gap('Verification.checks', 'none recorded: the scripted verifier gives a state and no named checks (the real verifier records them)');
    }
    if (c.state === 'BLOCKED') {
      const e = toLast(c.id, 'BLOCKED');
      m.because = e ? ['Blocked at ' + String(Math.floor(min(e.at) / 60)).padStart(2, '0') + ':' + String(min(e.at) % 60).padStart(2, '0') + ': ' + e.payload.reason, (e.payload.guard || {}).reason || e.payload.trigger] : ['Blocked', ''];
    }
    if (c.state === 'COMPLETED') { const e = toLast(c.id, 'COMPLETED'); m.done_at = e ? min(e.at) : FX.NOW; }
    return m;
  });

  // the day's record: the mission-level events E's Today and Activity read, under Core's own names
  let seq = 0;
  const ev = (mid, e, kind, x) => FX.events.push(Object.assign({ seq: ++seq, mission_id: mid, at: min(e.at), kind, core_type: e.type }, x || {}));
  FX.events = [];
  for (const e of evs) {
    const p = e.payload || {};
    if (e.type === 'mission.created') ev(e.subject.id, e, 'mission.created');
    else if (e.type === 'mission.state_changed') ev(e.subject.id, e, p.to === 'COMPLETED' ? 'mission.done' : 'mission.state_changed', { from: p.from, to: p.to, trigger: p.trigger, reason: p.reason });
    else if (e.type === 'approval.requested' || e.type === 'review.requested') ev(p.mission_id, e, e.type);
    else if (e.type === 'execution.started' && taskMission[p.task_id]) ev(taskMission[p.task_id], e, 'execution.started');
    else if (e.type === 'checkpoint.created' && taskMission[p.task_id]) ev(taskMission[p.task_id], e, 'checkpoint.created', { files: null });
  }
  gap('checkpoint.created{files}', 'the event names the execution and task, not how many files changed');
  gap('approval.decided, mission.done, verification.passed', 'not Core events: Core records approval.state_changed, mission.state_changed and verification.state_changed (the fixture had invented the shorter names)');
  FX.ideas = [];
  gap('ideas', 'none: capturing an idea needs the brain’s intent call, which a fake-harness Core does not make');
})();
