import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, run_flow, ESC

from claude_sessions import cluster_spec as _spec
from claude_sessions import connections


def _mkfile(base, rel, content=''):
    p = os.path.join(base, rel.replace('/', os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(content)
    return p


def _ids(g):
    return {n['id'] for n in g['nodes']}


def _dep_set(g):
    return {(e['source'], e['target']) for e in g['dep_edges']}


def _by_id(g, nid):
    return next(n for n in g['nodes'] if n['id'] == nid)


# ── hierarchy ────────────────────────────────────────────────

def test_hierarchy_nodes_parent_totals(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'lib/core.py', 'X=1\n')
    _mkfile(actual, 'lib/util.py', 'Y=2\n')
    _mkfile(actual, 'app/main.py', 'Z=3\n')
    g = connections.build_hierarchy(actual, folder)
    ids = _ids(g)
    assert 'root:' in ids and 'dir:lib' in ids and 'dir:app' in ids
    assert 'file:lib/core.py' in ids and 'file:app/main.py' in ids   # file leaves
    assert _by_id(g, 'dir:lib')['parent'] == 'root:'
    assert _by_id(g, 'file:lib/core.py')['parent'] == 'dir:lib'
    assert _by_id(g, 'dir:lib')['total_files'] == 2
    assert _by_id(g, 'root:')['total_files'] == 3       # whole tree counted


def test_file_dep_python(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'lib/__init__.py', '')
    _mkfile(actual, 'lib/core.py', 'X=1\n')
    _mkfile(actual, 'app/main.py', 'from lib import core\n')
    g = connections.build_hierarchy(actual, folder)
    assert ('file:app/main.py', 'file:lib/core.py') in _dep_set(g)


def test_file_dep_csharp(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('cs')
    _mkfile(actual, 'core/A.cs', 'namespace App.Core { class A {} }\n')
    _mkfile(actual, 'web/B.cs', 'using App.Core;\nnamespace App.Web { class B {} }\n')
    g = connections.build_hierarchy(actual, folder)
    assert ('file:web/B.cs', 'file:core/A.cs') in _dep_set(g)


def test_file_dep_cpp(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('cpp')
    _mkfile(actual, 'src/main.cpp', '#include "../inc/util.h"\n')
    _mkfile(actual, 'inc/util.h', '#pragma once\n')
    g = connections.build_hierarchy(actual, folder)
    assert ('file:src/main.cpp', 'file:inc/util.h') in _dep_set(g)


def test_rank_and_top_repos(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'big/a.py', 'x=1\n')
    _mkfile(actual, 'big/b.py', 'y=1\n')
    _mkfile(actual, 'small/c.py', 'z=1\n')
    g = connections.build_hierarchy(actual, folder)
    tops = connections.top_repos(g)
    assert tops and tops[0]['label'] == 'big'           # most files first


# ── cache ────────────────────────────────────────────────────

def test_cache_roundtrip(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'a/x.py', 'x=1\n')
    g1 = connections.build_hierarchy(actual, folder)
    cache = os.path.join(actual, '.archeus', connections._CACHE_NAME)
    assert os.path.isfile(cache)
    g2 = connections.build_hierarchy(actual, folder)            # served from cache
    assert g2['meta']['signature'] == g1['meta']['signature']
    # adding a file changes the signature → fresh build
    _mkfile(actual, 'a/y.py', 'y=1\n')
    g3 = connections.build_hierarchy(actual, folder)
    assert g3['meta']['signature'] != g1['meta']['signature']
    assert g3['meta']['counts']['files'] == 2


# ── the cage ─────────────────────────────────────────────────

def test_the_cage_really_is_a_geodesic_icosahedron():
    """The cage's faces are DERIVED from adjacency rather than read off a
    hardcoded face list, so a wrong tolerance quietly builds a different solid —
    and a wrong-but-plausible cage is exactly what a string assertion cannot
    see. So run the real JS and count.

    12 vertices, 30 edges, and the degree histogram is the proof it is the
    right solid and not merely the right totals: EVERY vertex of an icosahedron
    has exactly five neighbours, so a histogram with a 6 in it means the
    minimum-separation adjacency picked up a second ring.

    It used to be the once-subdivided cage — 42 vertices, 120 edges, the 12
    originals at degree 5 and the 30 new midpoints at 6 — and that went with
    the 3D: 120 strokes over a hull is the reference's fine mesh and it is also
    what made a cluster read as a ball of wool at every size the graph actually
    draws one.

    Skips without node. Local runs have it; the pytest CI job does not, which is
    why the shape is also pinned by string in test_stage.py."""
    import json
    import shutil
    import subprocess
    import tempfile

    if not shutil.which('node'):
        import pytest
        pytest.skip('node not available')

    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', 'connections.py'),
        encoding='utf-8').read()
    # the cage block asserts its own counts against the spec, so the harness
    # has to supply the spec — the page gets it substituted in as
    # __CLUSTER_JSON__, which is not a thing node knows about
    js = 'const CL = {FRAME_NODES: %d, FRAME_EDGES: %d};\n' % (
        _spec.FRAME_NODES, _spec.FRAME_EDGES)
    js += src[src.index('const PHI=1.6180339887;'):src.index('function drawCluster(')]
    js += """
console.log(JSON.stringify({v: FV.length, e: FE.length,
  unit: FV.every(v => Math.abs(Math.hypot(v[0],v[1],v[2]) - 1) < 1e-9),
  deg: (() => {const d = new Array(FV.length).fill(0);
    for (const [a,b] of FE) {d[a]++; d[b]++;}
    return [Math.min(...d), Math.max(...d), d.filter(x => x === 5).length];})()}));
"""
    fd, path = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(js)
        out = subprocess.run(['node', path], capture_output=True, text=True)
    finally:
        os.remove(path)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got['v'] == _spec.FRAME_NODES and got['e'] == _spec.FRAME_EDGES, got
    assert got['unit'], 'a vertex is off the circumsphere'
    assert got['deg'] == [5, 5, _spec.FRAME_NODES], got


def test_the_cage_costs_little_enough_to_raise_the_dot_fallback_back():
    """It cost 120 strokes plus a halo pass and an interior cloud, all of them
    on the CPU, and the dot fallback came down from 250 nodes to 180 to pay for
    it. A cage is thirty strokes and twelve joints now — what the platonic
    solid before it cost — so the threshold goes back up. Cost is the reason
    this number exists, so it has to move when the cost does."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', 'connections.py'),
        encoding='utf-8').read()
    assert 'const dod=VARR.length<=250;' in src, 'the fallback did not go back up'
    # gated on APPARENT size, not model radius. `r` is in graph units and the
    # view zooms, so `r >= 12` drew a 120-edge cage plus a 90-point cloud into
    # an 8px disc at low zoom — a solid burr — and skipped both on a hull
    # filling the screen at high zoom. `px` is `r * view.k`, which is the
    # number the decision is actually about.
    # ...and there is no interior cloud left to gate: the population inside a
    # hull, the beads on its surface and the two-stroke glass frame were all
    # part of the 3D reading, and a 2D canvas draws the coarse frame and its
    # twelve junctions now. What survives is the RULE the gate expressed —
    # decide on APPARENT size, never on model radius, because `r` is in graph
    # units and the view zooms.
    assert 'const px=r*view.k;' in src, 'the cluster is not sized in screen px'
    assert 'if(px>=44){' not in src, 'the interior cloud is back'
    # NO gradient inside a cluster, and the rule is stricter than it was
    # because there is nothing left that needs one. It used to allow exactly
    # one — the lit centre, where a white middle running out through the
    # cluster's own chord genuinely cannot be three flat discs — and forbid a
    # second, because a createRadialGradient per hull VERTEX is 42 across 180
    # nodes, 7,500 allocations a frame. The centre went with the 3D, so the
    # allowance goes with it.
    dc = src.split('function drawCluster(')[1].split('function draw()')[0]
    assert dc.count('createRadialGradient(') == 0, \
        'a gradient allocation inside the cluster'
    # ...and the one loop over the cage's vertices allocates nothing at all
    i = dc.index('for(const p of P)')
    assert 'createRadialGradient(' not in dc[i:], 'a gradient per junction'


# ── HTML ─────────────────────────────────────────────────────

def test_render_html_self_contained(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'a/x.py', 'x=1\n')
    html = connections.render_html(connections.build_hierarchy(actual, folder))
    for needle in ('<canvas', 'const CODE', 'id="search"', 'expanded', 'id="fit"', 'drawCluster'):
        assert needle in html, needle
    assert 'http://' not in html and 'https://' not in html
    assert '<script src=' not in html


def test_render_html_escapes_injection(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'a/x.py', 'x=1\n')
    g = connections.build_hierarchy(actual, folder)
    g['nodes'].append({'id': 'x', 'label': '</script><b>pwn', 'parent': 'root:',
                       'type': 'dir', 'own_files': 0, 'total_files': 0, 'repo': 'x',
                       'depth': 1, 'rank': 0})
    html = connections.render_html(g)
    assert '<\\/script>' in html
    assert html.count('</script>') == 1


def test_write_and_open(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'a/x.py', 'x=1\n')
    g = connections.build_hierarchy(actual, folder)
    p = connections.write_graph_html(g, actual, folder)
    assert p and os.path.isfile(p)
    opened = []
    monkeypatch.setattr(os, 'startfile', lambda x: opened.append(x), raising=False)
    ok, err = connections.open_graph(p)
    assert ok is True and err == '' and opened == [p]


# ── TUI ──────────────────────────────────────────────────────

def test_connections_screen_renders(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'a/x.py', 'x=1\n')
    monkeypatch.setattr(os, 'startfile', lambda x: None, raising=False)
    _res, cap, _ = run_flow(monkeypatch, ESC, connections.connections_screen,
                            actual, folder, 'alpha')
    assert 'ARCHITECTURE' in cap.plain
    assert 'Files' in cap.plain


def test_build_output_is_not_indexed(monkeypatch, tmp_path):
    """mkdocs writes `site/` and the walk had no reason to skip it, so build
    output became a memory unit — a paid Claude call and a rule file spent on
    generated JavaScript nobody edits."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    _mkfile(actual, 'src/app.py', 'x = 1\n')
    _mkfile(actual, 'site/assets/javascripts/bundle.js', 'var a=1;')
    g = connections.build_hierarchy(actual, folder)
    ids = _ids(g)
    assert 'dir:site' not in ids and not [i for i in ids if i.startswith('file:site/')], \
        'generated build output was indexed'
    assert 'dir:src' in ids
