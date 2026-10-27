// V2 Live simulation engine. No DOM, no network, no Core. Everything here is SIMULATED fixture data.
// Deterministic: the same seed and the same calls give the same event log, whatever the advance() chunking.
// State words and edges are copies of archeus/core/domain/states.py (V1); the table is checked by test/sim.test.mjs.

import { present } from './core-words.js';
import { createChat } from './chat-engine.js';

// The slash commands live in slash.js, one table for the chat, the terminal command line and say().

export const TIME_SCALE = 10; // one real second at 1x is ten simulated seconds
export const SPEEDS = [0.5, 1, 2, 4, 8];
const HOUR0 = 9; // the simulated day starts at 09:00:00

export const EDGES = {
  mission: [
    ['CREATED', 'UNDERSTANDING', 'start'], ['UNDERSTANDING', 'CONTEXT_GATHERING', 'understood'],
    ['UNDERSTANDING', 'BLOCKED', 'needs_clarification'], ['CONTEXT_GATHERING', 'REASONING', 'context_ready'],
    ['REASONING', 'PLANNING', 'reasoned'], ['REASONING', 'BLOCKED', 'challenge_raised'], ['REASONING', 'BLOCKED', 'plan_denied'],
    ['PLANNING', 'APPROVAL_REQUIRED', 'plan_needs_approval'], ['PLANNING', 'APPROVED', 'plan_auto_approved'],
    ['PLANNING', 'CANCELLED', 'cancel'], ['APPROVAL_REQUIRED', 'APPROVED', 'approve'],
    ['APPROVAL_REQUIRED', 'PLANNING', 'request_changes'], ['APPROVAL_REQUIRED', 'CANCELLED', 'reject'],
    ['APPROVED', 'EXECUTING', 'dispatch'], ['EXECUTING', 'VERIFYING', 'all_tasks_done'], ['EXECUTING', 'BLOCKED', 'block'],
    ['EXECUTING', 'PAUSED', 'pause'], ['EXECUTING', 'FAILED', 'unrecoverable'], ['EXECUTING', 'REPLANNING', 'task_failed_retryable'],
    ['BLOCKED', 'RESUMED', 'unblock'], ['PAUSED', 'RESUMED', 'resume'], ['RESUMED', 'EXECUTING', 'redispatch'],
    ['RESUMED', 'UNDERSTANDING', 'redispatch_before_plan'], ['FAILED', 'REPLANNING', 'replan'],
    ['REPLANNING', 'APPROVAL_REQUIRED', 'plan_needs_approval'], ['REPLANNING', 'APPROVED', 'plan_auto_approved'],
    ['REPLANNING', 'BLOCKED', 'replan_budget_exhausted'], ['VERIFYING', 'REVIEWING', 'verified'],
    ['VERIFYING', 'REPLANNING', 'verification_failed'], ['VERIFYING', 'BLOCKED', 'awaiting_human_acceptance'],
    ['REVIEWING', 'COMPLETED', 'accepted'], ['REVIEWING', 'REPLANNING', 'changes_requested'], ['CREATED', 'CANCELLED', 'cancel'],
    ['BLOCKED', 'CANCELLED', 'cancel'], ['PAUSED', 'CANCELLED', 'cancel'], ['FAILED', 'CANCELLED', 'cancel']
  ],
  plan: [
    ['DRAFT', 'PROPOSED', 'ready'], ['PROPOSED', 'APPROVED', 'approved'], ['PROPOSED', 'REJECTED', 'rejected'],
    ['PROPOSED', 'SUPERSEDED', 'superseded'], ['APPROVED', 'SUPERSEDED', 'superseded']
  ],
  task: [
    ['PENDING', 'READY', 'deps_satisfied'], ['PENDING', 'SKIPPED', 'skip'], ['READY', 'ROUTING', 'dispatch'],
    ['ROUTING', 'RUNNING', 'routed'], ['ROUTING', 'BLOCKED', 'no_eligible_resource'],
    ['ROUTING', 'AWAITING_APPROVAL', 'route_needs_approval'], ['RUNNING', 'AWAITING_APPROVAL', 'action_needs_approval'],
    ['AWAITING_APPROVAL', 'READY', 'approved'], ['AWAITING_APPROVAL', 'BLOCKED', 'rejected'], ['RUNNING', 'PAUSED', 'pause'],
    ['PAUSED', 'READY', 'resume'], ['RUNNING', 'VERIFYING', 'execution_succeeded'], ['RUNNING', 'READY', 'execution_failed_retry'],
    ['RUNNING', 'FAILED', 'execution_failed_final'], ['RUNNING', 'BLOCKED', 'merge_conflict'], ['VERIFYING', 'SUCCEEDED', 'checks_passed'],
    ['VERIFYING', 'READY', 'checks_failed_retry'], ['VERIFYING', 'FAILED', 'checks_failed_final'], ['BLOCKED', 'READY', 'unblock'],
    ['PENDING', 'CANCELLED', 'cancel'], ['READY', 'CANCELLED', 'cancel'], ['BLOCKED', 'CANCELLED', 'cancel'], ['PAUSED', 'CANCELLED', 'cancel']
  ],
  execution: [
    ['INTENT', 'STARTING', 'spawn'], ['INTENT', 'ABANDONED', 'spawn_failed'], ['INTENT', 'LOST', 'spawn_unconfirmed'],
    ['STARTING', 'RUNNING', 'first_output'], ['STARTING', 'LOST', 'start_timeout'], ['RUNNING', 'AWAITING_APPROVAL', 'hook_asked'],
    ['AWAITING_APPROVAL', 'STARTING', 'resume_approved'], ['AWAITING_APPROVAL', 'ENDED_REJECTED', 'rejected'],
    ['RUNNING', 'PAUSING', 'pause_requested'], ['PAUSING', 'PAUSED', 'halted_at_boundary'], ['PAUSING', 'STOPPING', 'pause_timeout'],
    ['PAUSED', 'STARTING', 'resume'], ['RUNNING', 'HANDING_OFF', 'pressure_or_account_change'],
    ['HANDING_OFF', 'ENDED_HANDOFF', 'checkpoint_written'], ['RUNNING', 'HANDING_OFF', 'user_handoff'],
    ['HANDING_OFF', 'ENDED_OK', 'exited_success'], ['HANDING_OFF', 'ENDED_ERROR', 'exited_error'], ['HANDING_OFF', 'STOPPING', 'stop'],
    ['RUNNING', 'STOPPING', 'stop'], ['STARTING', 'STOPPING', 'stop'], ['PAUSING', 'STOPPING', 'stop'],
    ['PAUSING', 'ENDED_OK', 'exited_success'], ['PAUSING', 'ENDED_ERROR', 'exited_error'], ['PAUSED', 'ENDED_KILLED', 'discarded'],
    ['AWAITING_APPROVAL', 'ENDED_KILLED', 'discarded'], ['STOPPING', 'ENDED_KILLED', 'process_gone'],
    ['RUNNING', 'ENDED_OK', 'exited_success'], ['RUNNING', 'ENDED_ERROR', 'exited_error'], ['RUNNING', 'LOST', 'heartbeat_missing'],
    ['LOST', 'RUNNING', 'adopted'], ['LOST', 'ENDED_KILLED', 'reconciled_kill']
  ],
  approval: [
    ['PENDING', 'APPROVED', 'approve'], ['PENDING', 'REJECTED', 'reject'], ['PENDING', 'EXPIRED', 'ttl_elapsed'],
    ['PENDING', 'SUPERSEDED', 'plan_replaced'], ['APPROVED', 'CONSUMED', 'action_executed'], ['APPROVED', 'EXPIRED', 'ttl_elapsed'],
    ['APPROVED', 'SUPERSEDED', 'plan_replaced']
  ],
  verification: [
    ['PENDING', 'RUNNING', 'start'], ['RUNNING', 'PASSED', 'all_checks_pass'], ['RUNNING', 'FAILED', 'a_check_fails'],
    ['RUNNING', 'ERROR', 'verifier_crashed'], ['PENDING', 'AWAITING_HUMAN', 'generic_verifier'],
    ['AWAITING_HUMAN', 'PASSED', 'user_accepts'], ['AWAITING_HUMAN', 'FAILED', 'user_rejects'], ['ERROR', 'PENDING', 'retry']
  ],
  review: [
    ['PENDING', 'IN_REVIEW', 'start'], ['IN_REVIEW', 'ACCEPTED', 'verdict_accept'], ['IN_REVIEW', 'CHANGES_REQUESTED', 'verdict_changes'],
    ['IN_REVIEW', 'REJECTED', 'verdict_reject'], ['PENDING', 'IN_REVIEW', 'user_reviews']
  ]
};

// Replay categories (T-147 REPLAY-coverage Part A). A state with no entry answers UNKNOWN, never a guess.
const INT = 'INTENDED', AUTH = 'AUTHORIZED', REC = 'RECORDED', MAY = 'MAY-HAVE-TAKEN-EFFECT', UNC = 'UNCERTAIN', SUS = 'SUSPENDED', NONE = 'NONE';
export const CATEGORY = {
  mission: { CREATED: INT, UNDERSTANDING: INT, CONTEXT_GATHERING: INT, BLOCKED: SUS, REASONING: INT, PLANNING: INT, APPROVAL_REQUIRED: SUS, APPROVED: AUTH, CANCELLED: REC, EXECUTING: MAY, VERIFYING: MAY, PAUSED: SUS, FAILED: REC, REPLANNING: INT, RESUMED: INT, REVIEWING: SUS, COMPLETED: REC },
  plan: { DRAFT: INT, PROPOSED: INT, APPROVED: AUTH, REJECTED: AUTH, SUPERSEDED: REC },
  task: { PENDING: INT, READY: INT, SKIPPED: NONE, ROUTING: MAY, RUNNING: MAY, BLOCKED: SUS, AWAITING_APPROVAL: SUS, PAUSED: SUS, VERIFYING: MAY, FAILED: REC, SUCCEEDED: REC, CANCELLED: REC },
  execution: { INTENT: INT, STARTING: MAY, ABANDONED: NONE, LOST: UNC, RUNNING: MAY, AWAITING_APPROVAL: SUS, PAUSING: MAY, PAUSED: SUS, HANDING_OFF: MAY, ENDED_HANDOFF: REC, ENDED_OK: REC, ENDED_ERROR: REC, STOPPING: MAY, ENDED_KILLED: 'RECONCILED' },
  approval: { PENDING: SUS, APPROVED: AUTH, REJECTED: AUTH, EXPIRED: UNC, SUPERSEDED: REC, CONSUMED: REC },
  verification: { PENDING: INT, RUNNING: MAY, PASSED: REC, FAILED: REC, ERROR: UNC, AWAITING_HUMAN: SUS },
  review: { PENDING: SUS, ACCEPTED: REC, CHANGES_REQUESTED: REC, REJECTED: REC }
};
export const REPLAY_CATEGORIES = [INT, AUTH, REC, MAY, UNC, SUS, 'RECONCILED', NONE, 'UNKNOWN'];
export const REPLAY_GAPS = 'NOT RECORDED: external effects or responses; a per-attempt starting digest; operator reconciliation; complete retained history (events are kept 180 days); the private reasoning and tool transcript; intermediate file snapshots; actual cost or served and billed provenance; confinement proof.';

export function categoryOf(machine, state, trigger) {
  if (trigger === 'adopted' || trigger === 'reconciled_kill') return 'RECONCILED';
  return (CATEGORY[machine] && CATEGORY[machine][state]) || 'UNKNOWN';
}

export function clockLabel(ms, seconds) {
  const total = Math.floor(ms / 1000) + HOUR0 * 3600;
  const s = ((total % 86400) + 86400) % 86400;
  const p = (n) => String(n).padStart(2, '0');
  return p(Math.floor(s / 3600)) + ':' + p(Math.floor((s % 3600) / 60)) + (seconds ? ':' + p(s % 60) : '');
}

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashEvents(events) {
  let h = 2166136261;
  const s = JSON.stringify(events);
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0).toString(16);
}

const sec = (n) => n * 1000;
const min = (n) => n * 60000;

export function createSim(opts = {}) {
  const seed0 = opts.seed == null ? 20261025 : opts.seed;
  const MAX_EVENTS = opts.maxEvents || 600;
  let S, rng, queue, qn, seq, subs = new Set();

  // ---------- helpers ----------
  const emit = (type, subject, payload, extra) => {
    const ev = Object.assign({ seq: ++seq, at: S.clock, type, subject, actor: S.actor, payload: payload || {} }, extra || {});
    S.events.push(ev);
    if (S.events.length > MAX_EVENTS) { S.events.splice(0, S.events.length - MAX_EVENTS); S.pruned = true; }
    if (!S.quiet) subs.forEach((f) => f(ev));
    return ev;
  };
  const edgeOk = (machine, from, to, trigger) => EDGES[machine].some((e) => e[0] === from && e[1] === to && (!trigger || e[2] === trigger));
  function move(machine, ent, to, trigger, extra) {
    if (!edgeOk(machine, ent.state, to, trigger)) throw new Error('no ' + machine + ' edge ' + ent.state + ' -> ' + to + ' (' + trigger + ')');
    const from = ent.state;
    if (machine === 'mission') {
      if (to === 'BLOCKED' || to === 'PAUSED') ent.held_from = from;
      if (from === 'RESUMED') ent.held_from = null;
    }
    ent.state = to;
    ent.updated_at = S.clock;
    emit(machine + '.state_changed', { kind: machine, id: ent.id }, Object.assign({ from, to, trigger }, extra || {}),
      { mission: machine === 'mission' ? ent.id : ent.mission, project: ent.project });
  }
  const at = (ms, name, fn) => { queue.push({ t: S.clock + ms, n: ++qn, name, fn }); };
  const atAbs = (t, name, fn) => { queue.push({ t, n: ++qn, name, fn }); };
  const M = (id) => S.missions[id];
  const missionOf = (x) => S.missions[x.mission];
  const taskOf = (m) => m.tasks.map((id) => S.tasks[id]);
  const pick = (arr) => arr[Math.floor(rng() * arr.length)];

  function newTask(m, key, title, state) { const t = { id: 't-' + m.id.slice(2) + '-' + key, mission: m.id, project: m.project, key, title, state: state || 'PENDING', execution: null }; S.tasks[t.id] = t; m.tasks.push(t.id); emit('task.created', { kind: 'task', id: t.id }, {}, { mission: m.id, project: m.project }); return t; }
  function newExec(m, t, state, extra) {
    const n = Object.values(S.executions).filter((x) => x.mission === m.id).length + 1;
    const acct = m.account || 'acc-work';
    const x = Object.assign({ id: 'x-' + m.id.slice(2) + '-' + n, mission: m.id, task: t.id, project: m.project, state, harness: 'claude_code', account: acct, model: m.model || 'claude-sonnet', started_at: S.clock, last_output_at: S.clock, stuck: false, outputs: 0, reason: null }, extra || {});
    S.executions[x.id] = x; t.execution = x.id;
    emit('execution.intent', { kind: 'execution', id: x.id }, {}, { mission: m.id, project: m.project });
    return x;
  }
  function newPlan(m, state) {
    m.plan_version = (m.plan_version || 0) + 1;
    Object.values(S.plans).filter((p) => p.mission === m.id && (p.state === 'PROPOSED' || p.state === 'APPROVED')).forEach((p) => move('plan', p, 'SUPERSEDED', 'superseded'));
    const p = { id: 'p-' + m.id.slice(2) + '-v' + m.plan_version, mission: m.id, project: m.project, version: m.plan_version, state: 'DRAFT' };
    S.plans[p.id] = p; emit('plan.created', { kind: 'plan', id: p.id }, { version: p.version }, { mission: m.id, project: m.project });
    move('plan', p, 'PROPOSED', 'ready');
    if (state === 'APPROVED') move('plan', p, 'APPROVED', 'approved');
    return p;
  }
  function newApproval(m, kind, presented, ref) {
    const a = { id: 'a-' + (++S.counters.approval), mission: m.id, project: m.project, kind, ref: ref || null, state: 'PENDING', created_at: S.clock, expires_at: S.clock + min(45), presented, decided_by: null };
    S.approvals[a.id] = a;
    emit('approval.requested', { kind: 'approval', id: a.id }, { kind, notify: true }, { mission: m.id, project: m.project });
    return a;
  }
  function decideApproval(a, to, trigger) {
    move('approval', a, to, trigger); a.decided_by = S.actor === 'device' ? 'user_device' : 'system'; a.decided_at = S.clock;
  }
  const usage = (acct) => S.usage[acct];
  function breakerOpen(h) { const b = S.harnesses.find((x) => x.id === h).breaker; return b.state === 'open' && S.clock < b.until; }

  // ---------- the progress of one running execution ----------
  function progressTick() {
    Object.values(S.executions).forEach((x) => {
      if (x.state !== 'RUNNING' || x.stuck) return;
      x.last_output_at = S.clock; x.outputs += 1;
      const u = usage(x.account);
      if (u && u.window5h != null) {
        u.window5h = Math.min(100, Math.round((u.window5h + 0.15 + rng() * 0.1) * 100) / 100);
        if (u.week != null) u.week = Math.round((u.week + 0.04) * 100) / 100;
        accountHealthCheck(x.account);
      }
      emit('execution.progress', { kind: 'execution', id: x.id }, { outputs: x.outputs }, { mission: x.mission, project: x.project });
    });
    at(sec(25), 'progress', progressTick);
  }
  function accountHealthCheck(id) {
    const acc = S.accounts.find((a) => a.id === id), u = usage(id);
    if (!acc || !u || u.window5h == null) return;
    const from = acc.state;
    let to = from;
    if (from === 'AVAILABLE' && u.window5h >= 85) to = 'CONSTRAINED';
    if (to === 'CONSTRAINED' && u.window5h >= 100) to = 'LIMITED';
    if (to !== from) {
      emit('account_health.state_changed', { kind: 'account', id }, { from, to, trigger: to === 'LIMITED' ? 'window_exhausted' : 'near_ceiling' }, {});
      acc.state = to;
    }
  }

  // ---------- reactions: what Core does next after a decision ----------
  const pending = (m) => taskOf(m).filter((t) => t.state === 'PENDING' || t.state === 'READY');
  function startExecution(m, delay) {
    // dispatch waits while the harness breaker is open (derived, never stored apart: T-106)
    at(delay, 'dispatch ' + m.id, () => {
      if (m.state !== 'APPROVED') return;
      if (S.estop.engaged) { m.reason = 'cannot start: the emergency stop is engaged; re-arm it first'; emit('mission.updated', { kind: 'mission', id: m.id }, { reason: m.reason }, { mission: m.id, project: m.project }); startExecution(m, sec(30)); return; }
      if (breakerOpen('claude_code')) { m.reason = 'cannot start: the claude_code harness breaker is open'; emit('mission.updated', { kind: 'mission', id: m.id }, { reason: m.reason }, { mission: m.id, project: m.project }); startExecution(m, sec(30)); return; }
      m.reason = null;
      move('mission', m, 'EXECUTING', 'dispatch');
      if (!pending(m).length) newTask(m, String(m.tasks.length + 1), 'Run the plan');
      pending(m).forEach((t, i) => spawnTask(m, t, sec(i * 7)));
    });
  }
  function spawnTask(m, t, delay) {
    at(delay, 'route ' + t.id, () => {
      if (m.state !== 'EXECUTING') return;
      if (t.state === 'PENDING') move('task', t, 'READY', 'deps_satisfied');
      move('task', t, 'ROUTING', 'dispatch');
      const x = newExec(m, t, 'INTENT');
      at(sec(4), 'spawn ' + x.id, () => { move('execution', x, 'STARTING', 'spawn'); });
      at(sec(9), 'first output ' + x.id, () => { move('execution', x, 'RUNNING', 'first_output'); x.last_output_at = S.clock; move('task', t, 'RUNNING', 'routed'); });
      at(sec(rng() < 0.5 ? 150 : 210), 'finish ' + x.id, () => finishExecution(m, t, x));
    });
  }
  function finishExecution(m, t, x) {
    if (x.state === 'LOST' || x.state === 'AWAITING_APPROVAL' || x.state === 'STARTING') { at(sec(30), 'finish ' + x.id, () => finishExecution(m, t, x)); return; }
    if (x.state !== 'RUNNING' || m.state !== 'EXECUTING') return;
    move('execution', x, 'ENDED_OK', 'exited_success', { exit_code: 0 });
    move('task', t, 'VERIFYING', 'execution_succeeded');
    if (taskOf(m).every((k) => k.state === 'VERIFYING' || k.state === 'SUCCEEDED' || k.state === 'SKIPPED')) verifyMission(m);
  }
  function verifyMission(m, failFirst) {
    move('mission', m, 'VERIFYING', 'all_tasks_done');
    const t = taskOf(m).find((k) => k.state === 'VERIFYING');
    const v = { id: 'v-' + (++S.counters.verification), mission: m.id, project: m.project, task: t.id, state: 'PENDING', checks: [], base_revision: 'r' + (100 + S.counters.verification) };
    S.verifications[v.id] = v; emit('verification.created', { kind: 'verification', id: v.id }, {}, { mission: m.id, project: m.project });
    at(sec(8), 'verify run ' + v.id, () => { move('verification', v, 'RUNNING', 'start'); });
    at(sec(failFirst ? 40 : 60), 'verify end ' + v.id, () => concludeVerification(m, v, !!failFirst));
    return v;
  }
  function concludeVerification(m, v, fail) {
    if (v.state !== 'RUNNING') { if (v.state === 'PENDING') at(sec(10), 'verify end ' + v.id, () => concludeVerification(m, v, fail)); return; }
    const ts = taskOf(m).filter((k) => k.state === 'VERIFYING');
    if (fail) {
      v.checks = [{ name: m.fail_check || 'unit checks', kind: 'command', result: 'fail' }];
      move('verification', v, 'FAILED', 'a_check_fails');
      ts.forEach((k) => move('task', k, 'READY', 'checks_failed_retry'));
      m.replans = (m.replans || 0) + 1;
      m.reason = 'Verification failed: ' + (m.fail_check || 'unit checks');
      move('mission', m, 'REPLANNING', 'verification_failed');
      replanChain(m);
    } else {
      v.checks = [{ name: 'unit checks', kind: 'command', result: 'pass' }, { name: 'lint', kind: 'command', result: 'pass' }];
      move('verification', v, 'PASSED', 'all_checks_pass');
      ts.forEach((k) => move('task', k, 'SUCCEEDED', 'checks_passed'));
      move('mission', m, 'REVIEWING', 'verified');
      m.reason = null;
      const r = { id: 'r-' + (++S.counters.review), mission: m.id, project: m.project, state: 'PENDING' };
      S.reviews[r.id] = r; emit('review.requested', { kind: 'review', id: r.id }, { notify: true }, { mission: m.id, project: m.project });
    }
  }
  function stopSiblings(m, except) {
    Object.values(S.executions).filter((e) => e.mission === m.id && e !== except && e.state === 'RUNNING').forEach((e) => {
      move('execution', e, 'STOPPING', 'stop'); move('execution', e, 'ENDED_KILLED', 'process_gone');
      const k = S.tasks[e.task]; if (k.state === 'RUNNING') move('task', k, 'READY', 'execution_failed_retry');
    });
  }
  function replanChain(m) {
    at(sec(30), 'replan ' + m.id, () => {
      if (m.state !== 'REPLANNING') return;
      if ((m.replans || 0) > 2) { m.reason = 'Replan budget exhausted'; move('mission', m, 'BLOCKED', 'replan_budget_exhausted'); return; }
      const p = newPlan(m);
      const a = newApproval(m, 'plan', { what: 'Plan v' + p.version + ' for "' + m.title + '"', why: m.reason || 'The previous attempt did not pass.', consequence: 'Approving starts the tasks again on ' + m.branch + '. Rejecting cancels the mission.' }, p.id);
      move('mission', m, 'APPROVAL_REQUIRED', 'plan_needs_approval');
      m.approval = a.id;
    });
  }
  function planningChain(m, auto) {
    at(sec(25), 'understood ' + m.id, () => { move('mission', m, 'CONTEXT_GATHERING', 'understood'); });
    at(sec(45), 'context ' + m.id, () => { move('mission', m, 'REASONING', 'context_ready'); });
    at(sec(75), 'reasoned ' + m.id, () => {
      move('mission', m, 'PLANNING', 'reasoned');
      const p = newPlan(m, auto ? 'APPROVED' : undefined);
      ['Make the change', 'Add a test'].forEach((title) => newTask(m, String(m.tasks.length + 1), title));
      if (auto) { move('mission', m, 'APPROVED', 'plan_auto_approved'); startExecution(m, sec(15)); } else {
        const a = newApproval(m, 'plan', { what: 'Plan v' + p.version + ' for "' + m.title + '"', why: 'The plan needs your approval.', consequence: 'Approving starts 2 tasks on ' + m.branch + '. Rejecting cancels the mission.' }, p.id);
        move('mission', m, 'APPROVAL_REQUIRED', 'plan_needs_approval'); m.approval = a.id;
      }
    });
  }

  // ---------- user and Core actions ----------
  function act(kind, id, arg) {
    S.actor = 'device';
    try { return doAct(kind, id, arg); } catch (e) { if (opts.strict) throw e; return { ok: false, reason: String(e.message || e) }; } finally { S.actor = 'system'; }
  }
  function doAct(kind, id, arg) {
    const bad = (reason) => ({ ok: false, reason });
    if (S.estop.engaged && ['resume', 'resume_all', 'unblock'].includes(kind)) return bad('The emergency stop is engaged: nothing new starts or resumes until you re-arm it');
    if (kind === 'rearm') {
      if (!S.estop.engaged) return bad('The emergency stop is not engaged');
      S.estop = { engaged: false, at: null }; emit('core.estop_rearmed', { kind: 'core', id: 'core' }, {}, {});
      return { ok: true };
    }
    if (kind === 'estop' && S.estop.engaged) return bad('The emergency stop is already engaged');
    if (kind === 'pause_all' || kind === 'resume_all' || kind === 'estop') {
      const [from, one] = { pause_all: ['EXECUTING', 'pause'], resume_all: ['PAUSED', 'resume'], estop: ['EXECUTING', 'stop'] }[kind];
      const done = Object.values(S.missions).filter((x) => x.state === from && doAct(one, x.id).ok);
      if (!done.length && kind !== 'estop') return bad(kind === 'resume_all' ? 'Nothing is paused' : 'Nothing is running');
      if (kind === 'estop') { done.forEach((x) => { x.reason = 'Emergency stop'; }); S.estop = { engaged: true, at: S.clock }; emit('core.estop_engaged', { kind: 'core', id: 'core' }, { stopped: done.length }, {}); }
      return { ok: true, n: done.length };
    }
    if (kind === 'approve' || kind === 'reject') {
      const a = S.approvals[id]; if (!a) return bad('No such approval');
      if (a.state !== 'PENDING') return bad('This approval is already ' + a.state.toLowerCase());
      const m = M(a.mission), yes = kind === 'approve';
      const stale = a.kind === 'plan' ? m.state !== 'APPROVAL_REQUIRED' : S.executions[a.ref].state !== 'AWAITING_APPROVAL' || m.state !== 'EXECUTING';
      if (stale) { move('approval', a, 'SUPERSEDED', 'plan_replaced'); return bad('This approval is no longer needed'); }
      decideApproval(a, yes ? 'APPROVED' : 'REJECTED', kind);
      if (a.kind === 'plan') {
        const p = S.plans[a.ref];
        if (yes) { if (p && p.state === 'PROPOSED') move('plan', p, 'APPROVED', 'approved'); move('mission', m, 'APPROVED', 'approve'); m.approval = null; startExecution(m, sec(15)); } else { if (p && p.state === 'PROPOSED') move('plan', p, 'REJECTED', 'rejected'); move('mission', m, 'CANCELLED', 'reject'); m.approval = null; }
      } else {
        const x = S.executions[a.ref], t = S.tasks[x.task];
        if (yes) {
          move('execution', x, 'STARTING', 'resume_approved'); move('task', t, 'READY', 'approved'); move('task', t, 'ROUTING', 'dispatch');
          at(sec(5), 'resume ' + x.id, () => { move('execution', x, 'RUNNING', 'first_output'); x.last_output_at = S.clock; move('task', t, 'RUNNING', 'routed'); });
          move('approval', a, 'CONSUMED', 'action_executed');
        } else {
          move('execution', x, 'ENDED_REJECTED', 'rejected'); move('task', t, 'BLOCKED', 'rejected');
          m.reason = 'You rejected: ' + a.presented.what; move('mission', m, 'BLOCKED', 'block');
        }
      }
      return { ok: true };
    }
    if (kind === 'plan_changes') {
      const a = S.approvals[id]; if (!a || a.state !== 'PENDING' || a.kind !== 'plan') return bad('No plan decision to change');
      const m = M(a.mission), p = S.plans[a.ref];
      if (m.state !== 'APPROVAL_REQUIRED') return bad('This plan is no longer waiting');
      move('approval', a, 'SUPERSEDED', 'plan_replaced'); a.decided_by = 'user_device'; a.decided_at = S.clock;
      if (p && p.state === 'PROPOSED') move('plan', p, 'SUPERSEDED', 'superseded');
      m.approval = null; m.reason = 'Changes requested on the plan';
      move('mission', m, 'PLANNING', 'request_changes');
      at(sec(30), 'replan after changes ' + m.id, () => {
        if (m.state !== 'PLANNING') return;
        const p2 = newPlan(m);
        const a2 = newApproval(m, 'plan', { what: 'Plan v' + p2.version + ' for "' + m.title + '"', why: 'You asked for changes to the previous plan.', consequence: 'Approving starts the tasks on ' + m.branch + '. Rejecting cancels the mission.' }, p2.id);
        m.reason = null; move('mission', m, 'APPROVAL_REQUIRED', 'plan_needs_approval'); m.approval = a2.id;
      });
      return { ok: true };
    }
    if (kind === 'confirm' || kind === 'retract') {
      const k = S.knowledge.find((x) => x.id === id);
      if (!k || k.state !== 'CANDIDATE') return bad('Nothing to decide on this item');
      const from = k.state; k.state = kind === 'confirm' ? 'CONFIRMED' : 'RETRACTED';
      emit('knowledge_item.state_changed', { kind: 'knowledge_item', id }, { from, to: k.state, trigger: kind === 'confirm' ? 'confirm' : 'reject' }, { project: k.project });
      return { ok: true };
    }
    if (kind === 'enable') {
      const a = S.automations.find((x) => x.id === id);
      if (!a || (a.state !== 'SUSPENDED' && a.state !== 'PENDING_APPROVAL')) return bad('This automation does not wait for you');
      const from = a.state; a.state = 'ENABLED'; a.note = null;
      emit('automation.state_changed', { kind: 'automation', id }, { from, to: 'ENABLED', trigger: from === 'SUSPENDED' ? 'user_reenables' : 'approve' }, {});
      return { ok: true };
    }
    const m = M(id); if (!m) return bad('No such mission');
    if (kind === 'accept' || kind === 'changes') {
      const r = Object.values(S.reviews).find((x) => x.mission === m.id && (x.state === 'PENDING' || x.state === 'IN_REVIEW'));
      if (m.state !== 'REVIEWING' || !r) return bad('Nothing to review on this mission');
      if (r.state === 'PENDING') move('review', r, 'IN_REVIEW', 'user_reviews');
      if (kind === 'accept') { move('review', r, 'ACCEPTED', 'verdict_accept'); move('mission', m, 'COMPLETED', 'accepted'); } else {
        move('review', r, 'CHANGES_REQUESTED', 'verdict_changes'); m.reason = 'Changes requested'; m.replans = (m.replans || 0) + 1; move('mission', m, 'REPLANNING', 'changes_requested'); replanChain(m);
      }
      return { ok: true };
    }
    if (kind === 'unblock') {
      if (m.state !== 'BLOCKED') return bad('This mission is not blocked');
      const back = m.held_from; m.reason = null;
      move('mission', m, 'RESUMED', 'unblock');
      if (back === 'EXECUTING') {
        at(sec(8), 'redispatch ' + m.id, () => {
          move('mission', m, 'EXECUTING', 'redispatch');
          taskOf(m).filter((t) => t.state === 'BLOCKED').forEach((t, i) => { move('task', t, 'READY', 'unblock'); spawnTask(m, t, sec(i * 7)); });
        });
      } else {
        at(sec(8), 'redispatch ' + m.id, () => { move('mission', m, 'UNDERSTANDING', 'redispatch_before_plan'); planningChain(m, false); });
      }
      return { ok: true };
    }
    if (kind === 'resume') {
      if (m.state !== 'PAUSED') return bad('This mission is not paused');
      move('mission', m, 'RESUMED', 'resume');
      at(sec(6), 'redispatch ' + m.id, () => {
        move('mission', m, 'EXECUTING', 'redispatch');
        const x = Object.values(S.executions).find((e) => e.mission === m.id && e.state === 'PAUSED');
        if (x) { const t = S.tasks[x.task]; move('execution', x, 'STARTING', 'resume'); at(sec(5), 'resume run', () => { move('execution', x, 'RUNNING', 'first_output'); x.last_output_at = S.clock; if (t.state === 'PAUSED') { move('task', t, 'READY', 'resume'); move('task', t, 'ROUTING', 'dispatch'); move('task', t, 'RUNNING', 'routed'); } at(sec(120), 'finish', () => finishExecution(m, t, x)); }); }
      });
      return { ok: true };
    }
    if (kind === 'replan') {
      if (m.state !== 'FAILED') return bad('Only a failed mission is replanned');
      m.replans = (m.replans || 0) + 1; m.reason = 'Replan after failure'; move('mission', m, 'REPLANNING', 'replan'); replanChain(m); return { ok: true };
    }
    if (kind === 'cancel') {
      if (!edgeOk('mission', m.state, 'CANCELLED', 'cancel')) return bad('A ' + m.state.toLowerCase().replace(/_/g, ' ') + ' mission cannot be cancelled here');
      if (m.state === 'PAUSED') Object.values(S.executions).filter((e) => e.mission === m.id && e.state === 'PAUSED').forEach((e) => move('execution', e, 'ENDED_KILLED', 'discarded'));
      move('mission', m, 'CANCELLED', 'cancel'); return { ok: true };
    }
    if (kind === 'start') {
      if (m.state !== 'CREATED') return bad('Only a mission that has not started can be started');
      move('mission', m, 'UNDERSTANDING', 'start'); planningChain(m, false); return { ok: true };
    }
    if (kind === 'stop') {
      const xs = Object.values(S.executions).filter((e) => e.mission === m.id && (e.state === 'RUNNING' || e.state === 'STARTING'));
      if (m.state !== 'EXECUTING' || !xs.length) return bad('Only a running mission can be stopped');
      xs.forEach((x) => { move('execution', x, 'STOPPING', 'stop'); move('execution', x, 'ENDED_KILLED', 'process_gone'); const k = S.tasks[x.task]; if (k.state === 'RUNNING') move('task', k, 'READY', 'execution_failed_retry'); });
      m.reason = 'You stopped this mission'; move('mission', m, 'BLOCKED', 'block'); return { ok: true };
    }
    if (kind === 'pause') {
      const xs = Object.values(S.executions).filter((e) => e.mission === m.id && e.state === 'RUNNING');
      if (m.state !== 'EXECUTING' || !xs.length) return bad('Only a running mission can be paused');
      xs.forEach((x) => move('execution', x, 'PAUSING', 'pause_requested'));
      at(sec(5), 'halt', () => { xs.forEach((x) => { move('execution', x, 'PAUSED', 'halted_at_boundary'); move('task', S.tasks[x.task], 'PAUSED', 'pause'); }); move('mission', m, 'PAUSED', 'pause'); });
      return { ok: true };
    }
    return bad('Unknown action ' + kind);
  }

  function triggerApproval() {
    S.actor = 'system';
    const xs = Object.values(S.executions).filter((x) => x.state === 'RUNNING' && !x.stuck);
    if (!xs.length) return { ok: false, reason: 'No running execution to ask from' };
    const x = pick(xs), m = missionOf(x), t = S.tasks[x.task];
    const ask = pick(['git push origin ' + m.branch, 'npm install --save-dev vitest', 'delete build/ and rebuild']);
    move('execution', x, 'AWAITING_APPROVAL', 'hook_asked');
    move('task', t, 'AWAITING_APPROVAL', 'action_needs_approval');
    newApproval(m, 'action', { what: 'Run: ' + ask, why: 'The execution asked before crossing its boundary.', consequence: 'Approving lets the execution continue with this one action. Rejecting ends the execution and blocks the mission.' }, x.id);
    return { ok: true, execution: x.id };
  }
  function injectFailure(kind, harness) {
    S.actor = 'system';
    kind = kind || 'execution';
    if (kind === 'spawn') {
      const hid = harness || 'claude_code', b = S.harnesses.find((h) => h.id === hid).breaker;
      for (let i = 0; i < 3; i++) b.failures.push(S.clock - i * 1000);
      b.state = 'open'; b.until = S.clock + min(5); b.last_error = 'spawn failed: could not start the process';
      emit('harness.breaker_opened', { kind: 'harness', id: hid }, { failures: 3, window_min: 10 }, {});
      at(min(5), 'half open', () => { if (b.state !== 'open') return; b.state = 'half_open'; emit('harness.breaker_half_open', { kind: 'harness', id: hid }, {}, {}); at(sec(40), 'close', () => { if (b.state !== 'half_open') return; b.state = 'closed'; b.failures = []; b.last_error = null; emit('harness.breaker_closed', { kind: 'harness', id: hid }, {}, {}); }); });
      return { ok: true };
    }
    if (kind === 'verification') {
      const v = Object.values(S.verifications).find((x) => x.state === 'RUNNING');
      if (!v) return { ok: false, reason: 'No verification is running' };
      concludeVerification(M(v.mission), v, true);
      return { ok: true, mission: v.mission };
    }
    const xs = Object.values(S.executions).filter((x) => x.state === 'RUNNING');
    if (!xs.length) return { ok: false, reason: 'No running execution to fail' };
    const x = pick(xs), m = missionOf(x), t = S.tasks[x.task];
    x.reason = 'exited with an error'; move('execution', x, 'ENDED_ERROR', 'exited_error', { exit_code: 1 });
    stopSiblings(m, x);
    if ((m.replans || 0) < 2) {
      move('task', t, 'READY', 'execution_failed_retry'); m.replans = (m.replans || 0) + 1; m.reason = 'Execution ended with an error';
      move('mission', m, 'REPLANNING', 'task_failed_retryable'); replanChain(m);
    } else {
      move('task', t, 'FAILED', 'execution_failed_final'); m.reason = 'Unrecoverable: the execution kept failing';
      move('mission', m, 'FAILED', 'unrecoverable');
    }
    return { ok: true, mission: m.id };
  }

  // ---------- the scripted story ----------
  function script() {
    const stuckAt = sec(200);
    atAbs(sec(20), 'progress', progressTick);
    atAbs(sec(60), 'theme starts', () => { const m = M('m-theme'); move('mission', m, 'UNDERSTANDING', 'start'); planningChain(m, true); });
    atAbs(sec(120), 'offline verified', () => { const v = Object.values(S.verifications).find((x) => x.mission === 'm-offline'); concludeVerification(M('m-offline'), v, false); });
    atAbs(stuckAt, 'date stuck', () => { const x = S.executions['x-date-1']; if (x && x.state === 'RUNNING') { x.stuck = true; emit('execution.quiet', { kind: 'execution', id: x.id }, { since: S.clock }, { mission: x.mission, project: x.project }); } });
    atAbs(stuckAt + sec(130), 'date lost', () => { const x = S.executions['x-date-1']; if (x && x.state === 'RUNNING' && x.stuck) move('execution', x, 'LOST', 'heartbeat_missing'); });
    atAbs(stuckAt + sec(190), 'date adopted', () => { const x = S.executions['x-date-1']; if (x && x.state === 'LOST') { move('execution', x, 'RUNNING', 'adopted'); x.stuck = false; x.last_output_at = S.clock; } });
    atAbs(sec(480), 'date ends', () => { const m = M('m-date'), x = S.executions['x-date-1'], t = S.tasks[x.task]; m.fail_check = 'date-boundary check'; if (x.state === 'RUNNING' && m.state === 'EXECUTING') { move('execution', x, 'ENDED_OK', 'exited_success', { exit_code: 0 }); move('task', t, 'VERIFYING', 'execution_succeeded'); verifyMission(m, true); } });
    atAbs(sec(300), 'ambient', ambient);
    atAbs(min(8), 'codex breaker trips', () => injectFailure('spawn', 'codex'));
    atAbs(min(12), 'personal window nearly full', () => { usage('acc-personal').window5h = 94; S.actor = 'system'; emit('usage.observed', { kind: 'account', id: 'acc-personal' }, { note: 'its 5 hour window is nearly full' }, {}); });
    atAbs(min(24), 'work week reaches the reserve line', () => { usage('acc-work').week = 80; S.actor = 'system'; emit('usage.observed', { kind: 'account', id: 'acc-work' }, { note: 'the week reached the 20% reserve line' }, {}); });
  }
  function ambient() {
    const roll = rng();
    S.actor = 'system';
    if (roll < 0.35) {
      const k = { id: 'k-' + (++S.counters.knowledge), project: pick(S.projects).id, state: 'CANDIDATE', text: pick(['Tests run with the date pinned to UTC', 'Release notes live in CHANGELOG.md', 'Prefer small commits per task']), source: 'feedback' };
      S.knowledge.push(k); emit('knowledge_item.created', { kind: 'knowledge_item', id: k.id }, {}, { project: k.project });
    } else if (roll < 0.65) {
      const u = usage('acc-personal'); if (u && u.week != null) u.week = Math.min(100, Math.round((u.week + 0.4) * 10) / 10);
      emit('usage.observed', { kind: 'account', id: 'acc-personal' }, {}, {});
    } else {
      const idea = { id: 'i-' + (++S.counters.idea), project: 'ideas', title: pick(['Quick-capture from the phone', 'Shared digest for the team', 'Weekly retrospective map']), state: 'CAPTURED' };
      S.ideas.push(idea); emit('idea.created', { kind: 'idea', id: idea.id }, {}, { project: 'ideas' });
    }
    at(sec(90 + Math.floor(rng() * 60)), 'ambient', ambient);
  }

  // ---------- fixtures ----------
  function build(sd) {
    rng = mulberry32(sd); queue = []; qn = 0; seq = 0;
    S = {
      seed: sd, clock: 0, speed: 1, playing: false, actor: 'system', quiet: true, pruned: false, estop: { engaged: false, at: null },
      counters: { approval: 0, verification: 0, review: 0, knowledge: 6, idea: 5, message: 4, mission: 0 },
      projects: [
        { id: 'archeus', name: 'Archeus', note: 'Active. Your projects, in context.', root: 'archeus/' },
        { id: 'notes', name: 'Notes', note: 'Research and capture evolving context.', root: 'notes/' },
        { id: 'ideas', name: 'Ideas', note: 'Early concepts.', root: 'ideas/' }
      ],
      missions: {}, tasks: {}, executions: {}, plans: {}, approvals: {}, verifications: {}, reviews: {}, events: [],
      ideas: [
        { id: 'i-1', project: 'ideas', title: 'Voice notes capture', state: 'PLANNED' }, { id: 'i-2', project: 'ideas', title: 'Calm mode for the evening', state: 'PARKED' },
        { id: 'i-3', project: 'notes', title: 'Search inside a Replay', state: 'EXPLORED' }, { id: 'i-4', project: 'archeus', title: 'Weekly digest as an email', state: 'SCHEDULED' },
        { id: 'i-5', project: 'ideas', title: 'Map of what changed since Monday', state: 'CAPTURED' }
      ],
      knowledge: [
        { id: 'k-1', project: 'archeus', state: 'CONFIRMED', text: 'Tests run through the shared lock', source: 'user' }, { id: 'k-2', project: 'archeus', state: 'CONFIRMED', text: 'Commits end with the two attribution lines', source: 'user' },
        { id: 'k-3', project: 'notes', state: 'CONFIRMED', text: 'Notes are Markdown, one file per topic', source: 'user' }, { id: 'k-4', project: 'archeus', state: 'CANDIDATE', text: 'Prefer the stdlib over a new dependency', source: 'feedback' },
        { id: 'k-5', project: 'ideas', state: 'SUPERSEDED', text: 'Ideas live in one list', source: 'user' }, { id: 'k-6', project: 'notes', state: 'CANDIDATE', text: 'Export formats: CSV and JSON', source: 'feedback' }
      ],
      automations: [
        { id: 'au-1', name: 'Nightly dependency check', state: 'ENABLED', trigger: 'schedule: 02:00', next_run: '02:00', runs: 12 },
        { id: 'au-2', name: 'Review a pull request when it opens', state: 'PENDING_APPROVAL', trigger: 'event: pull_request.opened', next_run: null, runs: 0 },
        { id: 'au-3', name: 'Weekly digest', state: 'SUSPENDED', trigger: 'schedule: Mon 08:00', next_run: null, runs: 7, note: 'The loop guard tripped; only you can re-enable it.' }
      ],
      accounts: [
        { id: 'acc-work', label: 'Claude Code, work', harness: 'claude_code', kind: 'subscription_oauth', state: 'AVAILABLE', priority: 1 },
        { id: 'acc-personal', label: 'Claude Code, personal', harness: 'claude_code', kind: 'subscription_oauth', state: 'CONSTRAINED', priority: 2 },
        { id: 'acc-codex', label: 'Codex, work', harness: 'codex', kind: 'subscription_oauth', state: 'UNVERIFIED', priority: 3 }
      ],
      models: [
        { id: 'claude-sonnet', label: 'Sonnet 5.5', harness: 'claude_code', tier: 'large' }, { id: 'claude-opus', label: 'Opus', harness: 'claude_code', tier: 'xlarge' },
        { id: 'claude-haiku', label: 'Haiku', harness: 'claude_code', tier: 'small' }, { id: 'codex-main', label: 'Codex default', harness: 'codex', tier: 'large' }
      ],
      usage: {
        'acc-work': { window5h: 38, week: 52, resets: '5 h window resets 13:10' },
        'acc-personal': { window5h: 84.6, week: 71, resets: '5 h window resets 12:40' },
        'acc-codex': { window5h: null, week: null, resets: null } // unknown, never shown as 0
      },
      harnesses: [
        { id: 'claude_code', label: 'Claude Code', state: 'AVAILABLE', breaker: { state: 'closed', failures: [], until: 0, last_error: null } },
        { id: 'codex', label: 'Codex', state: 'AVAILABLE', breaker: { state: 'closed', failures: [], until: 0, last_error: null } },
        { id: 'pi', label: 'pi', state: 'MISSING', breaker: { state: 'closed', failures: [], until: 0, last_error: null } }
      ],
      hooks: [{ id: 'h-1', event: 'PreToolUse', name: 'ask before git push', state: 'ENABLED' }, { id: 'h-2', event: 'PostToolUse', name: 'format changed files', state: 'ENABLED' }, { id: 'h-3', event: 'Stop', name: 'write a checkpoint', state: 'DISABLED' }],
      mcp: [{ id: 'mcp-1', name: 'filesystem (read only)', state: 'ENABLED' }, { id: 'mcp-2', name: 'issue tracker', state: 'DISABLED' }],
      agents: [{ id: 'ag-1', name: 'planner', tier: 'large' }, { id: 'ag-2', name: 'verifier', tier: 'small' }, { id: 'ag-3', name: 'reviewer', tier: 'large' }, { id: 'ag-4', name: 'doc writer', tier: 'small' }],
      devices: [{ id: 'd-1', name: 'This browser (simulated)', state: 'ACTIVE' }, { id: 'd-2', name: 'Phone (simulated)', state: 'ACTIVE' }, { id: 'd-3', name: 'Old laptop (simulated)', state: 'REVOKED' }],
      messages: [
        { id: 'c-1', from: 'you', text: 'What needs me today?', at: -min(40) },
        { id: 'c-2', from: 'archeus', text: 'Two things wait on you: the plan for Search provenance and a clarification on Export backup. Simulated reply.', at: -min(39) },
        { id: 'c-3', from: 'you', text: 'Fix the date test', at: -min(31) },
        { id: 'c-4', from: 'archeus', text: 'Started Fix date test as a mission on Archeus. Simulated reply.', at: -min(30) }
      ]
    };
    const mk = (id, title, project, branch, extra) => (S.missions[id] = Object.assign({ id, title, project, branch, state: 'CREATED', held_from: null, tasks: [], plan_version: 0, replans: 0, origin: 'conversation', reason: null, created_at: 0, updated_at: 0, account: 'acc-work', model: 'claude-sonnet' }, extra || {}));
    const path = (m, steps, t0) => { S.clock = t0; steps.forEach(([to, trig], i) => { S.clock = t0 + i * sec(45); move('mission', m, to, trig); }); };

    // m-docs: a finished mission with its history
    let m = mk('m-docs', 'Docs refresh', 'archeus', 'docs/changelog');
    S.clock = -min(120); emit('mission.created', { kind: 'mission', id: m.id }, {}, { mission: m.id, project: m.project });
    path(m, [['UNDERSTANDING', 'start'], ['CONTEXT_GATHERING', 'understood'], ['REASONING', 'context_ready'], ['PLANNING', 'reasoned'], ['APPROVED', 'plan_auto_approved'], ['EXECUTING', 'dispatch'], ['VERIFYING', 'all_tasks_done'], ['REVIEWING', 'verified'], ['COMPLETED', 'accepted']], -min(120));
    let t = newTask(m, '1', 'Summarise the merged changes', 'SUCCEEDED'); newExec(m, t, 'ENDED_OK', { started_at: -min(100) });
    newPlan(m, 'APPROVED'); S.plans['p-docs-v1'].state = 'APPROVED';

    // m-date: running, history up to its first execution
    m = mk('m-date', 'Fix date test', 'archeus', 'fix/date-test');
    S.clock = -min(31); emit('mission.created', { kind: 'mission', id: m.id }, {}, { mission: m.id, project: m.project });
    path(m, [['UNDERSTANDING', 'start'], ['CONTEXT_GATHERING', 'understood'], ['REASONING', 'context_ready'], ['PLANNING', 'reasoned'], ['APPROVED', 'plan_auto_approved'], ['EXECUTING', 'dispatch']], -min(31));
    newPlan(m, 'APPROVED'); t = newTask(m, '1', 'Run the date suite and fix the failing check', 'RUNNING');
    newExec(m, t, 'RUNNING', { started_at: -min(24), last_output_at: -sec(10) });
    m.plan_version = 1;

    // m-search: waits for a plan approval
    m = mk('m-search', 'Search provenance', 'archeus', 'feat/search');
    S.clock = -min(12); emit('mission.created', { kind: 'mission', id: m.id }, {}, { mission: m.id, project: m.project });
    path(m, [['UNDERSTANDING', 'start'], ['CONTEXT_GATHERING', 'understood'], ['REASONING', 'context_ready'], ['PLANNING', 'reasoned'], ['APPROVAL_REQUIRED', 'plan_needs_approval']], -min(12));
    ['Read the recorded sources for the search index', 'Attach a provenance link to each result', 'Add a test that every result links to a source'].forEach((tt, i) => newTask(m, String(i + 1), tt));
    S.clock = -min(8); const p1 = newPlan(m);
    m.approval = newApproval(m, 'plan', { what: 'Plan v1 for "Search provenance"', why: 'Plan approval required.', consequence: 'Approving starts 3 tasks on feat/search. Rejecting cancels the mission. No undo.' }, p1.id).id;

    // m-lint: failed
    m = mk('m-lint', 'Lint config migration', 'archeus', 'chore/lint', { replans: 1, reason: 'Unrecoverable: the lint schema was not found' });
    S.clock = -min(70); emit('mission.created', { kind: 'mission', id: m.id }, {}, { mission: m.id, project: m.project });
    path(m, [['UNDERSTANDING', 'start'], ['CONTEXT_GATHERING', 'understood'], ['REASONING', 'context_ready'], ['PLANNING', 'reasoned'], ['APPROVED', 'plan_auto_approved'], ['EXECUTING', 'dispatch'], ['FAILED', 'unrecoverable']], -min(70));
    newPlan(m, 'APPROVED'); t = newTask(m, '1', 'Migrate the lint config', 'FAILED'); newExec(m, t, 'ENDED_ERROR', { started_at: -min(60), reason: 'exited with an error' });

    // m-offline: verifying
    m = mk('m-offline', 'Offline capture', 'notes', 'feat/offline-index');
    S.clock = -min(25); emit('mission.created', { kind: 'mission', id: m.id }, {}, { mission: m.id, project: m.project });
    path(m, [['UNDERSTANDING', 'start'], ['CONTEXT_GATHERING', 'understood'], ['REASONING', 'context_ready'], ['PLANNING', 'reasoned'], ['APPROVED', 'plan_auto_approved'], ['EXECUTING', 'dispatch'], ['VERIFYING', 'all_tasks_done']], -min(25));
    newPlan(m, 'APPROVED'); t = newTask(m, '1', 'Capture an offline copy of the notes', 'VERIFYING'); newExec(m, t, 'ENDED_OK', { started_at: -min(18) });
    const v = { id: 'v-' + (++S.counters.verification), mission: m.id, project: m.project, task: t.id, state: 'PENDING', checks: [], base_revision: 'r90' };
    S.verifications[v.id] = v; S.clock = -min(2); move('verification', v, 'RUNNING', 'start');

    // m-export: blocked by a question
    m = mk('m-export', 'Export backup', 'notes', 'docs/export', { reason: 'Archeus asks: export as CSV or JSON?' });
    S.clock = -min(9); emit('mission.created', { kind: 'mission', id: m.id }, {}, { mission: m.id, project: m.project });
    path(m, [['UNDERSTANDING', 'start'], ['BLOCKED', 'needs_clarification']], -min(9));

    // m-voice: paused
    m = mk('m-voice', 'Voice notes prototype', 'ideas', 'spike/voice', { origin: 'idea' });
    S.clock = -min(50); emit('mission.created', { kind: 'mission', id: m.id }, {}, { mission: m.id, project: m.project });
    path(m, [['UNDERSTANDING', 'start'], ['CONTEXT_GATHERING', 'understood'], ['REASONING', 'context_ready'], ['PLANNING', 'reasoned'], ['APPROVED', 'plan_auto_approved'], ['EXECUTING', 'dispatch'], ['PAUSED', 'pause']], -min(50));
    newPlan(m, 'APPROVED'); t = newTask(m, '1', 'Record and transcribe a short note', 'PAUSED'); newExec(m, t, 'PAUSED', { started_at: -min(40) });

    // m-theme: starts later, in the script
    m = mk('m-theme', 'Theme tokens audit', 'archeus', 'chore/tokens');
    S.clock = -min(2); emit('mission.created', { kind: 'mission', id: m.id }, {}, { mission: m.id, project: m.project });

    S.events.sort((a, b) => a.at - b.at || a.seq - b.seq).forEach((e, i) => { e.seq = i + 1; });
    seq = S.events.length; S.clock = 0; S.quiet = false;
    script();
    if (opts.story === 'calm') calmDown();
  }
  // ?story=calm (concept 07): five projects, each with a finished mission and a captured idea, and the script silent.
  function calmDown() {
    const keep = new Set(['m-docs']), gone = (x) => x.mission && !keep.has(x.mission);
    for (const id of Object.keys(S.missions)) if (!keep.has(id)) delete S.missions[id];
    S.projects = [
      {id: 'notes', name: 'Notes', note: '', root: 'notes/'},
      {id: 'archeus', name: 'Archeus', note: '', root: 'archeus/'},
      {id: 'ideas', name: 'Website', note: '', root: 'website/'},
      {id: 'alpha', name: 'Project Alpha', note: '', root: 'alpha/'},
      {id: 'research', name: 'Research', note: '', root: 'research/'}
    ];
    const finished = S.missions['m-docs'];
    finished.title = 'Fix date test';
    for (const p of S.projects) if (p.id !== 'archeus') {
      const id = 'm-calm-' + p.id;
      S.missions[id] = {...finished, id, project: p.id, tasks: [], plan_version: 0, branch: 'fix/date-test'};
    }
    S.ideas = S.projects.map((p, i) => ({id: 'i-calm-' + i, project: p.id, title: 'Offline capture', state: 'CAPTURED'}));
    for (const key of ['tasks', 'executions', 'approvals', 'verifications', 'reviews', 'plans']) for (const [id, x] of Object.entries(S[key])) if (!keep.has(x.mission)) delete S[key][id];
    S.events = S.events.filter((e) => !gone(e)); seq = S.events.length;
    S.knowledge.forEach((k) => { if (k.state === 'CANDIDATE') k.state = 'CONFIRMED'; });
    S.automations.forEach((x) => { if (x.state === 'SUSPENDED' || x.state === 'PENDING_APPROVAL') x.state = 'ENABLED'; });
    queue = [];
  }

  // ---------- clock ----------
  function advance(ms) {
    const target = S.clock + ms;
    for (;;) {
      queue.sort((a, b) => a.t - b.t || a.n - b.n);
      if (!queue.length || queue[0].t > target) break;
      const it = queue.shift();
      S.clock = Math.max(S.clock, it.t);
      S.actor = 'system';
      it.fn();
    }
    S.clock = target;
    subs.forEach((f) => f({ seq, at: S.clock, type: 'clock', subject: null, payload: {} }));
  }

  // ---------- derived reads ----------
  function attention() {
    const out = [];
    const mission = (id) => S.missions[id];
    Object.values(S.approvals).filter((a) => a.state === 'PENDING').forEach((a) => out.push({ id: 'att-' + a.id, group: 'Decide', kind: 'approval', ref: a.id, state: a.state, reason: a.presented.what, mission_id: a.mission, project_id: a.project, since: a.created_at }));
    Object.values(S.missions).forEach((m) => {
      if (m.state === 'REVIEWING') out.push({ id: 'att-rev-' + m.id, group: 'Review', kind: 'verification', ref: m.id, state: m.state, reason: 'Verified, waiting for your review: ' + m.title, mission_id: m.id, project_id: m.project, since: m.updated_at });
      if (m.state === 'BLOCKED') out.push({ id: 'att-blk-' + m.id, group: 'Unblock', kind: 'mission', ref: m.id, state: m.state, reason: m.reason || 'Blocked', mission_id: m.id, project_id: m.project, since: m.updated_at });
      if (m.state === 'FAILED') out.push({ id: 'att-fail-' + m.id, group: 'Unblock', kind: 'mission', ref: m.id, state: m.state, reason: m.reason || 'Failed', mission_id: m.id, project_id: m.project, since: m.updated_at });
    });
    S.knowledge.filter((k) => k.state === 'CANDIDATE').forEach((k) => out.push({ id: 'att-' + k.id, group: 'Review', kind: 'knowledge', ref: k.id, state: k.state, reason: 'Remember this? ' + k.text, mission_id: null, project_id: k.project, since: 0 }));
    S.automations.filter((a) => a.state === 'SUSPENDED' || a.state === 'PENDING_APPROVAL').forEach((a) => out.push({ id: 'att-' + a.id, group: a.state === 'SUSPENDED' ? 'Unblock' : 'Decide', kind: 'automation', ref: a.id, state: a.state, reason: a.name + (a.state === 'SUSPENDED' ? ' is suspended' : ' waits for approval'), mission_id: null, project_id: null, since: 0 }));
    S.accounts.filter((a) => a.state === 'LIMITED' || a.state === 'UNAUTHENTICATED').forEach((a) => out.push({ id: 'att-' + a.id, group: 'Unblock', kind: 'account', ref: a.id, state: a.state, reason: a.label + ' is ' + a.state.toLowerCase(), mission_id: null, project_id: null, since: 0 }));
    const order = { Decide: 0, Review: 1, Unblock: 2 };
    return out.sort((a, b) => order[a.group] - order[b.group] || a.since - b.since);
  }
  const liveWork = () => Object.values(S.executions).filter((x) => present('execution', x.state).cls === 'active');
  function reading(x) {
    if (x.state === 'LOST') return 'Lost, Core is reconciling';
    if (x.state !== 'RUNNING') return null;
    const age = Math.floor((S.clock - x.last_output_at) / 1000);
    if (age >= 120) return 'no output for ' + Math.floor(age / 60) + ' min';
    return age < 60 ? 'output ' + Math.max(age, 0) + ' s ago' : 'output ' + Math.floor(age / 60) + ' min ago';
  }
  function sentence() {
    const a = attention().filter((i) => i.kind !== 'knowledge').length, r = liveWork().length;
    const blocked = Object.values(S.missions).filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED').length;
    const parts = [];
    if (a) parts.push(a + (a === 1 ? ' needs' : ' need') + ' you');
    if (r) parts.push(r + ' running');
    if (blocked) parts.push(blocked + ' stopped');
    return parts.length ? parts.join(' · ') : 'Nothing needs you.';
  }
  function replay(missionId) {
    const rows = S.events.filter((e) => e.mission === missionId && /state_changed$|created$|requested$|progress$/.test(e.type) && e.type !== 'execution.progress').map((e) => {
      const machine = e.subject.kind, p = e.payload || {};
      const state = e.type.endsWith('state_changed') ? p.to : null;
      return { seq: e.seq, at: e.at, time: clockLabel(e.at), title: machine + ' ' + (state || e.type.split('.')[1].toUpperCase()), subject: e.subject, trigger: p.trigger || null, category: state ? categoryOf(machine, state, p.trigger) : (e.type === 'approval.requested' ? 'SUSPENDED' : e.type.endsWith('created') ? 'INTENDED' : 'UNKNOWN'), settled_by: e.actor === 'device' ? 'device' : e.actor === 'system' ? 'core' : 'unknown' };
    });
    return { rows, pruned: S.pruned, gaps: REPLAY_GAPS };
  }

  // ---------- chat ----------
  const mid = () => 'c-' + (++S.counters.message);
  const post = (from, text, card) => { const m = { id: mid(), from, text, at: S.clock }; if (card) m.card = card; S.messages.push(m); emit('message.created', { kind: 'message', id: m.id }, {}, {}); return m; };
  function newMission(title, opts) {
    const id = 'm-n' + (++S.counters.mission);
    const m = { id, title, project: (opts && opts.project) || 'archeus', branch: 'feat/' + title.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 24), state: 'CREATED', held_from: null, tasks: [], plan_version: 0, replans: 0, origin: 'conversation', reason: null, created_at: S.clock, updated_at: S.clock, account: 'acc-work', model: 'claude-sonnet' };
    S.missions[id] = m; emit('mission.created', { kind: 'mission', id }, {}, { mission: id, project: m.project });
    if (!(opts && opts.hold)) at(sec(20), 'start ' + id, () => { move('mission', m, 'UNDERSTANDING', 'start'); planningChain(m, false); });
    return m;
  }
  // The same brain as the chat page and the terminal: slash.js parses, chat-engine.js answers.
  let sayChat = null;
  const say = (text) => (sayChat || (sayChat = createChat(api))).say(text);
  // ---------- S4: the chat module writes its records through these, so every record has an event and an actor ----------
  const asOwner = (fn) => { S.actor = 'device'; try { return fn(); } finally { S.actor = 'system'; } };
  const slug = (t) => String(t).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 24) || 'x';
  const chatApi = {
    post: (from, text, extra) => (from === 'you' ? asOwner : (f) => f())(() => { const m = post(from, text); if (extra) Object.assign(m, extra); return m; }),
    patch(id, fields) { const m = S.messages.find((x) => x.id === id); if (!m) return null; Object.assign(m, fields); emit('message.updated', { kind: 'message', id }, {}, {}); return m; },
    createMission: (title, project) => asOwner(() => newMission(title, { hold: true, project })),
    createIdea: (title, project) => asOwner(() => { const i = { id: 'i-' + (++S.counters.idea), project: project || 'ideas', title, state: 'CAPTURED' }; S.ideas.push(i); emit('idea.created', { kind: 'idea', id: i.id }, {}, { project: i.project }); return i; }),
    createProject: (name) => asOwner(() => { const p = { id: slug(name) + '-' + (S.projects.length + 1), name, note: 'Created from chat: a record only. Folders, clones and access are proposals.', root: slug(name) + '/' }; S.projects.push(p); emit('project.created', { kind: 'project', id: p.id }, {}, { project: p.id }); return p; }),
    addKnowledge: (rec) => asOwner(() => {
      const k = { id: 'k-' + (++S.counters.knowledge), project: rec.project || null, state: 'CANDIDATE', text: rec.text, source: rec.source || 'chat' };
      S.knowledge.push(k); emit('knowledge_item.created', { kind: 'knowledge_item', id: k.id }, {}, { project: k.project });
      if (rec.state === 'CONFIRMED') { k.state = 'CONFIRMED'; emit('knowledge_item.state_changed', { kind: 'knowledge_item', id: k.id }, { from: 'CANDIDATE', to: 'CONFIRMED', trigger: 'confirm' }, { project: k.project }); }
      return k;
    })
  };

  // ---------- security and health (as the board records them; simulated here) ----------
  function security() {
    const h = S.harnesses.find((x) => x.id === 'claude_code').breaker;
    return [
      { id: 'iso', label: 'Execution isolation (PV-20: AppContainer, job object, ACLs)', state: 'open', word: 'Not closed', note: 'Designed and tested with fixtures; physical reach is not built in V1. Critical holes G1 and G2 stay open until P20 closes.' },
      { id: 'broker', label: 'Provider broker (named pipe and bridge)', state: 'off', word: 'Built, switch off', note: 'Plumbing exists; no native broker runs.' },
      { id: 'origin', label: 'Core API origin gate', state: 'off', word: 'HTTP side built, switch off', note: 'The native interface is a fail-closed stub.' },
      { id: 'dispatch', label: 'Production dispatch switch', state: 'off', word: 'Off', note: 'No execution is started by a real Core in this build.' },
      { id: 'breaker', label: 'Spawn breaker (per harness)', state: h.state === 'closed' ? 'ok' : 'attention', word: h.state === 'closed' ? 'Closed' : h.state === 'open' ? 'Open: cannot start' : 'Half open: one trial', note: h.last_error || 'Trips at 3 failed starts in 10 minutes; a doubling wait of 15 s to 5 min per task; one trial after 5 minutes.' },
      { id: 'estop', label: 'Emergency stop and re-arm', state: S.estop.engaged ? 'attention' : 'ok', word: S.estop.engaged ? 'Engaged: nothing new starts' : 'Built', note: S.estop.engaged ? 'Missions stay Blocked "Emergency stop" and no new dispatch starts until you re-arm (a step-up).' : 'Stops every execution and blocks new dispatch until re-armed; re-arming needs a step-up.' },
      { id: 'cred', label: 'Credentials', state: 'ok', word: 'Rule: never handled', note: 'Archeus does not read, store, copy, inject or relay subscription tokens. Usage numbers come only from the existing usage reader (owner exception 2026-10-22).' },
      { id: 'stepup', label: 'Approvals', state: 'ok', word: 'Scoped and step-up', note: 'Deciding needs the approve scope; the chat decides only the card on screen.' }
    ];
  }
  function health() {
    const out = [];
    const ok = (id, label, detail) => out.push({ id, label, state: 'ok', detail });
    ok('core', 'Core process', 'Simulated: always up. Nothing is connected to a real Core.');
    ok('db', 'Database and event log', 'Events are kept 180 days; the open-mission extension is not built, so an older answer is UNKNOWN, never "nothing happened".');
    S.harnesses.forEach((x) => out.push({ id: 'h-' + x.id, label: 'Harness ' + x.label, state: x.state === 'MISSING' ? 'unknown' : x.breaker.state === 'closed' ? 'ok' : 'attention', detail: x.state === 'MISSING' ? 'Not found on this machine.' : x.breaker.state === 'closed' ? 'Available.' : 'Breaker ' + x.breaker.state.replace('_', ' ') + ': ' + (x.breaker.last_error || '') }));
    S.accounts.forEach((a) => out.push({ id: a.id, label: 'Account ' + a.label, state: a.state === 'AVAILABLE' ? 'ok' : a.state === 'UNVERIFIED' ? 'unknown' : 'attention', detail: present('account_health', a.state).label }));
    out.push({ id: 'disk', label: 'Disk space', state: 'unknown', detail: 'No reading. A missing reading is shown as unknown, never as 0.' });
    out.push({ id: 'notify', label: 'OS notifications', state: 'ok', detail: 'Built; one per breaker trip and per approval.' });
    return out;
  }
  const counts = () => {
    const a = attention().filter((i) => i.kind !== 'knowledge').length, r = liveWork().length;
    const stopped = Object.values(S.missions).filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED').length;
    return { need: a, running: r, stopped };
  };

  build(seed0);
  const api = {
    get state() { return S; },
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
    advance, act, edgeOk, say, chat: chatApi, security, health, counts, attention, liveWork, reading, sentence, replay, triggerApproval, injectFailure,
    play() { S.playing = true; emit('sim.play', null, {}, {}); }, pause() { S.playing = false; emit('sim.pause', null, {}, {}); },
    setSpeed(x) { if (!SPEEDS.includes(x)) return false; S.speed = x; emit('sim.speed', null, { speed: x }, {}); return true; },
    reset(seed) { const sp = S.speed; build(seed == null ? seed0 : seed); S.speed = sp; subs.forEach((f) => f({ seq, at: 0, type: 'sim.reset', subject: null, payload: {} })); },
    tickReal(realMs) { if (S.playing) advance(realMs * S.speed * TIME_SCALE); },
    hash() { return hashEvents(S.events); }
  };
  return api;
}
