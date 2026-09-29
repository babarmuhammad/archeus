"""The P18 mutation suite (p18-design-gate §15): break each invariant of the
graph query and the spatial view, run the test written for that invariant, and
require it to fail.

    py tools/mutate_p18.py            every mutation
    py tools/mutate_p18.py M01 M20    only these

The runner is tools/mutate_p11.py's snippet engine (each snippet occurs once,
every guarding test passes on the unmutated tree first, files restored whatever
happens). Guarding tests are pytest ids, `node:` TypeScript test files, or
browser tests; a mutant guarded by a browser test rebuilds the SPA before the
run and again after the restore. It edits sources: run it with nothing else
running against the tree.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (its snippet engine)

ROOT = mutate_p11.ROOT
APP = os.path.join(ROOT, 'clients', 'app')
GRAPH = 'archeus/core/application/graph.py'
ROUTES = 'archeus/api/routes.py'
G = 'clients/app/src/graph/'
MODEL, LAYOUT, LOOP, RENDER, KEYS, MIRROR, WIDE, REL, ENC, GV = (G + n for n in (
    'model.ts', 'layout.ts', 'loop.ts', 'render.ts', 'keys.ts', 'mirror.ts', 'wide.ts',
    'relations.ts', 'encoding.ts', 'GraphView.tsx'))
APPTSX = 'clients/app/src/App.tsx'
RULES = 'clients/app/src/data/rules.ts'
Q = 'tests/v1/integration/test_graph_query.py::'
R = 'tests/v1/integration/test_graph_routes.py::'
PAR = 'tests/v1/unit/test_graph_parity.py'
TS = 'node:test/graph.test.ts'
E2E = 'tests/v1/e2e/test_spa_p18.py::'

MUTATIONS = [
    ('M01', 'an edge emitted when its field is empty', [(GRAPH,
     "    if isinstance(value, str) and value:",
     "    if True:")],
     [Q + 'test_no_edge_is_emitted_for_an_empty_field']),
    ('M02', 'a hand-off read from the wrong field', [(GRAPH,
     "        _edge(out, me, 'Execution.handoff_from', 'execution', e.handoff_from)",
     "        _edge(out, me, 'Execution.handoff_from', 'execution', e.task_id)")],
     [PAR]),
    ('M03', "every relation drawn at the EXTRACTED tier, whatever its row says", [(GRAPH,
     "'rel': r.rel, 'tier': r.confidence_tier or 'EXTRACTED',",
     "'rel': r.rel, 'tier': 'EXTRACTED',")],
     [Q + 'test_relation_tiers_are_the_rows_own_and_superseded_plans_are_kept_marked']),
    ('M04', 'an INFERRED relation drawn solid', [(REL,
     "  INFERRED: 'dashed',",
     "  INFERRED: 'solid',")],
     [TS]),
    ('M05', 'a superseded plan version shown as current', [(GRAPH,
     "              inactive=e.state in ('SUPERSEDED', 'REJECTED'))",
     "              inactive=False)")],
     [Q + 'test_relation_tiers_are_the_rows_own_and_superseded_plans_are_kept_marked']),
    ('M06', 'the world level loads every project whole', [(GRAPH,
     "    if focus is None:\n        return _world_level(conn, seq, limit)",
     "    if focus is None:\n        g = _world_level(conn, seq, limit)\n"
     "        for p in list(g['nodes']):\n"
     "            g['nodes'] += world_graph(conn, ('project', p['id']), 1, limit)['nodes'][1:]\n"
     "        return g")],
     [Q + 'test_the_world_level_is_projects_only_collapsed_with_counts']),
    ('M07', 'the focus ignored for an execution', [(GRAPH,
     "    kind, fid = focus\n",
     "    kind, fid = focus if focus[0] != 'execution' else (\n"
     "        'mission', rows.get(conn, E.Execution, focus[1]).entity.mission_id)\n")],
     [Q + 'test_the_focus_is_the_first_node_and_the_depth_holds']),
    ('M08', 'the depth ignored', [(GRAPH,
     "    for hop in range(1, depth + 1):",
     "    for hop in range(1, DEPTH_MAX + 2):")],
     [Q + 'test_the_focus_is_the_first_node_and_the_depth_holds']),
    ('M09', 'the node cap ignored', [(GRAPH,
     "        room = max(0, limit - len(loaded))",
     "        room = len(ranked)")],
     [Q + 'test_the_cap_holds_and_hidden_counts_what_it_cut']),
    ('M10', 'a principal accepted as a focus', [(ROUTES,
     "        if kind not in graph.KINDS:",
     "        if kind not in graph.KINDS and kind != 'principal':")],
     [R + 'test_the_graph_needs_a_credential_and_refuses_what_is_not_a_node']),
    ('M11', "a route decision's explanation serialised", [(GRAPH,
     "        attrs = {a: getattr(e, a) for a in ROUTE_ATTRS}",
     "        attrs = {a: getattr(e, a) for a in ROUTE_ATTRS + ('explanation',)}")],
     [Q + 'test_a_route_decision_shows_recorded_selection_facts_only']),
    ('M12', 'nodes ordered by id instead of by hop, kind and state', [(GRAPH,
     "    return (hop, RANK[kind], settled, _desc(row.updated_at), e.id)",
     "    return (hop, e.id)")],
     [Q + 'test_nodes_come_in_hop_then_kind_rank_order_and_the_same_bytes_twice']),
    ('M13', 'the layout seeded with Math.random', [(LAYOUT,
     "  const rnd = prng(hash(inp.seed));",
     "  const rnd = Math.random;")],
     [TS]),
    ('M14', 'the mirror leaves out the endpoints and the stubs', [(MIRROR,
     "  return model.nodes.map((n) => {",
     "  return model.nodes.filter((n) => !n.endpoint).map((n) => {")],
     [TS]),
    ('M15', 'keyboard traversal skips the last edge', [(KEYS,
     "      return { walk: { ...w, sel: n ? (w.sel + 1) % n : 0 }, command: null };",
     "      return { walk: { ...w, sel: n ? (w.sel + 1) % Math.max(1, n - 1) : 0 }, command: null };")],
     [TS]),
    ('M16', 'search does not expand the ancestors of a match', [(MODEL,
     "    for (const a of ancestors(m, k)) next.add(a);\n",
     "")],
     [TS]),
    ('M17', 'the loop keeps scheduling with nothing to animate', [(LOOP,
     "    if (this.anims.size) this.kick();",
     "    if (true) this.kick();")],
     [TS]),
    ('M18', 'an animation accepted under reduced motion', [(LOOP,
     "    if (this.host.reduced()) {",
     "    if (false) {")],
     [TS]),
    ('M19', 'a second requestAnimationFrame caller', [(RENDER,
     "export function draw(ctx: CanvasRenderingContext2D, s: Scene): DrawStats {\n",
     "export function draw(ctx: CanvasRenderingContext2D, s: Scene): DrawStats {\n"
     "  if (typeof requestAnimationFrame !== 'undefined') requestAnimationFrame(() => undefined);\n")],
     [TS]),
    ('M20', 'the level of detail never drops to dots', [(RENDER,
     "lod: s.keys.length > LOD_NODES ? 'dots' : 'full'",
     "lod: 'full' as 'full' | 'dots'")],
     [TS]),
    ('M21', 'the import graph read from the working tree, not the stored payload', [(GRAPH,
     "        payload = _payload(i.payload_sha256, read)",
     "        payload = dict(_payload(i.payload_sha256, read))\n"
     "        payload['files'] = [f for f in payload['files']\n"
     "                            if __import__('os').path.exists(r.path + '/' + f)]")],
     [Q + 'test_the_repository_graph_goes_one_level_down_and_keeps_outside_ends']),
    ('M22', 'an inferred "same plan" edge between sibling tasks', [(GRAPH,
     "        if e.depends_on:\n",
     "        for t in rows.where(conn, E.Task, plan_id=e.plan_id):\n"
     "            _edge(out, me, 'Task.depends_on', 'task',\n"
     "                  t.entity.id if t.entity.id != e.id else None)\n"
     "        if e.depends_on:\n")],
     [Q + 'test_every_edge_is_a_recorded_column_or_relation_row']),
    ('M23', 'the graph route writes', [(ROUTES,
     "    with req.api.db.read() as conn:\n        return 200, graph.world_graph(conn, focus, depth, limit)",
     "    req.run(commands.create_mission, {'title': 'written by a read', 'objective': 'x'},\n"
     "            keyed=False)\n"
     "    with req.api.db.read() as conn:\n        return 200, graph.world_graph(conn, focus, depth, limit)")],
     [R + 'test_the_graph_routes_write_nothing']),
    ('M24', 'an edge lifted to the top instead of the nearest visible ancestor', [(MODEL,
     "  for (const a of ancestors(m, k)) if (vis.has(a)) return a;",
     "  const all = ancestors(m, k);\n"
     "  if (all.length && vis.has(all[all.length - 1])) return all[all.length - 1];")],
     [TS]),
    ('M25', "focus + context dims the focus's neighbours", [(MODEL,
     "  for (const x of around(drawn, k)) out.add(x.other);\n",
     "")],
     [TS]),
    ('M26', 'collapse leaves the grandchildren visible', [(MODEL,
     "    if (ancestors(m, k).every((a) => expanded.has(a))) out.add(k);",
     "    const p = m.parentOf.get(k);\n    if (!p || expanded.has(p)) out.add(k);")],
     [TS]),
    ('M27', 'what the cap cut goes uncounted', [(GRAPH,
     "        'hidden': [{'parent': {'kind': pk[0], 'id': pk[1]}, 'kind': k, 'count': n}\n"
     "                   for (pk, k), n in sorted(hidden.items())],",
     "        'hidden': [],")],
     [Q + 'test_the_cap_holds_and_hidden_counts_what_it_cut']),
    ('M28', 'a refresh re-places the nodes already placed', [(LAYOUT,
     "    const p = inp.prev?.get(k);",
     "    const p = undefined as Point | undefined;")],
     [TS]),
    ('M29', 'a stale import graph shown as current', [(GRAPH,
     "                stale=r.architecture_state == 'STALE' or r.last_revision != i.revision)",
     "                stale=False)")],
     [Q + 'test_stale_not_inspected_and_missing_payload_are_said_not_guessed']),
    ('M30', 'execution frames stop making the graph stale', [(RULES,
     '  "execution": [\n    "/v1/world/graph**",\n',
     '  "execution": [\n')],
     [TS]),
    ('M31', 'labels no longer redacted', [(GRAPH,
     "    s = redact(' '.join(str(text or '').split()))",
     "    s = ' '.join(str(text or '').split())")],
     [Q + 'test_labels_are_redacted_one_line_and_capped']),
    ('M32', 'an ended execution counted as live', [(MODEL,
     "if (n.kind === 'execution' && n.machine && n.state && isActive(n.machine, n.state)) out.add(keyOf(n));",
     "if (n.kind === 'execution' && n.machine && n.state) out.add(keyOf(n));")],
     [TS]),
    ('M33', 'the canvas drawn on a phone', [(WIDE,
     "export const MIN_WIDTH = 600;",
     "export const MIN_WIDTH = 300;")],
     [E2E + 'test_below_600_px_the_relations_list_is_the_view']),
    # ── the post-audit round (gate §22 F1-F6, D3, the 390 px regression) ──
    ('M34', 'a superseded plan version drawn like a current one (F5)', [(ENC,
     "  if (kind === 'plan' && machine && state && present(machine, state).cls === 'inactive') return '--text-3';\n",
     "")],
     [TS]),
    ('M35', 'the pin key does nothing (F1)', [(KEYS,
     "      return { walk: w, command: 'pin' };",
     "      return { walk: w, command: null };")],
     [TS]),
    ('M36', 'the mirror never says a node is pinned (F1)', [(MIRROR,
     "pinned: pinned.has(k) };",
     "pinned: false };")],
     [TS]),
    ('M37', 'slow frames never degrade an animation (F2)', [(LOOP,
     "      if (this.slow >= SLOW_FRAMES) this.degraded = true;",
     "      if (this.slow >= SLOW_FRAMES * 1000) this.degraded = true;")],
     [TS]),
    ('M38', 'a degraded frame still draws its pulses (F2)', [(RENDER,
     "  if (s.degraded || !s.pulse.size) return;",
     "  if (!s.pulse.size) return;")],
     [TS]),
    ('M39', 'the static layer redrawn on every frame (F3)', [(RENDER,
     "  const stale = !layer.sig ||",
     "  const stale = true || !layer.sig ||")],
     [TS]),
    ('M40', 'the pulse map part of the static layer, so a pulse redraws everything (F3)', [(RENDER,
     "  return [s.model, s.keys,",
     "  return [s.pulse, s.model, s.keys,")],
     [TS]),
    ('M41', 'closing the inspector leaves focus on the page heading (F4)', [(APPTSX,
     "      const back = closed ? document.querySelector<HTMLElement>('main .graph-canvas') : null;",
     "      const back = closed && false ? document.querySelector<HTMLElement>('main .graph-canvas') : null;")],
     [E2E + 'test_closing_the_inspector_returns_to_the_canvas_and_a_pin_is_never_stored']),
    ('M42', 'a live edge pulses on every frame, no rate limit (F6)', [(MODEL,
     "  return now - (last.get(d.id) ?? -Infinity) < PULSE_EVERY_MS ? null : d;",
     "  return d;")],
     [TS]),
    ('M43', 'a pulse under reduced motion (F6)', [(MODEL,
     "  if (reduced || !subject ||",
     "  if (!subject ||")],
     [TS]),
    ('M46', 'the frame after a degraded animation never comes, so its labels stay dropped (F2)', [(LOOP,
     "      this.last = null;\n      this.request();",
     "      this.last = null;")],
     [TS]),
    ('M47', 'the static layer never copied to the canvas (F3)', [(RENDER,
     "    ctx.drawImage(layer.ctx.canvas, 0, 0);\n",
     "")],
     [TS, E2E + 'test_zoom_fit_and_the_loop_parking']),
]


def _build():
    r = subprocess.run(['npm', 'run', 'build'], cwd=APP, capture_output=True, text=True,
                       timeout=mutate_p11.TIMEOUT_S, shell=os.name == 'nt')
    if r.returncode:
        raise SystemExit('the SPA does not build:\n' + r.stdout[-2000:] + r.stderr[-2000:])


def _run(tests, fail_fast=True):
    """(returncode, output) of the guarding tests: pytest ids and node test files."""
    node = [t[5:] for t in tests if t.startswith('node:')]
    py = [t for t in tests if not t.startswith('node:')]
    out, code = '', 0
    env = dict(mutate_p11._ENV, ARCHEUS_E2E='1')
    try:
        if py:
            r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                                *(['-x'] if fail_fast else []), *sorted(set(py))], cwd=ROOT,
                               capture_output=True, text=True, encoding='utf-8', errors='replace',
                               timeout=mutate_p11.TIMEOUT_S, env=env)
            out, code = out + r.stdout, code or r.returncode
        if node and not (fail_fast and code):
            r = subprocess.run(['node', '--experimental-strip-types', '--no-warnings', '--test', '--test-reporter=tap',
                                *sorted(set(node))], cwd=APP, capture_output=True, text=True,
                               encoding='utf-8', errors='replace',
                               timeout=mutate_p11.TIMEOUT_S, shell=os.name == 'nt')
            out, code = out + r.stdout, code or r.returncode
    except subprocess.TimeoutExpired:
        return 1, 'timed out'
    return code, out


def _needs_build(tests):
    return any('/e2e/' in t for t in tests)


def run(selected=()):
    chosen = [m for m in MUTATIONS if not selected or m[0] in selected]
    for _mid, _what, edits, _tests in chosen:          # every snippet checked before any run
        mutate_p11._apply(edits)
    if any(_needs_build(m[3]) for m in chosen):
        _build()
    code, out = _run([t for m in chosen for t in m[3]], fail_fast=False)
    if code:
        raise SystemExit('the guarding tests fail on the unmutated tree; fix them first:\n%s' % out[-6000:])
    survived, killed = [], []
    for mid, what, edits, tests in chosen:
        files = mutate_p11._apply(edits)
        build = _needs_build(tests)
        try:
            for path, (_src, mutated) in files.items():
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(mutated)
            if build:
                _build()
            code, out = _run(tests)
            caught = code != 0
            # the failing test that names this mutant, else the first: a kill is
            # auditable by name (a mutant that does not parse never gets here)
            fails = [f.strip() for f in re.findall(
                r'^(FAILED \S+|\s*not ok \d+ - .+|timed out)$', out, re.M)]
            own = [f for f in fails if re.search(r'\b%s\b' % mid, f)]
            how = ' <- ' + (own or fails)[0] if caught and fails else ''
        finally:
            for path, (src, _mutated) in files.items():
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(src)
                mutate_p11._drop_pyc(path)
            if build:
                _build()
        (killed if caught else survived).append(mid)
        print('%-5s %-8s %s%s' % (mid, 'killed' if caught else 'SURVIVED', what, how),
              flush=True)
    print('\n%d/%d killed' % (len(killed), len(killed) + len(survived)))
    return 1 if survived else 0


if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))
