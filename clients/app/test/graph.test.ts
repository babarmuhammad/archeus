// P18: the spatial view's pure parts (p18-design-gate §13, §15): the encoding
// against the renderer, the G4 mechanisms, keyboard traversal, the mirror,
// layout determinism, stability and budget, level of detail, the one loop and
// its parking, energy from Core's state, routes and invalidation.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { DASH, ENCODING, attrsText, colourVar, countsText, dashOf, lookOf, tracePath } from '../src/graph/encoding.ts';
import { allExpanded, around, build, inFocus, keyOf, lifted, liveExecutions, path, pathStatus, pulseEdge, pulseFor, PULSE_EVERY_MS, PULSE_MS, search, toggle, visible, type GraphData } from '../src/graph/model.ts';
import { ITERATIONS, layout, pinchCamera } from '../src/graph/layout.ts';
import { draw, frame, LOD_NODES, staticSig, type Scene } from '../src/graph/render.ts';
import { Loop, SLOW_FRAME_MS, SLOW_FRAMES, type LoopHost } from '../src/graph/loop.ts';
import { DOUBLE_TAP_MS, doubleTap, selected, start, step } from '../src/graph/keys.ts';
import { mirrorRows } from '../src/graph/mirror.ts';
import { TIER_STYLE } from '../src/graph/relations.ts';
import { present } from '../src/state/present.ts';
import { href, parse } from '../src/nav/destinations.ts';
import { staleBy } from '../src/data/invalidation.ts';

const P = { kind: 'project', id: 'prj_1' };
const M = { kind: 'mission', id: 'msn_1' };
const PL = { kind: 'plan', id: 'pln_1' };
const T1 = { kind: 'task', id: 'tsk_1' };
const T2 = { kind: 'task', id: 'tsk_2' };
const X1 = { kind: 'execution', id: 'exe_1' };
const X2 = { kind: 'execution', id: 'exe_2' };
const K = { kind: 'knowledge_item', id: 'kn_1' };

const e = (field: string, from: { kind: string; id: string }, to: { kind: string; id: string }, extra = {}) => ({
  id: `${field}|${from.kind}:${from.id}|${to.kind}:${to.id}`,
  from,
  to,
  field,
  rel: null,
  tier: null,
  inactive: false,
  structural: false,
  ...extra,
});

const DATA: GraphData = {
  nodes: [
    { ...M, label: 'Ship the chart', parent: P, machine: 'mission', state: 'EXECUTING' },
    { ...P, label: 'Atlas', parent: null },
    { ...PL, label: 'Plan v1', parent: M, machine: 'plan', state: 'APPROVED' },
    { ...T1, label: 'Write it', parent: PL, machine: 'task', state: 'RUNNING' },
    { ...T2, label: 'Test it', parent: PL, machine: 'task', state: 'PENDING' },
    { ...X1, label: 'Attempt 1', parent: T1, machine: 'execution', state: 'ENDED_HANDOFF' },
    { ...X2, label: 'Attempt 2', parent: T1, machine: 'execution', state: 'RUNNING' },
    { ...K, label: 'Use bars', parent: P, machine: 'knowledge_item', state: 'CONFIRMED', type: 'DECISION' },
    { kind: 'decision', id: 'dec_1', label: 'decision dec_1', endpoint: true, missing: false },
  ],
  edges: [
    e('missions.project_id', M, P),
    e('plans.mission_id', PL, M),
    e('tasks.plan_id', T1, PL, { structural: true }),
    e('tasks.plan_id', T2, PL, { structural: true }),
    e('Task.depends_on', T2, T1),
    e('executions.task_id', X1, T1),
    e('executions.task_id', X2, T1),
    e('executions.mission_id', X2, M),
    e('Execution.handoff_from', X2, X1),
    e('relations.learned_from', K, M, { rel: 'learned_from', tier: 'INFERRED' }),
    e('relations.motivated', { kind: 'decision', id: 'dec_1' }, K, { rel: 'motivated', tier: 'AMBIGUOUS' }),
  ],
  hidden: [{ parent: M, kind: 'session', count: 3 }],
  truncated: true,
};

const m = build(DATA);
const k = keyOf;

// ── the encoding against the renderer (A3, M04) ──

function recorder() {
  const ops: string[] = [];
  const state: Record<string, unknown> = {};
  const ctx = new Proxy(state, {
    get(t, p: string) {
      if (p in t) return t[p];
      return (...a: unknown[]) => {
        ops.push(`${p}(${a.map((x) => (typeof x === 'number' ? Math.round(x * 100) / 100 : JSON.stringify(x))).join(',')})`);
      };
    },
    set(t, p: string, v) {
      t[p] = v;
      if (p === 'fillStyle' || p === 'strokeStyle') ops.push(`${p}=${String(v)}`);
      return true;
    },
  }) as unknown as CanvasRenderingContext2D;
  return { ctx, ops };
}

function scene(data: GraphData, extra: Partial<Scene> = {}): Scene {
  const mm = build(data);
  const vis = visible(mm, allExpanded(mm));
  const keys = mm.nodes.map(keyOf).filter((x) => vis.has(x));
  const pos = new Map(keys.map((x, i) => [x, { x: i * 10, y: (i % 7) * 10 }]));
  return {
    model: mm, keys, drawn: lifted(mm, vis), pos, cam: { x: 0, y: 0, k: 1 }, focus: null, context: null, live: new Set(), liveStatic: false,
    pulse: new Map(), colour: (v) => v, width: 100, height: 100, dpr: 1, ...extra,
  };
}

test('every kind in the encoding is drawn as its own shape, filled or stroked as encoded (A3)', () => {
  for (const [kind, look] of Object.entries(ENCODING)) {
    const { ctx, ops } = recorder();
    draw(ctx, scene({ nodes: [{ kind, id: 'x', label: 'x' }], edges: [] }));
    const want = recorder();
    const { filled } = tracePath(want.ctx, look.shape, 0, 0, kind === 'project' ? 26 : look.shape === 'dot' ? 4 : ['circle', 'square', 'ring', 'folder'].includes(look.shape) ? 10 : 7);
    const traced = want.ops.join(';');
    assert.ok(ops.join(';').includes(traced), `${kind}: its shape is not what the encoding traces`);
    assert.ok(ops.includes(filled ? 'fill()' : 'stroke()'), kind);
  }
  assert.equal(lookOf('knowledge_item', false, 'DECISION').shape, 'diamond');
  assert.equal(lookOf('session').shape, 'ring'); // P16 §20.10, not "person" (V1)
  assert.equal(lookOf('decision', true).shape, 'endpoint');
});

test('each confidence tier is drawn with its own dash; a column edge is solid (M04)', () => {
  assert.deepEqual(TIER_STYLE, { EXTRACTED: 'solid', INFERRED: 'dashed', AMBIGUOUS: 'dotted' });
  assert.deepEqual(dashOf('INFERRED'), [6, 4]);
  assert.deepEqual(dashOf('AMBIGUOUS'), [1.5, 3]);
  assert.deepEqual(dashOf('EXTRACTED'), []);
  assert.deepEqual(dashOf(null), []);
  const { ctx, ops } = recorder();
  draw(ctx, scene({ nodes: [{ ...K, label: 'k' }, { ...M, label: 'm' }], edges: [e('relations.learned_from', K, M, { tier: 'INFERRED' })] }));
  assert.ok(ops.includes(`setLineDash(${JSON.stringify(DASH.dashed)})`), ops.join('\n'));
});

test('only missions, tasks and executions are coloured by state', () => {
  const { ctx, ops } = recorder();
  draw(ctx, scene({ nodes: [{ ...M, label: 'm', machine: 'mission', state: 'EXECUTING' }, { ...K, label: 'k', machine: 'knowledge_item', state: 'CONFIRMED' }], edges: [] }));
  const fills = ops.filter((o) => o.startsWith('fillStyle=')).map((o) => o.slice(10));
  assert.ok(fills.includes('--state-active'));
  assert.ok(!fills.some((f) => f.startsWith('--state-') && f !== '--state-active'));
});

// ── the G4 mechanisms (A7, A13) ──

test('edges lift to the nearest visible ancestor and count what they stand for (M24)', () => {
  const closed = toggle(allExpanded(m), k(PL)); // collapse the plan: tasks and executions hide
  const vis = visible(m, closed);
  assert.ok(vis.has(k(PL)) && !vis.has(k(T1)) && !vis.has(k(X2)));
  const d = lifted(m, vis);
  const toMission = d.find((x) => [x.a, x.b].includes(k(M)) && [x.a, x.b].includes(k(PL)));
  // plans.mission_id + X2's executions.mission_id, lifted to the plan
  assert.equal(toMission?.count, 2);
  assert.ok(!d.some((x) => x.a === x.b));
});

test('collapse hides every descendant, expand shows them again (M26)', () => {
  const closed = toggle(allExpanded(m), k(M));
  const vis = visible(m, closed);
  for (const x of [PL, T1, T2, X1, X2]) assert.ok(!vis.has(k(x)), x.id);
  assert.ok(vis.has(k(M)) && vis.has(k(P)) && vis.has(k(K)));
  assert.ok(visible(m, toggle(closed, k(M))).has(k(X2)));
});

test('focus + context keeps the focus and its neighbours, dims the rest (M25)', () => {
  const d = lifted(m, visible(m, allExpanded(m)));
  const ctx = inFocus(d, k(X2))!;
  assert.deepEqual([...ctx].sort(), [k(M), k(T1), k(X1), k(X2)].sort());
  assert.equal(inFocus(d, null), null);
});

test('search finds loaded nodes and expands their ancestors, asking Core nothing (M16)', () => {
  const closed = toggle(toggle(allExpanded(m), k(M)), k(PL));
  const { hits, expanded } = search(m, closed, 'attempt 2');
  assert.deepEqual(hits, [k(X2)]);
  assert.ok(visible(m, expanded).has(k(X2)));
  assert.deepEqual(search(m, closed, 'more').hits, []); // the "+N" stub is not a node
});

test('a path runs over loaded edges only; none is invented', () => {
  const p = path(m, k(X1), k(P))!;
  assert.deepEqual(p, path(m, k(X1), k(P))); // the same answer every time
  assert.equal(p[0], k(X1));
  assert.equal(p[p.length - 1], k(P));
  for (let i = 0; i + 1 < p.length; i++)
    assert.ok(m.edges.some((x) => [k(x.from), k(x.to)].includes(p[i]) && [k(x.from), k(x.to)].includes(p[i + 1])), `${p[i]}→${p[i + 1]} is no loaded edge`);
  const island = build({ nodes: [{ ...M, label: 'm' }, { ...K, label: 'k' }], edges: [] });
  assert.equal(path(island, k(M), k(K)), null);
});

test('what the cap cut is one "+N" stub per parent and kind, listed and drawable', () => {
  const stub = m.nodes.find((n) => n.kind === 'more')!;
  assert.equal(stub.label, '+3 more session');
  assert.equal(m.parentOf.get(keyOf(stub)), k(M));
});

// ── keyboard traversal (A11, M15) ──

test('↓ visits every edge of the focus in the drawn order and wraps; → crosses; ← returns', () => {
  const d = lifted(m, visible(m, allExpanded(m)));
  const edges = around(d, k(M));
  let w = start(k(M));
  const seen: string[] = [];
  for (let i = 0; i < edges.length; i++) {
    seen.push(edges[w.sel].other);
    w = step(w, 'ArrowDown', d, k(M)).walk;
  }
  assert.deepEqual(seen, edges.map((x) => x.other));
  assert.equal(w.sel, 0);
  assert.equal(step(w, 'ArrowUp', d, k(M)).walk.sel, edges.length - 1);
  const crossed = step(w, 'ArrowRight', d, k(M)).walk;
  assert.equal(crossed.at, edges[0].other);
  const back = step(crossed, 'ArrowLeft', d, k(M)).walk;
  assert.equal(back.at, k(M));
  assert.equal(around(d, k(M))[back.sel].other, crossed.at);
  assert.equal(step(crossed, 'Home', d, k(M)).walk.at, k(M));
  assert.equal(step(w, 'Enter', d, k(M)).command, 'open');
  for (const [key, cmd] of [['+', 'zoom-in'], ['-', 'zoom-out'], ['0', 'fit'], ['/', 'search'], [' ', 'toggle']] as const)
    assert.equal(step(w, key, d, k(M)).command, cmd);
});

// ── the mirror (A11, M14) ──

test('the mirror lists exactly the loaded nodes — collapsed ones and stubs too — with their edges in words', () => {
  const rows = mirrorRows(m);
  assert.deepEqual(rows.map((r) => r.k), m.nodes.map(keyOf));
  const x2 = rows.find((r) => r.k === k(X2))!;
  assert.ok(x2.edges.some((x) => x.text === 'continues Attempt 1'));
  assert.ok(rows.find((r) => r.k === k(X1))!.edges.some((x) => x.text === 'continued by Attempt 2'));
  assert.ok(rows.find((r) => r.k === k(K))!.edges.some((x) => x.text === 'learned_from Ship the chart (inferred)'));
});

// ── layout (A7, A10: M13, M28) ──

function big(n: number) {
  const nodes = [{ ...P, label: 'p' }] as GraphData['nodes'];
  const edges = [];
  for (let i = 0; i < n - 1; i++) {
    const me = { kind: 'knowledge_item', id: `kn_${i}` };
    nodes.push({ ...me, label: `fact ${i}`, parent: P });
    edges.push(e('knowledge_items.project_id', me, P, { structural: true }));
  }
  return { nodes, edges } as GraphData;
}

function place(d: GraphData, seed = 'focus', prev?: Map<string, { x: number; y: number }>) {
  const mm = build(d);
  const vis = visible(mm, allExpanded(mm));
  const keys = mm.nodes.map(keyOf).filter((x) => vis.has(x));
  return layout({ keys, parentOf: (x) => mm.parentOf.get(x) ?? null, radius: () => 8, links: lifted(mm, vis).map((x) => [x.a, x.b] as [string, string]), seed, prev });
}

test('the same data and focus give the same picture; nothing reads a clock or Math.random (M13)', () => {
  assert.deepEqual([...place(DATA)], [...place(DATA)]);
  assert.notDeepEqual([...place(DATA)], [...place(DATA, 'another focus')]);
  const src = readFileSync(new URL('../src/graph/layout.ts', import.meta.url), 'utf8').replace(/\/\/.*$/gm, '');
  assert.ok(!/Math\.random|Date\.now|performance\.now/.test(src));
});

test('a refresh that adds a node moves no node already placed (M28)', () => {
  const before = place(DATA);
  const more = { ...DATA, nodes: [...DATA.nodes, { kind: 'session', id: 'ses_9', label: 's', parent: M }], edges: [...DATA.edges, e('sessions.mission_id', { kind: 'session', id: 'ses_9' }, M)] };
  const after = place(more, 'focus', before);
  for (const [key, p] of before) assert.deepEqual(after.get(key), p, key);
  assert.ok(after.has('session:ses_9'));
});

test('a 1,000-node layout is a fixed amount of work within budget (A10 proxy 1)', () => {
  assert.equal(ITERATIONS, 120);
  const t = performance.now();
  const pos = place(big(1000));
  const took = performance.now() - t;
  assert.equal(pos.size, 1000);
  for (const p of pos.values()) assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y));
  // measured ~0.3 s on the development machine; a wide regression margin, not a GPU claim
  assert.ok(took < 5000, `layout took ${took} ms`);
});

// ── level of detail (A10, M20) ──

test('above 250 visible nodes every node is a dot, batched per colour', () => {
  const { ctx } = recorder();
  const many = draw(ctx, scene(big(LOD_NODES + 50)));
  assert.equal(many.lod, 'dots');
  assert.ok(many.paths < 20, `${many.paths} paths for ${many.nodes} nodes`);
  const few = draw(recorder().ctx, scene(big(LOD_NODES - 50)));
  assert.equal(few.lod, 'full');
  assert.ok(few.paths >= LOD_NODES - 50);
});

// ── the one loop (A9: M17, M18) ──

function host(over: Partial<LoopHost> = {}) {
  const q: ((t: number) => void)[] = [];
  let now = 0;
  const h: LoopHost & { run: () => number; tick: (ms: number) => void; pending: () => number } = {
    raf: (cb) => q.push(cb),
    caf: (id) => void (q[id - 1] = () => undefined),
    now: () => now,
    hidden: () => false,
    focused: () => true,
    reduced: () => false,
    ...over,
    run() {
      let n = 0;
      while (q.length && n < 1000) {
        q.shift()!(now);
        n++;
      }
      return n;
    },
    tick(ms) {
      now += ms;
    },
    pending: () => q.length,
  };
  return h;
}

test('a redraw is one frame, then the loop parks (M17)', () => {
  const h = host();
  let drawn = 0;
  const l = new Loop(h, () => drawn++);
  assert.equal(l.state, 'parked');
  l.request();
  l.request();
  assert.equal(h.run(), 1);
  assert.equal(drawn, 1);
  assert.equal(l.state, 'parked');
  assert.equal(h.pending(), 0);
});

test('an animation runs until it ends, then parks', () => {
  const h = host();
  const l = new Loop(h, () => h.tick(100));
  assert.equal(l.animate(240), true);
  h.run();
  assert.equal(l.state, 'parked');
  assert.equal(l.animating, 0);
  assert.ok(l.frames >= 3);
});

test('reduced motion: no animation is accepted; the change still draws once (M18)', () => {
  const h = host({ reduced: () => true });
  const l = new Loop(h, () => undefined);
  assert.equal(l.animate(240), false);
  assert.equal(l.animating, 0);
  assert.equal(h.run(), 1);
});

test('a hidden page, a blurred window and a lost context park the loop; waking resumes', () => {
  for (const cond of ['hidden', 'blurred', 'lost'] as const) {
    let hidden = cond === 'hidden';
    let focused = cond !== 'blurred';
    const h = host({ hidden: () => hidden, focused: () => focused });
    const l = new Loop(h, () => undefined);
    if (cond === 'lost') l.setLost(true);
    l.request();
    l.animate(1000);
    assert.equal(h.pending(), 0, cond);
    assert.equal(l.state, 'parked', cond);
    hidden = false;
    focused = true;
    if (cond === 'lost') l.setLost(false);
    else l.wake();
    assert.equal(l.state, 'running', cond);
  }
});

test('requestAnimationFrame has exactly one caller in the client: the graph loop (M19)', () => {
  const root = new URL('../src/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
  const hits: string[] = [];
  const walk = (dir: string) => {
    for (const f of readdirSync(dir)) {
      const p = join(dir, f);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.tsx?$/.test(f) && /requestAnimationFrame\s*\(/.test(readFileSync(p, 'utf8'))) hits.push(p.replace(/\\/g, '/'));
    }
  };
  walk(root);
  assert.deepEqual(hits.map((p) => p.slice(p.indexOf('src/'))), ['src/graph/loop.ts']);
});

// ── energy from Core's state (A8, M32) ──

test('only an execution Core says is active is live; its pulse edge is its task edge', () => {
  const live = liveExecutions(m, (mc, s) => present(mc, s).cls === 'active');
  assert.deepEqual([...live], [k(X2)]); // RUNNING, never ENDED_HANDOFF
  const d = lifted(m, visible(m, allExpanded(m)));
  assert.equal(pulseEdge(d, k(X2))?.edges[0].field, 'executions.task_id');
});

// ── routes and invalidation (A4, A8: M30) ──

test('every graph step is a URL, and a project page keeps its own', () => {
  assert.deepEqual(parse('#/world/graph'), { view: 'world', graph: 'world' });
  assert.deepEqual(parse('#/world/graph/mission/msn_1'), { view: 'world', graph: { kind: 'mission', id: 'msn_1' } });
  assert.deepEqual(parse('#/world/graph/repository/rep_1/modules/app%2Fcore'), { view: 'world', graph: { kind: 'repository', id: 'rep_1' }, modules: 'app/core' });
  assert.deepEqual(parse('#/world/prj_1'), { view: 'world', project: 'prj_1' });
  for (const h of ['#/world/graph', '#/world/graph/mission/msn_1', '#/world/graph/repository/rep_1/modules', '#/world/graph/repository/rep_1/modules/app%2Fcore'])
    assert.equal(href(parse(h)), h);
});

test('a frame about anything the graph is read from makes the graph stale (M30)', () => {
  const g = '/v1/world/graph?focus=mission:msn_1';
  for (const kind of ['mission', 'execution', 'task', 'plan', 'session', 'relation', 'knowledge_item', 'approval', 'verification', 'review', 'project', 'repository', 'automation_run'])
    assert.equal(staleBy({ event: `${kind}.updated`, data: { subject: { kind, id: 'x' } } })(g), true, kind);
  assert.equal(staleBy({ event: 'device.seen', data: { subject: { kind: 'device', id: 'x' } } })(g), false);
  assert.equal(staleBy({ event: 'repository_inspection.completed', data: { subject: { kind: 'repository_inspection', id: 'x' } } })('/v1/repositories/rep_1/graph?focus=app'), true);
});

test('the graph code sends nothing: its only reads are the two graph paths', () => {
  const dir = new URL('../src/graph/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
  for (const f of readdirSync(dir)) {
    const src = readFileSync(join(dir, f), 'utf8');
    assert.ok(!/'POST'|"POST"|send\(/.test(src), `${f} sends`);
    for (const m2 of src.matchAll(/[`'"](\/v1\/[^`'"]*)/g)) assert.ok(/^\/v1\/(world\/graph|repositories\/)/.test(m2[1]), `${f}: ${m2[1]}`);
  }
});

// ── the post-audit round (gate §22 F1–F6) ──

test('a superseded or rejected plan version is drawn at --text-3, a current one neutral (F5, A3: M34)', () => {
  const plan = (state: string) => {
    const { ctx, ops } = recorder();
    draw(ctx, scene({ nodes: [{ ...PL, label: 'v', machine: 'plan', state }], edges: [] }));
    return ops.filter((o) => o.startsWith('strokeStyle=')).map((o) => o.slice(12));
  };
  for (const s of ['SUPERSEDED', 'REJECTED']) assert.deepEqual(plan(s), ['--text-3'], s);
  for (const s of ['APPROVED', 'PROPOSED', 'DRAFT']) assert.deepEqual(plan(s), ['--text-2'], s);
  assert.equal(colourVar('plan', 'plan', 'SUPERSEDED'), '--text-3');
  assert.equal(colourVar('plan', 'plan', 'APPROVED'), '--text-2');
});

test('pin: "." toggles the focused node; the mirror says which are pinned; a pinned node stays put (F1, A13: M35, M36)', () => {
  const d = lifted(m, visible(m, allExpanded(m)));
  assert.equal(step(start(k(M)), '.', d, k(M)).command, 'pin');
  const pinned = toggle(new Set(), k(T1));
  assert.deepEqual(mirrorRows(m, pinned).filter((r) => r.pinned).map((r) => r.k), [k(T1)]);
  assert.deepEqual(mirrorRows(m).filter((r) => r.pinned), []);
  assert.equal(toggle(pinned, k(T1)).size, 0); // the same key unpins
  const mm = build(DATA);
  const vis = visible(mm, allExpanded(mm));
  const keys = mm.nodes.map(keyOf).filter((x) => vis.has(x));
  const at = { x: 999, y: -999 };
  const pos = layout({ keys, parentOf: (x) => mm.parentOf.get(x) ?? null, radius: () => 8, links: lifted(mm, vis).map((x) => [x.a, x.b] as [string, string]), seed: 'f', prev: new Map([[k(T1), at]]), pinned });
  assert.deepEqual(pos.get(k(T1)), at);
  // view state only: nothing in the graph code stores or sends a pin
  const view = readFileSync(new URL('../src/graph/GraphView.tsx', import.meta.url), 'utf8');
  assert.ok(!/localStorage|sessionStorage|indexedDB/.test(view));
});

test('three slow frames during an animation degrade it until it ends; one frame then restores (F2, A10: M37, M46)', () => {
  const h = host();
  const seen: boolean[] = [];
  const l = new Loop(h, () => {
    seen.push(l.degraded);
    h.tick(25); // every frame takes 25 ms: over SLOW_FRAME_MS
  });
  assert.equal(SLOW_FRAME_MS, 20);
  assert.equal(SLOW_FRAMES, 3);
  l.animate(300);
  h.run();
  // frame 1 has no previous frame; frames 2, 3 and 4 are slow: the third slow one is drawn degraded
  assert.deepEqual(seen.slice(0, 4), [false, false, false, true]);
  assert.equal(seen[seen.length - 1], false, 'the frame after the animation draws everything again');
  assert.equal(l.degraded, false);
  assert.equal(l.state, 'parked');
  const fast = host();
  const f = new Loop(fast, () => {
    fast.tick(10);
    assert.equal(f.degraded, false);
  });
  f.animate(300);
  fast.run();
  const idle = host(); // slow frames with nothing animating (single redraws) never degrade
  const r = new Loop(idle, () => idle.tick(100));
  for (let i = 0; i < 5; i++) {
    r.request();
    idle.run();
  }
  assert.equal(r.degraded, false);
});

test('degraded, a frame draws no pulse and no label but the focus (F2, A10: M38)', () => {
  const pulsed = scene(DATA);
  const id = pulseEdge(pulsed.drawn, k(X2))!.id;
  const run = (degraded: boolean) => {
    const { ctx, ops } = recorder();
    const st = draw(ctx, { ...pulsed, focus: k(M), pulse: new Map([[id, 0.5]]), degraded });
    return { st, active: ops.includes('strokeStyle=--state-active') };
  };
  const full = run(false);
  const slow = run(true);
  assert.ok(full.active && full.st.labels > 1);
  assert.ok(!slow.active, 'a pulse drawn while degraded');
  assert.equal(slow.st.labels, 1);
});

test('a pulse frame reuses the static layer: one copy and one path per pulse, whatever the size (F3, A10 proxy 5: M39, M40, M47)', () => {
  const s = scene(big(1000));
  const id = s.drawn[0].id;
  const layer = { ctx: recorder().ctx, sig: null as readonly unknown[] | null };
  const first = frame(recorder().ctx, layer, s);
  assert.equal(first.layer, true);
  assert.ok(first.layerPaths >= 1, 'the static layer is drawn once');
  for (const t of [0.1, 0.5, 0.9]) {
    const top = recorder();
    const f = frame(top.ctx, layer, { ...s, pulse: new Map([[id, t]]) });
    assert.equal(f.layer, false, 'a pulse redrew the static layer');
    assert.equal(f.paths, 1, `${f.paths} paths for one pulse over ${s.keys.length} nodes`);
    assert.equal(top.ops.filter((o) => o.startsWith('drawImage(')).length, 1);
  }
  // anything the static layer shows redraws it: the camera, the selection, the degrade
  for (const change of [{ cam: { x: 1, y: 0, k: 1 } }, { selected: id }, { degraded: true }, { width: 101 }] as Partial<Scene>[]) {
    frame(recorder().ctx, layer, s);
    assert.equal(frame(recorder().ctx, layer, { ...s, ...change }).layer, true, JSON.stringify(change));
  }
  assert.ok(!staticSig(s).includes(s.pulse), 'the pulse map is part of the static layer');
});

test('a pulse: only an execution.* frame about a live execution, once per 2 s per edge, never reduced (F6, A8: M42, M43)', () => {
  const d = lifted(m, visible(m, allExpanded(m)));
  const live = new Set([pulseEdge(d, k(X2))!.id]);
  const f = (kind: string, id: string, event = `${kind}.progress`) => ({ event, data: { subject: { kind, id } } });
  const last = new Map<string, number>();
  const got = pulseFor(f('execution', X2.id), d, live, last, 1000, false);
  assert.equal(got?.id, [...live][0]);
  last.set(got!.id, 1000);
  assert.equal(pulseFor(f('execution', X2.id), d, live, last, 1000 + PULSE_EVERY_MS - 1, false), null, 'twice within 2 s');
  assert.equal(pulseFor(f('execution', X2.id), d, live, last, 1000 + PULSE_EVERY_MS, false)?.id, got!.id);
  assert.equal(pulseFor(f('execution', X1.id), d, live, new Map(), 0, false), null, 'an ended execution pulsed'); // ENDED_HANDOFF
  assert.equal(pulseFor(f('execution', X2.id), d, live, new Map(), 0, true), null, 'a pulse under reduced motion');
  assert.equal(pulseFor(f('task', T1.id), d, live, new Map(), 0, false), null);
  assert.equal(pulseFor(f('execution', X2.id, 'mission.updated'), d, live, new Map(), 0, false), null);
  assert.equal(pulseFor({ event: 'execution.progress' }, d, live, new Map(), 0, false), null);
  assert.equal(PULSE_MS, 240);
});

// ── the approved behaviours built after the consistency pass (gate §22.2 N1–N7) ──

const WORLD: GraphData = {
  nodes: [
    { ...P, label: 'Atlas', parent: null, counts: { missions: 3, mission_states: { COMPLETED: 2, EXECUTING: 1 }, repositories: 1, sessions: 0, knowledge_items: 5 } },
    { kind: 'project', id: 'prj_2', label: 'Borealis', parent: null, counts: { missions: 0, mission_states: {}, repositories: 0, sessions: 2, knowledge_items: 1 } },
  ],
  edges: [],
};
const fills = (ops: string[]) => ops.filter((o) => o.startsWith('fillText(')).map((o) => JSON.parse('[' + o.slice(9, -1) + ']')[0] as string);

test('a world-level project shows the counts Core returned, by Core state, on the canvas and in the mirror (N1: M50, M51)', () => {
  const want = '3 missions (Done — verified and reviewed: 2, Executing: 1) · 1 repository · 0 sessions · 5 knowledge items';
  assert.equal(countsText(WORLD.nodes[0].counts), want);
  assert.equal(countsText(WORLD.nodes[1].counts), '0 missions · 0 repositories · 2 sessions · 1 knowledge item');
  assert.equal(countsText(undefined), '');
  const { ctx, ops } = recorder();
  draw(ctx, scene(WORLD));
  assert.ok(fills(ops).includes(want), fills(ops).join(' | '));
  const rows = mirrorRows(build(WORLD));
  assert.equal(rows.find((r) => r.k === k(P))!.detail, want);
});

const RD: GraphData = {
  nodes: [
    { kind: 'route_decision', id: 'rd_1', label: 'route for Write it', parent: T1, attrs: { harness_id: 'claude_code', account_id: 'personal', model: 'opus', effort: 'high', result: 'SELECTED', fallback_from: ['codex'], eliminated: 2, explanation: 'why it chose', requirements: ['x'], candidates: [{ id: 'c' }], input_snapshot: { a: 1 } } },
    { ...T1, label: 'Write it', machine: 'task', state: 'RUNNING' },
  ],
  edges: [e('RouteDecision.task_id', { kind: 'route_decision', id: 'rd_1' }, T1)],
};
const RD_WORDS = 'harness claude_code · account personal · model opus · effort high · result SELECTED · fell back from codex · 2 eliminated';

test('a focused route decision shows its recorded selection facts and nothing else (N2: M52)', () => {
  assert.equal(attrsText(RD.nodes[0].attrs), RD_WORDS);
  for (const bad of ['why it chose', 'explanation', 'requirements', 'candidates', 'input_snapshot', 'snapshot']) assert.ok(!attrsText(RD.nodes[0].attrs).includes(bad), bad);
  assert.equal(attrsText({ harness_id: 'h', fallback_from: [], eliminated: 0, model: null }), 'harness h');
  const focused = recorder();
  draw(focused.ctx, scene(RD, { focus: 'route_decision:rd_1' }));
  assert.ok(fills(focused.ops).includes(RD_WORDS), 'drawn on focus');
  const other = recorder();
  draw(other.ctx, scene(RD, { focus: k(T1) }));
  assert.ok(!fills(other.ops).includes(RD_WORDS), 'drawn although not focused');
  assert.equal(mirrorRows(build(RD)).find((r) => r.n.kind === 'route_decision')!.detail, RD_WORDS);
});

test('labels: the query focus and the selection always, a hovered node up to 250, never more above (N3: M53, M54)', () => {
  const small = scene(DATA);
  const ctxOf = inFocus(small.drawn, k(X2)); // the walk is at attempt 2: its neighbours
  const base = { focus: k(X2), context: ctxOf, root: k(K) };
  const run = (extra: Partial<Scene>, d = small) => {
    const { ctx, ops } = recorder();
    draw(ctx, { ...d, ...base, ...extra });
    return fills(ops);
  };
  const labelOf = (x: { kind: string; id: string }) => m.byKey.get(k(x))!.label;
  assert.ok(!ctxOf!.has(k(K)) && !ctxOf!.has(k(T2)));
  assert.ok(run({}).includes(labelOf(K)), 'the query focus lost its label when the walk moved');
  assert.ok(!run({}).includes(labelOf(T2)), 'a node outside the context is labelled');
  assert.ok(run({ hover: k(T2) }).includes(labelOf(T2)), 'the hovered node is not labelled');
  // above 250 visible nodes: the focus and the selection only, hover or not
  const many = scene(big(LOD_NODES + 50));
  const a = many.keys[3];
  const b = many.keys[7];
  const { ctx, ops } = recorder();
  draw(ctx, { ...many, focus: a, root: b, hover: many.keys[9], context: null });
  const drawnLabels = fills(ops);
  const names = [a, b].map((x) => many.model.byKey.get(x)!.label);
  for (const nm of names) assert.ok(drawnLabels.includes(nm), nm);
  assert.deepEqual(drawnLabels.filter((t) => !names.includes(t) && t !== 'p'), [], 'labels beyond the focus and the selection'); // 'p' is the project cluster
});

test('path tracing says "none" for two loaded ends with no loaded path, "found" otherwise (N5: M55)', () => {
  assert.equal(pathStatus(m, [k(X1), k(P)]), 'found');
  assert.equal(pathStatus(m, [k(X1)]), null);
  const island = build({ nodes: [{ ...M, label: 'm' }, { ...K, label: 'k' }], edges: [] });
  assert.equal(pathStatus(island, [k(M), k(K)]), 'none');
});

test('Esc clears the selected relationship; ↓ and ↑ start again from either end (N6: M56)', () => {
  const d = lifted(m, visible(m, allExpanded(m)));
  const n = around(d, k(M)).length;
  const w = step(start(k(M)), 'ArrowDown', d, k(M)).walk;
  assert.ok(selected(w, d));
  const cleared = step(w, 'Escape', d, k(M));
  assert.equal(cleared.command, 'clear');
  assert.equal(selected(cleared.walk, d), null, 'Esc kept the selection');
  assert.equal(cleared.walk.at, k(M), 'Esc moved the walk');
  assert.equal(step(cleared.walk, 'ArrowDown', d, k(M)).walk.sel, 0);
  assert.equal(step(cleared.walk, 'ArrowUp', d, k(M)).walk.sel, n - 1);
  assert.equal(step(cleared.walk, 'ArrowRight', d, k(M)).walk.at, k(M), 'crossed an edge nobody selected');
});

test('a pinch scales with the fingers and keeps the point under them still; a double-tap is one node twice, quickly (N7: M57, M58)', () => {
  const start0 = { x: 10, y: -20, k: 1 };
  const mid = { x: 40, y: 30 };
  const c = pinchCamera(start0, 100, 200, mid);
  assert.equal(c.k, 2);
  const world = (cam: { x: number; y: number; k: number }) => ({ x: cam.x + mid.x / cam.k, y: cam.y + mid.y / cam.k });
  assert.deepEqual(world(c), world(start0), 'the point under the fingers moved');
  assert.equal(pinchCamera(start0, 100, 50, mid).k, 0.5);
  assert.equal(pinchCamera(start0, 100, 10_000, mid).k, 4); // the zoom's own bounds
  assert.equal(DOUBLE_TAP_MS, 350);
  assert.equal(doubleTap({ k: 'a', t: 1000 }, 'a', 1300), true);
  assert.equal(doubleTap({ k: 'a', t: 1000 }, 'a', 1000 + DOUBLE_TAP_MS + 1), false);
  assert.equal(doubleTap({ k: 'a', t: 1000 }, 'b', 1100), false);
  assert.equal(doubleTap(null, 'a', 1100), false);
});
