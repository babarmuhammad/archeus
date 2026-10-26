// S3 model: everything the inspectors and the required areas (Security, Health, Usage, Accounts, Extensions) show beyond sim.js.
// No DOM. Reads the simulation state (or an offline snapshot of it) and keeps the small state the owner changes here
// (hooks, MCP servers, agents, default model, failover, launch config, pins, digest cursor, offline).
// Everything is SIMULATED fixture data with invented names; nothing is connected to a Core.
import { present } from '../core-words.js';
import { clockLabel } from '../sim.js';
import { spineOf, SPINE_STATES, STATIONS } from '../spine-model.js';

const MIN = 60000, SEC = 1000;
export const LOW_LINE = 20; // percent left: the owner's line
export const CRIT_LINE = 5;
export const PIN_KEY = 'archeus-v2-live-pins';

export const METER_WORD = { ok: 'On track', low: 'Low', critical: 'Almost out', out: 'Limit reached', unknown: 'Unknown' };
export function meterState(used) {
  if (used == null) return { key: 'unknown', left: null, used: null };
  const left = Math.max(0, Math.round((100 - used) * 10) / 10);
  return { key: left <= 0 ? 'out' : left <= CRIT_LINE ? 'critical' : left <= LOW_LINE ? 'low' : 'ok', left, used };
}

export const ROUTE_OF = { mission: 'work', task: 'work', execution: 'work', plan: 'work', verification: 'work', review: 'work', route: 'work', knowledge: 'work', idea: 'work', project: 'work', approval: 'attention', account: 'accounts', model: 'accounts', hook: 'extensions', mcp: 'extensions', agent: 'extensions', automation: 'extensions', device: 'extensions', breaker: 'security', boundary: 'security', check: 'health' };
const PREFIX = [['mcp-', 'mcp'], ['m-', 'mission'], ['t-', 'task'], ['x-', 'execution'], ['p-', 'plan'], ['a-', 'approval'], ['v-', 'verification'], ['r-', 'review'], ['k-', 'knowledge'], ['i-', 'idea'], ['au-', 'automation'], ['acc-', 'account'], ['ag-', 'agent'], ['h-', 'hook'], ['d-', 'device'], ['prj-', 'project'], ['mdl-', 'model'], ['bk-', 'breaker'], ['chk-', 'check'], ['sec-', 'boundary'], ['rd-', 'route']];
export function kindOfId(id) { const p = PREFIX.find(([x]) => String(id).startsWith(x)); return p ? p[1] : null; }

const HARNESS_LABEL = { claude_code: 'Claude Code', codex: 'Codex', pi: 'pi' };
export const harnessLabel = (id) => HARNESS_LABEL[id] || id;

// ---------- fixtures ----------
function fresh(S) {
  return {
    hooks: [
      { id: 'h-1', event: 'PreToolUse', name: 'ask before git push', matcher: 'Bash(git push:*)', does: 'Opens an approval and stops the action. It never pushes by itself.', enabled: true, locked: false, sensitive: true, runs: 41, last: -26 * MIN, outcome: 'Asked, you approved', scope: 'All projects' },
      { id: 'h-2', event: 'PostToolUse', name: 'format changed files', matcher: 'Edit | Write', does: 'Runs the project formatter on the files just written. Simulated receipt only.', enabled: true, locked: false, sensitive: false, runs: 188, last: -3 * MIN, outcome: '2 files formatted', scope: 'Archeus' },
      { id: 'h-3', event: 'Stop', name: 'write a checkpoint', matcher: 'End of a run', does: 'Would write a short checkpoint note for a handoff. Disabled, so no checkpoint is promised.', enabled: false, locked: false, sensitive: false, runs: 7, last: -190 * MIN, outcome: 'Checkpoint written', scope: 'All projects' },
      { id: 'h-live-4', event: 'PreToolUse', name: 'ask before external send', matcher: 'Bash(curl:*) | Bash(scp:*)', does: 'Proposal: ask before anything is sent outside this machine. Needs your confirmation to switch on.', enabled: false, locked: false, sensitive: false, runs: 0, last: null, outcome: 'Never run', scope: 'All projects' },
      { id: 'h-live-5', event: 'PreToolUse', name: 'keep writes inside the workdir', matcher: 'Any tool', does: 'Denies any path outside the execution workdir. If the hook cannot answer, the action is denied.', enabled: true, locked: true, sensitive: true, runs: 2406, last: -10 * SEC, outcome: 'Allowed, inside the workdir', scope: 'Built in' }
    ],
    mcp: [
      { id: 'mcp-1', name: 'filesystem (read only)', transport: 'Local process', enabled: true, tools: [['read_file', 'read'], ['list_dir', 'read'], ['search_text', 'read']], calls: 312, last: -40 * SEC, scope: 'Archeus, Notes', connectAt: null, fixed: false, error: null, detail: 'Returns the fixture schema. No real filesystem access.' },
      { id: 'mcp-2', name: 'issue tracker', transport: 'HTTPS', enabled: false, tools: [['list_issues', 'read'], ['comment', 'write']], calls: 0, last: null, scope: 'Archeus', connectAt: null, fixed: false, error: null, detail: 'Makes no external requests while it is off.' },
      { id: 'mcp-live-3', name: 'documentation index', transport: 'Local process', enabled: false, tools: [['search_docs', 'read']], calls: 0, last: null, scope: 'Archeus', connectAt: null, fixed: false, error: null, detail: 'Proposed local search over the docs folder.' },
      { id: 'mcp-live-4', name: 'release notes', transport: 'Unknown', enabled: false, unchecked: true, tools: [], calls: 0, last: null, scope: 'Notes', connectAt: null, fixed: false, error: null, detail: 'Its capability has not been checked, so it cannot be switched on from chat.' }
    ],
    agents: [
      { id: 'ag-1', name: 'planner', role: 'Proposes plan versions. It cannot grant an approval.', tier: 'large', model: 'claude-sonnet', enabled: true, runs: 19, last: -31 * MIN },
      { id: 'ag-2', name: 'verifier', role: 'Records checks against a revision. It cannot accept for you.', tier: 'small', model: 'claude-haiku', enabled: true, runs: 23, last: -2 * MIN },
      { id: 'ag-3', name: 'reviewer', role: 'Reviews the evidence. Its verdict is not the same as the process exit.', tier: 'large', model: 'claude-sonnet', enabled: true, runs: 11, last: -70 * MIN },
      { id: 'ag-4', name: 'doc writer', role: 'Drafts documentation. Publishing stays a separate effect.', tier: 'small', model: 'claude-haiku', enabled: true, runs: 6, last: -118 * MIN }
    ],
    defaultModel: 'claude-sonnet',
    failover: { order: S.accounts.slice().sort((a, b) => a.priority - b.priority).map((a) => a.id), handoff: true, pauseOn: true, pauseAt: LOW_LINE, askHarness: true },
    launch: {
      archeus: { harness: 'claude_code', model: 'claude-sonnet', account: 'auto', mode: 'ask', parallel: 2 },
      notes: { harness: 'claude_code', model: 'claude-haiku', account: 'auto', mode: 'plan', parallel: 1 },
      ideas: { harness: 'codex', model: 'codex-main', account: 'acc-codex', mode: 'ask', parallel: 1 }
    },
    pins: readPins(), cursor: -45 * MIN, offline: null, hist: backfill(S), lastSample: 0,
    log: [
      { at: -26 * MIN, kind: 'hook', text: 'Hook "ask before git push" asked about a push; you approved it.' },
      { at: -63 * MIN, kind: 'usage', text: 'Claude Code, personal passed 70% of its week.' },
      { at: -140 * MIN, kind: 'owner', text: 'You set the failover line to 20% left.' }
    ]
  };
}
function readPins() { try { return JSON.parse(localStorage.getItem(PIN_KEY)) || []; } catch (e) { return []; } }
function backfill(S) {
  const h = {};
  S.accounts.forEach((a) => {
    const v = S.usage[a.id] && S.usage[a.id].window5h;
    if (v == null) return;
    h[a.id] = Array.from({ length: 30 }, (_, i) => ({ t: -(29 - i) * 2 * MIN, s: Math.max(0, Math.round((v - (29 - i) * (v > 60 ? 0.9 : 0.55)) * 10) / 10) }));
  });
  return h;
}

// ---------- the object attached to a simulation ----------
export function areasOf(sim) { if (!sim.areas) sim.areas = createAreas(sim); return sim.areas; }

function createAreas(sim) {
  let X = fresh(sim.state);
  const live = () => sim.state;
  const S = () => (X.offline ? X.offline.snap : sim.state);
  const log = (kind, text, at) => { X.log.unshift({ at: at == null ? sim.state.clock : at, kind, text }); if (X.log.length > 40) X.log.length = 40; };
  const by = (list, id) => list.find((x) => x.id === id);
  const bump = (x, at) => { x.runs += 1; x.last = at; };

  sim.subscribe((e) => {
    if (e.type === 'sim.reset') { X = fresh(sim.state); return; }
    if (e.type === 'clock') {
      if (e.at - X.lastSample >= 2 * MIN) { X.lastSample = e.at; Object.keys(X.hist).forEach((id) => { const u = live().usage[id]; if (u && u.window5h != null) { X.hist[id].push({ t: e.at, s: u.window5h }); if (X.hist[id].length > 90) X.hist[id].shift(); } }); }
      return;
    }
    if (e.type === 'approval.requested' && e.payload && e.payload.kind === 'action') { const h = by(X.hooks, 'h-1'); if (h.enabled) { bump(h, e.at); h.outcome = 'Asked, waiting for you'; log('hook', 'Hook "ask before git push" stopped an action and asked you.', e.at); } }
    else if (e.type === 'execution.state_changed') {
      const to = e.payload.to;
      if (to === 'ENDED_OK') { const h = by(X.hooks, 'h-2'); if (h.enabled) { bump(h, e.at); h.outcome = '2 files formatted'; } }
      if (to === 'STARTING') { const h = by(X.hooks, 'h-live-5'); bump(h, e.at); }
    } else if (e.type === 'execution.progress') { const m = by(X.mcp, 'mcp-1'); if (m.enabled) { m.calls += 1; m.last = e.at; } }
    else if (e.type === 'mission.state_changed' && e.payload.to === 'PLANNING') bump(by(X.agents, 'ag-1'), e.at);
    else if (e.type === 'verification.state_changed' && e.payload.to === 'RUNNING') bump(by(X.agents, 'ag-2'), e.at);
    else if (e.type === 'review.requested') bump(by(X.agents, 'ag-3'), e.at);
    else if (e.type === 'harness.breaker_opened') log('breaker', 'The spawn breaker for ' + harnessLabel(e.subject.id) + ' opened after 3 failed starts in 10 minutes.', e.at);
    else if (e.type === 'harness.breaker_half_open') log('breaker', 'The spawn breaker for ' + harnessLabel(e.subject.id) + ' is half open: one trial start is allowed.', e.at);
    else if (e.type === 'harness.breaker_closed') log('breaker', 'The spawn breaker for ' + harnessLabel(e.subject.id) + ' closed again.', e.at);
    else if (e.type === 'account_health.state_changed') log('usage', accountLabel(live(), e.subject.id) + ' is now ' + present('account_health', e.payload.to).label + '.', e.at);
    else if (e.type === 'usage.observed' && e.payload && e.payload.note) log('usage', accountLabel(live(), e.subject.id) + ': ' + e.payload.note + '.', e.at);
  });

  const A = {
    get X() { return X; },
    S, isOffline: () => !!X.offline, offlineAt: () => (X.offline ? X.offline.at : null),
    goOffline() { if (X.offline) return { ok: false, reason: 'Already offline' }; X.offline = { at: sim.state.clock, snap: structuredClone(sim.state) }; log('owner', 'The client lost Core. It shows what it kept.'); return { ok: true }; },
    reconnect() { if (!X.offline) return { ok: false, reason: 'Already connected' }; X.offline = null; log('owner', 'The client reached Core again.'); return { ok: true }; },

    // pins and digest
    pinned: (id) => X.pins.includes(id),
    togglePin(id) { const on = !X.pins.includes(id); X.pins = on ? [...X.pins, id] : X.pins.filter((x) => x !== id); try { localStorage.setItem(PIN_KEY, JSON.stringify(X.pins)); } catch (e) { /* storage blocked: pins last until reload */ } return { ok: true, on }; },
    cursor: () => X.cursor,
    acknowledge() { X.cursor = sim.state.clock; return { ok: true }; },

    // hooks, MCP servers, agents
    hooks: () => X.hooks,
    hookAllows: (id) => by(X.hooks, id).enabled,
    toggleHook(id) {
      const h = by(X.hooks, id); if (!h) return { ok: false, reason: 'No such hook' };
      if (h.locked) return { ok: false, reason: 'This hook is built in and fail closed: it cannot be switched off.' };
      h.enabled = !h.enabled; log('owner', 'You ' + (h.enabled ? 'enabled' : 'disabled') + ' the hook "' + h.name + '".'); return { ok: true, on: h.enabled };
    },
    mcp: () => X.mcp,
    mcpStatus: (x, clock) => mcpStatus(x, clock == null ? sim.state.clock : clock),
    toggleMcp(id) {
      const x = by(X.mcp, id); if (!x) return { ok: false, reason: 'No such server' };
      x.enabled = !x.enabled; x.connectAt = x.enabled ? sim.state.clock + 8 * SEC : null; log('owner', 'You ' + (x.enabled ? 'enabled' : 'disabled') + ' the MCP server "' + x.name + '".'); return { ok: true, on: x.enabled };
    },
    agents: () => X.agents,
    toggleAgent(id) { const a = by(X.agents, id); if (!a) return { ok: false, reason: 'No such agent' }; a.enabled = !a.enabled; log('owner', 'You ' + (a.enabled ? 'enabled' : 'disabled') + ' the agent "' + a.name + '".'); return { ok: true, on: a.enabled }; },
    agentStatus: (a) => agentStatus(S(), a),

    // accounts, models, failover, launch
    defaultModel: () => X.defaultModel,
    setDefaultModel(id) { if (!by(live().models, id)) return { ok: false, reason: 'No such model' }; X.defaultModel = id; log('owner', 'You made ' + by(live().models, id).label + ' the default model.'); return { ok: true }; },
    failover: () => X.failover,
    setFailover(key, v) { if (!(key in X.failover) || key === 'order') return { ok: false, reason: 'No such rule' }; X.failover[key] = v; log('owner', 'You changed the failover rule "' + key + '".'); return { ok: true }; },
    moveAccount(id, dir) {
      const o = X.failover.order, i = o.indexOf(id), j = i + dir;
      if (i < 0 || j < 0 || j >= o.length) return { ok: false, reason: 'Already at the end' };
      [o[i], o[j]] = [o[j], o[i]]; o.forEach((a, k) => { by(live().accounts, a).priority = k + 1; }); log('owner', 'You changed the account order.'); return { ok: true };
    },
    launch: (pid) => X.launch[pid],
    setLaunch(pid, key, v) {
      const c = X.launch[pid]; if (!c) return { ok: false, reason: 'No such project' };
      c[key] = key === 'parallel' ? Number(v) : v;
      if (key === 'harness') { c.model = live().models.find((m) => m.harness === v).id; c.account = 'auto'; }
      log('owner', 'You changed the launch setting "' + key + '" of ' + by(live().projects, pid).name + '.'); return { ok: true };
    },
    preview: (pid) => launchPreview(S(), X, pid),

    // breakers
    breaker: (id) => by(live().harnesses, id).breaker,
    tripBreaker(id) { const h = by(live().harnesses, id); if (!h || h.state === 'MISSING') return { ok: false, reason: 'This harness is not installed' }; if (h.breaker.state !== 'closed') return { ok: false, reason: 'The breaker is already ' + h.breaker.state.replace('_', ' ') }; log('owner', 'You tripped the breaker for ' + h.label + ' (simulated).'); return sim.injectFailure('spawn', id); },
    resetBreaker(id) {
      const h = by(live().harnesses, id), b = h && h.breaker; if (!b) return { ok: false, reason: 'No such harness' };
      if (b.state === 'closed') return { ok: false, reason: 'The breaker is already closed' };
      b.state = 'closed'; b.failures = []; b.until = 0; b.last_error = null; log('owner', 'You reset the breaker for ' + h.label + ' (simulated step-up).'); return { ok: true };
    },

    // ideas
    advanceIdea(id) { const i = live().ideas.find((x) => x.id === id), k = IDEA_PATH.indexOf(i && i.state); if (!i || k < 0 || k >= IDEA_PATH.length - 1) return { ok: false, reason: 'This idea is not on the path' }; i.state = IDEA_PATH[k + 1]; log('owner', 'You moved "' + i.title + '" to ' + present('idea', i.state).label + '.'); return { ok: true }; },
    setIdea(id, state) { const i = live().ideas.find((x) => x.id === id); if (!i) return { ok: false, reason: 'No such idea' }; i.state = state; log('owner', 'You set "' + i.title + '" to ' + present('idea', state).label + '.'); return { ok: true }; },

    log: () => X.log,
    hist: (id) => X.hist[id] || [],

    // derived reads
    usage: () => usageRows(S(), X),
    security: () => security(S(), X, A),
    health: () => health(S(), X, A),
    privileges: () => privileges(S(), X),
    digest: (since) => digest(S(), since)
  };
  return A;
}

// ---------- usage ----------
export function accountLabel(S, id) { const a = S.accounts.find((x) => x.id === id); return a ? a.label : id; }
export function usageRows(S, X) {
  return S.accounts.slice().sort((a, b) => a.priority - b.priority).map((a, i) => {
    const u = S.usage[a.id] || {};
    const session = meterState(u.window5h), week = meterState(u.week);
    const worst = ['out', 'critical', 'low', 'ok', 'unknown'].find((k) => session.key === k || week.key === k);
    return { id: a.id, label: a.label, harness: a.harness, state: a.state, priority: a.priority, role: i === 0 ? 'First choice' : a.state === 'UNVERIFIED' ? 'Not verified' : 'Failover', session, week, worst, resets: u.resets, hist: (X.hist[a.id] || []).slice(-30) };
  });
}

// ---------- extensions ----------
export function mcpStatus(x, clock) {
  if (x.unchecked) return 'UNKNOWN';
  if (!x.enabled) return 'DISABLED';
  if (x.connectAt != null && clock < x.connectAt) return 'CONNECTING';
  return 'CONNECTED';
}
export function agentStatus(S, a) {
  if (!a.enabled) return { key: 'off', text: 'Off' };
  const ms = Object.values(S.missions);
  if (a.id === 'ag-1') { const m = ms.find((x) => ['UNDERSTANDING', 'CONTEXT_GATHERING', 'REASONING', 'PLANNING', 'REPLANNING'].includes(x.state)); if (m) return { key: 'working', text: 'Working on ' + m.title }; }
  if (a.id === 'ag-2') { const v = Object.values(S.verifications).find((x) => x.state === 'RUNNING'); if (v) return { key: 'working', text: 'Running checks for ' + S.missions[v.mission].title }; }
  if (a.id === 'ag-3') { const r = Object.values(S.reviews).find((x) => x.state === 'PENDING' || x.state === 'IN_REVIEW'); if (r) return { key: 'ready', text: 'Review of ' + S.missions[r.mission].title + ' waits for you' }; }
  return { key: 'idle', text: 'Idle' };
}
export const IDEA_PATH = ['CAPTURED', 'UNDERSTOOD', 'EXPLORED', 'VALIDATED', 'CONCEPT', 'PLANNED', 'SCHEDULED', 'IMPLEMENTING', 'COMPLETED', 'LEARNED'];

// ---------- launch preview (which account a new mission would take) ----------
export function launchPreview(S, X, pid) {
  const c = X.launch[pid], har = S.harnesses.find((h) => h.id === c.harness), model = S.models.find((m) => m.id === c.model);
  const out = { harness: c.harness, model: model ? model.label : c.model, account: null, tone: 'ok', note: '' };
  if (!har || har.state === 'MISSING') return Object.assign(out, { tone: 'blocked', note: harnessLabel(c.harness) + ' is not installed, so a mission here cannot start.' });
  if (har.breaker.state === 'open') return Object.assign(out, { tone: 'attention', note: 'The ' + har.label + ' spawn breaker is open, so a mission here waits and says "cannot start".' });
  const pool = X.failover.order.map((id) => S.accounts.find((a) => a.id === id)).filter((a) => a.harness === c.harness);
  let pick = c.account === 'auto' ? pool.find((a) => ['AVAILABLE', 'CONSTRAINED', 'UNVERIFIED'].includes(a.state)) : pool.find((a) => a.id === c.account);
  if (!pick) return Object.assign(out, { tone: 'blocked', note: 'No account of ' + har.label + ' can take new work right now.' });
  out.account = pick.label;
  const wk = meterState((S.usage[pick.id] || {}).week);
  if (X.failover.pauseOn && wk.left != null && wk.left <= X.failover.pauseAt) return Object.assign(out, { tone: 'attention', note: pick.label + ' has ' + wk.left + '% of its week left, at or under your ' + X.failover.pauseAt + '% line, so new work waits.' });
  if (pick.state === 'UNVERIFIED') return Object.assign(out, { tone: 'paused', note: pick.label + ' is not verified yet: the first start checks it.' });
  out.note = c.account === 'auto' && pick.id !== X.failover.order[0] ? 'Failover: the first account is not available, so ' + pick.label + ' takes it.' : pick.label + ' takes the next mission.';
  return out;
}

// ---------- security ----------
export const BOUNDARIES = [
  { id: 'sec-b1', n: 'B1', name: 'Execution', what: 'The identity a run starts under, its job object and its own files.', policy: 'Built', physical: 'Designed', note: 'The fail-closed hook, the workdir and the stripped environment are built. The isolated identity (AppContainer, job object, ACLs) is designed and gated off: production dispatch is a constant false.' },
  { id: 'sec-b2', n: 'B2', name: 'Verifier', what: 'The confined identity that runs verification commands.', policy: 'Partly', physical: 'Designed', note: 'Verification runs with the application policy only. A confined verifier identity is designed, not built.' },
  { id: 'sec-b3', n: 'B3', name: 'Broker', what: 'Provider access through Core, never from the run itself.', policy: 'Built, switch off', physical: 'Designed', note: 'The named pipe and bridge exist and are tested with fixtures. No native broker runs, and subscription logins stay out of scope.' },
  { id: 'sec-b4', n: 'B4', name: 'Core', what: 'Split-authority mailbox and the effect boundary.', policy: 'Built', physical: 'Designed', note: 'Core decides what has an effect; a run can only ask. The mailbox ACLs that make this physical are designed.' },
  { id: 'sec-b5', n: 'B5', name: 'User', what: 'Your profile, home and credential stores (finding G1, critical).', policy: 'Built', physical: 'Open', note: 'Policy denies a run these stores, but a started process still runs as your user and the OS does not stop it. This is the critical hole that P20 must close.' },
  { id: 'sec-b6', n: 'B6', name: 'Peer', what: 'Which process connects, and other executions.', policy: 'Built', physical: 'Designed', note: 'The origin gate is built on the HTTP side with its switch off; the native side is a fail-closed stub.' },
  { id: 'sec-b7', n: 'B7', name: 'Proxy', what: 'Forwarding hops and the remote tunnel.', policy: 'Designed', physical: 'Designed', note: 'A hop rule is specified: a proxy may not widen what a peer can reach. Nothing is built.' },
  { id: 'sec-b8', n: 'B8', name: 'Deputy', what: 'Archeus code that runs as you.', policy: 'Built', physical: 'Designed', note: 'The deputy rule keeps Archeus code from acting on a run\'s behalf without a recorded decision.' }
];
export const ISOLATED_BY_POLICY = [
  'Credentials: Archeus never reads, stores, copies, injects or relays subscription tokens.',
  'Environment: prompts off, askpass empty, no ssh agent, no credential helper.',
  'Writes outside the workdir are denied by a fail-closed hook.',
  'Risky actions ask you first: a push, a package install, a delete.',
  'Approvals are scoped: deciding needs the approve scope, and chat only opens a card.'
];
export const NOT_ISOLATED = [
  'A started CLI runs as your user. It can reach your profile, home and credential stores, because the OS does not stop it (finding G1, critical).',
  'Network access is not confined. Provider access is not yet brokered: the broker is built and switched off.',
  'Another execution is not walled off at the OS level.',
  'No process has ever been started under isolation by production code. The dispatch switch is off.',
  'The verifier is not confined.'
];

export function security(S, X, A) {
  const hs = S.harnesses;
  const bk = hs.filter((h) => h.state !== 'MISSING');
  const open = bk.filter((h) => h.breaker.state !== 'closed').length;
  const switches = [
    { id: 'sw-dispatch', label: 'Production dispatch of isolated runs', state: 'off', word: 'Off', note: 'A constant false in V1. No isolated process has been started by production code.' },
    { id: 'sw-broker', label: 'Provider broker', state: 'off', word: 'Built, switch off', note: 'Named pipe and bridge exist and pass fixture tests. Nothing runs them.' },
    { id: 'sw-origin', label: 'Core API origin gate', state: 'off', word: 'HTTP side built, switch off', note: 'The native side is a fail-closed stub.' },
    { id: 'sw-estop', label: 'Emergency stop and re-arm', state: S.estop.engaged ? 'attention' : 'ok', word: S.estop.engaged ? 'Engaged: nothing new starts' : 'Built', note: S.estop.engaged ? 'Missions stay Blocked "Emergency stop" and no new dispatch starts until you re-arm (a step-up).' : 'Stops every execution and blocks new dispatch until re-armed. Re-arming needs a step-up.' },
    { id: 'sw-notify', label: 'OS notification per approval and per breaker trip', state: 'ok', word: 'Built', note: 'One notification each, with no secret in the text.' }
  ];
  return { switches, open, breakers: bk.length, rows: { acceptance: { closed: 0, total: 15 }, additions: { closed: 0, total: 6 } }, boundaries: BOUNDARIES, policyList: ISOLATED_BY_POLICY, notList: NOT_ISOLATED };
}

export function privileges(S, X) {
  const push = X.hooks.find((h) => h.id === 'h-1');
  return [
    { id: 'p1', label: 'Read files in its workdir', state: 'allowed', by: 'Policy', note: 'Inside the execution workdir only.' },
    { id: 'p2', label: 'Write files in its workdir', state: 'allowed', by: 'Hook: keep writes inside the workdir', note: 'Anything outside is denied, and a hook that cannot answer denies.', link: 'h-live-5' },
    { id: 'p3', label: 'Run the project tests and commands', state: 'allowed', by: 'Policy', note: 'With the stripped environment.' },
    { id: 'p4', label: 'Commit locally', state: 'allowed', by: 'Policy', note: 'A push is a separate action.' },
    { id: 'p5', label: 'git push', state: push.enabled ? 'asks' : 'unguarded', by: 'Hook: ask before git push', note: push.enabled ? 'Stops and asks you with the exact command.' : 'The hook is off, so a push goes ahead without asking you.', link: 'h-1' },
    { id: 'p6', label: 'Install a package', state: 'asks', by: 'Policy', note: 'Asks with the package name.' },
    { id: 'p7', label: 'Start another execution', state: 'denied', by: 'Policy', note: 'Only Core dispatches.' },
    { id: 'p8', label: 'Read your credential stores', state: 'denied-policy', by: 'Policy only', note: 'Denied by policy, not by the OS: physical reach is not built (finding G1).', link: 'sec-b5' },
    { id: 'p9', label: 'Open its own network connections', state: 'unconfined', by: 'Not confined', note: 'Provider access is not brokered yet and the network is not walled off.', link: 'sec-b3' }
  ];
}

// ---------- health: six checks with causes and fixes ----------
export function health(S, X, A) {
  const clock = S.clock, order = { attention: 3, unknown: 2, ok: 1 };
  const worst = (xs) => xs.reduce((a, b) => (order[b] > order[a] ? b : a), 'ok');
  const checks = [];
  const suspended = S.automations.filter((a) => a.state === 'SUSPENDED');

  checks.push({ id: 'chk-core', label: 'Core process', state: 'ok', summary: 'Always up in this simulation. No real Core is connected.', readings: [['Process', 'Up (simulated)'], ['Plan, policy, verify and metrics workers', 'Running'], ['Automation worker', suspended.length ? 'Running, ' + suspended.length + ' automation held by the loop guard' : 'Running']], cause: null, fix: null });

  checks.push({ id: 'chk-log', label: 'Event log', state: 'ok', summary: 'Readable. Events are kept for 180 days.', readings: [['Kept for', '180 days'], ['Events in this session', String(S.events.length)], ['Oldest kept', S.events.length ? clockLabel(S.events[0].at) : 'none'], ['Older than that', 'Unknown, never "nothing happened"']], cause: null, fix: null });

  const hs = S.harnesses.filter((h) => h.state !== 'MISSING'), tripped = hs.filter((h) => h.breaker.state !== 'closed');
  checks.push({ id: 'chk-harness', label: 'Harnesses and spawn breakers', state: tripped.length ? 'attention' : 'ok', summary: tripped.length ? tripped.map((h) => h.label).join(', ') + ' cannot start new work.' : hs.length + ' harnesses start normally.', readings: S.harnesses.map((h) => [h.label, h.state === 'MISSING' ? 'Not installed (optional)' : h.breaker.state === 'closed' ? 'Closed, starts normally' : 'Breaker ' + h.breaker.state.replace('_', ' ')]), cause: tripped.length ? 'AVAILABLE only says the tool is installed. Three starts failed within ten minutes (' + (tripped[0].breaker.last_error || 'could not start the process') + '), so the breaker stops new starts instead of retrying in a loop.' : null, fix: tripped.length ? ['Wait. The breaker allows one trial start after 5 minutes and closes if it works.', 'Or reset it on Security after you check that ' + tripped[0].label + ' starts from a terminal.'] : null, action: tripped.length ? { label: 'Open the breaker', href: '#/security/bk-' + tripped[0].id } : null });

  const rows = usageRows(S, X), low = rows.filter((r) => ['low', 'critical', 'out'].includes(r.worst)), unv = S.accounts.filter((a) => a.state === 'UNVERIFIED');
  const accState = low.length || S.accounts.some((a) => ['LIMITED', 'DEGRADED', 'OPEN', 'UNAUTHENTICATED'].includes(a.state)) ? 'attention' : unv.length ? 'unknown' : 'ok';
  const lw = low[0];
  checks.push({ id: 'chk-accounts', label: 'Accounts and usage', state: accState, summary: low.length ? low.length + (low.length === 1 ? ' account is' : ' accounts are') + ' at or under your ' + LOW_LINE + '% line.' : unv.length ? 'One account is not verified: ' + unv[0].label + '.' : 'Every account has room.', readings: rows.map((r) => [r.label, r.session.left == null ? 'Unknown' : r.session.left + '% of the session, ' + (r.week.left == null ? 'week unknown' : r.week.left + '% of the week')]), cause: low.length ? lw.label + ' has ' + (lw.week.key !== 'ok' && lw.week.left != null ? lw.week.left + '% of its week' : lw.session.left + '% of its 5 hour window') + ' left, at or under the ' + LOW_LINE + '% line. New work prefers another account. These are account percentages, not the cost or tokens of one session.' : unv.length ? 'The account is UNVERIFIED and no live authentication probe has run. An unknown reading stays unknown; it is never shown as 0%.' : null, fix: low.length ? ['Let the window reset' + (lw.resets ? ' (' + lw.resets.replace('5 h window ', '') + ')' : '') + '.', 'Or put another account first in the failover order.', 'Or change the line under Failover rules.'] : unv.length ? ['Start one small mission on it so Core can read its usage.'] : null, action: { label: 'Open Usage', href: '#/usage' } });

  checks.push({ id: 'chk-disk', label: 'Disk space', state: 'unknown', summary: 'No reading yet.', readings: [['Free space', 'Unknown'], ['Last reading', 'None']], cause: 'Core does not read the disk yet. A missing reading is shown as unknown, never as 0 bytes.', fix: ['Nothing to do. The reading shows up when Core records it.'], action: null });

  const sent = S.events.filter((e) => e.type === 'approval.requested' || e.type === 'harness.breaker_opened').length;
  checks.push({ id: 'chk-notify', label: 'OS notifications', state: 'ok', summary: 'One simulated notification per approval request and per breaker trip.', readings: [['Sent in this session', String(sent)], ['Content', 'No secret in the text']], cause: null, fix: null });

  const n = (s) => checks.filter((c) => c.state === s).length;
  return { checks, counts: { ok: n('ok'), attention: n('attention'), unknown: n('unknown') }, overall: worst(checks.map((c) => c.state)) };
}

// ---------- digest ----------
export function digest(S, since) {
  const items = [], ev = S.events.filter((e) => e.at > since);
  const word = (st) => present('mission', st).label;
  const groups = new Map();
  ev.filter((e) => e.type === 'mission.state_changed').forEach((e) => {
    const g = groups.get(e.subject.id) || { id: e.subject.id, steps: [], at: 0 };
    g.steps.push(e.payload.to); g.at = e.at; groups.set(e.subject.id, g);
  });
  groups.forEach((g) => {
    const m = S.missions[g.id], last = g.steps[g.steps.length - 1], shown = g.steps.filter((s, i) => s !== g.steps[i - 1]).slice(-3);
    items.push({ kind: 'mission', id: g.id, at: g.at, tone: present('mission', last).cls, text: (m ? m.title : g.id) + ': ' + (g.steps.length > 3 ? '... ' : '') + shown.map(word).join(', then '), href: '#/work/' + g.id });
  });
  ev.filter((e) => e.type === 'approval.requested').forEach((e) => { const a = S.approvals[e.subject.id], m = a && S.missions[a.mission]; if (a) items.push({ kind: 'decision', id: a.id, at: e.at, tone: 'needs_you', text: 'A decision arrived: ' + a.presented.what, href: '#/attention/' + a.id, state: a.state }); });
  ev.filter((e) => e.type === 'review.requested').forEach((e) => { const m = S.missions[e.mission]; if (m) items.push({ kind: 'review', id: m.id, at: e.at, tone: 'needs_you', text: 'A result is ready to review: ' + m.title, href: '#/work/' + m.id }); });
  ev.filter((e) => e.type === 'execution.state_changed' && (e.payload.trigger === 'heartbeat_missing' || e.payload.trigger === 'adopted')).forEach((e) => items.push({ kind: 'execution', id: e.subject.id, at: e.at, tone: e.payload.trigger === 'adopted' ? 'active' : 'paused', text: e.payload.trigger === 'adopted' ? 'An execution went quiet and Core adopted it again.' : 'An execution went quiet; Core is reconciling.', href: '#/work/' + e.subject.id }));
  ev.filter((e) => e.type === 'knowledge_item.created').forEach((e) => { const k = S.knowledge.find((x) => x.id === e.subject.id); if (k) items.push({ kind: 'knowledge', id: k.id, at: e.at, tone: 'needs_you', text: 'Archeus suggests remembering: ' + k.text, href: '#/work/' + k.id }); });
  ev.filter((e) => e.type === 'harness.breaker_opened').forEach((e) => items.push({ kind: 'breaker', id: 'bk-' + e.subject.id, at: e.at, tone: 'blocked', text: 'The spawn breaker for ' + harnessLabel(e.subject.id) + ' opened.', href: '#/security/bk-' + e.subject.id }));
  ev.filter((e) => e.type === 'usage.observed' && e.payload && e.payload.note).forEach((e) => items.push({ kind: 'usage', id: e.subject.id, at: e.at, tone: 'needs_you', text: accountLabel(S, e.subject.id) + ': ' + e.payload.note + '.', href: '#/usage' }));
  items.sort((a, b) => b.at - a.at);
  const c = (k) => items.filter((i) => i.kind === k).length;
  return { items, counts: { missions: c('mission'), decisions: c('decision'), reviews: c('review'), other: items.length - c('mission') - c('decision') - c('review') } };
}

// ---------- inspectors: station times, why, relations, route, policy, output ----------
export function stationTimes(S, m) {
  const mine = S.events.filter((e) => e.mission === m.id && e.type === 'mission.state_changed');
  if (S.pruned && !S.events.some((e) => e.mission === m.id && e.type === 'mission.created')) return null;
  const at = Array(6).fill(null);
  mine.forEach((e) => { const to = e.payload.to; if (!SPINE_STATES.includes(to)) return; const st = spineOf(to, e.payload.from).station; if (st && at[st - 1] == null) at[st - 1] = e.at; });
  return at;
}

const WHY = {
  start: ['Began to understand it', (m) => 'The mission was created from ' + m.origin + ', so Core starts by reading what was asked.'],
  understood: ['Understood the request', () => 'The request was clear enough to go on without asking you.'],
  needs_clarification: ['Asked you a question', (m) => (m.reason || 'The request left a choice open.') + ' Core does not guess an answer.'],
  context_ready: ['Gathered the context', () => 'Confirmed project knowledge and the recent changes were collected into the context package.'],
  reasoned: ['Drafted a plan', () => 'Reasoning finished with a plan of tasks.'],
  plan_auto_approved: ['Plan approved by policy', () => 'The plan is low risk: it touches only files in the workdir and runs the project checks, so policy approved it without asking you.'],
  plan_needs_approval: ['Sent the plan to you', () => 'Policy needs a person on this plan: it has more than two tasks, or it changes behaviour other work relies on.'],
  approve: ['Plan approved', () => 'The decision was made on the card.'],
  reject: ['Plan rejected', () => 'A rejected plan cancels the mission.'],
  request_changes: ['Plan sent back', () => 'Changes were requested, so Core plans again.'],
  dispatch: ['Started the executions', () => 'The plan was approved and no spawn breaker was open, so Core dispatched the tasks.'],
  all_tasks_done: ['Moved to verification', () => 'Every task finished its run, so the checks start on the recorded base revision.'],
  verified: ['Verified', () => 'Every check passed. A person still has to accept the result.'],
  verification_failed: ['Replanning after a failed check', (m) => (m.reason || 'A check did not pass') + '. Failing work is replanned, not hidden.'],
  accepted: ['Accepted', () => 'You reviewed the verified result and accepted it.'],
  changes_requested: ['Changes requested', () => 'The review asked for changes, so Core plans again.'],
  unrecoverable: ['Failed', (m) => (m.reason || 'The work could not continue') + '.'],
  block: ['Blocked', (m) => (m.reason || 'Something needs a person') + '.'],
  pause: ['Paused', () => 'The runs stopped at a safe boundary; nothing is lost.'],
  resume: ['Resumed', () => 'The paused runs start again from their last boundary.'],
  unblock: ['Unblocked', () => 'The question was answered, so the mission goes on from where it was held.'],
  replan: ['Replanning', () => 'A failed mission can be planned again within the replan budget.'],
  replan_budget_exhausted: ['Blocked: replan budget used', () => 'The mission was replanned three times; a person has to decide what to do.'],
  task_failed_retryable: ['Replanning after an error', () => 'An execution ended with an error. A retry is allowed inside the replan budget.'],
  cancel: ['Cancelled', () => 'Cancelling ends the mission and stops its runs.'],
  redispatch: ['Started again', () => 'Core started the held tasks again.'],
  heartbeat_missing: ['An execution went quiet', () => 'No output heartbeat for two minutes. Core reconciles instead of guessing that it died.'],
  adopted: ['Adopted the execution again', () => 'The process was found again, so Core adopted it instead of starting a second one.']
};
export function whyOf(S, m) {
  const rows = [];
  S.events.filter((e) => e.mission === m.id).forEach((e) => {
    const p = e.payload || {}, w = WHY[p.trigger];
    if (e.type === 'mission.state_changed' || e.type === 'execution.state_changed') {
      if (!w) return;
      if (e.type === 'execution.state_changed' && !['heartbeat_missing', 'adopted'].includes(p.trigger)) return;
      rows.push({ at: e.at, time: clockLabel(e.at), title: w[0], because: w[1](m, e), by: e.actor === 'device' ? 'You' : 'Core', trigger: p.trigger, subject: e.subject });
    } else if (e.type === 'approval.requested') {
      const a = S.approvals[e.subject.id];
      if (a) rows.push({ at: e.at, time: clockLabel(e.at), title: 'Asked you to decide', because: a.presented.why, by: 'Core', trigger: 'approval', subject: e.subject, link: a.id });
    } else if (e.type === 'execution.intent') {
      const x = S.executions[e.subject.id], t = x && S.tasks[x.task];
      if (x && t) { const r = routeOf(S, t); rows.push({ at: e.at, time: clockLabel(e.at), title: 'Routed "' + t.title + '" to ' + r.chosen.harnessLabel + ' with ' + r.chosen.modelLabel, because: r.rule, by: 'Core', trigger: 'route', subject: { kind: 'task', id: t.id }, link: 'rd-' + t.id }); }
    }
  });
  return rows.sort((a, b) => b.at - a.at);
}

export function routeOf(S, t) {
  const m = S.missions[t.mission], x = t.execution ? S.executions[t.execution] : null;
  const acct = S.accounts.find((a) => a.id === (x ? x.account : m.account)), model = S.models.find((md) => md.id === (x ? x.model : m.model));
  const project = S.projects.find((p) => p.id === m.project);
  const considered = S.accounts.slice().sort((a, b) => a.priority - b.priority).map((a) => {
    const wk = meterState((S.usage[a.id] || {}).week);
    let result, why;
    if (a.id === acct.id) { result = 'Chosen'; why = 'First eligible by priority; its state is ' + present('account_health', a.state).label.toLowerCase() + '.'; }
    else if (a.harness !== acct.harness) { result = 'Not eligible'; why = 'This task class prefers ' + harnessLabel(acct.harness) + ', and the account is ' + present('account_health', a.state).label.toLowerCase() + '.'; }
    else { result = 'Passed over'; why = a.priority > acct.priority ? 'Lower priority, and ' + acct.label + ' was available.' : 'Skipped: ' + (wk.left != null && wk.left <= LOW_LINE ? 'only ' + wk.left + '% of its week left.' : 'not available.'); }
    return { id: a.id, label: a.label, result, why };
  });
  return { chosen: { harness: acct.harness, harnessLabel: harnessLabel(acct.harness), model: model.id, modelLabel: model.label, account: acct.id, accountLabel: acct.label }, rule: 'Rule: the default model for ' + project.name + ' is ' + model.label + '; accounts are tried in failover order; there is never an unisolated fallback.', considered, at: x ? x.started_at : m.updated_at, task: t.id };
}

export function policyOf(S, a) {
  const m = S.missions[a.mission];
  if (a.kind === 'plan') return { outcome: 'Needs a person', checks: [['Plan policy', 'More than two tasks, so auto-approval does not apply', 'asks'], ['Scope', 'Only the branch ' + m.branch + ' is touched', 'ok'], ['Budget', (m.replans || 0) + ' of 3 replans used', 'ok'], ['External effects', 'None in the plan', 'ok']] };
  const what = a.presented.what;
  const push = /git push/.test(what), install = /install/.test(what);
  return { outcome: 'Asks you', checks: [[push ? 'Hook: ask before git push' : install ? 'Policy: package installs ask' : 'Policy: destructive commands ask', push ? 'Bash(git push:*) matches' : install ? 'A new dependency changes what runs' : 'A delete cannot be undone', 'asks'], ['Hook: keep writes inside the workdir', 'The path is inside the workdir', 'ok'], ['Approve scope', 'Deciding needs the approve scope and a step-up', 'ok']] };
}

const OUT = ['Read the task and the project notes', 'Opened the files for "{t}"', 'Ran the checks: 3 failing', 'Found the cause in two helpers', 'Edited the first helper', 'Re-ran the checks: 1 failing', 'Edited the second helper', 'Wrote a test for the edge case', 'Re-ran the checks: all passing', 'Summarised the change for verification', 'Checked the diff against the plan', 'Wrote the commit message'];
export function execOutput(S, x) {
  const t = S.tasks[x.task], m = S.missions[x.mission];
  const ended = x.state.startsWith('ENDED'), n = Math.min(OUT.length, 3 + Math.floor((x.outputs + 4) / 1.5) + (ended ? 6 : 0));
  const lines = Array.from({ length: n }, (_, i) => ({ at: x.last_output_at - (n - 1 - i) * 45 * SEC, text: OUT[i].replace('{t}', m.title) }));
  if (x.state === 'ENDED_OK') lines.push({ at: x.last_output_at, text: 'Exited with code 0', end: true });
  if (x.state === 'ENDED_ERROR') lines.push({ at: x.last_output_at, text: 'Exited with an error: ' + (x.reason || 'the run did not finish'), end: true });
  if (x.state === 'LOST') lines.push({ at: x.last_output_at, text: 'No output heartbeat; Core is reconciling', end: true });
  return { lines: lines.slice(-12), total: lines.length, task: t };
}
export function checkpoints(S, x) {
  const end = x.state.startsWith('ENDED') || x.state === 'PAUSED' ? x.last_output_at : S.clock;
  const n = Math.max(0, Math.floor((end - x.started_at) / (8 * MIN)));
  return Array.from({ length: Math.min(n, 6) }, (_, i) => ({ n: i + 1, at: x.started_at + (i + 1) * 8 * MIN, text: i % 2 ? 'Wrote the notes and the list of changed files' : 'Saved the plan position and 2 changed files' }));
}

export function relationsOf(S, kind, id) {
  const G = [], g = (title, items) => { if (items.length) G.push({ title, items }); };
  const it = (k, i, label, note) => ({ kind: k, id: i, label, note });
  if (kind === 'mission') {
    const m = S.missions[id], tasks = m.tasks.map((x) => S.tasks[x]), execs = Object.values(S.executions).filter((x) => x.mission === id);
    g('Project', [it('project', 'prj-' + m.project, S.projects.find((p) => p.id === m.project).name, m.branch)]);
    g('Plans', Object.values(S.plans).filter((p) => p.mission === id).map((p) => it('plan', p.id, 'Plan version ' + p.version, present('plan', p.state).label)));
    g('Tasks', tasks.map((t) => it('task', t.id, t.title, present('task', t.state).label)));
    g('Executions', execs.map((x) => it('execution', x.id, x.id, present('execution', x.state).label + ' on ' + accountLabel(S, x.account))));
    g('Route decisions', tasks.filter((t) => t.execution).map((t) => it('route', 'rd-' + t.id, 'Route for "' + t.title + '"', routeOf(S, t).chosen.harnessLabel)));
    g('Decisions', Object.values(S.approvals).filter((a) => a.mission === id).map((a) => it('approval', a.id, a.presented.what, present('approval', a.state).label)));
    g('Verifications', Object.values(S.verifications).filter((v) => v.mission === id).map((v) => it('verification', v.id, v.id + ' on ' + v.base_revision, present('verification', v.state).label)));
    g('Knowledge it can use', S.knowledge.filter((k) => k.project === m.project && k.state === 'CONFIRMED').map((k) => it('knowledge', k.id, k.text, 'Confirmed')));
    g('Account and model', [it('account', m.account, accountLabel(S, m.account), 'Account'), it('model', 'mdl-' + m.model, (S.models.find((x) => x.id === m.model) || {}).label, 'Model')]);
    if (m.origin === 'idea') g('Came from', S.ideas.filter((i) => i.project === m.project).slice(0, 1).map((i) => it('idea', i.id, i.title, present('idea', i.state).label)));
  } else if (kind === 'task') {
    const t = S.tasks[id], m = S.missions[t.mission];
    g('Mission', [it('mission', m.id, m.title, present('mission', m.state).label)]);
    g('Execution', t.execution ? [it('execution', t.execution, t.execution, present('execution', S.executions[t.execution].state).label)] : []);
    g('Route decision', t.execution ? [it('route', 'rd-' + t.id, 'How it was routed', routeOf(S, t).chosen.harnessLabel)] : []);
    g('Plan', Object.values(S.plans).filter((p) => p.mission === m.id && p.state === 'APPROVED').map((p) => it('plan', p.id, 'Plan version ' + p.version, 'Approved')));
  } else if (kind === 'execution') {
    const x = S.executions[id], t = S.tasks[x.task], m = S.missions[x.mission];
    g('Task and mission', [it('task', t.id, t.title, present('task', t.state).label), it('mission', m.id, m.title, present('mission', m.state).label)]);
    g('Runs on', [it('account', x.account, accountLabel(S, x.account), 'Account'), it('model', 'mdl-' + x.model, (S.models.find((q) => q.id === x.model) || {}).label, 'Model'), it('breaker', 'bk-' + x.harness, harnessLabel(x.harness), 'Spawn breaker')]);
    g('Asked you', Object.values(S.approvals).filter((a) => a.ref === x.id).map((a) => it('approval', a.id, a.presented.what, present('approval', a.state).label)));
  } else if (kind === 'approval') {
    const a = S.approvals[id], m = S.missions[a.mission];
    g('Mission', [it('mission', m.id, m.title, present('mission', m.state).label)]);
    g(a.kind === 'plan' ? 'Plan' : 'Execution', a.kind === 'plan' ? [it('plan', a.ref, 'Plan ' + a.ref.split('-').pop(), 'Under decision')] : [it('execution', a.ref, a.ref, present('execution', S.executions[a.ref].state).label)]);
    g('Hook that asked', a.kind === 'action' ? [it('hook', 'h-1', 'ask before git push', 'PreToolUse')] : []);
  } else if (kind === 'plan') {
    const p = S.plans[id], m = S.missions[p.mission];
    g('Mission', [it('mission', m.id, m.title, present('mission', m.state).label)]);
    g('Tasks', m.tasks.map((x) => S.tasks[x]).map((t) => it('task', t.id, t.title, present('task', t.state).label)));
    g('Decision', Object.values(S.approvals).filter((a) => a.ref === id).map((a) => it('approval', a.id, a.presented.what, present('approval', a.state).label)));
  } else if (kind === 'verification') {
    const v = S.verifications[id], m = S.missions[v.mission];
    g('Mission', [it('mission', m.id, m.title, present('mission', m.state).label)]);
    g('Task', [it('task', v.task, S.tasks[v.task].title, present('task', S.tasks[v.task].state).label)]);
  } else if (kind === 'knowledge') {
    const k = S.knowledge.find((x) => x.id === id);
    g('Project', [it('project', 'prj-' + k.project, S.projects.find((p) => p.id === k.project).name, '')]);
    g('Missions that can use it', Object.values(S.missions).filter((m) => m.project === k.project).map((m) => it('mission', m.id, m.title, present('mission', m.state).label)));
  } else if (kind === 'idea') {
    const i = S.ideas.find((x) => x.id === id);
    g('Project', [it('project', 'prj-' + i.project, S.projects.find((p) => p.id === i.project).name, '')]);
    g('Missions from ideas', Object.values(S.missions).filter((m) => m.origin === 'idea' && m.project === i.project).map((m) => it('mission', m.id, m.title, present('mission', m.state).label)));
  } else if (kind === 'project') {
    const pid = id.replace(/^prj-/, '');
    g('Missions', Object.values(S.missions).filter((m) => m.project === pid).map((m) => it('mission', m.id, m.title, present('mission', m.state).label)));
    g('Ideas', S.ideas.filter((i) => i.project === pid).map((i) => it('idea', i.id, i.title, present('idea', i.state).label)));
    g('Knowledge', S.knowledge.filter((k) => k.project === pid).map((k) => it('knowledge', k.id, k.text, present('knowledge_item', k.state).label)));
  }
  return G;
}

export const BREAKER_WORD = { closed: 'Closed', open: 'Open', half_open: 'Half open' };
export function breakerView(S, h) {
  const b = h.breaker, left = b.state === 'open' ? Math.max(0, b.until - S.clock) : 0;
  return { id: h.id, label: h.label, installed: h.state !== 'MISSING', state: b.state, word: BREAKER_WORD[b.state], failures: b.failures.length, error: b.last_error, left };
}
export const waitLabel = (ms) => { const s = Math.ceil(ms / 1000); return s >= 60 ? Math.floor(s / 60) + ' min ' + String(s % 60).padStart(2, '0') + ' s' : s + ' s'; };
export { STATIONS };

// ---------- offline: a stale read of what the client kept ----------
export function keptSummary(S) {
  const ms = Object.values(S.missions);
  const decide = Object.values(S.approvals).filter((a) => a.state === 'PENDING'), review = ms.filter((m) => m.state === 'REVIEWING'), stopped = ms.filter((m) => m.state === 'BLOCKED' || m.state === 'FAILED');
  const running = Object.values(S.executions).filter((x) => present('execution', x.state).cls === 'active').length, need = decide.length + review.length + stopped.length;
  const parts = [];
  if (need) parts.push(need + (need === 1 ? ' needs' : ' need') + ' you');
  if (running) parts.push(running + ' running');
  return { decide, review, stopped, running, need, sentence: parts.length ? parts.join(' · ') : 'Nothing needed you' };
}
